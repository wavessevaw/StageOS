from __future__ import annotations
from datetime import datetime, timedelta
import hashlib, json
from copy import deepcopy
from collections import defaultdict
from typing import Literal
from pydantic import BaseModel, Field, field_validator, StrictInt
from sqlalchemy import select, delete
from ortools.sat.python import cp_model
from .models import Resource, Production, Event, Booking, Task, Audit
from .production_editor import cast_people


class TaskTiming(BaseModel):
    start: datetime | None = None
    duration: int | None = Field(default=None, ge=1, le=10080)

    @field_validator("start")
    @classmethod
    def local(cls, v):
        if v and v.tzinfo: raise ValueError("Только локальное время")
        return v.replace(second=0, microsecond=0) if v else v


class ExtraTask(BaseModel):
    name: str = Field(min_length=1,max_length=100)
    department: str = Field(default='Все',min_length=1,max_length=40)
    start: datetime
    duration: StrictInt = Field(ge=1,le=10080)
    after: str | None = None
    before: str | None = None

    @field_validator('name','department')
    @classmethod
    def trimmed(cls,v):
        if not v.strip():raise ValueError('Заполните название и подразделение')
        return v.strip()

    @field_validator('start')
    @classmethod
    def local(cls,v):
        if v.tzinfo:raise ValueError('Только локальное время')
        return v.replace(second=0,microsecond=0)


class Request(BaseModel):
    production_id: StrictInt = Field(gt=0)
    venue_id: StrictInt = Field(gt=0)
    start: datetime
    kind: Literal[
        "Спектакль",
        "Репетиция",
        "Генеральная репетиция",
        "Техническая репетиция",
        "Концерт",
        "Выездное мероприятие",
        "Монтаж",
    ] = "Спектакль"
    cast: Literal["A", "B"] = "A"
    duration: int | None = Field(default=None, ge=15, le=480)
    scenes: list[StrictInt] = Field(default_factory=list)
    adaptation: bool = True
    replacements: dict[str, StrictInt] = Field(default_factory=dict)
    equipment_kits: list[StrictInt] | None = None
    event_id: int | None = None
    version: int | None = None
    override_reason: str = ""
    force: bool = False
    notes: str = Field(default="", max_length=8000)
    rehearsal_people: list[StrictInt] | None = None
    rehearsal_items: list[StrictInt] = Field(default_factory=list)
    run_through: bool = False
    baseline_plan: bool = False
    task_overrides: dict[str, TaskTiming] = Field(default_factory=dict)
    removed_tasks: list[str] = Field(default_factory=list,max_length=50)
    extra_tasks: list[ExtraTask] = Field(default_factory=list,max_length=50)
    role_assignments: dict[str, StrictInt] = Field(default_factory=dict)

    @field_validator("start")
    @classmethod
    def local_time(cls, v):
        if v.tzinfo:
            raise ValueError("Используйте локальное театральное время без UTC offset")
        return v.replace(second=0, microsecond=0)


def serial(obj):
    return {
        c.name: (
            getattr(obj, c.name).isoformat()
            if isinstance(getattr(obj, c.name), datetime)
            else getattr(obj, c.name)
        )
        for c in obj.__table__.columns
    }


def issue(code, resource, reason, severity="ERROR", **kw):
    return {
        "code": code,
        "resource": resource,
        "reason": reason,
        "severity": severity,
        "solutions": kw.pop("solutions", ["Изменить время, площадку или конфигурацию"]),
        **kw,
    }


