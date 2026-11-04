# Phase 2: strategy import

Run on Windows with the configured Python interpreter:

```powershell
python -m battleship_lab C:/bots/v1/strategy.py --seed 42 --round round1
python -m unittest discover -s tests -v
```

The CLI snapshots source into `strategy_versions/<sha256>/` and runs seat A
against a local random-shooting opponent. `--store` selects another archive.
Every result retains the `local_approximation` engine label and includes the
version ID, ranking, and per-tick strategy diagnostics. This is one battle,
not a benchmark. The random opponent chooses legal random aims; it is not the
official arena's `random_shooter` implementation.

`import_strategy(source, store)` preserves the exact source bytes and sibling
Python helper modules. Versions are identified by a hash of the complete snapshot;
the same content reuses its version. Importing never executes strategy code.
Nested packages and non-Python assets are currently unsupported.

`StrategyProcess(version)` starts a persistent, separate Python process using
isolated interpreter mode and a temporary source copy. Each version and instance
gets its own module globals, bot instance, and working directory. Archived files
are not used as the worker's working copy. Close workers with a context manager.

Strategies use `from arena_sdk import Bot` and `class MyBot(Bot)` with
`on_state(state)`. A worker-only compatibility module supplies this interface;
it does not install or claim to implement the official SDK. Only JSON crosses
the process boundary. Unknown action keys are discarded, required values are
validated, and the simulation validates accepted actions again.

Startup has a separate five-second deadline. Calls use the state's deadline
(500ms normally). A timeout kills the worker and prevents late actions being
applied. Import errors, exceptions, invalid actions, and process exits have
distinct diagnostics. An exception or invalid action causes a silent tick;
exceptions can recover on the next tick. A terminated worker stays unavailable,
and normal silent-tick disconnection rules apply. Standard output is redirected
away from the protocol. Error details are bounded and stderr is discarded.

This provides process and failure isolation for trusted local Python strategies,
**not a security sandbox for hostile code**. Workers retain the current user's
filesystem and network privileges; no OS resource quota or descendant-process
containment is imposed. Do not run untrusted submissions with this local runner.
The original in-process `Battle.run` remains available for trusted callbacks;
the import CLI uses the process runner. No frontend is included.

Final integration correction: worker RNG seeds are now domain-separated SHA-256
derivations; the raw referee seed is no longer present in worker arguments.
Referee-specific `BATTLESHIP_*` environment variables are removed before startup.
Private state is unchanged by unobserved enemy/referee changes. This protects
the supported bot input channel, not hostile code with OS/filesystem access.
Rerun older benchmarks after this seeding correction; randomness-based strategies
can produce different actions from reports made before the correction.

Opt-in integration checks against a running local app (uses 15 full battles,
one 20-team smoke check and a real 100-match, 120-tick benchmark):

```powershell
$env:BATTLESHIP_INTEGRATION_URL = 'http://127.0.0.1:8000'
.venv/Scripts/python.exe -m unittest discover -s tests -p test_final_integration.py -v
Remove-Item Env:BATTLESHIP_INTEGRATION_URL
```

Use a disposable `BATTLESHIP_DATA` directory for the server when running these
checks: they import a privacy-probe strategy and save real experiment reports.
