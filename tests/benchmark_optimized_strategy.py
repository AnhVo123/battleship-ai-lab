"""Reproducible local-approximation paired strategy comparison."""
import argparse
import hashlib
import importlib.util
import json
import random
import statistics
import sys
import time
import types
from pathlib import Path
from battleship_lab.simulation import Battle, Bot
from battleship_lab.opponents import Opponent
from battleship_lab.benchmark import seed_pool, mean_ci, win_ci


def load(path, name):
    sdk = types.ModuleType('arena_sdk')
    sdk.Bot = Bot
    sys.modules['arena_sdk'] = sdk
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.MyBot


def run(bot_class, seed, teams):
    battle = Battle(seed, seats=teams)
    bot = bot_class()
    # Match the worker's independent randomness without exposing referee seed.
    bot.rng = random.Random(hashlib.sha256(f'battleship-lab:bot:v1:{seed}:bot:A'.encode()).hexdigest())
    bots = {'A':bot, **{s:Opponent('extreme', f'{seed}:bot:{s}') for s in battle.seats if s != 'A'}}
    runtimes, errors, timeouts = [], [], 0
    while not battle.finished:
        actions = {}
        for seat, other in bots.items():
            if battle.seats[seat].eliminated or not battle.seats[seat].connected:
                continue
            start = time.perf_counter()
            try:
                action = other.on_state(battle.state(seat))
            except Exception as exc:
                if seat == 'A':
                    errors.append(repr(exc))
                action = None
            elapsed = time.perf_counter()-start
            if seat == 'A':
                runtimes.append(elapsed*1000)
                timeouts += elapsed > .5
                if elapsed > .5:
                    action = None
            actions[seat] = action
        battle.step(actions)
    row = next(r for r in battle.results()['ranking'] if r['seat']=='A')
    shots = battle.seats['A'].shots
    scoring = sum(s[2] in ('hit','sunk') for s in shots)
    return dict(seed=seed,score=row['score'],rank=row['rank'],win=int(row['rank']==1),
                scoring_efficiency=scoring/max(1,len(shots)),points_per_shot=row['score']/max(1,len(shots)),
                shots=len(shots),timeouts=timeouts,errors=errors,
                runtime_mean_ms=statistics.mean(runtimes),runtime_max_ms=max(runtimes))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--matches',type=int,default=12)
    parser.add_argument('--teams',type=int,nargs='+',default=[2,6])
    parser.add_argument('--pool',default='development')
    parser.add_argument('--output',default='strategy_benchmark.json')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    versions={name:load(root/'examples'/file,name) for name,file in
              [('baseline','strategy_baseline.py'),('optimized','strategy.py')]}
    report=dict(engine_kind='local_approximation',opponent='extreme / Competitive Optimizer (local)',
                pool=args.pool,seeds=seed_pool(args.pool,args.matches),teams={},
                source_sha256={name:hashlib.sha256((root/'examples'/file).read_bytes()).hexdigest()
                               for name,file in [('baseline','strategy_baseline.py'),('optimized','strategy.py')]},
                notes=['120-tick round1; no boosters; same placement, wind and bot seeds per pair.',
                       'Runtime includes private state construction; direct callback runner.',
                       'Scoring efficiency is enemy hit/sunk outcomes divided by accepted shells.',
                       'Official referee and official opponents unavailable; small samples do not establish Rank 1 superiority.'])
    for teams in args.teams:
        records={name:[] for name in versions}
        for seed in report['seeds']:
            for name, cls in versions.items():
                row=run(cls,seed,teams)
                records[name].append(row)
                print(teams,name,len(records[name]),row['score'],row['rank'],round(row['runtime_max_ms'],1),flush=True)
        summaries={}
        for name, rows in records.items():
            summaries[name]={'rank1':win_ci([r['win'] for r in rows]),
                             **{key:mean_ci([r[key] for r in rows]) for key in
                                ('score','scoring_efficiency','points_per_shot','runtime_mean_ms')},
                             'runtime_max_ms':max(r['runtime_max_ms'] for r in rows),
                             'timeouts':sum(r['timeouts'] for r in rows),
                             'errors':[e for r in rows for e in r['errors']]}
        paired={key:mean_ci([a[key]-b[key] for a,b in zip(records['optimized'],records['baseline'])])
                for key in ('win','score','scoring_efficiency')}
        report['teams'][teams]=dict(summary=summaries,paired_optimized_minus_baseline=paired,records=records)
        Path(args.output).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v['summary'] for k,v in report['teams'].items()},indent=2))

if __name__=='__main__':
    main()