def compatibility(s, p, v, adapt=True):
    req = dict(p.data["requirements"])
    ov = p.data.get("overrides", {}).get(str(v.id)) if adapt else None
    if ov:
        req = dict(ov["requirements"])
    scenic_ids = list(dict.fromkeys((ov.get("scenery", p.data["scenery"]) if ov else p.data["scenery"]) + p.data.get("items", [])))
    scenic = [s.get(Resource, rid) for rid in scenic_ids]
    scenic = [x for x in scenic if x and x.kind == "Scenery"]
    flown = [x for x in scenic if x.data.get("fly")]
    req["fly_bars"] = max(req.get("fly_bars", 0), len(flown))
    req["bar_load"] = max([req.get("bar_load", 0)] + [x.data.get("mass", 0) for x in flown])
    issues = []
    checks = []
    labels = {
        "width": "Ширина сцены",
        "depth": "Глубина сцены",
        "height": "Высота",
        "soffits": "Софиты",
        "fly_bars": "Штанкеты",
        "power": "Мощность, кВт",
        "dmx": "Количество световых линий",
        "orchestra": "Места оркестра",
        "bar_load": "Нагрузка подвеса, кг",
        "gate_width": "Ширина ворот",
        "gate_height": "Высота ворот",
        "lighting_positions": "Световые позиции",
    }
    for k, label in labels.items():
        available = v.data.get(k, 0)
        if k in ["soffits", "fly_bars", "lighting_positions"]:
            kind = {
                "soffits": "Soffit",
                "fly_bars": "Fly Bar",
                "lighting_positions": "Lighting Position",
            }[k]
            available = sum(
                1
                for r in s.scalars(select(Resource).where(Resource.kind == kind))
                if r.data.get("venue_id") == v.id
                and not r.data.get("retired",False)
                and r.status not in ["maintenance", "broken"]
            )
        ok = available >= req.get(k, 0)
        checks.append(
            {"name": label, "ok": ok, "required": req.get(k, 0), "available": available}
        )
        if not ok:
            issues.append(
                issue(
                    k,
                    v.name,
                    f"{label}: требуется {req[k]}, доступно {available}",
                    "CRITICAL",
                )
            )
    if req.get("fly_bars", 0) > 0 and not v.data.get("fly_system"):
        issues.append(
            issue("fly_system", v.name, "Верхняя механика отсутствует", "CRITICAL")
        )
    if req.get("moving_fly_bars", 0) > 0 and not v.data.get("movement"):
        issues.append(
            issue(
                "movement",
                v.name,
                "Движение подвесов во время спектакля недоступно",
                "CRITICAL",
            )
        )
    if req.get("video") and not v.data.get("video"):
        issues.append(
            issue(
                "video",
                v.name,
                "Нет стационарного видео. Нужен привозной комплект",
                "WARNING",
            )
        )
    if (
        v.data.get("soffits", 0) < req.get("preferred_soffits", 0)
        and v.data.get("soffits", 0) >= req.get("soffits", 0)
    ):
        issues.append(
            issue(
                "preferred_soffits",
                v.name,
                "Софитов меньше предпочтительного количества",
                "WARNING",
            )
        )
    if req.get("pa") and not v.data.get("pa"):
        issues.append(issue("pa", v.name, "Нет стационарной звуковой системы: проверьте привозной комплект", "WARNING"))
    for item in scenic:
        if any(item.data.get(k, 0) > v.data.get(k, 0) for k in ['width','depth','height']):
            issues.append(issue("scenery", item.name, "Сценография не помещается на сцене", "CRITICAL"))
        for size, gate in [('transport_width','gate_width'),('transport_height','gate_height')]:
            if item.data.get(size,0)>v.data.get(gate,0):
                issues.append(issue(gate,item.name,"Декорация в транспортном виде не проходит в грузовые ворота","CRITICAL"))
    return {
        "version": "INCOMPATIBLE"
        if any(i["severity"] == "CRITICAL" for i in issues)
        else ov["version"]
        if ov
        else "FULL VERSION",
        "checks": checks,
        "conflicts": issues,
        "requirements": req,
        "override": ov,
    }


def pipeline(p, v, start, duration, rehearsal=False):
    if rehearsal:
        return [
            {
                "name": "Подготовка репетиции",
                "department": "Сцена",
                "start": start - timedelta(minutes=30),
                "end": start,
            },
            {
                "name": "Репетиция",
                "department": "Артисты",
                "start": start,
                "end": start + timedelta(minutes=duration),
            },
            {
                "name": "Освобождение зала",
                "department": "Сцена",
                "start": start + timedelta(minutes=duration),
                "end": start + timedelta(minutes=duration + 15),
            },
        ], {"status": "OPTIMAL", "objective": 0}
    d = p.data["pipeline"]
    model = cp_model.CpModel()
    vars = {}
    intervals = {}
    specs = [
        ("Погрузка", "Транспорт", d["load"], []),
        ("Выезд", "Транспорт", v.data["travel"], ["Погрузка"]),
        ("Разгрузка", "Сцена", d["unload"], ["Выезд"]),
        ("Монтаж сцены", "Сцена", d["stage"], ["Разгрузка"]),
        ("Световой монтаж", "Свет", d["lighting"], ["Разгрузка"]),
        ("Звуковой монтаж", "Звук", d["sound"], ["Разгрузка"]),
        ("Видеомонтаж", "Видео", d["video"], ["Разгрузка"]),
        ("RF check", "Звук", d["rf"], ["Звуковой монтаж"]),
        ("Orchestra setup", "Оркестр", d["orchestra"], ["Разгрузка"]),
        (
            "Technical Check",
            "Все",
            d["check"],
            [
                "Монтаж сцены",
                "Световой монтаж",
                "RF check",
                "Видеомонтаж",
                "Orchestra setup",
            ],
        ),
        ("Готовность", "Все", 15, ["Technical Check"]),
    ]
    for name, dept, dur, deps in specs:
        a = model.new_int_var(0, 1440, f"{name}_start")
        b = model.new_int_var(0, 1440, f"{name}_end")
        interval = model.new_interval_var(a, dur, b, name)
        vars[name] = (a, b)
        intervals[name] = interval
        for dep in deps:
            model.add(a >= vars[dep][1])
    model.add(vars["Готовность"][1] == 1440)
    model.add_no_overlap([intervals["Звуковой монтаж"], intervals["RF check"]])
    model.add_cumulative(
        [
            intervals[x]
            for x in [
                "Монтаж сцены",
                "Световой монтаж",
                "Звуковой монтаж",
                "Видеомонтаж",
            ]
        ],
        [4, 3, 2, 1],
        10,
    )
    model.maximize(sum(x[0] for x in vars.values()))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 2
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise ValueError("Производственный план не помещается в сутки")
    origin = start - timedelta(days=1)
    tasks = [
        {
            "name": n,
            "department": dept,
            "start": origin + timedelta(minutes=solver.value(vars[n][0])),
            "end": origin + timedelta(minutes=solver.value(vars[n][1])),
        }
        for n, dept, _, _ in specs
    ]
    end = start + timedelta(minutes=duration)
    tasks += [
        {"name": "Спектакль", "department": "Все", "start": start, "end": end},
        {
            "name": "Демонтаж",
            "department": "Все",
            "start": end + timedelta(minutes=10),
            "end": end + timedelta(minutes=10 + d["teardown"]),
        },
        {
            "name": "Возврат",
            "department": "Транспорт",
            "start": end + timedelta(minutes=10 + d["teardown"]),
            "end": end + timedelta(minutes=10 + d["teardown"] + v.data["travel"]),
        },
    ]
    return sorted(tasks, key=lambda x: x["start"]), {
        "status": solver.status_name(status),
        "objective": solver.objective_value,
    }


