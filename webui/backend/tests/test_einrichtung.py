"""Einrichtung: Rechte, Secrets (nie im Klartext), Validierung, Migration aus der Umgebung, Spielstart."""

import base64
import json
import os
import stat
import subprocess
import sys

import pytest
from conftest import ADMIN_PW, WURZEL

TOKEN = "sk-ant-oat01-" + "A" * 40 + "wxyz"


def test_nur_admin(nutzer):
    assert nutzer.get("/api/einrichtung").status_code == 404
    assert nutzer.put("/api/einrichtung/geheimnis/claude_token", json={"wert": TOKEN}).status_code == 404
    assert nutzer.post("/api/laeufe", json={"art": "trading", "auftraggeber": "auftraggeber-a",
                                             "bestaetigt": True}).status_code == 404


def test_ueberblick_ohne_secrets(admin):
    daten = admin.get("/api/einrichtung").json()
    assert set(daten["geheimnisse"]) == {"claude_token", "kurs_key_finnhub", "kurs_key_twelvedata"}
    assert daten["geheimnisse"]["claude_token"]["gesetzt"] is False
    assert {m["wert"] for m in daten["optionen"]["claude"]["modelle"]} >= {"opus", "sonnet", "haiku"}
    assert {a["wert"] for a in daten["optionen"]["claude"]["aufwand"]} >= {"low", "medium", "high"}
    assert {s["id"] for s in daten["systemstatus"]} == {"daten", "git", "kurse", "news", "claude", "worker"}
    schritte = [s["schritt"] for s in daten["pflichtschritte"]]
    assert schritte == ["kursdaten", "claude"]  # Demo-Spiel ist gestartet


def test_token_wird_nie_ausgeliefert(admin, tmp_path):
    antwort = admin.put("/api/einrichtung/geheimnis/claude_token", json={"wert": TOKEN})
    assert antwort.status_code == 200, antwort.text
    assert antwort.json() == {**antwort.json(), "gesetzt": True, "letzte4": "wxyz"}
    gesamt = admin.get("/api/einrichtung").text + admin.get("/api/admin/audit").text
    assert TOKEN not in gesamt and "A" * 40 not in gesamt
    datei = tmp_path / "app" / "geheimnisse.json"
    assert TOKEN not in datei.read_text() and "wxyz" not in datei.read_text()
    assert stat.S_IMODE(os.stat(datei).st_mode) == 0o600
    aktionen = [z["aktion"] for z in admin.get("/api/admin/audit").json()]
    assert "einrichtung_geheimnis_geaendert" in aktionen
    from stockmaster import appdaten

    assert appdaten.geheimnis("claude_token") == TOKEN
    assert admin.delete("/api/einrichtung/geheimnis/claude_token").json()["gesetzt"] is False


def test_token_format_und_csrf(admin):
    assert admin.put("/api/einrichtung/geheimnis/claude_token", json={"wert": "kein-token-123"}).status_code == 422
    assert admin.put("/api/einrichtung/geheimnis/claude_token", json={"wert": "sk-ant-mit leerzeichen"}).status_code == 422
    ohne = admin.put("/api/einrichtung/geheimnis/claude_token", json={"wert": TOKEN},
                     headers={"X-CSRF-Token": "falsch"})
    assert ohne.status_code == 403


def test_claude_voreinstellungen_validiert(admin):
    gut = {"trading": {"modell": "opus", "aufwand": "high"}, "review": {"modell": "claude-sonnet-5-5", "aufwand": ""}}
    assert admin.put("/api/einrichtung/claude", json=gut).status_code == 200
    gespeichert = admin.get("/api/einrichtung").json()["einstellungen"]["claude"]["voreinstellungen"]
    assert gespeichert["review"] == {"modell": "claude-sonnet-5-5", "aufwand": ""}
    for falsch, text in ((("haiku", "max"), "nicht"), (("opus", "ultra"), "Unbekannter Aufwand"),
                         (("Opus; rm -rf", "high"), "Unbekanntes Modell")):
        antwort = admin.put("/api/einrichtung/claude", json={**gut, "trading": {"modell": falsch[0], "aufwand": falsch[1]}})
        assert antwort.status_code == 422 and text in antwort.json()["detail"], antwort.text


def test_kursdaten_braucht_key(admin):
    daten = {"anbieter": "twelvedata", "intervall_offen_minuten": 5, "intervall_geschlossen_minuten": 60}
    assert admin.put("/api/einrichtung/kursdaten", json=daten).status_code == 422
    assert admin.put("/api/einrichtung/geheimnis/kurs_key_twelvedata", json={"wert": "td-key-12345678"}).status_code == 200
    assert admin.put("/api/einrichtung/kursdaten", json=daten).status_code == 200
    assert admin.put("/api/einrichtung/kursdaten", json={**daten, "intervall_offen_minuten": 0}).status_code == 422


