from copy import deepcopy
from datetime import datetime, timedelta
import base64
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import select, func
from test_core import ctx, confirm
from backend.models import Event, Resource
from backend.engine import availability
from windows.desktop_files import DesktopFiles
from backend.workload import employee_workload


def morning_request(r, day="2026-12-05", show="19:00", cast="B"):
    return {**r, "start": f"{day}T{show}:00", "cast": cast, "run_through": True,
        "task_overrides": {
            **{n: {"start": f"{day}T09:00:00", "duration": 60} for n in
               ("Монтаж сцены", "Световой монтаж", "Звуковой монтаж", "Видеомонтаж")},
            "Orchestra setup": {"start": f"{day}T09:00:00", "duration": 30},
            "Technical Check": {"duration": 15}, "RF check": {"duration": 15},
        }}


def test_morning_orchestra_parallel_setup_and_calls_persist(ctx):
    c, S, b, rs, r = ctx
    r = morning_request(r)
    p = c.post('/api/preview', json=r)
    assert p.status_code == 200, p.text
    p = p.json()
    tasks = {t['name']: t for t in p['tasks']}
    assert tasks['Orchestra setup']['start'] == '2026-12-05T09:00:00'
    assert tasks['Монтаж сцены']['end'] > tasks['Orchestra setup']['start']
    assert tasks['Разгрузка']['end'] <= tasks['Orchestra setup']['start']
    assert tasks['Technical Check']['end'] <= tasks['Прогон']['start']
    orchestra = [a for a in p['assignments'] if a['department'] == 'Оркестр']
    assert orchestra and all(a['call'] <= tasks['Orchestra setup']['start'] for a in orchestra)
    assert not any(x['code'] == 'long_shift' for x in p['conflicts'])
    saved = confirm(c, r)
    assert saved.status_code == 200, saved.text
    plan = c.get(f"/api/events/{saved.json()['id']}").json()['current']
    assert next(t for t in plan['tasks'] if t['name'] == 'Orchestra setup')['start'] == '2026-12-05T09:00:00'
    assert not any(x['code'] == 'long_shift' for x in plan['conflicts'])


def test_orchestra_cannot_start_before_fixed_unload(ctx):
    c, S, b, rs, r = ctx
    r = morning_request(r)
    r['task_overrides']['Разгрузка'] = {'start': '2026-12-05T09:00:00', 'duration': 30}
    assert c.post('/api/preview', json=r).status_code == 422


def test_third_preparation_suggested_across_cast_and_curtain_time(ctx):
    c, S, b, rs, r = ctx
    first = morning_request(r, '2026-12-01', cast='A')
    assert confirm(c, first).status_code == 200
    third = {**r, 'start': '2026-12-05T18:00:00', 'cast': 'A'}
    assert c.post('/api/suggestions', json=third).json()['suggestions'] == []
    second = morning_request(r, '2026-12-03', show='18:00', cast='B')
    assert confirm(c, second).status_code == 200
    with S() as session:
        before = session.scalar(select(func.count(Event.id)))
    result = c.post('/api/suggestions', json=third).json()
    proposal = next(x for x in result['suggestions'] if x['scope'] == 'organization')
    assert proposal['count'] == 2
    proposed = proposal['request']
    assert proposed['cast'] == 'A' and proposed['role_assignments'] == {}
    assert proposed['start'] == third['start']
    assert proposed['task_overrides']['Orchestra setup']['start'] == '2026-12-05T09:00:00'
    assert proposed['run_through']
    with S() as session:
        assert session.scalar(select(func.count(Event.id))) == before
    assert confirm(c, proposed).status_code == 200


@pytest.mark.parametrize('meal,warning', [
    (None, True), ((14, 15), False), ((14, 14), True), ((23, 24), True),
])
def test_lunch_interrupts_long_shift_only_inside_person_call(ctx, meal, warning):
    c, S, b, rs, r = ctx
    with S() as session:
        person = session.scalar(select(Resource).where(Resource.kind == 'Person'))
        venue = session.get(Resource, r['venue_id'])
        start = datetime(2027, 3, 1, 8)
        bookings = {person.id: {'start': start, 'end': start + timedelta(hours=14)}}
        breaks = [(start.replace(hour=0) + timedelta(hours=a), start.replace(hour=0) + timedelta(hours=z)) for a, z in [meal]] if meal else []
        result = availability(session, {person.id: person, venue.id: venue}, bookings, venue.id, meal_breaks=breaks)
        assert any(x['code'] == 'long_shift' for x in result) == warning


