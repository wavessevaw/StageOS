"""Reproducible conflict fixtures evaluated in a transaction that is rolled back."""

from datetime import datetime, timedelta
from sqlalchemy import select
from .models import Resource, Production, Booking, Event
from .engine import Request, preview

SCENARIOS = [
    ("actor", "Артист занят", "overlap"),
    ("assistant", "Помреж занят", "overlap"),
    ("conductor", "Дирижёр занят", "overlap"),
    ("orchestra", "Оркестрант занят", "overlap"),
    ("sound", "Звукорежиссёр занят", "overlap"),
    ("light", "Световик занят", "overlap"),
    ("video", "Видеооператор занят", "overlap"),
    ("equipment", "Оборудование занято", "overlap"),
    ("maintenance", "Оборудование на обслуживании", "maintenance"),
    ("venue", "Площадка занята", "overlap"),
    ("travel", "Недостаточно времени на переезд", "travel"),
    ("setup", "Монтаж до открытия площадки", "setup"),
    ("vacation", "Отпуск исполнителя", "absence"),
    ("qualification", "Нет нужной квалификации", "qualification"),
    ("orchestra_missing", "Оркестр не укомплектован", "orchestra_missing"),
    ("soffits", "Недостаточно софитов", "soffits"),
    ("bars", "Недостаточно штанкетов", "fly_bars"),
    ("fly", "Нет верхней механики", "fly_system"),
    ("load", "Превышена нагрузка", "bar_load"),
    ("scenery", "Сценография не помещается", "scenery"),
    ("power", "Недостаточная мощность", "power"),
    ("dmx", "Недостаточно DMX universes", "dmx"),
    ("height", "Недостаточная высота", "height"),
    ("gate", "Недостаточный размер ворот", "gate_width"),
]


def evaluate(s, key):
    case = next((x for x in SCENARIOS if x[0] == key), None)
    if not case:
        raise ValueError("Неизвестный сценарий")
    p = s.scalar(select(Production).where(Production.name == "Северный ветер"))
    v = s.scalar(select(Resource).where(Resource.name == "Большой зал"))
    if not p or not v:
        raise ValueError("Для сценариев создайте Demo Theatre")
    r = Request(
        production_id=p.id, venue_id=v.id, start=datetime(2026, 11, 10, 19), cast="B"
    )
    plan = preview(s, r)
    resources = {x.id: x for x in s.scalars(select(Resource))}
    departments = {
        "actor": "Артисты",
        "assistant": "Помреж",
        "conductor": "Дирижёр",
        "orchestra": "Оркестр",
        "sound": "Звук",
        "light": "Свет",
        "video": "Видео",
    }
    if key in departments or key in [
        "equipment",
        "maintenance",
        "venue",
        "vacation",
        "travel",
    ]:
        if key in departments or key in ["vacation", "travel"]:
            department = departments.get(
                key, "Артисты" if key == "vacation" else "Звук"
            )
            rid = next(
                a["actual_id"]
                for a in plan["assignments"]
                if a["department"] == department
            )
        elif key == "venue":
            rid = v.id
        else:
            rid = next(
                b["resource_id"] for b in plan["bookings"] if b["kind"] == "Equipment"
            )
        b = next(b for b in plan["bookings"] if b["resource_id"] == rid)
        start = datetime.fromisoformat(b["start"])
        end = datetime.fromisoformat(b["end"])
        eid = None
        if key not in ["maintenance", "vacation"]:
            other = (
                s.scalar(
                    select(Resource).where(
                        Resource.kind == "Venue", Resource.name == "ГДК"
                    )
                )
                if key == "travel"
                else v
            )
            if key == "travel":
                end = start - timedelta(minutes=20)
                start = end - timedelta(hours=2)
            ev = Event(
                production_id=p.id,
                venue_id=other.id,
                title="Проверочная занятость: " + case[1],
                kind="Репетиция",
                start=start,
                end=end,
                data={},
            )
            s.add(ev)
            s.flush()
            eid = ev.id
        s.add(
            Booking(
                event_id=eid,
                resource_id=rid,
                start=start,
                end=end,
                label=case[1],
                state="maintenance"
                if key == "maintenance"
                else "absence"
                if key == "vacation"
                else "reserved",
            )
        )
    elif key == "setup":
        r = r.model_copy(update={"start": datetime(2026, 11, 10, 9)})
    elif key == "qualification":
        r = r.model_copy(
            update={
                "replacements": {
                    str(p.data["responsibles"]["Звук"]): p.data["roles"][0]["B"]
                }
            }
        )
    elif key == "orchestra_missing":
        p.data = {
            **p.data,
            "groups": {**p.data["groups"], "Оркестр": p.data["groups"]["Оркестр"][:-1]},
        }
    elif key in ["soffits", "bars"]:
        kind = "Soffit" if key == "soffits" else "Fly Bar"
        matched = [
            x
            for x in resources.values()
            if x.kind == kind and x.data.get("venue_id") == v.id
        ]
        for x in matched[1:] if key == "soffits" else matched:
            x.status = "broken"
    elif key == "scenery":
        obj = resources[p.data["scenery"][0]]
        obj.data = {**obj.data, "width": v.data["width"] + 1}
    else:
        attr = {
            "fly": "fly_system",
            "load": "bar_load",
            "power": "power",
            "dmx": "dmx",
            "height": "height",
            "gate": "gate_width",
        }[key]
        v.data = {**v.data, attr: False if key == "fly" else 1}
    s.flush()
    result = preview(s, r)
    result["demo_scenario"] = {
        "key": key,
        "name": case[1],
        "expected_code": case[2],
        "detected": any(c["code"] == case[2] for c in result["conflicts"]),
    }
    return result