def availability(s, resources, bookings, venue_id, event_id=None, meal_breaks=()):
    first = min(b["start"] for b in bookings.values())
    last = max(b["end"] for b in bookings.values())
    horizon = timedelta(minutes=max([240] + [x.data.get("travel",0) for x in resources.values() if x.kind == "Venue"]))
    conflicts = []
    allbookings = list(
        s.scalars(
            select(Booking).where(
                Booking.end > first - horizon,
                Booking.start < last + horizon,
            )
        )
    )
    for rid, b in bookings.items():
        obj = resources[rid]
        if obj.kind == "Room":
            parent=resources.get(obj.data.get("venue_id"))
            if parent and parent.status in ["maintenance","broken"]:
                conflicts.append(issue("resource_status",parent.name,"Площадка помещения недоступна",resource_id=parent.id))
            for block in allbookings:
                if block.event_id is None and block.resource_id == obj.data.get("venue_id") and max(block.start,b["start"])<min(block.end,b["end"]):
                    conflicts.append(issue(block.state,obj.name,"Площадка помещения: "+block.label,resource_id=rid,busy=[block.start.isoformat(),block.end.isoformat()],required=[b["start"].isoformat(),b["end"].isoformat()]))
        if obj.status in ["maintenance", "broken"] or obj.data.get("retired"):
            conflicts.append(
                issue(
                    "resource_status",
                    obj.name,
                    f"Ресурс: {obj.status}",
                    resource_id=rid,
                )
            )
        if obj.status == "limited_use":
            conflicts.append(
                issue(
                    "limited_use",
                    obj.name,
                    "Ограниченное использование",
                    "WARNING",
                    resource_id=rid,
                )
            )
        for old in allbookings:
            if old.resource_id != rid or (
                event_id is not None and old.event_id == event_id
            ):
                continue
            overlap = max(old.start, b["start"]) < min(old.end, b["end"])
            if overlap:
                other = s.get(Event, old.event_id) if old.event_id else None
                conflicts.append(
                    issue(
                        "overlap" if old.event_id else old.state,
                        obj.name,
                        f"{obj.name}: {old.label}",
                        resource_id=rid,
                        other_event_id=old.event_id,
                        current_event=other.title if other else old.label,
                        venue=resources[other.venue_id].name if other else "",
                        busy=[old.start.isoformat(), old.end.isoformat()],
                        required=[b["start"].isoformat(), b["end"].isoformat()],
                        overlap=[
                            max(old.start, b["start"]).isoformat(),
                            min(old.end, b["end"]).isoformat(),
                        ],
                    )
                )
            elif old.event_id and obj.kind in ["Person", "Equipment", "Vehicle"]:
                other = s.get(Event, old.event_id)
                if other and other.venue_id != venue_id:
                    travel = max(
                        resources[venue_id].data.get("travel", 0),
                        resources[other.venue_id].data.get("travel", 0),
                    )
                    gap = (
                        b["start"] - old.end
                        if old.end <= b["start"]
                        else old.start - b["end"]
                    ).total_seconds() / 60
                    if gap < travel:
                        conflicts.append(
                            issue(
                                "travel",
                                obj.name,
                                f"Переезд: есть {int(gap)} мин, требуется {travel}",
                                resource_id=rid,
                                other_event_id=old.event_id,
                                busy=[old.start.isoformat(), old.end.isoformat()],
                                required=[b["start"].isoformat(), b["end"].isoformat()],
                            )
                        )
    for rid, b in bookings.items():
        if (
            resources[rid].kind == "Person"
            and (b["end"] - b["start"]).total_seconds() > 12 * 3600
            # This warning describes an uninterrupted shift. A real lunch
            # interval inside this person's call window interrupts it.
            and not any(b["start"] < a < z < b["end"] for a, z in meal_breaks)
        ):
            conflicts.append(
                issue(
                    "long_shift",
                    resources[rid].name,
                    "Смена более 12 часов",
                    "WARNING",
                    resource_id=rid,
                )
            )
    return conflicts


