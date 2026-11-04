# Local opponents and benchmarks

Official `arena_sdk` and `arena-sim` were checked again and remain unavailable.
All five opponents and every simulation result are explicitly local approximations.
Difficulty names describe heuristics, not a measured guarantee of strength:

| Level | Name | Policy |
|---|---|---|
| easy | Random Shooter | Random reachable targets, learns constant wind |
| medium | Hunt Target | Pursues neighbours of hits and revealed cells |
| hard | Parity Hunter | Parity search, target pursuit, flares without leads |
| expert | Probability Hunter | Counts compatible straight ship placements at candidate cells |
| extreme | Competitive Optimizer | Probability policy with targeted clusters and clear-axis revealed torpedoes |

Policies only receive private observations. They sample candidate cells for bounded
computation; probability counts are heuristic, not a full fleet posterior. Extreme
does not imply a globally optimal strategy. Current aiming uses preset physics.

Single battle:

```powershell
python -m battleship_lab C:/bots/v1/strategy.py --teams 20 --difficulty hard --round final
```

Paired benchmark (100–1000 matches **per strategy per round**, 2–20 teams):

```powershell
python -m battleship_lab.benchmark C:/bots/v1/strategy.py C:/bots/v2/strategy.py --matches 100 --teams 10 --round all --difficulty extreme --pool development --master-seed 42 --output development.json
python -m battleship_lab.benchmark C:/bots/v1/strategy.py --matches 100 --teams 10 --round final --difficulty hard --pool holdout --master-seed 42 --output holdout.json
```

Each strategy is imported into the version archive and runs in the Phase 2 process
worker. Every match uses a fresh instance. Strategy is seat A; fixed letters,
placement seed, wind seed, opponent difficulty and per-seat RNG seeds are shared
across comparisons. Opponents can react differently to changed strategy actions.
Other seats are filled with the selected difficulty. No seat balancing is claimed.

Rounds use the simulator's presets (including the documented approximation of the
Final tick cap). Default booster inventory is empty. `--loadout` accepts a JSON
object of booster counts applied equally to all seats; purchases must fit each
selected round's unlocks and budget. Use separate round runs for different loadouts.

Reports include all seeds, version paths, round, loadout, raw match records,
errors, rank-one win rate, mean rank, score, wasted shots, and timeout counts.
Win-rate intervals use Wilson's 95% interval. Mean metrics and paired differences
use a normal approximation, 1.96 standard errors. These intervals describe seed
variation for this fixed setup; they do not establish official-engine performance.
Paired differences are left minus right; lower rank/waste/timeouts are better.
Rank one uses the referee's deterministic tie breakers. Abandoned battles are
excluded from score/rank/win estimates and paired comparisons and counted explicitly;
timeouts include all attempted matches, including startup timeouts.

Development and holdout pools are reproducible, disjoint even/odd seed namespaces.
Counts extend the same ordered pool. Tune on development, freeze versions and
settings, then evaluate holdout once. The split prevents accidental seed overlap;
it cannot prevent a user tuning against holdout reports. No production benchmark
quality numbers are claimed by the test suite: its 100-match integration check
uses a one-tick cap to validate orchestration economically.

Run tests: `python -m unittest discover -s tests -v`.
