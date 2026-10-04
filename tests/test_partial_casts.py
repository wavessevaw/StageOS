from copy import deepcopy
from test_release import clean, setup_clean
from test_core import confirm


def test_save_name_only_and_add_role_incrementally(clean):
    c,_=clean
    p=c.get('/api/production-template').json();p['name']='Работа над постановкой'
    response=c.post('/api/productions',json=p)
    assert response.status_code==200,response.text
    p=response.json();pid=p['id']
    p['data']['roles']=[dict(role='Главная роль',A=0,B=0,eligible=[])]
    response=c.patch(f'/api/productions/{pid}',json=p);assert response.status_code==200,response.text
    p=response.json()
    venue=c.post('/api/venues',json={'name':'Зал','data':{}}).json()
    req=dict(production_id=pid,venue_id=venue['id'],start='2026-12-01T18:00:00')
    preview=c.post('/api/preview',json=req)
    assert preview.status_code==200,preview.text
    assert any(x['code']=='unassigned' for x in preview.json()['conflicts'])
    assert confirm(c,req).status_code==422
    artist=c.post('/api/resources',json={'name':'Артист','kind':'Person','department':'Артисты','data':{'qualification':['Артисты']}}).json()
    p['data']['roles'][0].update(A=artist['id'],eligible=[artist['id']])
    assert c.patch(f'/api/productions/{pid}',json=p).status_code==200
    assert confirm(c,req).status_code==200
    # The empty second cast still produces a specific conflict, never silently borrows A.
    other=c.post('/api/preview',json={**req,'cast':'B','start':'2026-12-02T18:00:00'})
    assert any(x['code']=='unassigned' for x in other.json()['conflicts'])


def test_optional_does_not_allow_bad_resource_references(clean):
    c,_=clean
    p=c.get('/api/production-template').json();p['name']='Черновик'
    for value in [True,-1,99999999]:
        bad=deepcopy(p);bad['data']['home_venue']=value
        assert c.post('/api/productions',json=bad).status_code==422
    bad=deepcopy(p);bad['data']['roles']=[dict(role='Роль',A=9999999,B=0,eligible=[])]
    assert c.post('/api/productions',json=bad).status_code==422


def test_department_casts_drive_assignments_and_snapshot(clean):
    c,_=clean
    v,artist,p,req=setup_clean(c)
    choir=[]
    for name in ['Первый певец','Второй певец']:
        choir.append(c.post('/api/resources',json={'name':name,'kind':'Person','department':'Хор','data':{'qualification':['Хор'],'specialization':'Тенор'}}).json()['id'])
    p['data']['groups']['Хор']=[]
    p['data']['groups_casts']={'Хор':{'A':[choir[0]],'B':[choir[1]]}}
    response=c.patch(f"/api/productions/{p['id']}",json=p);assert response.status_code==200,response.text
    p=response.json()
    pa=c.post('/api/preview',json=req).json()
    pb=c.post('/api/preview',json={**req,'cast':'B'}).json()
    assert {a['actual_id'] for a in pa['assignments']}=={artist['id'],choir[0]}
    assert {a['actual_id'] for a in pb['assignments']}=={artist['id'],choir[1]}
    event=confirm(c,{**req,'cast':'B'}).json()
    p['data']['groups_casts']['Хор']['B']=[]
    assert c.patch(f"/api/productions/{p['id']}",json=p).status_code==200
    saved=c.get(f"/api/events/{event['id']}").json()['current']
    assert choir[1] in {a['actual_id'] for a in saved['assignments']}
    new=c.post('/api/preview',json={**req,'cast':'B','start':'2026-12-03T18:00:00'}).json()
    assert choir[1] not in {a['actual_id'] for a in new['assignments']}
    assert c.delete(f'/api/resources/{choir[0]}').status_code in (409,422)


def test_cast_qualification_and_duplicates_still_rejected(clean):
    c,_=clean
    _,artist,p,_=setup_clean(c)
    p['data']['crew_casts']={'Звук':{'A':[artist['id']],'B':[]}}
    assert c.patch(f"/api/productions/{p['id']}",json=p).status_code==422
    p['data']['crew_casts']={'Артисты':{'A':[artist['id'],artist['id']],'B':[]}}
    assert c.patch(f"/api/productions/{p['id']}",json=p).status_code==422
