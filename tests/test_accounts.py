import json,sqlite3
from fastapi.testclient import TestClient
from backend.workspaces import create_workspace_app,password_hash, password_matches
from backend.app import create_app
from backend.models import make_engine,Setting,Resource


def make(tmp_path,monkeypatch):
    monkeypatch.delenv('STAGEOS_DATABASE_URL',raising=False);monkeypatch.delenv('STAGEOS_TOKEN',raising=False)
    app=create_workspace_app(tmp_path);return app,TestClient(app)

def theatre(c,name='Первый театр',login='Админ'):
    r=c.post('/api/auth/theatres',json={'theatre_name':name,'name':'Администратор','login':login,'password':'test-password'});assert r.status_code==200,r.text;return r.json()['id']

def login(c,tid,user='Админ',password='test-password'):
    return c.post('/api/auth/login',json={'theatre_id':tid,'login':user,'password':password})

def test_gate_isolation_logout_restart(tmp_path,monkeypatch):
    app,c=make(tmp_path,monkeypatch)
    assert c.get('/api/bootstrap').status_code==401
    assert c.get('/api/resources').status_code==401
    assert c.get('/api/database/export').status_code==401
    assert c.post('/api/resources',json={}).status_code==401
    one=theatre(c);two=theatre(c,'Другой театр')
    assert login(c,one,password='wrong').status_code==401
    assert login(c,one,'  АДМИН ').status_code==200
    assert 'HttpOnly' in login(c,one).headers['set-cookie']
    resource=c.post('/api/resources',json={'kind':'Person','name':'Человек первого театра','department':'Артисты','data':{'qualification':['Артисты']}});assert resource.status_code==200
    assert len(c.get('/api/bootstrap').json()['resources'])==1
    c.post('/api/auth/logout');assert c.get('/api/bootstrap').status_code==401
    assert login(c,two).status_code==200
    assert c.get('/api/bootstrap').json()['resources']==[]
    c.post('/api/auth/logout');assert login(c,one).status_code==200
    assert c.get('/api/bootstrap').json()['resources'][0]['name']=='Человек первого театра'
    reboot=TestClient(create_workspace_app(tmp_path));reboot.cookies.update(c.cookies)
    assert reboot.get('/api/bootstrap').status_code==401
    assert login(reboot,one).status_code==200
    assert len(reboot.get('/api/bootstrap').json()['resources'])==1


def test_roles_enforced_cross_theatre_users_and_last_admin(tmp_path,monkeypatch):
    app,c=make(tmp_path,monkeypatch);one=theatre(c);two=theatre(c,'Второй')
    login(c,one)
    for role in ['viewer','editor']:
        assert c.post('/api/auth/users',json={'name':role,'login':role,'password':'test-password','role':role}).status_code==200
    users=c.get('/api/auth/users').json();admin=next(x for x in users if x['role']=='admin');editor=next(x for x in users if x['role']=='editor')
    assert all('password' not in x for x in users)
    assert c.patch('/api/auth/users/'+admin['id'],json={'active':False}).status_code==409
    assert c.patch('/api/auth/users/'+admin['id'],json={'role':'viewer'}).status_code==409
    assert c.post('/api/auth/theatres/'+one+'/setup',json={'name':'Bad','login':'bad','password':'test-password'}).status_code==409
    c.post('/api/auth/logout');login(c,one,'viewer')
    assert c.get('/api/bootstrap').status_code==200
    for endpoint in ['/api/resources','/api/venues','/api/productions','/api/events','/api/proposals']:
        assert c.post(endpoint,json={}).status_code==403
    assert c.get('/api/auth/users').status_code==403
    assert c.get('/api/database/export').status_code==403
    assert c.put('/api/settings/llm',json={}).status_code==403
    c.post('/api/auth/logout');login(c,one,'editor')
    assert c.post('/api/venues',json={'name':'Создана планировщиком','data':{}}).status_code==200
    assert c.post('/api/proposals/1/approve',json={}).status_code==403
    assert c.post('/api/events',json={'request':{'force':True}}).status_code==403
    assert c.post('/api/database/import',content=b'invalid').status_code==403
    c.post('/api/auth/logout');login(c,two)
    assert c.patch('/api/auth/users/'+editor['id'],json={'role':'admin'}).status_code==404


