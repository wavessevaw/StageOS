"""Offline protocol regression tests. No theatre database, identities or weights.

IDs are protocol fixtures; role assignments below are not training examples or
approved theatre casts. All databases are fresh and in memory.
"""
import asyncio
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.models import Base, Resource, Production
from backend.production_editor import template
from backend import cast_proposals as cp, model_client


CFG = {'provider':'Ollama','endpoint':'http://127.0.0.1:11434/v1','model':'qwen3:0.6b'}


def context(messages):
    return json.loads(messages[0]['content'].split('\nДанные: ',1)[1])


async def eligible_reply(cfg, messages, factory, max_tokens):
    item=context(messages)
    return json.dumps({'answer':'Proposal only','choices':[{'key':item['key'],'people':[item['candidates'][0]['id']]}]})


class CastProposalTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.s=Session(self.engine)
        for rid in (19,33,37,38):
            self.s.add(Resource(id=rid,name=str(rid),kind='Person',department='Артисты',data={'qualification':['Артисты']}))
        data=template()['data']
        data['roles']=[{'role':'Старшина Васков Федот Евграфович','eligible':[19,33],'A':0,'B':0}]
        self.p=Production(id=1,name='Protocol test',version=1,data=data)
        self.s.add(self.p);self.s.commit()

    def tearDown(self):
        self.s.close();self.engine.dispose()

    def run_proposal(self,reply=eligible_reply):
        with patch.object(model_client,'request_model',reply):
            return asyncio.run(cp.propose(self.s,self.p,CFG,None))

    def test_distinct_casts_and_no_database_write(self):
        before=deepcopy(self.p.data)
        result=self.run_proposal()
        self.assertEqual([r['proposed'] for r in result['rows']],[[19],[33]])
        self.assertEqual(self.p.data,before)
        self.assertEqual(self.p.version,1)

    def test_preserve_existing_assignment(self):
        self.p.data['roles'][0]['A']=33
        result=self.run_proposal()
        self.assertEqual([r['proposed'] for r in result['rows']],[[33],[19]])

    def test_no_candidates_no_model_call(self):
        self.p.data['roles'][0]['eligible']=[]
        async def forbidden(*args,**kwargs):raise AssertionError('No model call expected')
        result=self.run_proposal(forbidden)
        self.assertTrue(all(not r['proposed'] for r in result['rows']))

    def test_collective_labels_and_explicit_marker(self):
        for label in ('Солисты','В спектакле принимают участие','Придворные','Семейная пара','Ромашки','Служанки'):
            with self.subTest(label=label):
                self.p.data['roles'][0]['role']=label
                result=self.run_proposal()
                self.assertTrue(all(not r['proposed'] and r['count']==0 for r in result['rows']))
        self.p.data['roles'][0].update(role='Unknown ensemble',collective=True)
        self.assertTrue(all(r['count']==0 for r in self.run_proposal()['rows']))

    def test_collective_existing_assignment_preserved(self):
        self.p.data['roles'][0].update(role='Солисты',A=19)
        result=self.run_proposal()
        self.assertEqual([r['proposed'] for r in result['rows']],[[19],[]])

    def test_raw_invalid_reply_stays_empty_and_has_exact_error(self):
        async def bad(cfg,messages,*args,**kwargs):
            item=context(messages)
            return json.dumps({'answer':'Invalid','choices':[{'key':item['key'],'people':[{'id':19}]}]})
        result=self.run_proposal(bad)
        self.assertTrue(all(not r['proposed'] for r in result['rows']))
        self.assertEqual(len(result['diagnostics']),4)
        self.assertTrue(all('ValidationError' in r['issue'] for r in result['rows']))

    def test_one_retry_repairs_response(self):
        attempts={}
        async def retry(cfg,messages,*args,**kwargs):
            item=context(messages);key=item['key'];attempts[key]=attempts.get(key,0)+1
            if attempts[key]==1:return json.dumps({'answer':'Bad','choices':[{'key':key,'people':['19']}]})
            return await eligible_reply(cfg,messages,None,256)
        result=self.run_proposal(retry)
        self.assertEqual([r['proposed'] for r in result['rows']],[[19],[33]])
        self.assertEqual([x['valid'] for x in result['diagnostics']],[False,True,False,True])

    def test_missing_extra_or_duplicate_keys_rejected(self):
        for mode in ('missing','extra','duplicate'):
            with self.subTest(mode=mode):
                async def bad(cfg,messages,*args,**kwargs):
                    item=context(messages);c={'key':item['key'],'people':[item['candidates'][0]['id']]}
                    choices=[] if mode=='missing' else [c,c] if mode=='duplicate' else [c,{'key':'role:999:A','people':[]}]
                    return json.dumps({'answer':'Bad','choices':choices})
                self.assertTrue(all(not r['proposed'] for r in self.run_proposal(bad)['rows']))

    def test_strict_codes_count_and_eligibility(self):
        rows=cp.slots(self.s,self.p)
        for ids in (['19'],[True],[{'id':19}],[19,33],[19,19],[38]):
            with self.subTest(ids=ids):
                with self.assertRaises((ValueError,TypeError)):
                    cp.checked_data(self.s,self.p,rows,[cp.Choice(key='role:0:A',people=ids)])

    def test_shared_pool_cannot_assign_actor_twice(self):
        # Adversarial intersecting pools, not a statement of theatre eligibility.
        self.p.data['roles'].append({'role':'Intersection protocol fixture','eligible':[19,33],'A':0,'B':0})
        result=self.run_proposal()
        for cast in ('A','B'):
            ids=[r['proposed'][0] for r in result['rows'] if r['cast']==cast and r['proposed']]
            self.assertEqual(len(ids),len(set(ids)))
        with self.assertRaisesRegex(ValueError,'несколько ролей'):
            cp.checked_data(self.s,self.p,cp.slots(self.s,self.p),[cp.Choice(key='role:0:A',people=[19]),cp.Choice(key='role:1:A',people=[19])])

    def test_context_is_refreshed_between_invocations(self):
        self.run_proposal()
        self.p.data['roles'][0]['eligible']=[37,38]
        result=self.run_proposal()
        self.assertEqual([r['proposed'] for r in result['rows']],[[37],[38]])

    def test_json_and_top_level_contract(self):
        for raw in ('not JSON','[]','{"choices":[]}','{"answer":"x","choices":[],"extra":1}'):
            with self.subTest(raw=raw):
                async def bad(*args,**kwargs):return raw
                self.assertTrue(all(not r['proposed'] for r in self.run_proposal(bad)['rows']))

    def test_collective_slot_cannot_be_filled_manually(self):
        self.p.data['roles'][0]['collective']=True
        with self.assertRaisesRegex(ValueError,'количество мест'):
            cp.checked_data(self.s,self.p,cp.slots(self.s,self.p),[cp.Choice(key='role:0:A',people=[19])])

    def test_group_casts_keep_full_known_pool_and_partial_warning(self):
        self.p.data['groups']={'Артисты':[19,33,37,38]}
        async def reply(cfg,messages,factory,max_tokens):
            item=context(messages)
            ids=[c['id'] for c in item['candidates']]
            if item['key'].startswith('groups:'):
                self.assertEqual(len(ids),4)
                return json.dumps({'answer':'Partial','choices':[{'key':item['key'],'people':ids[:2]}]})
            return await eligible_reply(cfg,messages,factory,max_tokens)
        result=self.run_proposal(reply)
        groups=[r for r in result['rows'] if r['section']=='groups']
        self.assertEqual(len(groups),2)
        self.assertTrue(all(len(r['proposed'])==2 and 'частично' in r['issue'] for r in groups))

    def test_native_ollama_request_parameters(self):
        captured={}
        class Response:
            def raise_for_status(self):pass
            def json(self):return {'message':{'content':'{"answer":"OK","choices":[]}'}}
        class Client:
            def __init__(self,**kwargs):captured['client']=kwargs
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            async def post(self,url,json):captured.update(url=url,payload=json);return Response()
        asyncio.run(model_client.request_model(CFG,[{'role':'user','content':'test'}],Client,max_tokens=256))
        self.assertEqual(captured['url'],'http://127.0.0.1:11434/api/chat')
        self.assertEqual(captured['payload']['format'],'json')
        self.assertIs(captured['payload']['stream'],False)
        self.assertIs(captured['payload']['think'],False)
        self.assertEqual(captured['payload']['options']['temperature'],0)
        self.assertEqual(captured['payload']['options']['num_predict'],256)


if __name__=='__main__':unittest.main()
