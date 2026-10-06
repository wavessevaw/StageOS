import sys, unittest, asyncio, json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
sys.path.insert(0,str(next(p for p in Path(__file__).resolve().parents if (p/'backend/models.py').is_file())))
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.models import Base, Production, Resource, Event, Booking, Task, Setting
from backend.assistant_facts import build_context, render_answer, period, theatre_clock, resolve, clipped_hours
from backend.assistant_service import answer_question
from backend.production_editor import template

NOW=datetime(2026,10,4,15,tzinfo=timezone.utc) # Oct 5 locally; host day is irrelevant.

class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.s=Session(self.engine)
        self.s.add(Setting(key='theatre',value={'name':'Test theatre','timezone':'Asia/Vladivostok'}))
        self.s.add_all([Resource(id=1,kind='Person',name='Марина Северова',department='Артисты',data={}),
                        Resource(id=2,kind='Person',name='Иван Северин',department='Артисты',data={}),
                        Resource(id=3,kind='Venue',name='Большая сцена',data={'width':4}),
                        Resource(id=4,kind='Person',name='Марина Восточная',department='Звук',data={})])
        data=template()['data'];data['duration']=95;data['requirements']['width']=8
        data['roles']=[{'role':'Главная роль','A':1,'B':0,'eligible':[1,2]}]
        data['responsibles']={'Звук':4}
        self.s.add_all([Production(id=1,name='Маринованные истории',data=data),Production(id=2,name='Лунный свет',data={})])
        self.s.flush()
    def tearDown(self):
        self.s.close();self.engine.dispose()
    def event(self,eid=1,actual=2,responsible=1,status='Approved',hour=19):
        start=datetime(2026,10,5,hour)
        e=Event(id=eid,production_id=1,venue_id=3,title='Маринованные истории',kind='Спектакль',
                start=start,end=start+timedelta(hours=2),status=status,
                data={'plan':{'assignments':[{'role':'Главная роль','department':'Артисты','actual_id':actual,
                      'actual':'Иван Северин','responsible_id':responsible,'responsible':'Марина Северова','call':start.isoformat()}]}})
        self.s.add(e);self.s.flush();return e
    def ctx(self,q):return build_context(self.s,q,NOW)
    def test_no_four_letter_collision(self):
        c=self.ctx('Расписание Иван Северин');self.assertFalse(c['productions'])
        self.assertEqual(resolve('Марина',self.s.query(Production).all())[0],[])
    def test_ambiguous_first_name(self):
        c=self.ctx('Сотрудник Марина');self.assertTrue(c['clarification']);self.assertFalse(c['events'])
    def test_participation_actual_not_responsible(self):
        self.event();self.assertFalse(self.ctx('Расписание Марина Северова')['events'])
        self.assertEqual(len(self.ctx('Расписание Иван Северин')['events']),1)
    def test_booked_person_is_participant(self):
        self.event();self.s.add(Booking(event_id=1,resource_id=4,start=datetime(2026,10,5,16),end=datetime(2026,10,5,21),label='Sound'))
        self.s.flush();self.assertEqual(len(self.ctx('Расписание Марина Восточная')['events']),1)
    def test_all_assignments_present(self):
        self.event();c=self.ctx('Кто фактически работает Маринованные истории сегодня')
        self.assertEqual(c['events'][0]['assignments'][0]['department'],'Артисты')
        self.assertEqual(c['events'][0]['assignments'][0]['actual_id'],2)
    def test_more_than_40_events(self):
        for i in range(1,46):self.event(eid=i)
        c=self.ctx('Расписание сегодня');self.assertEqual(len(c['events']),45);self.assertTrue(c['scope']['complete'])
    def test_partial_explicit(self):
        for i in range(1,203):self.event(eid=i)
        c=self.ctx('Расписание сегодня');self.assertEqual(c['scope']['matched_events'],202)
        self.assertFalse(c['scope']['complete']);self.assertIn('НЕПОЛНЫЙ',render_answer(c,'Расписание сегодня'))
    def test_today_theatre_timezone(self):
        self.event();self.assertEqual(self.ctx('schedule today')['scope']['start'],'2026-10-05T00:00:00')
        self.assertEqual(theatre_clock(self.s,NOW)[0].day,5)
    def test_week_and_inclusive_period(self):
        day=datetime(2026,10,7)
        self.assertEqual(period('следующая неделя',day)[0],datetime(2026,10,12))
        self.assertEqual(period('2026-10-04 — 2026-10-05',day)[1],datetime(2026,10,6))
    def test_cross_midnight_preparation(self):
        self.event(hour=0);self.s.add(Task(event_id=1,name='Погрузка',department='Транспорт',start=datetime(2026,10,4,23),end=datetime(2026,10,5,0)))
        self.s.flush();self.assertEqual(len(self.ctx('Погрузка 2026-10-04')['events']),1)
    def test_missing_fields_do_not_crash(self):
        c=self.ctx('Продолжительность Лунный свет');self.assertIsNone(c['productions'][0]['duration_minutes'])
        self.event();ev=self.s.get(Event,1);ev.data={};self.s.flush()
        self.assertEqual(self.ctx('Расписание сегодня')['events'][0]['assignments'],[])
    def test_cancelled_bookings_excluded(self):
        self.event(status='Cancelled');self.s.add(Booking(event_id=1,resource_id=2,start=datetime(2026,10,5,19),end=datetime(2026,10,5,21),label='Cancelled'))
        self.s.flush();c=self.ctx('Расписание Иван Северин');self.assertFalse(c['events']);self.assertFalse(c['people'][0]['bookings'])
    def test_cast_eligibility_not_assignment(self):
        c=self.ctx('Состав Маринованные истории');r=c['productions'][0]['roles'][0]
        self.assertIsNone(r['cast_B']);self.assertEqual([x['id'] for x in r['eligible']],[1,2])
    def test_union_hours_and_person_hours(self):
        self.event()
        for rid,a,b in [(1,10,12),(1,11,13),(2,10,12)]:self.s.add(Booking(event_id=1,resource_id=rid,start=datetime(2026,10,5,a),end=datetime(2026,10,5,b),label='work'))
        self.s.flush();c=self.ctx('Загрузка Артисты сегодня');self.assertEqual(c['analytics']['person_hours'],5)
        self.assertEqual(c['analytics']['people'][0]['booked_hours'],3)
    def test_compatibility_uses_engine(self):
        c=self.ctx('Совместимость Маринованные истории Большая сцена')
        self.assertEqual(c['compatibility'][0]['result']['version'],'INCOMPATIBLE')
        self.assertEqual(c['compatibility'][0]['result']['conflicts'][0]['code'],'width')
    def test_conflict_failure_visible(self):
        self.event();c=self.ctx('Конфликты сегодня');self.assertIn('KeyError',c['events'][0]['check_error'])
    def test_typos_only_clarify(self):
        c=self.ctx('Продолжительность Маринованые истории');self.assertTrue(c['clarification'])
    def test_unknown_employee_does_not_get_every_event(self):
        self.event();c=self.ctx('Расписание сотрудника «Неизвестный человек»');self.assertTrue(c['clarification']);self.assertFalse(c['events'])
    def test_fresh_session_and_no_mutation(self):
        self.assertEqual(self.ctx('Продолжительность Маринованные истории')['productions'][0]['duration_minutes'],95)
        p=self.s.get(Production,1);p.data={**p.data,'duration':100};self.s.flush()
        self.assertEqual(self.ctx('Продолжительность Маринованные истории')['productions'][0]['duration_minutes'],100)
        self.assertFalse(self.s.dirty)
    def test_disabled_model_still_returns_facts(self):
        out=asyncio.run(answer_question(self.s,'Продолжительность Маринованные истории','ru',{'enabled':False},None,NOW,True))
        self.assertIn('95',out['answer']);self.assertEqual(out['source'],'database')
    def test_model_hallucination_and_commands_rejected(self):
        async def wrong(*args,**kwargs):return '{"answer":"Назначен неизвестный артист 999","command":{}}'
        with patch('backend.assistant_service.request_model',wrong):
            out=asyncio.run(answer_question(self.s,'Продолжительность Маринованные истории','ru',{'enabled':True},None,NOW,True))
        self.assertFalse(out['model_accepted']);self.assertNotIn('999',out['answer'])
    def test_native_request_parameters(self):
        from backend.model_client import request_model
        seen={}
        class Reply:
            def raise_for_status(self):pass
            def json(self):return {'message':{'content':'{"answer":"ok"}'}}
        class Client:
            def __init__(self,**kw):seen.update(kw)
            async def __aenter__(self):return self
            async def __aexit__(self,*a):pass
            async def post(self,url,json):seen.update(url=url,payload=json);return Reply()
        asyncio.run(request_model({'provider':'Ollama','endpoint':'http://127.0.0.1:11434/v1','model':'qwen3:0.6b'},[],Client))
        self.assertTrue(seen['url'].endswith('/api/chat'));self.assertFalse(seen['payload']['think'])
        self.assertFalse(seen['payload']['stream']);self.assertEqual(seen['payload']['format'],'json')
        self.assertEqual(seen['payload']['options']['temperature'],0);self.assertEqual(seen['payload']['options']['num_ctx'],16384)

    def test_date_words_in_title_are_not_a_date_filter(self):
        self.s.add(Production(id=3,name='Я сегодня смеюсь',data={'duration':77}));self.s.flush()
        c=self.ctx('Продолжительность Я сегодня смеюсь')
        self.assertEqual(c['intent'],'productions');self.assertIsNone(c['scope']['start'])
        self.assertEqual(c['productions'][0]['duration_minutes'],77)
    def test_today_and_hours_do_not_resolve_title_tokens(self):
        self.s.add(Production(id=3,name='Пока часы двенадцать бьют',data={'duration':77}));self.s.flush()
        c=self.ctx('Часы Иван Северин сегодня');self.assertFalse(c['clarification']);self.assertFalse(c['productions'])
    def test_artist_not_booked_during_yesterday_loading(self):
        self.event(hour=19);self.s.add(Task(event_id=1,name='Погрузка',department='Транспорт',start=datetime(2026,10,4,22),end=datetime(2026,10,4,23)));self.s.flush()
        self.assertFalse(self.ctx('Расписание Иван Северин 2026-10-04')['events'])
    def test_nullable_eligible_and_groups(self):
        p=self.s.get(Production,1);p.data={**p.data,'roles':[{'role':'Solo','eligible':None}], 'groups':{'Хор':None}};self.s.flush()
        c=self.ctx('Состав Маринованные истории');self.assertEqual(c['productions'][0]['roles'][0]['eligible'],[])

