"""Read-only facts from the selected tenant session; no model-generated SQL."""
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy import select
from .models import Production, Resource, Event, Booking, Task, Setting

DEFAULT_TIMEZONE = 'Asia/Vladivostok'
MAX_EVENTS = 200
MAX_ANSWER = 14000

def norm(text):
    return ' '.join(re.findall(r'[\w]+', str(text).casefold().replace('ё', 'е')))

def resolve(question, rows):
    q = ' ' + norm(question) + ' '
    full = [r for r in rows if ' ' + norm(r.name) + ' ' in q]
    if full:
        full = [r for r in full if not any(r != x and norm(r.name) in norm(x.name) for x in full)]
        return full, []
    words = set(q.split())
    stop = {'театр','театра','сцена','сцены','основная','малая','постановка','музыкальный','спектакль','сотрудник','зал','имени','the','stage','сегодня','завтра','неделя','неделю','часы','часов','пока','день','почему','what','today','tomorrow','time','free','hours','week','who'}
    words -= stop
    exact = [r for r in rows if words & {w for w in norm(r.name).split() if len(w) >= 4 and w not in stop}]
    if exact:
        typos=[r.name for r in exact if any(a!=b and len(a)>=5 and len(b)>=5
               and SequenceMatcher(None,a,b).ratio()>=.84 for a in words for b in norm(r.name).split())]
        if typos:return [],typos
        return exact, []
    suggestions = [r.name for r in rows if any(len(a)>=5 and len(b)>=5 and SequenceMatcher(None,a,b).ratio()>=.84
                   for a in words for b in norm(r.name).split())]
    return [], suggestions

def strip_entities(question,entities):
    for r in entities:
        words=norm(r.name).split()
        pattern=r'\b'+r'[\W_]+'.join(re.escape(w).replace('е','[её]') for w in words)+r'\b'
        question=re.sub(pattern,' ',question,flags=re.IGNORECASE)
    return question

def theatre_clock(s, now=None):
    setting = s.get(Setting,'theatre')
    value = setting.value if setting and isinstance(setting.value,dict) else {}
    name = value.get('timezone',DEFAULT_TIMEZONE)
    try:
        tz = ZoneInfo(name)
    except ZoneInfoNotFoundError:
        if name != DEFAULT_TIMEZONE:
            raise ValueError('Неизвестный часовой пояс театра: '+str(name))
        tz = timezone(timedelta(hours=10))
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError('Контрольное время должно содержать часовой пояс')
    return instant.astimezone(tz).replace(tzinfo=None),name,value.get('name','')

def period(question, now):
    q = norm(question)
    dates = re.findall(r'\b(\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4})\b',question)
    if len(dates)>2:
        raise ValueError('Укажите одну дату или начало и конец периода')
    if dates:
        values=[datetime.strptime(x,'%Y-%m-%d' if '-' in x else '%d.%m.%Y') for x in dates]
        end=values[-1]+timedelta(days=1)
        if end<=values[0]:raise ValueError('Конец периода раньше начала')
        return values[0],end,True
    day=now.replace(hour=0,minute=0,second=0,microsecond=0)
    if 'послезавтра' in q:day+=timedelta(days=2)
    elif 'завтра' in q or 'tomorrow' in q:day+=timedelta(days=1)
    elif 'сегодня' in q or 'today' in q:pass
    elif 'недел' in q or 'week' in q:
        day-=timedelta(days=day.weekday())
        if 'следующ' in q or 'next' in q:day+=timedelta(days=7)
        return day,day+timedelta(days=7),True
    elif any(x in q for x in ['вчера','yesterday']):
        day-=timedelta(days=1)
    elif any(x in q for x in ['январ','феврал','март','апрел','мае','июн','июл','август','сентябр','октябр','ноябр','декабр',
                               'january','february','march','april','june','july','august','september','october','november','december']):
        raise ValueError('Укажите дату YYYY-MM-DD или DD.MM.YYYY / Use YYYY-MM-DD or DD.MM.YYYY')
    else:return None,None,False
    return day,day+timedelta(days=1),True

