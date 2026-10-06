"""Validated production passports and a template independent of example data."""
from copy import deepcopy
import math
from .models import Resource

REQUIREMENTS = dict(width=0, depth=0, height=0, soffits=0, preferred_soffits=0,
    fly_bars=0, moving_fly_bars=0, power=0, dmx=0, orchestra=0, bar_load=0,
    gate_width=0, gate_height=0, lighting_positions=0, pa=False, video=False)
PIPELINE = dict(load=0, unload=0, stage=0, lighting=0, sound=0, video=0,
    rf=0, orchestra=0, check=15, teardown=15)
DEPARTMENTS = ['Артисты','Хор','Балет','Оркестр','Режиссёр','Дирижёр','Помреж',
    'Техдир','Звук','Свет','Видео','Сцена','Грим','Костюм','Реквизит','Транспорт','Монтаж','Риггинг']

def template():
    return {'name':'', 'data': dict(genre='', duration=120, preparation=30, home_venue=0,
        responsibles={d:0 for d in ['Режиссёр','Дирижёр','Помреж','Техдир','Звук','Свет','Видео','Сцена']},
        roles=[], groups={d:[] for d in ['Хор','Балет','Оркестр','Грим','Костюм']},
        crew={d:[] for d in ['Сцена','Звук','Свет','Видео','Монтаж','Риггинг','Реквизит','Транспорт']},
        orchestra_versions={'Full':[],'Reduced':[],'Touring':[]}, equipment_kits=[],
        items=[], scenery=[], props=[], vehicle=0, requirements=deepcopy(REQUIREMENTS),
        scenes=[], pipeline=deepcopy(PIPELINE), overrides={},
        sound_notes='', lighting_notes='', video_notes='', stage_notes='', costume_notes='',
        props_notes='', transport_notes='', safety_notes='')}

def number(v, label, low=0, high=100000, integer=False):
    if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not low <= v <= high or (integer and not isinstance(v,int)):
        raise ValueError(f'{label}: требуется {"целое " if integer else ""}число от {low} до {high}')
    return v

def requirements(source):
    if not isinstance(source,dict): raise ValueError('Технические требования должны быть объектом')
    d={**REQUIREMENTS,**source}
    for key, default in REQUIREMENTS.items():
        if isinstance(default,bool):
            if not isinstance(d[key],bool): raise ValueError('Звук и видео: требуется Да/Нет')
        else: number(d[key], 'Технические требования: '+key, integer=key in ['soffits','preferred_soffits','fly_bars','moving_fly_bars','dmx','orchestra','lighting_positions'])
    if d['moving_fly_bars']>d['fly_bars']:raise ValueError('Подвижных штанкетов не может быть больше общего количества')
    return d

