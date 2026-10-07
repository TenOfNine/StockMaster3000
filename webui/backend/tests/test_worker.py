"""Hintergrunddienst: Abrufe, Zeitplan, Claude-Läufe mit einer Attrappe der CLI (kein Netzwerk)."""

import json
import os
import stat
import textwrap
from datetime import UTC, datetime

import pytest

TOKEN = "sk-ant-oat01-" + "B" * 40 + "1234"

ATTRAPPE = textwrap.dedent('''\
    #!{python}
    import json, os, sys
    args = sys.argv[1:]
    # Der Lauf bekommt eine minimale Umgebung: Protokoll und Modus liegen deshalb in Dateien.
    with open("{protokoll}", "a") as f:
        f.write(json.dumps({{"args": args, "env": sorted(os.environ)}}) + "\\n")
    modus = open("{modus}").read().strip() if os.path.exists("{modus}") else "ok"
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
    if args[:1] == ["setup-token"]:
        import time
        ziel = "https://evil.example/oauth/authorize?x=1" if modus == "boeser_link" else (
            "https://claude.com/cai/oauth/authorize?code=true&client_id=x&state=abc")
        sys.stdout.write("Welcome to Claude Code\\r\\n\\x1b]8;id=1;" + ziel + "\\x07" + ziel[:40] + "\\x1b]8;;\\x07\\r\\n")
        sys.stdout.write("\\x1b[?2004hPaste\\x1b[1Ccode\\x1b[1Chere\\x1b[1Cif\\x1b[1Cprompted>\\x1b[1C")
        sys.stdout.flush()
        eingabe = sys.stdin.readline().strip()
        if eingabe == "gut-code-12345#abc":
            print("\\r\\nYour OAuth token (valid for 1 year):\\r\\n\\r\\nsk-ant-oat01-" + "T" * 60 + "\\r\\n", flush=True)
            sys.exit(0)
        print("\\r\\nOAuth error: Request failed with status code 400\\r\\nPress Enter to retry.", flush=True)
        time.sleep(30)
        sys.exit(1)
    if "--output-format" in args and args[args.index("--output-format") + 1] == "json":
        if modus == "auth":
            print(json.dumps({{"type": "result", "is_error": True, "result": "Invalid API key · Please run /login"}}))
            sys.exit(1)
        print(json.dumps({{"type": "result", "is_error": False, "result": "OK"}}))
        sys.exit(0)
    def e(d): print(json.dumps(d), flush=True)
    e({{"type": "system", "subtype": "init", "model": args[args.index("--model") + 1]}})
    e({{"type": "assistant", "message": {{"content": [{{"type": "text", "text": "Ich lese CLAUDE.md. Token " + token}}]}}}})
    e({{"type": "assistant", "message": {{"content": [{{"type": "tool_use", "name": "Bash",
       "input": {{"command": "python tools/session.py status"}}}}]}}}})
    if modus == "limit":
        e({{"type": "result", "subtype": "error_during_execution", "is_error": True,
           "result": "Claude AI usage limit reached|1760000000"}})
        sys.exit(1)
    e({{"type": "result", "subtype": "success", "is_error": False, "num_turns": 3, "duration_ms": 1200,
       "result": "Session beendet: keine Orders, Begründung im Session-Eintrag."}})
''')


@pytest.fixture
def claude(tmp_path, monkeypatch):
    ordner = tmp_path / "bin"
    ordner.mkdir()
    datei = ordner / "claude"
    import sys

    protokoll = tmp_path / "claude-aufrufe.jsonl"
    modus = tmp_path / "claude-modus"
    datei.write_text(ATTRAPPE.format(python=sys.executable, protokoll=protokoll, modus=modus))
    datei.chmod(datei.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{ordner}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "darf-nie-weitergegeben-werden")

    def aufrufe():
        return [json.loads(z) for z in protokoll.read_text().splitlines()] if protokoll.exists() else []

    aufrufe.modus = modus.write_text
    return aufrufe


