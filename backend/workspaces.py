"""Local account registry and isolated theatre applications; no shared tenant Session."""
from pathlib import Path
import os, sys, sqlite3, json, secrets, hashlib, hmac, time, threading
from contextlib import contextmanager
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select
from .models import make_engine, Setting, Resource, Production
from .app import create_app

ROLES={'admin':'Администратор','artistic_director':'Художественный руководитель','editor':'Планировщик','viewer':'Наблюдатель'}
DECISION_ROLES={'admin','artistic_director'}
COOKIE='stageos_session'
ITERATIONS=600000

def password_hash(password):
    salt=secrets.token_hex(16)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),ITERATIONS).hex()
    return f'pbkdf2_sha256${ITERATIONS}${salt}${digest}'

def password_matches(password, encoded):
    try:
        method,n,salt,want=encoded.split('$')
        if method!='pbkdf2_sha256' or not 100000<=int(n)<=1000000:return False
        actual=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),int(n)).hex()
        return hmac.compare_digest(actual,want)
    except (ValueError,TypeError):return False

def normalized(value):return ' '.join(value.strip().casefold().split())

class AccountBody(BaseModel):
    name:str=Field(min_length=2,max_length=120)
    login:str=Field(min_length=2,max_length=120)
    password:str=Field(min_length=6,max_length=256)
    role:str='admin'

class TheatreBody(AccountBody):
    theatre_name:str=Field(min_length=2,max_length=200)

class LoginBody(BaseModel):
    theatre_id:str=Field(min_length=1,max_length=64)
    login:str=Field(min_length=1,max_length=120)
    password:str=Field(min_length=1,max_length=256)

