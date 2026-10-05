import json
from copy import deepcopy
import httpx
import pytest
from sqlalchemy import select, func
from test_core import ctx
from backend.models import Production, Event, Resource, Audit
from backend.cast_proposals import slots


def prepare(ctx):
    c,S,b,rs,r=ctx
    with S.begin() as s:
        p=s.get(Production,1)
        data=deepcopy(p.data)
        for role in data['roles']:role['A']=role['B']=0
        p.data=data
    c.put('/api/settings/llm',json={'enabled':True,'provider':'Ollama','endpoint':'http://127.0.0.1:11434/v1','model':'qwen3:0.6b'})
    return c,S


def mock_model(monkeypatch, build):
    async def handle(req):
        body=json.loads(req.content)
        assert req.url.path=='/api/chat' and body['think'] is False
        context=json.loads(body['messages'][1]['content'])
        return httpx.Response(200,json={'message':{'content':json.dumps(build(context))}})
    factory=httpx.AsyncClient
    monkeypatch.setattr('backend.app.httpx.AsyncClient',lambda **kw:factory(transport=httpx.MockTransport(handle),**kw))


def choices(context):
    used={'A':set(),'B':set()}
    out=[]
    for row in context['slots']:
        ids=[x['id'] for x in row['candidates'] if x['id'] not in used[row['cast']]][:row['count']]
        used[row['cast']].update(ids)
        out.append({'key':row['key'],'people':ids})
    return {'answer':'По допускам','choices':out}


def test_model_reads_database_proposes_without_writing_and_confirmation_is_atomic(ctx,monkeypatch):
    c,S=prepare(ctx)
    mock_model(monkeypatch,choices)
    with S() as s:
        before=deepcopy(s.get(Production,1).data)
        events=s.scalar(select(func.count(Event.id)))
    response=c.post('/api/productions/1/cast-proposal',json={'department':'Артисты'})
    assert response.status_code==200,response.text
    result=response.json()
    assert any(r['proposed'] for r in result['rows'])
    with S() as s:assert s.get(Production,1).data==before
    payload={'version':result['version'],'choices':[{'key':r['key'],'people':r['proposed']} for r in result['rows']]}
    saved=c.post('/api/productions/1/cast-proposal/confirm',json=payload)
    assert saved.status_code==200,saved.text
    assert saved.json()['version']==result['version']+1
    with S() as s:
        assert s.scalar(select(func.count(Event.id)))==events
        assert s.scalar(select(Audit).where(Audit.action=='Составы подтверждены'))
    assert c.post('/api/productions/1/cast-proposal/confirm',json=payload).status_code==409


@pytest.mark.parametrize('bad',[999999,True,'1'])
def test_invalid_model_ids_are_discarded_and_cannot_be_saved(ctx,monkeypatch,bad):
    c,S=prepare(ctx)
    mock_model(monkeypatch,lambda x:{'answer':'','choices':[{'key':x['slots'][0]['key'],'people':[bad]}]})
    result=c.post('/api/productions/1/cast-proposal',json={}).json()
    assert result['failed_departments']==['Артисты']
    assert all(not r['proposed'] for r in result['rows'])
    response=c.post('/api/productions/1/cast-proposal/confirm',json={'version':result['version'],
        'choices':[{'key':result['rows'][0]['key'],'people':[bad]}]})
    assert response.status_code==422
    with S() as s:assert all(not r['A'] and not r['B'] for r in s.get(Production,1).data['roles'])


def test_missing_eligibility_is_left_empty_without_calling_model(ctx,monkeypatch):
    c,S=prepare(ctx)
    with S.begin() as s:
        p=s.get(Production,1);d=deepcopy(p.data)
        for r in d['roles']:r['eligible']=[]
        p.data=d
    async def fail(*a,**k):raise AssertionError('Must not request model without eligibility')
    monkeypatch.setattr('backend.model_client.request_model',fail)
    result=c.post('/api/productions/1/cast-proposal',json={}).json()
    assert all(not r['proposed'] and r['issue'] for r in result['rows'])