@pytest.fixture
def werkzeug_attrappe(monkeypatch):
    from stockmaster import worker

    aufrufe = []

    class Ergebnis:
        def __init__(self, stdout="ok", returncode=0):
            self.stdout, self.stderr, self.returncode = stdout, "", returncode

    def falsch(name, *argumente, zusatz=None, timeout=600):
        aufrufe.append((name, *argumente))
        if name == "kurse" and argumente[0] == "test":
            return Ergebnis(json.dumps({"ok": True, "meldung": "AAPL: 230 (vor 1 Min.)"}))
        if name == "news" and argumente[0] == "test":
            return Ergebnis("Feed gültig: 2 Meldungen.\n- Eins\n- Zwei")
        if name == "pruefe":
            return Ergebnis("Prüfung bestanden (3 Portfolios, 0 Warnungen).")
        return Ergebnis("Marktübersicht: 8 von 8 Kursen aktuell")

    monkeypatch.setattr(worker, "werkzeug", falsch)
    return aufrufe


def _admin_token(admin):
    assert admin.put("/api/einrichtung/geheimnis/claude_token", json={"wert": TOKEN}).status_code == 200


def test_abrufe_nach_intervall(app, werkzeug_attrappe):
    from stockmaster.worker import Worker

    w = Worker()
    jetzt = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)  # 11:00 Berlin, Xetra offen
    meldungen = w.planen(jetzt)
    assert ("kurse", "markt", "--historie") in werkzeug_attrappe and any(a[0] == "news" for a in werkzeug_attrappe)
    assert len(meldungen) == 2
    werkzeug_attrappe.clear()
    assert w.planen(datetime(2026, 10, 12, 9, 3, tzinfo=UTC)) == []          # innerhalb von 5 Minuten nichts
    w.planen(datetime(2026, 10, 12, 9, 5, tzinfo=UTC))
    assert werkzeug_attrappe == [("kurse", "markt")]                           # nur Kurse (News: 15 Minuten)
    werkzeug_attrappe.clear()
    w.planen(datetime(2026, 10, 12, 21, 0, tzinfo=UTC))                        # 23:00 Berlin: nach Schluss
    assert ("kurse", "markt", "--historie") in werkzeug_attrappe              # einmal nach Börsenschluss mit Historie
    werkzeug_attrappe.clear()
    w.planen(datetime(2026, 10, 12, 21, 20, tzinfo=UTC))                       # geschlossen: stündlich
    assert not any(a[0] == "kurse" for a in werkzeug_attrappe)


def test_commit_stuendlich_nicht_waehrend_session(app, werkzeug_attrappe, monkeypatch):
    from stockmaster import auftraege
    from stockmaster.worker import Worker

    w = Worker()
    jetzt = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
    monkeypatch.setattr(auftraege, "session_sperre_aktiv", lambda: {"person": "auftraggeber-a", "start": "x"})
    assert w.committen(jetzt) is None
    monkeypatch.setattr(auftraege, "session_sperre_aktiv", lambda: None)
    w.committen(jetzt)
    assert ("datenverzeichnis", "commit", "-m", "daten: Kurs- und News-Abruf") in werkzeug_attrappe
    werkzeug_attrappe.clear()
    assert w.committen(datetime(2026, 10, 12, 9, 30, tzinfo=UTC)) is None and werkzeug_attrappe == []


def test_verbindungstests_ueber_auftraege(admin, werkzeug_attrappe, claude):
    from stockmaster.worker import Worker

    _admin_token(admin)
    admin.post("/api/einrichtung/news/test", json={"url": "https://example.org/feed.xml"})
    admin.put("/api/einrichtung/geheimnis/kurs_key_finnhub", json={"wert": "finnhub-key-12345"})
    admin.post("/api/einrichtung/kursdaten/test", json={"anbieter": "finnhub"})
    admin.post("/api/einrichtung/claude/test")
    Worker().auftraege_bearbeiten()
    daten = admin.get("/api/einrichtung").json()
    assert daten["einstellungen"]["kursdaten"]["letzter_test"]["ok"] is True
    test = daten["einstellungen"]["claude"]["letzter_test"]
    assert test["ok"] is True and "Verbindung in Ordnung" in test["meldung"]
    status = {s["id"]: s for s in daten["systemstatus"]}
    assert status["claude"]["stufe"] == "gruen"
    aufruf = claude()[-1]
    assert "--max-turns" in aufruf["args"] and "ANTHROPIC_API_KEY" not in aufruf["env"]
    assert "CLAUDE_CODE_OAUTH_TOKEN" in aufruf["env"]


