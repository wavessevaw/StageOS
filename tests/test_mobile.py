from datetime import datetime
import httpx
from fastapi.testclient import TestClient
from backend.models import Booking, Resource, Production, Event
from test_accounts import make, theatre, login
from test_network import network  # noqa: F401


def provision(app, c, tid):
    assert login(c, tid).status_code == 200
    assert c.post('/api/auth/users', json={'name':'Василиса Серова','login':'vasilisa','password':'test-password','role':'admin'}).status_code == 200
    with app.state.registry.tenant(tid).state.Session.begin() as s:
        person=Resource(kind='Person',name='Василиса Серова',data={})
        other=Resource(kind='Person',name='Чужой сотрудник',data={})
        venue=Resource(kind='Venue',name='Основная сцена',data={})
        production=Production(name='Спектакль',data={})
        s.add_all([person,other,venue,production]);s.flush()
        event=Event(production_id=production.id,venue_id=venue.id,title='Мой спектакль',kind='performance',start=datetime(2026,12,1,18),end=datetime(2026,12,1,20),data={'plan':{'assignments':[{'actual_id':person.id,'role':'Артисты'}]}})
        s.add(event);s.flush()
        for rid,label,start,end,eid in [
            (person.id,'Мой вызов','2026-12-01T17:00','2026-12-01T21:00',event.id),
            (other.id,'Чужая занятость','2026-12-01T09:00','2026-12-01T22:00',None),
            (person.id,'Ночной монтаж','2026-11-29T23:00','2026-11-30T02:00',None),
            (person.id,'Следующая неделя','2026-12-07T09:00','2026-12-07T10:00',None),
        ]:s.add(Booking(resource_id=rid,label=label,start=datetime.fromisoformat(start),end=datetime.fromisoformat(end),event_id=eid))
        return person.id


def test_personal_week_and_mobile_cookie_cannot_authorize_desktop(tmp_path,monkeypatch):
    app,admin=make(tmp_path,monkeypatch);tid=theatre(admin)
    person_id=provision(app,admin,tid);phone=TestClient(app)
    assert phone.get('/api/mobile/schedule?start=2026-12-01').status_code==401
    assert phone.post('/api/mobile/login',json={'login':' VASILISA ','password':'test-password'}).status_code==200
    own=phone.get('/api/mobile/session').json();assert own['employee']['id']==person_id
    week=phone.get('/api/mobile/schedule?start=2026-12-01').json()
    assert week['start']=='2026-11-30' and week['end']=='2026-12-07'
    assert [x['title'] for x in week['items']]==['Ночной монтаж','Мой спектакль']
    assert week['items'][1]['venue']=='Основная сцена' and week['items'][1]['role']=='Артисты'
    assert 'Чуж' not in str(week) and 'assignments' not in str(week)
    assert phone.get('/api/bootstrap').status_code==401
    phone.cookies.set('stageos_session',phone.cookies.get('stageos_mobile_session'))
    assert phone.get('/api/bootstrap').status_code==401
    assert phone.post('/api/resources',json={}).status_code==401
    assert phone.get('/api/mobile/schedule?start=bad').status_code==422
    assert phone.post('/api/mobile/logout').status_code==200
    assert phone.get('/api/mobile/session').status_code==401
    assert admin.get('/api/bootstrap').status_code==200


def test_missing_ambiguous_and_cross_theatre_names_do_not_reveal_others(tmp_path,monkeypatch):
    app,c=make(tmp_path,monkeypatch);tid=theatre(c);person_id=provision(app,c,tid)
    phone=TestClient(app)
    with app.state.registry.tenant(tid).state.Session.begin() as s:s.get(Resource,person_id).name='Другое имя'
    assert phone.post('/api/mobile/login',json={'login':'vasilisa','password':'test-password'}).status_code==200
    result=phone.get('/api/mobile/schedule?start=2026-12-01').json();assert result['items']==[] and result['link_error']
    with app.state.registry.tenant(tid).state.Session.begin() as s:
        s.get(Resource,person_id).name='Василиса Серова'
        s.add(Resource(kind='Person',name='  ВАСИЛИСА  СЕРОВА ',data={}))
    assert phone.get('/api/mobile/schedule?start=2026-12-01').json()['items']==[]
    other=theatre(c,'Другой театр','second-admin');login(c,other,'second-admin')
    c.post('/api/auth/users',json={'name':'Чужая Василиса','login':'vasilisa','password':'test-password','role':'viewer'})
    assert TestClient(app).post('/api/mobile/login',json={'login':'vasilisa','password':'test-password'}).status_code==401


def test_mobile_remote_login_without_code_but_desktop_stays_protected(network):
    host,admin,clients,tid,address,code=network
    admin.post('/api/auth/users',json={'name':'Василиса Серова','login':'vasilisa','password':'test-password','role':'viewer'})
    with httpx.Client(base_url=address,trust_env=False) as phone:
        assert phone.post('/api/mobile/login',json={'login':'vasilisa','password':'test-password'}).status_code==200
        assert phone.get('/api/mobile/session').status_code==200
        assert phone.get('/api/mobile/schedule?start=2026-12-01').json()['items']==[]
        assert phone.get('/api/bootstrap').status_code==403
        assert phone.get('/api/auth/users',headers={'X-StageOS-Code':code}).status_code==401
        assert phone.post('/api/mobile/login',headers={'Origin':'https://evil.example'},json={'login':'vasilisa','password':'test-password'}).status_code==403
        stats=admin.get('/api/connection').json()['users']
        assert any(x['login']=='vasilisa' for x in stats['items'])
        phone.post('/api/mobile/logout')
        assert not any(x['login']=='vasilisa' for x in admin.get('/api/connection').json()['users']['items'])


def test_sound_employee_sees_own_rehearsal_in_mobile(tmp_path,monkeypatch):
    app,c=make(tmp_path,monkeypatch);tid=theatre(c);person_id=provision(app,c,tid)
    with app.state.registry.tenant(tid).state.Session.begin() as db:
        person=db.get(Resource,person_id);person.department='Звук';person.data={'qualification':['Звук']}
        event=db.query(Event).filter_by(title='Мой спектакль').one()
        event.kind='Репетиция';event.title='Репетиция со звуком'
        event.data={'plan':{'assignments':[{'actual_id':person_id,'role':'Звук'}]}}
    phone=TestClient(app)
    assert phone.post('/api/mobile/login',json={'login':'vasilisa','password':'test-password'}).status_code==200
    item=next(x for x in phone.get('/api/mobile/schedule?start=2026-12-01').json()['items'] if x['event_id'])
    assert item['kind']=='Репетиция' and item['title']=='Репетиция со звуком' and item['role']=='Звук'
