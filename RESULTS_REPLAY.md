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