def preview(s, r: Request, production_data=None):
    p = s.get(Production, r.production_id)
    v = s.get(Resource, r.venue_id)
    if not p or not v or v.kind not in ["Venue", "Room"]:
        raise ValueError("Постановка или площадка не найдена")
    if v.kind == "Room":
        if r.kind != "Репетиция":
            raise ValueError("Помещение доступно только для репетиции")
        parent = s.get(Resource, v.data["venue_id"])
        if not parent or parent.kind != "Venue":raise ValueError("Площадка помещения не найдена")
        v = Resource(id=v.id, name=v.name, kind="Room", data={**parent.data, **v.data})
    if production_data is not None:
        p = Production(id=p.id, name=p.name, version=p.version, data=deepcopy(production_data))
    valid_replacements=set(p.data["responsibles"].values())
    for role in p.data["roles"]:valid_replacements.add(role[r.cast])
    for group in ["groups","crew"]:
        for ids in cast_people(p.data,group,r.cast).values():valid_replacements.update(ids)
    for ov in p.data.get("overrides",{}).values():valid_replacements.update(ov.get("orchestra",[]))
    valid_replacements.update(r.rehearsal_people or [])
    if any(not key.isdecimal() or int(key) not in valid_replacements for key in r.replacements):
        raise ValueError("Замена ссылается на отсутствующую позицию состава")
    if any(k not in {str(i) for i in range(len(p.data['roles']))} or v<=0 for k,v in r.role_assignments.items()):
        raise ValueError('Неизвестная роль или неверный исполнитель события')
    rehearsal = r.kind == "Репетиция"
    duration = r.duration if r.duration is not None else 120 if rehearsal else p.data['duration']
    if any(i < 0 or i >= len(p.data["scenes"]) for i in r.scenes):
        raise ValueError("Неизвестная сцена")
    comp = (
        {
            "version": "REHEARSAL",
            "checks": [],
            "conflicts": [],
            "override": None,
            "requirements": {},
        }
        if rehearsal
        else compatibility(s, p, v, r.adaptation)
    )
    tasks, solver = pipeline(p, v, r.start, duration, rehearsal)
    if r.baseline_plan and not rehearsal:
        from .day_plan import baseline
        tasks = baseline(tasks, r.start, duration, r.run_through)
    elif r.run_through and not rehearsal:
        morning = r.start.replace(hour=11, minute=0)
        prep, _ = pipeline(p, v, morning, duration)
        tasks = [t for t in prep if t['name'] not in ['Спектакль','Демонтаж','Возврат']] + [t for t in tasks if t['name'] in ['Спектакль','Демонтаж','Возврат']]
        tasks += [
            {'name':'Прогон','department':'Все','start':morning,'end':morning+timedelta(hours=3)},
            {'name':'Обед','department':'Все','start':morning+timedelta(hours=3),'end':morning+timedelta(hours=4)},
            {'name':'Сбор перед спектаклем','department':'Все','start':r.start-timedelta(hours=1),'end':r.start},
        ]
    from .timing import customize, retime
    tasks, dependencies = customize(tasks,r.removed_tasks,r.extra_tasks)
    if r.task_overrides or r.run_through or r.baseline_plan or r.removed_tasks or r.extra_tasks:
        overrides={**{t.name:TaskTiming(start=t.start,duration=t.duration) for t in r.extra_tasks},**r.task_overrides}
        tasks, solver = retime(tasks,overrides,r.start,r.run_through,dependencies)
    performance_call = min([t['start'] for t in tasks if t['name']=='Прогон'] or [r.start])
    first = min(t["start"] for t in tasks)
    last = max(t["end"] for t in tasks)
    end = r.start + timedelta(minutes=duration)
    conflicts = list(comp["conflicts"])
    bookings = {}
    assignments = []
    resources = {x.id: x for x in s.scalars(select(Resource))}

    def book(rid, a, b, label):
        if rid not in resources:
            raise ValueError(f"Ресурс {rid} не существует")
        if rid in bookings:
            bookings[rid]["start"] = min(a, bookings[rid]["start"])
            bookings[rid]["end"] = max(b, bookings[rid]["end"])
        else:
            bookings[rid] = {"resource_id": rid, "start": a, "end": b, "label": label}

    def assign(rid, role, dept, a, b, eligible=None, role_index=None):
        selected=r.role_assignments.get(str(role_index)) if role_index is not None else None
        if not rid and selected is None:
            if rehearsal and r.rehearsal_people is not None:return
            conflicts.append(issue("unassigned",role,"Не назначен исполнитель выбранного состава","ERROR"))
            return
        actual = selected if selected is not None else r.replacements.get(str(rid), rid)
        if rehearsal and r.rehearsal_people is not None and actual not in r.rehearsal_people:
            return
        person = resources.get(actual)
        if not person or person.kind != "Person":
            raise ValueError("Замена должна быть сотрудником")
        allowed = dept in person.data.get("qualification", []) and (eligible is None or actual in eligible)
        if not allowed:
            conflicts.append(
                issue(
                    "qualification",
                    person.name,
                    f"Нет квалификации для {role}",
                    "ERROR",
                )
            )
        duplicates = [x for x in assignments if x["actual_id"] == actual and
                      (x["responsible_id"] != rid or x["role"] != role)]
        if duplicates:
            actor_overlap = dept == "Артисты" and any(x["department"] == "Артисты" for x in duplicates)
            conflicts.append(issue("multiple_roles", person.name,
                "Один артист назначен на разные роли" if actor_overlap else
                "Совмещение обязанностей: проверьте возможность выполнения одним сотрудником",
                "ERROR" if actor_overlap else "WARNING"))
        assignments.append(
            {
                "role": role,
                "department": dept,
                "responsible_id": rid,
                "responsible": resources[rid].name if rid in resources else "Не назначен",
                "role_index": role_index,
                "actual_id": actual,
                "actual": person.name,
                "eligible_ids": eligible if eligible is not None else [x.id for x in resources.values() if x.kind == "Person" and dept in x.data.get("qualification", [])],
                "call": a.isoformat(),
            }
        )
        book(actual, a, b, role)

    techstart = min(t["start"] for t in tasks if t["department"] != "Транспорт")
    techend = max(t["end"] for t in tasks if t["department"] != "Транспорт")
    for dept, rid in p.data["responsibles"].items():
        if rehearsal and dept not in ["Режиссёр", "Помреж", "Дирижёр"]:
            continue
        a = (
            performance_call - timedelta(minutes=30 if rehearsal else 60)
            if dept in ["Режиссёр", "Дирижёр"]
            else techstart
        )
        assign(rid, dept, dept, a, end if dept in ["Режиссёр", "Дирижёр"] else techend)
    indices = (
        sorted({j for i in r.scenes for j in p.data["scenes"][i]["roles"]})
        if rehearsal and r.scenes
        else range(len(p.data["roles"]))
    )
    for i in indices:
        role = p.data["roles"][i]
        assign(
            role[r.cast],
            role["role"],
            "Артисты",
            performance_call - timedelta(minutes=15 if rehearsal else 90),
            end,
            role["eligible"] or None,
            role_index=i,
        )
    groupids = cast_people(p.data,"groups",r.cast)
    if comp["override"]:
        groupids["Оркестр"] = comp["override"]["orchestra"]
    if rehearsal and r.scenes:
        groupids = {}
    for dept, ids in groupids.items():
        for rid in ids:
            spec = resources[rid].data.get("specialization", resources[rid].department)
            eligible = [
                x.id
                for x in resources.values()
                if x.kind == "Person"
                and x.department == dept
                and x.data.get("specialization", x.department) == spec
            ]
            call = performance_call - timedelta(minutes=15 if rehearsal else 60)
            if dept == "Оркестр" and not rehearsal:
                call = min([call] + [t["start"] for t in tasks if t["name"] == "Orchestra setup"])
            assign(
                rid,
                spec,
                dept,
                call,
                end,
                eligible,
            )
    if rehearsal and r.rehearsal_people is not None:
        if not r.rehearsal_people: raise ValueError("Выберите хотя бы одного участника репетиции")
        for rid in dict.fromkeys(r.rehearsal_people):
            person=resources.get(rid)
            if not person or person.kind!="Person":raise ValueError("Участник репетиции должен быть сотрудником")
            if not any(a['actual_id']==rid for a in assignments):
                assign(rid,person.data.get('specialization',person.department),person.department,techstart if person.department in ['Звук','Свет','Видео','Сцена','Монтаж','Риггинг','Техдир','Транспорт','Реквизит'] else r.start-timedelta(minutes=15),techend if person.department in ['Звук','Свет','Видео','Сцена','Монтаж','Риггинг','Техдир','Транспорт','Реквизит'] else end,[rid])
    for rid in (r.rehearsal_items if rehearsal else p.data.get('items',[])):
        item=resources.get(rid)
        if not item or item.kind not in ['Equipment','Scenery','Prop','Costume']:raise ValueError('Неизвестная позиция имущества')
        book(rid,first,last,item.name)
        if item.kind=='Scenery' and (item.data.get('width',0)>v.data.get('width',0) or item.data.get('height',0)>v.data.get('height',0) or item.data.get('depth',0)>v.data.get('depth',0)):
            conflicts.append(issue('scenery',item.name,'Декорация не помещается на сцене','CRITICAL'))
    if not rehearsal:
        for dept, ids in cast_people(p.data,"crew",r.cast).items():
            for rid in ids:
                assign(rid, f"{dept} · техник", dept, first if dept == "Транспорт" else techstart, last if dept == "Транспорт" else techend)
        for kitid in (
            r.equipment_kits
            if r.equipment_kits is not None
            else p.data["equipment_kits"]
        ):
            kit = resources.get(kitid)
            if not kit or kit.kind != "Equipment Kit":
                raise ValueError("Неверный Equipment Kit")
            book(kitid, first, last, kit.name)
            for rid in kit.data["items"]:
                book(rid, first, last, kit.name)
        if r.equipment_kits is not None:
            supplied = {resources[i].department for i in r.equipment_kits}
            required_departments = {resources[i].department for i in p.data["equipment_kits"]}
            if not required_departments <= supplied:
                conflicts.append(
                    issue(
                        "kit_missing",
                        p.name,
                        "Не представлены все требуемые цехами комплекты оборудования",
                    )
                )
        for rid in (
            (
                comp["override"].get("scenery", p.data["scenery"])
                if comp["override"]
                else p.data["scenery"]
            )
            + p.data["props"]
            + ([p.data["vehicle"]] if p.data.get("vehicle") else [])
        ):
            book(rid, first, last, resources[rid].name)
        for kind, key in [
            ("Fly Bar", "fly_bars"),
            ("Soffit", "soffits"),
            ("Lighting Position", "lighting_positions"),
        ]:
            required = comp["requirements"].get(key, 0)
            candidates = [
                x
                for x in resources.values()
                if x.kind == kind
                and x.data.get("venue_id") == v.id
                and not x.data.get("retired",False)
                and x.status not in ["maintenance", "broken"]
            ]
            candidates.sort(key=lambda x: x.id)
            if kind == "Fly Bar":
                candidates = [
                    x
                    for x in candidates
                    if x.data.get("capacity", 0) - x.data.get("current_load", 0)
                    >= comp["requirements"].get("bar_load", 0)
                    and x.data.get("scenery_allowed", False)
                ]
                if sum(bool(x.data.get("movement")) for x in candidates) < comp[
                    "requirements"
                ].get("moving_fly_bars", 0):
                    conflicts.append(
                        issue(
                            "moving_bar_count",
                            v.name,
                            "Недостаточно доступных подвижных штанкетов",
                            "CRITICAL",
                        )
                    )
                candidates.sort(key=lambda x: (not x.data.get("movement", False), x.id))
                if len(candidates) < required:
                    conflicts.append(
                        issue(
                            "bar_capacity",
                            v.name,
                            "Недостаточно штанкетов с допустимой остаточной нагрузкой",
                            "CRITICAL",
                        )
                    )
            for x in candidates[:required]:
                book(x.id, techstart, techend, x.name)
    for task in r.extra_tasks:
        planned=next(t for t in tasks if t['name']==task.name)
        for a in assignments:
            if task.department=='Все' or a['department']==task.department:
                book(a['actual_id'],planned['start'],planned['end'],a['role'])
                a['call']=min(a['call'],planned['start'].isoformat())
    book(v.id, techstart, techend, v.name)
    opening = techstart.replace(hour=0,minute=0) + timedelta(hours=v.data.get("opening", 8))
    closing = techend.replace(hour=0,minute=0) + timedelta(hours=v.data.get("closing", 24))
    if techstart < opening:
        conflicts.append(
            issue(
                "setup",
                v.name,
                f"Монтаж начинается {techstart:%H:%M}, площадка открывается в {v.data.get('opening', 8)}:00",
            )
        )
    if techend > closing:
        conflicts.append(issue("closing",v.name,"Работы не завершаются до закрытия площадки"))
    if rehearsal and v.kind == "Room" and len({a["actual_id"] for a in assignments}) > v.data.get("capacity", 0):
        conflicts.append(issue("room_capacity", v.name, "Участники не помещаются в репетиционном помещении"))
    if techend.date() > r.start.date():
        conflicts.append(
            issue(
                "teardown",
                v.name,
                "Демонтаж выходит за пределы рабочего дня",
                "WARNING",
            )
        )
    if len(groupids.get("Оркестр", [])) < comp.get("requirements", {}).get(
        "orchestra", 0
    ):
        conflicts.append(issue("orchestra_missing", p.name, "Оркестр не укомплектован"))
    meals = [(t['start'], t['end']) for t in tasks if t['name'] == 'Обед']
    conflicts.extend(availability(s, resources, bookings, v.id, r.event_id, meals))
    if not assignments and r.kind != "Монтаж":
        conflicts.append(issue("empty_people",p.name,"В постановке или репетиции не назначены участники"))
    status = (
        "CONFLICT"
        if any(c["severity"] in ["ERROR", "CRITICAL"] for c in conflicts)
        else "WARNING"
        if conflicts
        else "READY"
    )
    result = {
        "request": r.model_dump(mode="json"),
        "production_snapshot": deepcopy(p.data),
        "production_version": p.version,
        "notes": r.notes,
        "forced": r.force,
        "title": p.name,
        "venue": v.name,
        "start": r.start.isoformat(),
        "end": end.isoformat(),
        "status": status,
        "compatibility": comp,
        "assignments": assignments,
        "event_roles": [dict(index=i,role=role['role'],baseline_id=role[r.cast],
                             actual_id=next((a['actual_id'] for a in assignments if a.get('role_index')==i),None),
                             eligible_ids=role['eligible']) for i,role in enumerate(p.data['roles']) if i in indices],
        "tasks": [
            {**t, "start": t["start"].isoformat(), "end": t["end"].isoformat()}
            for t in tasks
        ],
        "bookings": [
            {
                **b,
                "name": resources[b["resource_id"]].name,
                "kind": resources[b["resource_id"]].kind,
                "start": b["start"].isoformat(),
                "end": b["end"].isoformat(),
            }
            for b in bookings.values()
        ],
        "conflicts": conflicts,
        "solver": solver,
        "penalty": sum(10 for a in assignments if a["responsible_id"] != a["actual_id"])
        + (20 if comp["override"] else 0)
        + sum(3 for c in conflicts if c["severity"] == "WARNING"),
    }
    result["fingerprint"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return result


def save_plan(s, r, result, allow_demo=False):
    if not allow_demo:
        if any(c["severity"] == "CRITICAL" for c in result["conflicts"]) and not r.force:
            raise ValueError("Физическая несовместимость: назначение запрещено")
        if (r.force or result["status"] == "CONFLICT") and len(r.override_reason.strip()) < 12:
            raise ValueError(
                "Конфликты требуют обоснования администратора или художественного руководителя (минимум 12 символов)"
            )
    old = s.get(Event, r.event_id) if r.event_id else None
    if r.event_id and not old:
        raise ValueError("Событие не найдено")
    if old and old.status in ["Cancelled", "Completed", "In Progress"]:
        raise ValueError("Завершённое, отменённое или идущее событие нельзя перепланировать")
    if old and s.scalar(select(Task.id).where(Task.event_id == old.id, Task.actual_start != None).limit(1)):
        raise ValueError("Событие содержит фактические работы: перепланирование уничтожило бы план/факт")
    if old and old.version != r.version:
        raise ValueError("Событие изменилось. Откройте свежий Preview")
    before = serial(old) if old else None
    if old:
        s.execute(delete(Booking).where(Booking.event_id == old.id))
        s.execute(delete(Task).where(Task.event_id == old.id))
        ev = old
        ev.version += 1
    else:
        ev = Event()
        s.add(ev)
    ev.production_id = r.production_id
    ev.venue_id = r.venue_id
    ev.title = result["title"]
    ev.kind = r.kind
    ev.start = r.start
    ev.end = datetime.fromisoformat(result["end"])
    if not old: ev.status = "Approved"
    ev.data = {
        "request": r.model_dump(mode="json"),
        "plan": result,
        "layer": "PLANNED",
        "demo_exception": allow_demo,
    }
    s.flush()
    for b in result["bookings"]:
        s.add(
            Booking(
                event_id=ev.id,
                resource_id=b["resource_id"],
                start=datetime.fromisoformat(b["start"]),
                end=datetime.fromisoformat(b["end"]),
                label=ev.title + " · " + b["label"],
            )
        )
    for t in result["tasks"]:
        s.add(
            Task(
                event_id=ev.id,
                name=t["name"],
                department=t["department"],
                start=datetime.fromisoformat(t["start"]),
                end=datetime.fromisoformat(t["end"]),
            )
        )
    s.add(
        Audit(
            event_id=ev.id,
            action="Изменено" if before else "Создано",
            data={"before": before, "after": serial(ev), "reason": r.override_reason},
        )
    )
    s.flush()
    return ev


def substitutions(s, r):
    plan = preview(s, r)
    p = s.get(Production, r.production_id)
    resources = {x.id: x for x in s.scalars(select(Resource))}
    options = {}
    model = cp_model.CpModel()
    terms = []
    intervals = defaultdict(list)
    variables = {}
    processed = set()
    for a in plan["assignments"]:
        rid = f"role:{a['role_index']}" if a.get('role_index') is not None else a["responsible_id"]
        if rid in processed:continue
        processed.add(rid)
        eligible = [resources[cid] for cid in a['eligible_ids'] if cid in resources and resources[cid].kind == 'Person']
        b = next(x for x in plan["bookings"] if x["resource_id"] == a["actual_id"])
        start = datetime.fromisoformat(b["start"])
        end = datetime.fromisoformat(b["end"])
        vars = []
        options[str(rid)] = []
        for candidate in eligible:
            busy = s.scalars(
                select(Booking).where(
                    Booking.resource_id == candidate.id,
                    Booking.start < end + timedelta(minutes=60),
                    Booking.end > start - timedelta(minutes=60),
                )
            ).all()
            if (
                any(x.event_id != r.event_id or r.event_id is None for x in busy)
                or candidate.status != "available"
            ):
                continue
            if a["department"] not in candidate.data.get("qualification",[]):continue
            flag = model.new_bool_var(f"{rid}_{candidate.id}")
            vars.append(flag)
            variables[(rid, candidate.id)] = flag
            st = int(start.timestamp() / 60)
            dur = int((end - start).total_seconds() / 60)
            intervals[candidate.id].append(
                model.new_optional_interval_var(
                    st, dur, st + dur, flag, f"person_{rid}_{candidate.id}"
                )
            )
            penalty = 0 if candidate.id == a["actual_id"] else 10
            terms.append(flag * penalty)
            options[str(rid)].append(
                {"id": candidate.id, "name": candidate.name, "penalty": penalty}
            )
        if vars:
            model.add_exactly_one(vars)
        else:
            model.add_bool_or([])
    for val in intervals.values():
        model.add_no_overlap(val)
    model.minimize(sum(terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 3
    solver.parameters.num_search_workers = 1
    status = solver.solve(model)
    mapping = {
        str(rid): cid
        for (rid, cid), flag in variables.items()
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE] and solver.value(flag)
    }
    role_mapping={k.split(':',1)[1]:v for k,v in mapping.items() if k.startswith('role:')}
    legacy_mapping={k:v for k,v in mapping.items() if not k.startswith('role:')}
    # Keep legacy actor replacement output for existing integrations.
    for a in plan['assignments']:
        if a.get('role_index') is not None and str(a['role_index']) in role_mapping and a['responsible_id']:
            legacy_mapping[str(a['responsible_id'])]=role_mapping[str(a['role_index'])]
    return {
        "status": solver.status_name(status),
        "options": options,
        "replacements": legacy_mapping,
        "role_assignments": role_mapping,
        "plan": preview(s, r.model_copy(update={"replacements": legacy_mapping,"role_assignments":role_mapping}))
        if mapping
        else None,
    }

def saved_event_plan(s, ev):
    """Display committed assignments/tasks; recheck current resource availability only."""
    plan = deepcopy(ev.data['plan'])
    req = {**ev.data['request'], 'event_id':ev.id, 'version':ev.version}
    if req.get('duration') is not None:
        req['duration'] = int((ev.end-ev.start).total_seconds()/60)
    plan['request'] = req
    resources = {x.id:x for x in s.scalars(select(Resource))}
    stored = list(s.scalars(select(Booking).where(Booking.event_id==ev.id)))
    bs = {b.resource_id:dict(resource_id=b.resource_id,start=b.start,end=b.end,label=b.label) for b in stored}
    dynamic = {'overlap','travel','resource_status','limited_use','long_shift','absence','maintenance','vacation','sick','training','unavailable'}
    conflicts = [c for c in plan['conflicts'] if c['code'] not in dynamic and 'busy' not in c]
    meals = [(datetime.fromisoformat(t['start']), datetime.fromisoformat(t['end'])) for t in plan['tasks'] if t['name'] == 'Обед']
    if bs: conflicts.extend(availability(s,resources,bs,ev.venue_id,ev.id,meals))
    snapshot = plan.get('production_snapshot')
    current = s.get(Production,ev.production_id)
    plan['passport_changed'] = bool(snapshot and snapshot != current.data)
    if snapshot and ev.kind!='Репетиция':
        production = Production(id=current.id,name=ev.title,data=snapshot)
        venue=resources[ev.venue_id]
        comp=compatibility(s,production,venue,req.get('adaptation',True))
        old_codes={c['code'] for c in plan['compatibility']['conflicts']}
        conflicts=[c for c in conflicts if c['code'] not in old_codes]
        conflicts.extend(comp['conflicts']);plan['compatibility']=comp
    # Recheck the committed bookings against today's passports, without reallocating.
    if bs:
        venue=resources[ev.venue_id]
        site=resources.get(venue.data.get('venue_id')) if venue.kind=='Room' else venue
        site_data={**(site.data if site else {}),**venue.data}
        venue_booking=bs.get(ev.venue_id)
        if venue_booking:
            first_day=venue_booking['start'].replace(hour=0,minute=0)
            last_day=venue_booking['end'].replace(hour=0,minute=0)
            conflicts=[c for c in conflicts if c['code'] not in ['setup','closing','room_capacity']]
            if venue_booking['start']<first_day+timedelta(hours=site_data.get('opening',8)):
                conflicts.append(issue('setup',venue.name,'Подготовка начинается до открытия площадки'))
            if venue_booking['end']>last_day+timedelta(hours=site_data.get('closing',24)):
                conflicts.append(issue('closing',venue.name,'Работы завершаются после закрытия площадки'))
            if venue.kind=='Room' and len({a['actual_id'] for a in plan['assignments']})>site_data.get('capacity',0):
                conflicts.append(issue('room_capacity',venue.name,'Участники не помещаются в помещении'))
        conflicts=[c for c in conflicts if c['code'] not in ['qualification','bar_capacity','moving_bar_count']]
        for a in plan['assignments']:
            person=resources.get(a['actual_id'])
            if not person or a['department'] not in person.data.get('qualification',[]):
                conflicts.append(issue('qualification',a['actual'],'Нет действующей квалификации для '+a['role'],resource_id=a['actual_id']))
        requirements=plan['compatibility'].get('requirements',{})
        bars=[resources[rid] for rid in bs if resources[rid].kind=='Fly Bar']
        for bar in bars:
            if (bar.data.get('capacity',0)-bar.data.get('current_load',0)<requirements.get('bar_load',0)
                    or not bar.data.get('scenery_allowed',False) or bar.data.get('venue_id')!=ev.venue_id):
                conflicts.append(issue('bar_capacity',bar.name,'Назначенный штанкет больше не соответствует нагрузке или площадке','CRITICAL',resource_id=bar.id))
        if sum(bool(b.data.get('movement')) for b in bars)<requirements.get('moving_fly_bars',0):
            conflicts.append(issue('moving_bar_count',venue.name,'Назначенные штанкеты не обеспечивают нужное движение','CRITICAL'))
    plan['conflicts']=conflicts
    plan['status']='CONFLICT' if any(c['severity'] in ['ERROR','CRITICAL'] for c in conflicts) else 'WARNING' if conflicts else 'READY'
    plan['tasks']=[{'name':t.name,'department':t.department,'start':t.start.isoformat(),'end':t.end.isoformat()} for t in s.scalars(select(Task).where(Task.event_id==ev.id).order_by(Task.start))]
    plan['title']=ev.title
    return plan
