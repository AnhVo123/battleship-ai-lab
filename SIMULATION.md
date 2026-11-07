# Local simulation — Rulebook v1.5 (6 November 2026)

The supplied [Rulebook](<RULEBOOK (1).pdf>) supersedes older README assumptions.
See [verification and limitations](RULEBOOK_V15_VERIFICATION.md).

The official `arena_sdk` module and `arena-sim` executable were checked in the
configured Python 3.13 environment and are unavailable. This implementation is
**not the official referee** and results carry `engine_kind=local_approximation`.
The PDF's 27 pages were extracted using pypdf. No official Referee source or
reference fixtures are bundled. `docs/Readme.docx` and `AGENTS.md` are absent.

## Use

```python
from battleship_lab import Battle, Bot, RoundConfig

class MyBot(Bot):
    def on_state(self, state):
        ship = next(s for s in state['you']['ships'] if not s['sunk'])
        return dict(ship=ship['ship'], dir=90, elev=45, power=4)

battle = Battle(seed=42, config=RoundConfig.preset('round2'))
result = battle.run({seat: MyBot() for seat in battle.seats})
```

`step(actions_by_seat)` resolves one simultaneous tick; `state(seat)` supplies
the private observation. Missing/invalid actions are silent ticks. `run` accepts
any object with `on_state(state)`, including an official Bot subclass if provided
later. The local Bot is deliberately not installed as a counterfeit arena_sdk.
Purchases and carryover are optional seat-keyed dictionaries; `remaining_points`
contains unspent balances. All four aim fields remain mandatory for boosters.
Run tests with `python -m unittest discover -s tests -v` using your interpreter.

## Approximation boundaries

- Presets: Round 1 36×36/10 seats/two groups/top six; Round 2 28×28/6 seats/two
  groups/top three; Final 28×28/6 seats/one group/top three podium. All have
  120 ticks, speed per power 4, gravity 9.8, power 1–5, deadline 500 ms.
  Explicit custom seat counts remain supported for laboratory experiments.
- Seed derivation, fleet sampling, random cluster neighbour selection and
  teleport sampling are local deterministic algorithms, not official replay parity.
- Torpedoes traverse grid boundaries from the origin cell centre, crossing both
  axes at exact corners as specified in Rule 7.13. Floating comparisons use a
  local 1e-12 tolerance; exact numerical parity requires the official Referee.
- Teleports resolve in seat-letter order and avoid all ships, including wrecks.
  Their old placement is excluded; holes retain their positional indices.
- Flares have a local `flare` result only in the previous-action report, never
  in the Shot Record.
  Exact official booster result payloads are unspecified. They cause no waste.
- `run` catches exceptions and discards late returns measured by wall clock; it
  cannot interrupt a blocked bot. This is a trusted local callback runner, not a
  process sandbox or an official CPU-budget implementation. Direct `step` accepts
  already collected actions. Determinism assumes identical accepted actions.
- Runtime randomness uses independent placement, wind, Cluster and Teleport streams.
  Bot `rng` is seeded; global random/numpy and process hash seeds are not managed.

The existing frontend, benchmark and replay retain their effects and now carry
round configuration. Static submission checks are advisory, not a security
sandbox. The runtime validation endpoint runs a local 20-tick check with one of
each unlocked booster; it does not establish official acceptance.
