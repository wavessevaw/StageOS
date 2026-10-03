from alembic import context
from sqlalchemy import engine_from_config, pool
from backend.models import Base

config = context.config


def run(connection):
    context.configure(
        connection=connection, target_metadata=Base.metadata, render_as_batch=True
    )
    with context.begin_transaction():
        context.run_migrations()


if config.attributes.get("connection") is not None:
    run(config.attributes["connection"])
else:
    from backend.models import make_engine

    with make_engine().connect() as connection:
        run(connection)
