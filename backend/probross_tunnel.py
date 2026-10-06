"""Probross tunnel provider for StageOS.

Uses the official Windows CLI and keeps an optional tunnel token encrypted with
Windows DPAPI. The public endpoint is verified as the same StageOS server before
it is shown to the user.
"""
import base64
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from .tunnel import TunnelController as BaseTunnel, protect

AGENT_URL = "https://probross.ru/cli/windows/amd64/probross"
AGENT_VERSION = "current"


def validate_token(token):
    if not isinstance(token, str):
        raise ValueError("Укажите токен туннеля Probross")
    token = token.strip()
    if not 16 <= len(token) <= 1024 or any(ch.isspace() or ord(ch) < 32 for ch in token):
        raise ValueError("Укажите корректный токен туннеля из кабинета Probross")
    return token


def public_address(value):
    if not isinstance(value, str):
        raise ValueError("Некорректный внешний адрес Probross")
    try:
        p = urlsplit(value.strip())
        host = (p.hostname or "").lower()
        valid = (
            p.scheme == "https"
            and re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.probross\.ru", host)
            and not p.username
            and not p.password
            and p.port in (None, 443)
            and p.path in ("", "/")
            and not p.query
            and not p.fragment
        )
    except (ValueError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise ValueError("Некорректный внешний адрес Probross")
    return value.strip().rstrip("/")


class ProbrossTunnel(BaseTunnel):
    def __init__(self, home, network):
        super().__init__(home, network)
        self.exe = self.home / "probross.exe"
        self.key_file = self.home / "probross-token.dpapi"
        self.reader = None
        self.candidate = ""
        self.agent_error = ""

    def status(self):
        with self.state_lock:
            return {
                **self.state,
                "provider": "probross",
                "installed": self.exe.is_file(),
                "saved_key": self.key_file.is_file(),
                "version": AGENT_VERSION,
                "can_install": os.name == "nt",
            }

    def install(self):
        with self.operation_lock:
            if os.name != "nt":
                raise ValueError("Автоматическая установка Probross доступна только в Windows")
            if self.process is not None:
                raise ValueError("Сначала остановите интернет-туннель")
            self.update(phase="installing", error="")
            self.network.record("info", "Загрузка Probross с официального сайта")
            tmp = self.exe.with_suffix(".tmp")
            try:
                self.home.mkdir(parents=True, exist_ok=True)
                size = 0
                with httpx.stream("GET", AGENT_URL, timeout=60, follow_redirects=True, trust_env=False) as response:
                    response.raise_for_status()
                    with tmp.open("wb") as target:
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > 100 * 1024 * 1024:
                                raise ValueError("Недопустимый размер Probross")
                            target.write(chunk)
                data = tmp.read_bytes()[:2]
                if size < 64 * 1024 or data != b"MZ":
                    raise ValueError("Загруженный файл Probross не похож на Windows-приложение")
                os.replace(tmp, self.exe)
                self.update(phase="stopped", error="")
                self.network.record("success", "Probross установлен")
            except Exception:
                self.update(phase="error", error="Не удалось установить Probross. Проверьте интернет и повторите загрузку")
                self.network.record("error", self.status()["error"])
                raise ValueError(self.status()["error"]) from None
            finally:
                tmp.unlink(missing_ok=True)

    def save_key(self, token):
        encrypted = protect(validate_token(token).encode("utf-8"))
        self.home.mkdir(parents=True, exist_ok=True)
        tmp = self.key_file.with_suffix(".tmp")
        tmp.write_bytes(base64.b64encode(encrypted))
        os.replace(tmp, self.key_file)

    def read_key(self):
        try:
            raw = base64.b64decode(self.key_file.read_bytes())
            return validate_token(protect(raw, True).decode("utf-8"))
        except Exception:
            raise ValueError("Не удалось прочитать сохранённый токен Probross. Введите его заново") from None

    def forget_key(self):
        with self.operation_lock:
            self.stop()
            self.key_file.unlink(missing_ok=True)
            self.network.record("info", "Сохранённый токен Probross удалён")

    def start(self, token="", remember=False):
        with self.operation_lock:
            if not self.network.status()["running"]:
                raise ValueError("Сначала запустите сервер")
            if not self.exe.is_file():
                raise ValueError("Сначала установите Probross")
            if self.process is not None and self.process.poll() is None:
                raise ValueError("Туннель уже запущен. Сначала остановите его")
            token = validate_token(token) if token else self.read_key()
            self.stop()
            if remember:
                self.save_key(token)
            port = self.network.config["port"]
            env = {k: v for k, v in os.environ.items() if not k.upper().startswith("PROBROSS_")}
            try:
                self.process = subprocess.Popen(
                    [str(self.exe), "tunnel", "--local", f"http://127.0.0.1:{port}", "--token", token],
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except OSError:
                self.update(phase="error", url="", verified=False, error="Не удалось запустить Probross. Повторите установку")
                raise ValueError(self.status()["error"]) from None
            self.stop_event = threading.Event()
            self.candidate = ""
            self.agent_error = ""
            self.update(phase="starting", url="", verified=False, checked_at=None, error="")
            self.network.record("info", "Запуск туннеля Probross")
            self.reader = threading.Thread(target=self.read_output, args=(self.process, self.stop_event), daemon=True)
            self.worker = threading.Thread(target=self.monitor_probross, args=(self.process, self.stop_event), daemon=True)
            self.reader.start()
            self.worker.start()

    def read_output(self, process, stop_event):
        try:
            while not stop_event.is_set():
                line = process.stdout.readline(8192)
                if not line:
                    return
                for match in re.finditer(r"https://[a-z0-9-]+\.probross\.ru(?:/)?", line.lower()):
                    try:
                        address = public_address(match.group())
                    except ValueError:
                        continue
                    with self.state_lock:
                        self.candidate = address
                low = line.lower()
                if "unauthorized" in low or "invalid token" in low or "401" in low:
                    with self.state_lock:
                        self.agent_error = "Probross отклонил токен. Получите токен туннеля в кабинете и попробуйте снова"
                elif "connection refused" in low or "failed to connect" in low:
                    with self.state_lock:
                        self.agent_error = "Не удалось соединиться с Probross. Проверьте интернет"
        except (OSError, ValueError):
            return

    def monitor_probross(self, process, stop_event):
        started = time.monotonic()
        previous = "starting"
        last_probe = 0.0
        verified = False
        checked_at = None
        previous_candidate = ""
        while not stop_event.is_set():
            if process.poll() is not None:
                self.update(
                    phase="error",
                    url="",
                    verified=False,
                    error=self.agent_error or "Probross завершился. Проверьте токен и интернет, затем запустите снова",
                )
                self.network.record("error", self.status()["error"])
                return
            with self.state_lock:
                candidate = self.candidate
            if candidate and (candidate != previous_candidate or time.monotonic() - last_probe >= 60):
                try:
                    verified = self.verify(public_address(candidate))
                except (httpx.HTTPError, ValueError, TypeError, AttributeError):
                    verified = False
                previous_candidate = candidate
                last_probe = time.monotonic()
                checked_at = datetime.now(timezone.utc).isoformat()
            phase = "connected" if verified else ("starting" if time.monotonic() - started < 60 else "disconnected")
            error = "" if phase != "disconnected" else "Нет ответа StageOS через Probross. Агент продолжает переподключение"
            self.update(
                phase=phase,
                url=candidate if verified else "",
                verified=verified,
                checked_at=checked_at,
                error=error,
            )
            if phase != previous:
                self.network.record(
                    "success" if verified else "warning",
                    "Probross подключён. Внешний адрес проверен" if verified else error,
                )
            previous = phase
            if stop_event.wait(1):
                return

    def stop(self):
        process = self.process
        super().stop()
        reader, self.reader = self.reader, None
        if reader and reader is not threading.current_thread():
            reader.join(timeout=2)
        if process and process.stdout:
            process.stdout.close()
        with self.state_lock:
            self.candidate = ""
