# Phase 1: local approximation

The official `arena_sdk` module and `arena-sim` executable were checked in the
configured Python 3.13 environment and are unavailable. This implementation is
**not the official referee** and results carry `engine_kind=local_approximation`.
No packages were installed. The supplied [Readme](Readme) and [AGENTS](AGENTS)
were used; `docs/Readme.docx` and `AGENTS.md` are absent.

## Use

```python
from battleship_lab import Battle, Bot, RoundConfig

class MyBot(Bot):
    def on_state(self, state):
        ship = next(s for s in state['you']['ships'] if not s['sunk'])
        return dict(ship=ship['ship'], dir=90, elev=45, power=4)

battle = Battle(seed=42, config=RoundConfig.preset('round2'))
result = battle.run({'A': MyBot(), 'B': MyBot()})
```

`step(actions_by_seat)` resolves one simultaneous tick; `state(seat)` supplies
the private observation. Missing/invalid actions are silent ticks. `run` accepts
any object with `on_state(state)`, including an official Bot subclass if provided
later. The local Bot is deliberately not installed as a counterfeit arena_sdk.
Purchases and carryover are optional seat-keyed dictionaries; `remaining_points`
contains unspent balances. All four aim fields remain mandatory for boosters.
Run tests with `python -m unittest discover -s tests -v` using your interpreter.

## Approximation boundaries

- Final tick cap is undocumented: defaults to 120 and can be explicitly set on
  RoundConfig. Round 1 and Round 2 use the documented 120.
- Seed derivation, fleet sampling, random cluster neighbour selection and
  teleport sampling are local deterministic algorithms, not official replay parity.
- Torpedoes traverse grid boundaries from the origin cell centre, crossing both
  axes at exact corners. Official arbitrary-bearing cell traversal is unspecified.
- Teleports resolve in seat-letter order and avoid all ships, including wrecks.
  The document does not define conflicting simultaneous teleport destinations.
- Flares have a local `flare` result in shot history to expose their landing.
  Exact official booster result payloads are unspecified. They cause no waste.
- `run` catches exceptions and discards late returns measured by wall clock; it
  cannot interrupt a blocked bot. This is a trusted local callback runner, not a
  process sandbox or an official CPU-budget implementation. Direct `step` accepts
  already collected actions. Determinism assumes identical accepted actions.
- Runtime randomness uses independent placement, wind, and action streams.
  Bot `rng` is seeded; global random/numpy and process hash seeds are not managed.

No frontend, strategy benchmark, submission sandbox, or hosting is included.
