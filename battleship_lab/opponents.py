"""Private-observation local approximations; no official opponent code is bundled."""
import math
from .simulation import Bot, landing

LEVELS = {"easy": "Random Shooter", "medium": "Hunt Target", "hard": "Parity Hunter",
          "expert": "Probability Hunter", "extreme": "Competitive Optimizer"}


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
        if self.level != "easy":
            candidates |= neighbours | revealed
        candidates = [c for c in sorted(candidates) if c not in own and
                      (self.level == "easy" or c not in tried) and
                      (self.level not in ("hard", "expert", "extreme") or c in neighbours | revealed or sum(c) % 2 == 0)]
        self.rng.shuffle(candidates)
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
        if self.level in ("hard", "expert", "extreme") and not hits and not revealed and boosters["flare"]:
            action["action"] = "flare"
        elif self.level == "extreme" and target is not None:
            if boosters["cluster"] and (target in neighbours or target in revealed):
                action["action"] = "cluster"
            # Surface attack only along a known cell and a clear friendly line.
            elif boosters["torpedo"] and target in revealed:
                origin = next(s["cells"][0] for s in ships if s["ship"] == action["ship"])
                dr, dc = target[0]-origin[0], target[1]-origin[1]
                if (dr == 0 or dc == 0) and not any(
                    (r == origin[0] == target[0] and min(origin[1],target[1]) < c < max(origin[1],target[1])) or
                    (c == origin[1] == target[1] and min(origin[0],target[0]) < r < max(origin[0],target[0])) for r,c in own):
                    action.update(action="torpedo", dir=math.degrees(math.atan2(dc, -dr)) % 360)
        if action.get("action") not in ("torpedo", "teleport"):
            origin = next(s["cells"][0] for s in ships if s["ship"] == action["ship"])
            flight = 2 * action["power"] * 4 * math.sin(math.radians(action["elev"])) / 9.8
            self.previous = (origin, dict(action), flight)
        return action
