from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from backend.app import create_app
from backend.models import make_engine, Resource, Booking, Event, Task, Production
from backend.engine import Request, preview, compatibility, substitutions


@pytest.fixture()
def ctx(tmp_path):
    app = create_app(make_engine("sqlite:///" + str(tmp_path / "test.db")), demo_enabled=True)
    client = TestClient(app)
    assert client.post("/api/demo").status_code == 200
    b = client.get("/api/bootstrap").json()
    r = {x["name"]: x for x in b["resources"]}
    req = {
        "production_id": 1,
        "venue_id": r["Большой зал"]["id"],
        "start": "2026-10-16T19:00:00",
        "cast": "B",
    }
    return client, app.state.Session, b, r, req


def confirm(c, r):
    p = c.post("/api/preview", json=r)
    assert p.status_code == 200, p.text
    return c.post(
        "/api/events", json={"request": r, "fingerprint": p.json()["fingerprint"]}
    )


def test_seed_counts_idempotent(ctx):
    c, S, b, rs, r = ctx
    assert len([x for x in b["resources"] if x["kind"] == "Person"]) >= 130
    assert len([x for x in b["resources"] if x["kind"] == "Equipment"]) >= 150
    for dep, n in [("Оркестр", 35), ("Хор", 24), ("Балет", 16), ("Артисты", 20)]:
        assert (
            len(
                [
                    x
                    for x in b["resources"]
                    if x["kind"] == "Person" and x["department"] == dep
                ]
            )
            >= n
        )
    assert len([x for x in b["resources"] if x["kind"] == "Venue"]) == 7
    with S() as s:
        assert (
            s.scalar(select(func.count(Event.id)).where(Event.kind == "Спектакль"))
            >= 20
        )
        assert (
            s.scalar(select(func.count(Event.id)).where(Event.kind == "Репетиция"))
            >= 15
        )
    assert c.post("/api/demo").json() == {"created": False}


def test_end_to_end_and_filters(ctx):
    c, S, b, rs, r = ctx
    p = c.post("/api/preview", json=r).json()
    assert p["status"] == "READY"
    assert p["solver"]["status"] == "OPTIMAL"
    with S() as s:
        before = s.scalar(select(func.count(Event.id)))
    assert c.post("/api/preview", json=r).status_code == 200
    with S() as s:
        assert before == s.scalar(select(func.count(Event.id)))
    ev = confirm(c, r)
    assert ev.status_code == 200, ev.text
    eid = ev.json()["id"]
    detail = c.get(f"/api/events/{eid}").json()
    assert len(detail["current"]["assignments"]) > 80
    assert {
        "Погрузка",
        "Световой монтаж",
        "Technical Check",
        "Спектакль",
        "Демонтаж",
    } <= {t["name"] for t in detail["tasks"]}
    for query in [
        f"venue={r['venue_id']}",
        "production=1",
        "department=Звук",
        f"person={p['assignments'][0]['actual_id']}",
    ]:
        assert eid in [e["id"] for e in c.get("/api/events?" + query).json()]
    with S() as s:
        assert (
            s.scalar(select(func.count(Booking.id)).where(Booking.event_id == eid))
            > 100
        )
        assert s.scalar(select(func.count(Task.id)).where(Task.event_id == eid)) >= 10


