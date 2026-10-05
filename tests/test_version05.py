import asyncio, json, threading
from datetime import datetime
import httpx, pytest
from sqlalchemy import select, func
from test_core import ctx, confirm
from backend.models import Task, Event, Production, Booking, Setting
from backend.learning import explain_with_llm
from backend.small_model import SmallModelJob, MODEL


def test_edit_stages_and_individual_actor_persist(ctx):
    c, S, b, rs, r = ctx
    base = c.post("/api/preview", json=r).json()
    role = base["event_roles"][0]
    other = next(x for x in role["eligible_ids"] if x != role["actual_id"])
    r = {
        **r,
        "removed_tasks": ["Погрузка"],
        "role_assignments": {"0": other},
        "extra_tasks": [
            {
                "name": "Проверка реквизита",
                "department": "Реквизит",
                "start": "2026-10-16T18:20:00",
                "duration": 20,
                "before": "Спектакль",
            }
        ],
    }
    p = c.post("/api/preview", json=r)
    assert p.status_code == 200, p.text
    p = p.json()
    assert p["status"] == "READY"
    assert "Погрузка" not in [t["name"] for t in p["tasks"]]
    assert p["event_roles"][0]["actual_id"] == other
    assert [x["actual_id"] for x in p["event_roles"][1:]] == [
        x["actual_id"] for x in base["event_roles"][1:]
    ]
    with S() as s:
        passport = json.dumps(s.get(Production, 1).data, sort_keys=True)
    saved = confirm(c, r)
    assert saved.status_code == 200, saved.text
    eid = saved.json()["id"]
    with S() as s:
        tasks = s.scalars(select(Task).where(Task.event_id == eid)).all()
        assert "Погрузка" not in [x.name for x in tasks]
        assert "Проверка реквизита" in [x.name for x in tasks]
        assert (
            other
            in s.scalars(
                select(Booking.resource_id).where(Booking.event_id == eid)
            ).all()
        )
        assert json.dumps(s.get(Production, 1).data, sort_keys=True) == passport
    detail = c.get(f"/api/events/{eid}").json()["current"]
    assert detail["event_roles"][0]["actual_id"] == other
    assert any(t["name"] == "Проверка реквизита" for t in detail["tasks"])


@pytest.mark.parametrize(
    "changes",
    [
        {"removed_tasks": ["Спектакль"]},
        {"removed_tasks": ["Несуществующий этап"]},
        {"role_assignments": {"999": 1}},
        {"role_assignments": {"0": -1}},
        {
            "extra_tasks": [
                {"name": "Спектакль", "start": "2026-10-16T18:00:00", "duration": 10}
            ]
        },
        {
            "extra_tasks": [
                {
                    "name": "Новый",
                    "start": "2026-10-16T18:00:00",
                    "duration": 10,
                    "after": "Спектакль",
                    "before": "Спектакль",
                }
            ]
        },
        {
            "extra_tasks": [
                {
                    "name": "Новый",
                    "start": "2026-10-16T19:00:00",
                    "duration": 10,
                    "before": "Спектакль",
                }
            ]
        },
    ],
)
def test_invalid_plan_is_read_only(ctx, changes):
    c, S, b, rs, r = ctx
    with S() as s:
        n = s.scalar(select(func.count(Event.id)))
    assert c.post("/api/preview", json={**r, **changes}).status_code == 422
    with S() as s:
        assert s.scalar(select(func.count(Event.id))) == n


def test_learn_confirmed_templates_without_writes(ctx):
    c, S, b, rs, r = ctx
    for day in (1, 3):
        saved = confirm(
            c,
            {
                **r,
                "start": f"2026-12-{day:02d}T19:00:00",
                "removed_tasks": ["Погрузка"],
            },
        )
        assert saved.status_code == 200, saved.text
    with S() as s:
        n = s.scalar(select(func.count(Event.id)))
    result = c.post("/api/suggestions", json={**r, "start": "2026-12-05T19:00:00"})
    assert result.status_code == 200, result.text
    result = result.json()
    assert result["samples"] == 2 and result["suggestions"][0]["count"] == 2
    proposed = result["suggestions"][0]["request"]
    assert proposed["removed_tasks"] == ["Погрузка"]
    assert proposed["start"] == "2026-12-05T19:00:00" and not proposed["force"]
    with S() as s:
        assert s.scalar(select(func.count(Event.id))) == n
    assert c.put("/api/settings/learning", json={"enabled": False}).status_code == 200
    assert c.post("/api/suggestions", json=r).json()["suggestions"] == []
    assert c.put("/api/settings/learning", json={"enabled": "yes"}).status_code == 422


