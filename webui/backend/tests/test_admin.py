"""Administration und Isolationsmatrix."""

import pytest
from conftest import ADMIN_PW, anmelden

ADMIN_ROUTEN = [("GET", "/api/admin/benutzer"), ("POST", "/api/admin/benutzer"), ("GET", "/api/admin/audit"),
                ("GET", "/api/admin/system"), ("POST", "/api/admin/benutzer/x/passwort-zuruecksetzen"),
                ("POST", "/api/admin/benutzer/x/zwei-faktor-zuruecksetzen"), ("POST", "/api/admin/benutzer/x/aktiv"),
                ("POST", "/api/admin/benutzer/x/admin")]


@pytest.mark.parametrize("methode,pfad", ADMIN_ROUTEN)
def test_admin_routen_fuer_nutzer_404(nutzer, methode, pfad):
    assert nutzer.request(methode, pfad, json={}).status_code == 404


def test_alle_routen_ohne_anmeldung_401(client, app):
    oeffentlich = {"/api/health", "/api/auth/login"}
    for route in app.routes:
        pfad = getattr(route, "path", "")
        if not pfad.startswith("/api") or pfad in oeffentlich:
            continue
        for methode in route.methods - {"HEAD", "OPTIONS"}:
            konkret = pfad.replace("{profil}", "defensiv").replace("{eintrag_id}", "J-20260701-01") \
                .replace("{ticker}", "SAP.DE").replace("{hash_wert}", "abcdef1").replace("{user_id}", "x")
            antwort = client.request(methode, konkret, json={})
            assert antwort.status_code == 401, (methode, konkret, antwort.status_code)


def test_benutzer_anlegen_und_erste_anmeldung(admin, app):
    from fastapi.testclient import TestClient

    antwort = admin.post("/api/admin/benutzer", json={"email": "Neu@Example.org", "anzeigename": "Neu",
                                                       "passwort": ADMIN_PW})
    assert antwort.status_code == 201
    daten = antwort.json()
    assert daten["benutzer"]["email"] == "neu@example.org"
    assert daten["benutzer"]["kennung"].startswith("a-")
    with TestClient(app) as neu:
        assert anmelden(neu, "neu@example.org", daten["einmalpasswort"]) == "passwort_aendern"
    doppelt = admin.post("/api/admin/benutzer", json={"email": "neu@example.org", "anzeigename": "X",
                                                       "passwort": ADMIN_PW})
    assert doppelt.status_code == 409


def test_heimnetz_adressen_und_ungueltige_adressen(admin):
    antwort = admin.post("/api/admin/benutzer", json={"email": "kim@heimnetz.local", "anzeigename": "Kim",
                                                       "passwort": ADMIN_PW})
    assert antwort.status_code == 201
    for falsch in ("ohne-at", "a@b@c", "leer @x.de"):
        antwort = admin.post("/api/admin/benutzer", json={"email": falsch, "anzeigename": "X", "passwort": ADMIN_PW})
        assert antwort.status_code == 422, falsch


def test_kritische_aktionen_brauchen_passwort(admin):
    antwort = admin.post("/api/admin/benutzer", json={"email": "z@example.org", "anzeigename": "Z",
                                                       "passwort": "falsch"})
    assert antwort.status_code == 403


def test_sperren_und_zuruecksetzen(admin, app):
    from fastapi.testclient import TestClient

    neu = admin.post("/api/admin/benutzer", json={"email": "s@example.org", "anzeigename": "S",
                                                   "passwort": ADMIN_PW}).json()
    uid = neu["benutzer"]["id"]
    assert admin.post(f"/api/admin/benutzer/{uid}/aktiv", json={"passwort": ADMIN_PW, "aktiv": False}).json()["aktiv"] is False
    with TestClient(app) as gesperrt:
        assert gesperrt.post("/api/auth/login", json={"email": "s@example.org",
                                                       "passwort": neu["einmalpasswort"]}).status_code == 401
    admin.post(f"/api/admin/benutzer/{uid}/aktiv", json={"passwort": ADMIN_PW, "aktiv": True})
    reset = admin.post(f"/api/admin/benutzer/{uid}/passwort-zuruecksetzen", json={"passwort": ADMIN_PW}).json()
    assert reset["einmalpasswort"] != neu["einmalpasswort"]
    assert reset["benutzer"]["passwortwechsel_noetig"] is True


def test_letzter_admin_behaelt_rolle(admin):
    ich = admin.get("/api/auth/me").json()["benutzer"]["id"]
    antwort = admin.post(f"/api/admin/benutzer/{ich}/admin", json={"passwort": ADMIN_PW, "ist_admin": False})
    assert antwort.status_code == 400
    assert admin.post(f"/api/admin/benutzer/{ich}/aktiv", json={"passwort": ADMIN_PW, "aktiv": False}).status_code == 400


def test_audit_log(admin):
    eintraege = admin.get("/api/admin/audit").json()
    assert any(e["aktion"] == "login" for e in eintraege)


def test_admin_erstanlage_nur_einmal(app, capsys):
    from stockmaster.__main__ import main

    assert main(["admin-anlegen", "--email", "erster@example.org"]) == 0
    assert "Einmalpasswort" in capsys.readouterr().out
    assert main(["admin-anlegen", "--email", "zweiter@example.org"]) == 1


def test_migration_erzeugt_schema(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, inspect

    from stockmaster import config, db
    from stockmaster.__main__ import migrieren

    monkeypatch.setenv("SM_DATENBANK_URL", f"sqlite:///{tmp_path / 'm.db'}")
    config.einstellungen.cache_clear()
    db.zuruecksetzen()
    migrieren()
    tabellen = set(inspect(create_engine(f"sqlite:///{tmp_path / 'm.db'}")).get_table_names())
    assert {"users", "auth_sessions", "audit_log", "alembic_version"} <= tabellen


def test_warten_auf_datenbank_wiederholt_und_meldet_falsches_passwort(monkeypatch):
    import pytest
    from sqlalchemy.exc import OperationalError

    from stockmaster import __main__ as cli

    class Fehler(Exception):
        pass

    aufrufe = {"n": 0}

    class Verbindung:
        def __enter__(self):
            aufrufe["n"] += 1
            if aufrufe["n"] < 3:
                raise OperationalError("select 1", {}, Fehler("connection refused"))
            return self

        def __exit__(self, *a):
            return False

        def execute(self, *a):
            return None

    class Maschine:
        def connect(self):
            return Verbindung()

    import stockmaster.db as db
    monkeypatch.setattr(db, "engine", lambda: Maschine())
    monkeypatch.setattr("time.sleep", lambda s: None)
    cli.auf_datenbank_warten(versuche=5)
    assert aufrufe["n"] == 3

    class Falsch:
        def connect(self):
            raise OperationalError("select 1", {}, Fehler("password authentication failed for user x"))

    monkeypatch.setattr(db, "engine", lambda: Falsch())
    with pytest.raises(SystemExit, match="Passwort passt nicht zur Datenbank"):
        cli.auf_datenbank_warten(versuche=20)

    monkeypatch.setattr(db, "engine", lambda: Maschine())
    aufrufe["n"] = -100
    with pytest.raises(SystemExit, match="nicht erreichbar"):
        cli.auf_datenbank_warten(versuche=2)