def intent(question):
    q=norm(question)
    for kind,terms in [
        ('compatibility',['совместим','подходит','подойдет','compatible','suitable','fit']),
        ('conflicts',['конфликт','пересечен','conflict','overlap']),
        ('analytics',['часов','часы','человеко','загрузк','hours','workload']),
        ('preparation',['погруз','выезд','монтаж','прогон','обед','демонтаж','подготов','load in','setup','lunch','teardown','departure','run through']),
        ('casts',['состав','допуск','на роль','исполнител','cast','eligible','role','unassigned']),
        ('events',['расписан','сегодня','завтра','недел','занят','участи','событи','events','event','фактич','замен','вызов','работает','свобод','schedule','today','tomorrow','week','busy','particip','actual','replacement','call time','working','free']),
        ('people',['подраздел','сотрудник','отсутств','department','employee','absence']),
        ('resources',['оборудован','количеств','резерв','ремонт','ресурс','equipment','quantity','reserv','repair','resource']),
        ('venues',['площадк','характерист','блокиров','venue','capacity','blocking']),
        ('productions',['продолжитель','длится','режиссер','команд','постановк','duration','director','team','production','ведет','responsible','who','кто'])]:
        if any(t in q for t in terms):return kind
    if re.search(r'\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4}',question):return 'events'
    return 'unknown'

def clipped_hours(bookings,start=None,end=None):
    intervals=sorted((max(b.start,start) if start else b.start,min(b.end,end) if end else b.end) for b in bookings)
    merged=[]
    for a,b in intervals:
        if b<=a:continue
        if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else:merged.append((a,b))
    return round(sum((b-a).total_seconds()/3600 for a,b in merged),4)

def scheduled_hours(bookings,events,start=None,end=None):
    from .workload import working_intervals,hours
    intervals=[]
    for b in bookings:
        ev=events.get(b.event_id)
        if not ev or ev.status=='Cancelled' or b.state!='reserved':continue
        for a,z in working_intervals(b,ev):
            a=max(a,start) if start else a;z=min(z,end) if end else z
            if z>a:intervals.append((a,z))
    return round(hours(intervals),4)

