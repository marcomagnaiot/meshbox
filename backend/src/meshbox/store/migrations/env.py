"""Entorno de Alembic. Se configura desde `meshbox.store.migrate` (sin alembic.ini)."""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine

config = context.config
url = config.get_main_option("sqlalchemy.url")
assert url, "falta sqlalchemy.url"

engine = create_engine(url)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=None, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
