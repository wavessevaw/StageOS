"""Owned Quick Tunnel, pinned download and server identity verification."""
import hashlib
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

import httpx
from .tunnel import TunnelController as NgrokTunnel

VERSION = '2026.10.0'
URL = f'https://github.com/cloudflare/cloudflared/releases/download/{VERSION}/cloudflared-windows-amd64.exe'
SHA256 = '86aee4017b26625cee8484c113558f48effa4cd47f7aa05fcf425604e5d2b23c'


def public_address(value):
    try:
        p = urlsplit(value)
        valid = (p.scheme == 'https' and p.hostname and
                 re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com', p.hostname) and
                 not p.username and not p.password and p.port in (None, 443) and
                 p.path in ('', '/') and not p.query and not p.fragment)
    except (ValueError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise ValueError('Некорректный внешний адрес Cloudflare')
    return value.rstrip('/')


class CloudflareTunnel(NgrokTunnel):
    def __init__(self, home, network):
        super().__init__(home, network)
        self.exe = self.home / 'cloudflared.exe'
        self.config_file = self.home / 'cloudflare-empty.yml'
        self.reader = None
        self.candidate = ''
        self.protocol = 'http2'
        self.agent_error = ''

    def status(self):
        with self.state_lock:
            return {**self.state, 'provider': 'cloudflare', 'installed': self.exe.is_file(),
                    'saved_key': False, 'version': VERSION, 'can_install': os.name == 'nt',
                    'protocol': self.protocol}

    def install(self):
        with self.operation_lock:
            if os.name != 'nt':
                raise ValueError('Автоматическая установка Cloudflare доступна только в Windows')
            if self.process is not None:
                raise ValueError('Сначала остановите интернет-туннель')
            self.update(phase='installing', error='')
            self.network.record('info', 'Загрузка Cloudflare с официального GitHub')
            tmp = self.exe.with_suffix('.tmp')
            try:
                self.home.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                size = 0
                with httpx.stream('GET', URL, timeout=60, follow_redirects=True, trust_env=False) as response:
                    response.raise_for_status()
                    with tmp.open('wb') as target:
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > 100 * 1024 * 1024:
                                raise ValueError('Недопустимый размер Cloudflare')
                            digest.update(chunk)
                            target.write(chunk)
                if digest.hexdigest() != SHA256:
                    raise ValueError('Контрольная сумма Cloudflare не совпала')
                os.replace(tmp, self.exe)
                self.update(phase='stopped', error='')
                self.network.record('success', 'Cloudflare установлен и проверен')
            except Exception:
                self.update(phase='error', error='Не удалось установить Cloudflare. Проверьте интернет и повторите загрузку')
                self.network.record('error', self.status()['error'])
                raise ValueError(self.status()['error']) from None
            finally:
                tmp.unlink(missing_ok=True)

    def start(self, token='', remember=False, protocol='http2'):
        with self.operation_lock:
            if protocol not in ('http2', 'auto', 'quic'):
                raise ValueError('Выберите способ соединения Cloudflare')
            if not self.network.status()['running']:
                raise ValueError('Сначала запустите сервер')
            if not self.exe.is_file():
                raise ValueError('Сначала установите Cloudflare')
            if self.process is not None and self.process.poll() is None:
                raise ValueError('Туннель уже запущен. Сначала остановите его')
            self.stop()
            self.protocol = protocol
            self.candidate = ''
            self.agent_error = ''
            self.home.mkdir(parents=True, exist_ok=True)
            # Explicit empty config isolates Quick Tunnel from user's named tunnel config.
            self.config_file.write_text('{}\n', encoding='utf-8')
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                metrics_port = sock.getsockname()[1]
            port = self.network.config['port']
            env = {k: v for k, v in os.environ.items()
                   if not k.upper().startswith(('TUNNEL_', 'CLOUDFLARED_'))}
            try:
                self.process = subprocess.Popen(
                    [str(self.exe), 'tunnel', '--config', str(self.config_file),
                     '--no-autoupdate', '--protocol', protocol,
                     '--metrics', f'127.0.0.1:{metrics_port}',
                     '--http-host-header', f'127.0.0.1:{port}',
                     '--url', f'http://127.0.0.1:{port}'],
                    env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace',
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except OSError:
                self.update(phase='error', url='', verified=False,
                            error='Не удалось запустить Cloudflare. Повторите установку')
                raise ValueError(self.status()['error']) from None
            self.stop_event = threading.Event()
            self.update(phase='starting', url='', verified=False, checked_at=None, error='')
            self.network.record('info', 'Запуск Cloudflare Quick Tunnel · ' + protocol)
            self.reader = threading.Thread(target=self.read_output,
                args=(self.process, self.stop_event), daemon=True)
            self.worker = threading.Thread(target=self.monitor_cloudflare,
                args=(self.process, self.stop_event), daemon=True)
            self.reader.start()
            self.worker.start()

    def read_output(self, process, stop_event):
        try:
            while not stop_event.is_set():
                line = process.stderr.readline(8192)
                if not line:
                    return
                for match in re.finditer(r'https://[a-z0-9-]+\.trycloudflare\.com', line):
                    url = public_address(match.group())
                    with self.state_lock:
                        self.candidate = url
                # Expose only fixed messages, never raw process output.
                if 'could not lookup srv' in line.lower() or 'error looking up cloudflare edge ips' in line.lower():
                    with self.state_lock:
                        self.agent_error = 'DNS не находит серверы Cloudflare. Проверьте DNS или VPN на компьютере сервера'
                elif 'failed to dial' in line.lower() or 'unable to establish connection' in line.lower():
                    with self.state_lock:
                        self.agent_error = 'Не удалось соединиться с Cloudflare. Проверьте интернет и способ соединения'
        except (OSError, ValueError):
            return

    def monitor_cloudflare(self, process, stop_event):
        started = time.monotonic()
        last_probe = 0
        failures = 0
        previous = 'starting'
        checked_at = None
        verified = False
        previous_candidate = ''
        while not stop_event.is_set():
            if process.poll() is not None:
                self.update(phase='error', url='', verified=False,
                            error=self.agent_error or 'Cloudflare завершился. Проверьте интернет и запустите туннель снова')
                self.network.record('error', self.status()['error'])
                return
            with self.state_lock:
                candidate = self.candidate
            delay = 60 if verified else min(30, 5 * 2 ** min(failures, 3))
            if candidate and (candidate != previous_candidate or time.monotonic() - last_probe >= delay):
                try:
                    verified = self.verify(candidate)
                except (httpx.HTTPError, ValueError, TypeError, AttributeError):
                    verified = False
                last_probe = time.monotonic()
                previous_candidate = candidate
                checked_at = datetime.now(timezone.utc).isoformat()
                failures = 0 if verified else failures + 1
            if stop_event.is_set():
                return
            phase = 'connected' if verified else ('starting' if time.monotonic() - started < 60 else 'disconnected')
            error = '' if phase != 'disconnected' else 'Нет ответа StageOS через Cloudflare. Проверьте интернет; агент продолжает переподключение'
            self.update(phase=phase, url=candidate if verified else '', verified=verified,
                        checked_at=checked_at, error=error)
            if phase != previous:
                self.network.record('success' if verified else 'warning',
                    'Cloudflare подключён. Внешний адрес проверен' if verified else error)
            previous = phase
            if stop_event.wait(1):
                return

    def stop(self):
        process = self.process
        super().stop()
        reader, self.reader = self.reader, None
        if reader and reader is not threading.current_thread():
            reader.join(timeout=2)
        if process and process.stderr:
            process.stderr.close()
        with self.state_lock:
            self.candidate = ''


class InternetTunnelController:
    """One selected provider, with migration preserving saved ngrok setup."""
    def __init__(self, home, network):
        self.home = Path(home) / 'tunnel'
        self.preference = self.home / 'provider.json'
        self.lock = threading.RLock()
        self.providers = {'ngrok': NgrokTunnel(home, network), 'cloudflare': CloudflareTunnel(home, network)}
        self.provider = 'ngrok' if (self.home / 'authtoken.dpapi').exists() else 'cloudflare'
        try:
            value = json.loads(self.preference.read_text(encoding='utf-8'))
            if value.get('provider') in self.providers:
                self.provider = value['provider']
        except (OSError, ValueError, AttributeError):
            pass

    def status(self):
        with self.lock:
            return {**self.providers[self.provider].status(), 'provider': self.provider}

    def select(self, provider):
        with self.lock:
            if provider not in self.providers:
                raise ValueError('Выберите Cloudflare или ngrok')
            if provider == self.provider:
                return
            self.providers[self.provider].stop()
            self.home.mkdir(parents=True, exist_ok=True)
            tmp = self.preference.with_suffix('.tmp')
            tmp.write_text(json.dumps({'provider': provider}), encoding='utf-8')
            os.replace(tmp, self.preference)
            self.provider = provider

    def install(self):
        with self.lock:
            self.providers[self.provider].install()

    def start(self, token='', remember=False, protocol='http2'):
        with self.lock:
            agent = self.providers[self.provider]
            if self.provider == 'cloudflare':
                agent.start(protocol=protocol)
            else:
                agent.start(token, remember)

    def stop(self):
        with self.lock:
            self.providers[self.provider].stop()

    def forget_key(self):
        with self.lock:
            if self.provider != 'ngrok':
                raise ValueError('Cloudflare Quick Tunnel не использует ключ')
            self.providers['ngrok'].forget_key()
