# Strategy import and the local bot interface

The existing app now adds editing and validation to its preserved strategy archive.
Open **Strategy library** to paste, edit, validate, run an import check, save a new
version, and preview highlighted Python alongside the selected opponent. Uploads
retain their bytes; editor saves preserve their source as a new content hash.
No previous version is overwritten by an edit. The working template is available
from the editor or `GET /api/strategy-template`.
An uploadable starter is also provided in [examples/strategy.py](examples/strategy.py).

Use `from arena_sdk import Bot`, define `class MyBot(Bot)`, and implement synchronous
`on_state(self, state)`. Return exactly one action each tick:

```python
{"ship": 0, "dir": 90.0, "elev": 45.0, "power": 5}
```

Integer ship identifiers are zero-based indices in `state["you"]["ships"]` in
this local compatibility adapter. The supplied [Readme](Readme) actually uses
string identifiers such as `"carrier"`, returned as `ship["ship"]`; those remain
supported. This integer adapter is not claimed as verified official SDK behavior.
Booleans and invalid/dead ship indices are refused. The firing origin is always
the selected ship's `cells[0]`. `dir` accepts finite numbers 0–360, `elev` 0–90,
and `power` must be an integer 1–`state["config"]["physics"]["power_max"]`.
Optional `action`: `flare`, `cluster`, `torpedo`, or `teleport`; all aim keys
remain mandatory. Missing inventory causes the documented plain-shot fallback.

State on `self` survives ticks. A separate instance is created each battle.
Observations contain only the documented private fields. Referee wind, map seed,
enemy fleets and scores remain viewer/replay data and are not passed to bots.

Static validation checks syntax, permitted import roots and the bot interface.
The runtime check executes imports/initialization in the existing isolated worker;
exceptions, missing packages and timeouts are shown separately. It does not prove
that every future on_state action is valid. Standard library, the four documented
provided packages and arena_sdk are accepted import names. Optional packages may
not be installed locally; the runtime check reports this honestly. Local execution
is still for trusted code, not a hostile-code security sandbox.

## Armory and maps

Round 1 has budget 0 and no purchases. Round 2 offers Flare (4) and Cluster (1)
for 10 points. Final offers all four, including Torpedo (7) and Teleport (4), for
10 points plus eligible unspent Round 2 points. The UI prevents overspending and
the server validates all quantities, costs, unlocks and source balances again.
Battle purchases apply to Team A; opponents do not receive Team A's purchases.
Batch benchmark loadouts retain the existing equal-inventory comparison behavior
and base round budget; advancement carryover is a live/practice battle feature.

Complete Round 2, then declare advancement to Final. The balance is taken from
the actual previous battle, never an arbitrary user-entered amount. Save a finished
Round 2 experiment to preserve its carryover source after restart. The README
does not specify the organizers' top-team cutoff; the local advancement checkbox
records a declaration and does not certify tournament qualification. A saved
source can be reused for practice; this is not a tournament accounting service.
Spent boosters and unused inventory never become points or carry as inventory.

Fresh battles now generate a new random seed by default, placing ships and sampling
wind independently. Each wind component stays within [-1, 1] and remains constant
for the whole battle. Enable **Reuse seed** to reproduce a map and wind exactly.
The existing seeded benchmark workflow remains deterministic.

Grid labels display columns A–AN and rows 1–40. Hover/click shows both display
coordinates and the official zero-based [row, col]. Sticky labels remain visible
inside the zoomable/scrollable grid. Arrow keys move the selected coordinate.

The requested `AGENTS.md` and `docs/Readme.docx` are absent; the supplied [AGENTS](AGENTS)
and [Readme](Readme) are the sources used. The incoming request ended mid-sentence
after “Wind remains constant throughou”; no requirements beyond that text were inferred.
