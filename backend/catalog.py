from sqlalchemy import select
from .models import Resource, Booking, Audit

VENUE_DEFAULTS = dict(seats=300,width=12,depth=10,height=8,power=80,dmx=8,orchestra=35,fly_system=True,movement=False,bar_load=300,gate_width=3,gate_height=3,travel=30,soffits=3,fly_bars=8,lighting_positions=5,pa=True,video=True,rooms=4,opening=8,closing=24)

def save_venue(s, body, venue=None):
    name=str(body.get('name','')).strip()
    if not name or len(name)>200: raise ValueError('Название площадки: от 1 до 200 символов')
    if not isinstance(body.get('data',{}),dict):raise ValueError('Паспорт площадки должен быть объектом')
    data={**VENUE_DEFAULTS,**(venue.data if venue else {}),**body.get('data',{})}
    for k in VENUE_DEFAULTS:
        if isinstance(VENUE_DEFAULTS[k],bool):
            if not isinstance(data[k],bool):raise ValueError('Ожидается Да/Нет')
        elif isinstance(data[k],bool) or not isinstance(data[k],(int,float)) or not 0<=data[k]<=100000:raise ValueError('Параметры площадки должны быть неотрицательными числами')
    if not 0<=data['opening']<data['closing']<=24:raise ValueError('Время открытия должно предшествовать закрытию: 0–24 часа')
    for k in ['fly_bars','soffits','lighting_positions']:
        if isinstance(data[k],bool) or not isinstance(data[k],int) or data[k]>200:raise ValueError('Количество механических ресурсов: целое от 0 до 200')
    for k in ['seats','orchestra','rooms','dmx']:
        if isinstance(data[k],bool) or not isinstance(data[k],int):raise ValueError('Места, помещения и световые линии: целые числа')
    if not venue:
        venue=Resource(kind='Venue',department='Площадки',name=name,data=data);s.add(venue);s.flush()
    else:venue.name=name;venue.data=data
    for kind,key,label in [('Fly Bar','fly_bars','Штанкет'),('Soffit','soffits','Софит'),('Lighting Position','lighting_positions','Световая позиция')]:
        current=[r for r in s.scalars(select(Resource).where(Resource.kind==kind).order_by(Resource.id)) if r.data.get('venue_id')==venue.id]
        for i in range(max(len(current),data[key])):
            if i>=data[key]:
                r=current[i];r.data={**r.data,'retired':True};continue
            r=current[i] if i<len(current) else Resource(kind=kind,department='Сцена' if kind=='Fly Bar' else 'Свет',name=f'{name} · {label} {i+1}')
            r.data={**(r.data or {}),'venue_id':venue.id,'capacity':data['bar_load'],'current_load':(r.data or {}).get('current_load',0),'movement':data['movement'],'scenery_allowed':True,'lighting_allowed':True,'retired':False}
            if i>=len(current):s.add(r)
    s.add(Audit(action='Паспорт площадки сохранён',data={'venue_id':venue.id,'name':name}))
    s.flush();return venue

def create_units(s, body):
    kind=body.get('kind');name=str(body.get('name','')).strip();qty=body.get('quantity',1)
    if kind not in ['Equipment','Scenery','Prop','Costume'] or not name or len(name)>190 or isinstance(qty,bool) or not isinstance(qty,int) or not 1<=qty<=200:raise ValueError('Укажите тип, название и количество от 1 до 200')
    data=validate_resource(s,kind,str(body.get('department','Сцена')),body.get('data',{}))
    if kind=='Scenery':
        for key in ['width','height','depth','mass','setup']:
            if not isinstance(data.get(key,0),(int,float)) or data.get(key,0)<0:raise ValueError('Размеры и масса не могут быть отрицательными')
        data={**dict(width=1,height=1,depth=1,mass=1,setup=10,crew=2,fly=False),**data}
    result=[]
    for i in range(qty):
        item=Resource(kind=kind,name=name if qty==1 else f'{name} · №{i+1}',department=str(body.get('department','Сцена')),data={**data,'item_name':name,'quantity':1})
        s.add(item);s.flush();result.append(item)
    s.add(Audit(action='Позиции имущества созданы',data={'name':name,'quantity':qty,'ids':[r.id for r in result]}))
    return result

def validate_resource(s, kind, department, data):
    from .production_editor import number
    if not isinstance(data,dict):raise ValueError('Паспорт ресурса должен быть объектом')
    d=dict(data)
    if kind=='Person':
        if not str(department).strip():raise ValueError('Укажите цех сотрудника')
        qs=d.get('qualification')
        if not isinstance(qs,list) or not qs or any(not isinstance(q,str) or not q.strip() for q in qs):raise ValueError('Укажите квалификацию сотрудника')
        d.setdefault('specialization',department)
    for key in ['width','depth','height','mass','setup','crew','capacity','current_load','travel','power','dmx']:
        if key in d:number(d[key],'Параметр ресурса '+key,integer=key in ['crew','dmx'])
    if kind in ['Room','Fly Bar','Soffit','Lighting Position']:
        parent=s.get(Resource,d.get('venue_id')) if isinstance(d.get('venue_id'),int) else None
        if not parent or parent.kind!='Venue':raise ValueError('Укажите площадку ресурса')
    if kind=='Room':
        number(d.get('capacity',0),'Вместимость помещения',0,100000,True)
    if kind=='Equipment Kit':
        items=d.get('items')
        if not isinstance(items,list) or not items:raise ValueError('Выберите имущество комплекта')
        if any(not isinstance(i,int) or isinstance(i,bool) for i in items) or len(set(items))!=len(items):raise ValueError('Состав комплекта содержит неверные или повторные ресурсы')
        for rid in items:
            r=s.get(Resource,rid)
            if not r or r.kind!='Equipment':raise ValueError('Комплект может содержать только оборудование')
    if kind=='Scenery':
        d={**dict(width=1,height=1,depth=1,mass=1,setup=10,crew=2,fly=False),**d}
        if not isinstance(d['fly'],bool):raise ValueError('Подвес декорации: требуется Да/Нет')
    return d
