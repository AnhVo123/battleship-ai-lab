from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from battleship_lab import Battle, RoundConfig
from battleship_lab.validation import TEMPLATE
from battleship_lab.web import create_app


class RankingOrderTests(unittest.TestCase):
    def test_each_official_tiebreaker_in_isolation(self):
        cases=[('joined',True,False),('score',8,7),('wasted',0,1),
               ('last_sink',3,None),('last_sink',3,4),('last_point',3,None),
               ('last_point',3,4),('first_point',3,None),('first_point',3,4)]
        for field,better,worse in cases:
            with self.subTest(field=field,better=better,worse=worse):
                battle=Battle(42)
                setattr(battle.seats['B'],field,better)
                setattr(battle.seats['A'],field,worse)
                self.assertEqual(battle.results()['ranking'][0]['seat'],'B')
        self.assertEqual(Battle(42).results()['ranking'][0]['seat'],'A')

    def test_score_precedes_survival_and_other_tiebreakers(self):
        battle=Battle(42)
        a,b=battle.seats.values()
        a.score,b.score=5,4
        a.wasted,b.wasted=100,0
        for ship in a.ships:ship.holes.update(ship.cells)
        self.assertEqual(battle.results()['ranking'][0]['seat'],'A')
        a.joined=False
        self.assertEqual(battle.results()['ranking'][0]['seat'],'B')


class ResultHistoryTests(unittest.TestCase):
    def test_each_difficulty_records_its_actual_policy(self):
        from battleship_lab.opponents import LEVELS
        with tempfile.TemporaryDirectory() as temporary, TestClient(create_app(temporary)) as client:
            version=client.post('/api/versions',json={'source':TEMPLATE}).json()['id']
            for level,name in LEVELS.items():
                with self.subTest(level=level):
                    battle=client.post('/api/battles',json={'version':version,'difficulty':level}).json()
                    strategy=battle['frame']['teams'][1]['strategy']
                    self.assertEqual(strategy['level'],level)
                    self.assertEqual(strategy['name'],name)
                    self.assertEqual(strategy['implementation'],'local_approximation')
                    self.assertIn('class Opponent(Bot):',strategy['source'])
                    client.delete('/api/battles/'+battle['id'])

    def test_completion_autosaves_named_rankings_and_replay_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            with TestClient(create_app(temporary)) as client:
                version=client.post('/api/versions',json={'source':TEMPLATE,'label':'My test team'}).json()['id']
                with patch('battleship_lab.web.RoundConfig.preset',return_value=RoundConfig(tick_cap=1)):
                    created=client.post('/api/battles',json={'version':version,'teams':4,'difficulty':'easy','seed':42}).json()
                identifier=created['id']
                strategies={t['seat']:t['strategy'] for t in created['frame']['teams']}
                self.assertEqual(strategies['A']['source'],TEMPLATE)
                self.assertEqual(strategies['A']['version'],version)
                for seat in ('B','C','D'):
                    self.assertEqual(strategies[seat]['level'],'easy')
                    self.assertFalse(strategies[seat]['official'])
                    self.assertEqual(strategies[seat]['type'],'Opponent')
                    self.assertEqual(strategies[seat]['source'],Path('battleship_lab/opponents.py').read_text(encoding='utf-8'))
                self.assertEqual(client.get('/api/battle-history').json(),[])
                final=client.post(f'/api/battles/{identifier}/step').json()
                self.assertTrue(final['finished'])
                self.assertEqual({t['seat']:t['strategy'] for t in final['teams']},strategies)
                self.assertEqual(len(final['ranking']),4)
                self.assertEqual([r['rank'] for r in final['ranking']],[1,2,3,4])
                mine=next(r for r in final['ranking'] if r['seat']=='A')
                self.assertEqual(mine['name'],'My test team')
                self.assertEqual(mine['ships_remaining'],sum(not s['sunk'] for s in final['teams'][0]['ships']))
                saved=client.get('/api/battle-history').json()
                self.assertEqual(len(saved),1)
                history_id=final['history_id']
                self.assertEqual(saved[0]['id'],history_id)
                self.assertEqual(saved[0]['ranking'],final['ranking'])
                self.assertEqual(client.post(f'/api/battles/{identifier}/step').json(),final)
                self.assertEqual(client.post(f'/api/battles/{identifier}/experiments').json()['id'],history_id)
                self.assertEqual(len(client.get('/api/battle-history').json()),1)
                client.delete(f'/api/battles/{identifier}')
                self.assertEqual(client.get(f'/api/experiments/{history_id}').json()['frames'],[created['frame'],final])
            with TestClient(create_app(temporary)) as restarted:
                self.assertEqual(restarted.get('/api/battle-history').json()[0]['ranking'],final['ranking'])
                self.assertEqual(restarted.get(f'/api/experiments/{history_id}/replay/1').json(),final)
            self.assertEqual(len(list((Path(temporary)/'experiments').glob('*.json'))),1)

    def test_partial_snapshots_are_not_completed_history(self):
        with tempfile.TemporaryDirectory() as temporary, TestClient(create_app(temporary)) as client:
            version=client.post('/api/versions',json={'source':TEMPLATE}).json()['id']
            battle=client.post('/api/battles',json={'version':version}).json()['id']
            client.post(f'/api/battles/{battle}/experiments')
            self.assertEqual(client.get('/api/battle-history').json(),[])


if __name__=='__main__':unittest.main()
