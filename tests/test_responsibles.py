from copy import deepcopy
from sqlalchemy import select
from backend.models import Resource,Event
from backend.production_editor import referenced_ids
from test_core import ctx,confirm  # noqa: F401

def test_multiple_responsibles_are_all_called_and_booked(ctx):
    c,S,b,resources,request=ctx
    production=deepcopy(b['productions'][0]);first=production['data']['responsibles']['Звук']
    other=c.post('/api/resources',json={'kind':'Person','name':'Второй звукорежиссёр','department':'Звук','data':{'qualification':['Звук']}}).json()['id']
    production['data']['responsibles']['Звук']=[first,other]
    assert c.patch('/api/productions/'+str(production['id']),json=production).status_code==200
    plan=c.post('/api/preview',json=request).json()
    assert {a['actual_id'] for a in plan['assignments'] if a['role']=='Звук'}=={first,other}
    assert {first,other}<=referenced_ids(production['data'])
    assert {first,other}<={bk['resource_id'] for bk in plan['bookings']}
    production['version']+=1
    wrong=c.post('/api/resources',json={'kind':'Person','name':'Без допуска','department':'Артисты','data':{'qualification':['Артисты']}}).json()['id']
    production['data']['responsibles']['Звук']=[first,wrong]
    assert c.patch('/api/productions/'+str(production['id']),json=production).status_code==422

def test_general_call_all_artistic_groups_without_technical_people(ctx):
    c,S,b,resources,request=ctx;ids=[]
    for dept in ['Артисты','Балет','Хор','Оркестр']:
        ids.append(c.post('/api/resources',json={'kind':'Person','name':'Общий вызов '+dept,'department':dept,'data':{'qualification':[dept]}}).json()['id'])
    for kind in ['Спектакль','Репетиция']:
        result=c.post('/api/preview',json={**request,'kind':kind,'additional_people':ids}).json()
        assert set(ids)<={a['actual_id'] for a in result['assignments']}
        assert set(ids)<={bk['resource_id'] for bk in result['bookings']}
    tech=c.post('/api/resources',json={'kind':'Person','name':'Только свет','department':'Свет','data':{'qualification':['Свет']}}).json()['id']
    assert c.post('/api/preview',json={**request,'additional_people':[tech]}).status_code==422


def test_rehearsal_calls_sound_responsible_and_respects_explicit_selection(ctx):
    c,S,b,resources,request=ctx
    sound=b['productions'][0]['data']['responsibles']['Звук']
    rehearsal={**request,'kind':'Репетиция'}
    plan=c.post('/api/preview',json=rehearsal).json()
    assert sound in {a['actual_id'] for a in plan['assignments']}
    assert sound in {bk['resource_id'] for bk in plan['bookings']}
    actor=next(a['actual_id'] for a in plan['assignments'] if a['department']=='Артисты')
    selected=c.post('/api/preview',json={**rehearsal,'rehearsal_people':[actor]}).json()
    assert sound not in {a['actual_id'] for a in selected['assignments']}
