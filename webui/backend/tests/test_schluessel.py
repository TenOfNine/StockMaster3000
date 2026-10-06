"""Schlüsselprüfung: nachsichtig bei Formfehlern, hart bei falscher Länge; Start- und Gesundheitsprüfung."""

import base64
import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from stockmaster import __main__ as kommando
from stockmaster import config, main
from stockmaster.config import SchluesselFehler, schluessel_dekodieren

# 32 Byte, deren Base64-Form '+' und '/' enthält (sonst prüft die URL-sichere Schreibweise nichts).
ROH = bytes([251, 255, 191, 254, 250, 253] * 5 + [251, 255])
GUELTIG = base64.b64encode(ROH).decode()


@pytest.fixture(autouse=True)
def frisch():
    schluessel_dekodieren.cache_clear()
    config.einstellungen.cache_clear()
    yield
    schluessel_dekodieren.cache_clear()
    config.einstellungen.cache_clear()


def test_testschluessel_ist_aussagekraeftig():
    assert "+" in GUELTIG and "/" in GUELTIG and GUELTIG.endswith("=") and len(GUELTIG) == 44


def test_gueltiger_schluessel():
    assert schluessel_dekodieren(GUELTIG) == ROH


@pytest.mark.parametrize("wert", [
    GUELTIG.rstrip("="),                                   # '=' beim Kopieren verloren (der Fall aus der Praxis)
    f'"{GUELTIG}"',                                        # Anführungszeichen
    f"'{GUELTIG.rstrip('=')}'",                            # Anführungszeichen und fehlendes '='
    f"  {GUELTIG}\n",                                      # Leerraum und Zeilenumbruch
    GUELTIG[:20] + "\n" + GUELTIG[20:],                    # Umbruch mitten im Wert
    GUELTIG.replace("+", "-").replace("/", "_"),           # URL-sichere Schreibweise
    GUELTIG.replace("+", "-").replace("/", "_").rstrip("="),
], ids=["ohne-padding", "doppelte-anfuehrung", "einfache-anfuehrung-ohne-padding", "leerraum", "umbruch",
        "urlsicher", "urlsicher-ohne-padding"])
def test_formfehler_werden_korrigiert(wert):
    assert schluessel_dekodieren(wert) == ROH


def test_bisherige_schluessel_liefern_dieselben_bytes():
    """Gespeicherte Zwei-Faktor-Geheimnisse hängen an den Schlüssel-Bytes: das alte Verfahren hat Vorrang."""
    mit_muell = GUELTIG[:10] + "!!\n" + GUELTIG[10:]   # das alte, nicht strenge Dekodieren überspringt das
    assert schluessel_dekodieren(mit_muell) == base64.b64decode(mit_muell) == ROH


def test_korrektur_wird_gewarnt_gueltiger_wert_nicht(caplog):
    with caplog.at_level(logging.WARNING, logger="stockmaster"):
        schluessel_dekodieren(GUELTIG)
        assert "korrigiert" not in caplog.text
        schluessel_dekodieren(GUELTIG.rstrip("="))
    assert "korrigiert" in caplog.text
    assert GUELTIG.rstrip("=") not in caplog.text


@pytest.mark.parametrize("wert, teil", [
    (base64.b64encode(b"k" * 24).decode(), "24 statt 32 Byte"),     # openssl rand -base64 24
    (base64.b64encode(b"k" * 33).decode(), "33 statt 32 Byte"),
    ("Geheimer-Wert!?ohne-Base64", "kein gültiges Base64"),
    ("ä§$%&", "kein gültiges Base64"),
    ("QUJDRA=x1", "kein gültiges Base64"),                     # unzulässige Länge und Zeichen
])
def test_ungueltige_schluessel_werden_abgelehnt_ohne_den_wert_zu_nennen(wert, teil):
    with pytest.raises(SchluesselFehler) as fehler:
        schluessel_dekodieren(wert)
    meldung = str(fehler.value)
    assert teil in meldung
    assert "openssl rand -base64 32" in meldung
    assert wert not in meldung


