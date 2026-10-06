"""Personal read-only mobile access, isolated from desktop sessions and APIs."""
import hashlib
import time
from datetime import datetime, timedelta
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from .models import Resource, Booking, Event

COOKIE = 'stageos_mobile_session'
PATHS = {'/api/mobile/login','/api/mobile/logout','/api/mobile/session','/api/mobile/schedule'}


def current_mobile(registry, req):
    key = hashlib.sha256(req.cookies.get(COOKIE,'').encode()).hexdigest()
    entry = registry.sessions.get(key)
    if not entry or entry.get('kind')!='mobile' or entry['expires']<time.time():
        raise HTTPException(401,'Войдите в личное расписание')
    with registry.db() as db:
        user = db.execute('SELECT * FROM users WHERE id=? AND active=1',(entry['user_id'],)).fetchone()
    if not user:
        registry.sessions.pop(key,None)
        raise HTTPException(401,'Аккаунт отключён')
    return dict(user)


def employee(session, user):
    from .workspaces import normalized
    names = {normalized(user['login']), normalized(user['name'])}
    matches = [r for r in session.scalars(select(Resource).where(Resource.kind=='Person')) if normalized(r.name) in names]
    if len(matches)!=1:
        return None, 'Сотрудник не найден. Обратитесь к администратору для связи аккаунта с сотрудником.' if not matches else 'Найдено несколько сотрудников с этим именем. Администратору нужно уточнить связь аккаунта.'
    return matches[0], None


class MobileLogin(BaseModel):
    model_config = ConfigDict(extra='forbid')
    login: str = Field(min_length=1,max_length=120)
    password: str = Field(min_length=1,max_length=256)


def install_mobile_routes(app, registry):
    @app.post('/api/mobile/login')
    def login(body: MobileLogin, req: Request):
        from .workspaces import normalized, LoginBody, password_matches
        name = normalized(body.login)
        with registry.db() as db:
            users = db.execute('SELECT theatre_id FROM users WHERE login=? AND active=1',(name,)).fetchall()
        if len(users)!=1:
            # Do not reveal account or theatre lists through the public mobile entry.
            now=time.time();key=('mobile',name)
            with registry.lock:
                attempts=[t for t in registry.attempts.get(key,[]) if t>now-60]
                if len(attempts)>=5:raise HTTPException(429,'Слишком много попыток. Повторите через минуту')
                password_matches(body.password,registry.dummy_hash)
                registry.attempts[key]=attempts+[now]
            raise HTTPException(401,'Неверный логин или пароль. Логин должен быть уникальным на сервере.')
        response=registry.authenticate(LoginBody(theatre_id=users[0]['theatre_id'],**body.model_dump()),req,cookie=COOKIE,kind='mobile')
        return response

    @app.post('/api/mobile/logout')
    def logout(req: Request):
        try:
            user=current_mobile(registry,req)
            with registry.db() as db:registry.audit(db,user['id'],user['theatre_id'],'Выход из аккаунта','Мобильный браузер')
        except HTTPException:pass
        registry.sessions.pop(hashlib.sha256(req.cookies.get(COOKIE,'').encode()).hexdigest(),None)
        response=JSONResponse({'ok':True});response.delete_cookie(COOKIE,path='/api');return response

    @app.get('/api/mobile/session')
    def session(req: Request):
        user=current_mobile(registry,req)
        with registry.tenant(user['theatre_id']).state.Session() as s:
            person,error=employee(s,user)
            return {'name':user['name'],'login':user['login'],'theatre':registry.theatre(user['theatre_id'])['name'],
                    'employee':{'id':person.id,'name':person.name} if person else None,'link_error':error}

    @app.get('/api/mobile/schedule')
    def schedule(req: Request, start: str):
        user=current_mobile(registry,req)
        try:lower=datetime.strptime(start,'%Y-%m-%d')
        except ValueError:raise HTTPException(422,'Укажите дату недели в формате ГГГГ-ММ-ДД')
        lower -= timedelta(days=lower.weekday());upper=lower+timedelta(days=7)
        with registry.tenant(user['theatre_id']).state.Session() as s:
            person,error=employee(s,user)
            if not person:return {'employee':None,'link_error':error,'start':lower.date().isoformat(),'end':upper.date().isoformat(),'items':[]}
            rows=s.scalars(select(Booking).where(Booking.resource_id==person.id,Booking.start<upper,Booking.end>lower).order_by(Booking.start)).all()
            items=[]
            for booking in rows:
                event=s.get(Event,booking.event_id) if booking.event_id else None
                if event and event.status=='Cancelled':continue
                venue=s.get(Resource,event.venue_id) if event else None
                roles=sorted({a['role'] for a in event.data.get('plan',{}).get('assignments',[]) if a.get('actual_id')==person.id and a.get('role')}) if event else []
                items.append({'id':booking.id,'event_id':event.id if event else None,'title':event.title if event else booking.label,
                              'kind':event.kind if event else booking.state,'status':event.status if event else booking.state,
                              'start':booking.start.isoformat(),'end':booking.end.isoformat(),
                              'event_start':event.start.isoformat() if event else None,'event_end':event.end.isoformat() if event else None,
                              'venue':venue.name if venue else '', 'role':', '.join(roles)})
            return {'employee':{'id':person.id,'name':person.name},'link_error':None,'start':lower.date().isoformat(),'end':upper.date().isoformat(),'items':items}
