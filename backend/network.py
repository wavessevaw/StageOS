"""Desktop connection gateway and a single database-owning LAN server.

Clients proxy API requests to the host; database files never leave the host
except through the explicit administrator export command.
"""
import base64
import hashlib
from collections import deque
from datetime import datetime, timezone
import json
import subprocess
import sys
import os
import secrets
import socket
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import anyio
import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from .workspaces import create_workspace_app
from .tunnel import TunnelController, HEADERS
from .mobile import PATHS as MOBILE_PATHS, current_mobile, COOKIE as MOBILE_COOKIE

PROTOCOL = 1

def validate_address(value):
    if not isinstance(value, str):
        raise ValueError('Укажите адрес сервера')
    value = value.strip().rstrip('/')
    if '://' not in value:
        value = 'http://' + value
    parts = urlsplit(value)
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password or parts.path or parts.query or parts.fragment:
        raise ValueError('Адрес: http://192.168.1.10:8765 или HTTPS-адрес сервера')
    try:
        if parts.port is not None and not 1 <= parts.port <= 65535:
            raise ValueError()
    except ValueError:
        raise ValueError('Неверный порт сервера')
    if parts.scheme=='http' and any(parts.hostname.lower().endswith(suffix) for suffix in ('.ngrok-free.dev','.ngrok-free.app','.ngrok.app','.ngrok.io')) and parts.port in (None,80,443):
        return 'https://' + parts.hostname
    return value

class LanAccess:
    def __init__(self, app, code, desktop_token, on_request=None, server_id='', tunnel=None, on_user=None):
        self.app, self.code, self.token = app, code, desktop_token
        self.on_request=on_request
        self.server_id, self.tunnel = server_id, tunnel
        self.on_user = on_user

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        req = Request(scope)
        if req.url.path == '/api/network/hello' and req.method == 'GET':
            return await JSONResponse({'product':'StageOS Server','version':'1.0.12','protocol':PROTOCOL,'server_id':self.server_id})(scope, receive, send)
        if req.url.path.startswith('/api'):
            if req.url.path.startswith('/api/connection'):
                return await JSONResponse({'detail':'Управление подключением доступно только на компьютере сервера'},403,headers={'X-StageOS-Web':'1'})(scope,receive,send)
            if req.url.path not in MOBILE_PATHS and not secrets.compare_digest(req.headers.get('x-stageos-code','').encode(), self.code.encode()):
                return await JSONResponse({'detail':'Неверный код подключения к серверу'},403,headers={'X-StageOS-Disconnected':'1'})(scope,receive,send)
            if req.url.path in ('/api/auth/theatres',) and req.method == 'POST' or req.url.path.endswith('/setup'):
                return await JSONResponse({'detail':'Создание театра и первый администратор доступны на компьютере сервера'},403)(scope,receive,send)
            if self.on_request:self.on_request(scope.get('client',('unknown',0))[0])
            if self.on_user:self.on_user(req)
            headers = [(k,v) for k,v in scope['headers'] if k.lower() != b'x-stageos-token']
            origin=req.headers.get('origin')
            public_url=self.tunnel.status()['url'] if self.tunnel else ''
            if origin and origin not in (str(req.base_url).rstrip('/'), public_url):
                return await JSONResponse({'detail':'Источник запроса запрещён'},403)(scope,receive,send)
            # ngrok rewrites Host to loopback; normalize only a validated external origin.
            headers = [(k,v) for k,v in headers if k.lower() != b'origin']
            if origin:headers.append((b'origin',str(req.base_url).rstrip('/').encode()))
            headers.append((b'x-stageos-token', self.token.encode()))
            scope = {**scope, 'headers': headers}
        return await self.app(scope, receive, send)

