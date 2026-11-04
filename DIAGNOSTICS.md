# Phase 5: evidence-based strategy diagnostics

Battle ticks and benchmark matches now retain version-scoped actions, observed
results, score deltas, inventory consumption, flare reveals, and original replay
changes. Reports remain explicitly `local_approximation`. No AI API is used.

The battle room shows issue markers with jump-to-tick. Save a snapshot to retain
the original replay across server restarts. Completed benchmarks are automatically
saved as experiments. The Diagnostics & history tab selects experiments, rounds,
versions and individual matches, inspects evidence, replays original ticks, compares
development versus validation runs, exports JSON/CSV/Markdown, and generates a
copyable prompt. Prompts for a selected benchmark match cite its recorded events.

## Meaning of a finding

- `confirmed_error`: recorded runtime exception, timeout, invalid action, worker
  failure, or actual friendly damage. This establishes the event, not its root
  cause or whether a deliberate sacrifice could ever be strategic.
- `confirmed_observation`: measured score, waste, reported-target error, or a
  statistical performance difference. Misses alone do not prove poor targeting.
- `hypothesis`: a review suggestion tied to an observed event, such as a
  zero-point torpedo/cluster. This does not establish causal booster effectiveness.
- `hindsight`: comparison to hidden referee wind or post-tick enemy geometry.
  Such information was not necessarily available to the strategy and is never
  added to its private observation.

Every finding carries event/metric evidence references. Tick findings link to
seed, tick and seat; benchmark examples add round, version and match index.
Raw records accompany exports. Counts derive from original per-tick outcomes,
so historical hit-to-sunk relabeling does not fabricate additional points.
Multiple sunk labels are not assumed to represent multiple ships.

## Optional self-reported intent

Strategies may include inert diagnostic metadata in an otherwise valid action:

```python
return dict(ship=ship_name, dir=bearing, elev=elevation, power=power,
            diagnostics={"target": [row, col], "wind": [wind_row, wind_col]})
```

The worker retains only finite two-number vectors for these keys. Bad metadata
is ignored and never invalidates a valid game action. The engine ignores these
notes. Landing error is measured against the **declared** target, not a guessed
intention. Wind-estimate error compares the declared estimate with the hidden
referee vector and is explicitly hindsight. Without metadata, these accuracies
are unavailable. Wind displacement compares the actual rounded landing with
the no-wind rounded landing; rounding makes it a coarse measurement.

Booster tables record actual inventory consumption, same-action rewards,
wasted results, and newly revealed cells. Empty-inventory fallback is a plain
shot and is not counted as booster use. Information value, teleport survival
benefit, and alternative-action value require counterfactual experiments and
are not claimed here.

## Experiments and comparisons

In paired strategy A/B results, first version is baseline and later version is
candidate. A regression/improvement flag requires the per-metric paired 95%
interval to exclude zero in the adverse/favorable direction. These are exploratory
normal intervals without multiple-testing correction, not proof of a causal
regression. Every seed and raw match remains in the report.

Development/holdout comparison requires identical versions, rounds, team count,
opponent, loadout, engine and master seed, plus disjoint seed sets. Independent
pool mean differences use 1.96 standard errors. A gap is an observation; it is
not automatically evidence of overfitting. Abandoned matches are excluded from
win/rank/score/waste comparisons; timeout statistics include them.

Experiment JSON under `local_data/experiments/` retains raw evidence and replays.
CSV contains findings, metrics, booster observations and (for battle experiments)
individual events. Markdown contains evidence-backed findings, metrics and a
prompt. Benchmark aggregate findings include at most 100 representative tick
findings; full diagnostics remain in each match record. The UI shows at most
200 issue markers per selection. Exports and raw JSON retain the full selection.
Old reports lacking telemetry have no retroactively invented diagnostics/replay.

Compact benchmark replays retain initial ship positions and subsequent changes;
loading them does not rerun the strategy. Their trajectory overlay shows seat A.
Replay/telemetry increases disk and memory use for large benchmarks. No cloud
storage, auto-tuning, or automatic strategy source editing is included.
