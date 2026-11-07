"""Rule-numbered regression cases derived from the supplied v1.5 PDF."""
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from battleship_lab import Battle, RoundConfig, Ship
from battleship_lab.opponents import Opponent, opponent_loadout
from battleship_lab.diagnostics import EvidenceRecorder, replay_frame
from battleship_lab.validation import validate_source, TEMPLATE
from battleship_lab.strategies import import_strategy


def action(kind='shot', **extra):
    return dict(ship='carrier', dir=90, elev=0, power=1, action=kind, **extra)


class RulebookV15Tests(unittest.TestCase):
    def fixture(self):
        b = Battle(73, seats=3, config=RoundConfig.preset('final'))
        b.wind = (0, 0)
        b.seats['A'].ships = [Ship('carrier', [(5, 1), (6, 1)])]
        b.seats['B'].ships = [Ship('carrier', [(5, 8), (6, 8)])]
        b.seats['C'].ships = [Ship('carrier', [(20, 20), (21, 20)])]
        b.seats['A'].boosters.update(torpedo=2, cluster=2, teleport=2, flare=2)
        return b

    def test_2_9_configs_boundaries_and_3_5_fleets(self):
        for name, size, count, groups, advance in (
                ('round1', 36, 10, 2, 6), ('round2', 28, 6, 2, 3), ('final', 28, 6, 1, 3)):
            b = Battle(20261106, config=RoundConfig.preset(name))
            view = b.config.view()
            self.assertEqual((view['map'], len(b.seats), view['groups'], view['advance']),
                             ({'rows':size,'cols':size}, count, groups, advance))
            self.assertEqual((view['tick_cap'],view['action_deadline_ms'],view['physics']['speed_per_power']), (120,500,4))
            for cell, inside in [((0,0),True),((size-1,size-1),True),((-1,0),False),((size,0),False),((0,size),False)]:
                self.assertEqual(b.inside(cell), inside)
            cells = [(ship,c) for seat in b.seats.values() for ship in seat.ships for c in ship.cells]
            self.assertEqual(len(cells), count*17)
            for ship,c in cells:
                self.assertTrue(b.inside(c))
                for other,d in cells:
                    if other is not ship:
                        self.assertGreater(max(abs(c[0]-d[0]),abs(c[1]-d[1])),1)

    def test_3_5_places_every_carrier_before_battleships(self):
        seen = []
        original = Battle._place
        def record(battle, length, rng, exclude=None):
            seen.append(length)
            return original(battle,length,rng,exclude)
        with patch.object(Battle,'_place',record):
            Battle(1)
        self.assertEqual(seen, [n for n in (5,4,3,3,2) for _ in range(10)])

    def test_7_15_torpedo_holed_stop_is_sunk_but_only_unhit_scores(self):
        b = self.fixture()
        b.seats['B'].ships[0].holes.add((5,8))
        b.step({'A':action('torpedo')})
        self.assertEqual(b.seats['A'].last_results, [[5,8,'sunk'],[6,8,'sunk']])
        self.assertEqual(b.seats['A'].score, 3)
        self.assertEqual(b.seats['B'].incoming, [[6,8,'sunk']])

    def test_7_16_friendly_holed_stop_shields_enemy(self):
        b = self.fixture()
        friendly = Ship('destroyer', [(5,4),(6,4)], {(5,4)})
        b.seats['A'].ships.append(friendly)
        b.step({'A':action('torpedo')})
        self.assertEqual(b.seats['A'].last_results, [[5,4,'self_hit'],[6,4,'self_hit']])
        self.assertEqual((b.seats['A'].score,b.seats['A'].wasted), (0,2))
        self.assertFalse(b.seats['B'].ships[0].sunk)

    def test_7_13_exact_corner_skips_side_cells(self):
        b = self.fixture()
        origin = b.seats['A'].ships[0]
        side = Ship('side',[(4,1)])
        diagonal = Ship('diagonal',[(4,2)])
        board = {(4,1):('B',side),(4,2):('C',diagonal)}
        self.assertEqual(b._ray(origin,45,board,{id(side):set(),id(diagonal):set()},28,28)[1], ('C',diagonal))

    def test_7_10_off_sea_cluster_still_strikes_eligible_neighbour(self):
        b = self.fixture()
        with patch('battleship_lab.simulation.landing',return_value=(-1,5)):
            b.step({'A':action('cluster')})
        self.assertEqual(b.seats['A'].last_results,[[-1,5,'off_board'],[0,5,'miss']])

    def test_7_12_flare_report_without_shot_record(self):
        b = self.fixture()
        with patch('battleship_lab.simulation.landing',return_value=(5,8)):
            b.step({'A':action('flare')})
        self.assertEqual(b.seats['A'].shots, [])
        self.assertEqual(b.seats['A'].last_results, [[5,8,'flare']])
        self.assertEqual(b.state('A')['revealed'], [[5,8],[6,8]])
        self.assertEqual(b.seats['A'].wasted,0)

    def test_7_19_teleport_excludes_old_location_and_no_space_stays(self):
        b = self.fixture()
        ship = b.seats['A'].ships[0]
        old = list(ship.cells)
        b.step({'A':action('teleport')})
        self.assertNotEqual(ship.cells,old)
        with patch.object(b,'_place',return_value=list(ship.cells)):
            b.step({'A':action('teleport')})
        self.assertEqual(b.seats['A'].boosters['teleport'],0)

    def test_12_6_independent_random_streams_and_private_view(self):
        a, b = self.fixture(), self.fixture()
        a.cluster_rng.random()
        a.step({'A':action('teleport')})
        b.step({'A':action('teleport')})
        self.assertEqual(a.state('A'),b.state('A'))
        cluster_state = a.cluster_rng.getstate()
        a.teleport_rng.random()
        self.assertEqual(a.cluster_rng.getstate(),cluster_state)
        private = a.state('B')
        a.seed = 999
        a.wind = (1,1)
        a.seats['A'].score += 10
        self.assertEqual(a.state('B'),private)

    def test_10_disconnect_is_final_and_abandon_suppresses_ranks(self):
        b = self.fixture()
        b.disconnect('A')
        self.assertFalse(b.join('A'))
        b.step({'A':action('torpedo')})
        self.assertEqual(b.seats['A'].shots,[])
        b.disconnect('B')
        b.disconnect('C')
        self.assertEqual(b.results()['reason'],'abandoned')
        self.assertEqual(b.results()['ranking'],[])

    def test_11_7_limits_aliases_and_library_shadowing(self):
        for prefix in ('import os as o\no.urandom(1)\n', 'from random import SystemRandom as R\nR()\n',
                       'from os import getrandom as r\nr(1)\n'):
            self.assertFalse(validate_source(prefix+TEMPLATE)['valid'])
        self.assertFalse(validate_source(TEMPLATE+'\n#'+ 'x'*262144)['valid'])
        self.assertTrue(validate_source('import numpy, scipy, networkx, sortedcontainers\n'+TEMPLATE)['valid'])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'strategy.py').write_text(TEMPLATE)
            (root/'random.py').write_text('x=1')
            with self.assertRaisesRegex(ValueError,'shadowing'):
                import_strategy(root/'strategy.py',root/'store')

    def test_real_all_rounds_official_seats_deterministic_replay(self):
        for name in ('round1','round2','final'):
            config = RoundConfig.preset(name)
            labels = 'ABCDEFGHIJ'[:config.seats]
            purchases = {s:opponent_loadout(config,'hard',s) for s in labels}
            replays = []
            for _ in range(2):
                b = Battle(20261106,config=config,purchases=purchases)
                bots = {s:Opponent('hard',f'20261106:bot:{s}') for s in labels}
                recorder = EvidenceRecorder(b)
                while not b.finished:
                    actions = {s:bots[s].on_state(b.state(s)) for s,seat in b.seats.items() if seat.connected and not seat.eliminated}
                    for s, value in actions.items():
                        self.assertIsNotNone(b._valid(b.seats[s],value))
                    recorder.begin(b,actions.get('A'))
                    b.step(actions)
                    recorder.finish(b)
                self.assertFalse(b.abandoned)
                self.assertEqual(len(b.results()['ranking']),config.seats)
                self.assertEqual(b.tick,120)
                replay = json.loads(json.dumps(recorder.replay()))
                self.assertEqual(replay_frame(replay,120)['config'],config.view())
                replays.append(replay)
            self.assertEqual(replays[0],replays[1])
