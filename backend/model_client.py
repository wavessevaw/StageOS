"""Local model protocol and robust structured-output parsing."""
import json
import re


def visible_content(raw):
    if not isinstance(raw, str):
        raise ValueError('Модель не вернула текст ответа')
    text = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL | re.IGNORECASE).strip()
    if '<think>' in text.lower():
        raise ValueError('Модель завершила ответ до окончания рассуждений')
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*```$', '', text).strip()
    if not text:
        raise ValueError('Модель вернула пустой ответ')
    return text


def structured_content(raw, allow_text=False):
    text = visible_content(raw)
    decoder = json.JSONDecoder()
    # Some local models add an introduction or trailing explanation to JSON.
    for match in re.finditer(r'\{', text[:4096]):
        try:
            result, _ = decoder.raw_decode(text[match.start():])
        except ValueError:
            continue
        if isinstance(result, dict) and any(k in result for k in ('answer', 'command', 'id')):
            return result
    if allow_text and not text.startswith(('{', '[', '```')):
        return {'answer': text[:8000]}
    raise ValueError('Модель не вернула корректный ответ. Попробуйте задать вопрос короче.')


async def request_model(cfg, messages, client_factory, max_tokens=1024):
    async with client_factory(timeout=90, trust_env=False) as client:
        endpoint = cfg['endpoint'].rstrip('/')
        if cfg.get('provider') == 'Ollama':
            # Native Ollama reliably disables Qwen thinking; /v1 versions
            # differ in their support for reasoning_effort and /no_think.
            payload = {'model': cfg['model'], 'messages': messages,
                       'stream': False, 'format': 'json', 'think': False,
                       'options': {'temperature': 0, 'num_predict': max_tokens, 'num_ctx': 16384}}
            response = await client.post(endpoint.removesuffix('/v1') + '/api/chat', json=payload)
            response.raise_for_status()
            return response.json()['message']['content']
        payload = {'model': cfg['model'], 'messages': messages,
                   'temperature': 0, 'max_tokens': max_tokens,
                   'response_format': {'type': 'json_object'}}
        response = await client.post(endpoint + '/chat/completions', json=payload)
        if response.status_code in (400, 422):
            # Older compatible servers may not implement JSON mode.
            payload.pop('response_format')
            response = await client.post(endpoint + '/chat/completions', json=payload)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
