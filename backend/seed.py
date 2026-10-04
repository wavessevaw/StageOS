from datetime import datetime, timedelta
from sqlalchemy import select
from .models import Resource, Production, Booking, Setting

DEPTS = {
    "Оркестр": 35,
    "Хор": 24,
    "Балет": 16,
    "Артисты": 20,
    "Звук": 8,
    "Свет": 8,
    "Видео": 7,
    "Сцена": 12,
    "Помреж": 5,
    "Техдир": 3,
    "Режиссёр": 3,
    "Дирижёр": 3,
    "Грим": 4,
    "Костюм": 4,
}
INSTRUMENTS = (
    ["Violin I"] * 6
    + ["Violin II"] * 5
    + ["Viola"] * 3
    + ["Cello"] * 3
    + ["Double Bass"] * 2
    + ["Flute"] * 2
    + ["Oboe", "Clarinet", "Bassoon"]
    + ["Horn"] * 2
    + ["Trumpet"] * 2
    + ["Trombone", "Tuba", "Percussion", "Percussion", "Harp", "Keyboard", "Clarinet"]
)
NAMES = [
    "Алексей",
    "Дмитрий",
    "Роман",
    "Игорь",
    "Антон",
    "Виктор",
    "Александр",
    "Павел",
    "Михаил",
    "Олег",
    "Марина",
    "Елена",
    "Анна",
    "Софья",
    "Ирина",
    "Ольга",
]
SURNAMES = [
    "Петров",
    "Белов",
    "Соколов",
    "Лапин",
    "Коршунов",
    "Морозов",
    "Кравцов",
    "Гринёв",
    "Яровой",
    "Волков",
    "Лебедев",
    "Орлов",
    "Миронов",
    "Крылов",
    "Лазарев",
    "Фомин",
]


