from sqlalchemy import create_engine

from alembic import context
from stockmaster import modelle  # noqa: F401  (Tabellen registrieren)
from stockmaster.config import einstellungen
from stockmaster.db import Basis

ziel = Basis.metadata


def run_migrations_offline() -> None:
    context.configure(url=einstellungen().db_url(), target_metadata=ziel, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(einstellungen().db_url())
    with engine.connect() as verbindung:
        context.configure(connection=verbindung, target_metadata=ziel, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
