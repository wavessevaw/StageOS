"""Release gate: malformed inputs, chronology, persistence, and concurrent writers."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import pytest
from sqlalchemy import select, func
from backend.models import Event, Booking, Task
from test_release import clean, setup_clean
from test_core import confirm

@pytest.mark.parametrize('data',[{'travel':0.5},{'width':'large'},{'transport_width':-1},{'movement':'yes'}])
def test_bad_resource_data_never_enters_database(clean,data):
    c,S=clean;v,person,p,r=setup_clean(c)
    body={'kind':'Scenery','name':'Декорация','department':'Сцена','data':data}
    assert c.post('/api/resources',json=body).status_code==422

@pytest.mark.parametrize('data',[{'travel':0.5},{'opening':25},{'fly_system':'yes'},{'fly_bars':1.5}])
def test_general_resource_api_cannot_bypass_venue_validation(clean,data):
    c,S=clean;v,person,p,r=setup_clean(c)
    before=c.get('/api/bootstrap').json()
    assert c.patch('/api/resources/'+str(v['id']),json={'data':data}).status_code==422
    assert c.get('/api/bootstrap').json()==before

@pytest.mark.parametrize('change',[{'production_id':True},{'venue_id':True},{'scenes':[True]},{'rehearsal_people':[True]},{'replacements':{'12345':1}}])
def test_invalid_command_rejected_before_solver(clean,change):
    c,S=clean;v,person,p,r=setup_clean(c)
    assert c.post('/api/preview',json={**r,**change}).status_code==422

def test_calendar_range_includes_preparation_and_excludes_touching_boundary(clean):
    c,S=clean;v,person,p,r=setup_clean(c)
    ev=confirm(c,r).json();eid=ev['id']
    found=c.get('/api/events',params={'start':'2026-12-01T17:00:00','end':'2026-12-01T18:00:00'}).json()
    assert eid in [e['id'] for e in found]
    detail=c.get('/api/events/'+str(eid)).json()
    last=max(t['end'] for t in detail['tasks'])
    assert c.get('/api/events',params={'start':last}).json()==[]

def test_person_and_equipment_filters_are_intersection(clean):
    c,S=clean;v,person,p,r=setup_clean(c)
    item=c.post('/api/resources',json={'kind':'Equipment','name':'Другой прибор','department':'Свет','data':{}}).json()
    confirm(c,r)
    assert c.get('/api/events',params={'person':person['id'],'equipment':item['id']}).json()==[]

def test_cancel_is_terminal_and_actuals_cannot_be_added_after_cancel(clean):
    c,S=clean;v,person,p,r=setup_clean(c);ev=confirm(c,r).json()
    task=c.get('/api/events/'+str(ev['id'])).json()['tasks'][0]
    url='/api/events/'+str(ev['id'])+'/status'
    assert c.post(url,json={'status':'Cancelled','version':ev['version']}).status_code==200
    assert c.post(url,json={'status':'Cancelled','version':ev['version']+1}).status_code==422
    assert c.patch('/api/tasks/'+str(task['id'])+'/actual',json={'start':task['start'],'end':task['end']}).status_code==422

def test_import_corrupt_saved_snapshot_does_not_switch_database(clean,tmp_path):
    c,S=clean;v,person,p,r=setup_clean(c);confirm(c,r)
    original=c.get('/api/events').json()
    path=tmp_path/'bad.db';path.write_bytes(c.get('/api/database/export').content)
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("UPDATE events SET data=?", ('{"request":{},"plan":{}}',))
    assert c.post('/api/database/import',content=path.read_bytes()).status_code==422
    assert c.get('/api/events').json()==original

def test_simultaneous_confirm_has_one_winner_and_atomic_reservations(clean):
    c,S=clean;v,person,p,r=setup_clean(c)
    plan=c.post('/api/preview',json=r).json()
    body={'request':r,'fingerprint':plan['fingerprint']}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:c.post('/api/events',json=body),range(2)))
    assert sorted(x.status_code for x in responses)==[200,409]
    with S() as s:
        assert s.scalar(select(func.count(Event.id)))==1
        assert s.scalar(select(func.count(Task.id)))==len(plan['tasks'])
        assert s.scalar(select(func.count(Booking.id)))==len(plan['bookings'])

def test_import_valid_backup_can_restart_with_same_data(clean,tmp_path):
    c,S=clean;v,person,p,r=setup_clean(c);confirm(c,r)
    expected=c.get('/api/events').json()
    assert c.post('/api/database/import',content=c.get('/api/database/export').content).status_code==200
    assert c.get('/api/events').json()==expected


def test_saved_event_rechecks_opening_hours_and_qualifications(clean):
    c,S=clean;v,person,p,r=setup_clean(c);ev=confirm(c,r).json()
    assert c.patch('/api/venues/'+str(v['id']),json={'name':v['name'],'data':{'closing':18}}).status_code==200
    assert c.patch('/api/resources/'+str(person['id']),json={'data':{'qualification':['Балет']}}).status_code==200
    detail=c.get('/api/events/'+str(ev['id'])).json()['current']
    assert detail['status']=='CONFLICT'
    assert {'closing','qualification'} <= {x['code'] for x in detail['conflicts']}


@pytest.mark.parametrize('body',[{}, {'enabled':'false','endpoint':'http://localhost','model':'x','provider':'Custom'}, {'enabled':True,'endpoint':'http://localhost','model':'','provider':'Ollama'}])
def test_malformed_ai_settings_are_422_and_do_not_change_core(clean,body):
    c,S=clean;v,person,p,r=setup_clean(c)
    assert c.put('/api/settings/llm',json=body).status_code==422
    assert c.post('/api/preview',json=r).json()['status']=='READY'


def test_backup_preserves_live_conflicts_after_qualification_change(clean):
    c,S=clean;v,person,p,r=setup_clean(c);ev=confirm(c,r).json()
    assert c.patch('/api/resources/'+str(person['id']),json={'data':{'qualification':['Балет']}}).status_code==200
    assert 'qualification' in {x['code'] for x in c.post('/api/preview',json=r).json()['conflicts']}
    backup=c.get('/api/database/export').content
    restored=c.post('/api/database/import',content=backup)
    assert restored.status_code==200,restored.text
    assert c.get('/api/events/'+str(ev['id'])).json()['current']['status']=='CONFLICT'

def test_snapshot_references_cannot_be_deleted_when_passport_changes(clean):
    c,S=clean;v,person,p,r=setup_clean(c)
    item=c.post('/api/inventory/units',json={'kind':'Prop','name':'Исторический реквизит','quantity':1,'department':'Реквизит','data':{}}).json()[0]
    p['data']['items']=[item['id']]
    p=c.patch('/api/productions/'+str(p['id']),json=p).json();ev=confirm(c,r).json()
    p['data']['items']=[]
    assert c.patch('/api/productions/'+str(p['id']),json=p).status_code==200
    assert c.post('/api/events/'+str(ev['id'])+'/status',json={'status':'Cancelled','version':ev['version']}).status_code==200
    assert c.delete('/api/resources/'+str(item['id'])).status_code==409


def test_export_closes_every_sqlite_connection_before_removing_file(clean,monkeypatch):
    c,S=clean;v,person,p,r=setup_clean(c);confirm(c,r)
    connections=[]
    connect=sqlite3.connect
    class Tracked(sqlite3.Connection):
        closed=False
        def close(self):
            self.closed=True
            super().close()
    def opened(*args,**kwargs):
        conn=connect(*args,**kwargs,factory=Tracked)
        connections.append(conn)
        return conn
    monkeypatch.setattr(sqlite3,'connect',opened)
    response=c.get('/api/database/export')
    assert response.status_code==200
    assert len(connections)>=3 and all(conn.closed for conn in connections)
