"""Per-theatre editable qualification names, separate from primary departments."""
from sqlalchemy import select
from .models import Setting, Resource, Production, Event
from .production_editor import DEPARTMENTS


def names(s):
    setting=s.get(Setting,'qualification_catalog')
    if setting:
        return setting.value['names']
    result=list(DEPARTMENTS)
    for person in s.scalars(select(Resource).where(Resource.kind=='Person')):
        result.extend(person.data.get('qualification',[]))
    return sorted(set(result))


def usages(s, name):
    people=[p.name for p in s.scalars(select(Resource).where(Resource.kind=='Person'))
            if name in p.data.get('qualification',[]) or p.department==name]
    productions=[]
    for p in s.scalars(select(Production)):
        d=p.data
        if d.get('responsibles',{}).get(name) or any(d.get(key,{}).get(name) for key in ('crew','groups')) or any(
            any(d.get(key,{}).get(name,{}).values()) for key in ('crew_casts','groups_casts')):
            productions.append(p.name)
    events=[e.title for e in s.scalars(select(Event).where(Event.status!='Cancelled'))
            if any(a.get('department')==name for a in e.data.get('plan',{}).get('assignments',[]))]
    return {'people':people,'productions':productions,'events':events}