def test_claude_test_meldet_ungueltiges_token(admin, werkzeug_attrappe, claude, monkeypatch):
    from stockmaster.worker import Worker

    _admin_token(admin)
    claude.modus("auth")
    admin.post("/api/einrichtung/claude/test")
    Worker().auftraege_bearbeiten()
    test = admin.get("/api/einrichtung").json()["einstellungen"]["claude"]["letzter_test"]
    assert test["ok"] is False and "claude setup-token" in test["meldung"]


def _lauf_starten(admin, **zusatz):
    antwort = admin.post("/api/laeufe", json={"art": "trading", "auftraggeber": "auftraggeber-a", "bestaetigt": True,
                                              **zusatz})
    assert antwort.status_code == 201, antwort.text
    return antwort.json()


def test_lauf_mit_live_log_und_geschwaerztem_token(admin, werkzeug_attrappe, claude):
    from stockmaster.worker import Worker

    _admin_token(admin)
    lauf = _lauf_starten(admin, modell="sonnet", aufwand="low")
    assert lauf["modell"] == "sonnet" and lauf["aufwand"] == "low" and lauf["status"] == "wartet"
    assert admin.post("/api/laeufe", json={"art": "trading", "auftraggeber": "auftraggeber-a",
                                            "bestaetigt": True}).status_code == 409   # nur ein Lauf gleichzeitig
    w = Worker()
    w.auftraege_bearbeiten()
    w.lauf_thread.join(timeout=30)
    fertig = admin.get(f"/api/laeufe/{lauf['id']}").json()
    assert fertig["status"] == "ok" and fertig["pruefung_ok"] is True
    assert "keine Orders" in fertig["meldung"]
    log = admin.get(f"/api/laeufe/{lauf['id']}/log").json()
    assert log["fertig"] and "Modell sonnet, Aufwand low" in log["text"] and "→ Bash: python tools/session.py" in log["text"]
    assert TOKEN not in log["text"] and "[geheim]" in log["text"]
    teil = admin.get(f"/api/laeufe/{lauf['id']}/log", params={"ab": log["naechstes"]}).json()
    assert teil["text"] == ""
    aufruf = claude()[-1]["args"]
    assert aufruf[aufruf.index("--model") + 1] == "sonnet" and aufruf[aufruf.index("--effort") + 1] == "low"
    assert "--add-dir" in aufruf and "bypassPermissions" not in aufruf
    einstellungen = json.loads(aufruf[aufruf.index("--settings") + 1])
    assert any(r.startswith("Read(/") and "app" in r for r in einstellungen["permissions"]["deny"])
    assert "ANTHROPIC_API_KEY" not in claude()[-1]["env"]
    audit = [z for z in admin.get("/api/admin/audit").json() if z["aktion"] == "lauf_gestartet"]
    assert audit and audit[0]["ziel"] == lauf["id"]
    from stockmaster.db import neue_sitzung
    from stockmaster.modelle import AuditEintrag

    with neue_sitzung() as db:
        meta = json.loads(db.query(AuditEintrag).filter_by(aktion="lauf_gestartet").one().meta)
    assert meta == {"art": "trading", "modell": "sonnet", "aufwand": "low", "auftraggeber": "auftraggeber-a"}
    assert ("pruefe",) in werkzeug_attrappe


def test_lauf_kontingent_erschoepft(admin, werkzeug_attrappe, claude, monkeypatch):
    from stockmaster.worker import Worker

    _admin_token(admin)
    claude.modus("limit")
    lauf = _lauf_starten(admin)
    w = Worker()
    w.auftraege_bearbeiten()
    w.lauf_thread.join(timeout=30)
    fertig = admin.get(f"/api/laeufe/{lauf['id']}").json()
    assert fertig["status"] == "limit" and "Kontingent" in fertig["meldung"]