def test_news_feeds_validiert_und_wirksam(admin):
    from stockmaster.einrichtung import news_konfig_wirksam

    daten = {"aktiv": True, "intervall_minuten": 15, "deaktiviert": ["sec-8k"], "user_agent": "",
             "eigene": [{"id": "mein-feed", "name": "Mein Feed", "url": "https://example.org/rss", "ticker": ["SAP.DE"]}]}
    assert admin.put("/api/einrichtung/news", json=daten).status_code == 200
    wirksam = {f["id"]: f for f in news_konfig_wirksam()["feeds"]}
    assert wirksam["sec-8k"]["aktiv"] is False and wirksam["mein-feed"]["eigen"] is True
    assert json.loads((WURZEL / "config" / "news.json").read_text())["feeds"][0]["aktiv"] is True  # Datei unverändert
    schlecht = {**daten, "eigene": [{"id": "x1", "name": "X", "url": "javascript:alert(1)"}]}
    assert admin.put("/api/einrichtung/news", json=schlecht).status_code == 422
    assert admin.put("/api/einrichtung/news", json={**daten, "deaktiviert": ["gibts-nicht"]}).status_code == 422
    doppelt = {**daten, "eigene": [{"id": "ezb", "name": "EZB", "url": "https://example.org/x"}]}
    assert admin.put("/api/einrichtung/news", json=doppelt).status_code == 422


def test_zeitplan_validiert(admin):
    plan = {"automatik": True, "zeitzone": "Europe/Berlin", "auftraggeber": "auftraggeber-a",
            "termine": [{"wochentage": [0, 1, 2, 3, 4], "uhrzeit": "09:35", "art": "trading"}]}
    assert admin.put("/api/einrichtung/zeitplan", json=plan).status_code == 422  # ohne Token
    admin.put("/api/einrichtung/geheimnis/claude_token", json={"wert": TOKEN})
    assert admin.put("/api/einrichtung/zeitplan", json=plan).status_code == 200
    assert admin.put("/api/einrichtung/zeitplan", json={**plan, "zeitzone": "Mars/Olymp"}).status_code == 422
    falsch = {**plan, "termine": [{"wochentage": [9], "uhrzeit": "25:00", "art": "trading"}]}
    assert admin.put("/api/einrichtung/zeitplan", json=falsch).status_code == 422
    assert admin.put("/api/einrichtung/zeitplan", json={**plan, "auftraggeber": "jemand"}).status_code == 422


def test_tests_laufen_als_auftrag(admin):
    antwort = admin.post("/api/einrichtung/news/test", json={"url": "https://example.org/feed.xml"})
    assert antwort.status_code == 200 and antwort.json()["status"] == "wartet"
    assert "Hintergrunddienst" in antwort.json()["meldung"]
    assert admin.post("/api/einrichtung/news/test", json={"url": "file:///etc/passwd"}).status_code == 422
    assert admin.post("/api/einrichtung/claude/test").status_code == 409  # ohne Token


def test_cockpit_zeigt_offene_schritte(nutzer):
    daten = nutzer.get("/api/spiel/ueberblick").json()
    assert [s["link"] for s in daten["einrichtung_offen"]] == ["/einrichtung#kursdaten", "/einrichtung#claude"]
    assert daten["letzter_lauf"] is None and isinstance(daten["news"], list)


# --------------------------------------------------------------------------
# Master-Schlüssel und Übernahme aus der Umgebung


