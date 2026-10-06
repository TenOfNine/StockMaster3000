"""Datenbank-URL aus Einzelteilen: beliebige Passwörter."""

import pytest
from sqlalchemy.engine import make_url

from stockmaster import config

PASSWOERTER = ["einfach123", "p@ss:w/rd#%&?'\"$x y", "a=b+c/d==", "ümläut ß € ~!*()[]{}"]


@pytest.mark.parametrize("passwort", PASSWOERTER)
def test_url_aus_einzelteilen_maskiert_sonderzeichen(monkeypatch, passwort):
    monkeypatch.setenv("SM_DATENBANK_HOST", "db")
    monkeypatch.setenv("SM_DATENBANK_PASSWORT", passwort)
    config.einstellungen.cache_clear()
    url = make_url(config.einstellungen().db_url())
    assert (url.host, url.port, url.database, url.username) == ("db", 5432, "stockmaster", "stockmaster")
    assert url.password == passwort
    assert url.drivername == "postgresql+psycopg"
    config.einstellungen.cache_clear()


def test_ohne_host_gilt_die_url(monkeypatch):
    monkeypatch.delenv("SM_DATENBANK_HOST", raising=False)
    monkeypatch.setenv("SM_DATENBANK_URL", "sqlite:///x.db")
    config.einstellungen.cache_clear()
    assert config.einstellungen().db_url() == "sqlite:///x.db"
    config.einstellungen.cache_clear()
