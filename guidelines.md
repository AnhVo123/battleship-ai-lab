# Battleship Strategy Lab usage guidelines

Battleship Strategy Lab is a local workspace for importing a Battleship bot,
watching it play, comparing versions, and measuring performance across repeatable
sets of battles. The simulator is an approximation of the documented game; it is
not the official competition engine.

## 1. Install and start

### Requirements

- Windows
- Python 3.11 or newer, available through the `py` launcher
- Node.js 22.12+ or 24+

From the project directory, run:

```powershell
.\setup.bat
.\start.bat
```

Open <http://127.0.0.1:8000> in a browser. Keep the terminal open while using
the app and press `Ctrl+C` there to stop the server.

Setup only needs to be repeated after dependencies change or when the generated
frontend build is missing. For frontend hot reload during development, run this
after setup:

```powershell
powershell -File scripts/dev.ps1
```

The development UI is then available at <http://127.0.0.1:5173>.

## 2. Create or import a strategy

Open **Strategy library** to upload a UTF-8 Python file, paste code into the
editor, or start from the provided template. A strategy must import `Bot`, define
`MyBot(Bot)`, and implement a synchronous `on_state` method:

```python
from arena_sdk import Bot


class MyBot(Bot):
    def on_state(self, state):
        return {"ship": 0, "dir": 90.0, "elev": 45.0, "power": 5}
```

For each tick, return one action containing:

- `ship`: a living ship's zero-based index, or its supported string identifier
- `dir`: a finite bearing from 0 to 360 degrees
- `elev`: a finite elevation from 0 to 90 degrees
- `power`: an integer from 1 through the round's `power_max`
- `action`: optionally `flare`, `cluster`, `torpedo`, or `teleport`

Read limits and round settings from `state["config"]` instead of hard-coding
them. Instance attributes on the bot survive between ticks, but a new bot
instance is created for every battle.

Use **Validate** before saving. Static validation checks syntax, allowed imports,
and the expected bot interface. The import check runs initialization and reports
missing packages, exceptions, or timeouts. Passing these checks does not guarantee
that every action returned during a battle will be valid.

Saving an edit creates a new content-addressed version; it does not overwrite an
older version. Give versions useful labels so results remain easy to compare.

## 3. Run a practice battle

In **Battle room**:

1. Select a strategy version.
2. Choose a round and opponent difficulty.
3. Set the number of teams from 2 to 20.
4. Leave **Reuse seed** off for a fresh map and wind, or enable it to reproduce
   the displayed seed exactly.
5. In rounds that allow boosters, purchase a loadout in the armory without
   exceeding the available points.
6. Select **Create battle**, then use **Play** or **Next** to advance it.

The viewer is intentionally omniscient for analysis: it shows ships, damage,
scores, wind, and trajectories. Bots still receive only their private
observations. Do not write a strategy that depends on information visible only
in the viewer.

Use **Pause** before closely inspecting a tick. An already-running tick may
finish after pausing. The replay slider, **Previous**, **Next**, and **Restart**
let you inspect recorded states; moving the slider pauses playback. At the live
edge, **Next** computes one new tick.

Grid labels use columns A through AN and rows 1 through 40. Selecting a cell also
shows its official zero-based `[row, col]` coordinate.

## 4. Use boosters correctly

- Round 1 has no boosters and no purchase budget.
- Round 2 offers flares and clusters.
- The Final offers flares, clusters, torpedoes, and teleports.
- Purchases apply to the selected player strategy before a practice battle.
- Used boosters are consumed, and unused inventory expires after the battle.
- Only unspent points can carry from an eligible Round 2 experiment into the
  Final after advancement is declared.

Every booster action must still include `ship`, `dir`, `elev`, and `power`. If a
requested booster is unavailable, the documented behavior is a normal shot with
the same aiming values.

## 5. Benchmark strategy versions

Open **Benchmarks** when a strategy works reliably in individual battles.
Benchmark runs compare versions over 100 to 1,000 matches per round and report
win rate, rank, score, wasted shots, timeouts, and 95% confidence intervals.

For useful comparisons:

- Compare versions on the same round and opponent configuration.
- Use paired runs so versions receive identical seeds and seats.
- Treat the development pool as feedback while iterating.
- Reserve the holdout pool for less frequent checks to reduce overfitting.
- Avoid running practice battles during a benchmark because both use local CPU.
- Wait for the complete report rather than drawing conclusions from early
  progress values.

Only one benchmark can run at a time. Completed reports are saved locally;
interrupted jobs do not resume after the server restarts.

## 6. Diagnose and iterate

Open **Diagnostics & history** to review saved experiments, validation results,
timeouts, errors, and completed benchmark reports. A productive iteration loop
is:

1. Save a clearly labeled baseline strategy.
2. Run a reproducible battle and inspect misses, repeated targets, self-hits,
   off-board shots, and wind estimation.
3. Change one strategic idea at a time and save it as a new version.
4. Replay the same seed for a behavioral comparison.
5. Benchmark the promising versions across many seeds.
6. Confirm improvements on the holdout pool.

Do not treat a single win or one favorable seed as evidence that a strategy is
better.

## 7. Data, safety, and limitations

- Strategy versions, labels, saved experiments, and benchmark reports persist
  under `local_data/`, which Git ignores.
- Active battle replays live in memory and are lost when the server stops unless
  the experiment is saved through the UI.
- The server listens only on `127.0.0.1` and has no authentication. Do not expose
  it through a public proxy.
- Run only code you trust. Strategy workers isolate failures, but they are not a
  security sandbox for hostile Python code.
- No account, cloud service, or paid AI API is required.
- Placement, wind, opponents, and results come from the local approximate engine.
  Validate important conclusions against the official environment when it is
  available.

For the detailed game rules and bot observations, read [Readme](./Readme). For
deeper technical behavior, consult [INTERFACE.md](./INTERFACE.md),
[WEB.md](./WEB.md), [SIMULATION.md](./SIMULATION.md),
[STRATEGIES.md](./STRATEGIES.md), and [BENCHMARK.md](./BENCHMARK.md).
