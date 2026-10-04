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
    status=r.json();assert status['running'];assert local.get('/api/bootstrap').status_code==200
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


def test_host_configuration_keeps_login_and_running_listener(network):
    host,local,clients,tid,address,code=network
    controller=host.state.network
    token=local.cookies.get('stageos_session')
    thread=controller.thread
    for _ in range(2):
        result=local.post('/api/connection',json={'mode':'server','port':controller.config['port']})
        assert result.status_code==200,result.text
        assert 'set-cookie' not in result.headers
        assert local.cookies.get('stageos_session')==token
        assert local.get('/api/bootstrap').status_code==200
        assert controller.thread is thread
    # A non-Windows runner rejects the platform, not the authenticated session.
    import os
    if os.name!='nt':
        result=local.post('/api/connection/firewall')
        assert result.status_code==422
        assert 'Windows' in result.json()['detail']
    assert local.post('/api/connection',json={'mode':'local'}).status_code==200
    assert local.cookies.get('stageos_session')==token
    assert local.get('/api/bootstrap').status_code==200


def test_entering_and_leaving_remote_mode_clears_session(network):
    host,local,(a,b),tid,address,code=network
    token=a.cookies.get('stageos_session');assert token
    result=a.post('/api/connection',json={'mode':'client','address':address,'code':code})
    assert result.status_code==200
    assert a.cookies.get('stageos_session') is None
    assert a.get('/api/bootstrap').status_code==401
    assert login(a,tid).status_code==200
    assert a.post('/api/connection',json={'mode':'local'}).status_code==200
    assert a.cookies.get('stageos_session') is None
    assert a.get('/api/bootstrap').status_code==401


def test_firewall_waits_for_actual_success(monkeypatch):
    import base64
    import subprocess
    from backend.network import run_firewall_setup
    calls=[]
    def run(args,**kwargs):
        calls.append((args,kwargs))
        return subprocess.CompletedProcess(args,0)
    monkeypatch.setattr(subprocess,'run',run)
    assert run_firewall_setup(8765)['ok']
    args,kwargs=calls[0]
    script=base64.b64decode(args[-1]).decode('utf-16-le')
    assert '-Wait -PassThru' in script and 'exit $p.ExitCode' in script
    assert '-Verb RunAs' in script and '-Port 8765' in script
    assert kwargs['timeout']==120


@pytest.mark.parametrize('failure',['exit','timeout','missing'])
def test_firewall_never_reports_success_on_failure(monkeypatch,failure):
    import subprocess
    from fastapi import HTTPException
    from backend.network import run_firewall_setup
    def run(args,**kwargs):
        if failure=='timeout':raise subprocess.TimeoutExpired(args,120)
        if failure=='missing':raise FileNotFoundError()
        return subprocess.CompletedProcess(args,1)
    monkeypatch.setattr(subprocess,'run',run)
    with pytest.raises(HTTPException) as error:run_firewall_setup(8765)
    assert error.value.status_code==422


def test_live_status_and_http_probe(network):
    host,local,clients,tid,address,code=network
    check=local.get('/api/connection/diagnostics')
    assert check.status_code==200 and check.json()['http_ok'] is True
    state=local.get('/api/connection').json()
    assert state['running'] and state['phase']=='running'
    assert state['remote_requests']>0 and state['last_remote']['address']=='127.0.0.1'
    assert any('сервер отвечает' in row['message'] for row in state['logs'])
    assert code not in str(state['logs'])
    local.post('/api/connection',json={'mode':'local'})
    assert local.get('/api/connection/diagnostics').json()['http_ok'] is False
    state=local.get('/api/connection').json()
    assert not state['running'] and state['phase']=='stopped'


def test_busy_port_has_visible_error(tmp_path,monkeypatch):
    monkeypatch.delenv('STAGEOS_TOKEN',raising=False)
    app=create_desktop_app(tmp_path);c=TestClient(app)
    with socket.socket() as socket_owner:
        socket_owner.bind(('0.0.0.0',0));socket_owner.listen()
        r=c.post('/api/connection',json={'mode':'server','port':socket_owner.getsockname()[1]})
        assert r.status_code==422
    state=c.get('/api/connection').json()
    assert not state['running'] and state['phase']=='error' and state['error']
    assert state['logs'][-1]['level']=='error'


def test_status_remains_responsive_during_start(tmp_path,monkeypatch):
    import asyncio,threading
    monkeypatch.delenv('STAGEOS_TOKEN',raising=False)
    app=create_desktop_app(tmp_path);entered=threading.Event();release=threading.Event()
    def slow_start(port):
        app.state.network.phase='starting';entered.set();assert release.wait(5)
    monkeypatch.setattr(app.state.network,'start_server',slow_start)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
            start=asyncio.create_task(client.post('/api/connection',json={'mode':'server','port':8765}))
            try:
                assert await asyncio.to_thread(entered.wait,3)
                result=await asyncio.wait_for(client.get('/api/connection'),1)
                assert result.json()['phase']=='starting'
            finally:release.set();await start
    asyncio.run(scenario())


def test_windows_scripts_create_and_inspect_real_rule():
    import os,subprocess,sys,ctypes
    from pathlib import Path
    if os.name!='nt':pytest.skip('Requires Windows administrator runner')
    if not ctypes.windll.shell32.IsUserAnAdmin():pytest.skip('Requires administrator privileges')
    from backend.network import inspect_windows_network
    with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    script=Path(__file__).resolve().parents[1]/'backend/firewall.ps1'
    try:
        run=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),'-Port',str(port),'-RuntimePath',sys.executable],capture_output=True,timeout=30)
        assert run.returncode==0,run.stderr
        result=inspect_windows_network(port)
        assert result['firewall']=='allowed'
        assert isinstance(result['profiles'],list)
    finally:
        subprocess.run(['powershell.exe','-NoProfile','-Command',f'Remove-NetFirewallRule -Name StageOS-Server-{port} -ErrorAction SilentlyContinue'],capture_output=True,timeout=30)
