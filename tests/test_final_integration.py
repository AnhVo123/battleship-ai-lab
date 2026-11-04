"""Opt-in end-to-end checks against the real Windows-started local service.

Set BATTLESHIP_INTEGRATION_URL=http://127.0.0.1:8000 to run these tests.
Uses real 120-tick presets and 100-match benchmarks; no engine mocks.
"""
import json
import os
import time
import unittest

import httpx

from battleship_lab import Battle


PRIVACY_STRATEGY = '''from arena_sdk import Bot
import math, os, sys
class MyBot(Bot):
 def on_state(self, state):
  assert set(state) == {'tick','deadline_ms','seats','you','your_shots','last_results','revealed','config'}
  assert set(state['you']) == {'slot','score','ships','incoming_shots','ships_alive','boosters'}
  assert 'BATTLESHIP_DATA' not in os.environ
  assert ':bot:' not in sys.argv[-1]
  def check(value):
   if isinstance(value, dict):
    assert not set(value) & {'seed','wind','teams','ranking','frames','traces','opponents','enemy_ships'}
    for item in value.values(): check(item)
   elif isinstance(value,list):
    for item in value: check(item)
  check(state)
  ship = self.rng.choice([s for s in state['you']['ships'] if not s['sunk']])
  assert set(ship) == {'ship','cells','holed','sunk'}
  direction = self.rng.uniform(0,360)
  power = self.rng.randint(1,5)
  flight = 2*power*4*math.sin(math.pi/4)/9.8
  speed = power*4*math.cos(math.pi/4)
  target = [round(ship['cells'][0][0]-speed*math.cos(math.radians(direction))*flight), round(ship['cells'][0][1]+speed*math.sin(math.radians(direction))*flight)]
  action = dict(ship=ship['ship'],dir=direction,elev=45,power=power,diagnostics={'target':target,'wind':[0,0]})
  for kind,count in state['you']['boosters'].items():
   if count:
    action['action'] = kind
    break
  return action
'''


class RefereePrivacyTests(unittest.TestCase):
    def test_unobserved_referee_changes_do_not_change_private_view(self):
        battle = Battle(42)
        before = battle.state('A')
        battle.wind = (-.987,.765)
        battle.seed = 999999
        other = battle.seats['B']
        other.score = 31415
        other.connected = False
        other.boosters['flare'] = 20
        for ship in other.ships:
            ship.cells = [(39-r,39-c) for r,c in ship.cells]
            ship.holes = set(ship.cells)
        other.eliminated = True
        self.assertEqual(battle.state('A'),before)


