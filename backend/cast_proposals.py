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


COLLECTIVE_LABELS = {'солисты', 'в спектакле принимают участие', 'придворные',
                     'ромашки', 'служанки', 'ведущие', 'семейная пара', 'метель'}


def collective(role):
    return (role.get('collective') is True or role.get('role_type') == 'collective'
            or ' '.join(str(role.get('role', '')).casefold().split()).rstrip('.…:') in COLLECTIVE_LABELS)


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
                cast=cast, current=current, allowed=cast_allowed, count=len(current) if collective(role) else 1, section='roles', target=index))
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
        if row['section']=='roles' and not row['count']:
            row['issue'] = 'Коллективная запись: уточните индивидуальные роли и количество участников. Назначение оставлено пустым.'
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
    """Read current database context for every invocation; never commit assignments."""
    from .model_client import request_model
    rows = [r for r in slots(s, production) if r['department'] == department]
    diagnostics = []
    failed = set()
    pending = [r for r in rows if not r['current'] and r['allowed'] and r['count']]
    # Keep globally constrained roles first; never reorder their original keys.
    pending.sort(key=lambda r: (len(r['allowed']), r['target'] if r['section']=='roles' else -1, r['cast']))
    for row in pending:
        used = {i for other in rows if other['section']=='roles' and other['cast']==row['cast']
                and other['key']!=row['key'] for i in other['proposed']}
        allowed = [i for i in row['allowed'] if row['section']!='roles' or i not in used]
        counterpart = next((r for r in rows if r['section']==row['section'] and r['target']==row['target'] and r['cast']!=row['cast']), None)
        different = [i for i in allowed if not counterpart or i not in counterpart['proposed']]
        if row['section']=='roles' and different:
            allowed = different
        if not allowed:
            row['issue'] = 'Все допущенные артисты заняты в этом составе. Назначение оставлено пустым.'
            continue
        candidates = [{'id':c['id'], 'name':c['name']} for c in row['candidates'] if c['id'] in allowed]
        # This is a mechanically eligible EXAMPLE, never an approved cast or a fallback answer.
        # The model must still return a separately checked proposal; invalid output remains empty.
        example = {'answer':'Предложение', 'choices':[{'key':row['key'], 'people':allowed[:row['count']]}]}
        prompt = ('Выбери исполнителя только из candidates. Верни строго один объект JSON в показанном формате. '
                  'Это пример допустимого предложения, а не утверждённый состав. Можно заменить код на другой из candidates. '
                  'Не добавляй пункты. Ключ копируй точно. people — список чисел, не строк и не объектов. '
                  'Не превышай count. Если сведений недостаточно, people=[]. Пример: '
                  + json.dumps(example, ensure_ascii=False, separators=(',', ':')))
        context = {'production':production.name, 'role':row['label'], 'key':row['key'],
                   'cast':row['cast'], 'count':row['count'], 'candidates':candidates,
                   'occupied':sorted(used), 'existing':row['current']}
        messages = [{'role':'user', 'content':prompt+'\nДанные: '+json.dumps(context, ensure_ascii=False, separators=(',', ':'))}]
        for attempt in range(2):
            raw = None
            try:
                raw = await request_model(cfg, messages, client_factory, max_tokens=min(2048, max(256, row['count'] * 24 + 128)))
                result = json.loads(raw)
                if not isinstance(result,dict) or set(result)!={'answer','choices'} or not isinstance(result['answer'],str):
                    raise ValueError('Требуются только answer (строка) и choices')
                parsed = Choices.model_validate({'choices':result['choices']})
                if len(parsed.choices)!=1 or parsed.choices[0].key!=row['key']:
                    raise ValueError('Ответ должен содержать ровно переданный ключ '+row['key'])
                choice = parsed.choices[0]
                if any(i not in allowed for i in choice.people):
                    raise ValueError('Код отсутствует среди свободных candidates этого пункта')
                accepted = [Choice(key=r['key'], people=r['proposed']) for r in rows if r['proposed']]
                # Exclude the present slot defensively, then validate the accumulated cast.
                accepted = [c for c in accepted if c.key!=row['key']]
                checked_data(s, production, rows, accepted+[choice])
                row['proposed'] = choice.people
                row['issue'] = ('Модель оставила назначение пустым. Требуется проверка.' if not choice.people else
                    'Состав заполнен частично. Проверьте количество участников.' if len(choice.people)<row['count'] else '')
                diagnostics.append({'key':row['key'], 'attempt':attempt+1, 'valid':True})
                break
            except Exception as error:
                detail = str(error)[:600]
                diagnostics.append({'key':row['key'], 'attempt':attempt+1, 'valid':False,
                                    'error_type':type(error).__name__, 'error':detail})
                row['issue'] = 'Ответ отклонён: '+type(error).__name__+': '+detail
                if attempt==1:
                    failed.add(department)
                else:
                    messages = messages[:1]+[{'role':'user', 'content':'Предыдущий ответ отклонён: '+detail+'. Верни один исправленный JSON по исходным данным.'}]
    # Final validation after merging all small requests, including preserved assignments.
    checked_data(s, production, rows, [Choice(key=r['key'],people=r['proposed']) for r in rows])
    for row in rows:
        counterpart = next((r for r in rows if r['section']==row['section'] and r['target']==row['target'] and r['cast']!=row['cast']), None)
        if row['section']=='roles' and row['proposed'] and counterpart and row['proposed']==counterpart['proposed']:
            row['issue'] = 'Один исполнитель в обоих составах. Проверьте наличие замены.'
    return dict(production_id=production.id, version=production.version, rows=rows,
                model=cfg['model'], failed_departments=sorted(failed), diagnostics=diagnostics,
                notice='Предложение не сохранено. Это проверенные по допускам предложения, не утверждённый состав. Занятость на дату не проверена.')
