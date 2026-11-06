from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from battleship_lab import Battle, RoundConfig
from battleship_lab.benchmark import benchmark, mean_ci, run_match, seed_pool, summarize, win_ci
from battleship_lab.opponents import LEVELS, Opponent
from battleship_lab.strategies import import_strategy


SOURCE = "from arena_sdk import Bot\nclass MyBot(Bot):\n def on_state(self,s):\n  return dict(ship=next(x['ship'] for x in s['you']['ships'] if not x['sunk']),dir=90,elev=45,power=3)\n"


class OpponentTests(unittest.TestCase):
    def test_all_levels_legal_and_reproducible(self):
        battle = Battle(12, seats=2, config=RoundConfig.preset("final"))
        for level in LEVELS:
            a, b = Opponent(level, 7), Opponent(level, 7)
            state = battle.state("A")
            for _ in range(3):
                left, right = a.on_state(state), b.on_state(state)
                self.assertEqual(left, right)
                self.assertIsNotNone(battle._valid(battle.seats["A"], left))
            self.assertEqual(a.implementation, "local_approximation")

    def test_hunters_prioritize_revealed_cells(self):
        battle = Battle(11)
        state = battle.state("A")
        state["you"]["ships"] = [{"ship": "carrier", "cells": [[20,20]], "sunk": False}]
        state["revealed"] = [[20,25]]
        for level in ("medium", "hard", "expert", "extreme"):
            bot = Opponent(level)
            action = bot.on_state(state)
            from battleship_lab import landing
            self.assertEqual(landing((20,20), action["dir"], action["elev"], action["power"]), (20,25))

    def test_flare_and_probability(self):
        state = Battle(3).state("A")
        state["you"]["boosters"]["flare"] = 1
        for level in ("hard", "expert", "extreme"):
            self.assertEqual(Opponent(level).on_state(state)["action"], "flare")
        self.assertGreater(Opponent._probability((20,20), set(), {(20,21)}),
                           Opponent._probability((20,20), set(), set()))
        with self.assertRaises(ValueError):
            Opponent("unknown")


