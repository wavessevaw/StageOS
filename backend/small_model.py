"""Optional small local Ollama model installation, with a visible progress job."""

import json, threading
from urllib.parse import urlsplit
import httpx
from .models import Setting

MODEL = "qwen3:0.6b"


class SmallModelJob:
    def __init__(self, Session, lock):
        self.Session, self.database_lock = Session, lock
        self.lock = threading.Lock()
        self.state = {"status": "idle", "model": MODEL, "progress": 0, "message": ""}

    def status(self):
        with self.lock:
            return dict(self.state)

    def update(self, **values):
        with self.lock:
            self.state.update(values)

    def start(self, cfg):
        url = urlsplit(cfg["endpoint"])
        if (
            cfg["provider"] != "Ollama"
            or url.hostname not in ("localhost", "127.0.0.1", "::1")
            or url.username
            or url.password
        ):
            raise ValueError(
                "Загрузка малой модели доступна через локальный Ollama на компьютере сервера"
            )
        with self.lock:
            if self.state["status"] == "downloading":
                return dict(self.state)
            self.state = {
                "status": "downloading",
                "model": MODEL,
                "progress": 0,
                "message": "Подключение к Ollama…",
            }
        threading.Thread(
            target=self.run, args=(cfg, url.scheme + "://" + url.netloc), daemon=True
        ).start()
        return self.status()

    def run(self, cfg, base):
        try:
            succeeded = False
            with httpx.stream(
                "POST",
                base + "/api/pull",
                json={"model": MODEL, "stream": True},
                timeout=httpx.Timeout(180, connect=10),
                trust_env=False,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    item = json.loads(line)
                    if item.get("error"):
                        raise ValueError(item["error"])
                    total = item.get("total", 0)
                    done = item.get("completed", 0)
                    self.update(
                        progress=min(99, round(100 * done / total))
                        if total
                        else self.status()["progress"],
                        message="Загрузка модели…",
                    )
                    if item.get("status") == "success":
                        succeeded = True
            if not succeeded:
                raise ValueError("Incomplete model download")
            activated = False
            with self.database_lock, self.Session.begin() as session:
                setting = session.get(Setting, "llm")
                current = setting.value if setting else cfg
                if (
                    current["endpoint"] == cfg["endpoint"]
                    and current["provider"] == "Ollama"
                ):
                    activated = True
                    session.merge(
                        Setting(
                            key="llm",
                            value={**current, "model": MODEL, "enabled": True},
                        )
                    )
            self.update(
                status="ready",
                progress=100,
                message="Модель загружена. Локальный помощник включён для текущего Ollama."
                if activated
                else "Модель загружена. Настройки помощника изменились; включите модель вручную.",
            )
        except Exception as error:
            self.update(
                status="error",
                message="Не удалось загрузить модель. Убедитесь, что Ollama установлен и запущен, а интернет доступен.",
                error_type=type(error).__name__,
            )
