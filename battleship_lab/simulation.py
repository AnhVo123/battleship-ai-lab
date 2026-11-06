"""Document-derived local approximation. See SIMULATION.md for uncertainties."""
from copy import deepcopy
from dataclasses import dataclass, field
import math
import random
import time

BOOSTERS = {"flare": 4, "cluster": 1, "torpedo": 7, "teleport": 4}
FLEET = {"carrier": 5, "battleship": 4, "cruiser": 3, "submarine": 3, "destroyer": 2}


@dataclass
class RoundConfig:
    name: str = "round1"
    tick_cap: int = 120
    points: int = 0
    unlocked: tuple = ()

    @classmethod
    def preset(cls, name):
        if name == "round1":
            return cls()
        if name == "round2":
            return cls(name, 120, 10, ("flare", "cluster"))
        if name == "final":
            return cls(name, 120, 10, tuple(BOOSTERS))
        raise ValueError("Unknown round")

    def view(self):
        return {"map": {"rows": 40, "cols": 40}, "fleet": dict(FLEET),
                "tick_cap": self.tick_cap, "action_deadline_ms": 500,
                "physics": {"gravity": 9.8, "speed_per_power": 4, "power_max": 5, "wind_max": 1.0},
                "boosters": {"unlocked": list(self.unlocked), "costs": dict(BOOSTERS),
                             "flare_zone": 7, "cluster_extra": 3, "points": self.points},
                "scoring": {"hit": 1, "sink_bonus": "ship_length", "survival_per_cell": 0}}


@dataclass
class Ship:
    name: str
    cells: list
    holes: set = field(default_factory=set)

    @property
    def sunk(self):
        return len(self.holes) == len(self.cells)


@dataclass
class Seat:
    ships: list = field(default_factory=list)
    boosters: dict = field(default_factory=lambda: dict.fromkeys(BOOSTERS, 0))
    joined: bool = True
    connected: bool = True
    eliminated: bool = False
    silent: int = 0
    score: int = 0
    wasted: int = 0
    first_point: int | None = None
    last_point: int | None = None
    last_sink: int | None = None
    shots: list = field(default_factory=list)
    last_results: list = field(default_factory=list)
    incoming: list = field(default_factory=list)
    revealed: set = field(default_factory=set)


class Bot:
    """Local Bot base; accepts the same MyBot.on_state(state) interface."""
    def __init__(self):
        self.rng = random.Random()

    def on_state(self, state):
        raise NotImplementedError


def landing(origin, direction, elevation, power, wind=(0, 0)):
    bearing, angle = math.radians(direction), math.radians(elevation)
    speed = power * 4
    flight = 2 * speed * math.sin(angle) / 9.8
    return (round(origin[0] + (-speed * math.cos(angle) * math.cos(bearing) + wind[0]) * flight),
            round(origin[1] + (speed * math.cos(angle) * math.sin(bearing) + wind[1]) * flight))


