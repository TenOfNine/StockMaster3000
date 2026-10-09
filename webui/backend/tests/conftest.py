"""Test-Fixtures: Demo-Datenverzeichnis (einmal je Lauf), frische Datenbank und App-Verzeichnis je Test."""

from __future__ import annotations

import base64
import subprocess
import sys
from pathlib import Path

import pyotp
import pytest

WURZEL = Path(__file__).resolve().parents[3]
BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

SCHLUESSEL = base64.b64encode(b"k" * 32).decode()
ADMIN_PW = "Admin-Passwort-2026!"
NUTZER_PW = "Nutzer-Passwort-2026!"


@pytest.fixture(scope="session")
def demo_repo(tmp_path_factory) -> Path:
    ziel = tmp_path_factory.mktemp("demo") / "daten"
    subprocess.run([sys.executable, str(WURZEL / "webui" / "demo" / "demo_daten.py"), "--ziel", str(ziel),
                    "--tage", "75", "--ende", "2026-09-30", "--seed", "3"], check=True, capture_output=True)
    return ziel


@pytest.fixture
def app(demo_repo, tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKMASTER_DATA_DIR", str(demo_repo))
    monkeypatch.setenv("STOCKMASTER_FRAMEWORK_DIR", str(WURZEL))
    monkeypatch.setenv("STOCKMASTER_APP_DIR", str(tmp_path / "app"))
    monkeypatch.setenv("SM_AUFTRAG_WARTEN_SEKUNDEN", "0")
    monkeypatch.setenv("SM_DATENBANK_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("SM_COOKIE_SICHER", "false")
    monkeypatch.setenv("SM_SCHLUESSEL", SCHLUESSEL)
    monkeypatch.setenv("SM_ERLAUBTE_NETZE", "[]")
    from stockmaster import config, db, main, modelle  # noqa: F401
    from stockmaster.sicherheit import begrenzer
    from stockmaster.spiel import lesen

    config.einstellungen.cache_clear()
    db.zuruecksetzen()
    lesen.zuruecksetzen()
    begrenzer.leeren()
    db.Basis.metadata.create_all(db.engine())
    anwendung = main.app_erstellen()
    yield anwendung
    db.zuruecksetzen()


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app, base_url="http://testserver") as c:
        yield c


def benutzer_anlegen(email: str, passwort: str, admin: bool = False, totp: str | None = None,
                     wechsel: bool = False):
    from stockmaster import sicherheit as s
    from stockmaster.db import neue_sitzung
    from stockmaster.modelle import Benutzer

    with neue_sitzung() as db:
        b = Benutzer(email=email, anzeigename=email.split("@")[0], kennung=s.neue_kennung(),
                     passwort_hash=s.passwort_hash(passwort), ist_admin=admin, passwortwechsel_noetig=wechsel)
        db.add(b)
        db.flush()
        if totp:
            b.totp_secret_enc = s.totp_verschluesseln(totp, b.id)
            b.totp_aktiv = True
        db.commit()
        return b.id


def anmelden(client, email: str, passwort: str) -> str:
    """Anmeldung nur mit Passwort (kein Zwei-Faktor-Schritt, Entscheidung 40)."""
    antwort = client.post("/api/auth/login", json={"email": email, "passwort": passwort})
    assert antwort.status_code == 200, antwort.text
    daten = antwort.json()
    assert daten["naechster_schritt"] in ("fertig", "passwort_aendern")
    client.headers["X-CSRF-Token"] = daten["csrf"]
    return daten["naechster_schritt"]


def totp_code(client) -> str:
    """Aktueller Zwei-Faktor-Code des Test-Administrators (nur zum Anlegen neuer Benutzer nötig)."""
    return pyotp.TOTP(client.totp).now()


@pytest.fixture
def nutzer(client):
    benutzer_anlegen("nutzer@example.org", NUTZER_PW)
    assert anmelden(client, "nutzer@example.org", NUTZER_PW) == "fertig"
    return client


@pytest.fixture
def admin(client):
    geheimnis = pyotp.random_base32()
    benutzer_anlegen("admin@example.org", ADMIN_PW, admin=True, totp=geheimnis)
    assert anmelden(client, "admin@example.org", ADMIN_PW) == "fertig"
    client.totp = geheimnis
    return client
