"""Datenbank: SQLAlchemy 2 (PostgreSQL im Betrieb, SQLite in Tests und Entwicklung)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import einstellungen


class Basis(DeclarativeBase):
    pass


_engine: Engine | None = None
_fabrik: sessionmaker | None = None


def engine() -> Engine:
    global _engine, _fabrik
    if _engine is None:
        url = einstellungen().db_url()
        argumente = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, connect_args=argumente, pool_pre_ping=True)
        if url.startswith("sqlite"):
            @event.listens_for(_engine, "connect")
            def _fremdschluessel(verbindung, _):  # pragma: no cover - SQLite-Einstellung
                cursor = verbindung.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
        _fabrik = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def zuruecksetzen() -> None:
    """Für Tests: Engine nach geänderten Einstellungen neu aufbauen."""
    global _engine, _fabrik
    if _engine is not None:
        _engine.dispose()
    _engine, _fabrik = None, None


def sitzung() -> Iterator[Session]:
    engine()
    with _fabrik() as db:  # type: ignore[misc]
        yield db


def neue_sitzung() -> Session:
    engine()
    return _fabrik()  # type: ignore[misc]


def jetzt_utc() -> datetime:
    return datetime.now(UTC)


def utc(zeitpunkt: datetime | None) -> datetime | None:
    """SQLite liefert Zeiten ohne Zeitzone zurück; sie sind immer UTC."""
    if zeitpunkt is None:
        return None
    return zeitpunkt if zeitpunkt.tzinfo else zeitpunkt.replace(tzinfo=UTC)
