"""HKMT public programme: deterministic parsing and additive, plan-free import."""
import hashlib
import re
import threading
import time
from datetime import datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from .models import Production, Resource, Event, Setting, Audit

URL='https://hkmt.ru/'
MONTHS={'января':1,'февраля':2,'марта':3,'апреля':4,'мая':5,'июня':6,'июля':7,'августа':8,'сентября':9,'октября':10,'ноября':11,'декабря':12}


class Node:
    def __init__(self, tag='', attrs=()):self.tag=tag;self.attrs=dict(attrs);self.children=[]
    def all(self):
        yield self
        for child in self.children:
            if isinstance(child,Node):yield from child.all()
    def text(self):return ' '.join(' '.join(x.text() if isinstance(x,Node) else x for x in self.children).split())
    def cls(self,name):return name in self.attrs.get('class','').split()
    def field(self,name):return next((x.text() for x in self.all() if x.cls(name)),'')


class Document(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.root=Node();self.stack=[self.root]
    def handle_starttag(self,tag,attrs):
        n=Node(tag,attrs);self.stack[-1].children.append(n)
        if tag not in {'img','meta','link','br','hr','input','source','area','wbr','embed','param','col','base'}:self.stack.append(n)
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==tag:self.stack=self.stack[:i];break
    def handle_data(self,data):self.stack[-1].children.append(data)


def parse(html, year=2026, months=None):
    doc=Document();doc.feed(html);items={};warnings=[]
    for row in [n for n in doc.root.all() if n.cls('afishamonth')]:
        label=row.field('datetimeblock1')
        date_match=re.search(r'(\d{1,2})\s+('+'|'.join(MONTHS)+')',label.lower())
        if not date_match:continue
        day=int(date_match[1]);month=MONTHS[date_match[2]]
        if months is not None and month not in months:continue
        title=row.field('namespec');clock=re.search(r'\b(\d{1,2}):(\d{2})\b',row.field('datetimeblock3'))
        attrs=' '.join(str(v) for n in row.all() for v in n.attrs.values())
        tickets=set(re.findall(r't_(\d{8})_(\d{4})_p_(\d+)',attrs))
        if not title or not clock: warnings.append('Пропущена строка без названия или времени: '+label);continue
        try:
            expected_year=year+(month<10)
            start=datetime(expected_year,month,day,int(clock[1]),int(clock[2]))
            if tickets:
                times={datetime.strptime(d+t,'%Y%m%d%H%M') for d,t,p in tickets}
                if len(times)!=1 or next(iter(times)).date()!=start.date():raise ValueError('Дата билета не совпадает с афишей или выбранным сезоном')
                if next(iter(times))!=start:warnings.append(title+': время на афише отличается от ссылки билетов; взято время афиши.')
            link=next((urljoin(URL,n.attrs['href']) for n in row.all() if n.tag=='a' and '/performance/' in n.attrs.get('href','')),URL)
            if urlparse(link).hostname!='hkmt.ru':raise ValueError('Неизвестный источник постановки')
            ticket_ids={p for d,t,p in tickets}
            key='ticket:'+next(iter(ticket_ids)) if len(ticket_ids)==1 else hashlib.sha256((link+'|'+title.casefold()+'|'+start.isoformat()).encode()).hexdigest()
            description=row.field('afishatype1').split('Купить билет')[0].strip()
            text=description.casefold()
            venue=next((name for needle,name in [('одора','ОДОРА'),('дк профсоюзов','ДК Профсоюзов'),('мир говорящих машин','Музей «Мир говорящих машин»'),('художественн','Дальневосточный художественный музей')] if needle in text),'Площадка из афиши — уточнить')
            items[key]=dict(key=key,title=title[:200],start=start.isoformat(),url=link,venue=venue,description=description[:1000])
        except ValueError as e:warnings.append(title+': '+str(e))
    if not items:raise ValueError('В афише не найдено событий выбранного сезона. База не изменена.')
    return {'items':sorted(items.values(),key=lambda x:x['start']),'warnings':warnings}


def fetch_programme(year,months):
    with httpx.Client(timeout=15,follow_redirects=False) as client:
        with client.stream('GET',URL,headers={'User-Agent':'StageOS/1.0.15 programme-import'}) as response:
            response.raise_for_status();chunks=[];size=0
            for chunk in response.iter_bytes():
                size+=len(chunk)
                if size>2_000_000:raise ValueError('Афиша слишком велика')
                chunks.append(chunk)
    return parse(b''.join(chunks).decode('utf-8'),year,months)


def normal(name):return re.sub(r'[\W_]+',' ',name.casefold().replace('ё','е')).strip()


def passport_duration(production):
    value=production.data.get('duration') if production else None
    return value if production and not production.data.get('afisha_incomplete') and isinstance(value,int) and not isinstance(value,bool) and 15<=value<=480 else None


def empty_plan(event,request,venue,production=None):
    duration=passport_duration(production)
    end=event.start+timedelta(minutes=duration or 15)
    return dict(request=request,title=event.title,venue=venue.name,start=event.start.isoformat(),end=end.isoformat(),
                status='WARNING',needs_plan=True,estimated_end=duration is None,duration_minutes=duration,assignments=[],event_roles=[],tasks=[],bookings=[],conflicts=[],
                production_passport=dict(id=production.id,name=production.name,data=production.data) if production else None,
                compatibility=dict(checks=[],conflicts=[],requirements={},override=False,version='Не заполнено'),
                notes='Импорт из афиши hkmt.ru. Производственный план не заполнен.',fingerprint='')


def apply_programme(s,programme):
    from .production_editor import template, validate_production
    from .catalog import VENUE_DEFAULTS, validate_venue_data
    from .engine import Request
    productions=list(s.scalars(select(Production)));venues=list(s.scalars(select(Resource).where(Resource.kind=='Venue')));events=list(s.scalars(select(Event)))
    result=dict(added_events=0,added_productions=0,added_venues=0,updated_events=0,existing=0,available_months=sorted({datetime.fromisoformat(i['start']).month for i in programme['items']}),warnings=list(programme['warnings']))
    for item in programme['items']:
        existing=next((e for e in events if e.data.get('afisha',{}).get('key')==item['key']),None)
        start=datetime.fromisoformat(item['start'])
        if existing:
            production=s.get(Production,existing.production_id)
            if existing.status=='Draft' and existing.data.get('plan',{}).get('needs_plan'):
                duration=passport_duration(production)
                desired_end=existing.start+timedelta(minutes=duration or 15)
                if existing.end!=desired_end:
                    existing.end=desired_end;existing.version+=1;result['updated_events']+=1
                    venue=s.get(Resource,existing.venue_id)
                    existing.data={**existing.data,'plan':empty_plan(existing,existing.data['request'],venue,production)}
                    s.add(Audit(event_id=existing.id,action='Продолжительность из паспорта постановки',data={'production_id':production.id}))
            if existing.start!=start or normal(existing.title)!=normal(item['title']):
                if existing.status=='Draft' and existing.data.get('plan',{}).get('needs_plan') and normal(existing.title)==normal(item['title']):
                    existing.start=start;existing.end=start+timedelta(minutes=passport_duration(production) or 15);existing.version+=1
                    request={**existing.data['request'],'start':start.isoformat()};venue=s.get(Resource,existing.venue_id)
                    existing.data={**existing.data,'request':request,'plan':empty_plan(existing,request,venue,production)};result['updated_events']+=1
                    s.add(Audit(event_id=existing.id,action='Дата обновлена из афиши',data={'source':URL}))
                else:result['warnings'].append(item['title']+': дата или название на сайте изменились; заполненное или отменённое событие сохранено.')
            result['existing']+=1;continue
        production_matches=[p for p in productions if normal(p.name)==normal(item['title'])]
        venue_matches=[v for v in venues if normal(v.name)==normal(item['venue'])]
        if len(production_matches)>1 or len(venue_matches)>1:result['warnings'].append(item['title']+': несколько совпадений постановки или площадки; требуется уточнение.');continue
        p=production_matches[0] if production_matches else None
        v=venue_matches[0] if venue_matches else None
        if any(e.start==start and normal(e.title)==normal(item['title']) for e in events):result['existing']+=1;continue
        if not v:
            data={k:False if isinstance(val,bool) else 0 for k,val in VENUE_DEFAULTS.items()};data.update(opening=0,closing=24,afisha_incomplete=True)
            v=Resource(kind='Venue',name=item['venue'],department='Площадки',data=validate_venue_data(data));s.add(v);s.flush();venues.append(v);result['added_venues']+=1
        if not p:
            data=template()['data'];data.update(home_venue=v.id,afisha_url=item['url'],afisha_incomplete=True)
            p=Production(name=item['title'],data=validate_production(s,data));s.add(p);s.flush();productions.append(p);result['added_productions']+=1
        request=Request(production_id=p.id,venue_id=v.id,start=start,baseline_plan=True,run_through=True).model_dump(mode='json')
        event=Event(production_id=p.id,venue_id=v.id,title=p.name,kind='Спектакль',start=start,end=start+timedelta(minutes=passport_duration(p) or 15),status='Draft',data={})
        event.data=dict(request=request,plan=empty_plan(event,request,v,p),afisha=item,layer='PLANNED')
        s.add(event);s.flush();events.append(event);s.add(Audit(event_id=event.id,action='Добавлено из афиши без плана',data={'source':URL,'key':item['key']}));result['added_events']+=1
    return result


class Preferences(BaseModel):
    model_config=ConfigDict(extra='forbid')
    enabled:bool=True
    auto_months:bool=True
    year:int=Field(default=2026,ge=2020,le=2100)
    months:list[int]=Field(default_factory=lambda:[10,11,12,1],min_length=1,max_length=12)


def preferences(s):
    setting=s.get(Setting,'afisha');return setting.value if setting else {'enabled':False,'auto_months':True,'year':datetime.now().year,'months':[10,11,12,1]}


def sync(Session,lock,stop=None):
    with Session() as s:config=preferences(s)
    programme=fetch_programme(config['year'],None if config.get('auto_months',True) else config['months'])
    if stop and stop.is_set():return None
    with lock,Session.begin() as s:
        current=preferences(s)
        if (stop and (stop.is_set() or not current.get('enabled'))) or current.get('year')!=config['year'] or current.get('months')!=config['months'] or current.get('auto_months',True)!=config.get('auto_months',True):return None
        result=apply_programme(s,programme)
        setting=s.get(Setting,'afisha')
        if not setting:setting=Setting(key='afisha',value=config);s.add(setting)
        setting.value={**current,'last_attempt':time.time(),'last_success':time.time(),'error':'','result':result}
    return result


def install(app,Session,lock):
    @app.get('/api/afisha')
    def status():
        with Session() as s:return preferences(s)
    @app.post('/api/afisha/settings')
    def configure(body:Preferences):
        if len(set(body.months))!=len(body.months) or any(m not in range(1,13) for m in body.months):raise HTTPException(422,'Выберите месяцы от января до декабря')
        with lock,Session.begin() as s:
            old=preferences(s);setting=s.get(Setting,'afisha')
            if not setting:setting=Setting(key='afisha');s.add(setting)
            setting.value={**old,**body.model_dump(),'last_attempt':0};s.add(Audit(action='Настроен автоимпорт афиши',data=body.model_dump()))
        return status()
    @app.post('/api/afisha/sync')
    def refresh():
        try:return sync(Session,lock)
        except (httpx.HTTPError,ValueError,UnicodeError) as e:raise HTTPException(422,'Не удалось прочитать афишу hkmt.ru. Существующие события сохранены.') from e


class Worker:
    def __init__(self,registry):self.registry=registry;self.stop_event=threading.Event();self.thread=None
    def start(self):self.thread=threading.Thread(target=self.run,daemon=True,name='StageOS-afisha');self.thread.start()
    def stop(self):self.stop_event.set()
    def run(self):
        from .app import LOCK
        while not self.stop_event.is_set():
            with self.registry.db() as db:ids=[r[0] for r in db.execute('SELECT id FROM theatres')]
            for tid in ids:
                if self.stop_event.is_set():return
                app=None
                try:
                    app=self.registry.tenant(tid)
                    with app.state.Session() as s:config=preferences(s)
                    if not config.get('enabled') or time.time()-config.get('last_attempt',0)<1800:continue
                    with LOCK,app.state.Session.begin() as s:s.get(Setting,'afisha').value={**config,'last_attempt':time.time()}
                    result=sync(app.state.Session,LOCK,self.stop_event)
                    if result and (result['added_events'] or result['updated_events']):
                        with self.registry.lock:self.registry.revisions[tid]=self.registry.revisions.get(tid,0)+1
                except Exception:
                    if self.stop_event.is_set():return
                    if app is None:continue
                    with LOCK,app.state.Session.begin() as s:
                        row=s.get(Setting,'afisha')
                        if row:row.value={**row.value,'last_attempt':time.time(),'error':'Не удалось обновить афишу. Следующая попытка через 30 минут.'}
            self.stop_event.wait(10)
