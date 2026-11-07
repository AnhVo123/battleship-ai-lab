from copy import deepcopy
import csv
import io
import json
import unittest

from battleship_lab import Battle, RoundConfig, Ship
from battleship_lab.diagnostics import (EvidenceRecorder, benchmark_diagnostics, compare_pools, diagnose,
    export_report, improvement_prompt, regression_findings, replay_frame)
from battleship_lab.strategy_worker import validate


def action(**extra):
    return dict(ship='destroyer',dir=90,elev=0,power=1,**extra)


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(42,seats=2,config=RoundConfig.preset('final'))
        self.battle.wind = (.5,0)
        self.battle.seats['A'].ships = [Ship('destroyer',[(10,10),(10,11)])]
        self.battle.seats['B'].ships = [Ship('destroyer',[(15,15),(15,16)])]
        self.recorder = EvidenceRecorder(self.battle)

    def step(self, value, status='ok'):
        self.recorder.begin(self.battle,value,status)
        self.battle.step({'A':value})
        self.recorder.finish(self.battle)
        return diagnose(self.recorder.events)

    def test_confirmed_self_damage_has_exact_evidence(self):
        result = self.step(action())
        finding = result['findings'][0]
        self.assertEqual(finding['classification'],'confirmed_error')
        self.assertIn('self_hit',finding['message'])
        self.assertEqual(finding['evidence'][0]['event'],'seed:42/tick:1/seat:A')
        self.assertEqual(result['metrics']['wasted_results'],1)
        self.assertEqual(result['metrics']['points'],0)

    def test_missing_metadata_does_not_invent_intent(self):
        result = self.step(action())
        self.assertIsNone(result['metrics']['mean_declared_target_error_cells'])
        self.assertEqual(result['metrics']['target_samples'],0)
        self.assertFalse(any(f['code']=='target_error' for f in result['findings']))

    def test_reported_target_and_wind_are_labeled(self):
        result = self.step(action(diagnostics={'target':[20,20],'wind':[-1,0]}))
        codes = {f['code']:f for f in result['findings']}
        self.assertEqual(codes['target_error']['classification'],'confirmed_observation')
        self.assertEqual(codes['wind_estimate']['classification'],'hindsight')
        self.assertAlmostEqual(result['metrics']['mean_reported_wind_error'],1.5)
        self.assertAlmostEqual(result['metrics']['mean_declared_target_error_cells'],(200)**.5)

    def test_worker_exception_confirmed_without_a_shot(self):
        result = self.step(None,'exception')
        self.assertEqual(result['findings'][0]['code'],'exception')
        self.assertEqual(result['metrics']['outcomes'],{})

    def test_booster_zero_points_is_hypothesis(self):
        self.battle.seats['A'].boosters['cluster'] = 1
        result = self.step(dict(ship='destroyer',dir=90,elev=45,power=1,action='cluster'))
        stats = result['boosters']['cluster']
        self.assertEqual(stats['uses'],1)
        self.assertEqual(stats['points'],0)
        self.assertTrue(any(f['classification']=='hypothesis' for f in result['findings']))
        self.assertEqual(stats['evidence'],['seed:42/tick:1/seat:A'])

    def test_empty_booster_not_counted_as_use(self):
        result = self.step(action(action='cluster'))
        self.assertEqual(result['boosters'],{})

    def test_scoring_split_and_torpedo_effectiveness(self):
        self.battle.wind = (0,0)
        self.battle.seats['B'].ships[0].cells = [(10,15),(10,16)]
        self.battle.seats['A'].boosters['torpedo'] = 1
        result = self.step(action(action='torpedo'))
        self.assertEqual(result['metrics']['points'],4)
        self.assertEqual(result['metrics']['enemy_cell_points'],2)
        self.assertEqual(result['metrics']['sink_bonus_points'],2)
        self.assertEqual(result['boosters']['torpedo']['points_per_use'],4)
        self.assertAlmostEqual(result['boosters']['torpedo']['points_per_armory_point'],4/7)

    def test_flare_reveals_observed_not_assumed_points(self):
        self.battle.seats['A'].boosters['flare'] = 1
        self.battle.seats['B'].ships[0].cells = [(10,13),(10,14)]
        result = self.step(dict(ship='destroyer',dir=90,elev=45,power=1,action='flare'))
        self.assertEqual(result['boosters']['flare']['new_reveals'],2)
        self.assertEqual(result['boosters']['flare']['points'],0)
        self.assertEqual(result['metrics']['wasted_results'],0)

    def test_replay_originals_frozen_and_roundtrip(self):
        self.step(action())
        first = replay_frame(self.recorder.replay(),1)
        self.assertEqual(first['teams'][0]['ships'][0]['holes'],[[10,10]])
        self.assertTrue(first['traces'])
        self.step(action())
        self.assertEqual(replay_frame(self.recorder.replay(),1),first)
        roundtrip = json.loads(json.dumps(self.recorder.replay()))
        self.assertEqual(replay_frame(roundtrip,2)['teams'][0]['shots'][0][2],'wreck')
        self.assertEqual(replay_frame(roundtrip,0)['teams'][0]['ships'][0]['holes'],[])
        with self.assertRaises(ValueError): replay_frame(roundtrip,-1)
        with self.assertRaises(ValueError): replay_frame(roundtrip,99)

    def test_exports_and_prompt_cite_event(self):
        result = self.step(action())
        payload = {'diagnostics':result}
        self.assertIn('seed:42/tick:1/seat:A',improvement_prompt(payload))
        self.assertIn('Recorded event:',improvement_prompt(payload))
        data,media = export_report(payload,'json')
        self.assertEqual(json.loads(data),payload)
        self.assertEqual(media,'application/json')
        text,_ = export_report(payload,'csv')
        rows = list(csv.reader(io.StringIO(text)))
        self.assertTrue(any(r[0]=='recorded_event' for r in rows))
        self.assertIn('seed:42/tick:1/seat:A',text)
        markdown,_ = export_report(payload,'markdown')
        self.assertIn('confirmed_error',markdown)
        self.assertIn('## Improvement prompt',markdown)
        with self.assertRaises(ValueError): export_report(payload,'pdf')

    def test_unknown_evidence_produces_no_diagnosis(self):
        result = diagnose([])
        self.assertEqual(result['findings'],[])
        self.assertIn('do not invent',improvement_prompt(result))

    def test_metadata_optional_and_malformed_extra_ignored(self):
        state = self.battle.state('A')
        valid = validate(action(diagnostics={'target':[1,2],'wind':[.1,.2]}),state)
        self.assertEqual(valid['diagnostics']['target'],[1,2])
        invalid_notes = validate(action(diagnostics={'target':['bad',True],'wind':[float('nan'),0]}),state)
        self.assertNotIn('diagnostics',invalid_notes)
        self.assertIsNotNone(invalid_notes)

    def test_prompt_groups_misses_and_prioritizes_runtime(self):
        for _ in range(60):
            self.step(dict(ship='destroyer',dir=90,elev=45,power=1))
        result = self.step(None, 'timeout')
        prompt = improvement_prompt({'diagnostics': result, 'version': 'abc123'})
        self.assertLess(len(prompt), 11000)
        self.assertLess(prompt.index('runtime/timeout'), prompt.index('targeting/wasted_shot'))
        self.assertIn('occurrences=60', prompt)
        self.assertIn('Ordinary misses are observations, not bugs', prompt)
        self.assertIn('complete improved strategy.py', prompt)
        self.assertIn('untouched disjoint validation seeds', prompt)
        self.assertIn('abc123', prompt)
        self.assertNotIn('"revealed_before"', prompt)

    def test_trace_metadata_is_bounded_and_available_in_prompt(self):
        notes = {'target':[20,20], 'predicted_landing':[19,20], 'wind':[0,0], 'reason':'x'*300}
        value = validate(action(diagnostics=notes), self.battle.state('A'))
        self.assertEqual(len(value['diagnostics']['reason']), 160)
        result = self.step(value)
        prompt = improvement_prompt(result)
        self.assertIn('predicted_landing', prompt)
        self.assertIn('Referee-only hindsight', prompt)
        self.assertIn('Bot-visible decision trace samples', prompt)


