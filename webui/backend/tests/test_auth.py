"""Anmeldung, Sitzungen, CSRF, Zwei-Faktor, Sperre, Passwortwechsel."""

from datetime import timedelta

import pyotp
from conftest import ADMIN_PW, NUTZER_PW, anmelden, benutzer_anlegen


def test_falsches_passwort_und_unbekannte_email(client):
    benutzer_anlegen("a@example.org", NUTZER_PW)
    for email, pw in (("a@example.org", "falsch-falsch-falsch"), ("gibtsnicht@example.org", NUTZER_PW)):
        antwort = client.post("/api/auth/login", json={"email": email, "passwort": pw})
        assert antwort.status_code == 401
        assert antwort.json()["detail"].startswith("E-Mail oder Passwort falsch")


def test_sperre_nach_fehlversuchen(client):
    from stockmaster.sicherheit import begrenzer

    benutzer_anlegen("a@example.org", NUTZER_PW)
    for _ in range(5):
        client.post("/api/auth/login", json={"email": "a@example.org", "passwort": "falsch-falsch-falsch"})
    begrenzer.leeren()  # Rate-Limit beiseite: die Kontosperre greift trotzdem
    antwort = client.post("/api/auth/login", json={"email": "a@example.org", "passwort": NUTZER_PW})
    assert antwort.status_code == 401


def test_rate_limit_login(client):
    for _ in range(5):
        client.post("/api/auth/login", json={"email": "x@example.org", "passwort": "egal-egal-egal"})
    antwort = client.post("/api/auth/login", json={"email": "x@example.org", "passwort": "egal-egal-egal"})
    assert antwort.status_code == 429 and int(antwort.headers["Retry-After"]) >= 1


def test_passwortwechsel_pflicht(client):
    benutzer_anlegen("neu@example.org", NUTZER_PW, wechsel=True)
    assert anmelden(client, "neu@example.org", NUTZER_PW) == "passwort_aendern"
    assert client.get("/api/spiel/ueberblick").status_code == 403
    antwort = client.post("/api/auth/passwort", json={"alt": NUTZER_PW, "neu": "kurz"})
    assert antwort.status_code == 400
    antwort = client.post("/api/auth/passwort", json={"alt": NUTZER_PW, "neu": "Ein-ganz-neues-Passwort-7"})
    assert antwort.status_code == 200 and antwort.json()["naechster_schritt"] == "fertig"
    client.headers["X-CSRF-Token"] = antwort.json()["csrf"]
    assert client.get("/api/spiel/ueberblick").status_code == 200


def test_anmeldung_nur_mit_passwort_auch_mit_vorhandenem_zwei_faktor(client):
    geheimnis = pyotp.random_base32()
    benutzer_anlegen("t@example.org", NUTZER_PW, totp=geheimnis)
    antwort = client.post("/api/auth/login", json={"email": "t@example.org", "passwort": NUTZER_PW})
    assert antwort.status_code == 200 and antwort.json()["naechster_schritt"] == "fertig"
    csrf = antwort.json()["csrf"]
    assert client.get("/api/spiel/ueberblick").status_code == 200
    # Der Schritt „Code bei der Anmeldung“ ist abgeschafft; der Code bleibt gespeichert und gültig.
    assert client.post("/api/auth/totp", json={"code": pyotp.TOTP(geheimnis).now()},
                       headers={"X-CSRF-Token": csrf}).status_code in (404, 405)
    assert client.get("/api/auth/me").json()["benutzer"]["totp_aktiv"] is True


def test_admin_ohne_zwei_faktor_kommt_hinein_und_richtet_es_im_konto_ein(client):
    benutzer_anlegen("admin@example.org", ADMIN_PW, admin=True)
    assert anmelden(client, "admin@example.org", ADMIN_PW) == "fertig"  # keine Pflicht zur Einrichtung mehr
    assert client.get("/api/admin/benutzer").status_code == 200
    assert client.get("/api/einrichtung").status_code == 200
    einrichtung = client.post("/api/auth/totp/einrichten").json()
    assert einrichtung["uri"].startswith("otpauth://totp/StockMaster%203000")
    assert client.post("/api/auth/totp/aktivieren", json={"code": "000000"}).status_code == 400
    antwort = client.post("/api/auth/totp/aktivieren", json={"code": pyotp.TOTP(einrichtung["geheimnis"]).now()})
    assert antwort.status_code == 200 and antwort.json()["benutzer"]["totp_aktiv"] is True
    # Auch ein Administrator darf Zwei-Faktor wieder abschalten (mit Passwort und Code).
    assert client.post("/api/auth/totp/deaktivieren", json={"passwort": ADMIN_PW,
                                                            "code": pyotp.TOTP(einrichtung["geheimnis"]).now()}
                       ).status_code == 200


def test_csrf_und_herkunft(nutzer):
    csrf = nutzer.headers.pop("X-CSRF-Token")
    assert nutzer.post("/api/auth/logout").status_code == 403
    assert nutzer.post("/api/auth/logout", headers={"X-CSRF-Token": "falsch"}).status_code == 403
    assert nutzer.post("/api/auth/logout", headers={"X-CSRF-Token": csrf, "Origin": "https://boese.example"}
                       ).status_code == 403
    assert nutzer.post("/api/auth/logout", headers={"X-CSRF-Token": csrf, "Origin": "http://testserver"}
                       ).status_code == 200
    assert nutzer.get("/api/spiel/ueberblick").status_code == 401


def test_leerlauf_und_absolute_ablaufzeit(nutzer):
    from stockmaster.db import neue_sitzung
    from stockmaster.modelle import AuthSitzung

    assert nutzer.get("/api/auth/me").status_code == 200
    with neue_sitzung() as db:
        sitz = db.query(AuthSitzung).one()
        sitz.zuletzt_aktiv = sitz.zuletzt_aktiv - timedelta(minutes=31)
        db.commit()
    assert nutzer.get("/api/auth/me").status_code == 401


def test_absolut_abgelaufen(nutzer):
    from stockmaster.db import neue_sitzung
    from stockmaster.modelle import AuthSitzung

    with neue_sitzung() as db:
        sitz = db.query(AuthSitzung).one()
        sitz.laeuft_ab = sitz.erstellt - timedelta(seconds=1)
        db.commit()
    assert nutzer.get("/api/auth/me").status_code == 401


def test_cookie_eigenschaften(client):
    benutzer_anlegen("c@example.org", NUTZER_PW)
    antwort = client.post("/api/auth/login", json={"email": "c@example.org", "passwort": NUTZER_PW})
    cookie = antwort.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/" in cookie


def test_logout_alle_beendet_alle_sitzungen(client, app):
    from fastapi.testclient import TestClient

    benutzer_anlegen("m@example.org", NUTZER_PW)
    anmelden(client, "m@example.org", NUTZER_PW)
    with TestClient(app) as zweiter:
        anmelden(zweiter, "m@example.org", NUTZER_PW)
        assert len(client.get("/api/auth/sitzungen").json()) == 2
        assert client.post("/api/auth/logout-alle").status_code == 200
        assert zweiter.get("/api/auth/me").status_code == 401


def test_zusatzfelder_werden_abgelehnt(client):
    antwort = client.post("/api/auth/login", json={"email": "a@example.org", "passwort": "x", "ist_admin": True})
    assert antwort.status_code == 422
