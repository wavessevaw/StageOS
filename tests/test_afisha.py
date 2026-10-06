from copy import deepcopy
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from backend.afisha import parse,apply_programme,sync,Worker
from backend.models import Event,Production,Task,Booking,Setting
from backend.database_io import validate_saved_data
from test_accounts import make,theatre,login
from test_core import ctx  # noqa: F401

HTML='''<div class="afishamonth month-10"><div class="datetimeblock1">8 октября</div><div class="datetimeblock2">четверг</div><div class="datetimeblock3">19:00</div><div class="namespec"><a href="/performance/anna/">Анна Каренина</a></div><div class="afishatype1">Мюзикл на сцене ОДОРА</div><button onclick="show('t_20261008_1900_p_123')">Билет</button></div>'''

def test_parser_dates_year_rollover_and_no_hidden_ticket_time_override():
    r=parse(HTML);assert r['items'][0]['start']=='2026-10-08T19:00:00'
    jan=HTML.replace('8 октября','8 января').replace('20261008','20270108');assert parse(jan)['items'][0]['start']=='2027-01-08T19:00:00'
    wrong=HTML.replace('20261008_1900','20261008_1800');assert parse(wrong)['warnings'] and parse(wrong)['items'][0]['start'].endswith('19:00:00')

def test_add_once_reuse_normalized_production_and_no_plan_or_person_bookings(tmp_path,monkeypatch):
    app,c=make(tmp_path,monkeypatch);tid=theatre(c);login(c,tid);tenant=app.state.registry.tenant(tid)
    with tenant.state.Session.begin() as s:
        programme=parse(HTML);first=apply_programme(s,programme);assert first['added_events']==first['added_productions']==1
        again=apply_programme(s,programme);assert again['added_events']==again['added_productions']==0
        second=parse(HTML.replace('8 октября','9 октября').replace('20261008','20261009').replace('p_123','p_124').replace('Анна Каренина','  «АННА  КАРЕНИНА» '))
        assert apply_programme(s,second)['added_productions']==0
        assert s.scalar(select(func.count(Production.id)))==1 and s.scalar(select(func.count(Event.id)))==2
        assert s.scalar(select(func.count(Task.id)))==s.scalar(select(func.count(Booking.id)))==0
        validate_saved_data(s)
    entries=c.get('/api/events').json();assert all(e['needs_plan'] and e['status']=='Draft' for e in entries)
    detail=c.get('/api/events/'+str(entries[0]['id'])).json();assert detail['current']['needs_plan'] and detail['current']['tasks']==[]
    assert c.get('/api/schedule/export?start=2026-10-08&end=2026-10-09&format=pdf').status_code==200
    assert c.post('/api/events/'+str(entries[0]['id'])+'/status',json={'status':'Planning','version':1}).status_code==422

def test_auto_date_update_but_preserve_completed_plan_and_cancellation(tmp_path,monkeypatch):
    app,c=make(tmp_path,monkeypatch);tid=theatre(c);login(c,tid);Session=app.state.registry.tenant(tid).state.Session
    with Session.begin() as s:
        apply_programme(s,parse(HTML));e=s.scalar(select(Event));changed=parse(HTML.replace('8 октября','9 октября').replace('20261008','20261009'))
        assert apply_programme(s,changed)['updated_events']==1
        assert e.start==datetime(2026,10,9,19)
        e.status='Cancelled'
        result=apply_programme(s,parse(HTML));assert result['added_events']==result['updated_events']==0 and result['warnings']
        assert s.scalar(select(func.count(Event.id)))==1

def test_worker_imports_enabled_theatre_and_increments_revision(tmp_path,monkeypatch):
    app,c=make(tmp_path,monkeypatch);tid=theatre(c);login(c,tid)
    monkeypatch.setattr('backend.afisha.fetch_programme',lambda *args:parse(HTML))
    assert c.post('/api/afisha/settings',json={'enabled':True,'year':2026,'months':[10,11,12,1]}).status_code==200
    registry=app.state.registry;worker=Worker(registry)
    original=worker.stop_event.wait
    def one_loop(timeout):worker.stop();return True
    monkeypatch.setattr(worker.stop_event,'wait',one_loop);worker.run()
    assert c.get('/api/events').json()[0]['title']=='Анна Каренина'
    assert c.get('/api/afisha').json()['last_success']>0
    assert c.post('/api/afisha/sync').json()['added_events']==0
    c.post('/api/auth/users',json={'name':'Editor','login':'editor','password':'test-password','role':'editor'});login(c,tid,'editor')
    assert c.post('/api/afisha/sync').status_code==403


