"""Private-observation local approximations; no official opponent code is bundled."""
import math
from .simulation import Bot, landing, BOOSTERS, Battle, Ship

LEVELS = {"easy": "Random Shooter", "medium": "Hunt Target", "hard": "Parity Hunter",
          "expert": "Probability Hunter", "extreme": "Competitive Optimizer"}


def opponent_loadout(config, level, seat="B", carryover=0):
    """Pre-battle policy; only public market settings enter this decision."""
    budget = config.points + carryover
    result = {}
    # Diversify final loadouts across seats: neither premium booster fits
    # together in the preset ten-point budget.
    preferred = (["torpedo", "cluster"] if ord(seat) % 2 == 0 else
                 ["teleport", "flare", "cluster"]) if "torpedo" in config.unlocked else ["flare", "cluster"]
    for kind in preferred:
        if kind in config.unlocked and budget >= BOOSTERS[kind]:
            count = budget // BOOSTERS[kind] if kind == "cluster" else 1
            result[kind] = count
            budget -= count * BOOSTERS[kind]
    return result


class Opponent(Bot):
    implementation = "local_approximation"

    def __init__(self, level="easy", seed=0):
        super().__init__()
        if level not in LEVELS:
            raise ValueError("Unknown opponent difficulty")
        self.level = level
        self.rng.seed(seed)
        self.wind = [0., 0.]
        self.samples = 0
        self.previous = None

    def _learn(self, state):
        if self.previous and state["last_results"]:
            origin, action, flight = self.previous
            cell = state["last_results"][0]
            baseline = landing(origin, action["dir"], action["elev"], action["power"])
            if flight > .1:
                self.samples += 1
                for axis in (0, 1):
                    estimate = (cell[axis] - baseline[axis]) / flight
                    self.wind[axis] += (estimate - self.wind[axis]) / self.samples
        self.previous = None

    def _aim(self, ships, target):
        for ship in self.rng.sample(ships, len(ships)):
            origin = ship["cells"][0]
            dr, dc = target[0] - origin[0], target[1] - origin[1]
            elev = None
            for _ in range(4):
                distance = math.hypot(dr, dc)
                if distance > 400 / 9.8:
                    elev = None
                    break
                elev = math.asin(min(1, distance * 9.8 / 400)) / 2
                flight = 40 * math.sin(elev) / 9.8
                dr = target[0] - origin[0] - self.wind[0] * flight
                dc = target[1] - origin[1] - self.wind[1] * flight
            if elev is not None:
                return {"ship": ship["ship"], "dir": math.degrees(math.atan2(dc, -dr)) % 360,
                        "elev": math.degrees(elev), "power": 5}
        return None

    @staticmethod
    def _probability(cell, blocked, hits):
        # Count compatible straight placements covering this candidate cell.
        total = 0
        for length in (2, 3, 3, 4, 5):
            for dr, dc in ((0, 1), (1, 0)):
                for offset in range(length):
                    cells = {(cell[0] + (i-offset)*dr, cell[1] + (i-offset)*dc) for i in range(length)}
                    if all(0 <= r < 40 and 0 <= c < 40 for r, c in cells) and not cells & blocked:
                        total += 1 + 15 * len(cells & hits)
        return total

    def on_state(self, state):
        self._learn(state)
        ships = [s for s in state["you"]["ships"] if not s["sunk"]]
        shots = state["your_shots"]
        tried = {tuple(s[:2]) for s in shots if s[2] != "flare"}
        own = {tuple(c) for s in state["you"]["ships"] for c in s["cells"]}
        hits = {tuple(s[:2]) for s in shots if s[2] == "hit"}
        blocked = own | {tuple(s[:2]) for s in shots if s[2] in ("miss", "sunk", "wreck", "self_hit")}
        revealed = {tuple(c) for c in state["revealed"]}
        neighbours = {(r+dr, c+dc) for r, c in hits for dr, dc in ((-1,0),(1,0),(0,-1),(0,1))}
        candidates = {(self.rng.randrange(40), self.rng.randrange(40)) for _ in range(80)}
        candidates |= revealed
        if self.level != "easy":
            candidates |= neighbours
        candidates = [c for c in sorted(candidates) if 0 <= c[0] < 40 and 0 <= c[1] < 40 and c not in own and
                      (self.level == "easy" or c not in tried) and
                      (self.level not in ("hard", "expert", "extreme") or c in neighbours | revealed or sum(c) % 2 == 0)]
        self.rng.shuffle(candidates)
        candidates.sort(key=lambda c: c in revealed, reverse=True)
        if self.level in ("expert", "extreme"):
            candidates.sort(key=lambda c: (c in revealed, self._probability(c, blocked, hits)), reverse=True)
        elif self.level != "easy":
            candidates.sort(key=lambda c: (c in revealed, c in neighbours), reverse=True)
        action = None
        target = None
        for target in candidates:
            action = self._aim(ships, target)
            if action:
                break
        if action is None:
            action = {"ship": ships[0]["ship"], "dir": self.rng.uniform(0, 360), "elev": 45, "power": 5}
        boosters = state["you"]["boosters"]
        threatened = [s for s in ships if s.get("holed")]
        if boosters.get("teleport", 0) and threatened:
            # Preserve a damaged firing platform, using only our own damage.
            action.update(action="teleport", ship=max(threatened, key=lambda s: len(s["holed"])/len(s["cells"]))["ship"])
        elif boosters.get("torpedo", 0) and (revealed or hits):
            known = revealed | hits
            for firing in ships:
                origin = firing["cells"][0]
                for cell in sorted(known):
                    direction = math.degrees(math.atan2(cell[1]-origin[1], origin[0]-cell[0])) % 360
                    # Use the same grid traversal as the referee, but with ONLY
                    # private friendly cells and observed targets as obstacles.
                    source = Ship(firing["ship"], [tuple(c) for c in firing["cells"]])
                    board = {tuple(c): ("own", source if s is firing else Ship(s["ship"], [tuple(x) for x in s["cells"]]))
                             for s in ships for c in s["cells"]}
                    target_ship = Ship("observed", [cell])
                    board[cell] = ("enemy", target_ship)
                    holes = {id(s): set() for _, s in board.values()}
                    _, target_hit = Battle._ray(source, direction, board, holes)
                    if target_hit and target_hit[0] == "enemy":
                        action.update(action="torpedo", ship=firing["ship"], dir=direction)
                        break
                if action.get("action") == "torpedo":
                    break
        if "action" not in action and not hits and not revealed and boosters.get("flare", 0):
            action["action"] = "flare"
        if "action" not in action and boosters.get("cluster", 0) and target is not None:
            # Prefer a lead; spend remaining ammunition before expiration.
            if target in neighbours | revealed or state["tick"] >= state["config"]["tick_cap"] - boosters["cluster"]:
                action["action"] = "cluster"
        if action.get("action") not in ("torpedo", "teleport"):
            origin = next(s["cells"][0] for s in ships if s["ship"] == action["ship"])
            flight = 2 * action["power"] * 4 * math.sin(math.radians(action["elev"])) / 9.8
            self.previous = (origin, dict(action), flight)
        return action