def test_fehlender_schluessel(monkeypatch):
    monkeypatch.delenv("SM_SCHLUESSEL", raising=False)
    monkeypatch.delenv("SM_SCHLUESSEL_DATEI", raising=False)
    monkeypatch.delenv("SM_ENTWICKLUNG", raising=False)
    with pytest.raises(SchluesselFehler, match="fehlt"):
        config.einstellungen().schluessel_bytes()
    monkeypatch.setenv("SM_ENTWICKLUNG", "1")
    config.einstellungen.cache_clear()
    assert config.einstellungen().schluessel_bytes() == b"\x00" * 32


def test_schluessel_aus_datei(monkeypatch, tmp_path):
    datei = tmp_path / "sm_schluessel"
    datei.write_text(GUELTIG.rstrip("=") + "\n")
    monkeypatch.setenv("SM_SCHLUESSEL_DATEI", str(datei))
    monkeypatch.delenv("SM_SCHLUESSEL", raising=False)
    config.einstellungen.cache_clear()
    assert config.einstellungen().schluessel_bytes() == ROH


# --------------------------------------------------------------------------
# Start: kaputte Konfiguration verhindert ihn mit klarer Meldung


def _kaputt(monkeypatch):
    monkeypatch.setenv("SM_SCHLUESSEL", "Incorrect-padding!")
    # Eine unerreichbare Datenbank: die Prüfung muss vor dem Warten auf sie greifen.
    monkeypatch.setenv("SM_DATENBANK_URL", "postgresql+psycopg://x:y@127.0.0.1:1/x")
    config.einstellungen.cache_clear()


def test_migrieren_bricht_bei_ungueltigem_schluessel_sofort_ab(app, monkeypatch):
    _kaputt(monkeypatch)
    with pytest.raises(SystemExit) as ende:
        kommando.main(["migrieren"])
    assert str(ende.value).startswith("Konfigurationsfehler: SM_SCHLUESSEL")


def test_admin_anlegen_bricht_bei_ungueltigem_schluessel_ab(app, monkeypatch):
    _kaputt(monkeypatch)
    with pytest.raises(SystemExit) as ende:
        kommando.main(["admin-anlegen", "--email", "a@b.local"])
    assert "Konfigurationsfehler" in str(ende.value)


def test_anwendung_startet_nicht_mit_ungueltigem_schluessel(app, monkeypatch):
    monkeypatch.setenv("SM_SCHLUESSEL", "kaputt")
    config.einstellungen.cache_clear()
    with pytest.raises(SchluesselFehler):
        with TestClient(main.app_erstellen()):
            pass


def test_anwendung_startet_mit_gueltigem_schluessel(app):
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200


# --------------------------------------------------------------------------
# Gesundheitsprüfung


def test_health_gesund(app):
    antwort = TestClient(app).get("/api/health")
    assert (antwort.status_code, antwort.json()) == (200, {"ok": True})


def test_health_ungesund_bei_ungueltigem_schluessel_ohne_details(app, monkeypatch):
    client = TestClient(app)
    monkeypatch.setenv("SM_SCHLUESSEL", "kaputt")
    config.einstellungen.cache_clear()
    antwort = client.get("/api/health")
    assert (antwort.status_code, antwort.json()) == (503, {"ok": False})
    assert "Schlüssel" not in antwort.text and "kaputt" not in antwort.text


def test_health_ungesund_wenn_datenbank_fehlt(app, monkeypatch):
    def keine_verbindung():
        raise OperationalError("select 1", {}, Exception("Verbindung abgelehnt"))

    monkeypatch.setattr(main, "engine", keine_verbindung)
    antwort = TestClient(app).get("/api/health")
    assert (antwort.status_code, antwort.json()) == (503, {"ok": False})
