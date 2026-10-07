from datetime import datetime
from test_core import ctx, confirm


def test_free_stage_at_any_date_survives_save_and_reopen(ctx):
    client, _, _, _, request = ctx
    plan = client.post('/api/preview', json={**request, 'baseline_plan': True}).json()
    req = {**request, 'baseline_plan': True,
           'removed_tasks': [task['name'] for task in plan['tasks']],
           'extra_tasks': [{'name': 'Произвольный этап', 'department': 'Все',
                            'start': '2026-12-20T09:00:00', 'duration': 25}]}
    response = client.post('/api/preview', json=req)
    assert response.status_code == 200, response.text
    assert len(response.json()['tasks']) == 1
    assert datetime.fromisoformat(response.json()['tasks'][0]['start']) == datetime(2026, 12, 20, 9)
    req.update(force=True, override_reason='Контроль произвольного этапа')
    saved = confirm(client, req)
    assert saved.status_code == 200, saved.text
    current = client.get('/api/events/' + str(saved.json()['id'])).json()['current']
    assert current['tasks'][0]['name'] == 'Произвольный этап'
    assert datetime.fromisoformat(current['tasks'][0]['end']) == datetime(2026, 12, 20, 9, 25)


def test_deleted_standard_name_can_be_used_for_a_custom_stage(ctx):
    client, _, _, _, request = ctx
    plan = client.post('/api/preview', json=request).json()
    req = {**request, 'removed_tasks': [task['name'] for task in plan['tasks']],
           'extra_tasks': [{'name': 'Спектакль', 'start': '2026-10-15T09:00:00', 'duration': 10}]}
    response = client.post('/api/preview', json=req)
    assert response.status_code == 200, response.text
    assert datetime.fromisoformat(response.json()['tasks'][0]['start']) == datetime(2026, 10, 15, 9)
