from fastapi.testclient import TestClient
from backend.access_log import rows,Worker,export
from backend.workspaces import create_workspace_app
from test_accounts import make,theatre,login

def test_history_survives_restart_and_snapshots_account_name(tmp_path,monkeypatch):
    app,c=make(tmp_path,monkeypatch);tid=theatre(c);login(c,tid);c.post('/api/auth/logout')
    phone=TestClient(app);phone.post('/api/mobile/login',json={'login':'Админ','password':'test-password'});phone.post('/api/mobile/logout')
    registry=app.state.registry;history=rows(registry,tid)
    assert len(history)==4 and sum(r['action']=='Вход в аккаунт' for r in history)==2
    assert history[0]['client']=='Мобильный браузер'
    with registry.db() as db:db.execute("UPDATE users SET name='Другое имя'")
    reboot=create_workspace_app(tmp_path);assert rows(reboot.state.registry,tid)[0]['name']=='Администратор'
    assert not rows(registry,'other-theatre')
    assert all('password' not in r and 'session' not in r for r in history)

def test_seven_hour_export_clock_and_csv_near_program(tmp_path,monkeypatch):
    app,c=make(tmp_path/'database',monkeypatch);tid=theatre(c);login(c,tid)
    monkeypatch.setenv('STAGEOS_INSTALL_DIR',str(tmp_path/'program'))
    worker=Worker(app.state.registry)
    assert not worker.tick(1000)
    assert not worker.tick(1000+7*3600-1)
    assert worker.tick(1000+7*3600)
    files=list((tmp_path/'program'/'StageOS-Logs').glob('*.csv'));assert len(files)==1
    text=files[0].read_text(encoding='utf-8-sig');assert 'Администратор' in text and 'test-password' not in text
    restarted=Worker(app.state.registry);assert not restarted.tick(1000+7*3600+60)
