from pathlib import Path
import base64
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from battleship_lab.web import create_app

SOURCE = "from arena_sdk import Bot\nclass MyBot(Bot):\n def on_state(self,s):\n  return dict(ship=next(x['ship'] for x in s['you']['ships'] if not x['sunk']),dir=90,elev=45,power=3)\n"


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.client = TestClient(create_app(self.temp.name))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def upload(self, source=SOURCE):
        response = self.client.post('/api/versions', json=dict(filename='strategy.py',source=source,label='Baseline'))
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['id']

    def test_versions_upload_rename_download_persistence(self):
        identifier = self.upload()
        self.assertEqual(self.client.get('/api/versions').json()[0]['label'], 'Baseline')
        original = self.client.get(f'/api/versions/{identifier}/source')
        self.assertEqual(original.content, SOURCE.encode())
        self.assertEqual(self.client.patch(f'/api/versions/{identifier}',json={'label':'V1'}).status_code, 200)
        other = self.upload(SOURCE.replace('dir=90','dir=180'))
        self.assertNotEqual(identifier, other)
        self.assertEqual(self.client.get(f'/api/versions/{identifier}/source').content,SOURCE.encode())
        with TestClient(create_app(self.temp.name)) as restarted:
            self.assertEqual(len(restarted.get('/api/versions').json()), 2)
            self.assertIn('V1', [v['label'] for v in restarted.get('/api/versions').json()])

    def test_reject_bad_upload_and_identifiers(self):
        for body in (dict(filename='x.exe',source=SOURCE),dict(source='invalid ! python'),dict(source='x'*262145)):
            self.assertEqual(self.client.post('/api/versions',json=body).status_code,422)
        self.assertEqual(self.client.get('/api/versions/invalid/source').status_code,404)
        self.assertEqual(self.client.get('/api/benchmarks/invalid').status_code,404)

    def test_upload_preserves_bom_and_crlf_bytes(self):
        original = b'\xef\xbb\xbf' + SOURCE.replace('\n','\r\n').encode()
        response = self.client.post('/api/versions',json=dict(source_base64=base64.b64encode(original).decode()))
        self.assertEqual(response.status_code,201,response.text)
        identifier = response.json()['id']
        self.assertEqual(self.client.get(f'/api/versions/{identifier}/source').content,original)
        self.assertEqual(self.client.post('/api/versions',json={'source_base64':'!invalid!'}).status_code,422)

    def test_trajectory_ends_at_reported_landing_and_no_privacy_leak(self):
        from battleship_lab.web import Session
        from battleship_lab import Battle
        from unittest.mock import Mock
        b = Battle(42,seats=2)
        worker = Mock(last_status='ok')
        worker.on_state.return_value = dict(ship='carrier',dir=90,elev=45,power=3)
        opponent = Mock()
        opponent.on_state.return_value = None
        session = Session(b,worker,{'B':opponent},'version')
        session.snapshot()
        frame = session.step()
        trace = frame['traces'][0]
        self.assertEqual([round(v) for v in trace['points'][-1][:2]],trace['landing'])
        state = worker.on_state.call_args.args[0]
        self.assertNotIn('wind',state)
        self.assertNotIn('teams',state)

    def test_battle_step_replay_and_close(self):
        identifier = self.upload()
        created = self.client.post('/api/battles',json=dict(version=identifier,teams=3,difficulty='hard'))
        self.assertEqual(created.status_code,201,created.text)
        battle = created.json()['id']
        zero = created.json()['frame']
        first = self.client.post(f'/api/battles/{battle}/step').json()
        self.assertEqual(first['tick'],1)
        self.assertEqual(len(first['teams']),3)
        self.assertEqual(len(first['wind']),2)
        self.assertTrue(first['traces'])
        self.assertTrue(all(len(p)==3 for p in first['traces'][0]['points']))
        self.assertEqual(self.client.get(f'/api/battles/{battle}/frames/0').json(),zero)
        self.assertEqual(self.client.get(f'/api/battles/{battle}/frames/1').json(),first)

    def test_battle_recovers_after_worker_exit(self):
        source = SOURCE.replace("  return dict", "  if s['tick'] == 1:\n   import os\n   os._exit(7)\n  return dict")
        identifier = self.upload(source)
        created = self.client.post('/api/battles', json=dict(version=identifier, teams=2, difficulty='easy'))
        self.assertEqual(created.status_code, 201, created.text)
        battle = created.json()['id']
        first = self.client.post(f'/api/battles/{battle}/step')
        self.assertEqual(first.status_code, 200, first.text)
        second = self.client.post(f'/api/battles/{battle}/step')
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()['tick'], 2)
        self.assertTrue(any(t['seat'] == 'A' for t in second.json()['traces']))
        self.assertEqual(self.client.get(f'/api/battles/{battle}/frames/99').status_code,404)
        self.assertEqual(self.client.delete(f'/api/battles/{battle}').status_code,200)
        self.assertEqual(self.client.post(f'/api/battles/{battle}/step').status_code,404)

    def test_invalid_config_and_import_exception(self):
        identifier = self.upload()
        for overrides in (dict(teams=21),dict(round='all'),dict(difficulty='bad'),dict(loadout={'torpedo':1})):
            self.assertEqual(self.client.post('/api/battles',json=dict(version=identifier,**overrides)).status_code,422)
        broken = self.upload('raise RuntimeError("no bot")\n'+SOURCE)
        response = self.client.post('/api/battles',json=dict(version=broken))
        self.assertEqual(response.status_code,422)
        self.assertIn('import_error',response.text)

    def test_jobs_progress_report_and_restart(self):
        identifier = self.upload()
        def fake_benchmark(*args, progress):
            progress(100,100)
            return {'engine_kind':'local_approximation','rounds':{}}
        with patch('battleship_lab.web.benchmark',side_effect=fake_benchmark):
            response = self.client.post('/api/benchmarks',json=dict(versions=[identifier],matches=100))
            self.assertEqual(response.status_code,202,response.text)
            job = response.json()['id']
            for _ in range(100):
                result = self.client.get(f'/api/benchmarks/{job}').json()
                if result['status'] != 'running': break
                time.sleep(.01)
        self.assertEqual(result['status'],'complete')
        self.assertEqual(result['done'],100)
        self.assertEqual(result['report']['engine_kind'],'local_approximation')
        self.assertEqual(self.client.get('/api/benchmarks').json()[0]['id'],job)
        with TestClient(create_app(self.temp.name)) as restarted:
            self.assertEqual(restarted.get(f'/api/benchmarks/{job}').json()['status'],'complete')

    def test_job_validation_and_failure(self):
        identifier = self.upload()
        for overrides in (dict(matches=0),dict(versions=[identifier,identifier]),dict(pool='bad'),dict(round='bad')):
            body = dict(versions=[identifier]);body.update(overrides)
            self.assertEqual(self.client.post('/api/benchmarks',json=body).status_code,422)
        with patch('battleship_lab.web.benchmark',side_effect=RuntimeError('failed')):
            job = self.client.post('/api/benchmarks',json=dict(versions=[identifier])).json()['id']
            for _ in range(100):
                result = self.client.get(f'/api/benchmarks/{job}').json()
                if result['status'] != 'running': break
                time.sleep(.01)
        self.assertEqual(result['status'],'failed')
        self.assertIn('failed',result['error'])

    def test_cross_origin_and_host_rejected(self):
        self.assertEqual(self.client.post('/api/versions',headers={'Origin':'https://evil.example'},json=dict(source=SOURCE)).status_code,403)
        self.assertEqual(self.client.get('/api/health',headers={'Host':'evil.example'}).status_code,403)
        self.assertEqual(self.client.get('/api/health',headers={'Origin':'http://localhost:5173'}).status_code,200)

    def test_windows_scripts_parse(self):
        import subprocess
        root = Path(__file__).resolve().parent.parent
        for name in ('setup','start','dev'):
            script = root/'scripts'/f'{name}.ps1'
            command = "$parseErrors = $null; [System.Management.Automation.Language.Parser]::ParseFile('" + str(script).replace("'","''") + "', [ref]$null, [ref]$parseErrors) | Out-Null; if ($parseErrors.Count) { $parseErrors; exit 1 }"
            result = subprocess.run(['powershell.exe','-NoProfile','-Command',command],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_diagnostics_experiment_exports_and_original_replay(self):
        identifier = self.upload()
        response = self.client.post('/api/battles',json={'version':identifier,'seed':42})
        battle = response.json()['id']
        self.client.post(f'/api/battles/{battle}/step')
        diagnostics = self.client.get(f'/api/battles/{battle}/diagnostics').json()
        self.assertEqual(len(diagnostics['events']),1)
        self.assertEqual(diagnostics['events'][0]['seed'],42)
        experiment = self.client.post(f'/api/battles/{battle}/experiments').json()
        saved = experiment['id']
        self.assertEqual(self.client.get('/api/experiments').json()[0]['id'],saved)
        for format in ('json','csv','markdown'):
            exported = self.client.get(f'/api/experiments/{saved}/export/{format}')
            self.assertEqual(exported.status_code,200)
            self.assertIn('seed:42/tick:1/seat:A',exported.text)
        prompt = self.client.get(f'/api/experiments/{saved}/prompt')
        self.assertIn('seed:42/tick:1/seat:A',prompt.text)
        replay = self.client.get(f'/api/experiments/{saved}/replay/1').json()
        self.assertEqual(replay,self.client.get(f'/api/battles/{battle}/frames/1').json())
        self.client.delete(f'/api/battles/{battle}')
        with TestClient(create_app(self.temp.name)) as restarted:
            self.assertEqual(restarted.get(f'/api/experiments/{saved}/replay/1').json(),replay)
        self.assertEqual(self.client.get(f'/api/experiments/{saved}/replay/99').status_code,404)
        self.assertEqual(self.client.get(f'/api/experiments/{saved}/export/pdf').status_code,422)

    def test_pool_experiments_and_benchmark_record_replay(self):
        from test_diagnostics import report
        from battleship_lab import Battle
        from battleship_lab.diagnostics import EvidenceRecorder, diagnose
        identifier = self.upload()
        b = Battle(2)
        recorder = EvidenceRecorder(b)
        recorder.begin(b,None,'invalid_action');b.step({});recorder.finish(b)
        def fake_benchmark(*args,progress):
            progress(100,100)
            value = report(args[5])
            value['rounds']['round1']['strategies'][0]['records'][0].update(diagnostics=diagnose(recorder.events),replay=recorder.replay())
            return value
        experiments = []
        with patch('battleship_lab.web.benchmark',side_effect=fake_benchmark):
            for pool in ('development','holdout'):
                job = self.client.post('/api/benchmarks',json={'versions':[identifier],'pool':pool}).json()['id']
                for _ in range(100):
                    result = self.client.get(f'/api/benchmarks/{job}').json()
                    if result['status']!='running':break
                    time.sleep(.01)
                self.assertEqual(result['status'],'complete',result)
                experiments.append(result['experiment_id'])
        combined = self.client.post('/api/experiments/compare-pools',json={'development':experiments[0],'validation':experiments[1]})
        self.assertEqual(combined.status_code,200,combined.text)
        self.assertTrue(combined.json()['diagnostics']['findings'])
        replay = self.client.get(f'/api/experiments/{experiments[0]}/replay/1?round=round1&strategy=0&match=0')
        self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(replay.json()['tick'],1)
        prompt = self.client.get(f'/api/experiments/{experiments[0]}/prompt?round=round1&strategy=0&match=0')
        self.assertIn('invalid_action',prompt.text)


    def test_tick_checked_requests_are_idempotent_and_opponents_have_purchases(self):
        version = self.upload()
        battle = self.client.post('/api/battles',json=dict(version=version,round='round2',seed=7,loadout={'flare':2})).json()
        identifier = battle['id']
        opponent = battle['frame']['teams'][1]['boosters']
        self.assertEqual(opponent['purchased']['flare'],1)
        self.assertEqual(opponent['purchased']['cluster'],6)
        first = self.client.post(f'/api/battles/{identifier}/step',json={'expected_tick':0})
        duplicate = self.client.post(f'/api/battles/{identifier}/step',json={'expected_tick':0})
        self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(first.json(),duplicate.json())
        self.assertEqual(first.json()['tick'],1)
        self.assertEqual(self.client.post(f'/api/battles/{identifier}/step',json={'expected_tick':2}).status_code,409)
        self.assertEqual(self.client.post(f'/api/battles/{identifier}/step',json={'expected_tick':True}).status_code,422)


if __name__ == '__main__':
    unittest.main()
