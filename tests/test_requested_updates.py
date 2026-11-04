import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from battleship_lab import Battle, RoundConfig
from battleship_lab.validation import TEMPLATE, validate_source
from battleship_lab.strategies import StrategyProcess, import_strategy
from battleship_lab.strategy_worker import validate
from battleship_lab.web import create_app


class SourceValidationTests(unittest.TestCase):
    def test_template_and_readme_interface(self):
        self.assertTrue(validate_source(TEMPLATE)['valid'])
        self.assertFalse(validate_source('class MyBot: pass')['valid'])
        self.assertFalse(validate_source(TEMPLATE.replace('def on_state(self, state):','async def on_state(self, state):'))['valid'])
        self.assertFalse(validate_source(TEMPLATE.replace('def on_state(self, state):','def on_state(self, state, extra):'))['valid'])

    def test_invalid_imports_and_prohibited_calls(self):
        for line in ('import requests','import secrets','import importlib','from os import urandom','os.urandom(1)','eval("1")'):
            with self.subTest(line=line):
                result = validate_source(line+'\n'+TEMPLATE)
                self.assertFalse(result['valid'])
                self.assertTrue(result['errors'])
        self.assertTrue(validate_source('import math\nimport numpy\n'+TEMPLATE)['valid'])

    def test_integer_and_named_ship_actions(self):
        b = Battle(42)
        state = b.state('A')
        action = dict(ship=0,dir=90.,elev=45.,power=5)
        self.assertEqual(validate(action,state)['ship'],'carrier')
        self.assertIs(b._valid(b.seats['A'],action),b.seats['A'].ships[0])
        for identifier in (True,-1,5,0.0,'unknown'):
            self.assertIsNone(validate({**action,'ship':identifier},state))
        b.seats['A'].ships[0].holes.update(b.seats['A'].ships[0].cells)
        self.assertIsNone(validate(action,b.state('A')))
        self.assertIsNone(b._valid(b.seats['A'],action))

    def test_template_runs_and_instances_reset(self):
        code = TEMPLATE.replace('self.rng.uniform(0.0, 360.0)', 'float(getattr(self, "counter", 0))').replace('# Preserve state on self between ticks; a new instance starts each battle.', 'self.counter = getattr(self, "counter", 0) + 1')
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'strategy.py';path.write_text(code,encoding='utf-8')
            version = import_strategy(path,Path(temporary)/'versions')
            state = Battle().state('A')
            with StrategyProcess(version) as first:
                self.assertEqual(first.on_state(state)['dir'],1.)
                self.assertEqual(first.on_state(state)['dir'],2.)
            with StrategyProcess(version) as second:
                self.assertEqual(second.on_state(state)['dir'],1.)


class UpdateApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.client = TestClient(create_app(self.temp.name))
        self.client.__enter__();self.addCleanup(self.client.__exit__,None,None,None)
        response = self.client.post('/api/versions',json={'source':TEMPLATE})
        self.assertEqual(response.status_code,201,response.text)
        self.version = response.json()['id']

    def test_static_and_runtime_validation(self):
        self.assertFalse(self.client.post('/api/validate',json={'source':'invalid !'}).json()['valid'])
        self.assertFalse(self.client.post('/api/validate',json={'source':'import requests\n'+TEMPLATE}).json()['valid'])
        self.assertTrue(self.client.post('/api/validate-runtime',json={'source':TEMPLATE}).json()['valid'])
        result = self.client.post('/api/validate-runtime',json={'source':'raise RuntimeError("startup failure")\n'+TEMPLATE}).json()
        self.assertFalse(result['valid'])
        self.assertIn('startup failure',result['errors'][0]['message'])

    def test_opponent_actual_source_is_labeled_custom(self):
        for level in ('easy','medium','hard','expert','extreme'):
            response = self.client.get('/api/opponents/'+level)
            self.assertEqual(response.status_code,200)
            value=response.json()
            self.assertFalse(value['official'])
            self.assertIn('class Opponent',value['source'])
            self.assertTrue(value['algorithm'])

    def test_round_armory_rejects_invalid_purchases(self):
        for body in ({'round':'round1','loadout':{'flare':1}}, {'round':'round2','loadout':{'torpedo':1}},
                     {'round':'final','loadout':{'torpedo':2}}, {'round':'final','loadout':{'flare':-1}},
                     {'round':'final','loadout':{'flare':True}}, {'round':'final','loadout':{'flare':.5}},
                     {'round':'final','advanced':True}):
            self.assertEqual(self.client.post('/api/armory',json=body).status_code,422,str(body))
        quote = self.client.post('/api/armory',json={'round':'round2','loadout':{'flare':2,'cluster':2}}).json()
        self.assertEqual(quote['remaining'],0)

    def test_purchased_inventory_is_used_not_refunded(self):
        body = dict(version=self.version,round='round2',seed=42,loadout={'flare':1})
        response = self.client.post('/api/battles',json=body)
        self.assertEqual(response.status_code,201,response.text)
        frame=response.json()['frame']
        self.assertEqual(frame['armory']['inventory']['flare'],1)
        self.assertEqual(frame['armory']['remaining_points'],6)
        self.assertEqual(response.json()['armory']['spent'],4)
        self.assertEqual(frame['teams'][0]['seat'],'A')

    def test_only_completed_round2_points_carry_to_final(self):
        with patch('battleship_lab.web.RoundConfig.preset',return_value=RoundConfig('round2',tick_cap=1,points=10,unlocked=('flare','cluster'))):
            response=self.client.post('/api/battles',json=dict(version=self.version,round='round2',seed=42,loadout={'flare':1}))
        previous=response.json()['id']
        quote=dict(round='final',carryover_from=previous,advanced=True,loadout={'torpedo':2,'cluster':2})
        self.assertEqual(self.client.post('/api/armory',json=quote).status_code,422)
        ended=self.client.post(f'/api/battles/{previous}/step').json()
        self.assertTrue(ended['armory']['expired'])
        value=self.client.post('/api/armory',json=quote).json()
        self.assertEqual(value['budget'],16)
        self.assertEqual(value['remaining'],0)
        final=self.client.post('/api/battles',json={**quote,'version':self.version,'seed':42})
        self.assertEqual(final.status_code,201,final.text)
        inventory=final.json()['frame']['armory']['inventory']
        self.assertEqual(inventory['torpedo'],2)
        self.assertEqual(inventory['flare'],0)  # unused purchased flare is not carried
        self.assertEqual(self.client.post('/api/armory',json={**quote,'advanced':False}).status_code,422)
        snapshot=self.client.post(f'/api/battles/{previous}/experiments').json()
        self.client.delete(f'/api/battles/{previous}')
        self.assertIn(snapshot['id'],[s['id'] for s in self.client.get('/api/armory/carryover').json()])
        with TestClient(create_app(self.temp.name)) as restarted:
            carried=restarted.post('/api/armory',json={**quote,'carryover_from':snapshot['id']})
            self.assertEqual(carried.status_code,200,carried.text)
            self.assertEqual(carried.json()['budget'],16)

    def test_new_battles_randomize_but_explicit_seed_replays(self):
        initial=[]
        for _ in range(2):
            response=self.client.post('/api/battles',json={'version':self.version})
            self.assertEqual(response.status_code,201,response.text)
            initial.append(response.json())
        self.assertNotEqual(initial[0]['seed'],initial[1]['seed'])
        self.assertNotEqual(initial[0]['frame']['wind'],initial[1]['frame']['wind'])
        again=self.client.post('/api/battles',json={'version':self.version,'seed':initial[0]['seed']}).json()
        self.assertEqual(again['frame']['wind'],initial[0]['frame']['wind'])
        self.assertEqual(again['frame']['teams'],initial[0]['frame']['teams'])
        for _ in range(3):
            frame=self.client.post(f'/api/battles/{again["id"]}/step').json()
            self.assertEqual(frame['wind'],again['frame']['wind'])
            self.assertTrue(all(-1 <= n <= 1 for n in frame['wind']))
            self.assertEqual(frame['strategy_status'],'ok')


if __name__=='__main__':
    unittest.main()