class NetworkController:
    def __init__(self, home, workspace):
        self.home = Path(home)
        self.workspace = workspace
        self.path = self.home/'connection.json'
        self.config = {'mode':'local','port':8765,'address':'','code':secrets.token_urlsafe(18)}
        if self.path.exists():
            self.config.update(json.loads(self.path.read_text(encoding='utf-8')))
        self.lock = threading.RLock()
        self.server = self.thread = self.listener = None
        self.error = ''
        self.phase='stopped'
        self.logs=deque(maxlen=80)
        self.log_lock=threading.Lock()
        self.diagnostics_lock=threading.Lock()
        self.diagnostics={'checked_at':None,'http_ok':None,'firewall':'unknown','profiles':[],'detail':''}
        self.firewall_state='unknown'
        self.remote_requests=0
        self.last_remote=None
        self.user_activity = {}
        self.server_id = secrets.token_hex(24)
        self.tunnel = TunnelController(self.home, self)
        if self.config['mode'] == 'server':
            try:self.start_server(self.config['port'])
            except (OSError,RuntimeError) as error:
                self.error = str(error);self.phase='error';self.record('error',self.error)

    def record(self,level,message):
        with self.log_lock:
            self.logs.append({'time':datetime.now(timezone.utc).isoformat(),'level':level,'message':message})

    def observe_request(self,address):
        with self.log_lock:
            first=self.last_remote is None
            self.remote_requests+=1
            self.last_remote={'address':address,'time':datetime.now(timezone.utc).isoformat()}
        if first:self.record('success','Получен первый сетевой запрос с верным кодом подключения')

    def observe_user(self,req):
        registry=self.workspace.state.registry
        cookie=MOBILE_COOKIE if req.url.path in MOBILE_PATHS else 'stageos_session'
        try:user=current_mobile(registry,req) if cookie==MOBILE_COOKIE else registry.current(req)
        except HTTPException:return
        key=hashlib.sha256(req.cookies.get(cookie,'').encode()).hexdigest()
        now=time.time()
        with self.log_lock:
            # Store only identifiers/timestamps, never passwords, cookies or session tokens.
            self.user_activity[key]={'user_id':user['id'],'seen':now}

    def active_users(self,theatre_id):
        registry=self.workspace.state.registry
        now=time.time()
        with self.log_lock:
            snapshot=list(self.user_activity.items())
        with registry.lock:
            sessions=dict(registry.sessions)
        valid={key:value for key,value in snapshot if now-value['seen']<=90
               and key in sessions and sessions[key]['expires']>=now}
        with self.log_lock:
            for key,value in snapshot:
                if key not in valid and self.user_activity.get(key)==value:self.user_activity.pop(key,None)
        grouped={}
        with registry.db() as db:
            for value in valid.values():
                user=db.execute('SELECT id,name,login,role FROM users WHERE id=? AND theatre_id=? AND active=1',
                                (value['user_id'],theatre_id)).fetchone()
                if not user:continue
                row=grouped.setdefault(user['id'],{**dict(user),'sessions':0,'seen':0})
                row['sessions']+=1;row['seen']=max(row['seen'],value['seen'])
        result=[]
        for row in grouped.values():
            seen=row.pop('seen')
            result.append({**row,'last_seen':datetime.fromtimestamp(seen,timezone.utc).isoformat()})
        return sorted(result,key=lambda row:(row['name'].casefold(),row['login']))

    def inspect(self):
        with self.diagnostics_lock:
            port=self.config['port']
            result={'checked_at':datetime.now(timezone.utc).isoformat(),'http_ok':False,
                    'firewall':'unknown','profiles':[],'detail':''}
            if self.status()['running']:
                try:
                    response=httpx.get(f'http://127.0.0.1:{port}/api/network/hello',timeout=3,trust_env=False)
                    result['http_ok']=response.status_code==200 and response.json().get('product')=='StageOS Server'
                except (httpx.HTTPError,ValueError):pass
            if os.name=='nt':
                try:result.update(inspect_windows_network(port))
                except (OSError,subprocess.TimeoutExpired,ValueError) as error:
                    result['detail']='Не удалось проверить настройки сети Windows'
            else:result['detail']='Проверка брандмауэра доступна только в Windows'
            self.diagnostics=result
            self.record('success' if result['http_ok'] else 'warning',
                        'Проверка HTTP: сервер отвечает' if result['http_ok'] else 'Проверка HTTP: сервер не отвечает')
            return result

    def set_mode(self,mode,**values):
        with self.lock:
            if mode=='server':return self.start_server(values['port'])
            self.stop_server();self.config.update(mode=mode,**values);self.error='';self.persist()

    def persist(self):
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.config,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(tmp,self.path)

    def status(self):
        addresses = {'127.0.0.1'}
        try:addresses.update(socket.gethostbyname_ex(socket.gethostname())[2])
        except OSError:pass
        with self.log_lock:logs=list(self.logs);last_remote=self.last_remote;requests=self.remote_requests
        server,thread=self.server,self.thread
        return {**self.config,'tunnel':self.tunnel.status(),'phase':self.phase,'diagnostics':self.diagnostics,'firewall_state':self.firewall_state,'logs':logs,'last_remote':last_remote,'remote_requests':requests,'windows':os.name=='nt','enabled':True,'running':bool(server and thread and server.started and thread.is_alive()),'addresses':[f'http://{a}:{self.config["port"]}' for a in sorted(addresses)],'error':self.error}

    def start_server(self, port):
        if isinstance(port,bool) or not isinstance(port,int) or not 1024 <= port <= 65535:
            raise ValueError('Порт сервера: от 1024 до 65535')
        if self.config['mode']=='server' and self.config['port']==port and self.status()['running']:
            self.record('info','Сервер уже работает. Повторный запуск не требуется')
            return
        self.stop_server()
        self.phase='starting';self.record('info',f'Запуск сервера: порт {port}')
        self.diagnostics={'checked_at':None,'http_ok':None,'firewall':'unknown','profiles':[],'detail':''}
        listener = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        try:listener.bind(('0.0.0.0',port))
        except Exception as error:
            listener.close();self.phase='error';self.error=str(error);self.record('error',self.error);raise
        old_code=self.config['code']
        if self.config['mode']!='server':self.config['code']=secrets.token_urlsafe(18)
        self.server_id = secrets.token_hex(24)
        app = LanAccess(self.workspace,self.config['code'],os.environ.get('STAGEOS_TOKEN',''),self.observe_request,self.server_id,self.tunnel,self.observe_user)
        server = uvicorn.Server(uvicorn.Config(app,host='0.0.0.0',port=port,log_level='warning',access_log=False,log_config=None))
        thread = threading.Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True)
        self.listener,self.server,self.thread = listener,server,thread
        thread.start()
        deadline = time.monotonic()+10
        while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.02)
        if not server.started:
            self.stop_server();self.config['code']=old_code;raise RuntimeError('Сервер не запустился. Проверьте порт.')
        self.config.update(mode='server',port=port,address='');self.error=''
        self.persist()
        self.phase='running';self.record('success',f'Сервер запущен. Ожидание подключений на порту {port}')

    def stop_server(self):
        self.tunnel.stop()
        was_running=bool(self.server)
        if self.server:self.server.should_exit=True
        if self.thread:self.thread.join(timeout=5)
        if self.thread and self.thread.is_alive():raise RuntimeError('Сервер ещё завершает запросы. Повторите позже.')
        if self.listener:self.listener.close()
        self.server=self.thread=self.listener=None
        with self.log_lock:self.user_activity.clear()
        self.phase='stopped'
        if was_running:self.record('info','Сервер остановлен')