def test_incompatible(ctx):
    c, S, b, rs, r = ctx
    r = {**r, "production_id": 6, "venue_id": rs["Камерный зал"]["id"]}
    p = c.post("/api/preview", json=r).json()
    assert p["status"] == "CONFLICT"
    assert {"fly_bars", "soffits", "fly_system", "scenery", "orchestra"} <= {
        x["code"] for x in p["conflicts"]
    }
    assert (
        confirm(
            c, {**r, "override_reason": "Я администратор и принимаю решение"}
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "key,value,code",
    [
        ("power", 1, "power"),
        ("dmx", 1, "dmx"),
        ("width", 1, "width"),
        ("depth", 1, "depth"),
        ("height", 1, "height"),
        ("gate_width", 1, "gate_width"),
        ("gate_height", 1, "gate_height"),
        ("bar_load", 1, "bar_load"),
        ("fly_system", False, "fly_system"),
        ("movement", False, "movement"),
        ("orchestra", 1, "orchestra"),
    ],
)
def test_compatibility_dimensions(ctx, key, value, code):
    c, S, b, rs, r = ctx
    c.patch("/api/resources/" + str(r["venue_id"]), json={"data": {key: value}})
    p = c.post("/api/preview", json=r).json()
    assert code in {x["code"] for x in p["conflicts"]}


@pytest.mark.parametrize(
    "dept", ["Артисты", "Оркестр", "Звук", "Свет", "Видео", "Помреж", "Дирижёр"]
)
def test_person_overlap(ctx, dept):
    c, S, b, rs, r = ctx
    p = c.post("/api/preview", json=r).json()
    a = next(a for a in p["assignments"] if a["department"] == dept)
    res = c.post(
        "/api/blocks",
        json={
            "resource_id": a["actual_id"],
            "start": "2026-10-16T12:00:00",
            "end": "2026-10-16T23:00:00",
            "label": "Больничный",
            "state": "absence",
        },
    )
    assert res.status_code == 200
    p = c.post("/api/preview", json=r).json()
    cs = [x for x in p["conflicts"] if x.get("resource_id") == a["actual_id"]]
    assert cs and cs[0]["overlap"] and cs[0]["required"]
    assert confirm(c, r).status_code == 422


@pytest.mark.parametrize("kind", ["Equipment", "Equipment Kit", "Venue", "Vehicle"])
def test_resource_busy(ctx, kind):
    c, S, b, rs, r = ctx
    p = c.post("/api/preview", json=r).json()
    book = next(b for b in p["bookings"] if b["kind"] == kind)
    c.post(
        "/api/blocks",
        json={
            "resource_id": book["resource_id"],
            "start": book["start"],
            "end": book["end"],
            "label": "Обслуживание",
            "state": "maintenance",
        },
    )
    p = c.post("/api/preview", json=r).json()
    assert any(
        x["code"] == "maintenance" and x.get("resource_id") == book["resource_id"]
        for x in p["conflicts"]
    )


def test_broken_fly_bars_and_soffits(ctx):
    c, S, b, rs, r = ctx
    for x in b["resources"]:
        if (
            x["kind"] in ["Fly Bar", "Soffit"]
            and x["data"].get("venue_id") == r["venue_id"]
        ):
            c.patch("/api/resources/" + str(x["id"]), json={"status": "broken"})
    codes = {x["code"] for x in c.post("/api/preview", json=r).json()["conflicts"]}
    assert {"fly_bars", "soffits", "bar_capacity"} <= codes


def test_override_reduces_real_resources(ctx):
    c, S, b, rs, r = ctx
    r = {**r, "production_id": 6, "venue_id": rs["ГДК"]["id"]}
    p = c.post("/api/preview", json=r).json()
    assert p["compatibility"]["version"] == "REDUCED VERSION"
    assert len([a for a in p["assignments"] if a["department"] == "Оркестр"]) == 20
    assert not [b for b in p["bookings"] if b["kind"] == "Scenery"]
    assert (
        c.post("/api/preview", json={**r, "adaptation": False}).json()["compatibility"][
            "version"
        ]
        == "INCOMPATIBLE"
    )


def test_move_resize_cancel_and_stale(ctx):
    c, S, b, rs, r = ctx
    r = {**r, "kind": "Репетиция", "scenes": [0], "duration": 60}
    ev = confirm(c, r).json()
    eid = ev["id"]
    req = {
        **r,
        "event_id": eid,
        "version": ev["version"],
        "start": "2026-10-16T10:00:00",
        "duration": 90,
    }
    p = c.post("/api/preview", json=req).json()
    assert c.get(f"/api/events/{eid}").json()["start"] == "2026-10-16T19:00:00"
    res = c.post("/api/events", json={"request": req, "fingerprint": p["fingerprint"]})
    assert res.status_code == 200, res.text
    assert res.json()["end"] == "2026-10-16T11:30:00"
    assert confirm(c, req).status_code == 422
    assert (
        c.post(
            f"/api/events/{eid}/status",
            json={"status": "Cancelled", "version": res.json()["version"]},
        ).status_code
        == 200
    )
    with S() as s:
        assert not s.scalars(select(Booking).where(Booking.event_id == eid)).all()


def test_stale_fingerprint(ctx):
    c, S, b, rs, r = ctx
    p = c.post("/api/preview", json=r).json()
    c.post(
        "/api/blocks",
        json={
            "resource_id": r["venue_id"],
            "start": p["tasks"][0]["start"],
            "end": p["end"],
            "label": "Зал закрыт",
        },
    )
    assert (
        c.post(
            "/api/events", json={"request": r, "fingerprint": p["fingerprint"]}
        ).status_code
        == 409
    )


def test_substitution_and_qualification(ctx):
    c, S, b, rs, r = ctx
    p = c.post("/api/preview", json=r).json()
    a = next(a for a in p["assignments"] if a["role"] == "Звук")
    c.post(
        "/api/blocks",
        json={
            "resource_id": a["actual_id"],
            "start": "2026-10-16T00:00:00",
            "end": "2026-10-17T00:00:00",
            "label": "Отпуск",
        },
    )
    result = c.post("/api/substitutions", json=r)
    assert result.status_code == 200, result.text
    result = result.json()
    assert result["status"] == "OPTIMAL"
    assert result["replacements"][str(a["responsible_id"])] != a["responsible_id"]
    assert result["plan"]["status"] != "CONFLICT"
    wrong = next(x for x in b["resources"] if x["department"] == "Артисты")
    p = c.post(
        "/api/preview",
        json={**r, "replacements": {str(a["responsible_id"]): wrong["id"]}},
    ).json()
    assert "qualification" in {c["code"] for c in p["conflicts"]}


def test_windows_and_ai_off(ctx):
    c, S, b, rs, r = ctx
    req = {**r, "kind": "Репетиция", "scenes": [0], "duration": 60}
    windows = c.post("/api/windows", json=req).json()
    assert len(windows) == 3
    for w in windows:
        assert c.post("/api/preview", json=w["request"]).json()["status"] != "CONFLICT"
    assert (
        "отключён"
        in c.post("/api/assistant", json={"text": "Создай событие"}).json()["answer"]
    )
    assert confirm(c, req).status_code == 200


def test_proposal_approval(ctx):
    c, S, b, rs, r = ctx
    p = c.post("/api/proposals", json=r).json()
    assert p["data"]["state"] == "Pending Approval"
    res = c.post("/api/proposals/" + str(p["id"]) + "/approve")
    assert res.status_code == 200, res.text
    assert c.post("/api/proposals/" + str(p["id"]) + "/approve").status_code == 422


def test_actuals_analytics(ctx):
    c, S, b, rs, r = ctx
    ev = confirm(c, r).json()
    t = c.get("/api/events/" + str(ev["id"])).json()["tasks"][0]
    assert (
        c.patch(
            "/api/tasks/" + str(t["id"]) + "/actual",
            json={"start": t["start"], "end": t["end"]},
        ).status_code
        == 200
    )
    a = c.get("/api/analytics").json()
    assert a["actuals"][0]["actual"] == a["actuals"][0]["planned"]


def test_travel(ctx):
    c, S, b, rs, r = ctx
    first = {
        **r,
        "kind": "Репетиция",
        "scenes": [0],
        "start": "2026-10-16T10:00:00",
        "duration": 60,
    }
    assert confirm(c, first).status_code == 200
    second = {
        **first,
        "venue_id": rs["Летняя сцена"]["id"],
        "start": "2026-10-16T11:45:00",
    }
    p = c.post("/api/preview", json=second).json()
    assert "travel" in {x["code"] for x in p["conflicts"]}


def test_setup_and_precedence(ctx):
    c, S, b, rs, r = ctx
    p = c.post("/api/preview", json={**r, "start": "2026-10-16T09:00:00"}).json()
    assert "setup" in {x["code"] for x in p["conflicts"]}
    tasks = {x["name"]: x for x in p["tasks"]}
    for pred, succ in [
        ("Погрузка", "Выезд"),
        ("Выезд", "Разгрузка"),
        ("Разгрузка", "Световой монтаж"),
        ("Звуковой монтаж", "RF check"),
        ("Orchestra setup", "Technical Check"),
        ("Technical Check", "Готовность"),
        ("Готовность", "Спектакль"),
    ]:
        assert tasks[pred]["end"] <= tasks[succ]["start"]


def test_atomic_rejection(ctx):
    c, S, b, rs, r = ctx
    with S() as s:
        n = s.scalar(select(func.count(Event.id)))
        nb = s.scalar(select(func.count(Booking.id)))
    r = {**r, "production_id": 6, "venue_id": rs["Камерный зал"]["id"]}
    assert confirm(c, r).status_code == 422
    with S() as s:
        assert n == s.scalar(select(func.count(Event.id)))
        assert nb == s.scalar(select(func.count(Booking.id)))


def test_auth(ctx, monkeypatch):
    c, *_ = ctx
    monkeypatch.setenv("STAGEOS_TOKEN", "secret")
    assert c.get("/api/bootstrap").status_code == 401
    assert (
        c.get("/api/bootstrap", headers={"x-stageos-token": "secret"}).status_code
        == 200
    )
    assert (
        c.get(
            "/api/bootstrap",
            headers={
                "x-stageos-token": "secret",
                "origin": "https://untrusted.invalid",
            },
        ).status_code
        == 403
    )


def test_equipment_replacement(ctx):
    c, S, b, rs, r = ctx
    p = c.post("/api/preview", json=r).json()
    kit = next(x for x in p["bookings"] if x["kind"] == "Equipment Kit")
    c.patch("/api/resources/" + str(kit["resource_id"]), json={"status": "broken"})
    out = c.post("/api/equipment-substitutions", json=r)
    assert out.status_code == 200, out.text
    p = out.json()["plan"]
    assert kit["resource_id"] not in [b["resource_id"] for b in p["bookings"]]
    assert p["status"] == "READY"


def test_crud_resource_and_production(ctx):
    c, S, b, rs, r = ctx
    x = c.post(
        "/api/resources",
        json={
            "kind": "Person",
            "name": "Тестовый музыкант",
            "department": "Оркестр",
            "data": {"qualification": ["Оркестр", "Tuba"], "specialization": "Tuba"},
        },
    ).json()
    assert (
        c.patch("/api/resources/" + str(x["id"]), json={"name": "Новое имя"}).json()[
            "resource"
        ]["name"]
        == "Новое имя"
    )
    assert c.delete("/api/resources/" + str(x["id"])).status_code == 200
    assert c.delete("/api/resources/" + str(r["venue_id"])).status_code == 409
    p = c.post("/api/productions/1/clone", json={"name": "Новая постановка"}).json()
    upd = c.patch(
        "/api/productions/" + str(p["id"]),
        json={"version": 1, "data": {"duration": 130}},
    ).json()
    assert upd["version"] == 2
    assert c.delete("/api/productions/" + str(p["id"])).status_code == 200


def test_both_conflict_markers(ctx):
    c, S, b, rs, r = ctx
    first = confirm(c, r).json()
    second = confirm(c, {**r, "override_reason": "Демонстрация совместной занятости"})
    assert second.status_code == 200
    ids = [first["id"], second.json()["id"]]
    es = c.get("/api/events?start=2026-10-16&end=2026-10-17").json()
    assert all(e["health"] == "CONFLICT" for e in es if e["id"] in ids)


def test_missing_orchestra(ctx):
    c, S, b, rs, r = ctx
    with S.begin() as s:
        p = s.get(Production, 1)
        d = dict(p.data)
        d["groups"] = {**d["groups"], "Оркестр": d["groups"]["Оркестр"][:-1]}
        p.data = d
    assert "orchestra_missing" in {
        x["code"] for x in c.post("/api/preview", json=r).json()["conflicts"]
    }


def test_individual_bar_movement(ctx):
    c, S, b, rs, r = ctx
    with S.begin() as s:
        for bar in s.scalars(select(Resource).where(Resource.kind == "Fly Bar")):
            if bar.data["venue_id"] == r["venue_id"]:
                bar.data = {**bar.data, "movement": False}
    assert "moving_bar_count" in {
        x["code"] for x in c.post("/api/preview", json=r).json()["conflicts"]
    }


def test_invalid_scene_and_timezone(ctx):
    c, S, b, rs, r = ctx
    assert (
        c.post(
            "/api/preview", json={**r, "kind": "Репетиция", "scenes": [99]}
        ).status_code
        == 422
    )
    assert (
        c.post("/api/preview", json={**r, "start": "2026-10-16T19:00:00Z"}).status_code
        == 422
    )


def test_database_backup_and_import(ctx, tmp_path):
    c, S, b, rs, r = ctx
    data = c.get("/api/database/export")
    assert data.status_code == 200
    assert data.content.startswith(b"SQLite format 3")
    first = confirm(c, r).json()
    restored = c.post(
        "/api/database/import",
        content=data.content,
        headers={"content-type": "application/octet-stream"},
    )
    assert restored.status_code == 200, restored.text
    assert c.get("/api/events/" + str(first["id"])).status_code == 404
    assert c.get("/api/bootstrap").json()["initialized"]
    assert c.post("/api/database/import", content=b"not sqlite").status_code == 422


def test_twenty_four_isolated_scenarios(ctx):
    c, S, b, rs, r = ctx
    with S() as s:
        before = s.scalar(select(func.count(Event.id)))
    cases = c.get("/api/demo/scenarios").json()
    assert len(cases) == 24
    for case in cases:
        res = c.post("/api/demo/scenarios/" + case["id"])
        assert res.status_code == 200, res.text
        result = res.json()
        assert result["demo_scenario"]["detected"], (case, result["conflicts"])
        assert result["status"] == "CONFLICT"
    with S() as s:
        assert before == s.scalar(select(func.count(Event.id)))
    assert c.post("/api/preview", json=r).json()["status"] == "READY"


def test_diagnostics_executes_engines(ctx):
    c, *_ = ctx
    d = c.get("/api/diagnostics").json()
    for k in [
        "Production Engine",
        "Calendar Engine",
        "Venue Compatibility",
        "Stage Mechanics",
        "Lighting Infrastructure",
        "Resource Engine",
        "Conflict Engine",
    ]:
        assert d[k] == "OK"


def test_llm_protocol_is_read_only(ctx, monkeypatch):
    import httpx

    c, S, b, rs, r = ctx
    cfg = {
        "enabled": True,
        "provider": "Custom",
        "endpoint": "http://127.0.0.1:11434/v1",
        "model": "contract-model",
    }
    assert c.put("/api/settings/llm", json=cfg).status_code == 200
    captured = []

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json):
            captured.append(json)
            import json as codec

            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={
                    "choices": [{"message": {"content": codec.dumps({"command": r})}}]
                },
            )

    monkeypatch.setattr("backend.app.httpx.AsyncClient", Client)
    with S() as s:
        count = s.scalar(select(func.count(Event.id)))
    out = c.post(
        "/api/assistant",
        json={"text": "Поставь Северный ветер 16 октября в Большом зале в 19:00"},
    )
    assert out.status_code == 200, out.text
    assert out.json()["preview"]["title"] == "Северный ветер"
    assert len(captured[0]["messages"][0]["content"]) < 100000
    with S() as s:
        assert count == s.scalar(select(func.count(Event.id)))


def test_configure_ai_before_creating_theatre(tmp_path):
    c = TestClient(
        create_app(make_engine("sqlite:///" + str(tmp_path / "firstrun.db")), demo_enabled=True)
    )
    settings = {
        "enabled": False,
        "provider": "LM Studio",
        "endpoint": "http://127.0.0.1:1234/v1",
        "model": "local-test",
    }
    assert c.put("/api/settings/llm", json=settings).status_code == 200
    assert c.post("/api/demo").status_code == 200
    assert c.get("/api/settings/llm").json() == settings