class Registry:
    def __init__(self,home,static_dir=None,bootstrap_file=None):
        self.home=Path(home);self.home.mkdir(parents=True,exist_ok=True)
        self.path=self.home/'accounts.sqlite';self.lock=threading.RLock();self.apps={};self.mutation_locks={};self.revisions={};self.sessions={};self.attempts={};self.static_dir=static_dir;self.dummy_hash=password_hash(secrets.token_urlsafe(32))
        with self.db() as d:
            d.executescript('''CREATE TABLE IF NOT EXISTS theatres(id TEXT PRIMARY KEY,name TEXT NOT NULL,path TEXT NOT NULL UNIQUE);
            CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,theatre_id TEXT NOT NULL REFERENCES theatres(id),name TEXT NOT NULL,login TEXT NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,UNIQUE(theatre_id,login));
            CREATE TABLE IF NOT EXISTS account_audit(id INTEGER PRIMARY KEY,created TEXT,actor TEXT,theatre_id TEXT,action TEXT);''')
        # Adopt the existing data file without copying, resetting or seeding its content.
        with self.db() as d:empty=not d.execute('SELECT 1 FROM theatres LIMIT 1').fetchone()
        if empty:
            legacy_path=self.home/'stageos.db'
            choice=self.home/'database-choice.json'
            if choice.is_file():
                try:
                    chosen=Path(json.loads(choice.read_text(encoding='utf-8'))['path'])
                    if chosen.is_file():legacy_path=chosen
                except (ValueError,KeyError,OSError):pass
            engine=make_engine(os.environ.get('STAGEOS_DATABASE_URL','sqlite:///'+str(legacy_path.resolve())));legacy=create_app(engine,static_dir=static_dir,demo_enabled=False)
            with legacy.state.Session() as s:
                setting=s.get(Setting,'theatre');exists=setting or s.scalar(select(Production.id).limit(1))
                name=setting.value.get('name','Рабочий театр') if setting else 'Рабочий театр'
            if exists:
                tid=secrets.token_hex(16)
                with self.db() as d:d.execute('INSERT INTO theatres VALUES(?,?,?)',(tid,name,str(Path(engine.url.database).resolve())))
                self.apps[tid]=legacy
            else:engine.dispose()
        if bootstrap_file and Path(bootstrap_file).is_file():self.bootstrap(Path(bootstrap_file))

    def close(self):
        """Release SQLite handles after the HTTP listeners have stopped."""
        with self.lock:
            for app in self.apps.values():app.state.Session.kw['bind'].dispose()
            self.apps.clear();self.sessions.clear()

    @contextmanager
    def db(self):
        d=sqlite3.connect(self.path,timeout=30);d.row_factory=sqlite3.Row;d.execute('PRAGMA foreign_keys=ON')
        try:
            with d:yield d
        finally:d.close()

    def audit(self,d,actor,tid,action):d.execute('INSERT INTO account_audit(created,actor,theatre_id,action) VALUES(?,?,?,?)',(datetime.now().isoformat(),actor,tid,action))

    def bootstrap(self,path):
        # Private provisioning file contains salted hashes, never published default credentials.
        payload=json.loads(path.read_text(encoding='utf-8'))
        users=payload.get('users',[])
        if len(users)!=3:raise ValueError('Файл настройки должен содержать трёх администраторов')
        for u in users:
            if not u.get('name','').strip() or not u.get('login','').strip() or u.get('role')!='admin':raise ValueError('Неверный файл настройки учётных записей')
            parts=u.get('password_hash','').split('$')
            if len(parts)!=4 or parts[0]!='pbkdf2_sha256' or int(parts[1])!=ITERATIONS or len(bytes.fromhex(parts[2]))!=16 or len(bytes.fromhex(parts[3]))!=32:raise ValueError('Неверный формат хеша пароля')
        with self.lock,self.db() as d:
            rows=d.execute('SELECT id FROM theatres WHERE NOT EXISTS(SELECT 1 FROM users WHERE users.theatre_id=theatres.id)').fetchall()
            for row in rows:
                for u in users:d.execute('INSERT INTO users VALUES(?,?,?,?,?,?,1)',(secrets.token_hex(16),row['id'],u['name'].strip(),normalized(u['login']),u['password_hash'],'admin'))
                self.audit(d,'initial-setup',row['id'],'Созданы администраторы из локального файла настройки')

    def theatre(self,tid):
        with self.db() as d:row=d.execute('SELECT * FROM theatres WHERE id=?',(tid,)).fetchone()
        if not row:raise HTTPException(404,'Театр не найден')
        return dict(row)

    def tenant(self,tid):
        with self.lock:
            if tid not in self.apps:self.apps[tid]=create_app(make_engine('sqlite:///'+self.theatre(tid)['path']),static_dir=self.static_dir,demo_enabled=False)
            return self.apps[tid]

    def current(self,req):
        token=req.cookies.get(COOKIE,'');key=hashlib.sha256(token.encode()).hexdigest()
        entry=self.sessions.get(key)
        if not entry or entry['expires']<time.time() or entry.get('kind','desktop')!='desktop':raise HTTPException(401,'Войдите в аккаунт театра')
        with self.db() as d:u=d.execute('SELECT * FROM users WHERE id=? AND active=1',(entry['user_id'],)).fetchone()
        if not u:self.sessions.pop(key,None);raise HTTPException(401,'Аккаунт отключён')
        return dict(u)

    def public_user(self,u):return {k:u[k] for k in ['id','name','login','role','active']}

    def add_user(self,d,tid,body):
        if body.role not in ROLES or not normalized(body.login) or not body.name.strip():raise HTTPException(422,'Укажите имя, логин и допустимую роль')
        try:d.execute('INSERT INTO users VALUES(?,?,?,?,?,?,1)',(secrets.token_hex(16),tid,body.name.strip(),normalized(body.login),password_hash(body.password),body.role))
        except sqlite3.IntegrityError:raise HTTPException(409,'Этот логин уже используется в театре')

    def authenticate(self,body,req,cookie=COOKIE,kind='desktop'):
        self.theatre(body.theatre_id);key=(body.theatre_id,normalized(body.login));now=time.time()
        with self.lock:
            attempts=self.attempts.get(key,[]);attempts=[x for x in attempts if x>now-60]
            if len(attempts)>=5:raise HTTPException(429,'Слишком много попыток. Повторите через минуту')
            with self.db() as d:u=d.execute('SELECT * FROM users WHERE theatre_id=? AND login=? AND active=1',key).fetchone()
            encoded=u['password'] if u else self.dummy_hash
            if not password_matches(body.password,encoded):self.attempts[key]=attempts+[now];raise HTTPException(401,'Неверный логин или пароль')
            self.attempts.pop(key,None)
            # A successful account switch replaces this browser's old session only.
            previous=req.cookies.get(cookie,'')
            if previous:self.sessions.pop(hashlib.sha256(previous.encode()).hexdigest(),None)
            token=secrets.token_urlsafe(32);self.sessions[hashlib.sha256(token.encode()).hexdigest()]={'user_id':u['id'],'expires':now+12*3600,'kind':kind}
            with self.db() as d:self.audit(d,u['id'],body.theatre_id,'Вход в аккаунт')
        result=JSONResponse({'user':self.public_user(u),'theatre':{'id':body.theatre_id,'name':self.theatre(body.theatre_id)['name']}})
        result.set_cookie(cookie,token,httponly=True,samesite='strict',path='/api');return result