class Battle:
    engine_kind = "local_approximation"

    def __init__(self, seed=0, seats=2, config=None, purchases=None, carryover=None, joined=None):
        self.config = deepcopy(config or RoundConfig.preset("round1"))
        if self.config.tick_cap < 1:
            raise ValueError("tick_cap must be positive")
        labels = list("ABCDEFGHIJKLMNOPQRST"[:seats]) if isinstance(seats, int) else list(seats)
        if not 2 <= len(labels) <= 20 or len(set(labels)) != len(labels) or any(s not in "ABCDEFGHIJKLMNOPQRST" or len(s) != 1 for s in labels):
            raise ValueError("Require 2–20 distinct seats A–T")
        self.seed = seed
        self.rng = random.Random(f"{seed}:actions")
        placement = random.Random(f"{seed}:placement")
        wind_rng = random.Random(f"{seed}:wind")
        self.wind = (wind_rng.uniform(-1, 1), wind_rng.uniform(-1, 1))
        self.tick = 0
        self.finished = self.abandoned = False
        self.seats = {s: Seat(joined=joined is None or s in joined, connected=joined is None or s in joined) for s in sorted(labels)}
        self._shot_targets = {}
        self.remaining_points = {}
        self.purchases = {}
        self.booster_stats = {label: {kind: {"used": 0, "points": 0, "hits": 0, "revealed": 0, "sinks": 0} for kind in BOOSTERS} for label in labels}
        self.events = []
        for label, seat in self.seats.items():
            credit = (carryover or {}).get(label, 0)
            if type(credit) is not int or credit < 0 or (credit and self.config.name != "final"):
                raise ValueError("Invalid carryover")
            budget = self.config.points + credit
            for booster, count in (purchases or {}).get(label, {}).items():
                if booster not in self.config.unlocked or type(count) is not int or count < 0:
                    raise ValueError("Invalid booster purchase")
                budget -= BOOSTERS[booster] * count
                seat.boosters[booster] = count
            if budget < 0:
                raise ValueError("Booster budget exceeded")
            self.remaining_points[label] = budget
            self.purchases[label] = dict(seat.boosters)
            for name, length in FLEET.items():
                seat.ships.append(Ship(name, self._place(length, placement)))

    @staticmethod
    def inside(cell):
        return 0 <= cell[0] < 40 and 0 <= cell[1] < 40

    def _place(self, length, rng, exclude=None):
        occupied = [cell for seat in self.seats.values() for ship in seat.ships if ship is not exclude for cell in ship.cells]
        forbidden = {(r + dr, c + dc) for r, c in occupied for dr in (-1, 0, 1) for dc in (-1, 0, 1)}
        candidates = []
        for dr, dc in ((0, 1), (1, 0)):
            for r in range(40 - (length - 1) * dr):
                for c in range(40 - (length - 1) * dc):
                    cells = [(r + i * dr, c + i * dc) for i in range(length)]
                    if all(cell not in forbidden for cell in cells):
                        candidates.append(cells)
        if not candidates:
            raise RuntimeError("No free ship placement")
        return rng.choice(candidates)

    def _valid(self, seat, action):
        if not isinstance(action, dict):
            return None
        identifier = action.get("ship")
        if type(identifier) is int:
            ship = seat.ships[identifier] if 0 <= identifier < len(seat.ships) else None
            ship = ship if ship is not None and not ship.sunk else None
        else:
            ship = next((s for s in seat.ships if type(identifier) is str and s.name == identifier and not s.sunk), None)
        if ship is None or type(action.get("power")) is not int or not 1 <= action["power"] <= 5:
            return None
        for key, maximum in (("dir", 360), ("elev", 90)):
            value = action.get(key)
            if type(value) not in (int, float) or not 0 <= value <= maximum or not math.isfinite(value):
                return None
        if action.get("action", "shot") not in ("shot", *BOOSTERS):
            return None
        return ship

    def state(self, label):
        seat = self.seats[label]
        unhit = {c for owner, other in self.seats.items() if owner != label for ship in other.ships for c in ship.cells if c not in ship.holes}
        return deepcopy({"tick": self.tick + 1, "deadline_ms": 500, "seats": list(self.seats),
                         "you": {"slot": label, "score": seat.score, "boosters": seat.boosters,
                                 "ships_alive": sum(not s.sunk for s in seat.ships),
                                 "incoming_shots": seat.incoming,
                                 "ships": [{"ship": s.name, "cells": [list(c) for c in s.cells],
                                            "holed": [list(c) for c in sorted(s.holes)], "sunk": s.sunk} for s in seat.ships]},
                         "your_shots": seat.shots, "last_results": seat.last_results,
                         "revealed": [list(c) for c in sorted(seat.revealed & unhit)], "config": self.config.view()})

    def step(self, actions):
        if self.finished:
            raise RuntimeError("Battle finished")
        self.tick += 1
        self.events = []
        before = {label: (seat.score, len(seat.revealed)) for label, seat in self.seats.items()}
        accepted = []
        for label, seat in self.seats.items():
            seat.last_results = []
            if not seat.connected or seat.eliminated:
                continue
            action = actions.get(label)
            ship = self._valid(seat, action)
            if ship is None:
                if self.tick > 5:
                    seat.silent += 1
                    if seat.silent >= 3:
                        seat.connected = False
                continue
            seat.silent = 0
            kind = action.get("action", "shot")
            if kind != "shot":
                if seat.boosters[kind]:
                    seat.boosters[kind] -= 1
                else:
                    kind = "shot"
            accepted.append((label, ship, action, kind))
            self.events.append({"seat": label, "kind": kind, "ship": ship.name,
                                "aim": {k: action[k] for k in ("dir", "elev", "power")},
                                "origin": list(ship.cells[0]), "from_cells": list(ship.cells)})
        for label, ship, action, kind in accepted:
            if kind == "teleport":
                indices = [i for i, c in enumerate(ship.cells) if c in ship.holes]
                ship.cells = self._place(len(ship.cells), self.rng, ship)
                ship.holes = {ship.cells[i] for i in indices}
        board = {c: (owner, ship) for owner, seat in self.seats.items() for ship in seat.ships for c in ship.cells}
        old_holes = {id(ship): set(ship.holes) for seat in self.seats.values() for ship in seat.ships}
        events = []
        for label, ship, action, kind in accepted:
            if kind == "teleport":
                continue
            cell = landing(ship.cells[0], action["dir"], action["elev"], action["power"], self.wind)
            event = next(e for e in self.events if e["seat"] == label)
            event["landing"] = list(cell)
            if kind == "flare":
                for c, (owner, target) in board.items():
                    if owner != label and c not in old_holes[id(target)] and abs(c[0] - cell[0]) <= 3 and abs(c[1] - cell[1]) <= 3:
                        self.seats[label].revealed.add(c)
                self._record(label, cell, "flare")
                continue
            if kind == "torpedo":
                cell, target = self._ray(ship, action["dir"], board, old_holes)
                event["landing"] = list(cell)
                if target is None:
                    events.append((label, cell, None, None))
                else:
                    owner, target_ship = target
                    events.extend((label, c, owner, target_ship) for c in target_ship.cells if c not in old_holes[id(target_ship)])
                continue
            cells = [cell]
            if kind == "cluster":
                previous = {(s[0], s[1]) for s in self.seats[label].shots if s[2] != "flare"}
                neighbours = [(cell[0] + dr, cell[1] + dc) for dr, dc in ((-1, 0), (0, 1), (1, 0), (0, -1))]
                eligible = [c for c in neighbours if self.inside(c) and c not in previous and (c not in board or board[c][0] != label)]
                cells += self.rng.sample(eligible, min(3, len(eligible)))
            for c in cells:
                owner, target = board.get(c, (None, None))
                events.append((label, c, owner, target))
        for label, cell, owner, target in events:
            if target is not None and cell not in old_holes[id(target)]:
                target.holes.add(cell)
        for label, cell, owner, target in events:
            result = "off_board" if not self.inside(cell) else "miss"
            if target is not None:
                if cell in old_holes[id(target)]:
                    result = "wreck"
                elif owner == label:
                    result = "self_hit"
                else:
                    result = "sunk" if target.sunk else "hit"
                    seat = self.seats[label]
                    seat.score += 1 + (len(target.cells) if target.sunk else 0)
                    seat.first_point = seat.first_point or self.tick
                    seat.last_point = self.tick
                    if target.sunk:
                        seat.last_sink = self.tick
                if cell not in old_holes[id(target)]:
                    self.seats[owner].incoming.append([*cell, result])
            entry = self._record(label, cell, result)
            if target is not None:
                self._shot_targets[id(entry)] = target
        # A torpedo receives one sink bonus, rather than one per holed cell.
        for label, ship, action, kind in accepted:
            if kind == "torpedo":
                own_events = [e for e in events if e[0] == label and e[3] is not None and e[2] != label]
                if own_events:
                    self.seats[label].score -= (len(own_events) - 1) * len(own_events[0][3].cells)
        for seat in self.seats.values():
            for shot in seat.shots:
                target = self._shot_targets.get(id(shot))
                if shot[2] == "hit" and target and target.sunk:
                    shot[2] = "sunk"
            seat.eliminated = all(s.sunk for s in seat.ships)
        self.abandoned = not any(s.connected for s in self.seats.values())
        self.finished = self.abandoned or sum(not s.eliminated for s in self.seats.values()) <= 1 or self.tick >= self.config.tick_cap
        for event, (label, ship, action, kind) in zip(self.events, accepted):
            seat = self.seats[label]
            event.update(cells=list(ship.cells), results=deepcopy(seat.last_results),
                         points=seat.score-before[label][0],
                         sunk_cells=[list(c) for target in {id(board[tuple(s[:2])][1]): board[tuple(s[:2])][1] for s in seat.last_results if s[2] == "sunk"}.values() for c in target.cells])
            if kind in BOOSTERS:
                stats = self.booster_stats[label][kind]
                stats["used"] += 1
                stats["points"] += event["points"]
                stats["hits"] += sum(s[2] in ("hit", "sunk") for s in seat.last_results)
                stats["revealed"] += len(seat.revealed)-before[label][1]
                stats["sinks"] += len({id(board.get(tuple(s[:2]), (None, None))[1]) for s in seat.last_results if s[2] == "sunk"})
        return self.results() if self.finished else None

    def _record(self, label, cell, result):
        seat = self.seats[label]
        entry = [*cell, result]
        seat.shots.append(entry)
        seat.last_results.append(entry.copy())
        seat.wasted += result in ("miss", "wreck", "off_board", "self_hit")
        return entry

    @staticmethod
    def _ray(ship, direction, board, old_holes):
        # Grid traversal through cell boundaries (ties cross both axes).
        angle = math.radians(direction)
        dr, dc = -math.cos(angle), math.sin(angle)
        dr = 0 if abs(dr) < 1e-12 else dr
        dc = 0 if abs(dc) < 1e-12 else dc
        r, c = ship.cells[0]
        tr = .5 / abs(dr) if dr else math.inf
        tc = .5 / abs(dc) if dc else math.inf
        while True:
            crossing = min(tr, tc)
            if tr <= crossing + 1e-12:
                r += 1 if dr > 0 else -1
                tr += 1 / abs(dr)
            if tc <= crossing + 1e-12:
                c += 1 if dc > 0 else -1
                tc += 1 / abs(dc)
            cell = (r, c)
            if not Battle.inside(cell):
                return cell, None
            target = board.get(cell)
            if target and target[1] is not ship and len(old_holes[id(target[1])]) != len(target[1].cells):
                return cell, target

    def traces(self):
        """Omniscient presentation data, never included in a bot observation."""
        traces = []
        for event in self.events:
            if event["kind"] == "teleport" or not event["results"]:
                continue
            origin, aim, contact = event["origin"], event["aim"], event["landing"]
            bearing, elev = math.radians(aim["dir"]), math.radians(aim["elev"])
            speed = aim["power"] * 4
            flight = 2*speed*math.sin(elev)/9.8
            points = []
            for i in range(21):
                t = flight*i/20
                points.append([origin[0]+(-speed*math.cos(elev)*math.cos(bearing)+self.wind[0])*t,
                               origin[1]+(speed*math.cos(elev)*math.sin(bearing)+self.wind[1])*t,
                               max(0, speed*math.sin(elev)*t-4.9*t*t)])
            if event["kind"] == "torpedo":
                points, flight = [[*origin, 0], [*contact, 0]], 0
            traces.append({"seat":event["seat"], "kind":event["kind"], "points":points,
                           "landing":list(contact), "result":event["results"][0][2], "flight_seconds":flight})
        return traces

    def results(self):
        if self.abandoned:
            return {"engine_kind": self.engine_kind, "abandoned": True, "ranking": []}
        def key(label):
            s = self.seats[label]
            return (not s.joined, -s.score, s.wasted,
                    s.last_sink if s.last_sink is not None else math.inf,
                    s.last_point if s.last_point is not None else math.inf,
                    s.first_point if s.first_point is not None else math.inf, label)
        return {"engine_kind": self.engine_kind, "abandoned": False,
                "ranking": [{"rank": i + 1, "seat": label, "score": self.seats[label].score,
                             "wasted": self.seats[label].wasted, "eliminated": self.seats[label].eliminated}
                            for i, label in enumerate(sorted(self.seats, key=key))]}

    def run(self, bots):
        for label, bot in bots.items():
            bot.rng = random.Random(f"{self.seed}:bot:{label}")
        while not self.finished:
            actions = {}
            for label, seat in self.seats.items():
                if not seat.connected or seat.eliminated or label not in bots:
                    continue
                start = time.perf_counter()
                try:
                    action = bots[label].on_state(self.state(label))
                    if time.perf_counter() - start <= .5:
                        actions[label] = action
                except Exception:
                    pass
            self.step(actions)
        return self.results()
