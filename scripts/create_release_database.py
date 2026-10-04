"""Create an empty release database without touching a working database."""
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.app import create_app
from backend.models import make_engine

path = ROOT / 'database/stageos-empty.db'
path.parent.mkdir(exist_ok=True)
if path.exists():
    raise RuntimeError('Release database already exists; refusing to overwrite it')
engine = make_engine('sqlite:///' + path.as_posix())
try:
    create_app(engine, demo_enabled=False)
finally:
    engine.dispose()
with sqlite3.connect(path) as db:
    assert db.execute('pragma integrity_check').fetchone()[0] == 'ok'
    for table in ['resources', 'productions', 'events', 'bookings', 'tasks', 'audit', 'settings']:
        assert db.execute('select count(*) from ' + table).fetchone()[0] == 0
print('Empty release database: PASS')