class IntegrationTests(unittest.TestCase):
    def test_authenticated_selected_theatre_isolation_and_no_writes(self):
        import tempfile,os
        from fastapi.testclient import TestClient
        from backend.workspaces import create_workspace_app
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'STAGEOS_HOME':folder,'STAGEOS_DATABASE_URL':''}):
            # An unset override avoids an invalid empty SQLAlchemy URL.
            os.environ.pop('STAGEOS_DATABASE_URL',None)
            app=create_workspace_app(folder);r=app.state.registry
            clients=[];tids=[]
            try:
                for index,duration in [(1,91),(2,137)]:
                    client=TestClient(app,headers={'X-StageOS-Token':os.environ.get('STAGEOS_TOKEN','')})
                    body={'theatre_name':'Synthetic theatre '+str(index),'name':'Synthetic admin','login':'test'+str(index),'password':'synthetic-only-secret'}
                    response=client.post('/api/auth/theatres',json=body);self.assertEqual(response.status_code,200)
                    tid=response.json()['id'];tids.append(tid)
                    response=client.post('/api/auth/login',json={'theatre_id':tid,'login':body['login'],'password':body['password']});self.assertEqual(response.status_code,200)
                    with r.tenant(tid).state.Session.begin() as s:s.add(Production(name='Тестовая постановка',data={'duration':duration}))
                    clients.append(client)
                for index,client in enumerate(clients):
                    response=client.post('/api/assistant',json={'text':'Продолжительность Тестовая постановка','language':'ru'})
                    self.assertEqual(response.status_code,200);self.assertIn(str([91,137][index]),response.json()['answer'])
                    self.assertNotIn(str([137,91][index]),response.json()['answer'])
                    with r.tenant(tids[index]).state.Session() as s:
                        self.assertEqual(s.query(Event).count(),0);self.assertEqual(s.query(Booking).count(),0)
                    self.assertEqual(r.revisions.get(tids[index],0),0)
            finally:
                for client in clients:client.close()
                r.close()
    def test_stored_conflict_engine_and_lunch(self):
        fixture=AssistantTests();fixture.setUp()
        try:
            ev=fixture.event();ev.data={'request':{},'plan':{'assignments':[], 'conflicts':[{'code':'width','severity':'CRITICAL','reason':'Too narrow','resource':'Test venue'}],'tasks':[]}}
            fixture.s.flush()
            c=fixture.ctx('Конфликты сегодня');self.assertIsNone(c['events'][0]['check_error'])
            self.assertEqual(c['events'][0]['conflicts'][0]['code'],'width')
            from backend.assistant_facts import scheduled_hours
            ev.data={'plan':{'tasks':[{'name':'Обед','start':'2026-10-05T12:00:00','end':'2026-10-05T13:00:00'}]}}
            b=Booking(event_id=ev.id,resource_id=1,start=datetime(2026,10,5,10),end=datetime(2026,10,5,14),label='Work',state='reserved')
            self.assertEqual(scheduled_hours([b],{ev.id:ev}),3)
        finally:fixture.tearDown()

if __name__=='__main__':unittest.main(verbosity=2)
