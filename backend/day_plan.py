"""Default day sequence based on the theatre's production plan."""
from datetime import timedelta


def baseline(tasks, start, duration, run_through=True):
    end = start + timedelta(minutes=duration)
    rows = [
        ('Монтаж сцены','Сцена',-600,120),
        ('Световой монтаж','Свет',-600,120),
        ('Звуковой монтаж','Звук',-600,120),
        ('Видеомонтаж','Видео',-600,120),
        ('Orchestra setup','Оркестр',-540,60),
        ('Technical Check','Все',-480,40),
        ('Готовность','Все',-440,15),
    ]
    if run_through:
        rows += [('Прогон','Все',-420,180),('Обед','Все',-240,180)]
    rows += [('Сбор перед спектаклем','Все',-60,60),('Спектакль','Все',0,duration)]
    original = {t['name']:int((t['end']-t['start']).total_seconds()/60) for t in tasks}
    result = [dict(name=n,department=d,start=start+timedelta(minutes=offset),end=start+timedelta(minutes=offset+max(minutes,original.get(n,0)))) for n,d,offset,minutes in rows]
    # Preserve required transport and RF checks from the passport; zero stages
    # are omitted. Transport finishes before the parallel setup starts.
    before = start-timedelta(hours=10)
    for task in reversed([t for t in tasks if t['name'] in {'Погрузка','Выезд','Разгрузка'}]):
        minutes = task['end']-task['start']
        if minutes.total_seconds()>0:
            result.append({**task,'start':before-minutes,'end':before})
            before -= minutes
    for task in tasks:
        if task['name']=='RF check' and task['end']>task['start']:
            result.append({**task,'start':start-timedelta(hours=8),'end':start-timedelta(hours=8)+(task['end']-task['start'])})
    teardown = max(90, original.get('Демонтаж',0))
    returning = max(60, original.get('Возврат',0))
    result += [dict(name='Демонтаж',department='Все',start=end+timedelta(hours=1),end=end+timedelta(minutes=60+teardown)),
               dict(name='Возврат',department='Транспорт',start=end+timedelta(minutes=60+teardown),end=end+timedelta(minutes=60+teardown+returning))]
    return sorted(result,key=lambda t:t['start'])
