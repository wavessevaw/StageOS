from copy import deepcopy
from datetime import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from backend.app import create_app
from backend.models import make_engine,Task,Booking,Event
from test_core import ctx,confirm

@pytest.fixture
def clean(tmp_path):
    app=create_app(make_engine('sqlite:///'+str(tmp_path/'empty.db')),demo_enabled=False)
    return TestClient(app),app.state.Session

def setup_clean(c):
    assert c.post('/api/theatre',json={'name':'Рабочий театр'}).status_code==200
    v=c.post('/api/venues',json={'name':'Новая площадка','data':{}}).json()
    p=c.post('/api/resources',json={'kind':'Person','name':'Новый артист','department':'Артисты','data':{'qualification':['Артисты']}}).json()
    template=c.get('/api/production-template').json()
    template['name']='Новая постановка';template['data']['home_venue']=v['id']
    template['data']['roles']=[dict(role='Главная роль',A=p['id'],B=p['id'],eligible=[p['id']])]
    response=c.post('/api/productions',json=template);assert response.status_code==200,response.text
    req=dict(production_id=response.json()['id'],venue_id=v['id'],start='2026-12-01T18:00:00')
    return v,p,response.json(),req

def test_empty_first_run_and_no_demo(clean):
    c,S=clean;b=c.get('/api/bootstrap').json()
    assert not b['initialized'] and not b['demo_enabled']
    assert b['productions']==b['resources']==[]
    assert c.post('/api/demo').status_code==404
    assert c.get('/api/demo/scenarios').json()==[]
    v,person,p,r=setup_clean(c)
    assert c.get('/api/bootstrap').json()['initialized']
    plan=c.post('/api/preview',json=r).json();assert plan['status']=='READY'
    ev=confirm(c,r);assert ev.status_code==200,ev.text
    d=c.get('/api/events/'+str(ev.json()['id'])).json()
    assert d['current']['assignments'][0]['actual_id']==person['id']
    assert len(c.get('/api/events').json())==1

@pytest.mark.parametrize('key,value',[('requirements',[]),('pipeline',[]),('duration',True),('roles',None),('scenes',{}),('home_venue',True)])
def test_malformed_passport_is_422(clean,key,value):
    c,S=clean;v,person,p,r=setup_clean(c)
    bad=deepcopy(p);bad['data'][key]=value
    assert c.patch('/api/productions/'+str(p['id']),json=bad).status_code==422

def test_calendar_snapshot_does_not_change_with_passport(ctx):
    c,S,b,rs,r=ctx;ev=confirm(c,r).json();eid=ev['id']
    before=c.get('/api/events/'+str(eid)).json()['current']
    p=deepcopy(b['productions'][0]);p['data']['roles'][0]['B']=p['data']['roles'][0]['A']
    p['data']['duration']=180;p['data']['pipeline']['stage']=80
    assert c.patch('/api/productions/1',json=p).status_code==200
    after=c.get('/api/events/'+str(eid)).json()['current']
    assert after['assignments']==before['assignments']
    assert after['end']==before['end'] and after['tasks']==before['tasks']
    assert after['passport_changed']
    edit=c.post('/api/preview',json=after['request']).json()
    assert edit['end']!=after['end']

def test_close_time_and_scenery_depth_are_conflicts(clean):
    c,S=clean;v,person,p,r=setup_clean(c)
    assert c.patch('/api/venues/'+str(v['id']),json={'name':v['name'],'data':{'closing':18}}).status_code==200
    unit=c.post('/api/inventory/units',json={'name':'Глубокая декорация','kind':'Scenery','quantity':1,'data':{'depth':40}}).json()[0]
    p['data']['items']=[unit['id']]
    assert c.patch('/api/productions/'+str(p['id']),json=p).status_code==200
    plan=c.post('/api/preview',json=r).json()
    assert {'closing','scenery'} <= {x['code'] for x in plan['conflicts']}

def test_cancelled_event_and_actuals_cannot_be_resaved(ctx):
    c,S,b,rs,r=ctx;ev=confirm(c,r).json();eid=ev['id']
    detail=c.get('/api/events/'+str(eid)).json()
    task=detail['tasks'][0]
    assert c.patch('/api/tasks/'+str(task['id'])+'/actual',json={'start':task['start'],'end':task['end']}).status_code==200
    assert confirm(c,detail['current']['request']).status_code==422
    assert c.post('/api/events/'+str(eid)+'/status',json={'status':'Cancelled','version':ev['version']}).status_code==200
    req={**detail['current']['request'],'version':ev['version']+1}
    assert confirm(c,req).status_code==422
    with S() as s:assert not s.scalar(select(Booking.id).where(Booking.event_id==eid))

def test_delete_unrelated_numeric_id_is_not_false_reference(clean):
    c,S=clean;v,person,p,r=setup_clean(c)
    unrelated=c.post('/api/resources',json={'name':'Запасной прибор','kind':'Equipment','department':'Свет','data':{}}).json()
    p['data']['requirements']['power']=unrelated['id']
    assert c.patch('/api/productions/'+str(p['id']),json=p).status_code==200
    assert c.delete('/api/resources/'+str(unrelated['id'])).status_code==200

@pytest.mark.parametrize('endpoint,body',[('/api/blocks',{'start':'2026-12-01T10:00:00+10:00','end':'2026-12-01T12:00:00+10:00','resource_id':1,'label':'Отпуск'}),('/api/inventory/units',{'name':'Прибор','kind':'Equipment','quantity':True}),('/api/venues',{'name':'Зал','data':{'seats':1.5}})])
def test_invalid_catalog_and_timezone_requests(clean,endpoint,body):
    c,S=clean;assert c.post(endpoint,json=body).status_code==422

def test_rehearsal_room_capacity_and_parent_closure(clean):
    c,S=clean;v,person,p,r=setup_clean(c)
    room=c.post('/api/resources',json={'kind':'Room','name':'Малая комната','department':'Площадки','data':{'venue_id':v['id'],'capacity':0}}).json()
    assert c.post('/api/blocks',json={'resource_id':v['id'],'start':'2026-12-01T08:00:00','end':'2026-12-01T23:00:00','label':'Закрытие здания','state':'maintenance'}).status_code==200
    r.update(kind='Репетиция',venue_id=room['id'],rehearsal_people=[person['id']])
    result=c.post('/api/preview',json=r);assert result.status_code==200,result.text
    assert {'room_capacity','maintenance'} <= {x['code'] for x in result.json()['conflicts']}

def test_technical_rehearsal_people_called_for_preparation(clean):
    c,S=clean;v,person,p,r=setup_clean(c)
    tech=c.post('/api/resources',json={'kind':'Person','name':'Звуковой техник','department':'Звук','data':{'qualification':['Звук']}}).json()
    r.update(kind='Репетиция',rehearsal_people=[tech['id']])
    plan=c.post('/api/preview',json=r).json()
    assert plan['assignments'][0]['call']==min(t['start'] for t in plan['tasks'])
