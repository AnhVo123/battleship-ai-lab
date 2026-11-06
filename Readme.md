Docs — Game AI Arena

# ⚓ Battleship Strategy Lab

> **Build a bot. Read the battlefield. Outsmart the fleet.**

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Game](https://img.shields.io/badge/Game-Battleship-0f766e)](#the-game)
[![Mode](https://img.shields.io/badge/Mode-Strategy%20Arena-f59e0b)](#how-this-works)

Battleship Strategy Lab is a sandbox for designing, testing, and submitting autonomous Battleship bots. You describe a strategy to Pi, inspect the generated code, run practice battles, tune your approach, and submit when you are ready.

## Quick start

1. Open the web workspace and review the starter bot.
2. Ask Pi to improve `strategy.py`.
3. Run **START PRACTICE** to test the latest version.
4. Use the replay and diagnostics to understand misses, wind, and targeting decisions.
5. Buy boosters in **ARMORY**, then **SUBMIT** before the round closes.

> [!TIP]
> The first useful upgrade is usually wind estimation: your bot learns from where its own shells land, not from the hidden wind value itself.

## At a glance

| Area | What matters |
| --- | --- |
| **Objective** | Score hits and sink enemy ships before the other seats do |
| **Arena** | A shared 40 × 40 sea with 2–20 teams |
| **Bot loop** | One private state update and one action per tick |
| **Constraint** | 500 ms per turn; invalid or late actions are silent ticks |
| **Core challenge** | Infer the hidden wind and spend limited reach wisely |

## Contents

- [How this works](#how-this-works)
- [Event clock](#event-clock)
- [The game](#the-game)
- [Writing the bot](#writing-the-bot)
- [The built-in opponents](#the-built-in-opponents)
- [Getting help](#getting-help)

---

How this works

You get a workspace with a bot that already plays, and Pi, an AI agent that writes the bot for you. You never edit the code yourself. The loop is short on purpose:

Tell Pi what your bot should do. Pi changes strategy.py and tests it; Bot code shows you the result, read-only.

START PRACTICE — a practice battle on the sea against built-in bots, played with your latest code. On the result, IMPROVE WITH PI hands it to Pi.

ARMORY — spend your team's points on boosters before the round's deadline. Your bot starts the round's battle holding what you buy.

SUBMIT — sends your bot, exactly as it is now, into the round. It sits beside START PRACTICE; on a phone it is in the top bar.

Three things refuse SUBMIT, each for a stated reason: the round — none is open for your team, or its deadline has passed; a sandbox that is not ready; and Pi still working, so you send the finished bot.

The workspace works on a phone too: below 1024px wide, PI and BATTLE are two tabs instead of two columns side by side. This page and the leaderboard work at any size.

Event clock

All times below are in your browser's time zone, with the UTC offset shown so you can check them against anything an organizer announces.

Event

AIArena

Starts

11:33 GMT+7 Thứ 4, 4 thg 11

Submissions close

23:33 GMT+7 Thứ 4, 4 thg 11

Ends

23:33 GMT+7 Thứ 4, 4 thg 11

The game

Battleship Royale is every team at once on one shared sea. Every bot fires one shell per tick, all at the same moment, through a wind nobody is told. Hits and sinkings score; the battle ends when one team is left afloat or the tick cap is reached.

Every number below is from the event's preset rounds. A round can set its own, and your bot always gets the real ones in state["config"], so it should read them rather than hard-code them.

The sea and the fleets · R1

Sea

40×40 cells in every round. A cell is [row, col], zero-based: row 0 is the top edge and column 0 the left edge.

Seats

Two to twenty teams per battle, each a seat with a letter from A to T. Your bot never learns which team sits where.

Fleet

Five ships, 17 cells: carrier 5, battleship 4, cruiser 3, submarine 3, destroyer 2.

Placement

The referee places every fleet from a hidden seed — you never choose where your ships go. Each ship is a straight horizontal or vertical line, scattered over the whole sea, so enemy ships sit among yours. No two ships touch, diagonals included, whoever owns them: the cells diagonal to a ship cell are always water.

Firing origin

A ship's first cell, cells[0] — its top or left end — is where its shells leave from for the whole battle, even after that cell is hit.

A tick · R2

Each tick every seat still playing gets its own private view and has 500 ms to answer with one action.

Everyone acts at the same moment. Teleports move first; then all of a tick's shells land against that sea, so seat order never changes an outcome, and a ship sunk during a tick still fires its shell that tick.

A missed deadline, an exception out of your code, None, or an invalid action is a silent tick: your seat fires nothing. Nothing is substituted and nothing is repaired.

The 3rd silent tick in a row disconnects your seat for the rest of the battle. Silent ticks in the first 5 ticks do not count, so a bot that is slow to start is not dropped. A disconnected seat fires nothing more, but its ships stay on the sea as targets, and reconnecting does not bring it back.

Aiming a shot · R3, R4

You never name a cell to fire at. You name one of your ships still afloat, a compass bearing dir, an elevation elev and a whole-number power, and the shell flies an arc from that ship's first cell:

v0  = power * speed_per_power

t   = 2 * v0 * sin(elev) / gravity

row = origin_row + (-v0 * cos(elev) * cos(dir) + wind_row) * t

col = origin_col + ( v0 * cos(elev) * sin(dir) + wind_col) * t

dir is 0–360, clockwise: 0 is up the screen (towards row 0), 90 right, 180 down, 270 left. That is why the row line has a minus sign: row numbers grow downwards.

elev is 0–90 degrees; 0 drops the shell on its own ship. power is 1 to power_max (5). Every round uses gravity 9.8 and speed_per_power 4.

The landing point is rounded once to a cell, half to even (Python's round: 2.5 becomes 2).

Anything out of range, a missing key or a wrong type makes the action invalid and it fires nothing — nothing is clamped or wrapped. Extra keys are ignored, so a bot can add its own notes.

Reach is (power_max × speed_per_power)² / gravity from the firing ship: under 41 cells in every round, so from any one ship a good part of the sea is out of range. It shrinks as your ships sink, because only ships afloat can fire.

The wind · R4

A hidden two-dimensional wind pushes every shell by wind × t. It is the same for every seat and the whole battle, each component somewhere between −1.0 and +1.0, and nobody is told what it is. Your bot learns it only from where its own shells land: compare state["your_shots"] with where the no-wind arithmetic said they would land. Working the wind out is most of the game.

What a shell finds · R5

Each landing cell is judged against the sea as it stood when the tick began:

miss

Open water, including water you already shot. Wasted.

hit

An enemy ship cell not holed before this tick. Scores.

sunk

That hit left the ship with no unhit cell. Scores the hit and a sink bonus.

wreck

Any ship cell already holed before this tick, by anyone. Nothing changes. Wasted.

off_board

Left the sea. You are told the out-of-sea cell it would have hit. Wasted.

self_hit

One of your own unhit cells. It holes the cell exactly as an enemy shell would, and can sink your own ship. You earn nothing for that sinking; an enemy whose shell hit the same ship that tick still takes it. Wasted.

Two shells on the same unhit enemy cell in one tick both read hit and both score. When a ship goes down, every shell that holed it that tick reads sunk and each firer scores the sink bonus.

When a ship goes down, your earlier hits on it turn into sunk in your_shots, whoever fired the last shell. That is news, not points: you learn the ship you were hunting is gone, not who sank it.

Boosters · R6 and the booster market

Boosters are bought before the battle, in the ARMORY, with the points the round gives your team; the bot never buys anything. Your seat starts the round's battle — and every practice battle — holding what you bought, and firing one uses one up. What is left when the battle ends is lost.

Flare · 4 points

Flies like a shell and lights the 7×7 square around where it lands: your bot learns every unhit enemy ship cell inside, in state["revealed"]. It is not a shot — it damages nothing, scores nothing and is never wasted — and nobody else learns it was fired. Its landing cell still tells you about the wind.

Cluster · 1 point

Flies like a shell. The landing cell is a shot, and then up to 3 more of its four orthogonal neighbours are struck — never cells off the sea, cells you shot before, or your own ship cells. Each extra cell scores, or is wasted, like any shot.

Torpedo · 7 points

Does not fly. It runs from the ship in a straight line along dir — any bearing, on the surface, with no wind — over sunk ships, and sinks the whole of the first ship on that line, even if the cell it met was already hit. It scores 1 for each of that ship's cells nobody had hit, plus the ship's length. Your own ships stop it too: one in the way sinks as a self_hit, scores nothing and shields what is behind it. Only the ship that fires it is passed. With nothing in line it leaves the sea as off_board.

Teleport · 4 points

Fires nothing. Teleports happen first: before any shot of the tick lands, the named ship moves to a random free place, keeping its holes; its new first cell is its new firing origin. Shots that tick find it where it went, so shells aimed at the cells it left find water. Only you are told where it went.

In the preset rounds, round 1 sells nothing and gives no points; round 2 sells flares and clusters; the final sells all four. Rounds 2 and the final give 10 points each. The ARMORY shows what this round sells and what you have left.

You can change what you bought until the round's submit deadline; then it is locked in. Points you did not spend carry into the next round if your team goes through. Boosters you bought and did not fire never come back as points.

Your bot fires a booster by adding "action": "flare" (or cluster, torpedo, teleport) to its action. With none of that booster left, it is fired as a plain shot at the same aim — which is why every action needs dir, elev and power, even a teleport.

What your bot sees · R9

Its own fleet and which cells of it are holed, its own score so far, the boosters it has left, the seat letters in the battle, where each of its own shells and torpedoes landed, the shells that holed its own cells (but not who fired them), and the enemy cells its own flares lit.

Never: another team's ships, shots, score or boosters; which seats are still standing; whether anyone fired a flare or teleported; the wind; or the seed.

How a battle ends · R8

A seat with no ship afloat is eliminated at the end of that tick, and its score stops.

The battle ends when at most one seat still has a ship afloat, or at the tick cap — 120 ticks in rounds 1 and 2. A disconnected seat with ships afloat still counts as standing: its ships are targets.

If no seat is still connected, the battle is abandoned: it shows no scores, and the organizers play it again. Every bot dropping at once is more likely our fault than every team's.

The same battle, every time · R10

The same round, seed, seats, boosters and actions produce the same battle, shot for shot. Placement and wind come from the seed, so they never move when the bots play differently. The seed is never published, but the replay shows every ship, the wind and every landing, so any result can be checked from it.

The built-in opponents

START PRACTICE fills every other seat with one of these, picked under Practice options:

random_shooter

Easy. Fires at a random cell in reach — the floor every bot has to beat.

hunt_target

Medium. Searches at random; once something is hit, works outward from it until it sinks.

parity_hunter

Hard. Searches every other cell, and spends a flare when it has no lead.

All three work the wind out from where their own shells land. The starter bot in your workspace does not — that is the first thing worth asking Pi for.

Writing the bot

Your bot is a class with one method. bot.py — the entrypoint that speaks to the game server — comes from the platform and is never yours to edit; it imports your MyBot out of strategy.py and runs it. There is no placement method: the referee places your fleet.

strategy.py

# strategy.py — the only file Pi needs to change

from arena_sdk import Bot

class MyBot(Bot):

    def on_state(self, state) -> dict:

        # called once a tick, for every tick your seat is playing

        ship = next(s for s in state["you"]["ships"] if not s["sunk"])

        return {

            "ship": ship["ship"],  # fire from this ship's first cell

            "dir": 137.0,          # compass bearing: 0 up, 90 right

            "elev": 31.5,          # 0 to 90 degrees

            "power": 4,            # 1 to config["physics"]["power_max"]

        }

The action you return

ship

One of your ships still afloat at the start of the tick. The shell or torpedo leaves from its first cell; a teleport moves this ship.

dir

A compass bearing, 0–360: 0 up, 90 right, 180 down, 270 left.

elev

0–90 degrees.

power

A whole number from 1 to config["physics"]["power_max"]. A boolean is not a number.

action

Optional: "flare", "cluster", "torpedo" or "teleport", if your team bought one. Always send the other four keys with it.

A missing key, a wrong type or a value out of range makes the action invalid, and an invalid action fires nothing — the same silent tick as no answer. Any other key is ignored, so a bot can add its own "reason".

What you get in on_state

Everything your seat is allowed to know, and nothing it is not. No field anywhere in here holds another team's ships, shots or score, or the wind.

state["tick"]                   # 12

state["deadline_ms"]            # 500

state["seats"]                  # ["A", "B", "C", ...] — fixed for the whole battle

state["you"]["slot"]            # "C"

state["you"]["score"]           # 7 — your hits and sink bonuses so far

state["you"]["ships"]           # [{"ship": "carrier", "cells": [[4, 9], [4, 10], ...],

                                #   "holed": [[4, 10]], "sunk": False}, ...]

state["you"]["incoming_shots"]  # [[4, 10, "hit"], ...] — shells that holed you, no shooter

state["you"]["ships_alive"]     # 5

state["you"]["boosters"]        # {"flare": 2, "cluster": 1, "torpedo": 0, "teleport": 0}

state["your_shots"]             # [[17, 22, "miss"], [18, 22, "hit"], ...] — where each landed

state["last_results"]           # what your previous action did; empty after a silent tick

state["revealed"]               # enemy cells your flares lit that are still unhit

state["config"] is the round's config, the source of every number on this page:

config["map"]                 # {"rows": 40, "cols": 40}

config["fleet"]               # {"carrier": 5, "battleship": 4, ...}

config["tick_cap"]            # 120

config["action_deadline_ms"]  # 500

config["physics"]             # {"gravity": 9.8, "speed_per_power": 4, "power_max": 5, "wind_max": 1.0}

config["boosters"]            # what this round sells: "unlocked", "costs", "flare_zone", ...

config["scoring"]             # {"hit": 1, "sink_bonus": "ship_length", "survival_per_cell": 0}

Cells are [row, col] everywhere, zero-based, with row 0 at the top. An off_board entry in your_shots carries the cell outside the sea it would have hit, so even a shell that flew overboard tells you about the wind.

Randomness is already deterministic

self.rng is a random.Random seeded before your first on_state. The entrypoint also seeds the module-level random and numpy.random, so a bot that uses randomness is reproducible with no action from you — the same seed and the same code play the same battle, every time.

Not yet in __init__: draw from self.rng in on_state, not when the bot is built.

secrets and os.urandom are rejected at submission, before anything runs, because they cannot be seeded and would make a battle irreproducible.

The seed your bot is given says nothing about where any ship is or which way the wind blows. It is derived separately, on purpose.

Every bot process runs with PYTHONHASHSEED=0, so set and dict iteration order is fixed too — a bot that iterates a set of candidate cells behaves the same on every run.

Testing locally with arena-sim

arena-sim plays a whole battle in your sandbox with the same referee a scored battle uses, against built-in bots, and prints your rank, score, hits, sinks, wasted shots and boosters spent. Pi uses it to test your bot; START PRACTICE plays one you can watch, with your round's settings and the boosters you bought.

arena-sim strategy.py --seed 42 --replay -

arena-sim strategy.py --seed 7 --opponents hunt_target,parity_hunter --replay -

arena-sim strategy.py --seed 42 --strict --replay -

arena-sim strategy.py --seed 42 --replay - --watch 3>records.jsonl

One battle is mostly luck. Change one thing, then compare the same few seeds before and after — that is the difference between a measurement and a feeling.

--opponents fills the other seats with random_shooter, hunt_target and parity_hunter; --teams sets how many seats (2 to 15).

--strict exits with an error naming the first tick your bot raised or ran out of time on. Every submission is checked with a short battle played the same way, so this is how to see a rejection coming.

--replay - writes no replay file, so a test never overwrites your last practice battle.

--watch streams the battle's records, and it writes them to file descriptor 3 rather than to stdout, so your own print() calls can never corrupt the stream. Redirect it — without 3>records.jsonl the command exits and tells you so.

The local 500 ms and the server's 500 ms are not the same 500 ms

Locally, arena-sim budgets CPU time — so Pi thinking in the background, or a file save, cannot manufacture a fake timeout on your single-vCPU sandbox.

In a scored battle the server measures something else: the wall clock from sending your bot the tick to receiving its action, minus a per-connection latency baseline. A bot that sits at 450 ms locally can pass every local run and still go silent in the round's battle — and three silent ticks in a row disconnect it. Leave real headroom: avoid looping over the whole sea every tick when a smaller search will do.

After a practice battle, the result card shows your slowest tick once it passes half the deadline. Code that waits rather than computes — a time.sleep, say — uses no CPU time, so practice cannot see it at all.

Splitting your bot across files

Your modules

Add *.py files next to strategy.py (say targeting.py) and import them. They travel with your submission.

Reserved names

A module of yours may not be called bot, arena_sdk, engine, sitecustomize, or a top-level standard-library module name — json.py is refused, helpers.py is fine. Submissions that shadow one are rejected before anything runs.

Working with Pi

The agent in your workspace edits strategy.py for you. It is better at a specific change than at an open brief, so this is the shape worth copying:

Ask the agent

In strategy.py, aim_at ignores the wind, so my shells drift. In on_state,

learn the wind from my own shots:

  When I fire, remember the cell I aimed at and the shell's flight time t.

  Next tick, compare that cell with where state["your_shots"] says the shell

  landed. The difference divided by t is one reading of the wind. Keep a

  running average — the wind never changes during a battle, and one rounded

  landing cell is a noisy reading.

  Then, before solving for the aim, subtract wind * t from the distance to

  the target, so the shell lands where I meant it to.

Keep a tick under about 50 ms — the deadline is 500 ms and the server

measures it less forgivingly than arena-sim does, so I want real headroom.

Then run:

  arena-sim strategy.py --seed 42 --replay -

  arena-sim strategy.py --seed 7 --replay -

and tell me score, hits and wasted shots on both seeds, before and after.

Why that works

It names the file and the method. The agent is not left guessing which of your modules the change belongs in.

It states the rule in terms of the state you actually get. state["your_shots"] exists; “the ships it has found so far” does not, and asking for it invites invented fields.

It sets a time budget. A clever policy that misses the deadline fires nothing, and three silent ticks in a row disconnect your seat, so the constraint belongs in the request rather than in the post-mortem.

It asks for a measurement on fixed seeds. The same seeds before and after are the difference between an improvement and a feeling — and two, because one battle is mostly luck.

When something breaks

Paste the traceback and say what you were running. “on_state raised KeyError on tick 14 with --seed 42 --opponents hunt_target, here is the traceback” gets a fix. “It crashed” gets questions.

You can keep typing while the agent is working. Your message is delivered at the end of its current step rather than instantly — the panel shows it as pending until it lands, so send it once and wait.

Scoring and ranking

Points · R7

Score = hits + sinking bonuses. A bot that holes 7 enemy cells, two of them the shots that finish a cruiser (length 3) and a destroyer (length 2), scores 7 + 3 + 2 = 12.

Hit

+1 for each enemy ship cell your shell holes.

Sinking

+1 for the hit, plus the ship's length: sinking a carrier with your shell is worth 6. A torpedo sinks a whole ship at once and scores 1 for each of its cells nobody had hit, plus the length: a 4-cell ship with one hole in it is worth 3 + 4. Anyone whose shell hit that ship in the same tick scores the sinking too.

Nothing else

In every preset round your own unhit cells score nothing — the referee placed them, not your bot. A self_hit scores nothing. Boosters never score by themselves, and a flare is not a shot.

Wasted shots

miss, wreck, off_board and self_hit, including a cluster's extra cells, a torpedo that runs off the sea, and every self_hit cell a torpedo reports when it sinks your own ship. They cost no points, but they break ties.

An eliminated seat's score stops where it was. A disconnected seat earns nothing more from shooting.

Ranking a battle · R8

0. Showed up

Every seat that joined the battle ranks above every seat that never did, even if it later disconnected. A team with no accepted submission still has its fleet on the sea, as targets, and ranks below every seat that joined.

1. Score

Highest first.

2. Wasted shots

Fewer first.

3. Last sinking

The seat whose last sinking came earlier ranks higher; a seat that never sank anything sorts after every seat that did.

4. Final point

The seat that scored its last point earlier — reached its final score sooner — ranks higher; a seat that never scored sorts after every seat that did.

5. First point

The seat that scored its first point earlier ranks higher.

6. Seat letter

If everything above is level. Seat letters are drawn at random when the battle starts, and the step exists so the order is fully decided — a rank never shuffles between one refresh and the next.

In short: score more, waste less, and get there sooner. Two seats on 4 points with 115 wasted shots each and no sinking are split by step 4: the one whose last point came in tick 96 ranks above the one whose last point came in tick 110.

A round, start to finish

The organizers publish a round with its team list and a submit deadline — the countdown in your top bar. Only a team on the list can submit.

Until the deadline, practise, buy boosters in the ARMORY, and press SUBMIT as often as you like. Your newest accepted submission is the one that plays; one that is rejected leaves the previous one in place.

The organizers put the round's teams into groups of up to twenty and, once submissions have closed, start each group's battle. Your bot plays it alone: Pi, your workspace and your team cannot step in. The room screen shows it live.

When it reports, your workspace says where you finished — and, if your bot fired nothing on some ticks or was disconnected, how many and why.

The top teams of each group's battle go through to the next round, carrying the points they did not spend in the ARMORY.

What SUBMIT checks

Every submission is inspected the moment you press SUBMIT, before anything runs, so a problem the platform can see costs you seconds. It refuses:

imports outside the standard library, the four provided packages (numpy, scipy, networkx, sortedcontainers), arena_sdk and your own modules — the message names the offending package;

secrets and os.urandom, which cannot be seeded;

modules that shadow a platform or top-level standard-library name;

more than 256 KB of player code in total, across every file you added;

any call to __import__, exec, eval or compile, and any use of importlib.

Then your bot plays a 20-tick check battle against built-in bots, holding some of every booster the round sells, so its booster code runs too. It must not raise or run out of time on any tick. The badge in your top bar follows it:

Checking…

Waiting for a checker, or the check battle is running.

In ‹round›

Accepted — “In Heats”, say. This is the code that will play the round's battle.

Rejected

Your code did not pass. The message is the last thing the check said — the import, the file or the tick that broke — and your previous accepted submission still stands.

Check failed

Our infrastructure broke. It does not count against you, and you can submit again.

The leaderboard page is a different game

/leaderboard scores the original one-on-one Battleship on a 10×10 board, not the Royale, and nothing on it decides who goes through. A bot there plays a fixed gauntlet of 20 matches against two built-in bots, five seeds each, both ways round. A win is 3 points, a tie is 1, a loss is 0, so 60 is a clean sweep. Equal scores are separated by fewer mean shots to win (a bot with no wins has no mean and sorts last), then by more enemy cells hit, then by who scored first. The board shows each team's newest scored submission, not its best.

Packages

Your bot may import the Python standard library, arena_sdk, your own modules, and these four packages. Nothing else.

numpy 2.2.6

arrays, vectorised board maths

scipy 1.15.3

optimisation, spatial helpers

networkx 3.4.2

graphs, connectivity

sortedcontainers 2.4.0

sorted sets and dicts, priority queues

pip install does not survive, and there are two separate reasons

Ranked evaluation has no PyPI access. Your matches run in fresh sandboxes whose network is closed except for the game server, so a package you installed by hand becomes an ImportError at the one moment it matters.

And a dev install is temporary anyway. Your workspace saves your files, not the packages under them. If your sandbox ever has to be rebuilt — after a failure, or a resume that does not come back — anything pip-installed is simply gone, with no warning and no trace in your code.

The agent will not run pip install for you, and that is deliberate rather than a limitation to work around.

If you need more code: vendor it

Pure-Python code can just live next to your bot. Drop the module in your workspace, import it, and it travels with your submission — evaluation copies every *.py file you created.

workspace/

  strategy.py      # your bot

  targeting.py     # your module — imported normally, submitted with it

  probability.py

This is the supported answer for most of what a person would reach for a package for. Two limits apply: a vendored module may not shadow a reserved name (see the SDK section), and all your files together must come to under 256 KB — generous for logic, not for a copied library.

If you really need a package: ask

Ask an organizer in the support channel. Adding a pinned package and rebuilding the template takes minutes, and it lands in the practice sandboxes and the evaluation sandboxes together — so they can never disagree.

Before you ask, weigh whether it helps: a match gets 512 MB and 200 ms a turn, which makes most heavyweight libraries useless here. The four above cover arrays, graphs and priority queues, which is what bot logic actually wants.

Getting help

Organizers are on hand for the things you cannot fix from inside your workspace: a lost team key, a sandbox that will not come back, a package you need added to the template, or a result that looks wrong.

Support channel — placeholder, not yet set

This page currently shows #arena-help, which is a placeholder. Organizers must replace it with the real channel before the event opens — until then, ask whoever handed you your team key.

To fix: edit CHANNEL in apps/web/components/docs/Support.tsx and set CHANNEL_IS_PLACEHOLDER to false.

Lost your team key? An organizer reissues it. Your workspace, files, sandbox and leaderboard row are untouched by a reissue.

Signed out unexpectedly? Your team was full, and a teammate signing in on another device took your place. Sign in again: your bot and your team's chat with Pi are saved.

Sandbox stopped? The workspace offers a Recreate action and tells you when your files were last saved. Your files are in the save, not in the sandbox.

Conduct and your data

Two people share every match: whoever wrote the other bot, and whoever has to run the event. The rules below are the ones the platform enforces, so they are worth knowing before you trip one.

What is published

Your team name, bot name, gauntlet score, win-loss-tie record, mean shots to win, when you last scored, and your ranked replays appear on the leaderboard, which is public and may be projected in the room.

Practice replays stay private to your team. Ranked ones do not — a ranked replay reveals both fleets after the match, which is what makes a result auditable.

Your bot name is the one string on that board you choose, and it is the one an organizer can moderate: hiding a bot name removes that team's whole row from the board, and the action is recorded. What crosses the line is the organizers' call — see the note at the end of this section.

Play the game, not the platform

Beat the built-in bots with better Battleship. Do not go after the entrypoint, the sandbox boundary, the network, other teams' workspaces, or the evaluation pipeline.

The pre-match check refuses unseeded randomness, imports outside the allowed set, and modules that shadow platform names. These are not obstacles to route around — deliberately defeating one is the kind of thing organizers can disqualify a submission for.

A disqualification applies to one submission, carries a stated reason, and leaves your earlier scored submission standing. Every organizer action of this kind — disqualify, hide, rename, re-run — is written to an audit log.

The AI agent is there to write your bot. Asking it to work on anything else in the sandbox is off-topic at best, and the same conduct rules apply to what you type into it.

Your data

Chat messages are sent to and logged by a model provider to generate replies, and are also stored with your workspace here so the panel survives a reload.

Submitted code is kept for the event and its results, so a score can be re-checked afterwards.

To have your workspace deleted — files, chat and leaderboard row — ask an organizer. The exact route and how long anything is kept afterwards are theirs to state, and are part of the note below.

Code of conduct — organizers' text still to come

The section above states what this platform does. Four things it cannot state for the organizers, all of which must land here before sign-in opens: the formal code of conduct and its reporting route, the bot-name policy — what is out of bounds and how a hidden name is put right — the grounds for disqualification, and the data-deletion and retention path. The acknowledgement checkbox on the sign-in card points at this anchor (/docs#conduct), so a participant is agreeing to whatever is written here.