def test_native_save_dialog_cancellation_and_exact_path(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, 'webview', SimpleNamespace(FileDialog=SimpleNamespace(SAVE=30)))
    target = tmp_path / 'Расписание.pdf'
    selected = [str(target)]
    class Window:
        def get_current_url(self): return 'http://127.0.0.1:8765/'
        def create_file_dialog(self, mode, **kwargs):
            assert mode == 30 and kwargs['save_filename'] == 'StageOS.pdf'
            return selected
    bridge = DesktopFiles('http://127.0.0.1:8765')
    bridge._window = Window()
    raw = b'%PDF-test-export'
    result = bridge.save_file('StageOS.pdf', base64.b64encode(raw).decode())
    assert result == {'status': 'saved', 'path': str(target)}
    assert target.read_bytes() == raw
    selected.clear()
    assert bridge.save_file('StageOS.pdf', base64.b64encode(raw).decode()) == {'status': 'cancelled'}
    assert target.read_bytes() == raw
    assert bridge.save_file('../StageOS.pdf', base64.b64encode(raw).decode())['status'] == 'error'
    assert bridge.save_file('StageOS.pdf', 'invalid-base64')['status'] == 'error'
    assert bridge.save_file('StageOS.exe', base64.b64encode(raw).decode())['status'] == 'error'
    bridge._window.get_current_url = lambda: 'http://127.0.0.1:87650/'
    assert bridge.save_file('StageOS.pdf', base64.b64encode(raw).decode())['status'] == 'error'


def test_department_workload_is_average_not_sum_and_merges_overlaps():
    start = datetime(2027, 3, 1, 8)
    people = {rid: SimpleNamespace(id=rid, kind='Person', department='Артисты') for rid in (1, 2, 3)}
    people[4] = SimpleNamespace(id=4, kind='Equipment', department='Артисты')
    events = {eid: SimpleNamespace(status=status, data={}) for eid, status in ((1, 'Approved'), (2, 'Approved'), (3, 'Cancelled'))}
    def booking(rid, eid, a, z):
        return SimpleNamespace(resource_id=rid, event_id=eid, start=start+timedelta(hours=a), end=start+timedelta(hours=z))
    bookings = [booking(rid, 1, 0, 12) for rid in people]
    bookings += [booking(1, 2, 2, 8), booking(1, 3, 12, 20)]
    individuals, departments = employee_workload(people, bookings, events)
    assert individuals == {1: 12, 2: 12, 3: 12}
    assert departments['Артисты'] == {'people': 3, 'average_hours': 12, 'person_hours': 36, 'busy_hours': 12}
    events[1].data = {'plan': {'tasks': [{'name': 'Обед', 'start': '2027-03-01T14:00:00', 'end': '2027-03-01T15:00:00'}]}}
    individuals, departments = employee_workload(people, bookings[:4], events)
    assert individuals == {1: 11, 2: 11, 3: 11}
    assert departments['Артисты']['average_hours'] == 11


def test_analytics_api_and_employee_statistics_use_same_workload(ctx):
    from backend.models import Booking
    from sqlalchemy import delete
    c, S, b, rs, r = ctx
    with S.begin() as session:
        session.execute(delete(Booking))
        event = session.scalar(select(Event).where(Event.status != 'Cancelled'))
        people = session.scalars(select(Resource).where(Resource.department == 'Артисты', Resource.kind == 'Person').limit(3)).all()
        ids = [p.id for p in people]
        start = datetime(2027, 3, 1, 8)
        for rid in ids:
            session.add(Booking(resource_id=rid, event_id=event.id, start=start, end=start+timedelta(hours=12), label='Проверка нагрузки'))
    result = c.get('/api/analytics').json()
    assert result['departments']['Артисты'] == 12
    assert result['department_stats']['Артисты']['person_hours'] == 36
    assert all(x['hours'] == 12 for x in result['resources'])
    assert c.get(f'/api/resources/{ids[0]}/statistics').json()['hours'] == 12
