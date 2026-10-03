"""Bounded database context for the optional model; never grants mutation authority."""

import re
from datetime import datetime, timedelta
from sqlalchemy import select
from .models import Production, Resource, Event, Booking
from .engine import Request, preview, compatibility


def build_context(s, question):
    q = question.lower()
    tokens = {x[:4] for x in re.findall(r"[а-яёa-z]+", q) if len(x) >= 4}

    def matches(name):
        return bool(
            tokens
            & {x[:4] for x in re.findall(r"[а-яёa-z]+", name.lower()) if len(x) >= 4}
        )

    productions = s.scalars(select(Production)).all()
    resources = {r.id: r for r in s.scalars(select(Resource))}
    selected = [p for p in productions if matches(p.name)]
    people = [r for r in resources.values() if r.kind == "Person" and matches(r.name)][
        :12
    ]
    venues = [r for r in resources.values() if r.kind == "Venue" and matches(r.name)]
    query = select(Event).where(Event.status != "Cancelled").order_by(Event.start)
    if selected:
        query = query.where(Event.production_id.in_([p.id for p in selected]))
    if venues:
        query = query.where(Event.venue_id.in_([v.id for v in venues]))
    now = datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if "завтра" in q:
        start += timedelta(days=1)
        query = query.where(
            Event.start >= start, Event.start < start + timedelta(days=1)
        )
    elif "сегодня" in q:
        query = query.where(
            Event.start >= start, Event.start < start + timedelta(days=1)
        )
    elif "недел" in q:
        start -= timedelta(days=start.weekday())
        query = query.where(
            Event.start >= start, Event.start < start + timedelta(days=7)
        )
    evs = s.scalars(query.limit(40)).all()
    events = []
    for ev in evs:
        row = {
            "id": ev.id,
            "title": ev.title,
            "kind": ev.kind,
            "start": ev.start.isoformat(),
            "end": ev.end.isoformat(),
            "venue": resources[ev.venue_id].name,
            "status": ev.status,
        }
        if selected or people:
            row["assignments"] = [
                {
                    "role": a["role"],
                    "name": a["actual"],
                    "responsible": a["responsible"],
                    "call": a["call"],
                }
                for a in ev.data["plan"]["assignments"]
                if a["department"]
                in ["Режиссёр", "Дирижёр", "Помреж", "Техдир", "Звук", "Свет", "Видео"]
                or a["actual_id"] in [r.id for r in people]
            ]
        if "конфликт" in q:
            r = Request(
                **{**ev.data["request"], "event_id": ev.id, "version": ev.version}
            )
            row["conflicts"] = preview(s, r)["conflicts"][:12]
        events.append(row)
    checks = []
    if any(x in q for x in ["совместим", "почему", "штанкет", "софит"]):
        for p in selected[:2]:
            for v in venues[:2]:
                result = compatibility(s, p, v)
                checks.append({"production": p.name, "venue": v.name, "result": result})
    return {
        "as_of": now.isoformat(),
        "limits": "До 40 событий и 12 совпавших сотрудников; это ограниченная выборка, а не весь архив. Если сведений нет — сообщи об этом.",
        "production_catalog": [{"id": p.id, "name": p.name} for p in productions],
        "venues": [
            {"id": r.id, "name": r.name}
            for r in resources.values()
            if r.kind == "Venue"
        ],
        "productions": [
            {
                "id": p.id,
                "name": p.name,
                "responsibles": {
                    d: resources[rid].name for d, rid in p.data["responsibles"].items()
                },
                "requirements": p.data["requirements"],
                "roles": p.data["roles"],
            }
            for p in (selected or productions)[:8]
        ],
        "events": events,
        "people": [
            {
                "id": r.id,
                "name": r.name,
                "department": r.department,
                "bookings": [
                    {
                        "start": b.start.isoformat(),
                        "end": b.end.isoformat(),
                        "label": b.label,
                    }
                    for b in s.scalars(
                        select(Booking)
                        .where(Booking.resource_id == r.id, Booking.end >= now)
                        .order_by(Booking.start)
                        .limit(20)
                    )
                ],
            }
            for r in people
        ],
        "compatibility": checks,
    }
