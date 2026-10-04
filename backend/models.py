from __future__ import annotations
import os
from pathlib import Path
from datetime import datetime
from sqlalchemy import create_engine, event, String, ForeignKey, DateTime, JSON, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Resource(Base):
    __tablename__ = "resources"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    name: Mapped[str] = mapped_column(String(200))
    department: Mapped[str] = mapped_column(String(40), default="")
    status: Mapped[str] = mapped_column(String(30), default="available")
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class Production(Base):
    __tablename__ = "productions"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(default=1)
    data: Mapped[dict] = mapped_column(JSON)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    production_id: Mapped[int] = mapped_column(ForeignKey("productions.id"))
    venue_id: Mapped[int] = mapped_column(ForeignKey("resources.id"))
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(40))
    start: Mapped[datetime] = mapped_column(DateTime, index=True)
    end: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(40), default="Approved")
    version: Mapped[int] = mapped_column(default=1)
    data: Mapped[dict] = mapped_column(JSON)


class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=True, index=True
    )
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id"), index=True)
    start: Mapped[datetime] = mapped_column(DateTime, index=True)
    end: Mapped[datetime] = mapped_column(DateTime)
    label: Mapped[str] = mapped_column(String(200))
    state: Mapped[str] = mapped_column(String(40), default="reserved")


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    department: Mapped[str] = mapped_column(String(40))
    start: Mapped[datetime] = mapped_column(DateTime)
    end: Mapped[datetime] = mapped_column(DateTime)
    actual_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    actual_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int | None] = mapped_column(nullable=True)
    created: Mapped[datetime] = mapped_column(default=datetime.now)
    action: Mapped[str] = mapped_column(String(100))
    data: Mapped[dict] = mapped_column(JSON)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


def make_engine(url=None):
    if url is None:
        home = Path(
            os.environ.get(
                "STAGEOS_HOME",
                Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share"))
                / "StageOS-Work",
            )
        )
        home.mkdir(parents=True, exist_ok=True)
        default = home / "stageos.db"
        choice = home / "database-choice.json"
        if choice.exists():
            import json

            try:
                selected = Path(json.loads(choice.read_text(encoding="utf-8"))["path"])
                if selected.is_file():
                    default = selected
            except (ValueError, KeyError, OSError):
                pass
        url = os.environ.get("STAGEOS_DATABASE_URL", f"sqlite:///{default}")
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 30}
        if url.startswith("sqlite")
        else {},
    )
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def pragmas(db, *_):
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA journal_mode=WAL")

    return engine
