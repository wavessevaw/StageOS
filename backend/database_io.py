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


def validate_saved_data(session):
    """Reject structurally corrupt snapshots before the active database is switched."""
    from datetime import datetime
    from sqlalchemy import select
    from .models import Resource, Event, Task, Booking
    from .engine import Request
    from .production_editor import validate_production
    resources={r.id:r for r in session.scalars(select(Resource))}
    states={'Draft','Planning','Pending Approval','Approved','In Preparation','Ready','In Progress','Completed','Cancelled'}
    def span(a,b,empty=False):
        if not isinstance(a,datetime):a=datetime.fromisoformat(a)
        if not isinstance(b,datetime):b=datetime.fromisoformat(b)
        if a.tzinfo or b.tzinfo or (b<a or (b==a and not empty)):raise ValueError('Некорректный интервал сохранённого плана')
        return a,b
    for event in session.scalars(select(Event)):
        span(event.start,event.end)
        request=Request.model_validate(event.data['request'])
        plan=event.data['plan']
        if event.status not in states or event.version<1:raise ValueError('Некорректный статус или версия события')
        if request.production_id!=event.production_id or request.venue_id!=event.venue_id or request.start!=event.start or request.kind!=event.kind:
            raise ValueError('Событие не соответствует сохранённой команде')
        if not isinstance(plan,dict) or not {'request','assignments','tasks','bookings','conflicts','compatibility','title','start','end','status'}<=plan.keys():
            raise ValueError('Сохранённый план неполон')
        if plan['start']!=event.start.isoformat() or plan['end']!=event.end.isoformat():raise ValueError('Время сохранённого плана повреждено')
        if plan.get('production_snapshot') is not None:
            validate_production(session,plan['production_snapshot'],check_qualifications=False,allow_retired=True)
        for assignment in plan['assignments']:
            for key in ['actual_id','responsible_id']:
                if assignment[key] not in resources or resources[assignment[key]].kind!='Person':raise ValueError('В плане отсутствует сотрудник')
        for conflict in plan['conflicts']:
            if not {'code','resource','reason','severity'}<=conflict.keys():raise ValueError('Описание конфликта повреждено')
        if not {'checks','conflicts','requirements','override','version'}<=plan['compatibility'].keys():raise ValueError('Паспорт совместимости повреждён')
        persisted=list(session.scalars(select(Task).where(Task.event_id==event.id)))
        task_keys=lambda t:(t['name'],t['department'],*span(t['start'],t['end'],empty=True))
        if sorted(task_keys(t) for t in plan['tasks'])!=sorted((t.name,t.department,*span(t.start,t.end,empty=True)) for t in persisted):
            raise ValueError('Задачи не соответствуют сохранённому плану')
        for t in persisted:
            if (t.actual_start is None)!=(t.actual_end is None):raise ValueError('Фактический интервал неполон')
            if t.actual_start is not None:span(t.actual_start,t.actual_end)
        for b in plan['bookings']:
            span(b['start'],b['end'])
            if b['resource_id'] not in resources:raise ValueError('В плане отсутствует ресурс')
        saved=list(session.scalars(select(Booking).where(Booking.event_id==event.id)))
        if event.status=='Cancelled':
            if saved:raise ValueError('Отменённое событие удерживает ресурсы')
        elif sorted((b['resource_id'],*span(b['start'],b['end'])) for b in plan['bookings'])!=sorted((b.resource_id,*span(b.start,b.end)) for b in saved):
            raise ValueError('Бронирования не соответствуют сохранённому плану')
