# Rulebook v1.5 update

Authority: all 27 pages of [RULEBOOK (1).pdf](<RULEBOOK (1).pdf>), effective
6 November 2026. No official Referee source or reference test fixtures were found
in this project. This remains `local_approximation`, not an official-equivalence claim.

## Changed implementation

- [simulation.py](battleship_lab/simulation.py): round dimensions/seats/groups/
  advancement, shared physics settings, longest-first fleet placement with shuffled
  seats and retry, independent placement/wind/Cluster/Teleport random streams,
  Teleport old-position exclusion, Flare report/record separation, Torpedo holed
  stop-cell handling and scoring, per-result points, final disconnection and end reasons.
- [opponents.py](battleship_lab/opponents.py): dynamic boundaries, probability
  placement bounds, torpedo traversal and aiming from visible physics settings.
- [web.py](battleship_lab/web.py), [benchmark.py](battleship_lab/benchmark.py),
  [diagnostics.py](battleship_lab/diagnostics.py), [CLI](battleship_lab/__main__.py):
  round seat defaults, configuration in replay/report/prompt, legal inventory caps,
  round-specific 20-tick runtime validation and CLI opponent purchases.
- [validation.py](battleship_lab/validation.py), [strategies.py](battleship_lab/strategies.py):
  256 KiB total source cap, library shadowing rejection, aliased OS randomness and
  SystemRandom detection, official extra-library allowlist and explicit validation limits.
- [App](frontend/src/App.tsx), [Board](frontend/src/Board.tsx),
  [types](frontend/src/types.ts), [styles](frontend/src/style.css),
  [workbench](frontend/src/StrategyWorkbench.tsx): dynamic grid, coordinates and
  picking boundaries, round seat counts, report counts, per-result score display,
  20-tick check control. Existing projectile, impact, flare, teleport, sinking,
  trajectory, wind and flight-profile effects remain; scene memoization is retained.
- Regression fixtures updated to declare two-seat custom scenarios explicitly.
  Added [v1.5 regression cases](tests/test_rulebook_v15.py) and round board tests.
  Updated tests: [boosters](tests/test_battle_boosters.py),
  [benchmark](tests/test_benchmark.py), [diagnostics](tests/test_diagnostics.py),
  [API updates](tests/test_requested_updates.py), [ranking/history](tests/test_results_history.py),
  [simulation](tests/test_simulation.py), [strategy CLI](tests/test_strategies.py),
  [web](tests/test_web.py), [board](frontend/src/Board.test.tsx),
  [UI updates](frontend/src/Updates.test.tsx). Documentation:
  [simulation guide](SIMULATION.md) and this verification report.

## Evidence

Rule-derived assertions cover 2.9/2.10 round settings, 3.5 placement and spacing,
5.1–5.4 physics/rounding, simultaneous shared hits and sinking credit, Cluster
eligibility and off-board neighbours, Flare privacy and Shot Record exclusion,
Torpedo friendly shielding/holed stop/corner traversal, Teleport movement and holes,
all ranking tie-breaks, grace/silence/disconnection/abandonment, immutable private
observations, inventory accounting, and deterministic replay.

Six real 120-tick simulations (two per round, seed 20261106, hard opponents) use
10/6/6 seats; their serialized replay data matches exactly within each pair.
Existing tests also exercise all five opponent policies and all legal booster kinds.

- `.venv/Scripts/python.exe -m unittest discover -s tests`: **139 tests run,
  135 passed, 4 opt-in live-service tests skipped**, 95.954 seconds. Includes the
  six full-round deterministic simulations and real subprocess runtime checks for
  all three rounds; a strategy crashing on tick 7 is rejected after six ticks.
- `npm test -- --reporter=dot`: **24 passed in 6 files**, 5.64 seconds. Covers
  round dimensions, boundary picking, zoom, existing effects, replay and UI flows.
- VS Code **Build local web UI** task: TypeScript and Vite production build passed
  (3.44 seconds for Vite). Editor diagnostics: no errors in backend/frontend paths.
- Real integrated browser on `http://127.0.0.1:8000`: switching Round 1 / Round 2 /
  Final produced 36/28/28 rows and columns and 10/6/6 displayed seats. A real Final
  with the existing Default strategy rendered six teams, five simultaneous Flare
  zones and six projectiles after tick 1. A 30-frame requestAnimationFrame sample
  measured median **16.7 ms**, p95 **16.8 ms**; this small smoke sample is not a
  sustained-load guarantee.
- That Final then completed all **120 ticks through the real browser UI**, with
  six ranking rows and no visible alert errors, at the selected 4× playback speed.
  Keyboard replay seeking returned to tick 0 (zero projectiles) and then tick 120,
  preserving the six-row final ranking.

## Remaining limits and discrepancies

- No official Referee implementation/examples are available for differential
  testing. Random seed derivation, payload formats and floating tolerances remain
  local. Ship integer indices are a documented local compatibility adapter.
- Practice opponents are clearly marked custom approximations. The described
  random/hunt/parity behavior is implemented, but exact official policies are
  unavailable. The Lab's independent opponent purchase policies differ from
  Rule 11.10's shared player Armory choice; these are custom comparison battles.
  The battle UI defaults to a Practice inventory option that mirrors the player's
  purchased inventory across every opponent, implementing Rule 11.10. Unchecking
  it selects custom purchases; benchmarks retain custom opponent purchases.
- Local worker deadline measures wall time, including IPC; official Practice
  measures bot CPU time, and tournament timing includes measured network allowance.
  No official network service, Join Window timer, tournament draw or submission
  locking service is implemented by this local Lab.
- Static checks cannot prove arbitrary Python code safe or catch every indirect
  dynamic loading/randomness alias. The worker is process isolation, not an OS
  security sandbox. No official submission acceptance is asserted.
- Local playback speed is user-controlled, rather than enforcing official live
  pacing of one tick per 1.5 seconds. No browser FPS claim is made from jsdom tests.
- Newly recorded replays contain dimensions. Legacy replays without configuration
  retain their original 40×40 dimensions through an explicit compatibility fallback.
- Four opt-in live-service integration tests require BATTLESHIP_INTEGRATION_URL.

Imported player strategy files were not edited.