class ConnectionDispatch:
    def __init__(self, app, controller):self.app,self.c = app,controller
    async def __call__(self,scope,receive,send):
        if scope['type'] != 'http':
            return await self.app(scope,receive,send)
        if not scope['path'].startswith('/api/'):
            return await self.c.workspace(scope,receive,send)
        req = Request(scope,receive=receive)
        token=os.environ.get('STAGEOS_TOKEN','')
        if token and not secrets.compare_digest(req.headers.get('x-stageos-token',''),token):
            return await JSONResponse({'detail':'Доступ запрещён'},401)(scope,receive,send)
        origin=req.headers.get('origin')
        if origin and origin not in [str(req.base_url).rstrip('/'),'http://localhost:5173','http://127.0.0.1:5173']:
            return await JSONResponse({'detail':'Источник запроса запрещён'},403)(scope,receive,send)
        if scope['path'].startswith('/api/connection'):
            return await self.app(scope,receive,send)
        if self.c.config['mode'] != 'client':
            return await self.c.workspace(scope,receive,send)
        # Keep separate browser cookies, with no shared httpx cookie jar between users.
        address,code=self.c.config['address'],self.c.config['code']
        headers={k:v for k,v in req.headers.items() if k.lower() in ('content-type','cookie','accept','if-none-match')}
        headers.update({'X-StageOS-Code':code,**HEADERS})
        try:
            timeout = 8 if scope['path'] in {'/api/auth/session','/api/mobile/session'} else 120
            async with httpx.AsyncClient(timeout=timeout,follow_redirects=False,trust_env=False) as client:
                response=await client.request(req.method,address+scope['path']+('?' + scope['query_string'].decode() if scope['query_string'] else ''),headers=headers,content=await req.body())
            if response.status_code in {502,503,504} or response.headers.get('X-StageOS-Disconnected')=='1':
                raise httpx.ConnectError('Server disconnected')
            outgoing=Response(response.content,status_code=response.status_code)
            outgoing.raw_headers=[(k,v) for k,v in response.headers.raw if k.lower() not in (b'content-length',b'transfer-encoding',b'content-encoding',b'connection')]
            return await outgoing(scope,receive,send)
        except httpx.HTTPError:
            outgoing=JSONResponse({'detail':'Сервер недоступен. Проверьте сеть и запущен ли StageOS Server. Изменения не сохранены.'},503,headers={'X-StageOS-Disconnected':'1'})
            outgoing.delete_cookie('stageos_session',path='/api')
            return await outgoing(scope,receive,send)