def test_retired_employee_and_duplicate_actor_are_rejected_at_confirmation(ctx):
    c,S=prepare(ctx)
    with S() as s:rows=slots(s,s.get(Production,1));version=s.get(Production,1).version
    first=rows[0];person=first['allowed'][0]
    with S.begin() as s:
        p=s.get(Production,1);d=deepcopy(p.data);d['roles'][1]['eligible'].append(person);p.data=d
    body={'version':version,'choices':[{'key':first['key'],'people':[person]},
        {'key':rows[2]['key'],'people':[person]}]}
    assert c.post('/api/productions/1/cast-proposal/confirm',json=body).status_code==422
    with S.begin() as s:
        r=s.get(Resource,person);r.data={**r.data,'retired':True}
    body['choices']=body['choices'][:1]
    assert c.post('/api/productions/1/cast-proposal/confirm',json=body).status_code==422


def test_groups_use_only_known_production_members_and_preserve_existing_casts(ctx,monkeypatch):
    c,S=prepare(ctx)
    mock_model(monkeypatch,choices)
    result=c.post('/api/productions/1/cast-proposal',json={'department':'Хор'}).json()
    assert result['rows'] and all(set(r['proposed'])<=set(r['allowed']) for r in result['rows'])
    payload={'version':result['version'],'choices':[{'key':r['key'],'people':r['proposed']} for r in result['rows']]}
    assert c.post('/api/productions/1/cast-proposal/confirm',json=payload).status_code==200
    response=c.post('/api/productions/1/cast-proposal',json={'department':'Хор'}).json()
    assert all(r['current']==r['proposed'] for r in response['rows'])
    wrong={'version':response['version'],'choices':[{'key':response['rows'][0]['key'],'people':[]}]}
    assert c.post('/api/productions/1/cast-proposal/confirm',json=wrong).status_code==422


def test_disabled_model_and_unknown_production(ctx):
    c,S=prepare(ctx)
    assert c.post('/api/productions/999999/cast-proposal',json={}).status_code==404
    assert c.post('/api/productions/1/cast-proposal',json={'department':'Несуществующий'}).status_code==422
    c.put('/api/settings/llm',json={'enabled':False,'provider':'Ollama','endpoint':'http://127.0.0.1:11434/v1','model':'qwen3:0.6b'})
    assert c.post('/api/productions/1/cast-proposal',json={}).status_code==409


def test_cast_generation_does_not_lock_theatre_writes_and_viewer_cannot_confirm(tmp_path,monkeypatch):
    import asyncio
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    from test_accounts import make,theatre,login
    from backend.production_editor import template
    app,c=make(tmp_path,monkeypatch)
    tid=theatre(c);assert login(c,tid).status_code==200
    person=c.post('/api/resources',json={'kind':'Person','name':'Артист','department':'Артисты',
        'data':{'qualification':['Артисты']}}).json()
    draft=template();draft['name']='Проверка ожидания модели'
    draft['data']['roles']=[{'role':'Роль','A':0,'B':0,'eligible':[person['id']]}]
    p=c.post('/api/productions',json=draft).json()
    assert p.get('id'),p
    c.put('/api/settings/llm',json={'enabled':True,'provider':'Ollama','endpoint':'http://127.0.0.1:11434/v1','model':'qwen3:0.6b'})
    entered,release=threading.Event(),threading.Event()
    async def model(*a,**k):
        entered.set();await asyncio.to_thread(release.wait,10)
        return '{"answer":"Нет предложения","choices":[]}'
    monkeypatch.setattr('backend.model_client.request_model',model)
    with ThreadPoolExecutor() as pool:
        pending=pool.submit(c.post,f"/api/productions/{p['id']}/cast-proposal",json={})
        assert entered.wait(5)
        try:
            start=time.monotonic()
            changed=c.patch(f"/api/productions/{p['id']}",json={'version':p['version'],'name':'Изменено во время ожидания'})
            assert changed.status_code==200,changed.text
            assert time.monotonic()-start<5
        finally:release.set()
        result=pending.result().json()
    assert c.post(f"/api/productions/{p['id']}/cast-proposal/confirm",json={'version':result['version'],
        'choices':[{'key':'role:0:A','people':[person['id']]}]}).status_code==409
    assert c.post('/api/auth/users',json={'name':'Наблюдатель','login':'viewer','password':'test-password','role':'viewer'}).status_code==200
    c.post('/api/auth/logout');assert login(c,tid,'viewer').status_code==200
    assert c.post(f"/api/productions/{p['id']}/cast-proposal",json={}).status_code==200
    assert c.post(f"/api/productions/{p['id']}/cast-proposal/confirm",json={}).status_code==403
