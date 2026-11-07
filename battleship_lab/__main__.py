"""Minimal local strategy import and battle CLI."""
import argparse
import json
from .simulation import Battle, Bot, RoundConfig
from .strategies import StrategyProcess, import_strategy, run_imported
from .opponents import LEVELS, Opponent, opponent_loadout


class RandomShooter(Bot):
    def on_state(self, state):
        ships = [s for s in state["you"]["ships"] if not s["sunk"]]
        return {"ship": self.rng.choice(ships)["ship"], "dir": self.rng.uniform(0, 360),
                "elev": self.rng.uniform(15, 75), "power": self.rng.randint(1, 5)}


def main():
    parser = argparse.ArgumentParser(description="Import and run a strategy using the local approximation")
    parser.add_argument("strategy", help="Path to strategy.py")
    parser.add_argument("--store", default="strategy_versions")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--round", choices=("round1", "round2", "final"), default="round1")
    parser.add_argument("--difficulty", choices=tuple(LEVELS), default="easy")
    parser.add_argument("--teams", type=int, choices=range(2, 21), default=None)
    args = parser.parse_args()
    try:
        version = import_strategy(args.strategy, args.store)
        config = RoundConfig.preset(args.round)
        teams = args.teams or config.seats
        purchases = {s:opponent_loadout(config,args.difficulty,s) for s in 'ABCDEFGHIJKLMNOPQRST'[1:teams]}
        battle = Battle(args.seed, seats=teams, config=config, purchases=purchases)
        opponents = {s: Opponent(args.difficulty, f"{args.seed}:bot:{s}") for s in battle.seats if s != "A"}
        with StrategyProcess(version, seed=f"{args.seed}:bot:A") as strategy:
            if strategy.last_status != "ready":
                print(json.dumps({"version": version.name, "engine_kind": battle.engine_kind, "strategy_events": strategy.events}))
                return 1
            result = run_imported(battle, strategy, opponents)
        result["version"] = version.name
        result["opponent_implementation"] = "local_approximation"
        print(json.dumps(result))
        return 0
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