class BenchmarkTests(unittest.TestCase):
    def test_seed_pools_disjoint_stable_and_nested(self):
        development = seed_pool(count=1000)
        holdout = seed_pool("holdout", 1000)
        self.assertEqual(len(set(development)), 1000)
        self.assertFalse(set(development) & set(holdout))
        self.assertEqual(seed_pool(), development[:100])
        self.assertNotEqual(seed_pool(master_seed=1), development[:100])
        for count in (0, 1001, True):
            with self.assertRaises(ValueError):
                seed_pool(count=count)

    def test_statistics(self):
        interval = win_ci([1]*100)
        self.assertEqual(interval["rate"], 1)
        self.assertLess(interval["ci95"][0], 1)
        self.assertAlmostEqual(interval["ci95"][1], 1)
        self.assertEqual(mean_ci([1,2,3])["mean"], 2)
        self.assertEqual(mean_ci([])["n"], 0)
        row = dict(abandoned=True, timeouts=1)
        summary = summarize([row])
        self.assertIsNone(summary["win_rate"]["rate"])
        self.assertEqual(summary["timeouts_total"], 1)

    def test_paired_all_rounds_same_seed_and_options(self):
        calls = []
        def match(version, seed, teams, name, level, loadout):
            calls.append((str(version),seed,teams,name,level))
            return dict(seed=seed, abandoned=False, win=1, rank=1, score=5 if str(version)=="a" else 3, wasted_shots=2, timeouts=0, errors=[])
        with patch("battleship_lab.benchmark.run_match", side_effect=match):
            report = benchmark(["a", "b"], matches=100, teams=20, round_name="all", level="extreme")
        self.assertEqual(len(calls), 600)
        for name, result in report["rounds"].items():
            self.assertEqual([x[1] for x in calls if x[0]=="a" and x[3]==name],
                             [x[1] for x in calls if x[0]=="b" and x[3]==name])
            comparison = result["comparisons"][0]
            self.assertEqual(comparison["score"]["mean"], 2)
            self.assertEqual(comparison["score"]["ci95"], [2,2])
            self.assertEqual(comparison["paired_matches"], 100)

    def test_validation_and_maximum_matches(self):
        for kwargs in ({"teams":1}, {"teams":21}, {"round_name":"bad"}, {"level":"bad"}, {"pool":"bad"}, {"loadout":{"flare":1}}):
            with self.assertRaises(ValueError):
                benchmark(["a"], **kwargs)
        with patch("battleship_lab.benchmark.run_match", return_value=dict(abandoned=False,win=0,rank=2,score=0,wasted_shots=1,timeouts=0)) as runner:
            benchmark(["a"], matches=1000)
            self.assertEqual(runner.call_count, 1000)

    def test_pair_excludes_abandoned_and_preserves_timeouts(self):
        def match(version, seed, *args):
            abandoned = str(version) == "a"
            return dict(seed=seed, abandoned=abandoned, win=None if abandoned else 1,
                        rank=None if abandoned else 1, score=None if abandoned else 0,
                        wasted_shots=None if abandoned else 0, timeouts=1, errors=[])
        with patch("battleship_lab.benchmark.run_match", side_effect=match):
            report = benchmark(["a", "b"])
        result = report["rounds"]["round1"]
        self.assertEqual(result["comparisons"][0]["paired_matches"], 0)
        self.assertEqual(result["strategies"][0]["summary"]["abandoned"], 100)
        self.assertEqual(result["strategies"][0]["summary"]["timeouts_total"], 100)

    def test_round_loadout_forwarded(self):
        row = dict(abandoned=False,win=0,rank=2,score=0,wasted_shots=0,timeouts=0)
        with patch("battleship_lab.benchmark.run_match", return_value=row) as runner:
            report = benchmark(["a"], round_name="round2", loadout={"flare":2,"cluster":2})
            self.assertEqual(runner.call_args.args[-1], {"flare":2,"cluster":2})
            self.assertEqual(report["loadout"], {"flare":2,"cluster":2})
        with self.assertRaises(ValueError):
            benchmark(["a"], round_name="round2", loadout={"flare":3})

    def test_real_match_twenty_teams_and_timeout_count(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/"strategy.py").write_text(SOURCE)
            version = import_strategy(root/"strategy.py", root/"store")
            with patch("battleship_lab.benchmark.RoundConfig.preset", return_value=RoundConfig(tick_cap=2)):
                result = run_match(version, 42, teams=20, level="easy")
            self.assertFalse(result["abandoned"])
            self.assertTrue(1 <= result["rank"] <= 20)
            self.assertEqual(result["timeouts"], 0)
            (root/"strategy.py").write_text("from arena_sdk import Bot\nclass MyBot(Bot):\n def on_state(self,s):\n  while True: pass\n")
            version = import_strategy(root/"strategy.py", root/"store")
            with patch("battleship_lab.benchmark.RoundConfig.preset", return_value=RoundConfig(tick_cap=1)):
                result = run_match(version, 42)
            self.assertEqual(result["timeouts"], 1)

    def test_real_hundred_short_matches(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/"strategy.py").write_text(SOURCE)
            version = import_strategy(root/"strategy.py", root/"store")
            # Integration uses a one-tick cap; not evidence of strategy quality.
            with patch("battleship_lab.benchmark.RoundConfig.preset", return_value=RoundConfig(tick_cap=1)):
                report = benchmark([version], matches=100)
            summary = report["rounds"]["round1"]["strategies"][0]["summary"]
            self.assertEqual(summary["matches"], 100)
            self.assertEqual(summary["win_rate"]["n"], 100)
            self.assertEqual(summary["timeouts_total"], 0)


if __name__ == "__main__":
    unittest.main()