def test_lauf_ungueltige_kombination_und_ohne_token(admin):
    assert admin.post("/api/laeufe", json={"art": "trading", "auftraggeber": "auftraggeber-a",
                                            "bestaetigt": True}).status_code == 409   # kein Token
    _admin_token(admin)
    antwort = admin.post("/api/laeufe", json={"art": "trading", "auftraggeber": "auftraggeber-a", "bestaetigt": True,
                                               "modell": "haiku", "aufwand": "max"})
    assert antwort.status_code == 422 and "unterstützt" in antwort.json()["detail"]
    assert admin.post("/api/laeufe", json={"art": "trading", "auftraggeber": "x", "bestaetigt": True}).status_code == 422
    assert admin.post("/api/laeufe", json={"art": "trading", "auftraggeber": "auftraggeber-a",
                                            "bestaetigt": False}).status_code == 422


def test_lauf_abbrechen_vor_start(admin):
    _admin_token(admin)
    lauf = _lauf_starten(admin)
    abgebrochen = admin.post(f"/api/laeufe/{lauf['id']}/abbrechen").json()
    assert abgebrochen["status"] == "abgebrochen"


def test_zeitplan_legt_lauf_an(admin, werkzeug_attrappe):
    from stockmaster.worker import Worker

    _admin_token(admin)
    plan = {"automatik": True, "zeitzone": "Europe/Berlin", "auftraggeber": "auftraggeber-b",
            "termine": [{"wochentage": [0, 1, 2, 3, 4], "uhrzeit": "09:35", "art": "trading"}]}
    assert admin.put("/api/einrichtung/zeitplan", json=plan).status_code == 200
    w = Worker()
    assert w.zeitplan(datetime(2026, 10, 12, 7, 0, tzinfo=UTC)) is None          # 09:00 Berlin: noch nicht
    meldung = w.zeitplan(datetime(2026, 10, 12, 7, 40, tzinfo=UTC))             # 09:40 Berlin, Montag
    assert "angelegt" in meldung
    assert w.zeitplan(datetime(2026, 10, 12, 7, 45, tzinfo=UTC)) is None         # nur einmal je Termin
    laeufe = admin.get("/api/laeufe").json()
    assert laeufe[0]["ausloeser"] == "zeitplan" and laeufe[0]["auftraggeber"] == "auftraggeber-b"
    assert w.zeitplan(datetime(2026, 10, 17, 7, 40, tzinfo=UTC)) is None         # Samstag: kein Termin


def test_wartung_pausiert_worker(app, werkzeug_attrappe):
    from stockmaster import appdaten
    from stockmaster.worker import Worker

    appdaten.zustand_schreiben("wartung", {"seit": "jetzt"})
    assert Worker().einmal() == ["Wartung"] and werkzeug_attrappe == []
    appdaten.zustand_schreiben("wartung", {})



# --------------------------------------------------------------------------
# Anmeldung mit dem Claude-Abo aus der App (claude setup-token im Worker)


def _anmeldung_bis(admin, anmeldung_id, bedingung, sekunden=15):
    import time

    ende = time.monotonic() + sekunden
    while time.monotonic() < ende:
        stand = admin.get(f"/api/einrichtung/claude/anmeldung/{anmeldung_id}").json()
        if bedingung(stand):
            return stand
        time.sleep(0.2)
    raise AssertionError(stand)


def _anmeldung_starten(admin):
    from stockmaster.worker import Worker

    antwort = admin.post("/api/einrichtung/claude/anmeldung")
    assert antwort.status_code == 200, antwort.text
    w = Worker()
    w.auftraege_bearbeiten()
    stand = _anmeldung_bis(admin, antwort.json()["id"], lambda s: s["phase"] != "starte")
    return w, stand