def test_passwords_disabled_users_and_login_throttling(tmp_path,monkeypatch):
    app,c=make(tmp_path,monkeypatch);tid=theatre(c);login(c,tid)
    assert c.post('/api/auth/password',json={'current_password':'wrong','password':'changed-password'}).status_code==403
    assert c.post('/api/auth/password',json={'current_password':'test-password','password':'changed-password'}).status_code==200
    assert c.get('/api/bootstrap').status_code==401
    assert login(c,tid,password='test-password').status_code==401
    assert login(c,tid,password='changed-password').status_code==200
    assert c.post('/api/auth/users',json={'name':'Second','login':'second','password':'test-password','role':'admin'}).status_code==200
    second=next(x for x in c.get('/api/auth/users').json() if x['login']=='second')
    assert c.patch('/api/auth/users/'+second['id'],json={'active':False}).status_code==200
    c.post('/api/auth/logout');assert login(c,tid,'second').status_code==401
    for _ in range(4):assert login(c,tid,'unknown').status_code==401
    assert login(c,tid,'unknown').status_code==401
    assert login(c,tid,'unknown').status_code==429
    raw=(tmp_path/'accounts.sqlite').read_bytes();assert b'test-password' not in raw and b'changed-password' not in raw


def test_adopt_existing_database_private_admin_profile(tmp_path,monkeypatch):
    monkeypatch.delenv('STAGEOS_DATABASE_URL',raising=False);monkeypatch.delenv('STAGEOS_TOKEN',raising=False)
    old=create_app(make_engine('sqlite:///'+str(tmp_path/'stageos.db')),demo_enabled=False)
    with old.state.Session.begin() as s:
        s.add(Setting(key='theatre',value={'name':'Существующий театр'}));s.add(Resource(kind='Person',name='Существующий человек',department='Артисты',data={'qualification':['Артисты']}))
    # Test credentials only. Real account material is provisioned outside the public repository.
    names=['Первый администратор','Второй администратор','Третий администратор']
    profile=tmp_path/'bootstrap-accounts.json';profile.write_text(json.dumps({'users':[{'name':n,'login':n,'password_hash':password_hash('private-test'),'role':'admin'} for n in names]}))
    app=create_workspace_app(tmp_path);c=TestClient(app);tid=c.get('/api/auth/theatres').json()['theatres'][0]['id']
    assert len(c.get('/api/auth/theatres').json()['theatres'])==1
    for name in names:
        assert login(c,tid,name,'private-test').status_code==200
        assert len(c.get('/api/auth/users').json())==3
        assert c.get('/api/bootstrap').json()['resources'][0]['name']=='Существующий человек'
        c.post('/api/auth/logout')
    reboot=TestClient(create_workspace_app(tmp_path));assert login(reboot,tid,names[0],'private-test').status_code==200
    assert len(reboot.get('/api/auth/users').json())==3


def test_import_updates_only_own_workspace_and_survives_restart(tmp_path,monkeypatch):
    app,c=make(tmp_path,monkeypatch);one=theatre(c);two=theatre(c,'Другая среда');login(c,one)
    c.post('/api/resources',json={'kind':'Person','name':'До экспорта','department':'Артисты','data':{'qualification':['Артисты']}})
    exported=c.get('/api/database/export').content
    assert c.post('/api/database/import',content=exported).status_code==200
    c.post('/api/resources',json={'kind':'Person','name':'После импорта','department':'Артисты','data':{'qualification':['Артисты']}})
    c.post('/api/auth/logout');login(c,two);assert c.get('/api/bootstrap').json()['resources']==[]
    reboot=TestClient(create_workspace_app(tmp_path));assert login(reboot,one).status_code==200
    assert len(reboot.get('/api/bootstrap').json()['resources'])==2


def test_origin_token_and_no_account_escalation(tmp_path,monkeypatch):
    app,c=make(tmp_path,monkeypatch);tid=theatre(c);login(c,tid)
    assert c.post('/api/auth/users',headers={'origin':'https://evil.example'},json={}).status_code==403
    assert c.post('/api/auth/login',headers={'origin':'https://evil.example'},json={}).status_code==403
    monkeypatch.setenv('STAGEOS_TOKEN','desktop-test-token')
    assert c.get('/api/auth/theatres').status_code==401
    assert c.get('/api/auth/theatres',headers={'x-stageos-token':'desktop-test-token'}).status_code==200
    assert password_matches('test-password',password_hash('test-password'))
    assert not password_matches('bad','broken-hash')


def test_malformed_account_changes_rejected(tmp_path,monkeypatch):
    app,c=make(tmp_path,monkeypatch);tid=theatre(c);login(c,tid)
    uid=c.get('/api/auth/users').json()[0]['id']
    for body in [None,[],{'role':[]},{'active':1},{'password':None},{'extra':True}]:
        assert c.patch('/api/auth/users/'+uid,content=json.dumps(body),headers={'content-type':'application/json'}).status_code==422
    assert c.post('/api/auth/password',json=[]).status_code==422
    assert c.patch('/api/auth/users/'+uid,content=b'broken',headers={'content-type':'application/json'}).status_code==422
    assert c.get('/api/auth/session').status_code==200
