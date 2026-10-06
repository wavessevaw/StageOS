import pytest
from test_accounts import make, theatre, login


def prepared(tmp_path, monkeypatch):
    app, c = make(tmp_path, monkeypatch)
    tid = theatre(c)
    assert login(c, tid).status_code == 200
    for role in ['editor', 'artistic_director', 'viewer']:
        assert c.post('/api/auth/users', json={'name': role, 'login': role, 'password': 'test-password', 'role': role}).status_code == 200
    venue = c.post('/api/venues', json={'name':'Основная сцена','data':{}}).json()
    person = c.post('/api/resources', json={'kind':'Person','name':'Артист','department':'Артисты','data':{'qualification':['Артисты']}}).json()
    template = c.get('/api/production-template').json()
    template['name'] = 'Тестовая постановка'
    template['data']['home_venue'] = venue['id']
    template['data']['roles'] = [dict(role='Главная роль', A=person['id'], B=person['id'], eligible=[person['id']])]
    response = c.post('/api/productions', json=template)
    assert response.status_code == 200, response.text
    production = response.json()
    request = dict(production_id=production['id'], venue_id=venue['id'], start='2026-12-01T18:00:00')
    return c, tid, production, request


def commit(c, request):
    plan = c.post('/api/preview', json=request)
    assert plan.status_code == 200, plan.text
    return c.post('/api/events', json={'request': request, 'fingerprint': plan.json()['fingerprint']})


@pytest.mark.parametrize('reviewer', ['admin', 'artistic_director'])
def test_conflicted_planner_requires_authorized_decision(tmp_path, monkeypatch, reviewer):
    c, tid, production, request = prepared(tmp_path, monkeypatch)
    assert login(c, tid, 'editor').status_code == 200
    production['name'] = 'Составлено планировщиком'
    assert c.patch('/api/productions/' + str(production['id']), json=production).status_code == 200
    assert commit(c, request).status_code == 200
    plan = c.post('/api/preview', json=request).json()
    assert any(x['severity'] in {'ERROR', 'CRITICAL'} for x in plan['conflicts'])
    before = c.get('/api/events').json()
    assert commit(c, request).status_code == 403
    assert c.post('/api/events', json={'request': {**request, 'override_reason': 'Разрешённое ручное решение', 'force': True}, 'fingerprint': plan['fingerprint']}).status_code == 403
    proposal = c.post('/api/proposals', json=request)
    assert proposal.status_code == 200, proposal.text
    aid = proposal.json()['id']
    for action in ['approve', 'reject']:
        assert c.post(f'/api/proposals/{aid}/{action}', json={'reason': 'Согласование планировщиком', 'force': True}).status_code == 403
    assert c.get('/api/events').json() == before
    assert login(c, tid, 'Админ' if reviewer == 'admin' else reviewer).status_code == 200
    assert c.post(f'/api/proposals/{aid}/approve').status_code == 422
    assert c.post(f'/api/proposals/{aid}/approve', json={'reason': 'Коротко', 'force': True}).status_code == 422
    decision = {'reason': 'Согласовано с ответственными за пересечение', 'force': True}
    approved = c.post(f'/api/proposals/{aid}/approve', json=decision)
    assert approved.status_code == 200, approved.text
    assert len(c.get('/api/events').json()) == len(before) + 1
    data = next(n['data'] for n in c.get('/api/notifications').json() if n['id'] == aid)
    assert data['state'] == 'Approved'
    assert data['reason'] == decision['reason']
    assert data['decision_by']['role'] == reviewer
    assert data['approved_plan']['conflicts']
    assert c.post(f'/api/proposals/{aid}/approve', json=decision).status_code == 422


def test_director_scheduling_and_stale_approval_without_admin_privileges(tmp_path, monkeypatch):
    c, tid, production, request = prepared(tmp_path, monkeypatch)
    assert login(c, tid, 'artistic_director').status_code == 200
    production['name'] = 'Назначение художественного руководителя'
    assert c.patch('/api/productions/' + str(production['id']), json=production).status_code == 200
    for path in ['/api/auth/users', '/api/database/export', '/api/diagnostics']:
        assert c.get(path).status_code == 403
    assert c.put('/api/settings/llm', json={}).status_code == 403
    assert commit(c, request).status_code == 200
    assert commit(c, {**request, 'override_reason': 'Ответственные согласовали пересечение', 'force': True}).status_code == 200
    future = {**request, 'start': '2026-12-03T18:00:00'}
    aid = c.post('/api/proposals', json=future).json()['id']
    assert commit(c, future).status_code == 200
    assert c.post(f'/api/proposals/{aid}/approve', json={'reason': 'Согласовано после изменений', 'force': True}).status_code == 409
    assert c.post(f'/api/proposals/{aid}/reject', json={'reason': 'План устарел'}).status_code == 200
