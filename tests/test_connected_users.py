import time
from test_network import network  # noqa: F401
from test_accounts import login,theatre


def test_active_remote_users_group_sessions_and_remove_logout(network):
    host,local,(a,b),tid,address,code=network
    assert a.get('/api/bootstrap').status_code==200
    assert b.get('/api/bootstrap').status_code==200
    stats=local.get('/api/connection').json()['users']
    assert stats['online']==1 and stats['sessions']==2
    assert stats['items'][0]['name']=='Администратор'
    assert stats['items'][0]['login']=='админ'
    assert set(stats['items'][0])=={'id','name','login','role','sessions','last_seen'}
    a.post('/api/auth/logout')
    assert local.get('/api/connection').json()['users']['sessions']==1
    b.post('/api/auth/logout')
    assert local.get('/api/connection').json()['users']['items']==[]
    assert login(b,tid).status_code==200
    b.get('/api/bootstrap')
    assert local.get('/api/connection').json()['users']['online']==1
    for key in host.state.network.user_activity:host.state.network.workspace.state.registry.sessions[key]['expires']=time.time()-1
    assert local.get('/api/connection').json()['users']['online']==0


def test_inactive_and_other_theatre_sessions_are_not_shown(network):
    host,local,(a,b),tid,address,code=network
    a.get('/api/bootstrap')
    assert local.get('/api/connection').json()['users']['online']==1
    for row in host.state.network.user_activity.values():row['seen']=time.time()-91
    assert local.get('/api/connection').json()['users']['online']==0
    other=theatre(local,'Другой театр','other-admin')
    assert login(a,other,'other-admin').status_code==200
    a.get('/api/bootstrap')
    assert local.get('/api/connection').json()['users']['online']==0
    assert login(local,other,'other-admin').status_code==200
    assert local.get('/api/connection').json()['users']['items'][0]['login']=='other-admin'


def test_user_statistics_are_local_admin_only(network):
    host,local,(a,b),tid,address,code=network
    a.get('/api/bootstrap')
    local.post('/api/auth/users',json={'name':'Наблюдатель','login':'viewer','password':'test-password','role':'viewer'})
    local.post('/api/auth/logout')
    assert 'users' not in local.get('/api/connection').json()
    assert login(local,tid,'viewer').status_code==200
    assert 'users' not in local.get('/api/connection').json()
    # A remote administrator cannot fetch the host's connection-management data.
    assert 'users' not in a.get('/api/connection').json()
