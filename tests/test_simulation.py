import unittest
from battleship_lab import Battle, Bot, RoundConfig, Ship, landing


def action(kind=None, **values):
    result = dict(ship="destroyer", dir=90, elev=0, power=1)
    if kind:
        result["action"] = kind
    result.update(values)
    return result


class SimulationTests(unittest.TestCase):
    def battle(self, count=2):
        b = Battle(seed=42, seats=count, config=RoundConfig.preset("final"))
        b.wind = (0, 0)
        for i, seat in enumerate(b.seats.values()):
            seat.ships = [Ship("destroyer", [(10 + i * 5, 10), (10 + i * 5, 11)])]
            seat.boosters = dict(flare=2, cluster=2, torpedo=2, teleport=2)
        return b

    def test_physics(self):
        self.assertEqual(landing((20, 20), 0, 45, 1), (18, 20))
        self.assertEqual(landing((20, 20), 90, 45, 1), (20, 22))
        self.assertEqual(landing((20, 20), 180, 45, 1), (22, 20))
        self.assertEqual(landing((20, 20), 270, 45, 1), (20, 18))
        self.assertEqual(landing((20, 20), 0, 90, 1, (1, -1)), (21, 19))
        self.assertEqual(landing((2.5, 3.5), 0, 0, 1), (2, 4))

    def test_seeded_placement_and_wind(self):
        a, b = Battle(7), Battle(7)
        self.assertEqual(a.wind, b.wind)
        self.assertEqual(a.state("A"), b.state("A"))
        cells = [(owner, ship, c) for owner, seat in a.seats.items() for ship in seat.ships for c in ship.cells]
        self.assertEqual(len(cells), 170)
        for owner, ship, c in cells:
            self.assertTrue(a.inside(c))
            for other_owner, other, d in cells:
                if ship is not other:
                    self.assertGreater(max(abs(c[0]-d[0]), abs(c[1]-d[1])), 1)
        self.assertTrue(all(-1 <= w <= 1 for w in a.wind))
        initial = a.wind
        a.step({})
        self.assertEqual(a.wind, initial)

    def test_twenty_seats(self):
        b = Battle(5, seats=20)
        self.assertEqual(sum(len(s.cells) for seat in b.seats.values() for s in seat.ships), 340)

    def test_config_and_budget(self):
        self.assertEqual(RoundConfig.preset("round1").unlocked, ())
        self.assertEqual(RoundConfig.preset("round2").unlocked, ("flare", "cluster"))
        b = Battle(config=RoundConfig.preset("final"), purchases={"A": {"torpedo": 2}}, carryover={"A": 4})
        self.assertEqual(b.remaining_points["A"], 0)
        for config, purchase in [(RoundConfig(), {"flare": 1}), (RoundConfig.preset("final"), {"torpedo": 2})]:
            with self.assertRaises(ValueError):
                Battle(config=config, purchases={"A": purchase})

    def test_invalid_actions(self):
        b = self.battle()
        for value in [None, {}, action(power=True), action(power=1.5), action(dir=float("nan")), action(elev=91), action(dir=-1), action(ship="missing"), action("unknown")]:
            self.assertIsNone(b._valid(b.seats["A"], value))
        self.assertIsNotNone(b._valid(b.seats["A"], action(reason="ignored", dir=360)))

    def test_self_hit_and_wreck(self):
        b = self.battle()
        b.step({"A": action()})
        self.assertEqual(b.seats["A"].shots[-1][2], "self_hit")
        b.step({"A": action()})
        self.assertEqual(b.seats["A"].shots[-1][2], "wreck")
        self.assertEqual(b.seats["A"].score, 0)
        self.assertEqual(b.seats["A"].wasted, 2)

    def test_miss_offboard(self):
        b = self.battle()
        b.step({"A": action(elev=45)})
        self.assertEqual(b.seats["A"].shots[-1][2], "miss")
        b.step({"A": action(dir=0, elev=45, power=5)})
        self.assertEqual(b.seats["A"].shots[-1][2], "off_board")

    def test_simultaneous_shared_hit_sink_and_history(self):
        b = self.battle(3)
        b.seats["A"].ships[0].cells = [(10, 8), (11, 8)]
        b.seats["B"].ships[0].cells = [(10, 12), (11, 12)]
        target = b.seats["C"].ships[0]
        target.cells = [(10, 10), (11, 10)]
        b.step({"A": action(elev=45), "B": action(dir=270, elev=45)})
        self.assertEqual([b.seats[s].score for s in "AB"], [1, 1])
        self.assertEqual([b.seats[s].shots[-1][2] for s in "AB"], ["hit", "hit"])
        b.step({"A": action("torpedo", dir=120)})
        self.assertTrue(target.sunk)
        self.assertEqual(b.seats["A"].score, 4)
        self.assertEqual(b.seats["B"].shots[0][2], "sunk")

    def test_mutual_sinking_still_fires(self):
        b = self.battle()
        b.seats["A"].ships[0].cells = [(10, 8), (11, 8)]
        b.seats["B"].ships[0].cells = [(10, 10), (11, 10)]
        b.step({"A": action("torpedo"), "B": action("torpedo", dir=270)})
        self.assertTrue(b.finished)
        self.assertFalse(b.abandoned)
        self.assertEqual([s.score for s in b.seats.values()], [4, 4])

    def test_torpedo_self_shield_and_wreck_skip(self):
        b = self.battle()
        b.seats["A"].ships.append(Ship("cruiser", [(10, 13), (11, 13), (12, 13)]))
        b.seats["B"].ships[0].cells = [(10, 16), (11, 16)]
        b.step({"A": action("torpedo")})
        self.assertEqual(b.seats["A"].wasted, 3)
        self.assertFalse(b.seats["B"].ships[0].sunk)
        b.step({"A": action("torpedo")})
        self.assertTrue(b.seats["B"].ships[0].sunk)
        self.assertEqual(b.seats["A"].score, 4)

    def test_torpedo_offboard(self):
        b = self.battle()
        b.step({"A": action("torpedo")})
        self.assertEqual(b.seats["A"].shots[-1], [10, b.config.cols, "off_board"])

    def test_flare(self):
        b = self.battle()
        b.seats["B"].ships[0].cells = [(10, 13), (10, 14)]
        b.step({"A": action("flare", elev=45)})
        self.assertEqual(b.state("A")["revealed"], [[10, 13], [10, 14]])
        self.assertEqual(b.state("B")["revealed"], [])
        self.assertEqual(b.seats["A"].wasted, 0)
        self.assertEqual(b.seats["A"].score, 0)
        b.step({"A": action("torpedo")})
        self.assertEqual(b.state("A")["revealed"], [])

    def test_cluster_exclusions(self):
        b = self.battle()
        b.seats["A"].shots.append([9, 12, "miss"])
        b.step({"A": action("cluster", elev=45)})
        cells = [tuple(s[:2]) for s in b.seats["A"].last_results]
        self.assertEqual(len(cells), 3)  # prior shot and own ship exclude two neighbours
        self.assertNotIn((9, 12), cells)
        self.assertNotIn((10, 11), cells)
        self.assertTrue(all(b.inside(c) for c in cells))

    def test_teleport_before_shots_preserves_holes(self):
        b = self.battle()
        a = b.seats["A"].ships[0]
        a.cells = [(15, 12), (15, 13)]
        a.holes.add((15, 13))
        b.step({"A": action("teleport"), "B": action(elev=45)})
        self.assertNotEqual(a.cells, [(15, 12), (15, 13)])
        self.assertEqual(a.holes, {a.cells[1]})
        self.assertEqual(b.seats["B"].shots[-1][2], "miss")
        self.assertEqual(b.seats["A"].shots, [])

    def test_empty_booster_fallback(self):
        b = self.battle()
        b.seats["A"].boosters["teleport"] = 0
        b.step({"A": action("teleport")})
        self.assertEqual(b.seats["A"].shots[-1][2], "self_hit")

    def test_same_tick_sink_bonus_to_each_shell(self):
        b = self.battle(3)
        b.seats["A"].ships[0].cells = [(10, 8), (11, 8)]
        b.seats["B"].ships[0].cells = [(10, 12), (11, 12)]
        target = b.seats["C"].ships[0]
        target.cells = [(10, 10), (11, 10)]
        target.holes.add((11, 10))
        b.step({"A": action(elev=45), "B": action(dir=270, elev=45)})
        self.assertEqual([b.seats[s].score for s in "AB"], [3, 3])
        self.assertTrue(b.seats["C"].eliminated)

    def test_self_sinking_awards_enemy_same_tick(self):
        b = self.battle()
        b.seats["A"].ships[0].cells = [(15, 12), (15, 13)]
        b.seats["A"].ships[0].holes.add((15, 13))
        b.step({"A": action(), "B": action(elev=45)})
        self.assertEqual(b.seats["A"].score, 0)
        self.assertEqual(b.seats["B"].score, 3)
        self.assertTrue(b.seats["A"].eliminated)

    def test_teleported_hit_history_still_updates(self):
        b = self.battle()
        b.seats["B"].ships[0].cells = [(10, 12), (10, 13)]
        b.step({"A": action(elev=45)})
        self.assertEqual(b.seats["A"].shots[0][2], "hit")
        b.step({"B": action("teleport")})
        target = b.seats["B"].ships[0]
        target.holes.update(target.cells)
        b.step({})
        self.assertEqual(b.seats["A"].shots[0][2], "sunk")

    def test_valid_action_resets_silent_streak(self):
        b = self.battle()
        for _ in range(7):
            b.step({})
        b.step({"A": action(), "B": action()})
        self.assertEqual(b.seats["A"].silent, 0)
        for _ in range(2):
            b.step({})
        self.assertTrue(b.seats["A"].connected)

    def test_silent_grace_disconnect_and_abandon(self):
        b = self.battle()
        for _ in range(7):
            b.step({})
        self.assertTrue(b.seats["A"].connected)
        b.step({})
        self.assertTrue(b.abandoned)
        self.assertEqual(b.results()["ranking"], [])

    def test_disconnected_ships_still_standing(self):
        b = self.battle()
        b.seats["B"].connected = False
        b.step({"A": action()})
        self.assertFalse(b.finished)

    def test_privacy_and_detached_state(self):
        b = self.battle()
        state = b.state("A")
        self.assertNotIn("wind", state)
        self.assertNotIn("seed", state)
        self.assertNotIn("B", state["you"])
        state["you"]["ships"][0]["cells"].clear()
        self.assertEqual(len(b.seats["A"].ships[0].cells), 2)

    def test_ranking_all_tiebreakers(self):
        b = self.battle()
        a, other = b.seats.values()
        for attribute, left, right in [("joined", True, False), ("score", 2, 1), ("wasted", 0, 1), ("last_sink", 1, None), ("last_point", 1, 2), ("first_point", 1, 2)]:
            setattr(a, attribute, left)
            setattr(other, attribute, right)
            self.assertEqual(b.results()["ranking"][0]["seat"], "A")
            setattr(other, attribute, left)
        self.assertEqual(b.results()["ranking"][0]["seat"], "A")

    def test_runner_exceptions_and_cap(self):
        class Broken(Bot):
            def on_state(self, state):
                raise ValueError("broken")
        b = self.battle()
        self.assertTrue(b.run({"A": Broken(), "B": Broken()})["abandoned"])
        c = self.battle()
        c.config.tick_cap = 1
        c.step({})
        self.assertTrue(c.finished)
        with self.assertRaises(RuntimeError):
            c.step({})

    def test_action_order_determinism(self):
        a, b = self.battle(), self.battle()
        a.step({"A": action("teleport"), "B": action("cluster", elev=45)})
        b.step({"B": action("cluster", elev=45), "A": action("teleport")})
        self.assertEqual(a.state("A"), b.state("A"))
        self.assertEqual(a.state("B"), b.state("B"))


if __name__ == "__main__":
    unittest.main()