def seed(s):
    if s.scalar(select(Production.id).limit(1)):
        return False
    groups = {}
    for d, n in DEPTS.items():
        groups[d] = []
        for i in range(n):
            idx = sum(len(v) for v in groups.values())
            name = f"{SURNAMES[(idx // 16) % 16]} {NAMES[idx % 16]}"
            specialization = (
                INSTRUMENTS[i]
                if d == "Оркестр"
                else ["Soprano", "Alto", "Tenor", "Bass"][i // 6]
                if d == "Хор"
                else ["Principal", "Soloist", "Ensemble", "Reserve"][min(3, i // 4)]
                if d == "Балет"
                else d
            )
            r = Resource(
                kind="Person",
                name=name,
                department=d,
                data={
                    "qualification": [d, specialization],
                    "specialization": specialization,
                    "level": 6 if i < 2 else 4,
                },
            )
            s.add(r)
            s.flush()
            groups[d].append(r.id)
    venues = []
    specs = [
        ("Большой зал", 6, 18, 18, 16, 20, 160, 16, 40, True, 5),
        ("ГДК", 3, 8, 12, 10, 12, 80, 8, 25, True, 40),
        ("Камерный зал", 1, 0, 7, 5, 4, 20, 2, 8, False, 20),
        ("Летняя сцена", 0, 0, 14, 10, 7, 60, 6, 25, False, 60),
        ("Репетиционный зал", 1, 0, 10, 8, 4, 20, 2, 35, False, 5),
        ("ДК Профсоюзов", 4, 10, 14, 12, 14, 100, 10, 32, True, 30),
        ("Зал Совкино", 2, 2, 10, 7, 6, 40, 4, 16, False, 15),
    ]
    for name, so, fly, w, d, h, power, dmx, pit, moving, travel in specs:
        v = Resource(
            kind="Venue",
            name=name,
            department="Площадки",
            data={
                "soffits": so,
                "fly_bars": fly,
                "width": w,
                "depth": d,
                "height": h,
                "power": power,
                "dmx": dmx,
                "orchestra": pit,
                "fly_system": fly > 0,
                "movement": moving,
                "bar_load": 500 if fly > 10 else 200,
                "gate_width": 4 if fly > 10 else 2,
                "gate_height": 5 if fly > 10 else 2.5,
                "travel": travel,
                "pa": True,
                "video": name != "Летняя сцена",
                "rooms": 6,
                "opening": 8,
                "closing": 24,
                "lighting_positions": so + 2,
            },
        )
        s.add(v)
        s.flush()
        venues.append(v)
        for kind, count in [
            ("Fly Bar", fly),
            ("Soffit", so),
            ("Lighting Position", so + 2),
            ("Room", 2),
        ]:
            for i in range(count):
                s.add(
                    Resource(
                        kind=kind,
                        name=f"{name} · {kind} {i + 1}",
                        department="Сцена" if kind == "Fly Bar" else "Свет",
                        data={
                            "venue_id": v.id,
                            "capacity": v.data["bar_load"],
                            "current_load": 0,
                            "movement": moving,
                            "scenery_allowed": True,
                            "lighting_allowed": True,
                        },
                    )
                )
    kits = {}
    for d, n in [
        ("Звук", 40),
        ("Свет", 60),
        ("Видео", 30),
        ("Сцена", 20),
        ("Rigging", 12),
    ]:
        items = []
        types = {
            "Звук": ["Console", "Stagebox", "Wireless", "IEM", "Microphone"],
            "Свет": ["Profile", "Wash", "Moving Head", "Followspot"],
            "Видео": ["Media Server", "Projector", "LED", "Camera", "SDI"],
            "Сцена": ["Platform", "Stand"],
            "Rigging": ["Hoist", "Sling"],
        }
        for i in range(n):
            r = Resource(
                kind="Equipment",
                name=f"{types[d][i % len(types[d])]} {i + 1:02}",
                department=d,
                data={
                    "qualification": [types[d][i % len(types[d])]],
                    "protocol": "Dante / MADI"
                    if d == "Звук"
                    else "DMX / sACN"
                    if d == "Свет"
                    else "NDI / SDI",
                    "capacity": 500,
                },
            )
            s.add(r)
            s.flush()
            items.append(r.id)
        kits[d] = []
        for i in range(2):
            r = Resource(
                kind="Equipment Kit",
                name=f"{d} Kit {'AB'[i]}",
                department=d,
                data={"items": items[i * len(items) // 2 : (i + 1) * len(items) // 2]},
            )
            s.add(r)
            s.flush()
            kits[d].append(r.id)
    vehicles = []
    for i in range(3):
        r = Resource(
            kind="Vehicle",
            name=f"Грузовой фургон {i + 1}",
            department="Транспорт",
            data={"capacity": 3500},
        )
        s.add(r)
        s.flush()
        vehicles.append(r.id)
    names = [
        "Северный ветер",
        "Последний рейс",
        "Белая ночь",
        "Город у моря",
        "Три письма",
        "Золотая ночь",
        "Голоса времени",
        "Дом на площади",
    ]
    prep = [300, 210, 120, 255, 105, 360, 150, 180]
    for i, name in enumerate(names):
        big = i in [0, 3, 5]
        tech = {
            d: groups[d][i % 2]
            for d in [
                "Режиссёр",
                "Дирижёр",
                "Помреж",
                "Техдир",
                "Звук",
                "Свет",
                "Видео",
                "Сцена",
            ]
        }
        roles = [
            {
                "role": x,
                "A": groups["Артисты"][j],
                "B": groups["Артисты"][j + 5],
                "reserve": groups["Артисты"][j + 10],
                "eligible": [
                    groups["Артисты"][j],
                    groups["Артисты"][j + 5],
                    groups["Артисты"][j + 10],
                ],
            }
            for j, x in enumerate(
                ["Александр", "Мария", "Виктор", "Анна", "Рассказчик"]
            )
        ]
        scenic = []
        for j in range(3):
            r = Resource(
                kind="Scenery",
                name=f"{name} · {'Портал Задник Стена'.split()[j]}",
                department="Сцена",
                data={
                    "width": 14 if big else 5,
                    "height": 8 if big else 3,
                    "depth": 2,
                    "mass": 300 if big else 80,
                    "fly": big,
                    "setup": 30,
                    "crew": 4,
                    "installation": "flying" if big else "floor",
                    "gate_width": 3 if big else 1.8,
                    "gate_height": 3.5 if big else 2,
                },
            )
            s.add(r)
            s.flush()
            scenic.append(r.id)
        props = []
        for j, kind in enumerate(["Prop", "Costume"]):
            r = Resource(
                kind=kind,
                name=f"{name} · {'Критический реквизит' if j == 0 else 'Комплект костюмов'}",
                department="Реквизит" if j == 0 else "Костюм",
                data={"critical": True, "quantity": 20},
            )
            s.add(r)
            s.flush()
            props.append(r.id)
        choir = groups["Хор"][:] if big else groups["Хор"][:8] if i == 6 else []
        ballet = groups["Балет"][:12] if big else []
        orchestra = (
            groups["Оркестр"][:] if big else groups["Оркестр"][:12] if i != 4 else []
        )
        required = {
            "width": 14 if big else 6,
            "depth": 12 if big else 4,
            "height": 10 if big else 3,
            "soffits": 5 if i == 5 else 4 if big else 1,
            "preferred_soffits": 6 if big else 2,
            "fly_bars": 5 if big else 0,
            "moving_fly_bars": 2 if big else 0,
            "power": 110 if big else 15,
            "dmx": 12 if big else 2,
            "orchestra": len(orchestra),
            "bar_load": 300 if big else 0,
            "gate_width": 3 if big else 1.8,
            "gate_height": 3.5 if big else 2,
            "lighting_positions": 6 if big else 2,
            "pa": True,
            "video": big,
        }
        data = {
            "genre": "Музыкальный спектакль" if big else "Камерная постановка",
            "duration": 155 if big else 100,
            "preparation": prep[i],
            "home_venue": venues[0].id,
            "responsibles": tech,
            "roles": roles,
            "groups": {
                "Хор": choir,
                "Балет": ballet,
                "Оркестр": orchestra,
                "Грим": groups["Грим"][:2],
                "Костюм": groups["Костюм"][:2],
            },
            "orchestra_versions": {
                "Full": groups["Оркестр"],
                "Reduced": groups["Оркестр"][:20],
                "Touring": groups["Оркестр"][:12],
            },
            "crew": {
                "Сцена": groups["Сцена"][2:6],
                "Звук": groups["Звук"][2:4],
                "Свет": groups["Свет"][2:4],
                "Видео": groups["Видео"][2:3],
            },
            "equipment_kits": [kits[d][i % 2] for d in ["Звук", "Свет", "Видео"]],
            "scenery": scenic,
            "props": props,
            "vehicle": vehicles[i % 3],
            "requirements": required,
            "scenes": [
                {"name": "Сцена 1", "roles": [0, 1]},
                {"name": "Сцена 2", "roles": [2, 3, 4]},
                {"name": "Финал", "roles": [0, 1, 2, 3, 4]},
            ],
            "pipeline": {
                "load": 30,
                "unload": 20,
                "stage": prep[i] - 75,
                "lighting": prep[i] - 65,
                "sound": max(30, prep[i] - 110),
                "video": max(20, prep[i] - 130),
                "rf": 15,
                "orchestra": 20,
                "check": 25,
                "teardown": 90 if big else 45,
            },
            "overrides": {},
        }
        if big:
            reduced = {
                **required,
                "width": 10,
                "depth": 8,
                "height": 7,
                "soffits": 3,
                "fly_bars": 2,
                "moving_fly_bars": 0,
                "power": 60,
                "dmx": 6,
                "orchestra": 20,
                "bar_load": 150,
                "gate_width": 2,
                "gate_height": 2.5,
                "lighting_positions": 4,
            }
            data["overrides"][str(venues[1].id)] = {
                "version": "REDUCED VERSION",
                "requirements": reduced,
                "orchestra": groups["Оркестр"][:20],
                "scenery": [],
                "note": "Напольная адаптация: большие декорации исключены, оркестр 20, без движения подвесов",
            }
        s.add(Production(name=name, data=data))
    if s.get(Setting, "llm") is None:
        s.add(
            Setting(
                key="llm",
                value={
                    "enabled": False,
                    "provider": "Ollama",
                    "endpoint": "http://127.0.0.1:11434/v1",
                    "model": "",
                },
            )
        )
    s.add(
        Booking(
            resource_id=groups["Артисты"][0],
            start=datetime(2026, 10, 10, 0),
            end=datetime(2026, 10, 13, 23, 59),
            label="Отпуск",
            state="absence",
        )
    )
    s.add(
        Booking(
            resource_id=kits["Звук"][0],
            start=datetime(2026, 10, 22, 0),
            end=datetime(2026, 10, 24, 0),
            label="Профилактика Sound Kit A",
            state="maintenance",
        )
    )
    s.add(
        Booking(
            resource_id=venues[0].id,
            start=datetime(2026, 10, 26, 8),
            end=datetime(2026, 10, 26, 18),
            label="Регламент механики",
            state="maintenance",
        )
    )
    s.flush()
    return True
