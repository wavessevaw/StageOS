import asyncio
import json
import httpx
import pytest
from sqlalchemy import select, func
from test_core import ctx
from backend.models import Event
from backend.model_client import structured_content, request_model


@pytest.mark.parametrize('raw', [
    '{"answer":"Ответ"}',
    ' ```json\n{"answer":"Ответ"}\n``` ',
    '<think>Скрытые рассуждения</think>\n{"answer":"Ответ"}',
    'Ответ по данным:\n{"answer":"Ответ"}\nКонец',
    'Ответ',
])
def test_local_model_response_formats(raw):
    assert structured_content(raw, allow_text=True) == {'answer': 'Ответ'}


@pytest.mark.parametrize('raw', ['', '<think>незавершённое', '{"answer":', '[]', None])
def test_invalid_response_cannot_be_command(raw):
    with pytest.raises(ValueError): structured_content(raw)


def test_native_ollama_disables_thinking_and_requests_json():
    async def handle(request):
        body = json.loads(request.content)
        assert request.url.path == '/api/chat'
        assert body['think'] is False and body['stream'] is False and body['format'] == 'json'
        return httpx.Response(200, json={'message': {'content': '{"answer":"Готово"}'}})
    def factory(**kwargs): return httpx.AsyncClient(transport=httpx.MockTransport(handle), **kwargs)
    raw = asyncio.run(request_model({'provider': 'Ollama', 'endpoint': 'http://127.0.0.1:11434/v1', 'model': 'qwen3:0.6b'}, [], factory))
    assert structured_content(raw)['answer'] == 'Готово'


def test_compatible_server_can_decline_json_mode():
    calls = []
    async def handle(request):
        body = json.loads(request.content); calls.append(body)
        if 'response_format' in body: return httpx.Response(400, json={'error': 'Unsupported response_format'})
        return httpx.Response(200, json={'choices': [{'message': {'content': 'Ответ'}}]})
    def factory(**kwargs): return httpx.AsyncClient(transport=httpx.MockTransport(handle), **kwargs)
    raw = asyncio.run(request_model({'provider': 'Custom', 'endpoint': 'http://localhost/v1', 'model': 'local'}, [], factory))
    assert len(calls) == 2 and structured_content(raw, allow_text=True)['answer'] == 'Ответ'


@pytest.mark.parametrize('raw, status', [
    ('<think>Не показывать</think>```json\n{"answer":"По базе: Дмитрий Петров"}\n```', 200),
    ('По базе: Дмитрий Петров', 200), ('', 200), ('{"answer":', 200),
])
def test_assistant_ollama_response_does_not_mutate_database(ctx, monkeypatch, raw, status):
    c, S, b, rs, r = ctx
    cfg = {'enabled': True, 'provider': 'Ollama', 'endpoint': 'http://127.0.0.1:11434/v1', 'model': 'qwen3:0.6b'}
    assert c.put('/api/settings/llm', json=cfg).status_code == 200
    async def handle(request):
        assert request.url.path == '/api/chat'
        return httpx.Response(200, json={'message': {'content': raw}})
    original = httpx.AsyncClient
    def factory(**kwargs): return original(transport=httpx.MockTransport(handle), **kwargs)
    monkeypatch.setattr('backend.app.httpx.AsyncClient', factory)
    with S() as session: before = session.scalar(select(func.count(Event.id)))
    response = c.post('/api/assistant', json={'text': 'Кто ведёт звук на Северном ветре?'})
    assert response.status_code == status, response.text
    if status == 200:
        assert response.json()['source'] == 'database'
        assert not response.json()['model_accepted']
        assert response.json()['answer'] != 'По базе: Дмитрий Петров'
        assert '<think>' not in response.text
    with S() as session: assert session.scalar(select(func.count(Event.id))) == before


def test_model_check_verifies_generation_not_only_models_list(ctx, monkeypatch):
    c, S, b, rs, r = ctx
    cfg = {'enabled': True, 'provider': 'Ollama', 'endpoint': 'http://127.0.0.1:11434/v1', 'model': 'qwen3:0.6b'}
    c.put('/api/settings/llm', json=cfg)
    calls = []
    async def handle(request):
        calls.append(request.url.path)
        if request.url.path == '/v1/models': return httpx.Response(200, json={'data': [{'id': 'qwen3:0.6b'}]})
        return httpx.Response(200, json={'message': {'content': '{"answer":"Модель готова"}'}})
    original = httpx.AsyncClient
    def factory(**kwargs): return original(transport=httpx.MockTransport(handle), **kwargs)
    monkeypatch.setattr('backend.app.httpx.AsyncClient', factory)
    response = c.post('/api/settings/llm/test')
    assert response.status_code == 200, response.text
    assert response.json()['generation'] == 'PASS'
    assert calls == ['/v1/models', '/api/chat']
