"""Versioned source storage and process-isolated local strategy execution."""
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading


def import_strategy(source, store):
    """Archive strategy.py and sibling Python modules without executing them."""
    source = Path(source).resolve()
    if not source.is_file() or source.suffix != ".py":
        raise ValueError("Strategy must be a Python source file")
    files = {"strategy.py": source.read_bytes()}
    for helper in sorted(source.parent.glob("*.py")):
        if helper.resolve() != source and helper.name != "strategy.py":
            if helper.is_symlink():
                raise ValueError("Symlink helpers are unsupported")
            files[helper.name] = helper.read_bytes()
    digest = hashlib.sha256()
    for name, content in sorted(files.items()):
        digest.update(name.encode() + b"\0" + str(len(content)).encode() + b"\0" + content)
    root = Path(store).resolve()
    root.mkdir(parents=True, exist_ok=True)
    destination = root / digest.hexdigest()
    if destination.exists():
        if {p.name: p.read_bytes() for p in destination.iterdir()} != files:
            raise ValueError("Stored version has been modified")
        return destination
    with tempfile.TemporaryDirectory(dir=root) as temporary:
        stage = Path(temporary) / "snapshot"
        stage.mkdir()
        for name, content in files.items():
            (stage / name).write_bytes(content)
        stage.rename(destination)
    return destination


class StrategyProcess:
    """Persistent worker. Timeouts terminate it; failures are silent actions."""
    def __init__(self, version, seed=0, startup_timeout=5):
        self.events = []
        self.last_status = None
        self._temporary = tempfile.TemporaryDirectory()
        self._process = None
        self._messages = queue.Queue(maxsize=1)
        self._reader = None
        try:
            work = Path(self._temporary.name)
            for source in Path(version).glob("*.py"):
                shutil.copyfile(source, work / source.name)
            # Domain-separated bot randomness must not disclose the referee seed.
            bot_seed = hashlib.sha256(f"battleship-lab:bot:v1:{seed}".encode()).hexdigest()
            worker_environment = {key:value for key,value in os.environ.items() if not key.upper().startswith("BATTLESHIP_")}
            self._process = subprocess.Popen(
                [sys.executable, "-I", "-u", str(Path(__file__).with_name("strategy_worker.py")), str(work), bot_seed],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                cwd=work, env=worker_environment, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self._reader = threading.Thread(target=self._read, daemon=True)
            self._reader.start()
            response = self._receive(startup_timeout)
            self._status(response["status"], response.get("detail", ""), 0)
            if response["status"] != "ready":
                self.close()
        except BaseException:
            self.close()
            raise

    def _read(self):
        try:
            while True:
                line = self._process.stdout.readline(65537)
                if not line or len(line) > 65536:
                    self._messages.put({"status": "worker_exit"})
                    return
                self._messages.put(json.loads(line))
        except (ValueError, OSError):
            self._messages.put({"status": "protocol_error"})

    def _receive(self, timeout):
        try:
            return self._messages.get(timeout=timeout)
        except queue.Empty:
            return {"status": "timeout"}

    def _status(self, status, detail, tick):
        self.last_status = status
        self.events.append({"tick": tick, "status": status, "detail": detail})

    def on_state(self, state):
        if self._process is None or self._process.poll() is not None:
            self._status("worker_exit", "Worker is unavailable", state["tick"])
            return None
        try:
            payload = json.dumps(state, allow_nan=False).encode() + b"\n"
            self._process.stdin.write(payload)
            self._process.stdin.flush()
            response = self._receive(state["deadline_ms"] / 1000)
        except (OSError, ValueError):
            response = {"status": "worker_exit"}
        status = response.get("status", "protocol_error")
        self._status(status, response.get("detail", ""), state["tick"])
        if status in ("timeout", "worker_exit", "protocol_error"):
            self.close()
        return response.get("action") if status == "ok" else None

    def close(self):
        if self._process is not None:
            if self._process.poll() is None:
                self._process.kill()
            self._process.wait()
            if self._reader:
                self._reader.join(timeout=1)
            self._process.stdin.close()
            self._process.stdout.close()
        self._temporary.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def run_imported(battle, strategy, opponent):
    """Collect private actions before resolving each simultaneous tick."""
    bots = {"A": strategy, **(opponent if isinstance(opponent, dict) else {"B": opponent})}
    while not battle.finished:
        actions = {}
        for label, bot in bots.items():
            seat = battle.seats[label]
            if seat.connected and not seat.eliminated:
                actions[label] = bot.on_state(battle.state(label))
        battle.step(actions)
    result = battle.results()
    result["strategy_events"] = strategy.events
    return result