def build_context(s,question,now=None):
    clock,tz,theatre=theatre_clock(s,now)
    kind=intent(question)
    ps=list(s.scalars(select(Production).order_by(Production.id)))
    rs=list(s.scalars(select(Resource).order_by(Resource.id)))
    resources={r.id:r for r in rs}
    def person(rid):
        r=resources.get(rid)
        return {'id':rid,'name':r.name} if r and r.kind=='Person' else None
    selected,p_suggestions=resolve(question,ps)
    people,r_suggestions=resolve(question,[r for r in rs if r.kind=='Person'])
    venues,v_suggestions=resolve(question,[r for r in rs if r.kind in ('Venue','Room')])
    items,i_suggestions=resolve(question,[r for r in rs if r.kind not in ('Person','Venue','Room')])
    parsed_question=strip_entities(question,selected+people+venues+items)
    kind=intent(parsed_question)
    result={'as_of':clock.isoformat(),'timezone':tz,'theatre':theatre,'intent':kind,'clarification':[],
            'missing':[],'productions':[],'people':[],'venues':[],'resources':[],'events':[],
            'compatibility':[],'analytics':{}}
    start,end,bounded=period(parsed_question,clock)
    result['scope']={'start':start.isoformat() if start else None,'end_exclusive':end.isoformat() if end else None,
                     'period_explicit':bounded,'cancelled_excluded':True,'event_limit':MAX_EVENTS,
                     'complete':True,'matched_events':0}
    for label,rows in [('production',selected),('person',people),('venue',venues),('resource',items)]:
        if len(rows)>1:result['clarification'].append({'type':label,'options':[{'id':r.id,'name':r.name} for r in rows]})
    if result['clarification']:return result
    quoted=re.findall(r'[«"]([^»"]+)[»"]',question)
    known=[norm(r.name) for r in selected+people+venues+items]
    for label in quoted:
        if not any(norm(label) in name or name in norm(label) for name in known):
            result['clarification'].append({'type':'unknown_name','options':[label]})
    if any(x in norm(question) for x in ['сотрудник','employee']) and not people:
        result['clarification'].append({'type':'person','options':r_suggestions})
    suggestions=p_suggestions+r_suggestions+v_suggestions+i_suggestions
    if kind in ('productions','casts','compatibility') and not selected:
        result['clarification'].append({'type':'production','options':p_suggestions or [p.name for p in ps]})
    if kind=='people' and not people:result['clarification'].append({'type':'person','options':r_suggestions})
    if kind=='compatibility' and not venues:
        result['clarification'].append({'type':'venue','options':v_suggestions or [r.name for r in rs if r.kind=='Venue']})
    if suggestions and not (selected or people or venues or items):
        result['clarification'].append({'type':'possible_spelling','options':suggestions})
    if kind=='unknown':result['clarification'].append({'type':'question','options':['Укажите постановку, сотрудника, площадку или период / Specify production, employee, venue or dates']})
    if result['clarification']:return result
    for p in selected:
        d=p.data if isinstance(p.data,dict) else {}
        result['productions'].append({'id':p.id,'name':p.name,'version':p.version,'duration_minutes':d.get('duration'),
            'permanent_responsibles':{dept:person(rid) for dept,rid in (d.get('responsibles') or {}).items()},
            'groups':{dept:[person(rid) for rid in (ids or [])] for dept,ids in (d.get('groups') or {}).items()},
            'crew':{dept:[person(rid) for rid in (ids or [])] for dept,ids in (d.get('crew') or {}).items()},
            'roles':[{'index':i,'role':r.get('role'),'cast_A':person(r.get('A')),'cast_B':person(r.get('B')),
                      'eligible':[person(rid) for rid in (r.get('eligible') or [])],
                      'collective':any(x in norm(r.get('role','')) for x in ['солисты','семейная пара','принимают участие'])}
                     for i,r in enumerate(d.get('roles') or []) if isinstance(r,dict)],
            'requirements':d.get('requirements'),'notes':{k:v for k,v in d.items() if k.endswith('_notes') and v}})
    all_events=list(s.scalars(select(Event).where(Event.status!='Cancelled').order_by(Event.start,Event.id)))
    active_ids={e.id for e in all_events}
    event_map={e.id:e for e in all_events}
    bookings=[b for b in s.scalars(select(Booking).order_by(Booking.start,Booking.id)) if b.event_id is None or b.event_id in active_ids]
    if start:bookings=[b for b in bookings if b.start<end and b.end>start]
    person_ids={r.id for r in people};venue_ids={r.id for r in venues};item_ids={r.id for r in items}
    events=[]
    for ev in all_events:
        data=ev.data if isinstance(ev.data,dict) else {};plan=data.get('plan') or {}
        if selected and ev.production_id!=selected[0].id:continue
        if venue_ids and ev.venue_id not in venue_ids:continue
        bs=[b for b in bookings if b.event_id==ev.id]
        tasks=list(s.scalars(select(Task).where(Task.event_id==ev.id).order_by(Task.start,Task.id)))
        starts=[ev.start]+[b.start for b in bs]+[t.start for t in tasks]
        ends=[ev.end]+[b.end for b in bs]+[t.end for t in tasks]
        if start and not (min(starts)<end and max(ends)>start):continue
        actual_ids={a.get('actual_id') for a in plan.get('assignments',[]) if isinstance(a,dict)}
        actual_participation=bool(actual_ids & person_ids)
        if start and actual_participation:
            actual_participation=False
            for assignment in plan.get('assignments',[]):
                if assignment.get('actual_id') not in person_ids:continue
                call=assignment.get('call')
                try:a=datetime.fromisoformat(call) if call else ev.start
                except (ValueError,TypeError):a=ev.start
                if a<end and ev.end>start:actual_participation=True
        if person_ids and not (actual_participation or any(b.resource_id in person_ids for b in bs)):continue
        if item_ids and not any(b.resource_id in item_ids for b in bs):continue
        v=resources.get(ev.venue_id)
        row={'id':ev.id,'title':ev.title,'production_id':ev.production_id,'kind':ev.kind,'status':ev.status,
             'start':ev.start.isoformat(),'end':ev.end.isoformat(),'venue':{'id':ev.venue_id,'name':v.name if v else None},
             'assignments':[{k:a.get(k) for k in ['role','department','actual_id','actual','responsible_id','responsible','call']}
                            for a in plan.get('assignments',[]) if isinstance(a,dict)],
             'tasks':[{'name':t.name,'department':t.department,'start':t.start.isoformat(),'end':t.end.isoformat(),
                       'actual_start':t.actual_start.isoformat() if t.actual_start else None,
                       'actual_end':t.actual_end.isoformat() if t.actual_end else None} for t in tasks],
             'conflicts':[],'check_error':None}
        if kind=='conflicts':
            from .engine import saved_event_plan
            try:row['conflicts']=saved_event_plan(s,ev)['conflicts']
            except (KeyError,ValueError,TypeError,AttributeError) as error:
                row['check_error']=type(error).__name__+': '+str(error)
                result['missing'].append('Не удалось проверить сохранённый план события '+str(ev.id))
        events.append(row)
    result['scope']['matched_events']=len(events);result['scope']['complete']=len(events)<=MAX_EVENTS
    result['events']=events[:MAX_EVENTS]
    def booking_rows(r):
        return [{'event_id':b.event_id,'start':b.start.isoformat(),'end':b.end.isoformat(),'label':b.label,'state':b.state}
                for b in bookings if b.resource_id==r.id]
    for r in people:
        result['people'].append({'id':r.id,'name':r.name,'department':r.department,'status':r.status,
            'bookings':booking_rows(r),'booked_hours':scheduled_hours([b for b in bookings if b.resource_id==r.id],event_map,start,end)})
    for r in venues:
        result['venues'].append({'id':r.id,'name':r.name,'kind':r.kind,'status':r.status,'characteristics':r.data or {},'bookings':booking_rows(r)})
    inventory=items
    if kind=='resources' and not inventory and not selected:inventory=[r for r in rs if r.kind not in ('Person','Venue','Room')]
    if kind=='resources' and selected:
        d=selected[0].data or {};ids=set(d.get('items',[])+d.get('scenery',[])+d.get('props',[])+d.get('equipment_kits',[]))
        if d.get('vehicle'):ids.add(d['vehicle'])
        inventory=[resources[rid] for rid in ids if rid in resources]
    result['resources']=[{'id':r.id,'name':r.name,'kind':r.kind,'status':r.status,'properties':r.data or {},'bookings':booking_rows(r)} for r in inventory]
    if kind=='compatibility':
        from .engine import compatibility
        try:result['compatibility'].append({'production':selected[0].name,'venue':venues[0].name,'result':compatibility(s,selected[0],venues[0])})
        except (KeyError,ValueError,TypeError,AttributeError) as error:result['missing'].append('Совместимость не вычислена: '+type(error).__name__+': '+str(error))
    if kind=='analytics':
        candidates=people or [r for r in rs if r.kind=='Person' and r.department and norm(r.department) in norm(question)]
        if not candidates:result['clarification'].append({'type':'person_or_department','options':r_suggestions})
        per_person=[{'id':r.id,'name':r.name,'department':r.department,'booked_hours':scheduled_hours([b for b in bookings if b.resource_id==r.id],event_map,start,end)} for r in candidates]
        result['analytics']={'people':per_person,'person_hours':round(sum(x['booked_hours'] for x in per_person),4),
                             'basis':'scheduled event reservations; union per person excluding lunch; not actual worked time','complete_bookings':True}
    if not events and kind in ('events','conflicts','preparation'):
        result['missing'].append('В указанной выборке нет неотменённых событий / No non-cancelled events in this scope')
    return result

