"""Desktop connection gateway and a single database-owning LAN server.

Clients proxy API requests to the host; database files never leave the host
except through the explicit administrator export command.
"""
import base64
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

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from .workspaces import create_workspace_app

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
    return value

class LanAccess:
    def __init__(self, app, code, desktop_token):
        self.app, self.code, self.token = app, code, desktop_token

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        req = Request(scope)
        if req.url.path == '/api/network/hello' and req.method == 'GET':
            return await JSONResponse({'product':'StageOS Server','version':'1.0.4','protocol':PROTOCOL})(scope, receive, send)
        if req.url.path.startswith('/api'):
            if not secrets.compare_digest(req.headers.get('x-stageos-code','').encode(), self.code.encode()):
                return await JSONResponse({'detail':'Неверный код подключения к серверу'},403)(scope,receive,send)
            if req.url.path in ('/api/auth/theatres',) and req.method == 'POST' or req.url.path.endswith('/setup'):
                return await JSONResponse({'detail':'Создание театра и первый администратор доступны на компьютере сервера'},403)(scope,receive,send)
            headers = [(k,v) for k,v in scope['headers'] if k.lower() != b'x-stageos-token']
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
        if self.config['mode'] == 'server':
            try:self.start_server(self.config['port'])
            except (OSError,RuntimeError) as error:self.error = str(error)

    def persist(self):
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.config,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(tmp,self.path)

    def status(self):
        addresses = {'127.0.0.1'}
        try:addresses.update(socket.gethostbyname_ex(socket.gethostname())[2])
        except OSError:pass
        return {**self.config,'enabled':True,'running':bool(self.server and self.server.started and self.thread.is_alive()),'addresses':[f'http://{a}:{self.config["port"]}' for a in sorted(addresses)],'error':self.error}

    def start_server(self, port):
        if isinstance(port,bool) or not isinstance(port,int) or not 1024 <= port <= 65535:
            raise ValueError('Порт сервера: от 1024 до 65535')
        if self.config['mode']=='server' and self.config['port']==port and self.status()['running']:
            return
        self.stop_server()
        listener = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        try:listener.bind(('0.0.0.0',port))
        except Exception:listener.close();raise
        old_code=self.config['code']
        if self.config['mode']!='server':self.config['code']=secrets.token_urlsafe(18)
        app = LanAccess(self.workspace,self.config['code'],os.environ.get('STAGEOS_TOKEN',''))
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

    def stop_server(self):
        if self.server:self.server.should_exit=True
        if self.thread:self.thread.join(timeout=5)
        if self.thread and self.thread.is_alive():raise RuntimeError('Сервер ещё завершает запросы. Повторите позже.')
        if self.listener:self.listener.close()
        self.server=self.thread=self.listener=None

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
        headers.update({'X-StageOS-Code':code,'Origin':address})
        try:
            async with httpx.AsyncClient(timeout=120,follow_redirects=False,trust_env=False) as client:
                response=await client.request(req.method,address+scope['path']+('?' + scope['query_string'].decode() if scope['query_string'] else ''),headers=headers,content=await req.body())
            outgoing=Response(response.content,status_code=response.status_code)
            outgoing.raw_headers=[(k,v) for k,v in response.headers.raw if k.lower() not in (b'content-length',b'transfer-encoding',b'content-encoding',b'connection')]
            return await outgoing(scope,receive,send)
        except httpx.HTTPError:
            return await JSONResponse({'detail':'Сервер недоступен. Проверьте сеть и запущен ли StageOS Server. Изменения не сохранены.'},503)(scope,receive,send)

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
    def status():return controller.status()

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
                async with httpx.AsyncClient(timeout=10,trust_env=False) as client:
                    hello=await client.get(address+'/api/network/hello');hello.raise_for_status()
                    if hello.json().get('protocol')!=PROTOCOL or hello.json().get('product')!='StageOS Server':raise ValueError('Это не совместимый StageOS Server')
                    check=await client.get(address+'/api/auth/theatres',headers={'X-StageOS-Code':code});check.raise_for_status()
                with controller.lock:
                    controller.stop_server();controller.config.update(mode=mode,address=address,code=code);controller.error='';controller.persist()
            elif mode=='server':
                # Running host can only be managed by its logged-in administrator.
                if controller.server:
                    user=workspace.state.registry.current(req)
                    if user['role']!='admin':raise HTTPException(403,'Требуются права администратора')
                with controller.lock:controller.start_server(body.get('port',8765))
            elif mode=='local':
                if controller.server:
                    user=workspace.state.registry.current(req)
                    if user['role']!='admin':raise HTTPException(403,'Требуются права администратора')
                with controller.lock:
                    controller.stop_server();controller.config.update(mode=mode,address='');controller.error='';controller.persist()
            else:raise ValueError('Выберите режим подключения')
        except (ValueError,OSError) as error:raise HTTPException(422,str(error))
        except httpx.HTTPStatusError as error:
            raise HTTPException(422,'Неверный код подключения' if error.response.status_code==403 else 'Сервер отклонил подключение')
        except httpx.HTTPError:raise HTTPException(503,'Не удалось подключиться. Проверьте адрес, сеть и брандмауэр сервера.')
        result=JSONResponse(controller.status())
        # Local and server modes share the same registry and theatre identity.
        # Clear only when entering/leaving/reconfiguring a remote connection.
        if previous_mode=='client' or mode=='client':
            result.delete_cookie('stageos_session',path='/api')
        return result

    @app.post('/api/connection/firewall')
    def firewall(req:Request):
        user=workspace.state.registry.current(req)
        if user['role']!='admin':raise HTTPException(403,'Требуются права администратора')
        if os.name!='nt':raise HTTPException(422,'Настройка брандмауэра доступна только в Windows')
        if not controller.server:raise HTTPException(422,'Сначала запустите сервер')
        return run_firewall_setup(controller.config['port'])
    return app


def run_firewall_setup(port):
    """Wait for elevated PowerShell and report its actual exit status to the UI."""
    script=Path(__file__).resolve().parent/'firewall.ps1'
    args=subprocess.list2cmdline(['-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
                                 '-File',str(script),'-Port',str(port),'-RuntimePath',sys.executable])
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
