"""Seeded, paired local benchmark; reports uncertainty without claiming official parity."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
from .opponents import LEVELS, Opponent, opponent_loadout
from .simulation import BOOSTERS, Battle, RoundConfig
from .strategies import StrategyProcess, import_strategy
from .diagnostics import EvidenceRecorder, diagnose, benchmark_diagnostics


def seed_pool(pool="development", count=100, master_seed=0):
    if pool not in ("development", "holdout") or type(count) is not int or not 1 <= count <= 1000:
        raise ValueError("Choose development/holdout and 1–1000 matches")
    parity = int(pool == "holdout")
    return [2 * int.from_bytes(hashlib.sha256(f"{master_seed}:{i}".encode()).digest()[:8], "big") + parity for i in range(count)]


def mean_ci(values):
    if not values:
        return {"mean": None, "ci95": [None, None], "n": 0}
    mean = statistics.mean(values)
    margin = 1.96 * statistics.stdev(values) / math.sqrt(len(values)) if len(values) > 1 else None
    return {"mean": mean, "ci95": [mean-margin, mean+margin] if margin is not None else [None, None], "n": len(values)}


def win_ci(wins):
    if not wins:
        return {"rate": None, "ci95": [None, None], "n": 0}
    n, p, z = len(wins), statistics.mean(wins), 1.96
    denominator = 1 + z*z/n
    centre = (p + z*z/(2*n))/denominator
    radius = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n))/denominator
    return {"rate": p, "ci95": [max(0, centre-radius), min(1, centre+radius)], "n": n}


def run_match(version, seed, teams=None, round_name="round1", level="medium", loadout=None):
    config = RoundConfig.preset(round_name)
    teams = teams or config.seats
    purchases = {s: opponent_loadout(config, level, s) for s in "ABCDEFGHIJKLMNOPQRST"[1:teams]}
    battle = Battle(seed, seats=teams, config=config, purchases={**purchases, "A": dict(loadout or {})})
    opponents = {s: Opponent(level, f"{seed}:bot:{s}") for s in battle.seats if s != "A"}
    recorder = EvidenceRecorder(battle)
    with StrategyProcess(version, seed=f"{seed}:bot:A") as strategy:
        while not battle.finished:
            actions = {}
            for label, seat in battle.seats.items():
                if seat.connected and not seat.eliminated:
                    actions[label] = (strategy if label == "A" else opponents[label]).on_state(battle.state(label))
            recorder.begin(battle, actions.get("A"), strategy.last_status, strategy.events[-1].get("detail","") if strategy.events else "")
            battle.step(actions)
            recorder.finish(battle)
        result = battle.results()
        row = next((r for r in result["ranking"] if r["seat"] == "A"), None)
        return {"seed": seed, "abandoned": result["abandoned"], "win": int(row["rank"] == 1) if row else None,
                "rank": row["rank"] if row else None, "score": row["score"] if row else None,
                "wasted_shots": row["wasted"] if row else None,
                "timeouts": sum(e["status"] == "timeout" for e in strategy.events),
                "errors": [e for e in strategy.events if e["status"] not in ("ready", "ok")],
                "diagnostics": diagnose(recorder.events), "replay": recorder.replay()}


METRICS = ("rank", "score", "wasted_shots", "timeouts")


def summarize(records):
    valid = [r for r in records if not r["abandoned"]]
    return {"matches": len(records), "abandoned": len(records)-len(valid),
            "win_rate": win_ci([r["win"] for r in valid]),
            **{metric: mean_ci([r[metric] for r in (records if metric == "timeouts" else valid)]) for metric in METRICS},
            "timeouts_total": sum(r["timeouts"] for r in records)}


def benchmark(versions, matches=100, teams=None, round_name="round1", level="medium", pool="development", master_seed=0, loadout=None, progress=None):
    if teams is not None and (type(teams) is not int or not 2 <= teams <= 20):
        raise ValueError("teams must be 2–20")
    if level not in LEVELS:
        raise ValueError("Unknown difficulty")
    rounds = ["round1", "round2", "final"] if round_name == "all" else [round_name]
    for name in rounds:
        config = RoundConfig.preset(name)
        budget = config.points
        for booster, count in (loadout or {}).items():
            if booster not in config.unlocked or type(count) is not int or not 0 <= count <= 99:
                raise ValueError("Invalid loadout for selected round")
            budget -= BOOSTERS[booster] * count
        if budget < 0:
            raise ValueError("Loadout exceeds round budget")
    versions = list(versions)
    if not versions or len({str(Path(v).resolve()) for v in versions}) != len(versions):
        raise ValueError("Supply distinct strategy versions")
    seeds = seed_pool(pool, matches, master_seed)
    report = {"engine_kind": "local_approximation", "opponent_implementation": "local_approximation",
              "opponent": LEVELS[level], "teams": teams, "pool": pool, "master_seed": master_seed,
              "seeds": seeds, "loadout": dict(loadout or {}),
              "ci_method": "Wilson win rate; normal approximation for means and paired deltas (95%)",
              "rounds": {}}
    completed = 0
    total = len(rounds)*len(versions)*len(seeds)
    for name in rounds:
        runs = []
        for version in versions:
            records = []
            for seed in seeds:
                records.append(run_match(version, seed, teams, name, level, loadout))
                completed += 1
                if progress:
                    progress(completed, total)
            runs.append({"version": str(Path(version).resolve()), "records": records})
        for run in runs:
            run["summary"] = summarize(run["records"])
        comparisons = []
        for i, left in enumerate(runs):
            for right in runs[i+1:]:
                pairs = [(a,b) for a,b in zip(left["records"], right["records"]) if not a["abandoned"] and not b["abandoned"]]
                comparisons.append({"left": left["version"], "right": right["version"], "direction": "left minus right",
                                    "paired_matches": len(pairs),
                                    **{m: mean_ci([a[m]-b[m] for a,b in pairs]) for m in ("win", *METRICS)}})
        report["rounds"][name] = {"teams":teams or RoundConfig.preset(name).seats,"config":RoundConfig.preset(name).view(),"strategies": runs, "comparisons": comparisons}
    report["diagnostics"] = benchmark_diagnostics(report)
    return report


def main():
    parser = argparse.ArgumentParser(description="Local approximate strategy benchmark")
    parser.add_argument("strategies", nargs="+")
    parser.add_argument("--store", default="strategy_versions")
    parser.add_argument("--matches", type=int, default=100)
    parser.add_argument("--teams", type=int, default=None)
    parser.add_argument("--round", choices=("round1", "round2", "final", "all"), default="round1")
    parser.add_argument("--difficulty", choices=tuple(LEVELS), default="medium")
    parser.add_argument("--pool", choices=("development", "holdout"), default="development")
    parser.add_argument("--master-seed", type=int, default=0)
    parser.add_argument("--loadout", default="{}", help='JSON booster counts, e.g. {"flare":2,"cluster":2}')
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        seed_pool(args.pool, args.matches, args.master_seed)
        if args.teams is not None and not 2 <= args.teams <= 20:
            raise ValueError("teams must be 2–20")
        loadout = json.loads(args.loadout)
        if not isinstance(loadout, dict):
            raise ValueError("loadout must be a JSON object")
        versions = [import_strategy(s, args.store) for s in args.strategies]
        report = benchmark(versions, args.matches, args.teams, args.round, args.difficulty, args.pool, args.master_seed, loadout)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"report": str(args.output), "engine_kind": report["engine_kind"]}))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
