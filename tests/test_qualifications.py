from copy import deepcopy
from test_core import ctx


def test_actor_director_requires_explicit_qualification(ctx):
    c,S,b,rs,r=ctx
    production=b['productions'][0]
    data=deepcopy(production['data'])
    actor_id=data['roles'][0]['B']
    actor=next(x for x in b['resources'] if x['id']==actor_id)
    data['responsibles']['Режиссёр']=actor_id
    response=c.patch('/api/productions/'+str(production['id']),json={'version':production['version'],'data':data})
    assert response.status_code==422
    updated=deepcopy(actor['data'])
    updated['qualification']=list(set(updated['qualification']+['Режиссёр']))
    response=c.patch('/api/resources/'+str(actor_id),json={'name':actor['name'],'department':actor['department'],'kind':'Person','data':updated})
    assert response.status_code==200,response.text
    response=c.patch('/api/productions/'+str(production['id']),json={'version':production['version'],'data':data})
    assert response.status_code==200,response.text
    response=c.post('/api/preview',json=r)
    assert response.status_code==200,response.text
    plan=response.json()
    assigned=[a for a in plan['assignments'] if a['actual_id']==actor_id]
    assert {'Артисты','Режиссёр'} <= {a['department'] for a in assigned}
    assert not any(x['code']=='qualification' and x.get('resource')==actor['name'] for x in plan['conflicts'])
    assert not any(x['code']=='multiple_roles' and x['severity'] in ('ERROR','CRITICAL') and x.get('resource')==actor['name'] for x in plan['conflicts'])


def test_qualification_catalog_create_delete_and_protect_used(ctx):
    c,S,b,rs,r=ctx
    rows=c.get('/api/settings/qualifications').json()
    names=[row['name'] for row in rows]
    assert c.put('/api/settings/qualifications',json={'names':names+['Тестовая квалификация']}).status_code==200
    assert 'Тестовая квалификация' in c.get('/api/bootstrap').json()['qualifications']
    assert c.put('/api/settings/qualifications',json={'names':names}).status_code==200
    assert 'Тестовая квалификация' not in c.get('/api/bootstrap').json()['qualifications']
    assert c.put('/api/settings/qualifications',json={'names':[n for n in names if n!='Артисты']}).status_code==409
    assert 'Артисты' in c.get('/api/bootstrap').json()['qualifications']
    assert c.put('/api/settings/qualifications',json={'names':['Повтор','Повтор']}).status_code==422
