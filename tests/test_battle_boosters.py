"""Real local simulations plus targeted private-observation booster scenarios."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import unittest
from unittest.mock import Mock

from battleship_lab.simulation import Battle, RoundConfig, Ship, BOOSTERS
from battleship_lab.opponents import LEVELS, Opponent, opponent_loadout
from battleship_lab.web import Session


class BoosterBattleTests(unittest.TestCase):
    def test_all_opponents_all_rounds_complete_real_simulations(self):
        for round_name in ("round1", "round2", "final"):
            for level in LEVELS:
                with self.subTest(round=round_name, level=level):
                    config = RoundConfig.preset(round_name)
                    purchases = {s: opponent_loadout(config, level, s) for s in "ABCD"}
                    b = Battle(17, seats=4, config=config, purchases=purchases)
                    bots = {s: Opponent(level, f"17:bot:{s}") for s in b.seats}
                    while not b.finished:
                        actions = {s: bots[s].on_state(b.state(s)) for s, seat in b.seats.items()
                                   if seat.connected and not seat.eliminated}
                        for s, action in actions.items():
                            self.assertIsNotNone(b._valid(b.seats[s], action))
                            if action.get("action") in BOOSTERS:
                                self.assertGreater(b.seats[s].boosters[action["action"]], 0)
                                self.assertIn(action["action"], config.unlocked)
                        b.step(actions)
                    self.assertFalse(b.abandoned)
                    self.assertTrue(all(s.connected for s in b.seats.values()))
                    for s in b.seats:
                        for kind in BOOSTERS:
                            self.assertEqual(b.purchases[s][kind], b.seats[s].boosters[kind] + b.booster_stats[s][kind]["used"])
                    self.assertEqual(len(b.results()["ranking"]), 4)

    def test_each_level_activates_each_supported_booster_using_private_state(self):
        for level in LEVELS:
            for kind in BOOSTERS:
                with self.subTest(level=level, booster=kind):
                    b = Battle(9, config=RoundConfig.preset("final"), purchases={"A": {kind: 1}})
                    b.wind = (0, 0)
                    b.seats["A"].ships = [Ship("carrier", [(20,20),(20,21),(20,22),(20,23),(20,24)])]
                    b.seats["B"].ships = [Ship("destroyer", [(15,20),(15,21)])]
                    if kind == "teleport":
                        b.seats["A"].ships[0].holes.add((20,21))
                    if kind in ("cluster", "torpedo"):
                        b.seats["A"].revealed.add((15,20))
                    state = b.state("A")
                    self.assertEqual(set(state), {"tick","deadline_ms","seats","you","your_shots","last_results","revealed","config"})
                    action = Opponent(level, 3).on_state(state)
                    self.assertEqual(action.get("action"), kind)
                    self.assertIsNotNone(b._valid(b.seats["A"], action))
                    b.step({"A": action})
                    self.assertEqual(b.seats["A"].boosters[kind], 0)
                    self.assertEqual(b.booster_stats["A"][kind]["used"], 1)
                    self.assertEqual(b.events[0]["kind"], kind)
                    if kind == "torpedo":
                        self.assertTrue(b.seats["B"].ships[0].sunk)
                        self.assertEqual(b.booster_stats["A"][kind]["points"], 4)
                    if kind == "teleport":
                        self.assertEqual(len(b.seats["A"].ships[0].holes), 1)
                        self.assertNotEqual(b.events[0]["from_cells"], b.events[0]["cells"])

    def test_invalid_actions_and_empty_inventory_do_not_consume_boosters(self):
        b = Battle(1, config=RoundConfig.preset("round2"), purchases={"A":{"cluster":1}})
        action = dict(ship="carrier", dir=90, elev=30, power=True, action="cluster")
        b.step({"A":action})
        self.assertEqual(b.seats["A"].boosters["cluster"], 1)
        self.assertEqual(b.events, [])
        action["power"] = 5
        b.step({"A":action})
        self.assertEqual(b.booster_stats["A"]["cluster"]["used"], 1)
        b.step({"A":action})
        self.assertEqual(b.events[0]["kind"], "shot")
        self.assertEqual(b.booster_stats["A"]["cluster"]["used"], 1)
        for config, purchase in (("round1",{"cluster":1}), ("round2",{"torpedo":1}), ("final",{"torpedo":2})):
            with self.assertRaises(ValueError):
                Battle(config=RoundConfig.preset(config), purchases={"A":purchase})
        for credit in (-1, True, 1.5):
            with self.assertRaises(ValueError):
                Battle(config=RoundConfig.preset("final"), carryover={"A":credit})

    def test_duplicate_steps_consume_once_and_replay_is_frozen(self):
        b = Battle(1, config=RoundConfig.preset("round2"), purchases={"A":{"flare":2}})
        worker = Mock(last_status="ok", events=[])
        worker.on_state.return_value = dict(ship="carrier",dir=90,elev=30,power=5,action="flare")
        opponent = Mock()
        opponent.on_state.return_value = None
        session = Session(b, worker, {"B":opponent}, "test")
        session.snapshot()
        with ThreadPoolExecutor(max_workers=2) as pool:
            frames = list(pool.map(session.step, [0, 0]))
        self.assertEqual(frames[0], frames[1])
        self.assertEqual(b.tick, 1)
        self.assertEqual(b.seats["A"].boosters["flare"], 1)
        saved = deepcopy(session.frames[1])
        session.step(1)
        self.assertEqual(session.frames[1], saved)
        self.assertEqual(session.frames[2]["teams"][0]["boosters"]["stats"]["flare"]["used"], 2)

    def test_torpedo_avoids_friendly_blocker(self):
        b = Battle(1, config=RoundConfig.preset("final"), purchases={"A":{"torpedo":1}})
        b.seats["A"].ships = [Ship("carrier",[(20,20)]),Ship("destroyer",[(17,20)])]
        b.seats["B"].ships = [Ship("destroyer",[(15,20),(15,21)])]
        b.seats["A"].revealed.add((15,20))
        action = Opponent("easy", 1).on_state(b.state("A"))
        self.assertEqual(action.get("action"), "torpedo")
        self.assertEqual(action["ship"], "destroyer")

    def test_flare_landing_is_not_a_previous_shot_for_cluster(self):
        b = Battle(1, config=RoundConfig.preset("round2"), purchases={"A":{"cluster":1}})
        b.wind = (0, 0)
        b.seats["A"].ships = [Ship("destroyer",[(20,20),(20,21)])]
        b.seats["B"].ships = [Ship("destroyer",[(30,30),(30,31)])]
        b.seats["A"].shots.append([19,20,"flare"])
        b.step({"A":dict(ship="destroyer",dir=90,elev=0,power=1,action="cluster")})
        self.assertIn([19,20,"miss"], b.seats["A"].last_results)

    def test_saved_benchmark_replay_retains_all_team_boosters_and_paths(self):
        from battleship_lab.diagnostics import EvidenceRecorder, replay_frame
        b = Battle(7, config=RoundConfig.preset("round2"), purchases={s:{"flare":1} for s in "AB"})
        recorder = EvidenceRecorder(b)
        actions = {s:dict(ship="carrier",dir=90,elev=30,power=5,action="flare") for s in "AB"}
        recorder.begin(b, actions["A"])
        b.step(actions)
        recorder.finish(b)
        frame = replay_frame(recorder.replay(), 1)
        self.assertEqual({t["seat"] for t in frame["traces"]}, {"A","B"})
        self.assertEqual({e["kind"] for e in frame["events"]}, {"flare"})
        self.assertTrue(all(t["boosters"]["stats"]["flare"]["used"]==1 for t in frame["teams"]))


if __name__ == "__main__":
    unittest.main()
