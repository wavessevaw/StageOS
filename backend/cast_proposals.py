"""Read-only model proposals, with deterministic eligibility checks on every save."""
from copy import deepcopy
import json
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy import select
from .models import Resource
from .production_editor import validate_production


class Choice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    key: str = Field(max_length=160)
    people: list[StrictInt] = Field(max_length=100)


class Choices(BaseModel):
    model_config = ConfigDict(extra='forbid')
    choices: list[Choice] = Field(max_length=300)


class Confirmation(Choices):
    version: StrictInt


def slots(s, production):
    data = production.data
    people = {r.id: r for r in s.scalars(select(Resource).where(Resource.kind == 'Person'))
              if not r.data.get('retired')}
    def eligible(ids, dept):
        return sorted({i for i in ids if i in people and dept in people[i].data.get('qualification', [])})
    rows = []
    for index, role in enumerate(data.get('roles', [])):
        allowed = eligible(role.get('eligible', []), 'Артисты')
        for cast in ('A', 'B'):
            current = [role[cast]] if role.get(cast) else []
            occupied = {other.get(cast) for i, other in enumerate(data.get('roles', [])) if i != index and other.get(cast)}
            cast_allowed = [i for i in allowed if i not in occupied] if not current else allowed
            rows.append(dict(key=f'role:{index}:{cast}', label=role['role'], department='Артисты',
                cast=cast, current=current, allowed=cast_allowed, count=1, section='roles', target=index))
    for section in ('groups', 'crew'):
        base = data.get(section, {})
        overrides = data.get(section + '_casts', {})
        for dept in sorted(set(base) | set(overrides)):
            options = overrides.get(dept, {})
            pool = list(base.get(dept, [])) + options.get('A', []) + options.get('B', [])
            allowed = eligible(pool, dept)
            for cast in ('A', 'B'):
                current = list(options.get(cast, []))
                count = max(len(base.get(dept, [])), len(options.get('A', [])), len(options.get('B', [])))
                rows.append(dict(key=f'{section}:{dept}:{cast}', label=dept, department=dept,
                    cast=cast, current=current, allowed=allowed, count=count, section=section, target=dept))
    for row in rows:
        row['candidates'] = [dict(id=i, name=people[i].name,
            specialization=str(people[i].data.get('specialization', ''))) for i in row['allowed']]
        row['proposed'] = list(row['current'])
        row['issue'] = '' if row['current'] or row['allowed'] else 'Нет допущенных сотрудников. Заполните паспорт постановки.'
    return rows


def checked_data(s, production, rows, choices):
    by_key = {r['key']: r for r in rows}
    seen = set()
    data = deepcopy(production.data)
    for choice in choices:
        row = by_key.get(choice.key)
        if not row or choice.key in seen:
            raise ValueError('Неизвестный или повторный пункт состава')
        seen.add(choice.key)
        ids = choice.people
        if row['current'] and ids != row['current']:
            raise ValueError('Заполненный состав изменён. Используйте редактор постановки.')
        if len(ids) != len(set(ids)) or any(i not in row['allowed'] for i in ids):
            raise ValueError('Сотрудник отсутствует в допущенных исполнителях или указан повторно')
        if len(ids) > row['count']:
            raise ValueError('Предложение превышает количество мест в составе')
        if not ids:
            continue
        cast = row['cast']
        if row['section'] == 'roles':
            data['roles'][row['target']][cast] = ids[0]
        else:
            data.setdefault(row['section'] + '_casts', {}).setdefault(row['target'], {})[cast] = ids
    for cast in ('A', 'B'):
        ids = [r.get(cast) for r in data.get('roles', []) if r.get(cast)]
        if len(ids) != len(set(ids)):
            raise ValueError('Один артист назначен на несколько ролей одного состава')
    return validate_production(s, data)


async def propose(s, production, cfg, client_factory, department='Артисты'):
    from .model_client import request_model, structured_content
    rows = [r for r in slots(s, production) if r['department'] == department]
    pending = [r for r in rows if not r['current'] and r['allowed'] and r['count']]
    # One bounded request per department, rather than passing the entire theatre to a small model.
    errors = []
    for dept in dict.fromkeys(r['department'] for r in pending):
        batch = [r for r in pending if r['department'] == dept]
        if len(batch) > 40 or any(len(r['allowed']) > 100 for r in batch):
            for row in batch:
                row['issue'] = 'Слишком большой раздел для малой модели. Заполните вручную.'
            continue
        prompt = ('Предложи только незаполненные составы. Не выдумывай людей, допуски или факты. '
            'Бери идентификаторы только из candidates соответствующего пункта. '
            'Не назначай одного артиста на разные роли одного состава. При наличии замен предпочитай разных людей в первом и втором составах. Не превышай count. '
            'Если информации недостаточно, верни пустой people. Верни JSON '
            '{"answer":"краткое пояснение", "choices":[{"key":"ключ пункта","people":[1]}]}. /no_think')
        try:
            raw = await request_model(cfg, [{'role':'system', 'content':prompt},
                {'role':'user', 'content':json.dumps({'production':production.name, 'department':dept,
                    'slots':batch}, ensure_ascii=False)}], client_factory, max_tokens=2048)
            result = structured_content(raw)
            parsed = Choices.model_validate({'choices':result.get('choices', [])})
            batch_keys = {r['key'] for r in batch}
            if any(c.key not in batch_keys for c in parsed.choices):
                raise ValueError('Модель вернула пункт другого подразделения')
            accepted = [Choice(key=r['key'], people=r['proposed']) for r in rows if r['proposed'] and not r['current']]
            checked_data(s, production, rows, accepted + parsed.choices)
            for choice in parsed.choices:
                next(r for r in rows if r['key'] == choice.key)['proposed'] = choice.people
            for row in batch:
                if not row['proposed']:
                    row['issue'] = 'Недостаточно сведений для назначения. Выберите вручную или дополните допуски.'
                elif len(row['proposed']) < row['count']:
                    row['issue'] = 'Состав заполнен частично. Проверьте количество участников.'
        except Exception:
            errors.append(dept)
            for row in batch:
                row['issue'] = 'Модель не предложила допустимый состав. Выберите сотрудников вручную.'
    for row in rows:
        counterpart = next((r for r in rows if r['section']==row['section'] and r['target']==row['target'] and r['cast']!=row['cast']), None)
        if row['section']=='roles' and row['proposed'] and counterpart and row['proposed']==counterpart['proposed']:
            row['issue'] = 'Один исполнитель в обоих составах. Проверьте наличие замены.'
    return dict(production_id=production.id, version=production.version, rows=rows,
        model=cfg['model'], failed_departments=errors,
        notice='Предложение не сохранено. Проверяются допуски, а не занятость на конкретную дату. События календаря не меняются.')
