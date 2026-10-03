"""Validated SQLite import/export. Imports become a separate managed database."""

import sqlite3, uuid, json
from pathlib import Path

REQUIRED = {
    "resources",
    "productions",
    "events",
    "bookings",
    "tasks",
    "audit",
    "settings",
    "alembic_version",
}


def validate_database(path):
    with sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("База SQLite повреждена")
        tables = {
            x[0]
            for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if not REQUIRED <= tables:
            raise ValueError("Файл не является базой StageOS")
        if db.execute("SELECT version_num FROM alembic_version").fetchone() != (
            "0001",
        ):
            raise ValueError("Версия базы не поддерживается этой сборкой")
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("В базе нарушены связи ресурсов")


def import_database(content: bytes, directory: Path):
    if len(content) > 64 * 1024 * 1024:
        raise ValueError("Размер базы превышает 64 МБ")
    if not content.startswith(b"SQLite format 3\x00"):
        raise ValueError("Выберите файл SQLite .db")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"imported-{uuid.uuid4().hex}.db"
    target.write_bytes(content)
    try:
        validate_database(target)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target


def backup_database(source: Path, target: Path):
    with sqlite3.connect(str(source)) as src, sqlite3.connect(str(target)) as dst:
        src.backup(dst)
    validate_database(target)