def create_desktop_app(home=None,static_dir=None,bootstrap_file=None):
    home=Path(home or os.environ.get('STAGEOS_HOME',Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/share'))/'StageOS-Work'))
    workspace=create_workspace_app(home,static_dir,bootstrap_file)
    controller=NetworkController(home,workspace)
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    app.state.network=controller
    app.add_middleware(ConnectionDispatch,controller=controller)

    @app.exception_handler(ValueError)
    async def invalid(_,error):return JSONResponse({'detail':'Проверьте настройки подключения'},422)

    @app.get('/api/connection')
    def status(req:Request):
        result=controller.status()
        try:
            user=workspace.state.registry.current(req)
            result['can_manage_tunnel']=user['role']=='admin' and result['mode']=='server'
            if result['can_manage_tunnel']:
                users=controller.active_users(user['theatre_id'])
                result['users']={'online':len(users),'sessions':sum(row['sessions'] for row in users),'items':users}
        except HTTPException:result['can_manage_tunnel']=False
        return result

    @app.get('/api/connection/diagnostics')
    def diagnostics():return controller.inspect()

    @app.post('/api/connection')
    async def configure(req:Request):
        body=await req.json()
        if not isinstance(body,dict):raise HTTPException(422,'Проверьте настройки подключения')
        mode=body.get('mode')
        previous_mode=controller.config['mode']
        try:
            if controller.server:
                user=workspace.state.registry.current(req)
                if user['role']!='admin':raise HTTPException(403,'Требуются права администратора')
            if mode=='client':
                address=validate_address(body.get('address',''));code=body.get('code','')
                if not isinstance(code,str) or not 8 <= len(code) <= 128 or not code.isascii():raise ValueError('Укажите код подключения к серверу')
                # Probe before switching; a wrong code must never replace a working connection.
                async with httpx.AsyncClient(timeout=10,trust_env=False,headers=HEADERS) as client:
                    hello=await client.get(address+'/api/network/hello')
                    if hello.status_code in {301,302,307,308}:
                        raise ValueError('Адрес перенаправляет подключение. Используйте проверенный HTTPS-адрес из окна туннеля сервера.')
                    hello.raise_for_status()
                    if hello.json().get('protocol')!=PROTOCOL or hello.json().get('product')!='StageOS Server':raise ValueError('Это не совместимый StageOS Server')
                    check=await client.get(address+'/api/auth/theatres',headers={'X-StageOS-Code':code});check.raise_for_status()
                await anyio.to_thread.run_sync(lambda:controller.set_mode(mode,address=address,code=code))
            elif mode=='server':
                # Running host can only be managed by its logged-in administrator.
                if controller.server:
                    user=workspace.state.registry.current(req)
                    if user['role']!='admin':raise HTTPException(403,'Требуются права администратора')
                await anyio.to_thread.run_sync(lambda:controller.set_mode(mode,port=body.get('port',8765)))
            elif mode=='local':
                if controller.server:
                    user=workspace.state.registry.current(req)
                    if user['role']!='admin':raise HTTPException(403,'Требуются права администратора')
                await anyio.to_thread.run_sync(lambda:controller.set_mode(mode,address=''))
            else:raise ValueError('Выберите режим подключения')
        except (ValueError,OSError,RuntimeError) as error:
            controller.record('error',str(error));raise HTTPException(422,str(error))
        except httpx.HTTPStatusError as error:
            raise HTTPException(422,'Неверный код подключения' if error.response.status_code==403 else 'Сервер отклонил подключение')
        except httpx.HTTPError:raise HTTPException(503,'Не удалось подключиться. Проверьте адрес, сеть и брандмауэр сервера.')
        result=JSONResponse(status(req))
        # Local and server modes share the same registry and theatre identity.
        # Clear only when entering/leaving/reconfiguring a remote connection.
        if previous_mode=='client' or mode=='client':
            result.delete_cookie('stageos_session',path='/api')
        return result

    @app.post('/api/connection/firewall')
    def firewall(req:Request,body:dict|None=None):
        user=workspace.state.registry.current(req)
        if user['role']!='admin':raise HTTPException(403,'Требуются права администратора')
        if os.name!='nt':raise HTTPException(422,'Настройка брандмауэра доступна только в Windows')
        if not controller.server:raise HTTPException(422,'Сначала запустите сервер')
        interface_index=(body or {}).get('interface_index',0)
        if isinstance(interface_index,bool) or not isinstance(interface_index,int) or not 0<=interface_index<=2147483647:
            raise HTTPException(422,'Выберите сетевой адаптер')
        controller.firewall_state='pending'
        controller.record('info','Настройка брандмауэра: подтвердите запрос администратора Windows')
        try:
            result=run_firewall_setup(controller.config['port'],interface_index)
        except HTTPException as error:
            controller.firewall_state='error';controller.record('error',error.detail);raise
        controller.firewall_state='success'
        controller.record('success','Windows: правило брандмауэра создано и проверено')
        controller.inspect()
        return result

    @app.post('/api/connection/tunnel')
    def tunnel(req:Request,body:dict):
        user=workspace.state.registry.current(req)
        if user['role']!='admin':raise HTTPException(403,'Требуются права администратора')
        if controller.config['mode']!='server' or not controller.status()['running']:
            raise HTTPException(422,'Сначала запустите сервер')
        with controller.lock:
            try:
                action=body.get('action')
                if action=='install':controller.tunnel.install()
                elif action=='start':
                    if not isinstance(body.get('remember',False),bool):raise ValueError('Проверьте настройки подключения')
                    controller.tunnel.start(body.get('authtoken',''),body.get('remember',False))
                elif action=='stop':controller.tunnel.stop()
                elif action=='forget':controller.tunnel.forget_key()
                else:raise ValueError('Выберите действие туннеля')
            except (ValueError,OSError,RuntimeError) as error:
                # Exceptions from ngrok itself are never returned, as they may contain credentials.
                if isinstance(error,ValueError):raise HTTPException(422,str(error)) from None
                raise HTTPException(422,'Не удалось изменить состояние туннеля. Повторите действие') from None
        return status(req)
    return app


def run_firewall_setup(port,interface_index=0):
    """Wait for elevated PowerShell and report its actual exit status to the UI."""
    script=Path(__file__).resolve().parent/'firewall.ps1'
    args=subprocess.list2cmdline(['-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
                                 '-File',str(script),'-Port',str(port),'-RuntimePath',sys.executable,'-InterfaceIndex',str(interface_index)])
    quoted=args.replace("'", "''")
    command=("$ErrorActionPreference='Stop'; try { "
             " $p=Start-Process -FilePath 'powershell.exe' -Verb RunAs -WindowStyle Hidden "
             f"-ArgumentList '{quoted}' -Wait -PassThru -ErrorAction Stop; exit $p.ExitCode "
             "} catch { Write-Error $_; exit 1 }")
    encoded=base64.b64encode(command.encode('utf-16-le')).decode('ascii')
    try:
        completed=subprocess.run(
            ['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',encoded],
            capture_output=True,timeout=120,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except subprocess.TimeoutExpired:
        raise HTTPException(422,'Ожидание настройки Windows истекло. Проверьте запрос разрешения Windows и повторите настройку.')
    except OSError:
        raise HTTPException(422,'Не удалось запустить настройку Windows. Проверьте доступность PowerShell.')
    if completed.returncode!=0:
        raise HTTPException(422,'Windows не подтвердила настройку брандмауэра. Разрешите запрос администратора и повторите. Подробности: app\\backend\\firewall-error.log в папке Windows-Portable.')
    return {'ok':True,'message':'Правило брандмауэра создано и проверено. Подключения разрешены в частной локальной сети. Вход в аккаунт сохранён.'}


def inspect_windows_network(port):
    script=Path(__file__).resolve().parent/'network_status.ps1'
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
                           '-File',str(script),'-Port',str(port),'-RuntimePath',sys.executable],
                          capture_output=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise ValueError('Windows network query failed')
    data=json.loads(result.stdout.decode('utf-8-sig'))
    if not isinstance(data,dict) or not isinstance(data.get('profiles'),list) or data.get('firewall') not in ('allowed','missing','mismatch'):
        raise ValueError('Invalid Windows network status')
    return {key:data[key] for key in ('profiles','firewall')}
