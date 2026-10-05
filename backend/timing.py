"""Editable production timeline: fixed user anchors with precedence constraints."""
from datetime import datetime, timedelta
from ortools.sat.python import cp_model

DEPS = {
    'Выезд':['Погрузка'], 'Разгрузка':['Выезд'],
    **{x:['Разгрузка'] for x in ['Монтаж сцены','Световой монтаж','Звуковой монтаж','Видеомонтаж']},
    'RF check':['Звуковой монтаж'], 'Orchestra setup':['Монтаж сцены'],
    'Technical Check':['Монтаж сцены','Световой монтаж','RF check','Видеомонтаж','Orchestra setup'],
    'Готовность':['Technical Check'], 'Прогон':['Готовность'], 'Обед':['Прогон'],
    'Сбор перед спектаклем':['Обед'], 'Спектакль':['Готовность','Сбор перед спектаклем'],
    'Демонтаж':['Спектакль'], 'Возврат':['Демонтаж'],
    'Репетиция':['Подготовка репетиции'], 'Освобождение зала':['Репетиция'],
}

def retime(tasks, overrides, start, run_through=False, dependencies=None):
    deps=DEPS if dependencies is None else dependencies
    origin = start.replace(hour=0, minute=0) - timedelta(days=1)
    names = {t['name'] for t in tasks}
    if set(overrides)-names:
        raise ValueError('Неизвестный этап производственного плана')
    model=cp_model.CpModel(); starts={}; ends={}; intervals={}; penalties=[]
    baseline={t['name']:int((t['start']-origin).total_seconds()/60) for t in tasks}
    # A single edited anchor shifts the preferred times of its successors, not the performance.
    preferred=dict(baseline)
    for name, edit in overrides.items():
        if edit.start is None: continue
        delta=int((edit.start-origin).total_seconds()/60)-baseline[name]
        boundaries={'Спектакль','Репетиция','Прогон'}
        descendants={name}
        ancestors={name}
        for _ in tasks:
            descendants.update(n for n in names if n not in boundaries and any(d in descendants and d not in boundaries for d in deps.get(n,[])))
            ancestors.update(d for n in list(ancestors) if n not in boundaries for d in deps.get(n,[]) if d in names and d not in boundaries)
        for n in (descendants | ancestors) - boundaries:
            preferred[n]=baseline[n]+delta
    for t in tasks:
        n=t['name']; edit=overrides.get(n)
        dur=edit.duration if edit and edit.duration is not None else int((t['end']-t['start']).total_seconds()/60)
        a=model.new_int_var(0,4320,n); b=model.new_int_var(0,4320,n+'_end')
        starts[n]=a; ends[n]=b; intervals[n]=model.new_interval_var(a,dur,b,n)
        if n in ['Спектакль','Репетиция']:
            model.add(a==baseline[n])
            if edit: raise ValueError('Время основного события изменяется в форме назначения')
        elif n=='Прогон' and not (edit and edit.start is not None):
            model.add(a==baseline[n])
        elif edit and edit.start is not None:
            model.add(a==int((edit.start-origin).total_seconds()/60))
        diff=model.new_int_var(0,10000,n+'_deviation'); model.add_abs_equality(diff,a-preferred[n]); penalties.append(diff)
    for n in names:
        for dep in deps.get(n,[]):
            if dep in names: model.add(starts[n]>=ends[dep]+(10 if n=='Демонтаж' else 0))
    for dep in {t['department'] for t in tasks} - {'Все'}:
        model.add_no_overlap([intervals[t['name']] for t in tasks if t['department']==dep])
    model.minimize(sum(penalties)); solver=cp_model.CpSolver(); solver.parameters.num_search_workers=1; solver.parameters.max_time_in_seconds=3
    status=solver.solve(model)
    if status not in (cp_model.OPTIMAL,cp_model.FEASIBLE):
        raise ValueError('Указанные времена несовместимы: монтаж и проверка должны завершиться до прогона/спектакля; обед и сбор — после прогона. Измените время или длительность этапов.')
    return sorted([{**t,'start':origin+timedelta(minutes=solver.value(starts[t['name']])),'end':origin+timedelta(minutes=solver.value(ends[t['name']]))} for t in tasks],key=lambda t:t['start']), {'status':solver.status_name(status),'objective':solver.objective_value}


def customize(tasks,removed,extra):
    """Remove optional nodes, reconnect dependencies, then add event-only tasks."""
    original={t['name'] for t in tasks}
    gone=set(removed)
    if gone-original:raise ValueError('Неизвестный удаляемый этап')
    if gone & {'Спектакль','Репетиция'}:raise ValueError('Основное событие нельзя удалить из производственного плана')
    added=[t.name for t in extra]
    if len(set(added))!=len(added) or set(added)&(original|set(DEPS)):
        raise ValueError('Названия дополнительных этапов должны быть уникальны. Удалённый стандартный этап можно восстановить.')
    names=(original-gone)|set(added)
    def upstream(name,seen=None):
        seen=set() if seen is None else seen
        if name in seen:raise ValueError('Циклическая зависимость этапов')
        if name in names:return [name]
        return [p for dep in DEPS.get(name,[]) for p in upstream(dep,seen|{name})]
    deps={name:list(dict.fromkeys(p for dep in DEPS.get(name,[]) for p in upstream(dep))) for name in original-gone}
    result=[dict(t) for t in tasks if t['name'] not in gone]
    for t in extra:deps[t.name]=[t.after] if t.after else []
    for t in extra:
        for ref in [t.after,t.before]:
            if ref and (ref not in names or ref==t.name):raise ValueError('Укажите существующий другой этап зависимости')
        if t.before:deps.setdefault(t.before,[]).append(t.name)
        result.append(dict(name=t.name,department=t.department,start=t.start,end=t.start+timedelta(minutes=t.duration),custom=True))
    # Reject cycles even for zero-duration original tasks.
    visited=set()
    def visit(name,path):
        if name in path:raise ValueError('Циклическая зависимость этапов')
        if name in visited:return
        for dep in deps.get(name,[]):visit(dep,path|{name})
        visited.add(name)
    for name in names:visit(name,set())
    return result,deps
