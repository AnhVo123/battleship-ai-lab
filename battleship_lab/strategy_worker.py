"""Private JSON worker entrypoint. Process isolation is not an OS security sandbox."""
import contextlib
import importlib.util
import json
import math
from pathlib import Path
import random
import sys
import types


class Bot:
    def __init__(self):
        self.rng = random.Random()


def validate(action, state):
    if type(action) is not dict:
        return None
    cleaned = {k: action[k] for k in ("ship", "dir", "elev", "power", "action") if k in action}
    identifier = cleaned.get("ship")
    fleet = state["you"]["ships"]
    ships = {s["ship"] for s in fleet if not s["sunk"]}
    if type(identifier) is int:
        if not 0 <= identifier < len(fleet) or fleet[identifier]["sunk"]:
            return None
        # Normalize before IPC so existing consumers use one unambiguous name.
        cleaned["ship"] = fleet[identifier]["ship"]
    elif type(identifier) is not str or identifier not in ships:
        return None
    if type(cleaned.get("power")) is not int or not 1 <= cleaned["power"] <= state["config"]["physics"]["power_max"]:
        return None
    for key, maximum in (("dir", 360), ("elev", 90)):
        value = cleaned.get(key)
        if type(value) not in (int, float) or not 0 <= value <= maximum or not math.isfinite(value):
            return None
    if cleaned.get("action", "shot") not in ("shot", "flare", "cluster", "torpedo", "teleport"):
        return None
    metadata = action.get("diagnostics")
    if type(metadata) is dict:
        safe = {}
        for key in ("target", "wind", "predicted_landing"):
            value = metadata.get(key)
            if type(value) in (list, tuple) and len(value) == 2 and all(type(n) in (int,float) and -10000 <= n <= 10000 and math.isfinite(n) for n in value):
                safe[key] = list(value)
        if type(metadata.get("reason")) is str:
            safe["reason"] = metadata["reason"][:160]
        if safe:
            cleaned["diagnostics"] = safe
    return cleaned


def main():
    output = sys.stdout
    def send(value):
        output.write(json.dumps(value, allow_nan=False) + "\n")
        output.flush()
    try:
        with contextlib.redirect_stdout(sys.stderr):
            random.seed(sys.argv[2])
            sys.path.insert(0, sys.argv[1])
            sdk = types.ModuleType("arena_sdk")
            sdk.Bot = Bot
            sys.modules["arena_sdk"] = sdk
            spec = importlib.util.spec_from_file_location("strategy", Path(sys.argv[1]) / "strategy.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules["strategy"] = module
            spec.loader.exec_module(module)
            if not isinstance(module.MyBot, type) or not issubclass(module.MyBot, Bot) or not callable(getattr(module.MyBot, "on_state", None)):
                raise TypeError("Expected MyBot(Bot) with on_state(state)")
            bot = module.MyBot()
            import inspect
            inspect.signature(bot.on_state).bind({})
            random.seed(sys.argv[2])
            bot.rng = random.Random(sys.argv[2])
        send({"status": "ready"})
    except BaseException as exc:
        send({"status": "import_error", "detail": f"{type(exc).__name__}: {exc}"[:2000]})
        return
    for line in sys.stdin:
        try:
            state = json.loads(line)
            with contextlib.redirect_stdout(sys.stderr):
                action = validate(bot.on_state(state), state)
            send({"status": "ok" if action is not None else "invalid_action", "action": action,
                  "detail": "" if action is not None else "Return an action with an alive ship (name or zero-based index), dir 0–360, elev 0–90, integer power 1–power_max, and a documented action name."})
        except BaseException as exc:
            send({"status": "exception", "detail": f"{type(exc).__name__}: {exc}"[:2000]})


if __name__ == "__main__":
    main()
