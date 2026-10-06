"""An owned ngrok agent; secrets never enter config, command line or logs."""
import base64
import ctypes
import hashlib
import io
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit
from zipfile import ZipFile

import httpx

AGENT_VERSION = '3.39.11'
AGENT_URL = 'https://bin.ngrok.com/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip'
AGENT_SHA256 = '699bbf1932ec43a573b764bd03e6568efa2c4e45955eb3cc2089c19bb4be4464'
HEADERS = {'ngrok-skip-browser-warning': 'StageOS'}


def validate_token(token):
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,256}', token):
        raise ValueError('Укажите корректный Authtoken из аккаунта ngrok')
    return token


def protect(data, decrypt=False):
    """Windows DPAPI, bound to the current user; no plaintext fallback."""
    if os.name != 'nt':
        raise ValueError('Сохранение ключа доступно только в Windows')

    class Blob(ctypes.Structure):
        _fields_ = [('size', ctypes.c_ulong), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    buf = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    func = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    func.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                     ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(Blob)]
    func.restype = ctypes.c_int
    if not func(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ValueError('Windows не смогла обработать сохранённый ключ ngrok')
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


def public_address(value):
    if not isinstance(value, str):
        raise ValueError('Некорректный внешний адрес ngrok')
    p = urlsplit(value)
    if (p.scheme != 'https' or not p.hostname or p.username or p.password
            or p.path not in ('', '/') or p.query or p.fragment or p.port not in (None, 443)
            or not any(p.hostname.endswith(s) for s in
                       ('.ngrok.app', '.ngrok-free.app', '.ngrok.io', '.ngrok-free.dev', '.ngrok.dev'))):
        raise ValueError('Некорректный внешний адрес ngrok')
    return value.rstrip('/')


class TunnelController:
    def __init__(self, home, network):
        self.network = network
        self.home = Path(home) / 'tunnel'
        self.exe = self.home / 'ngrok.exe'
        self.key_file = self.home / 'authtoken.dpapi'
        self.config_file = self.home / 'agent.json'
        self.operation_lock = threading.RLock()
        self.state_lock = threading.Lock()
        self.process = None
        self.worker = None
        self.stop_event = threading.Event()
        self.state = {'phase': 'stopped', 'url': '', 'verified': False,
                      'checked_at': None, 'error': ''}

    def status(self):
        with self.state_lock:
            return {**self.state, 'installed': self.exe.is_file(),
                    'saved_key': self.key_file.is_file(), 'version': AGENT_VERSION,
                    'can_install': os.name == 'nt'}

    def update(self, **values):
        with self.state_lock:
            self.state.update(values)

    def install(self):
        with self.operation_lock:
            if os.name != 'nt':
                raise ValueError('Автоматическая установка ngrok доступна только в Windows')
            if self.process is not None:
                raise ValueError('Сначала остановите интернет-туннель')
            self.update(phase='installing', error='')
            self.network.record('info', 'Загрузка ngrok с официального сайта')
            try:
                self.home.mkdir(parents=True, exist_ok=True)
                data = bytearray()
                with httpx.stream('GET', AGENT_URL, timeout=60, follow_redirects=True, trust_env=False) as response:
                    response.raise_for_status()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > 64 * 1024 * 1024:
                            raise ValueError('Недопустимый размер загрузки ngrok')
                if hashlib.sha256(data).hexdigest() != AGENT_SHA256:
                    raise ValueError('Контрольная сумма ngrok не совпала. Требуется обновление StageOS')
                with ZipFile(io.BytesIO(data)) as archive:
                    entry = archive.getinfo('ngrok.exe')
                    if entry.file_size > 100 * 1024 * 1024:
                        raise ValueError('Недопустимый размер ngrok')
                    executable = archive.read(entry)
                tmp = self.exe.with_suffix('.tmp')
                tmp.write_bytes(executable)
                os.replace(tmp, self.exe)
                self.update(phase='stopped', error='')
                self.network.record('success', 'ngrok установлен и проверен')
            except Exception:
                self.update(phase='error', error='Не удалось установить ngrok. Проверьте интернет и повторите загрузку')
                self.network.record('error', self.status()['error'])
                raise ValueError(self.status()['error']) from None

    def save_key(self, token):
        encrypted = protect(validate_token(token).encode('ascii'))
        self.home.mkdir(parents=True, exist_ok=True)
        tmp = self.key_file.with_suffix('.tmp')
        tmp.write_bytes(base64.b64encode(encrypted))
        os.replace(tmp, self.key_file)

    def read_key(self):
        try:
            return validate_token(protect(base64.b64decode(self.key_file.read_bytes()), True).decode('ascii'))
        except Exception:
            raise ValueError('Не удалось прочитать сохранённый ключ. Введите Authtoken заново') from None

    def forget_key(self):
        with self.operation_lock:
            self.stop()
            self.key_file.unlink(missing_ok=True)
            self.network.record('info', 'Сохранённый ключ ngrok удалён')

    def start(self, token='', remember=False):
        with self.operation_lock:
            if not self.network.status()['running']:
                raise ValueError('Сначала запустите сервер')
            if not self.exe.is_file():
                raise ValueError('Сначала установите ngrok')
            if self.process is not None and self.process.poll() is None:
                raise ValueError('Туннель уже запущен. Для смены ключа сначала остановите его')
            token = validate_token(token) if token else self.read_key()
            self.stop()
            if remember:
                self.save_key(token)
            self.home.mkdir(parents=True, exist_ok=True)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                api_port = sock.getsockname()[1]
            config = {'version': '3', 'agent': {
                'web_addr': f'127.0.0.1:{api_port}', 'console_ui': False,
                'remote_management': False, 'update_check': False,
                'log': False}}
            self.config_file.write_text(json.dumps(config), encoding='utf-8')
            env = {k: v for k, v in os.environ.items() if not k.upper().startswith('NGROK_')}
            env['NGROK_AUTHTOKEN'] = token
            port = self.network.config['port']
            try:
                self.process = subprocess.Popen(
                    [str(self.exe), 'http', f'http://127.0.0.1:{port}',
                     '--config', str(self.config_file), '--inspect=false',
                     '--host-header', f'127.0.0.1:{port}'],
                    env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except OSError:
                self.update(phase='error', url='', verified=False, error='Не удалось запустить ngrok. Повторите установку')
                raise ValueError(self.status()['error']) from None
            self.stop_event = threading.Event()
            self.update(phase='starting', url='', verified=False, checked_at=None, error='')
            self.network.record('info', 'Запуск интернет-туннеля')
            self.worker = threading.Thread(target=self.monitor,
                                           args=(self.process, self.stop_event, api_port, port), daemon=True)
            self.worker.start()

    def verify(self, url):
        """Check identity before transmitting the connection code to the endpoint."""
        with httpx.Client(timeout=4, follow_redirects=False, trust_env=False, headers=HEADERS) as client:
            hello = client.get(url + '/api/network/hello')
            hello.raise_for_status()
            data = hello.json()
            if (data.get('product') != 'StageOS Server' or data.get('protocol') != 1
                    or data.get('server_id') != self.network.server_id):
                return False
            access = client.get(url + '/api/auth/theatres', headers={'X-StageOS-Code': self.network.config['code']})
            return access.status_code == 200 and isinstance(access.json().get('theatres'), list)

    def monitor(self, process, stop_event, api_port, port):
        attempts = 0
        previous = 'starting'
        last_probe = 0
        candidate = ''
        ok = False
        checked_at = None
        while not stop_event.is_set():
            if process.poll() is not None:
                self.update(phase='error', url='', verified=False,
                            error='ngrok завершился. Проверьте Authtoken, аккаунт и интернет, затем запустите снова')
                self.network.record('error', self.status()['error'])
                return
            attempts += 1
            url = ''
            try:
                response = httpx.get(f'http://127.0.0.1:{api_port}/api/tunnels', timeout=2, trust_env=False)
                response.raise_for_status()
                for tunnel in response.json().get('tunnels', []):
                    if tunnel.get('proto') == 'https' and tunnel.get('config', {}).get('addr') == f'http://127.0.0.1:{port}':
                        url = public_address(tunnel.get('public_url'))
                        break
                if not url:
                    ok = False
                    candidate = ''
                elif url != candidate or time.monotonic() - last_probe >= 60:
                    ok = self.verify(url)
                    candidate = url
                    last_probe = time.monotonic()
                    checked_at = datetime.now(timezone.utc).isoformat()
            except (httpx.HTTPError, ValueError, TypeError, AttributeError):
                ok = False
                candidate = ''
            if stop_event.is_set():
                return
            phase = 'connected' if ok else ('starting' if attempts < 6 else 'disconnected')
            error = '' if ok or phase == 'starting' else 'Внешний адрес не подтвердил связь с вашим сервером. Проверьте интернет и аккаунт ngrok'
            self.update(phase=phase, url=url if ok else '', verified=ok,
                        checked_at=checked_at, error=error)
            if phase != previous:
                self.network.record('success' if ok else 'warning',
                                    'Интернет-туннель подключён. Внешний адрес проверен' if ok else error)
            previous = phase
            if stop_event.wait(5):
                return

    def stop(self):
        with self.operation_lock:
            self.stop_event.set()
            process, worker = self.process, self.worker
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            if worker and worker is not threading.current_thread():
                worker.join(timeout=12)
                if worker.is_alive():
                    raise RuntimeError('Туннель ещё завершает проверку. Повторите позже')
            self.process = self.worker = None
            self.config_file.unlink(missing_ok=True)
            self.update(phase='stopped', url='', verified=False, error='')
            if process:
                self.network.record('info', 'Интернет-туннель остановлен')