class TenantDispatch:
    def __init__(self,app,registry):self.app=app;self.r=registry
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        req=Request(scope,receive=receive);path=req.url.path
        if not path.startswith('/api'):return await self.app(scope,receive,send)
        token=os.environ.get('STAGEOS_TOKEN','')
        if token and not secrets.compare_digest(req.headers.get('x-stageos-token',''),token):return await JSONResponse({'detail':'Доступ запрещён'},401)(scope,receive,send)
        origin=req.headers.get('origin')
        if origin and origin not in [str(req.base_url).rstrip('/'),'http://localhost:5173','http://127.0.0.1:5173']:
            return await JSONResponse({'detail':'Источник запроса запрещён'},403)(scope,receive,send)
        if path.startswith('/api/auth/') or path.startswith('/api/mobile/') or path=='/api/sync':return await self.app(scope,receive,send)
        try:
            u=self.r.current(req);method=req.method
            if u['role']!='admin' and (path.startswith('/api/database/') or path.startswith('/api/settings/llm') or path=='/api/diagnostics'):raise HTTPException(403,'Требуются права администратора')
            read_only={'/api/preview','/api/windows','/api/substitutions','/api/equipment-substitutions','/api/assistant','/api/suggestions','/api/suggestions/explain'}
            cast_proposal = path.startswith('/api/productions/') and path.endswith('/cast-proposal')
            if cast_proposal:
                read_only.add(path)
            if method not in ['GET','HEAD'] and path not in read_only and path!='/api/settings/interface':
                if u['role']=='viewer':raise HTTPException(403,'Доступ только для просмотра')
                if u['role']!='admin' and (path.startswith('/api/database/') or path.startswith('/api/settings/')):
                    raise HTTPException(403,'Требуются права администратора')
                if u['role'] not in DECISION_ROLES and (path.endswith('/approve') or path.endswith('/reject')):
                    raise HTTPException(403,'Согласование доступно администратору или художественному руководителю')
            # Editors cannot bypass conflicts; inspect body and replay it to tenant API.
            if method in ['POST','PATCH','PUT'] and u['role'] not in DECISION_ROLES:
                raw=await req.body()
                try:body=json.loads(raw or b'{}')
                except ValueError:body={}
                command=body.get('request',body) if isinstance(body,dict) else {}
                if isinstance(command,dict) and (command.get('force') or command.get('override_reason') or (path.endswith('/status') and command.get('status')=='Approved')):raise HTTPException(403,'Подтверждение конфликтов доступно администратору или художественному руководителю')
                sent=False
                async def replay():
                    nonlocal sent
                    if not sent:sent=True;return {'type':'http.request','body':raw,'more_body':False}
                    return await receive()
                downstream=replay
            else:downstream=receive
            status=0
            async def outgoing(message):
                nonlocal status
                if message['type']=='http.response.start':status=message['status']
                await send(message)
            scope.setdefault('state',{})['actor']={k:u[k] for k in ['id','name','login','role']}
            tenant=self.r.tenant(u['theatre_id'])
            # Serialize writes across LAN and local host event loops. Recompute preview
            # and commit inside the same critical section; stale versions still fail.
            if method in ['POST','PUT','PATCH','DELETE'] and not cast_proposal:
                import anyio
                with self.r.lock:mutation=self.r.mutation_locks.setdefault(u['theatre_id'],threading.Lock())
                await anyio.to_thread.run_sync(mutation.acquire)
                try:
                    await tenant(scope,downstream,outgoing)
                    if 200<=status<300 and path not in read_only:
                        with self.r.lock:self.r.revisions[u['theatre_id']]=self.r.revisions.get(u['theatre_id'],0)+1
                finally:mutation.release()
            else:await tenant(scope,downstream,outgoing)
            if path=='/api/database/import' and status==200:
                with self.r.lock,self.r.db() as d,tenant.state.Session() as s:
                    database=str(Path(s.bind.url.database).resolve());d.execute('UPDATE theatres SET path=? WHERE id=?',(database,u['theatre_id']))
                    self.r.audit(d,u['id'],u['theatre_id'],'Импортирована база театра')
        except HTTPException as e:await JSONResponse({'detail':e.detail},e.status_code)(scope,receive,send)