@unittest.skipUnless(os.environ.get('BATTLESHIP_INTEGRATION_URL'),'opt-in live service integration')
class LiveIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = httpx.Client(base_url=os.environ['BATTLESHIP_INTEGRATION_URL'],timeout=60,trust_env=False)
        response = cls.client.post('/api/versions',json={'filename':'integration.py','source':PRIVACY_STRATEGY,'label':'Integration privacy probe'})
        response.raise_for_status()
        cls.version = response.json()['id']

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def test_01_startup_and_import(self):
        self.assertEqual(self.client.get('/').status_code,200)
        self.assertIn('Battleship Strategy Lab',self.client.get('/').text)
        self.assertEqual(self.client.get('/api/health').json()['engine_kind'],'local_approximation')
        self.assertEqual(self.client.get(f'/api/versions/{self.version}/source').text,PRIVACY_STRATEGY)

    def test_02_all_rounds_and_difficulties_complete_with_replay(self):
        summaries = []
        for round_name in ('round1','round2','final'):
            for index,difficulty in enumerate(('easy','medium','hard','expert','extreme')):
                with self.subTest(round=round_name,difficulty=difficulty):
                    loadout = {} if round_name=='round1' else {'flare':2,'cluster':2}
                    if round_name=='final':
                        loadout = {'torpedo':1,'cluster':3} if index%2==0 else {'flare':1,'cluster':2,'teleport':1}
                    response = self.client.post('/api/battles',json={'version':self.version,'round':round_name,'difficulty':difficulty,'teams':2,'seed':42+index,'loadout':loadout})
                    self.assertEqual(response.status_code,201,response.text)
                    battle = response.json()['id']
                    initial = response.json()['frame']
                    try:
                        for _ in range(120):
                            result = self.client.post(f'/api/battles/{battle}/step')
                            self.assertEqual(result.status_code,200,result.text)
                            frame = result.json()
                            self.assertEqual(frame['strategy_status'],'ok',frame)
                            if frame['finished']:break
                        self.assertTrue(frame['finished'])
                        self.assertFalse(frame['abandoned'])
                        self.assertEqual(len(frame['ranking']),2)
                        self.assertEqual(self.client.get(f'/api/battles/{battle}/frames/0').json(),initial)
                        diagnostic = self.client.get(f'/api/battles/{battle}/diagnostics').json()
                        errors = [f for f in diagnostic['findings'] if f['code'] in ('exception','timeout','invalid_action','worker_exit')]
                        self.assertEqual(errors,[])
                        self.assertGreater(diagnostic['metrics']['wind_samples'],0)
                        saved = self.client.post(f'/api/battles/{battle}/experiments').json()
                        prompt = self.client.get(f'/api/experiments/{saved["id"]}/prompt').text
                        if diagnostic['findings']:
                            self.assertIn('seed:',prompt)
                        self.assertEqual(self.client.get(f'/api/experiments/{saved["id"]}/replay/{frame["tick"]}').json(),frame)
                        for format in ('json','csv','markdown'):
                            exported = self.client.get(f'/api/experiments/{saved["id"]}/export/{format}')
                            self.assertEqual(exported.status_code,200)
                            self.assertIn('seed:',exported.text)
                        summaries.append({'round':round_name,'difficulty':difficulty,'ticks':frame['tick'],'score':frame['teams'][0]['score'],'boosters_used':list(diagnostic['boosters'])})
                    finally:
                        self.client.delete(f'/api/battles/{battle}')
        print('FULL_BATTLES '+json.dumps(summaries),flush=True)

    def test_03_twenty_teams_live_battle(self):
        response = self.client.post('/api/battles',json={'version':self.version,'round':'final','difficulty':'easy','teams':20,'seed':7})
        self.assertEqual(response.status_code,201,response.text)
        battle = response.json()['id']
        try:
            for _ in range(3):
                frame = self.client.post(f'/api/battles/{battle}/step').json()
                self.assertEqual(len(frame['teams']),20)
                self.assertEqual(frame['strategy_status'],'ok')
            self.assertEqual(self.client.get(f'/api/battles/{battle}/frames/3').json(),frame)
        finally:
            self.client.delete(f'/api/battles/{battle}')

    def test_04_real_full_length_batch_benchmark(self):
        response = self.client.post('/api/benchmarks',json={'versions':[self.version],'matches':100,'teams':2,'round':'round1','difficulty':'medium','pool':'development','master_seed':20261104})
        self.assertEqual(response.status_code,202,response.text)
        identifier = response.json()['id']
        deadline,previous = time.monotonic()+900,-1
        while time.monotonic()<deadline:
            result = self.client.get(f'/api/benchmarks/{identifier}').json()
            if result['status']!='running':break
            done = result.get('done',0)
            if done//20 != previous:
                print(f'REAL_BENCHMARK {done}/100',flush=True)
                previous=done//20
            time.sleep(.5)
        self.assertEqual(result['status'],'complete',result)
        run = result['report']['rounds']['round1']['strategies'][0]
        records = run['records']
        self.assertEqual(len(records),100)
        self.assertEqual(len({r['seed'] for r in records}),100)
        self.assertTrue(any(r['score']>0 for r in records))
        self.assertTrue(all(len(r['diagnostics']['events'])==120 for r in records))
        self.assertTrue(all(not r['errors'] for r in records))
        self.assertTrue(all(r['diagnostics']['metrics']['points']==r['score'] for r in records))
        self.assertEqual(run['summary']['timeouts_total'],0)
        experiment = result['experiment_id']
        self.assertEqual(self.client.get(f'/api/experiments/{experiment}/replay/120?round=round1&strategy=0&match=0').json()['tick'],120)
        self.assertIn('seed:',self.client.get(f'/api/experiments/{experiment}/prompt?round=round1&strategy=0&match=0').text)
        print('REAL_BENCHMARK_RESULT '+json.dumps({'job':identifier,'experiment':experiment,'summary':run['summary']}),flush=True)


if __name__=='__main__':
    unittest.main()