@pytest.mark.parametrize("candidate", ["known", "invented"])
def test_llm_can_only_select_existing_candidate(candidate):
    async def handle(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"id": candidate, "explanation": "История подтверждена"}
                            )
                        }
                    }
                ]
            },
        )

    def factory(**kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(handle), **kwargs)

    result = asyncio.run(
        explain_with_llm(
            {
                "suggestions": [
                    {
                        "id": "known",
                        "count": 2,
                        "share": 1,
                        "status": "READY",
                        "roles": [],
                        "stages": [],
                    }
                ]
            },
            {"enabled": True, "model": MODEL, "endpoint": "http://localhost/v1"},
            factory,
        )
    )
    assert result["llm_status"] == (
        "connected" if candidate == "known" else "unavailable"
    )
    assert result.get("selected_id") == ("known" if candidate == "known" else None)


def test_small_model_stream_activation_and_failure(ctx, monkeypatch):
    c, S, b, rs, r = ctx
    job = SmallModelJob(S, threading.RLock())
    cfg = {
        "provider": "Ollama",
        "endpoint": "http://127.0.0.1:11434/v1",
        "enabled": False,
        "model": "old",
    }
    with S.begin() as s:
        s.merge(Setting(key="llm", value=cfg))

    class Stream:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def raise_for_status(self):
            pass

        def iter_lines(self):
            return iter(['{"total":100,"completed":60}', '{"status":"success"}'])

    monkeypatch.setattr(httpx, "stream", lambda *a, **k: Stream())
    job.run(cfg, "http://127.0.0.1:11434")
    assert job.status()["status"] == "ready"
    with S() as s:
        assert (
            s.get(Setting, "llm").value["model"] == MODEL
            and s.get(Setting, "llm").value["enabled"]
        )
    with pytest.raises(ValueError):
        job.start({**cfg, "endpoint": "https://example.com/v1"})
    monkeypatch.setattr(
        Stream, "iter_lines", lambda self: iter(['{"error":"offline"}'])
    )
    with S.begin() as s:
        s.get(Setting, "llm").value = cfg
    job.run(cfg, "http://127.0.0.1:11434")
    assert job.status()["status"] == "error"
    with S() as s:
        assert not s.get(Setting, "llm").value["enabled"]


def test_actor_slot_without_baseline_and_existing_event_edit(ctx):
    from copy import deepcopy

    c, S, b, rs, r = ctx
    base = c.post("/api/preview", json=r).json()
    actor = base["event_roles"][0]["actual_id"]
    with S.begin() as s:
        production = s.get(Production, 1)
        data = deepcopy(production.data)
        data["roles"][0]["A"] = None
        data["roles"][0]["B"] = None
        production.data = data
    r = {**r, "role_assignments": {"0": actor}}
    p = c.post("/api/preview", json=r)
    assert p.status_code == 200, p.text
    assert p.json()["event_roles"][0]["baseline_id"] is None
    assert p.json()["event_roles"][0]["actual_id"] == actor
    saved = confirm(c, r)
    assert saved.status_code == 200, saved.text
    eid = saved.json()["id"]
    plan = c.get(f"/api/events/{eid}").json()["current"]
    edit = {**plan["request"], "removed_tasks": ["Погрузка"]}
    changed = confirm(c, edit)
    assert changed.status_code == 200, changed.text
    assert changed.json()["id"] == eid
    current = c.get(f"/api/events/{eid}").json()["current"]
    assert current["event_roles"][0]["actual_id"] == actor
    assert "Погрузка" not in [x["name"] for x in current["tasks"]]