def test_anmeldung_aus_der_app(admin, werkzeug_attrappe, claude, tmp_path):
    w, stand = _anmeldung_starten(admin)
    assert stand["phase"] == "warte_auf_code" and stand["link"].startswith("https://claude.com/cai/oauth/authorize")
    assert stand["token"]["gesetzt"] is False
    antwort = admin.post(f"/api/einrichtung/claude/anmeldung/{stand['id']}/code", json={"code": "gut-code-12345#abc"})
    assert antwort.status_code == 200, antwort.text
    w.anmeldung_thread.join(timeout=20)
    fertig = admin.get(f"/api/einrichtung/claude/anmeldung/{stand['id']}").json()
    assert fertig["status"] == "ok" and fertig["phase"] == "fertig" and fertig["test_ok"] is True
    assert fertig["token"]["gesetzt"] is True and fertig["token"]["letzte4"] == "TTTT"
    assert fertig["token"]["quelle"] == "anmeldung"
    from stockmaster import appdaten

    assert appdaten.geheimnis("claude_token") == "sk-ant-oat01-" + "T" * 60
    # Das Token taucht in keiner Antwort, keinem Audit-Eintrag und keiner Datei im Klartext auf.
    alles = json.dumps(fertig) + admin.get("/api/einrichtung").text + admin.get("/api/admin/audit").text
    assert "T" * 60 not in alles
    for datei in (tmp_path / "app").rglob("*"):
        if datei.is_file():
            assert b"T" * 60 not in datei.read_bytes(), datei
    assert not list((tmp_path / "app" / "tmp").glob("anmeldung-*"))
    aktionen = [z["aktion"] for z in admin.get("/api/admin/audit").json()]
    assert {"einrichtung_claude_anmeldung_gestartet", "einrichtung_claude_anmeldung_code",
            "claude_anmeldung_abgeschlossen"} <= set(aktionen)
    # Der anschließende Verbindungstest lief mit dem neuen Token.
    assert admin.get("/api/einrichtung").json()["einstellungen"]["claude"]["letzter_test"]["ok"] is True


def test_anmeldung_falscher_code(admin, werkzeug_attrappe, claude):
    w, stand = _anmeldung_starten(admin)
    admin.post(f"/api/einrichtung/claude/anmeldung/{stand['id']}/code", json={"code": "falscher-code-999"})
    w.anmeldung_thread.join(timeout=20)
    fertig = admin.get(f"/api/einrichtung/claude/anmeldung/{stand['id']}").json()
    assert fertig["status"] == "fehler" and "abgelehnt" in fertig["meldung"]
    assert fertig["token"]["gesetzt"] is False
    nochmal = admin.post(f"/api/einrichtung/claude/anmeldung/{stand['id']}/code", json={"code": "gut-code-12345#abc"})
    assert nochmal.status_code == 409


def test_anmeldung_code_format_und_abbruch(admin):
    antwort = admin.post("/api/einrichtung/claude/anmeldung")
    anmeldung_id = antwort.json()["id"]
    assert admin.post(f"/api/einrichtung/claude/anmeldung/{anmeldung_id}/code",
                      json={"code": "mit leerzeichen 123"}).status_code == 422
    assert admin.post(f"/api/einrichtung/claude/anmeldung/{anmeldung_id}/code",
                      json={"code": "noch-kein-link-123"}).status_code == 409
    assert admin.post(f"/api/einrichtung/claude/anmeldung/{anmeldung_id}/abbrechen").json()["status"] == "abgebrochen"


def test_anmeldung_nur_admin(nutzer):
    assert nutzer.post("/api/einrichtung/claude/anmeldung").status_code == 404


def test_anmeldung_fremder_link_wird_abgelehnt(admin, werkzeug_attrappe, claude):
    from stockmaster.worker import Worker

    claude.modus("boeser_link")
    antwort = admin.post("/api/einrichtung/claude/anmeldung")
    w = Worker()
    w.auftraege_bearbeiten()
    w.anmeldung_thread.join(timeout=20)
    stand = admin.get(f"/api/einrichtung/claude/anmeldung/{antwort.json()['id']}").json()
    assert stand["status"] == "fehler" and "nicht von Anthropic" in stand["meldung"] and stand["link"] is None


def test_anmeldung_abbrechen_beendet_prozess(admin, werkzeug_attrappe, claude):
    w, stand = _anmeldung_starten(admin)
    admin.post(f"/api/einrichtung/claude/anmeldung/{stand['id']}/abbrechen")
    w.anmeldung_thread.join(timeout=20)
    assert not w.anmeldung_thread.is_alive()
    assert admin.get(f"/api/einrichtung/claude/anmeldung/{stand['id']}").json()["status"] == "abgebrochen"


