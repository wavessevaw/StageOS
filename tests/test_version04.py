from copy import deepcopy
from test_core import ctx,confirm


def test_rehearsal_selected_people_and_notes(ctx):
    c,S,b,rs,r=ctx
    people=[next(x['id'] for x in b['resources'] if x['kind']=='Person' and x['department']==d) for d in ['Балет','Звук']]
    r.update(kind='Репетиция',rehearsal_people=people,notes='Балетный прогон. Нужен звук.')
    p=c.post('/api/preview',json=r).json()
    assert {a['actual_id'] for a in p['assignments']}==set(people)
    ev=confirm(c,r);assert ev.status_code==200,ev.text
    d=c.get('/api/events/'+str(ev.json()['id'])).json()
    assert d['current']['notes']==r['notes']
    assert {a['department'] for a in d['current']['assignments']}=={'Балет','Звук'}
    r['rehearsal_people']=[];assert c.post('/api/preview',json=r).status_code==422


def test_force_incompatible_event_with_reason(ctx):
    c,S,b,rs,r=ctx
    r.update(production_id=6,venue_id=rs['Камерный зал']['id'],force=True)
    assert confirm(c,r).status_code==422
    r['override_reason']='Демонстрация ручного производственного решения'
    ev=confirm(c,r);assert ev.status_code==200,ev.text
    d=c.get('/api/events/'+str(ev.json()['id'])).json()
    assert d['current']['forced'] is True
    assert d['current']['status']=='CONFLICT'
    assert any(i['severity']=='CRITICAL' for i in d['current']['conflicts'])


def test_venue_creation_edit_materializes_mechanics(ctx):
    c,S,b,rs,r=ctx
    created=c.post('/api/venues',json={'name':'Новая площадка','data':{'seats':650,'fly_bars':5,'soffits':5,'lighting_positions':8}})
    assert created.status_code==200,created.text
    v=created.json();assert v['data']['seats']==650
    r['venue_id']=v['id'];p=c.post('/api/preview',json=r).json()
    checks={x['name']:x for x in p['compatibility']['checks']};assert checks['Штанкеты']['available']==5
    assert c.patch('/api/venues/'+str(v['id']),json={'name':v['name'],'data':{'fly_bars':2}}).status_code==200
    p=c.post('/api/preview',json=r).json();assert next(x for x in p['compatibility']['checks'] if x['name']=='Штанкеты')['available']==2


def test_four_units_are_individual_reserved_resources(ctx):
    c,S,b,rs,r=ctx
    result=c.post('/api/inventory/units',json={'name':'BSW 350','kind':'Equipment','department':'Свет','quantity':4,'data':{'category':'BSW'}})
    assert result.status_code==200,result.text
    ids=[x['id'] for x in result.json()];assert len(set(ids))==4
    p=deepcopy(b['productions'][0]);p['data']['items']=ids
    assert c.patch('/api/productions/'+str(p['id']),json=p).status_code==200
    plan=c.post('/api/preview',json=r).json();assert set(ids)<={x['resource_id'] for x in plan['bookings']}
    assert confirm(c,r).status_code==200
    plan=c.post('/api/preview',json=r).json();assert set(ids)<={x.get('resource_id') for x in plan['conflicts'] if x['code']=='overlap'}
    assert c.post('/api/inventory/units',json={'name':'Ошибка','kind':'Equipment','quantity':0}).status_code==422


def test_new_scenery_is_checked_for_fit(ctx):
    c,S,b,rs,r=ctx
    unit=c.post('/api/inventory/units',json={'name':'Задник','kind':'Scenery','department':'Сцена','quantity':1,'data':{'width':90,'height':40,'depth':1}}).json()[0]
    p=deepcopy(b['productions'][0]);p['data']['items']=[unit['id']]
    assert c.patch('/api/productions/'+str(p['id']),json=p).status_code==200
    plan=c.post('/api/preview',json=r).json();assert any(x['code']=='scenery' and x['resource']==unit['name'] for x in plan['conflicts'])