def create_workspace_app(home=None,static_dir=None,bootstrap_file=None):
    home=Path(home or os.environ.get('STAGEOS_HOME',Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/share'))/'StageOS-Work'))
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent.parent))
    if bootstrap_file is None:bootstrap_file=home/'bootstrap-accounts.json'
    r=Registry(home,static_dir,bootstrap_file);app=FastAPI(title='StageOS Accounts',docs_url=None,redoc_url=None,openapi_url=None);app.state.registry=r
    app.add_middleware(TenantDispatch,registry=r)
    from .mobile import install_mobile_routes
    install_mobile_routes(app,r)

    @app.exception_handler(ValueError)
    async def invalid(_,error):
        return JSONResponse({'detail':'Проверьте поля формы'},422)

    @app.get('/api/auth/theatres')
    def theatres():
        with r.db() as d:return {'enabled':True,'theatres':[{'id':x['id'],'name':x['name'],'needs_setup':not x['users']} for x in d.execute('SELECT t.id,t.name,COUNT(u.id) users FROM theatres t LEFT JOIN users u ON u.theatre_id=t.id GROUP BY t.id ORDER BY t.name')]}

    @app.get('/api/sync')
    def sync(req:Request):
        u=r.current(req)
        return {'revision':r.revisions.get(u['theatre_id'],0)}

    @app.get('/api/auth/session')
    def session(req:Request):
        u=r.current(req);return {'user':r.public_user(u),'theatre':{'id':u['theatre_id'],'name':r.theatre(u['theatre_id'])['name']}}

    @app.post('/api/auth/theatres')
    def new_theatre(body:TheatreBody):
        if not body.theatre_name.strip():raise HTTPException(422,'Укажите название театра')
        tid=secrets.token_hex(16);folder=home/'theatres'/tid;folder.mkdir(parents=True);path=folder/'stageos.db'
        tenant=create_app(make_engine('sqlite:///'+str(path.resolve())),static_dir=static_dir,demo_enabled=False)
        with tenant.state.Session.begin() as s:s.add(Setting(key='theatre',value={'name':body.theatre_name.strip()}))
        try:
            with r.lock,r.db() as d:
                d.execute('INSERT INTO theatres VALUES(?,?,?)',(tid,body.theatre_name.strip(),str(path.resolve())))
                body.role='admin';r.add_user(d,tid,body);r.audit(d,'initial-setup',tid,'Создан театр и его администратор')
            r.apps[tid]=tenant
        except Exception:
            tenant.state.Session.kw['bind'].dispose()
            import shutil
            shutil.rmtree(folder,ignore_errors=True)
            raise
        return {'id':tid,'name':body.theatre_name.strip()}

    @app.post('/api/auth/theatres/{tid}/setup')
    def setup(tid:str,body:AccountBody):
        r.theatre(tid)
        with r.lock,r.db() as d:
            if d.execute('SELECT 1 FROM users WHERE theatre_id=?',(tid,)).fetchone():raise HTTPException(409,'Вход уже настроен; обратитесь к администратору')
            body.role='admin';r.add_user(d,tid,body);r.audit(d,'initial-setup',tid,'Настроен первый администратор')
        return {'ok':True}

    @app.post('/api/auth/login')
    def login(body:LoginBody,req:Request):
        return r.authenticate(body,req)

    @app.post('/api/auth/logout')
    def logout(req:Request):
        token=req.cookies.get(COOKIE,'');r.sessions.pop(hashlib.sha256(token.encode()).hexdigest(),None)
        response=JSONResponse({'ok':True});response.delete_cookie(COOKIE,path='/api');return response

    def admin(req):
        u=r.current(req)
        if u['role']!='admin':raise HTTPException(403,'Требуются права администратора')
        return u

    @app.get('/api/auth/users')
    def users(req:Request):
        u=admin(req)
        with r.db() as d:return [r.public_user(x) for x in d.execute('SELECT * FROM users WHERE theatre_id=? ORDER BY name',(u['theatre_id'],))]

    @app.post('/api/auth/users')
    def add_user(body:AccountBody,req:Request):
        u=admin(req)
        with r.lock,r.db() as d:r.add_user(d,u['theatre_id'],body);r.audit(d,u['id'],u['theatre_id'],'Добавлен пользователь '+normalized(body.login))
        return {'ok':True}

    @app.patch('/api/auth/users/{uid}')
    async def edit_user(uid:str,req:Request):
        u=admin(req);body=await req.json()
        if not isinstance(body,dict):raise HTTPException(422,'Ожидается объект учётной записи')
        if set(body)-{'role','active','password'}:raise HTTPException(422,'Неизвестные поля учётной записи')
        with r.lock,r.db() as d:
            target=d.execute('SELECT * FROM users WHERE id=? AND theatre_id=?',(uid,u['theatre_id'])).fetchone()
            if not target:raise HTTPException(404,'Пользователь не найден')
            role=body.get('role',target['role']);active=body.get('active',bool(target['active']))
            if not isinstance(role,str) or role not in ROLES or not isinstance(active,bool):raise HTTPException(422,'Неверная роль или состояние')
            if target['role']=='admin' and target['active'] and (role!='admin' or not active) and d.execute("SELECT COUNT(*) FROM users WHERE theatre_id=? AND role='admin' AND active=1",(u['theatre_id'],)).fetchone()[0]<=1:raise HTTPException(409,'Нельзя отключить последнего администратора')
            digest=target['password']
            if 'password' in body:
                pw=body['password']
                if not isinstance(pw,str) or not 6<=len(pw)<=256:raise HTTPException(422,'Пароль: от 6 до 256 символов')
                digest=password_hash(pw)
            d.execute('UPDATE users SET role=?,active=?,password=? WHERE id=?',(role,int(active),digest,uid));r.audit(d,u['id'],u['theatre_id'],'Изменены права или пароль пользователя '+target['login'])
            for key,entry in list(r.sessions.items()):
                if entry['user_id']==uid:r.sessions.pop(key,None)
        return {'ok':True}

    @app.post('/api/auth/password')
    async def change_password(req:Request):
        u=r.current(req);body=await req.json()
        if not isinstance(body,dict):raise HTTPException(422,'Ожидается объект учётной записи')
        old=body.get('current_password','');new=body.get('password','')
        if not isinstance(old,str) or not isinstance(new,str) or not 6<=len(new)<=256:raise HTTPException(422,'Пароль: от 6 до 256 символов')
        if not password_matches(old,u['password']):raise HTTPException(403,'Текущий пароль неверен')
        with r.lock,r.db() as d:d.execute('UPDATE users SET password=? WHERE id=?',(password_hash(new),u['id']));r.audit(d,u['id'],u['theatre_id'],'Изменён личный пароль')
        for key,entry in list(r.sessions.items()):
            if entry['user_id']==u['id']:r.sessions.pop(key,None)
        result=JSONResponse({'ok':True});result.delete_cookie(COOKIE,path='/api');return result

    static=Path(static_dir) if static_dir else root/'frontend'/'dist'
    if static.exists():
        app.mount('/assets',StaticFiles(directory=static/'assets'),name='assets')
        @app.get('/{path:path}')
        def index(path:str):
            if path.startswith('api'):raise HTTPException(404)
            return FileResponse(static/('stageos-icon.svg' if path=='stageos-icon.svg' else 'index.html'))
    return app