def render_answer(context,question,language='ru'):
    en=language=='en';c=context;k=c['intent'];q=norm(question)
    def label(ru,eng):return eng if en else ru
    def named(p):return (p['name']+' [#'+str(p['id'])+']') if p else label('не назначен / нет сведений','unassigned / unknown')
    def show_bookings(rows):
        return '\n'.join(f"{b['start']} — {b['end']}: {b['label']} ({b['state']})" for b in rows) or label('Бронирований нет.','No bookings.')
    if c['clarification']:
        options=[]
        for x in c['clarification']:
            options.extend(named(v) if isinstance(v,dict) else str(v) for v in x['options'])
        return label('Уточните название или вопрос. Возможные варианты: ','Please clarify the name or question. Possible matches: ')+('; '.join(options) or label('укажите полное имя или название','specify a full name or title'))
    lines=[label('Театр: ','Theatre: ')+c['theatre'],label('Часовой пояс: ','Timezone: ')+c['timezone']]
    if k in ('events','conflicts','preparation','analytics','people','venues','resources'):
        sc=c['scope'];lines.append(label('Период: ','Scope: ')+(f"[{sc['start']}, {sc['end_exclusive']})" if sc['start'] else label('весь сохранённый архив','entire stored archive')))
        lines.append(label('Неотменённых событий: ','Non-cancelled events: ')+str(sc['matched_events']))
        if not sc['complete']:lines.append(label('НЕПОЛНЫЙ РЕЗУЛЬТАТ: первые ','PARTIAL: first ')+str(sc['event_limit']))
    for p in c['productions'] if k in ('productions','casts') else []:
        lines.append(p['name'])
        if k=='productions':
            if any(x in q for x in ['продолжитель','длится','duration','long']):
                lines.append(label('Продолжительность по паспорту, мин: ','Passport duration, min: ')+str(p['duration_minutes'] if p['duration_minutes'] is not None else label('не указана','unknown')))
            else:
                lines.append(label('Постоянные ответственные (не назначения события):','Permanent responsibles (not event assignments):'))
                for dept,who in p['permanent_responsibles'].items():lines.append(dept+': '+named(who))
                if any(x in q for x in ['режиссер','director']) and not any(norm(d)=='режиссер' for d in p['permanent_responsibles']):
                    lines.append(label('В поле ответственного режиссёр не назначен. Титры паспорта приведены ниже; они не подтверждают работу на конкретном показе.','No responsible director assigned. Passport credits below do not confirm an event assignment.'))
                for key,note in p['notes'].items():lines.append(str(note).replace('\\n','\n'))
                if any(x in q for x in ['команд','team']):
                    for dept,members in {**p['groups'],**p['crew']}.items():lines.append(dept+': '+(', '.join(named(x) for x in members) or label('не заполнено','not filled')))
        else:
            lines.append(label('Допуск не является утверждённым составом.','Eligibility is not an approved cast.'))
            for r in p['roles']:
                lines.append(f"{r['role']}: A — {named(r['cast_A'])}; B — {named(r['cast_B'])}")
                lines.append(label('Допущены: ','Eligible: ')+(', '.join(named(x) for x in r['eligible']) or label('нет сведений','unknown')))
                if r['collective']:lines.append(label('Коллективная запись; не индивидуальная роль.','Collective entry; not an individual role.'))
    for p in c['people']:
        lines.append(f"{p['name']} [#{p['id']}]: {p['department']}; {p['status']}")
        lines.append(show_bookings(p['bookings']))
    for v in c['venues'] if k=='venues' else []:
        lines.append(f"{v['name']} [#{v['id']}]: {v['status']}")
        for key,value in v['characteristics'].items():lines.append(f"{key}: {value}")
        lines.append(show_bookings(v['bookings']))
    for r in c['resources']:
        lines.append(f"{r['name']} [#{r['id']}]: {r['kind']}; {r['status']}")
        for key,value in r['properties'].items():lines.append(f"{key}: {value}")
        lines.append(show_bookings(r['bookings']))
    for ev in c['events'] if k in ('events','conflicts','preparation','venues','people') else []:
        lines.append(f"#{ev['id']} {ev['title']} {ev['start']} — {ev['end']} / {ev['venue']['name']}")
        if k=='conflicts':
            if ev['check_error']:lines.append(label('Проверка недоступна: ','Check unavailable: ')+ev['check_error'])
            for issue in ev['conflicts']:lines.append(str(issue.get('resource',''))+': '+str(issue.get('reason',''))+'; '+str(issue.get('solutions',[])))
            if not ev['conflicts'] and not ev['check_error']:lines.append(label('Движок не выявил конфликтов в этом событии.','Engine found no conflicts in this event.'))
        elif k=='preparation':
            for task in ev['tasks']:lines.append(f"{task['name']} / {task['department']}: {task['start']} — {task['end']}")
            if not ev['tasks']:lines.append(label('Этапы подготовки не заполнены.','Preparation tasks not filled.'))
        elif any(x in q for x in ['фактич','замен','вызов','кто','actual','replacement','call','who','участ','particip']):
            for a in ev['assignments']:
                lines.append(f"{a['role']} / {a['department']}: "+label('фактически ','actual ')+str(a['actual'])+f" [#{a['actual_id']}]"+label('; постоянный ответственный ','; permanent responsible ')+str(a['responsible'])+label('; вызов ','; call ')+str(a['call']))
            if not ev['assignments']:lines.append(label('Фактические назначения не заполнены.','Actual assignments not filled.'))
    if k=='compatibility':
        for item in c['compatibility']:
            result=item['result'];lines.append(item['production']+' / '+item['venue']+': '+result['version'])
            lines.append(label('Расчёт по записанным требованиям. Нулевые значения или пустой паспорт не подтверждают фактическую совместимость.','Calculated from stored requirements. Zero requirements or an incomplete passport do not confirm real compatibility.'))
            for check in result['checks']:lines.append(f"{check['name']}: "+label('требуется ','required ')+str(check['required'])+label(', доступно ',', available ')+str(check['available']))
            for issue in result['conflicts']:lines.append(str(issue.get('resource',''))+': '+str(issue.get('reason','')))
    if k=='analytics':
        for p in c['analytics'].get('people',[]):lines.append(p['name']+': '+str(p['booked_hours'])+label(' часов бронирования',' booked hours'))
        lines.append(label('Сумма человеко-часов: ','Total person-hours: ')+str(c['analytics'].get('person_hours',0)))
        lines.append(label('Плановые рабочие бронирования событий; пересечения объединены по человеку, обед исключён. Это не фактически отработанное время.','Planned event work; union per person excluding lunch. Not actual worked time.'))
    lines.extend(c['missing'])
    if c['people'] or k=='analytics':lines.append(label('Отсутствие бронирований не доказывает свободу или фактически отработанные часы.','No bookings does not prove availability or actual worked hours.'))
    answer='\n'.join(lines)
    if len(answer)>MAX_ANSWER:answer=answer[:MAX_ANSWER]+label('\n[Ответ сокращён; уточните период или объект]','\n[Answer truncated; narrow scope]')
    return answer