def test_link_und_token_erkennung():
    from stockmaster import claude_anmeldung as a

    roh = (b"\x1b]8;id=1;https://claude.com/cai/oauth/authorize?code=true&state=s\x1b\\https://claude.com/cai/oa"
           b"\x1b]8;;\x1b\\")
    assert a.link_finden(roh) == "https://claude.com/cai/oauth/authorize?code=true&state=s"
    assert a.token_finden(b"\x1b[1mYour token:\x1b[22m sk-ant-oat01-abcdefghijklmnopqrstuvwxyz0123\r\n") == \
        "sk-ant-oat01-abcdefghijklmnopqrstuvwxyz0123"
    with pytest.raises(a.AnmeldeFehler):
        a.link_pruefen("https://claude.com.evil.example/oauth")
    with pytest.raises(ValueError):
        a.code_pruefen("a b")


# --------------------------------------------------------------------------
# Trading-Läufe brauchen Startdatum und ausformulierte Anlagerichtlinien


def _spiel(demo_repo, **felder):
    import json as _json

    datei = demo_repo / "spiel.json"
    alt = _json.loads(datei.read_text())
    datei.write_text(_json.dumps({**alt, **felder}))
    return alt


def test_manueller_lauf_ohne_richtlinien_mit_hinweis(admin, demo_repo):
    from stockmaster.spiel import lesen

    _admin_token(admin)
    vorlage = (demo_repo / "strategie" / "defensiv.md")
    inhalt = vorlage.read_text()
    vorlage.write_text("# Anlagerichtlinie Defensiv\n\nStand: Vorlage aus tools/init.py (2026-10-06).\n")
    try:
        lesen.zuruecksetzen()
        hinweise = admin.get("/api/laeufe/vorpruefung", params={"art": "trading"}).json()["hinweise"]
        assert any("Anlagerichtlinien fehlen (defensiv)" in h for h in hinweise)
        assert admin.get("/api/laeufe/vorpruefung", params={"art": "review"}).json()["hinweise"] == []
        schritte = [s["schritt"] for s in admin.get("/api/einrichtung").json()["pflichtschritte"]]
        assert "richtlinien" in schritte
        # Manuell startet jeder Lauf jederzeit; die Richtlinien-Session selbst sowieso.
        ok = admin.post("/api/laeufe", json={"art": "trading", "auftraggeber": "auftraggeber-a", "bestaetigt": True})
        assert ok.status_code == 201, ok.text
        admin.post(f"/api/laeufe/{ok.json()['id']}/abbrechen")
        ok = admin.post("/api/laeufe", json={"art": "richtlinien", "auftraggeber": "auftraggeber-a", "bestaetigt": True})
        assert ok.status_code == 201, ok.text
        status = admin.get("/api/spiel/status").json()
        ap12 = next(p for p in status["arbeitspakete"] if p["kennung"] == "AP12")
        assert ap12["instanz"] and not ap12["erledigt"] and "Anlagerichtlinien offen: defensiv" in ap12["detail"]
    finally:
        vorlage.write_text(inhalt)
        lesen.zuruecksetzen()


def test_manueller_lauf_vor_startdatum_mit_hinweis_geplanter_wird_uebersprungen(admin, demo_repo):
    from stockmaster.spiel import lesen
    from stockmaster.worker import Worker

    _admin_token(admin)
    alt = _spiel(demo_repo, startdatum="2099-01-01")
    try:
        lesen.zuruecksetzen()
        hinweise = admin.get("/api/laeufe/vorpruefung").json()["hinweise"]
        assert any("2099-01-01" in h and "vorziehen" in h for h in hinweise)
        # Manuell: jederzeit (der Lauf selbst bucht vor dem Startdatum nichts, das sperrt buchen.py).
        antwort = admin.post("/api/laeufe", json={"art": "trading", "auftraggeber": "auftraggeber-a", "bestaetigt": True})
        assert antwort.status_code == 201, antwort.text
        admin.post(f"/api/laeufe/{antwort.json()['id']}/abbrechen")
        # Geplant: übersprungen mit Grund, das schont das Abo-Kontingent.
        meldung = Worker().geplanten_lauf_anlegen("trading", "auftraggeber-a")
        assert meldung.startswith("übersprungen:") and "2099-01-01" in meldung
        assert Worker().geplanten_lauf_anlegen("review", "auftraggeber-a").startswith("Lauf ")
    finally:
        (demo_repo / "spiel.json").write_text(__import__("json").dumps(alt))
        lesen.zuruecksetzen()


