from contextlib import closing
import json,sqlite3
from sqlalchemy import select
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.models import make_engine,Resource,Production,Event,Task,Booking,Audit,Setting
from test_release import clean,setup_clean
from test_core import confirm


def test_complete_working_database_roundtrip_restart_and_continue(clean,tmp_path,monkeypatch):
    c,S=clean;venue,person,p,req=setup_clean(c)
    technician=c.post('/api/resources',json={'kind':'Person','name':'Звук второго состава','department':'Звук','data':{'qualification':['Звук']}}).json()
    items=c.post('/api/inventory/units',json={'name':'Прибор','kind':'Equipment','department':'Свет','quantity':4,'data':{'category':'BSW'}}).json()
    scenery=c.post('/api/inventory/units',json={'name':'Задник','kind':'Scenery','department':'Сцена','quantity':1,'data':{'width':2,'height':2,'depth':1}}).json()
    p['data']['items']=[r['id'] for r in items+scenery]
    p['data']['crew_casts']={'Звук':{'A':[],'B':[technician['id']]}}
    response=c.patch(f"/api/productions/{p['id']}",json=p);assert response.status_code==200,response.text
    req.update(cast='B',notes='Проверить вызовы и декорацию')
    response=confirm(c,req);assert response.status_code==200,response.text
    eid=response.json()['id'];detail=c.get(f'/api/events/{eid}').json();task=next(t for t in detail['tasks'] if t['end']>t['start'])
    assert c.patch(f"/api/tasks/{task['id']}/actual",json={'start':task['start'],'end':task['end']}).status_code==200
    assert c.put('/api/settings/interface',json={'language':'en'}).status_code==200
    # Include an incomplete passport in the same real working database.
    draft=c.get('/api/production-template').json();draft['name']='Позже дополним'
    assert c.post('/api/productions',json=draft).status_code==200
    expected_boot=c.get('/api/bootstrap').json();expected_detail=c.get(f'/api/events/{eid}').json()
    with S() as s:
        def rows(model):
            from backend.engine import serial
            return sorted([serial(row) for row in s.scalars(select(model))],key=lambda row:str(row.get('id',row.get('key'))))
        expected={model.__tablename__:rows(model) for model in [Resource,Production,Event,Task,Booking,Audit,Setting]}
    backup=c.get('/api/database/export');assert backup.status_code==200
    assert backup.content.startswith(b'SQLite format 3\x00')
    response=c.post('/api/database/import',content=backup.content);assert response.status_code==200,response.text
    assert c.get('/api/bootstrap').json()==expected_boot
    assert c.get(f'/api/events/{eid}').json()==expected_detail
    with S() as s:
        for model in [Resource,Production,Event,Task,Booking,Audit,Setting]:assert rows(model)==expected[model.__tablename__]
        reopened_path=s.bind.url.database
    monkeypatch.setenv('STAGEOS_HOME',str(__import__('pathlib').Path(reopened_path).parent))
    monkeypatch.delenv('STAGEOS_DATABASE_URL',raising=False)
    restarted=TestClient(create_app(demo_enabled=False))
    assert restarted.get('/api/bootstrap').json()==expected_boot
    assert restarted.get(f'/api/events/{eid}').json()==expected_detail
    # Reopening must allow subsequent transactions, not only read the restored rows.
    assert restarted.post('/api/resources',json={'kind':'Person','name':'После восстановления','department':'Грим','data':{'qualification':['Грим']}}).status_code==200
    assert len(restarted.get('/api/bootstrap').json()['resources'])==len(expected_boot['resources'])+1


def test_failed_import_never_switches_active_database_or_leaves_files(clean,tmp_path):
    c,S=clean;_,_,p,req=setup_clean(c);confirm(c,req)
    before=c.get('/api/bootstrap').json();events=c.get('/api/events').json()
    with S() as s:directory=__import__('pathlib').Path(s.bind.url.database).parent
    # Invalid file, truncated SQLite and a valid SQLite with corrupt settings all fail atomically.
    backup=c.get('/api/database/export').content
    for content in [b'not sqlite',backup[:100]]:
        response=c.post('/api/database/import',content=content);assert response.status_code==422,response.text
        assert c.get('/api/bootstrap').json()==before
        assert c.get('/api/events').json()==events
        assert not (directory/'database-choice.json').exists()
    path=tmp_path/'corrupt-setting.db';path.write_bytes(backup)
    with closing(sqlite3.connect(path)) as db:db.execute("INSERT INTO settings(key,value) VALUES (?,?)",('interface',json.dumps({'language':'unsupported'})));db.commit()
    assert c.post('/api/database/import',content=path.read_bytes()).status_code==422
    assert c.get('/api/bootstrap').json()==before
    assert not list(directory.glob('imported-*.db'))