def report(pool='development',score=5):
    seeds = [2,4,6] if pool=='development' else [3,5,7]
    records = [dict(seed=seed,abandoned=False,win=1,rank=1,score=score,wasted_shots=0,timeouts=0) for seed in seeds]
    return dict(engine_kind='local_approximation',opponent_implementation='local_approximation',opponent='Hunt Target',
                teams=2,loadout={},master_seed=42,pool=pool,seeds=seeds,
                rounds={'round1':{'strategies':[dict(version='/store/version1',records=records)],'comparisons':[]}})


class ExperimentComparisonTests(unittest.TestCase):
    def test_prompt_summarizes_actual_runs_and_missing_metrics(self):
        data = report()
        prompt = improvement_prompt({'report': data, 'diagnostics': benchmark_diagnostics(data)})
        self.assertIn('Hunt Target', prompt)
        self.assertIn('"difficulty":"medium"', prompt)
        self.assertIn('round1/version1', prompt)
        self.assertIn('"matches":3', prompt)
        self.assertIn('"ci95"', prompt)
        self.assertIn('"enemy_hit_result_rate":{"mean":null', prompt)
        self.assertIn('"sink_bonus_points":{"mean":null', prompt)
        self.assertIn('No evidence-backed findings', prompt)

    def test_pool_comparison_uses_independent_observations(self):
        result = compare_pools(report(),report('holdout',2))
        score = next(r for r in result['comparisons'] if r['metric']=='score')
        self.assertEqual(score['holdout_minus_development'],-3)
        self.assertEqual(score['ci95'],[-3,-3])
        self.assertEqual(score['evidence']['development_seeds'],[2,4,6])
        self.assertIn('not proof',score['interpretation'])

    def test_confounded_pools_rejected(self):
        for key,value in [('teams',3),('loadout',{'flare':1}),('master_seed',8),('opponent','Other')]:
            holdout = report('holdout');holdout[key]=value
            with self.assertRaises(ValueError):compare_pools(report(),holdout)
        overlap = report('holdout');overlap['seeds']=[2,3,5]
        with self.assertRaises(ValueError):compare_pools(report(),overlap)
        wrong = report('holdout');wrong['rounds']['round1']['strategies'][0]['version']='other'
        with self.assertRaises(ValueError):compare_pools(report(),wrong)

    def test_regression_direction_and_uncertain_intervals(self):
        data = report()
        comparison = dict(left='baseline',right='candidate',paired_matches=100,
                          **{m:dict(n=100,mean=0,ci95=[-1,1]) for m in ('score','win','rank','wasted_shots','timeouts')})
        comparison['score']['ci95']=[1,2]
        comparison['rank']['ci95']=[-2,-1]
        data['rounds']['round1']['comparisons']=[comparison]
        findings = regression_findings(data)
        self.assertEqual(len(findings),2)
        self.assertTrue(all(f['code']=='regression' for f in findings))
        comparison['score']['ci95']=[-2,-1]
        self.assertEqual(regression_findings(data)[0]['code'],'improvement')

    def test_aggregate_does_not_fabricate_tick_findings(self):
        diagnostics = benchmark_diagnostics(report())
        self.assertEqual(diagnostics['findings'],[])
        self.assertTrue(diagnostics['metrics'])


if __name__=='__main__':
    unittest.main()
