# Strategy optimization validation

The selected `examples/OpusStrategyOptimize` was preserved byte-for-byte in `examples/strategy_baseline.py`. The optimized code is identical in `examples/strategy.py` and `examples/OpusStrategyOptimize`.

## Scope and evidence

Read `AGENTS`, `Readme`, and the local simulation, state builder, scoring, ranking, and opponent implementations. `agents.md` and `docs/Readme.docx` are absent. The official referee and arena-sim are unavailable. All measurements below use the **local approximation**, round1, no boosters, a 120-tick cap, and the extreme Competitive Optimizer opponents. Each version receives identical placement, wind, seat, and independent bot-randomness seeds within each pair. Runtime includes private-state construction in the direct callback runner. A separate process-worker smoke test checks 20 ticks.

## Measurements

| Pool | Seats | Matches/version | Mean score baseline -> optimized | Rank 1 baseline -> optimized | Scoring efficiency baseline -> optimized | Mean tick ms baseline -> optimized |
|---|---:|---:|---:|---:|---:|---:|
| development | 2 | 8 | 7.00 -> 11.75 | 62.5% -> 50.0% | 2.92% -> 5.10% | 1.24 -> 26.81 |
| development | 6 | 8 | 18.50 -> 27.62 | 12.5% -> 12.5% | 8.02% -> 11.25% | 2.06 -> 25.53 |
| holdout | 2 | 16 | 6.25 -> 13.38 | 43.8% -> 56.2% | 2.66% -> 5.57% | 2.22 -> 26.42 |
| holdout | 6 | 16 | 15.44 -> 23.31 | 6.2% -> 37.5% | 6.75% -> 9.48% | 1.60 -> 23.89 |

Scoring efficiency means enemy cells scored per accepted shell; points per shell, 95% intervals, per-seed records, paired differences, and source hashes are in the JSON reports. Optimized maximum observed tick: 110.0 ms; deadline: 500 ms. No strategy exceptions or timeouts in the 96 evaluated battles (48 per version). The separate 20-tick process check returned valid actions throughout.

The development two-seat Rank 1 rate decreased; the six-seat rate tied. Holdout rates improved for both seat counts. Samples are small, confidence intervals are wide, and these results do not establish statistically reliable or official Rank 1 superiority. No further tuning used holdout results.

## Implementation

- One high-arc scoring shot on tick 1; exact rounded-landing wind intervals become available on tick 2. Later ordinary scoring shots refine them passively.
- Cached valid fleet placements, own/sunk exclusion halos, randomized parity preferences, conditional hit-sequence extensions, and fractional remaining-length estimates for partially observed sinking reports.
- Claimed cells have zero direct value. Aging hit leads receive a crowd-dependent unclaimed-value discount. Sink value is discounted when insufficient ticks remain. These are lightweight probability/value approximations, not exact joint fleet posteriors or direct estimates of opponent scores.
- Every surviving firing ship and legal integer power is evaluated for the pruned target set. Low-arc ballistic solutions and exact integration over uniform rectangular wind bounds provide landing-cell expected values. Calibration uses high arcs. Friendly landing probability is rejected; actual landing history, rather than intended targets, prevents repeats.
- Four action keys only; standard library plus the required arena_sdk base. No additional calibration shots, fixed phase quotas, boosters, opponent score access, or hidden referee inputs.

## Validation and limitations

- Seven focused tests pass: inverse physics, interval mass, calibration bounds/safety, hit orientation/claimed cells/sinking news, actual landing tracking, static contract, and a 20-tick process-worker run.
- Full suite run before adding the worker smoke test: 111 tests, 104 passed, 4 skipped, 3 failed. The three failures reproduce pre-existing changes outside this strategy task: `test_seed_pools_disjoint_stable_and_nested` and `test_job_validation_and_failure` expect a 100-match minimum while existing edits allow 1; `test_only_completed_round2_points_carry_to_final` fails because existing session cleanup removes the completed carryover battle. The latter was reproduced individually. Those user edits were not changed.
- Editor diagnostics found no errors in the strategy or added test/benchmark scripts.
- No official referee validation, booster-loadout benchmarks, twenty-seat performance guarantee, or exact Rank 1 probability model is available. Candidate pruning and independent placement/claim models deliberately trade exhaustive optimization for runtime headroom.

Reproduce from the repository root:

```powershell
& ./.venv/Scripts/python.exe -m unittest tests.test_optimized_strategy -v
& ./.venv/Scripts/python.exe -m tests.benchmark_optimized_strategy --matches 8 --teams 2 6 --output strategy_benchmark.json
& ./.venv/Scripts/python.exe -m tests.benchmark_optimized_strategy --matches 16 --teams 2 6 --pool holdout --output strategy_benchmark_holdout.json
```