def test_existing_rich_passport_and_eligible_cast_are_preserved(ctx):
    c,Session,b,resources,request=ctx
    with Session.begin() as db:
        original=db.get(Production,request['production_id']);original.name='Я — Утёсов!'
        passport=deepcopy(original.data);original_id=original.id
        programme=parse(HTML.replace('Анна Каренина','Я-Утесов').replace('ОДОРА','Большой зал'))
        programme['items'][0]['venue']='Большой зал'
        result=apply_programme(db,programme)
        assert result['added_productions']==0
        event=db.scalar(select(Event).where(Event.title=='Я — Утёсов!'))
        assert event.production_id==original_id and event.data['request']['production_id']==original_id
        assert original.data==passport and any(role['eligible'] for role in passport['roles'])
        assert event.data['plan']['tasks']==[] and event.data['plan']['assignments']==[]
        assert (event.end-event.start).total_seconds()==passport['duration']*60
        event_id=event.id
        event_request=event.data['request']
    detail=c.get('/api/events/'+str(event_id)).json()['current']
    assert detail['production_passport']['id']==original_id and detail['production_passport']['data']==passport
    assert not detail['estimated_end']
    prepared=c.post('/api/preview',json=event_request)
    assert prepared.status_code==200,prepared.text
    assert prepared.json()['event_roles'][0]['eligible_ids']==passport['roles'][0]['eligible']


def test_previous_short_imported_draft_uses_passport_and_sync_repairs_storage(ctx):
    c,Session,b,resources,request=ctx
    programme=parse(HTML);programme['items'][0].update(title=b['productions'][0]['name'],venue='Большой зал')
    with Session.begin() as db:
        apply_programme(db,programme);event=db.scalar(select(Event).where(Event.data['afisha']['key'].as_string()=='ticket:123'))
        from datetime import timedelta
        event.end=event.start+timedelta(minutes=15);eid=event.id
    shown=next(e for e in c.get('/api/events').json() if e['id']==eid)
    assert (datetime.fromisoformat(shown['end'])-datetime.fromisoformat(shown['start'])).total_seconds()==b['productions'][0]['data']['duration']*60
    with Session.begin() as db:
        result=apply_programme(db,programme);assert result['updated_events']==1 and result['added_events']==0
        event=db.get(Event,eid);stored_end=event.end;event.status='Cancelled'
        production=db.get(Production,event.production_id);production.data={**production.data,'duration':90}
        assert apply_programme(db,programme)['updated_events']==0 and event.end==stored_end


def test_all_months_mode_imports_new_february_without_reconfiguration(tmp_path,monkeypatch):
    app,c=make(tmp_path,monkeypatch);tid=theatre(c);login(c,tid)
    html=HTML
    def source(year,months):return parse(html,year,months)
    monkeypatch.setattr('backend.afisha.fetch_programme',source)
    assert c.post('/api/afisha/settings',json={'enabled':True,'year':2026,'months':[10,11,12,1]}).status_code==200
    assert c.post('/api/afisha/sync').json()['added_events']==1
    html+=HTML.replace('8 октября','8 февраля').replace('20261008','20270208').replace('p_123','p_126')
    result=c.post('/api/afisha/sync').json()
    assert result['added_events']==1 and result['added_productions']==0 and result['available_months']==[2,10]
    assert any(e['start'].startswith('2027-02-08') for e in c.get('/api/events').json())
    assert c.post('/api/afisha/settings',json={'enabled':True,'year':2026,'months':[10],'auto_months':False}).status_code==200
    assert c.post('/api/afisha/sync').json()['available_months']==[10]
