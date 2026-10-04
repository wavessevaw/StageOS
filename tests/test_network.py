"""Real HTTP LAN host + two independent desktop clients, not a mock transport."""
import socket
from concurrent.futures import ThreadPoolExecutor
import pytest
import httpx
from fastapi.testclient import TestClient
from backend.network import create_desktop_app,validate_address
from test_accounts import theatre,login


@pytest.fixture
def network(tmp_path,monkeypatch):
    monkeypatch.delenv('STAGEOS_DATABASE_URL',raising=False)
    monkeypatch.delenv('STAGEOS_TOKEN',raising=False)
    host=create_desktop_app(tmp_path/'host');local=TestClient(host)
    tid=theatre(local);assert login(local,tid).status_code==200
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    r=local.post('/api/connection',json={'mode':'server','port':port});assert r.status_code==200,r.text
    status=r.json();assert status['running'];assert login(local,tid).status_code==200
    address=f'http://127.0.0.1:{port}'
    clients=[]
    for index in range(2):
        app=create_desktop_app(tmp_path/f'client-{index}');c=TestClient(app)
        assert c.post('/api/connection',json={'mode':'client','address':address,'code':status['code']}).status_code==200
        assert login(c,tid).status_code==200
        clients.append(c)
    try:yield host,local,clients,tid,address,status['code']
    finally:
        host.state.network.stop_server();host.state.network.workspace.state.registry.close()
        for c in clients:c.app.state.network.workspace.state.registry.close()

def test_two_clients_share_database_notifications_export_and_restart(network,tmp_path):
    host,local,(a,b),tid,address,code=network
    before=b.get('/api/sync').json()['revision']
    person=a.post('/api/resources',json={'kind':'Person','name':'Общий сотрудник','department':'Артисты','data':{'qualification':['Артисты']}});assert person.status_code==200
    assert b.get('/api/bootstrap').json()['resources'][0]['name']=='Общий сотрудник'
    assert local.get('/api/bootstrap').json()['resources'][0]['id']==person.json()['id']
    assert b.get('/api/sync').json()['revision']>before
    export=b.get('/api/database/export');assert export.status_code==200;assert export.content.startswith(b'SQLite format 3')
    assert a.post('/api/database/import',content=export.content).status_code==200
    assert b.get('/api/bootstrap').json()['resources'][0]['name']=='Общий сотрудник'
    for fmt,magic in [('pdf',b'%PDF-'),('png',b'\x89PNG')]:
        report=b.get('/api/schedule/export',params={'start':'2026-12-01','end':'2026-12-01','format':fmt})
        assert report.status_code==200 and report.content.startswith(magic)
    assert a.post('/api/auth/logout').status_code==200
    assert a.get('/api/bootstrap').status_code==401
    assert b.get('/api/bootstrap').status_code==200
    # Client database remains empty: no copied production data.
    app=create_desktop_app(tmp_path/'client-0');c=TestClient(app)
    assert c.get('/api/connection').json()['mode']=='client'
    assert login(c,tid).status_code==200
    assert len(c.get('/api/bootstrap').json()['resources'])==1
    for folder in ['client-0','client-1']:
        assert not list((tmp_path/folder/'theatres').glob('*'))

def test_code_origin_roles_and_host_control(network):
    host,local,(a,b),tid,address,code=network
    assert httpx.get(address+'/api/bootstrap',trust_env=False).status_code==403
    assert httpx.get(address+'/api/auth/theatres',trust_env=False,headers={'X-StageOS-Code':'wrong-code'}).status_code==403
    assert httpx.get(address+'/api/auth/theatres',trust_env=False,headers={'X-StageOS-Code':code}).status_code==200
    assert httpx.post(address+'/api/auth/theatres',trust_env=False,headers={'X-StageOS-Code':code},json={}).status_code==403
    assert httpx.get(address+'/api/auth/theatres',trust_env=False,headers={'X-StageOS-Code':code,'Origin':'https://evil.example'}).status_code==403
    assert a.post('/api/auth/users',json={'name':'Наблюдатель','login':'viewer','password':'test-password','role':'viewer'}).status_code==200
    a.post('/api/auth/logout');assert login(a,tid,'viewer').status_code==200
    assert a.get('/api/bootstrap').status_code==200
    assert a.post('/api/resources',json={}).status_code==403
    assert a.get('/api/database/export').status_code==403
    local.post('/api/auth/logout');login(local,tid,'viewer')
    assert local.post('/api/connection',json={'mode':'local'}).status_code==403
    assert host.state.network.status()['running']

