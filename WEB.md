# Phase 4: local web workspace

Requires Windows, Python 3.11+ (with the `py` launcher), and Node.js 22.12+
or 24+. From the project folder:

```powershell
.\setup.bat
.\start.bat
```

Open http://127.0.0.1:8000. Setup creates a Python virtual environment,
installs FastAPI/Uvicorn/test dependencies, installs the locked frontend packages,
and builds React/TypeScript with Vite. Startup serves API and built UI from one
loopback origin. Ctrl+C stops the server and closes battle workers.
For hot reload, run `powershell -File scripts/dev.ps1` after setup; the UI is
at http://127.0.0.1:5173 and proxies `/api` to FastAPI. The script closes its
backend when the frontend exits. No cloud service, account, or paid API is used.

## Workflow

- Upload a UTF-8 `.py` file defining `MyBot(Bot)`. The browser preserves its
  text content as a content-addressed version. List, select, rename labels,
  view source, and download originals from the strategy library. Source is
  immutable through the API. The web uploader supports a single Python file;
  helper bundles remain supported by the Phase 2 CLI only.
- Select a round, difficulty, seed, and 2–20 teams, then create a battle.
  Play advances ticks, Pause stops scheduling new ticks, and Step resolves one
  simultaneous tick. An in-flight tick can finish after Pause. Replay resets
  the timeline cursor; Play replays recorded frames before advancing new ticks.
  The timeline permits scrubbing while paused. Replay frames are frozen copies.
- The viewer is deliberately omniscient: team-colored ships, damage, scores,
  wind, ground trajectories, and height-versus-time profiles are available for
  analysis. Bots still receive their private observations only. Off-board paths
  are clipped on the map. Torpedo lines follow the local referee's reported cell;
  their flight profile is flat. Teleports do not draw a shell trajectory.
- The benchmark dashboard runs 100–1000 matches per version per round, with
  separate development/holdout pools and paired comparisons using identical
  seeds and seats. It displays win rate, rank, score, wasted shots, timeouts,
  and 95% confidence intervals. All-round benchmarks are supported. Background
  jobs show progress and save complete reports to disk for later viewing.
  No sample results are fabricated; the dashboard is empty until a run completes.

The UI defaults to no purchased boosters. The battle and benchmark APIs accept
`loadout` dictionaries validated against each selected round. Round selection
does not itself purchase boosters.

## Local data and limits

Versions, labels, and benchmark reports persist under ignored `local_data/`.
Set `BATTLESHIP_DATA` to change that location. Battle replay frames live in
memory until the server exits or the battle is closed; at most eight battles
are retained. One benchmark runs at a time. Benchmarks and battles share local
CPU resources; avoid simultaneous runs when measuring deadlines. Interrupted
benchmark jobs are not resumed after restart; completed reports are retained.
Benchmark jobs are daemon threads and are not guaranteed to finish on shutdown.

Only run trusted local strategies: workers provide process/failure isolation,
not a hostile-code OS sandbox. The server binds loopback; it checks Host and
Origin and does not expose permissive CORS. Do not expose it through a public
proxy. There is no user authentication because this is a single-user local app.
The official engine and opponents remain unavailable; UI and reports carry
explicit approximation labels. Final tick cap remains the local 120 default.

Tests:

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
cd frontend
npm.cmd test
npm.cmd run build
```
