from copy import deepcopy
from datetime import datetime
from test_core import ctx, confirm


def test_edit_departure_and_rehearsal_day(ctx):
    c,S,b,rs,r=ctx
    r.update(run_through=True,task_overrides={'Выезд':{'start':'2026-10-16T08:00:00'},'Монтаж сцены':{'duration':90},'Световой монтаж':{'duration':90},'Звуковой монтаж':{'duration':60},'Видеомонтаж':{'duration':30},'Technical Check':{'duration':15}})
    result=c.post('/api/preview',json=r); assert result.status_code==200,result.text
    p=result.json(); tasks={t['name']:t for t in p['tasks']}
    assert tasks['Выезд']['start']=='2026-10-16T08:00:00'
    assert tasks['Прогон']['start']=='2026-10-16T11:00:00'
    assert tasks['Погрузка']['end']<=tasks['Выезд']['start']
    assert tasks['Technical Check']['end']<=tasks['Прогон']['start']
    assert tasks['Обед']['start']=='2026-10-16T14:00:00'
    assert tasks['Демонтаж']['start']=='2026-10-16T21:45:00'
    assert tasks['Погрузка']['end']==tasks['Выезд']['start']
    assert tasks['Прогон']['end']<=tasks['Обед']['start']
    assert tasks['Обед']['end']<=tasks['Сбор перед спектаклем']['start']
    assert tasks['Сбор перед спектаклем']['end']<=r['start']
    assert tasks['Спектакль']['start']==r['start']
    artist=next(a for a in p['assignments'] if a['department']=='Артисты')
    assert artist['call']<tasks['Прогон']['start']
    ev=confirm(c,r); assert ev.status_code==200,ev.text
    saved=c.get('/api/events/'+str(ev.json()['id'])).json()
    assert saved['current']['request']['task_overrides']==p['request']['task_overrides']


def test_impossible_manual_times_rejected(ctx):
    c,S,b,rs,r=ctx
    r['task_overrides']={'Выезд':{'start':'2026-10-16T18:55:00'},'Погрузка':{'start':'2026-10-16T18:50:00','duration':60}}
    assert c.post('/api/preview',json=r).status_code==422


def test_replace_actor_in_existing_event(ctx):
    c,S,b,rs,r=ctx
    ev=confirm(c,r).json(); detail=c.get('/api/events/'+str(ev['id'])).json(); req=detail['current']['request']
    assignment=next(a for a in detail['current']['assignments'] if a['department']=='Артисты')
    original=assignment['actual_id']; replacement=next(i for i in assignment['eligible_ids'] if i!=original)
    req['replacements']={str(assignment['responsible_id']):replacement}
    assert confirm(c,req).status_code==200
    person=c.get(f'/api/resources/{replacement}/statistics').json();assert person['replacements']>=1
    assert person['hours']>0


def test_reject_proposal_does_not_change_event(ctx):
    c,S,b,rs,r=ctx
    count=len(c.get('/api/events').json()); proposal=c.post('/api/proposals',json=r).json()
    reject=c.post(f"/api/proposals/{proposal['id']}/reject",json={'reason':'Не согласован состав'})
    assert reject.status_code==200 and reject.json()['data']['state']=='Rejected'
    assert c.post(f"/api/proposals/{proposal['id']}/approve").status_code==422
    assert len(c.get('/api/events').json())==count


def test_create_edit_full_passport(ctx):
    c,S,b,rs,r=ctx
    body=deepcopy(b['productions'][0]);body['name']='Новая премьера';body.pop('id')
    created=c.post('/api/productions',json=body);assert created.status_code==200,created.text
    p=created.json();p['data']['pipeline']['load']=45;p['data']['genre']='Оперетта'
    edited=c.patch('/api/productions/'+str(p['id']),json=p);assert edited.status_code==200,edited.text
    assert edited.json()['data']['pipeline']['load']==45
    r['production_id']=p['id'];assert c.post('/api/preview',json=r).status_code==200
    p['version']=edited.json()['version'];p['data']['roles'][0]['A']=999999
    assert c.patch('/api/productions/'+str(p['id']),json=p).status_code==422