def test_plan_und_automatik_schalten(admin):
    _admin_token(admin)
    plan = {"automatik": False, "zeitzone": "Europe/Berlin", "auftraggeber": "auftraggeber-a",
            "termine": [{"wochentage": [0, 1, 2, 3, 4], "uhrzeit": "09:35", "art": "trading"},
                        {"wochentage": [4], "uhrzeit": "21:30", "art": "review"}]}
    assert admin.put("/api/einrichtung/zeitplan", json=plan).status_code == 200
    aus = admin.get("/api/laeufe/plan").json()
    assert aus["automatik"] is False and aus["naechste"] == [] and aus["token_gesetzt"] is True
    assert admin.post("/api/einrichtung/zeitplan/automatik", json={"an": True}).json()["automatik"] is True
    an = admin.get("/api/laeufe/plan").json()
    assert an["automatik"] is True and 1 <= len(an["naechste"]) <= 5
    zeiten = [t["zeit"] for t in an["naechste"]]
    assert zeiten == sorted(zeiten) and all(t["art"] in ("trading", "review") for t in an["naechste"])
    assert admin.post("/api/einrichtung/zeitplan/automatik", json={"an": False}).json()["automatik"] is False
    assert admin.get("/api/laeufe/plan").json()["naechste"] == []


def test_automatik_braucht_token_und_termine(admin):
    plan = {"automatik": False, "zeitzone": "Europe/Berlin", "auftraggeber": "auftraggeber-a", "termine": []}
    assert admin.put("/api/einrichtung/zeitplan", json=plan).status_code == 200
    assert admin.post("/api/einrichtung/zeitplan/automatik", json={"an": True}).status_code == 422


def test_naechste_termine_beruecksichtigt_wochentag_und_handelstag(app):
    from stockmaster.auftraege import naechste_termine

    plan = {"zeitzone": "Europe/Berlin",
            "termine": [{"wochentage": [0, 1, 2, 3, 4], "uhrzeit": "09:35", "art": "trading"}]}
    # Freitag 2026-10-09 10:30 Berlin: der Freitagstermin ist vorbei (Fenster 30 Min), nächster ist Montag.
    naechste = naechste_termine(plan, datetime(2026, 10, 9, 8, 30, tzinfo=UTC), 2)
    assert [t["zeit"][:16] for t in naechste] == ["2026-10-12T09:35", "2026-10-13T09:35"]
    # Mitten im Fenster zählt der Termin noch (der Worker legt ihn dann an).
    assert naechste_termine(plan, datetime(2026, 10, 9, 7, 45, tzinfo=UTC), 1)[0]["zeit"][:16] == "2026-10-09T09:35"


def test_ap12_wird_je_instanz_abgeleitet(admin):
    ap12 = next(p for p in admin.get("/api/spiel/status").json()["arbeitspakete"] if p["kennung"] == "AP12")
    assert ap12["instanz"] is True and ap12["erledigt"] is True and "gestartet" in ap12["detail"]


# --------------------------------------------------------------------------
# Ergebnis nicht abschneiden, Berechtigungen für git -C


def test_ergebnis_bleibt_vollstaendig(admin, werkzeug_attrappe, claude):
    from stockmaster.claude_lauf import ereignis_text

    lang = "## Vor dem Spielstart zu klären\n" + "\n".join(f"{n}. Punkt mit Text " * 3 for n in range(1, 400))
    zeilen = ereignis_text({"type": "result", "subtype": "success", "num_turns": 3, "duration_ms": 1200, "result": lang})
    assert len(lang) > 2000 and "\n".join(zeilen).endswith(lang.splitlines()[-1])
    assert zeilen[1] == "## Vor dem Spielstart zu klären"  # Zeilenumbrüche bleiben (Markdown)


def test_erlaubnisliste_fuer_git_mit_c():
    from stockmaster import claude_lauf

    erlaubt = claude_lauf.ERLAUBTE_WERKZEUGE
    assert "Bash(git -C * log*)" in erlaubt and "Bash(git -C * status*)" in erlaubt
    verboten = json.loads(claude_lauf.einstellungen_json())["permissions"]["deny"]
    assert {"Bash(git * push*)", "Bash(git * remote*)", "Bash(git * config*)", "Bash(git * reset*)"} <= set(verboten)
    assert not any("push" in e or "reset" in e or "config" in e for e in erlaubt)
