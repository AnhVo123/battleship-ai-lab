# Battle results and replay controls

Completed live/practice battles now automatically save their original frames,
diagnostics and final ranking as a battle experiment. The battle room shows the
full ranking immediately and highlights Team A. Team names use the strategy label
for Team A and the configured opponent name plus seat for other teams. The table
includes score, rank and ships remaining; remaining ships are not a tiebreaker.

Ordering reuses the existing referee rules from [Readme](Readme): joined seats
first, descending score, fewer wasted shots, earlier last sinking, earlier final
point, earlier first point, then seat letter. Missing scoring/sinking times sort
after recorded times. An abandoned battle is saved with an empty ranking and an
explicit explanation, rather than invented scores.

The **Completed battles** selector shows saved results after restart and loads
their original replay. Completed battles save once, even after repeated step or
save requests. Partial diagnostic snapshots remain available under experiment
history but are not presented as completed results. Existing saved completed
battle experiments also appear in battle history.

The larger replay slider supports native click, drag and keyboard seeking to any
recorded tick. Previous, Next, Play/Pause, Restart and 0.25×–4× speed controls
are shared by the battle room and saved Failure Replay. Seeking pauses playback.
Restart returns to tick zero without running another battle. At an unfinished
live battle's recorded edge, Next resolves one new simultaneous tick. Saved
replays never fire new shots. A live tick already in flight may finish, but its
response cannot override a newly sought replay position.

Battle history is stored in the existing `local_data/experiments/` directory.
No bot observations or ranking physics were changed. Results retain the existing
local approximation label.

Booster purchases are made before battle for every seat. Round 1 has none;
Round 2 opponents buy one flare and spend the remainder on clusters. Final
opponents alternate between a torpedo with clusters and a teleport/flare/cluster
loadout across seats, staying within ten points. All five difficulty levels use
their private observations to activate boosters: flares without a lead,
clusters on leads or before expiry, clear friendly paths toward observed targets
for torpedoes, and damaged ships for teleports. These are local policies, not
official opponent implementations.

Each team's expandable booster details show purchases, usage, inventory or
expiration, unspent points, and observed points, hits, sinks and revealed cells.
These statistics and resolved activation events persist in battle history and
benchmark replay. They do not estimate counterfactual flare or teleport value.
The SVG effects use those recorded events only, respect reduced motion, and
scale their duration with playback speed. Legacy recordings remain readable.

The UI sends the displayed tick as `expected_tick` when advancing a live battle.
Repeated requests for that tick return its already-recorded successor under the
session lock, preventing duplicate consumption. Existing clients can still step
without a request body. Seeking never creates an action or changes inventory.
