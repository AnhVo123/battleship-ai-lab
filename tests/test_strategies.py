import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from battleship_lab import Battle, RoundConfig
from battleship_lab.__main__ import RandomShooter
from battleship_lab.strategies import StrategyProcess, import_strategy, run_imported


HEADER = "from arena_sdk import Bot\nclass MyBot(Bot):\n"
VALID = HEADER + "    def on_state(self, state):\n        return dict(ship=state['you']['ships'][0]['ship'], dir=90, elev=45, power=1)\n"


class StrategyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "strategy.py"
        self.store = self.root / "versions"
        self.state = Battle(1).state("A")

    def version(self, code=VALID):
        self.source.write_text(code, encoding="utf-8")
        return import_strategy(self.source, self.store)

    def worker(self, code=VALID, **kwargs):
        worker = StrategyProcess(self.version(code), **kwargs)
        self.addCleanup(worker.close)
        return worker

    def test_referee_seed_and_data_directory_not_exposed_in_worker_inputs(self):
        code = 'import os, sys\n' + VALID.replace("return dict", "assert not any('92739123' in arg for arg in sys.argv), 'raw referee seed in argv'\n        assert 'BATTLESHIP_DATA' not in os.environ, 'referee storage path in environment'\n        return dict")
        with patch.dict('os.environ',{'BATTLESHIP_DATA':'private-referee-data'}):
            worker = self.worker(code, seed='92739123:bot:A')
        self.assertIsNotNone(worker.on_state(self.state),worker.events)

    def test_seeded_worker_randomness_is_repeatable(self):
        code = VALID.replace('dir=90','dir=self.rng.uniform(0,360)')
        first = self.worker(code,seed='same-seed')
        second = self.worker(code,seed='same-seed')
        self.assertEqual(first.on_state(self.state),second.on_state(self.state))

    def test_versions_preserve_original_bytes(self):
        first = self.version()
        original = self.source.read_bytes()
        second = self.version(VALID.replace("dir=90", "dir=180"))
        self.assertNotEqual(first, second)
        self.assertEqual((first / "strategy.py").read_bytes(), original)
        self.assertEqual(import_strategy(self.source, self.store), second)
        self.assertEqual(len(list(self.store.iterdir())), 2)

    def test_snapshot_tamper_detected(self):
        version = self.version()
        (version / "strategy.py").write_text("changed")
        with self.assertRaises(ValueError):
            import_strategy(self.source, self.store)

    def test_no_execution_during_import(self):
        marker = self.root / "marker"
        self.version(f"raise RuntimeError('must not run')\n")
        self.assertFalse(marker.exists())

    def test_valid_and_stdout_isolation(self):
        code = VALID.replace("return dict", "print('noise')\n        return dict")
        worker = self.worker(code)
        self.assertEqual(worker.last_status, "ready")
        self.assertEqual(worker.on_state(self.state)["dir"], 90)
        self.assertEqual(worker.last_status, "ok")

    def test_state_and_instance_persist(self):
        code = HEADER + "    def on_state(self, state):\n        self.n = getattr(self, 'n', 0) + 1\n        state['you']['score'] = 999\n        return dict(ship=state['you']['ships'][0]['ship'], dir=self.n, elev=45, power=1)\n"
        worker = self.worker(code)
        self.assertEqual(worker.on_state(self.state)["dir"], 1)
        self.assertEqual(worker.on_state(self.state)["dir"], 2)
        self.assertEqual(self.state["you"]["score"], 0)

    def test_helper_and_working_source_copy(self):
        (self.root / "helper.py").write_text("DIRECTION = 123\n")
        code = "from helper import DIRECTION\n" + VALID.replace("dir=90", "dir=DIRECTION")
        worker = self.worker(code)
        self.assertEqual(worker.on_state(self.state)["dir"], 123)
        self.assertTrue((self.version(code) / "helper.py").exists())

    def test_worker_edits_do_not_change_archive(self):
        code = VALID.replace("return dict", "open('strategy.py', 'w').write('changed')\n        return dict")
        version = self.version(code)
        with StrategyProcess(version) as worker:
            self.assertIsNotNone(worker.on_state(self.state))
        self.assertEqual((version / "strategy.py").read_text(encoding="utf-8"), code)
        self.assertEqual(self.source.read_text(encoding="utf-8"), code)

    def test_exception_then_recovery(self):
        code = HEADER + "    def on_state(self, state):\n        if state['tick'] == 1: raise RuntimeError('boom')\n        return dict(ship=state['you']['ships'][0]['ship'], dir=90, elev=45, power=1)\n"
        worker = self.worker(code)
        self.assertIsNone(worker.on_state(self.state))
        self.assertEqual(worker.last_status, "exception")
        self.assertIn("boom", worker.events[-1]["detail"])
        self.state["tick"] = 2
        self.assertIsNotNone(worker.on_state(self.state))

    def test_invalid_action_types(self):
        for value in ("None", "{}", "dict(ship='carrier', dir=90, elev=45, power=True)", "dict(ship='carrier', dir=10**1000, elev=45, power=1)", "dict(ship='carrier', dir=float('nan'), elev=45, power=1)"):
            with self.subTest(value=value):
                code = HEADER + f"    def on_state(self, state):\n        return {value}\n"
                with StrategyProcess(self.version(code)) as worker:
                    self.assertIsNone(worker.on_state(self.state))
                    self.assertEqual(worker.last_status, "invalid_action")

    def test_import_errors_and_wrong_interface(self):
        for code in ("this is invalid syntax!", "class MyBot: pass", "raise RuntimeError('import failed')"):
            with StrategyProcess(self.version(code)) as worker:
                self.assertEqual(worker.last_status, "import_error")
                self.assertIsNotNone(worker._process.poll())

    def test_timeout_terminates_worker(self):
        worker = self.worker(HEADER + "    def on_state(self, state):\n        while True: pass\n")
        self.state["deadline_ms"] = 50
        self.assertIsNone(worker.on_state(self.state))
        self.assertEqual(worker.last_status, "timeout")
        self.assertIsNotNone(worker._process.poll())

    def test_import_timeout(self):
        worker = self.worker("while True: pass", startup_timeout=.2)
        self.assertEqual(worker.last_status, "timeout")
        self.assertIsNotNone(worker._process.poll())

    def test_worker_exit(self):
        worker = self.worker(HEADER + "    def on_state(self, state):\n        import os\n        os._exit(7)\n")
        self.assertIsNone(worker.on_state(self.state))
        self.assertEqual(worker.last_status, "worker_exit")

    def test_multiple_versions_independent(self):
        first = self.worker()
        second = self.worker(VALID.replace("dir=90", "dir=180"))
        self.assertEqual(first.on_state(self.state)["dir"], 90)
        self.assertEqual(second.on_state(self.state)["dir"], 180)

    def test_cli(self):
        self.version()
        completed = subprocess.run([sys.executable, "-m", "battleship_lab", str(self.source), "--store", str(self.store), "--seed", "7"], capture_output=True, text=True, timeout=20)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["engine_kind"], "local_approximation")
        self.assertEqual(len(result["ranking"]), 2)
        self.assertTrue(all(e["status"] in ("ready", "ok") for e in result["strategy_events"]))

    def test_invalid_actions_become_silent_ticks(self):
        worker = self.worker(HEADER + "    def on_state(self, state): return {}\n")
        battle = Battle(2, config=RoundConfig(tick_cap=9))
        run_imported(battle, worker, RandomShooter())
        self.assertFalse(battle.seats["A"].connected)
        self.assertEqual(len(battle.seats["A"].shots), 0)


if __name__ == "__main__":
    unittest.main()