def validate_production(s, source, *, check_qualifications=True, allow_retired=False):
    if not isinstance(source,dict):raise ValueError('Паспорт постановки должен быть объектом')
    required=['duration','home_venue','responsibles','roles','groups','crew','equipment_kits','scenery','props','vehicle','requirements','scenes','pipeline','overrides']
    if any(k not in source for k in required):raise ValueError('Паспорт постановки неполон')
    d=deepcopy(source)
    def ref(rid,kinds):
        r=s.get(Resource,rid) if isinstance(rid,int) and not isinstance(rid,bool) and rid>0 else None
        if not r or r.kind not in kinds or (r.data.get('retired') and not allow_retired):raise ValueError(f'Неверный или выведенный из эксплуатации ресурс: {rid}')
        return r
    def ids(value,kinds):
        if not isinstance(value,list):raise ValueError('Состав должен быть списком ресурсов')
        if any(not isinstance(i,int) or isinstance(i,bool) for i in value):raise ValueError('Неверный идентификатор ресурса')
        if len(set(value))!=len(value):raise ValueError('Ресурс указан несколько раз в одном списке')
        for rid in value:ref(rid,kinds)
    number(d['duration'],'Продолжительность, мин',15,480,True)
    if 'preparation' in d:number(d['preparation'],'Подготовка, мин',0,1440,True)
    number(d['home_venue'],'Основная площадка',0,1000000000,True)
    if d['home_venue']:ref(d['home_venue'],['Venue'])
    if d['vehicle']:ref(d['vehicle'],['Vehicle'])
    for group in ['responsibles','groups','crew','orchestra_versions','pipeline','overrides']:
        if not isinstance(d.get(group,{}),dict):raise ValueError('Раздел паспорта должен быть объектом: '+group)
    for dept,value in d['responsibles'].items():
        people=responsible_ids(value)
        ids(people,['Person'])
        for rid in people:
            person=ref(rid,['Person'])
            if check_qualifications and dept not in person.data.get('qualification',[]):raise ValueError('Сотрудник не имеет квалификации: '+dept)
    d['responsibles']={k:v for k,v in d['responsibles'].items() if v}
    for group in ['groups','crew','orchestra_versions']:
        for dept,people in d.get(group,{}).items():
            ids(people,['Person'])
            qualification='Оркестр' if group=='orchestra_versions' else dept
            for rid in people:
                if check_qualifications and qualification not in ref(rid,['Person']).data.get('qualification',[]):raise ValueError('Сотрудник не имеет квалификации: '+qualification)
    for section in ['groups','crew']:
        casts=d.get(section+'_casts',{})
        if not isinstance(casts,dict):raise ValueError('Составы подразделений должны быть объектом')
        for dept,options in casts.items():
            if not isinstance(options,dict) or set(options)-{'A','B'}:raise ValueError('Допустимы первый и второй состав')
            for people in options.values():
                ids(people,['Person'])
                for rid in people:
                    if check_qualifications and dept not in ref(rid,['Person']).data.get('qualification',[]):raise ValueError('Сотрудник не имеет квалификации: '+dept)
    if not isinstance(d['roles'],list) or not isinstance(d['scenes'],list):raise ValueError('Роли и сцены должны быть списками')
    for role in d['roles']:
        if not isinstance(role,dict) or not str(role.get('role','')).strip():raise ValueError('Укажите название роли')
        for key in ['A','B']:
            number(role.get(key,0),'Исполнитель состава',0,1000000000,True)
            role.setdefault(key,0)
            if not role[key]:continue
            person=ref(role[key],['Person'])
            if check_qualifications and 'Артисты' not in person.data.get('qualification',[]):raise ValueError('Исполнитель роли должен иметь квалификацию артиста')
        ids(role.get('eligible'),['Person'])
        if any(role[key] and role[key] not in role['eligible'] for key in ['A','B']):raise ValueError('Назначенные исполнители должны входить в допущенных исполнителей')
        for rid in role['eligible']:
            if check_qualifications and 'Артисты' not in ref(rid,['Person']).data.get('qualification',[]):raise ValueError('Резерв роли должен иметь квалификацию артиста')
    for key,kinds in [('equipment_kits',['Equipment Kit']),('scenery',['Scenery']),('props',['Prop','Costume']),('items',['Equipment','Scenery','Prop','Costume'])]:ids(d.get(key,[]),kinds)
    for scene in d['scenes']:
        if not isinstance(scene,dict) or not str(scene.get('name','')).strip() or not isinstance(scene.get('roles'),list):raise ValueError('Укажите название и роли сцены')
        if any(isinstance(i,bool) or not isinstance(i,int) or i<0 or i>=len(d['roles']) for i in scene['roles']):raise ValueError('Сцена ссылается на отсутствующую роль')
    for key in PIPELINE:number(d['pipeline'].get(key),'Длительность этапа '+key,0,1440,True)
    d['preparation']=d['pipeline']['load']+d['pipeline']['unload']+max(d['pipeline']['stage']+d['pipeline']['orchestra'],d['pipeline']['lighting'],d['pipeline']['sound']+d['pipeline']['rf'],d['pipeline']['video'])+d['pipeline']['check']+15
    d['requirements']=requirements(d['requirements'])
    for vid,ov in d['overrides'].items():
        try:ref(int(vid),['Venue'])
        except (TypeError,ValueError):raise ValueError('Адаптация ссылается на отсутствующую площадку')
        if not isinstance(ov,dict) or ov.get('version') not in ['FULL VERSION','REDUCED VERSION','TOURING VERSION']:raise ValueError('Недопустимая версия адаптации')
        ov['requirements']=requirements(ov.get('requirements',{}))
        ids(ov.get('orchestra',[]),['Person']);ids(ov.get('scenery',[]),['Scenery'])
        for rid in ov.get('orchestra',[]):
            if check_qualifications and 'Оркестр' not in ref(rid,['Person']).data.get('qualification',[]):raise ValueError('Адаптация требует музыканта оркестра')
    return d

def responsible_ids(value):
    return value if isinstance(value,list) else [value] if value else []

def referenced_ids(data):
    """IDs only; dimensions, quantities and numeric scene indices are not references."""
    out=set()
    for k in ['home_venue','vehicle']:
        if data.get(k):out.add(data[k])
    for value in data.get('responsibles',{}).values():out.update(responsible_ids(value))
    for k in ['groups','crew','orchestra_versions']:
        for ids in data.get(k,{}).values():out.update(ids)
    for role in data.get('roles',[]):
        out.update(role.get('eligible',[]));out.update([role.get('A'),role.get('B')])
    for k in ['equipment_kits','items','scenery','props']:out.update(data.get(k,[]))
    for vid,ov in data.get('overrides',{}).items():
        out.add(int(vid));out.update(ov.get('orchestra',[]));out.update(ov.get('scenery',[]))
    for section in ['groups','crew']:
        for options in data.get(section+'_casts',{}).values():
            for people in options.values():out.update(people)
    return {rid for rid in out if isinstance(rid,int) and not isinstance(rid,bool) and rid>0}


def cast_people(data, section, cast):
    """Old passports use the same list in both casts; explicit empty casts stay empty."""
    base=data.get(section,{})
    overrides=data.get(section+'_casts',{})
    return {dept:list(overrides.get(dept,{}).get(cast,base.get(dept,[])))
            for dept in dict.fromkeys([*base,*overrides])}