@pytest.fixture
def leer(app, monkeypatch):
    for name in ("SM_SCHLUESSEL", "SM_SCHLUESSEL_DATEI", "CLAUDE_CODE_OAUTH_TOKEN", "FINNHUB_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    from stockmaster import config

    config.einstellungen.cache_clear()
    return monkeypatch


def test_master_schluessel_neu_mit_0600(leer, tmp_path):
    from stockmaster import appdaten, config

    meldungen = appdaten.schluessel_einrichten(totp_vorhanden=False)
    datei = tmp_path / "app" / "master.key"
    assert "erzeugt" in meldungen[0] and stat.S_IMODE(os.stat(datei).st_mode) == 0o600
    assert len(config.einstellungen().schluessel_bytes()) == 32
    assert appdaten.schluessel_einrichten(totp_vorhanden=True) == []  # vorhanden: nichts zu tun


def test_master_schluessel_aus_umgebung_gleiche_bytes(leer, tmp_path):
    from stockmaster import appdaten, config

    wert = base64.b64encode(b"q" * 32).decode()
    leer.setenv("SM_SCHLUESSEL", wert)
    config.einstellungen.cache_clear()
    assert "übernommen" in appdaten.schluessel_einrichten(totp_vorhanden=True)[0]
    leer.setenv("SM_SCHLUESSEL", base64.b64encode(b"z" * 32).decode())  # spätere Änderung gilt nicht mehr
    config.einstellungen.cache_clear()
    assert config.einstellungen().schluessel_bytes() == b"q" * 32
    assert "SM_SCHLUESSEL" in appdaten.ueberfluessige_variablen()


def test_kein_neuer_schluessel_wenn_zwei_faktor_existiert(leer):
    from stockmaster import appdaten
    from stockmaster.config import SchluesselFehler

    with pytest.raises(SchluesselFehler, match="SM_SCHLUESSEL einmalig"):
        appdaten.schluessel_einrichten(totp_vorhanden=True)


def test_umgebung_wird_einmalig_uebernommen(leer):
    from stockmaster import appdaten

    leer.setenv("SM_SCHLUESSEL", base64.b64encode(b"k" * 32).decode())
    leer.setenv("CLAUDE_CODE_OAUTH_TOKEN", TOKEN)
    leer.setenv("FINNHUB_API_KEY", "finnhub-key-123456")
    meldungen = appdaten.aus_umgebung_uebernehmen()
    assert len(meldungen) == 2 and all(TOKEN not in m and "finnhub-key" not in m for m in meldungen)
    assert appdaten.geheimnis_info("claude_token")["quelle"] == "umgebung"
    assert appdaten.laden()["kursdaten"]["anbieter"] == "finnhub"
    leer.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-anderes-token-0000")
    assert appdaten.aus_umgebung_uebernehmen() == []
    assert appdaten.geheimnis("claude_token") == TOKEN  # danach gilt die App-Konfiguration
    assert "CLAUDE_CODE_OAUTH_TOKEN" in appdaten.ueberfluessige_variablen()


# --------------------------------------------------------------------------
# Datenverzeichnis beim Start und Git-Hook gegen Secrets


@pytest.fixture
def frisch(app, tmp_path, monkeypatch):
    """Leeres Datenverzeichnis wie bei einem neuen Volume."""
    from stockmaster import config, db
    from stockmaster.spiel import lesen

    daten = tmp_path / "daten-neu"
    daten.mkdir()
    monkeypatch.setenv("STOCKMASTER_DATA_DIR", str(daten))
    config.einstellungen.cache_clear()
    lesen.zuruecksetzen()
    db.Basis.metadata.create_all(db.engine())
    yield daten
    lesen.zuruecksetzen()


def test_einrichten_initialisiert_leeres_volume_und_hook(frisch):
    from stockmaster import __main__ as cli
    from stockmaster import appdaten

    meldungen = cli.einrichten()
    assert any("aus der Vorlage angelegt" in m for m in meldungen)
    assert (frisch / ".git").is_dir() and (frisch / "lessons.md").exists()
    assert subprocess.run(["git", "remote"], cwd=frisch, capture_output=True, text=True).stdout == ""
    appdaten.geheimnis_setzen("claude_token", TOKEN)
    (frisch / "journal" / "2026-10-12_auftraggeber-a.md").write_text(f"Versehen: {TOKEN}\n")
    subprocess.run(["git", "add", "-A"], cwd=frisch, check=True)
    assert cli.geheimnisse_pruefen(frisch) == 1
    (frisch / "journal" / "2026-10-12_auftraggeber-a.md").write_text("# Journal\n")
    subprocess.run(["git", "add", "-A"], cwd=frisch, check=True)
    assert cli.geheimnisse_pruefen(frisch) == 0
    # zweiter Start ist harmlos
    assert any("bereits eingerichtet" in m for m in cli.einrichten())


def test_hook_blockiert_commit(frisch):
    from stockmaster import __main__ as cli
    from stockmaster import appdaten

    cli.einrichten()
    appdaten.geheimnis_setzen("kurs_key_finnhub", "finnhub-geheim-987654")
    (frisch / "lessons.md").write_text("finnhub-geheim-987654\n")
    umgebung = {**os.environ, "PYTHONPATH": str(WURZEL / "webui" / "backend")}
    ergebnis = subprocess.run(["git", "commit", "-qam", "session: Test"], cwd=frisch, capture_output=True, text=True,
                              env=umgebung)
    assert ergebnis.returncode != 0 and "Finnhub-API-Key" in ergebnis.stderr
    assert "finnhub-geheim" not in ergebnis.stderr


def test_spielstart_einmalig(frisch, client):
    import pyotp
    from conftest import anmelden, benutzer_anlegen

    from stockmaster import __main__ as cli

    cli.einrichten()
    cache = frisch / ".cache"
    cache.mkdir()
    (cache / "markt.json").write_text(json.dumps({"zeit": "2026-10-07T09:00:00+02:00", "erfolgreich": 1, "anzahl": 1,
                                                  "eintraege": [{"ticker": "EUNL.DE", "kurs": "100", "veraltet": False}]}))
    geheimnis = pyotp.random_base32()
    benutzer_anlegen("admin2@example.org", ADMIN_PW, admin=True, totp=geheimnis)
    anmelden(client, "admin2@example.org", ADMIN_PW, geheimnis)
    liste = client.get("/api/einrichtung").json()["spielstart"]
    assert liste["bereit"] is True and liste["gestartet"] is False
    daten = {"startdatum": liste["vorschlag_startdatum"], "freigabe_durch": "auftraggeber-b",
             "freigabe_ap12_bestaetigt": True, "passwort": ADMIN_PW}
    assert client.post("/api/einrichtung/spielstart", json={**daten, "passwort": "falsch"}).status_code == 403
    assert client.post("/api/einrichtung/spielstart", json={**daten, "freigabe_ap12_bestaetigt": False}).status_code == 422
    antwort = client.post("/api/einrichtung/spielstart", json=daten)
    assert antwort.status_code == 200, antwort.text
    spiel = json.loads((frisch / "spiel.json").read_text())
    assert spiel["startdatum"] == daten["startdatum"] and spiel["freigabe_ap12"] == "auftraggeber-b"
    log = subprocess.run(["git", "log", "-1", "--format=%s"], cwd=frisch, capture_output=True, text=True).stdout
    assert log.startswith("aufbau: Spielstart")
    assert client.post("/api/einrichtung/spielstart", json=daten).status_code == 409
    pruefung = subprocess.run([sys.executable, str(WURZEL / "tools" / "pruefe.py"), "--historie"], cwd=frisch,
                              capture_output=True, text=True, env={**os.environ, "STOCKMASTER_DATA_DIR": str(frisch)})
    assert pruefung.returncode == 0, pruefung.stdout


def test_startdatum_vorziehen_per_api(frisch, client):
    from datetime import date, timedelta

    import pyotp
    from conftest import anmelden, benutzer_anlegen

    from stockmaster import __main__ as cli
    from stockmaster.einrichtung import naechster_handelstag

    cli.einrichten()
    cache = frisch / ".cache"
    cache.mkdir()
    (cache / "markt.json").write_text(json.dumps({"zeit": "2026-10-07T09:00:00+02:00", "erfolgreich": 1, "anzahl": 1,
                                                  "eintraege": [{"ticker": "EUNL.DE", "kurs": "100", "veraltet": False}]}))
    geheimnis = pyotp.random_base32()
    benutzer_anlegen("admin3@example.org", ADMIN_PW, admin=True, totp=geheimnis)
    anmelden(client, "admin3@example.org", ADMIN_PW, geheimnis)
    liste = client.get("/api/einrichtung").json()["spielstart"]
    heute_ziel = liste["vorschlag_startdatum"]
    assert liste["vorziehen"]["moeglich"] is False  # noch nicht gestartet
    spaeter = naechster_handelstag(date.today() + timedelta(days=7)).isoformat()
    daten = {"startdatum": spaeter, "freigabe_durch": "auftraggeber-a", "freigabe_ap12_bestaetigt": True,
             "passwort": ADMIN_PW}
    assert client.post("/api/einrichtung/spielstart", json=daten).status_code == 200
    vorher = client.get("/api/einrichtung").json()["spielstart"]["vorziehen"]
    assert vorher == {"moeglich": True, "grund": None, "ziel": heute_ziel}
    ziel = {"startdatum": heute_ziel, "passwort": ADMIN_PW}
    assert client.post("/api/einrichtung/spielstart/vorziehen", json={**ziel, "passwort": "falsch"}).status_code == 403
    # Nicht rückwirkend.
    gestern = (date.today() - timedelta(days=1)).isoformat()
    assert client.post("/api/einrichtung/spielstart/vorziehen", json={**ziel, "startdatum": gestern}).status_code == 422
    antwort = client.post("/api/einrichtung/spielstart/vorziehen", json=ziel)
    assert antwort.status_code == 200, antwort.text
    spiel = json.loads((frisch / "spiel.json").read_text())
    assert spiel["startdatum"] == heute_ziel and spiel["startdatum_vorher"][0]["datum"] == spaeter
    log = subprocess.run(["git", "log", "-1", "--format=%s"], cwd=frisch, capture_output=True, text=True).stdout
    assert log.startswith("aufbau: Startdatum auf")
    assert client.get("/api/einrichtung").json()["spielstart"]["vorziehen"]["moeglich"] is False
    assert client.post("/api/einrichtung/spielstart/vorziehen", json=ziel).status_code == 422
