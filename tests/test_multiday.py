from test_core import ctx, confirm
from backend.engine import TaskTiming, ExtraTask
from backend.timing import retime
from datetime import datetime, timedelta
import pytest


def test_multiday_preparation_is_saved_and_rechecked(ctx):
    c, S, b, rs, r = ctx
    r.update(start='2026-12-06T18:00:00', run_through=True,
             task_overrides={'Выезд': {'start': '2026-12-03T08:00:00'},
                             'Монтаж сцены': {'start': '2026-12-05T09:00:00'}})
    response=c.post('/api/preview',json=r)
    assert response.status_code==200,response.text
    plan=response.json();tasks={t['name']:t for t in plan['tasks']}
    assert tasks['Выезд']['start']=='2026-12-03T08:00:00'
    assert tasks['Монтаж сцены']['start']=='2026-12-05T09:00:00'
    assert tasks['Прогон']['start']=='2026-12-06T11:00:00'
    assert tasks['Готовность']['end']<=tasks['Прогон']['start']
    assert not any(x['code']=='setup' for x in plan['conflicts'])
    saved=confirm(c,r)
    assert saved.status_code==200,saved.text
    detail=c.get('/api/events/'+str(saved.json()['id'])).json()['current']
    assert detail['request']['task_overrides']==plan['request']['task_overrides']
    assert not any(x['code']=='setup' for x in detail['conflicts'])


def test_long_stage_crosses_midnight_and_precedence_is_kept():
    show=datetime(2026,12,6,18)
    tasks=[dict(name='Монтаж сцены',department='Сцена',start=show-timedelta(hours=3),end=show-timedelta(hours=1)),
           dict(name='Спектакль',department='Все',start=show,end=show+timedelta(hours=2))]
    result,_=retime(tasks,{'Монтаж сцены':TaskTiming(start=datetime(2026,12,4,9),duration=1800)},show,
                    dependencies={'Спектакль':['Монтаж сцены']})
    assert result[0]['end']==datetime(2026,12,5,15)
    ExtraTask(name='Монтаж',start=datetime(2026,12,4,9),duration=1800)
    with pytest.raises(ValueError):
        retime(tasks,{'Монтаж сцены':TaskTiming(start=show+timedelta(days=1))},show,
               dependencies={'Спектакль':['Монтаж сцены']})