def test_simultaneous_event_commit_and_stale_change(network):
    host,local,(a,b),tid,address,code=network
    v=a.post('/api/venues',json={'name':'Общая площадка','data':{}}).json()
    person=a.post('/api/resources',json={'kind':'Person','name':'Общий артист','department':'Артисты','data':{'qualification':['Артисты']}}).json()
    draft=a.get('/api/production-template').json();draft['name']='Общий спектакль';draft['data']['home_venue']=v['id']
    draft['data']['roles']=[dict(role='Роль',A=person['id'],B=person['id'],eligible=[person['id']])]
    prod=a.post('/api/productions',json=draft).json()
    req=dict(production_id=prod['id'],venue_id=v['id'],start='2026-12-01T18:00:00')
    preview=a.post('/api/preview',json=req).json();assert preview['status']=='READY'
    body={'request':req,'fingerprint':preview['fingerprint']}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda c:c.post('/api/events',json=body),[a,b]))
    assert sorted(r.status_code for r in results)==[200,409]
    events=b.get('/api/events').json();assert len(events)==1
    eid=events[0]['id'];detail=a.get('/api/events/'+str(eid)).json()
    version=detail['version']
    result=a.post(f'/api/events/{eid}/status',json={'status':'Cancelled','version':version});assert result.status_code==200,result.text
    assert b.post(f'/api/events/{eid}/status',json={'status':'Cancelled','version':version}).status_code==409
    assert b.get('/api/events/'+str(eid)).json()['status']=='Cancelled'

def test_server_loss_and_bad_connection_do_not_copy_or_write(network):
    host,local,(a,b),tid,address,code=network
    saved=a.get('/api/connection').json()
    assert a.post('/api/connection',json={'mode':'client','address':address,'code':'incorrect-code'}).status_code==422
    assert a.post('/api/connection',json={'mode':'client','address':address,'code':'неверный-код'}).status_code==422
    assert a.get('/api/connection').json()['address']==saved['address']
    host.state.network.stop_server()
    assert a.get('/api/bootstrap').status_code==503
    assert a.post('/api/resources',json={'kind':'Person','name':'Не сохранён'}).status_code==503
    assert local.get('/api/bootstrap').json()['resources']==[]
    assert a.post('/api/connection',json={'mode':'local'}).status_code==200
    assert a.get('/api/auth/theatres').json()['theatres']==[]
    # The native Server launcher also creates its own code when changing roles.
    native=a.app.state.network
    try:
        native.start_server(int(address.rsplit(':',1)[1]))
        assert native.config['code']!=code
        assert native.status()['running']
    finally:native.stop_server()

@pytest.mark.parametrize('address',['ftp://host','http://user:pass@host','http://host/path','http://host:bad','http://host?token=abc'])
def test_bad_address(address):
    with pytest.raises(ValueError):validate_address(address)


def test_invalid_connection_configuration_and_origin(tmp_path,monkeypatch):
    monkeypatch.delenv('STAGEOS_TOKEN',raising=False)
    app=create_desktop_app(tmp_path);c=TestClient(app)
    for body in [None,[],{}, {'mode':'server','port':True},{'mode':'server','port':22},{'mode':'client','address':'http://host/path','code':'test-code'}]:
        assert c.post('/api/connection',json=body).status_code==422
    assert c.post('/api/connection',content=b'broken',headers={'content-type':'application/json'}).status_code==422
    assert c.post('/api/connection',headers={'Origin':'https://evil.example'},json={'mode':'local'}).status_code==403
    assert c.get('/api/connection').json()['mode']=='local'


def test_registry_close_releases_database_and_sessions(tmp_path,monkeypatch):
    monkeypatch.delenv('STAGEOS_TOKEN',raising=False)
    monkeypatch.delenv('STAGEOS_DATABASE_URL',raising=False)
    app=create_desktop_app(tmp_path);c=TestClient(app);tid=theatre(c);login(c,tid)
    registry=app.state.network.workspace.state.registry
    path=registry.theatre(tid)['path']
    registry.close()
    assert not registry.apps and not registry.sessions
    from pathlib import Path
    Path(path).unlink()
    assert not Path(path).exists()
