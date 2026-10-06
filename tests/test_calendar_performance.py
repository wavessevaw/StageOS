from sqlalchemy import event as sqlalchemy_event,select
from backend.engine import saved_event_plan,calendar_context
from backend.models import Event
from test_core import ctx  # noqa: F401


def test_batched_calendar_rechecks_same_conflicts_with_constant_query_count(ctx):
    c,Session,b,resources,request=ctx
    with Session() as db:
        events=list(db.scalars(select(Event).order_by(Event.start)))
        context=calendar_context(db,events)
        for ev in events:
            assert saved_event_plan(db,ev,context)==saved_event_plan(db,ev)
    engine=Session.kw['bind'];queries=[]
    def queried(*args):queries.append(args[2])
    sqlalchemy_event.listen(engine,'before_cursor_execute',queried)
    try:
        response=c.get('/api/events',headers={'Accept-Encoding':'identity'})
        assert response.status_code==200 and len(response.json())>=40
        assert len(queries)<20
    finally:sqlalchemy_event.remove(engine,'before_cursor_execute',queried)
    compressed=c.get('/api/events',headers={'Accept-Encoding':'gzip'})
    assert compressed.headers['content-encoding']=='gzip'
    assert compressed.json()==response.json()
    assert int(compressed.headers['content-length'])<len(response.content)/2
