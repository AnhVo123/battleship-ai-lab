import importlib.util
import sys
import types
import unittest
from pathlib import Path
from battleship_lab.simulation import Bot, Battle, landing
from battleship_lab.validation import validate_source
from battleship_lab.strategies import StrategyProcess, import_strategy
import tempfile

sdk = types.ModuleType('arena_sdk')
sdk.Bot = Bot
sys.modules.setdefault('arena_sdk', sdk)
spec = importlib.util.spec_from_file_location('optimized_strategy', Path(__file__).parents[1] / 'examples/strategy.py')
strategy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(strategy)

class OptimizedStrategyTests(unittest.TestCase):
    def test_static_submission_contract(self):
        self.assertTrue(validate_source(Path(strategy.__file__).read_text(encoding='utf-8'))['valid'])

    def test_worker_twenty_ticks_no_invalid_actions_or_timeouts(self):
        with tempfile.TemporaryDirectory() as store:
            version = import_strategy(strategy.__file__, store)
            with StrategyProcess(version, seed='strategy-smoke') as worker:
                battle = Battle(42, seats=6)
                for _ in range(20):
                    action = worker.on_state(battle.state('A'))
                    self.assertEqual(worker.last_status, 'ok', worker.events[-1])
                    self.assertIsNotNone(battle._valid(battle.seats['A'], action))
                    battle.step({'A':action})
                    self.assertNotEqual(battle.seats['A'].shots[-1][2], 'self_hit')

    def test_inverse_physics(self):
        bot = strategy.MyBot()
        for wind in ((0,0),(-1,1),(.35,-.7)):
            for target in ((0,0),(39,39),(20,21),(4,22),(38,3)):
                for high in (False, True):
                    solved = bot._flight((20,20), target, 20, 9.8, wind, high)
                    if solved:
                        flight, elev, direction = solved
                        self.assertEqual(landing((20,20), direction, elev, 5, wind), target)

    def test_calibration_bounds_and_safe_shot(self):
        for seed in range(5):
            battle, bot = Battle(seed), strategy.MyBot()
            action = bot.on_state(battle.state('A'))
            self.assertEqual(set(action), {'ship','dir','elev','power'})
            battle.step({'A':action})
            self.assertNotEqual(battle.seats['A'].shots[-1][2], 'self_hit')
            bot._learn(battle.state('A'))
            for axis in (0,1):
                self.assertLessEqual(bot.bounds[axis][0], battle.wind[axis] + 1e-9)
                self.assertGreaterEqual(bot.bounds[axis][1], battle.wind[axis] - 1e-9)
                self.assertLess(bot.bounds[axis][1] - bot.bounds[axis][0], .6)

    def test_hit_sequence_claim_and_sunk_news(self):
        state = Battle(3).state('A')
        state['you']['ships'] = [{'ship':'carrier','cells':[[0,i] for i in range(5)],'sunk':False}]
        state['your_shots'] = [[20,20,'HIT'],[20,21,'HIT_NO_SCORE']]
        bot = strategy.MyBot()
        heat = bot._heat(state,40,40,set(range(5)))
        self.assertEqual(heat[820], 0)
        self.assertEqual(heat[821], 0)
        self.assertGreater(heat[819], heat[780])
        self.assertGreater(heat[822], heat[861])
        state['your_shots'] = [[20,20,'sunk'],[20,21,'sunk']]
        heat = bot._heat(state,40,40,set(range(5)))
        self.assertEqual(heat[819], 0)
        self.assertEqual(heat[822], 0)

    def test_failed_intent_is_not_marked_as_shot(self):
        bot = strategy.MyBot()
        state = Battle(4).state('A')
        bot.pending = (0, (10.,10.), 3.)
        state['your_shots'] = [[12,11,'miss']]
        bot._learn(state)
        heat = bot._heat(state,40,40,set())
        self.assertEqual(heat[12*40+11],0)
        self.assertGreater(heat[10*40+10],0)

    def test_interval_distribution_sums_to_one(self):
        for bounds in ((-1,1),(.1,.2),(.5,.5)):
            self.assertAlmostEqual(sum(p for _,p in strategy.MyBot._axis(12.2,3.5,bounds)),1)

if __name__ == '__main__':
    unittest.main()
