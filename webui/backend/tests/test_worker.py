"""Hintergrunddienst: Abrufe, Zeitplan, Claude-Läufe mit einer Attrappe der CLI (kein Netzwerk)."""

import json
import os
import stat
import subprocess
import textwrap
from datetime import UTC, datetime, timedelta

import pytest

TOKEN = "sk-ant-oat01-" + "B" * 40 + "1234"

ATTRAPPE = textwrap.dedent('''\
    #!{python}
    import json, os, sys
    args = sys.argv[1:]
    # Läufe bekommen den Auftrag als stream-json über stdin (erste Zeile).
    eingabe = sys.stdin.readline() if "--input-format" in args else ""
    # Der Lauf bekommt eine minimale Umgebung: Protokoll und Modus liegen deshalb in Dateien.
    with open("{protokoll}", "a") as f:
        f.write(json.dumps({{"args": args, "env": sorted(os.environ), "stdin": eingabe}}) + "\\n")
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
    if modus.startswith("frage|"):
        # frage|<Befehl>|<Anzahl>: fragt wie die CLI per control_request nach, wartet auf die Antwort über stdin
        teile = (modus.split("|") + ["1"])[:3]
        for n in range(int(teile[2])):
            e({{"type": "control_request", "request_id": "r" + str(n), "request": {{
               "subtype": "can_use_tool", "tool_name": "Bash", "input": {{"command": teile[1]}},
               "description": "Test", "tool_use_id": "t" + str(n)}}}})
            antwort = json.loads(sys.stdin.readline())["response"]
            urteil = antwort["response"]
            erlaubt = urteil["behavior"] == "allow"
            e({{"type": "user", "message": {{"content": [{{"type": "tool_result", "is_error": not erlaubt,
               "content": "ausgefuehrt" if erlaubt else urteil["message"]}}]}}}})
        e({{"type": "result", "subtype": "success", "is_error": False, "num_turns": 2, "duration_ms": 1000,
           "result": "Freigabe: " + urteil["behavior"]}})
        sys.exit(0)
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


def test_news_abruf_meldet_ausgefallene_feeds(admin, werkzeug_attrappe, monkeypatch):
    import json as _json

    from stockmaster import einrichtung
    from stockmaster.db import neue_sitzung
    from stockmaster.modelle import Auftrag
    from stockmaster.worker import Worker

    stand = {"zeit": "2026-10-12T10:00:00+02:00", "neu": 3, "anzahl_feeds": 2, "fehlerhaft": 1,
             "feeds": {"a": {"name": "A", "ok": True, "anzahl": 1}, "b": {"name": "B", "ok": False, "fehler": "HTTP 404"}}}
    original = einrichtung._cache
    monkeypatch.setattr(einrichtung, "_cache", lambda name: stand if name == "news_stand.json" else original(name))
    auftrag_id = admin.post("/api/einrichtung/news/abrufen").json()["id"]
    Worker().auftraege_bearbeiten()
    with neue_sitzung() as db:
        ergebnis = _json.loads(db.get(Auftrag, auftrag_id).ergebnis)
    assert ergebnis["ok"] is True and ergebnis["fehlerhaft"] == 1


def test_news_meldung_im_herzschlag_ohne_doppeltes_praefix(app, werkzeug_attrappe):
    from stockmaster.worker import Worker

    w = Worker()
    w.news_abrufen = lambda: "News: 3 neue Meldungen aus 18 Feeds, 1 mit Fehler – SEC 8-K: HTTP 403."
    meldungen = w.planen(datetime(2026, 10, 12, 9, 0, tzinfo=UTC))
    assert "News: 3 neue Meldungen aus 18 Feeds, 1 mit Fehler – SEC 8-K: HTTP 403." in meldungen
    w.news_abrufen = lambda: "Fehler: nicht erreichbar"
    assert "News: Fehler: nicht erreichbar" in w.planen(datetime(2026, 10, 12, 9, 20, tzinfo=UTC))  # 15-Minuten-Takt


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


def _plan_einstellen(admin, termine=None, auftraggeber="auftraggeber-a"):
    plan = {"automatik": True, "zeitzone": "Europe/Berlin", "auftraggeber": auftraggeber,
            "termine": termine or [{"wochentage": list(range(7)), "uhrzeit": "09:35", "art": "trading"}]}
    assert admin.put("/api/einrichtung/zeitplan", json=plan).status_code == 200


def test_geplanter_lauf_laeuft_auch_an_feiertag_und_wochenende(admin, werkzeug_attrappe):
    from stockmaster.worker import Worker

    _admin_token(admin)
    _plan_einstellen(admin)
    w = Worker()
    # 25.12.2026 ist ein Freitag und Feiertag an Xetra und NYSE; 2026-10-17 ein Samstag.
    for tag in (datetime(2026, 12, 25, 8, 40, tzinfo=UTC), datetime(2026, 10, 17, 7, 40, tzinfo=UTC)):
        assert "angelegt" in w.zeitplan(tag)
        lauf = admin.get("/api/laeufe").json()[0]
        assert lauf["ausloeser"] == "zeitplan" and lauf["status"] == "wartet"
        admin.post(f"/api/laeufe/{lauf['id']}/abbrechen")


def test_geplanter_lauf_wartet_sichtbar_auf_aktive_session_und_wird_nicht_uebersprungen(admin, demo_repo, werkzeug_attrappe):
    from stockmaster.spiel import lesen
    from stockmaster.worker import Worker

    _admin_token(admin)
    _plan_einstellen(admin)
    sperre = demo_repo / "session.lock"
    sperre.write_text(json.dumps({"person": "auftraggeber-b", "start": "2026-10-12T09:00:00+02:00"}))
    try:
        lesen.zuruecksetzen()
        w = Worker()
        assert w.zeitplan(datetime(2026, 10, 12, 7, 40, tzinfo=UTC)) is None  # 09:40 Berlin: wartet
        plan = admin.get("/api/laeufe/plan").json()
        assert len(plan["wartend"]) == 1 and "Session-Sperre von auftraggeber-b" in plan["wartend"][0]["grund"]
        assert not [z for z in admin.get("/api/laeufe").json() if z["ausloeser"] == "zeitplan"]
        assert w.zeitplan(datetime(2026, 10, 12, 8, 10, tzinfo=UTC)) is None  # Wiederholung, weiter wartend
        assert len(admin.get("/api/laeufe/plan").json()["wartend"]) == 1
        # Session vorbei: der nächste Takt startet den Lauf und räumt den wartenden Termin ab.
        sperre.unlink()
        meldung = w.zeitplan(datetime(2026, 10, 12, 8, 15, tzinfo=UTC))
        assert "angelegt" in meldung
        plan = admin.get("/api/laeufe/plan").json()
        assert plan["wartend"] == [] and "angelegt" in plan["letzte"][0]["ergebnis"]
        assert w.zeitplan(datetime(2026, 10, 12, 8, 20, tzinfo=UTC)) is None  # nur einmal je Termin
    finally:
        sperre.unlink(missing_ok=True)
        lesen.zuruecksetzen()


def test_wartender_termin_wird_nach_24_stunden_sichtbar_aufgegeben(admin, werkzeug_attrappe):
    from stockmaster import appdaten
    from stockmaster.worker import Worker

    _admin_token(admin)
    _plan_einstellen(admin)
    assert admin.delete("/api/einrichtung/geheimnis/claude_token").status_code == 200  # ohne Token wartet der Termin
    w = Worker()
    assert w.zeitplan(datetime(2026, 10, 12, 7, 40, tzinfo=UTC)) is None
    assert "Kein Claude-Token" in admin.get("/api/laeufe/plan").json()["wartend"][0]["grund"]
    assert "aufgegeben" in w.zeitplan(datetime(2026, 10, 13, 7, 45, tzinfo=UTC))
    plan = admin.get("/api/laeufe/plan").json()
    assert plan["letzte"][0]["termin"].startswith("2026-10-12") and "aufgegeben" in plan["letzte"][0]["ergebnis"]
    assert plan["letzte"][0]["ergebnis"].startswith("nicht gestartet: Kein Claude-Token")
    # Der Termin des neuen Tages ist inzwischen fällig und wartet seinerseits sichtbar.
    assert [e["termin"][:10] for e in plan["wartend"]] == ["2026-10-13"]
    assert list(appdaten.zustand_lesen("planer")["zeitplan_offen"]) == ["2026-10-13T09:35-trading"]


def test_verpasster_termin_wird_kurz_nachgeholt_aber_nicht_spaeter(admin, werkzeug_attrappe):
    from stockmaster.worker import Worker

    _admin_token(admin)
    _plan_einstellen(admin)
    # Dienst war nach 09:35 Berlin nicht aktiv: um 10:50 (75 Minuten später) wird nachgeholt, um 12:00 nicht mehr.
    assert "angelegt" in Worker().zeitplan(datetime(2026, 10, 12, 8, 50, tzinfo=UTC))
    admin.post(f"/api/laeufe/{admin.get('/api/laeufe').json()[0]['id']}/abbrechen")
    assert Worker().zeitplan(datetime(2026, 10, 13, 10, 0, tzinfo=UTC)) is None  # 12:00 Berlin: 145 Minuten zu spät


@pytest.fixture
def leeres_spiel(app, tmp_path, monkeypatch):
    """Frisch eingerichtetes Datenverzeichnis ohne Spiel (wie ein neues Volume)."""
    from stockmaster import __main__ as cli
    from stockmaster import config, db
    from stockmaster.spiel import lesen

    daten = tmp_path / "daten-neu"
    daten.mkdir()
    monkeypatch.setenv("STOCKMASTER_DATA_DIR", str(daten))
    config.einstellungen.cache_clear()
    lesen.zuruecksetzen()
    db.Basis.metadata.create_all(db.engine())
    cli.einrichten()
    yield daten
    lesen.zuruecksetzen()


def _lauf_stand(art="trading", person="auftraggeber-a"):
    from types import SimpleNamespace

    return SimpleNamespace(id="lauf-test", art=art, auftraggeber=person)


def test_trading_lauf_startet_das_spiel_selbst(admin, leeres_spiel, tmp_path):
    from stockmaster.claude_lauf import Schwaerzer
    from stockmaster.spiel import lesen
    from stockmaster.worker import Worker

    g = lesen.werkzeuge()["gemeinsam"]
    assert g.spiel_lesen() == {} and g.vorhandene_profile() == []
    log = tmp_path / "lauf.log"
    meldungen = Worker().spiel_vorbereiten(_lauf_stand(), log, Schwaerzer([]))
    assert len(meldungen) == 1 and "hat es gestartet" in meldungen[0]
    spiel = g.spiel_lesen()
    assert spiel["startdatum"] == g.heute().isoformat() and spiel["freigabe_ap12"] == "auftraggeber-a"
    assert spiel["ausloeser"] == "lauf" and g.vorhandene_profile() == list(g.PROFILE)
    assert g.richtlinien_offen() == []  # Standard-Anlagerichtlinien gelten von Anfang an
    assert "hat es gestartet" in log.read_text()
    aktionen = [e["aktion"] for e in admin.get("/api/admin/audit").json()]
    assert "spielstart_automatisch" in aktionen
    commit = subprocess.run(["git", "log", "--format=%s", "-3"], cwd=leeres_spiel, capture_output=True, text=True).stdout
    assert "Spielstart durch Trading-Lauf" in commit
    assert Worker().spiel_vorbereiten(_lauf_stand(), log, Schwaerzer([])) == []  # idempotent


def test_trading_lauf_zieht_ein_zukuenftiges_startdatum_vor(admin, leeres_spiel, tmp_path):
    from stockmaster.claude_lauf import Schwaerzer
    from stockmaster.spiel import lesen
    from stockmaster.worker import Worker, werkzeug

    g = lesen.werkzeuge()["gemeinsam"]
    erst = werkzeug("init", "--freigabe", "auftraggeber-a", "--startdatum", "2099-01-01")
    assert erst.returncode == 0, erst.stderr
    meldungen = Worker().spiel_vorbereiten(_lauf_stand(), tmp_path / "l.log", Schwaerzer([]))
    assert meldungen and "auf heute vorgezogen" in meldungen[0]
    assert g.spiel_lesen()["startdatum"] == g.heute().isoformat()


def test_nur_trading_laeufe_starten_das_spiel_und_der_lauf_ruft_die_vorbereitung_auf(admin, leeres_spiel, werkzeug_attrappe,
                                                                                    claude):
    from stockmaster.worker import Worker

    _admin_token(admin)
    for art, erwartet in (("review", False), ("trading", True)):
        werkzeug_attrappe.clear()
        antwort = admin.post("/api/laeufe", json={"art": art, "auftraggeber": "auftraggeber-b", "bestaetigt": True})
        assert antwort.status_code == 201, antwort.text
        w = Worker()
        w.auftraege_bearbeiten()
        w.lauf_thread.join(timeout=30)
        init_aufrufe = [a for a in werkzeug_attrappe if a[0] == "init"]
        assert bool(init_aufrufe) is erwartet, (art, werkzeug_attrappe)
        if erwartet:
            assert init_aufrufe[0][1:] == ("--freigabe", "auftraggeber-b", "--ausloeser", "lauf")


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


def test_lauf_ist_nie_durch_startdatum_oder_richtlinien_gesperrt(admin, demo_repo):
    from stockmaster.spiel import lesen

    _admin_token(admin)
    vorlage = (demo_repo / "strategie" / "defensiv.md")
    inhalt = vorlage.read_text()
    vorlage.write_text("# Anlagerichtlinie Defensiv\n\nStand: Vorlage aus tools/init.py (2026-10-06).\n")
    alt = _spiel(demo_repo, startdatum="2099-01-01")
    try:
        lesen.zuruecksetzen()
        assert admin.get("/api/laeufe/vorpruefung").status_code == 404  # keine Vorprüfung und keine Hinweise mehr
        schritte = [s["schritt"] for s in admin.get("/api/einrichtung").json()["pflichtschritte"]]
        assert "richtlinien" not in schritte and "spielstart" not in schritte
        for art in ("trading", "review", "testsession", "richtlinien"):
            ok = admin.post("/api/laeufe", json={"art": art, "auftraggeber": "auftraggeber-a", "bestaetigt": True})
            assert ok.status_code == 201, (art, ok.text)
            admin.post(f"/api/laeufe/{ok.json()['id']}/abbrechen")
    finally:
        vorlage.write_text(inhalt)
        (demo_repo / "spiel.json").write_text(__import__("json").dumps(alt))
        lesen.zuruecksetzen()


def test_worker_uebernimmt_standard_anlagerichtlinien(admin, demo_repo):
    from stockmaster.spiel import lesen
    from stockmaster.worker import Worker

    vorlage = demo_repo / "strategie" / "defensiv.md"
    inhalt = vorlage.read_text()
    vorlage.write_text("# Anlagerichtlinie Defensiv\n\nStand: Vorlage aus tools/init.py (2026-10-06).\n")
    try:
        lesen.zuruecksetzen()
        assert lesen.werkzeuge()["gemeinsam"].richtlinien_offen() == ["defensiv"]
        assert Worker().richtlinien_standard(datetime(2026, 10, 12, 8, 0, tzinfo=UTC)) == \
            "Standard-Anlagerichtlinien übernommen bzw. aktualisiert."
        assert lesen.werkzeuge()["gemeinsam"].richtlinien_offen() == []
        assert "Standard-Richtlinie" in vorlage.read_text()
        assert Worker().richtlinien_standard(datetime(2026, 10, 12, 8, 5, tzinfo=UTC)) is None  # nichts mehr zu tun
    finally:
        vorlage.write_text(inhalt)
        lesen.zuruecksetzen()


def test_worker_aktualisiert_unveraenderte_alte_standard_richtlinie_und_laesst_angepasste_stehen(admin, demo_repo):
    from stockmaster.spiel import lesen
    from stockmaster.worker import Worker

    g = lesen.werkzeuge()["gemeinsam"]
    dateien = {p: demo_repo / "strategie" / f"{p}.md" for p in ("defensiv", "ausgewogen")}
    inhalt = {p: d.read_text() for p, d in dateien.items()}
    try:
        lesen.zuruecksetzen()
        g = lesen.werkzeuge()["gemeinsam"]
        alt = inhalt["defensiv"].replace("Standard-Richtlinie v2 aus", "Standard-Richtlinie aus") \
            .replace("Standard-Richtlinie v2 übernommen", "Standard-Richtlinie übernommen")
        if g.richtlinie_standard_version("defensiv") is None:  # Demo-Daten enthalten eigene Richtlinien: Standard daraus bauen
            alt = g.framework_pfad("config", "richtlinien", "defensiv.md").read_text().format(
                datum="2026-07-13", version=1, **{k: "x" for k in ("max_anteil_zertifikate", "max_hebel", "max_exposure",
                "max_einzelposition", "min_cashquote", "max_risiko_trade", "drawdown_stufe1", "drawdown_stufe2",
                "benchmark")}).replace("Standard-Richtlinie v1 aus", "Standard-Richtlinie aus").replace(
                "Standard-Richtlinie v1 übernommen", "Standard-Richtlinie übernommen")
        dateien["defensiv"].write_text(alt)
        assert g.richtlinie_standard_version("defensiv") == 1 and g.richtlinien_veraltet() == ["defensiv"]
        assert Worker().richtlinien_standard(datetime(2026, 10, 12, 8, 0, tzinfo=UTC)) == \
            "Standard-Anlagerichtlinien übernommen bzw. aktualisiert."
        assert g.richtlinie_standard_version("defensiv") == 2 and g.richtlinien_veraltet() == []
        assert Worker().richtlinien_standard(datetime(2026, 10, 12, 8, 5, tzinfo=UTC)) is None
    finally:
        for p, d in dateien.items():
            d.write_text(inhalt[p])
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


def test_naechste_termine_nur_nach_wochentagen_des_zeitplans(app):
    from stockmaster.auftraege import naechste_termine

    plan = {"zeitzone": "Europe/Berlin",
            "termine": [{"wochentage": [0, 1, 2, 3, 4], "uhrzeit": "09:35", "art": "trading"}]}
    # Freitag 2026-10-09 10:30 Berlin: der Freitagstermin ist vorbei, nächster ist Montag.
    naechste = naechste_termine(plan, datetime(2026, 10, 9, 8, 30, tzinfo=UTC), 2)
    assert [t["zeit"][:16] for t in naechste] == ["2026-10-12T09:35", "2026-10-13T09:35"]
    assert naechste_termine(plan, datetime(2026, 10, 9, 7, 0, tzinfo=UTC), 1)[0]["zeit"][:16] == "2026-10-09T09:35"
    # Feiertage und Wochenenden sind keine Sperre: der Zeitplan nennt jeden eingestellten Tag (hier auch Samstag/Sonntag).
    alle = {"zeitzone": "Europe/Berlin", "termine": [{"wochentage": list(range(7)), "uhrzeit": "21:00", "art": "trading"}]}
    tage = [t["zeit"][:10] for t in naechste_termine(alle, datetime(2026, 12, 24, 12, 0, tzinfo=UTC), 4)]
    assert tage == ["2026-12-24", "2026-12-25", "2026-12-26", "2026-12-27"]  # 24./25. Dezember: Xetra und NYSE zu


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


# --------------------------------------------------------------------------
# Freigaben (Entscheidung 37): Befehle, die weder erlaubt noch verboten sind, entscheidet ein Administrator

AWK = "awk 'BEGIN{print 1+1}'"


@pytest.fixture
def schnell(monkeypatch):
    """Kurze Taktung und Wartezeit, damit die Läufe in Sekunden durch sind."""
    from stockmaster import config, freigaben

    monkeypatch.setattr(freigaben, "TAKT_SEKUNDEN", 0.05)

    def wartezeit(sekunden: int):
        monkeypatch.setenv("SM_FREIGABE_WARTEZEIT_SEKUNDEN", str(sekunden))
        config.einstellungen.cache_clear()

    return wartezeit


def _offene_freigabe(admin, sekunden=20):
    import time

    ende = time.monotonic() + sekunden
    while time.monotonic() < ende:
        offen = admin.get("/api/freigaben", params={"offen": "true"}).json()
        if offen:
            return offen[0]
        time.sleep(0.05)
    raise AssertionError("Es kam keine Freigabe-Anfrage an.")


def _lauf_mit_frage(admin, claude, befehl, anzahl=1):
    from stockmaster.worker import Worker

    _admin_token(admin)
    claude.modus(f"frage|{befehl}|{anzahl}")
    lauf = _lauf_starten(admin)
    worker = Worker()
    worker.auftraege_bearbeiten()
    return lauf, worker


def _entscheiden(admin, freigabe, entscheidung):
    return admin.post(f"/api/freigaben/{freigabe['id']}/entscheidung", json={"entscheidung": entscheidung})


def test_freigabe_erlauben_ueber_die_web_ui(admin, werkzeug_attrappe, claude, schnell):
    lauf, worker = _lauf_mit_frage(admin, claude, AWK)
    offen = _offene_freigabe(admin)
    assert offen["befehl"] == AWK and offen["werkzeug"] == "Bash" and offen["lauf"] == lauf["id"]
    assert offen["entscheidbar"] and 0 < offen["sekunden_rest"] <= 180 and offen["beschreibung"] == "Test"
    antwort = _entscheiden(admin, offen, "erlauben")
    assert antwort.status_code == 200 and antwort.json()["status"] == "erlaubt"
    worker.lauf_thread.join(timeout=30)
    fertig = admin.get(f"/api/laeufe/{lauf['id']}").json()
    assert fertig["status"] == "ok" and "Freigabe: allow" in fertig["meldung"]
    log = admin.get(f"/api/laeufe/{lauf['id']}/log").json()["text"]
    assert f"? Freigabe angefragt – Bash: {AWK}" in log and "✓ Freigabe erteilt" in log and "← ausgefuehrt" in log
    verlauf = admin.get("/api/freigaben", params={"lauf": lauf["id"]}).json()
    assert [f["status"] for f in verlauf] == ["erlaubt"] and verlauf[0]["entschieden"]
    aktionen = [z["aktion"] for z in admin.get("/api/admin/audit").json()]
    assert "freigabe_erlaubt" in aktionen
    # Der Auftrag kam über stdin, nicht über die Kommandozeile.
    aufruf = claude()[-1]
    assert "--input-format" in aufruf["args"] and aufruf["args"][aufruf["args"].index("--permission-prompt-tool") + 1] == "stdio"
    assert "Trading-Session" in json.loads(aufruf["stdin"])["message"]["content"]
    assert not any("Trading-Session" in a for a in aufruf["args"])


def test_freigabe_ablehnen(admin, werkzeug_attrappe, claude, schnell):
    lauf, worker = _lauf_mit_frage(admin, claude, AWK)
    assert _entscheiden(admin, _offene_freigabe(admin), "ablehnen").json()["status"] == "abgelehnt"
    worker.lauf_thread.join(timeout=30)
    assert "Freigabe: deny" in admin.get(f"/api/laeufe/{lauf['id']}").json()["meldung"]
    log = admin.get(f"/api/laeufe/{lauf['id']}/log").json()["text"]
    assert "✗ Freigabe abgelehnt: Von einem Administrator abgelehnt." in log
    assert "freigabe_abgelehnt" in [z["aktion"] for z in admin.get("/api/admin/audit").json()]


def test_freigabe_verfaellt_ohne_antwort_und_wird_nicht_wiederholt(admin, werkzeug_attrappe, claude, schnell):
    schnell(1)
    lauf, worker = _lauf_mit_frage(admin, claude, AWK, anzahl=2)  # Claude fragt zweimal dasselbe
    worker.lauf_thread.join(timeout=30)
    assert admin.get(f"/api/laeufe/{lauf['id']}").json()["status"] == "ok"
    verlauf = admin.get("/api/freigaben", params={"lauf": lauf["id"]}).json()
    assert [f["status"] for f in verlauf] == ["abgelaufen"]  # die Wiederholung wartet nicht noch einmal
    log = admin.get(f"/api/laeufe/{lauf['id']}/log").json()["text"]
    assert "Keine Entscheidung innerhalb von 1 Sekunden; automatisch abgelehnt." in log
    assert "Bereits abgelehnt (keine Entscheidung rechtzeitig)" in log
    # Zu spät entschieden: keine Wirkung.
    assert _entscheiden(admin, verlauf[0], "erlauben").status_code == 409


def test_nie_freigebbar_wird_ohne_rueckfrage_abgelehnt(admin, werkzeug_attrappe, claude, schnell):
    lauf, worker = _lauf_mit_frage(admin, claude, "echo x > /data/trades/x.csv")
    worker.lauf_thread.join(timeout=30)
    assert admin.get("/api/freigaben", params={"offen": "true"}).json() == []
    verlauf = admin.get("/api/freigaben", params={"lauf": lauf["id"]}).json()
    assert [f["status"] for f in verlauf] == ["gesperrt"] and "Umleitung" in verlauf[0]["grund"]
    assert verlauf[0]["entscheidbar"] is False and _entscheiden(admin, verlauf[0], "erlauben").status_code == 409
    log = admin.get(f"/api/laeufe/{lauf['id']}/log").json()["text"]
    assert "Nicht freigebbar: Umleitung in eine Datei" in log and "Freigabe: deny" in admin.get(
        f"/api/laeufe/{lauf['id']}").json()["meldung"]


def test_abbruch_beendet_offene_freigabe(admin, werkzeug_attrappe, claude, schnell):
    lauf, worker = _lauf_mit_frage(admin, claude, AWK)
    _offene_freigabe(admin)
    assert admin.post(f"/api/laeufe/{lauf['id']}/abbrechen").status_code == 200
    worker.lauf_thread.join(timeout=30)
    assert admin.get(f"/api/laeufe/{lauf['id']}").json()["status"] == "abgebrochen"
    verlauf = admin.get("/api/freigaben", params={"lauf": lauf["id"]}).json()
    assert [f["status"] for f in verlauf] == ["abgebrochen"] and not verlauf[0]["entscheidbar"]


def test_freigaben_api_eingaben_und_einmal_entscheiden(admin, werkzeug_attrappe, claude, schnell):
    lauf, worker = _lauf_mit_frage(admin, claude, AWK)
    offen = _offene_freigabe(admin)
    url = f"/api/freigaben/{offen['id']}/entscheidung"
    assert admin.post(url, json={"entscheidung": "vielleicht"}).status_code == 422
    assert admin.post(url, json={"entscheidung": "erlauben", "zusatz": 1}).status_code == 422
    assert admin.post("/api/freigaben/gibt-es-nicht/entscheidung", json={"entscheidung": "erlauben"}).status_code == 404
    assert admin.post(url, json={"entscheidung": "erlauben"}, headers={"X-CSRF-Token": "falsch"}).status_code == 403
    assert _entscheiden(admin, offen, "erlauben").status_code == 200
    assert _entscheiden(admin, offen, "ablehnen").status_code == 409  # einmal entschieden, nicht umzuentscheiden
    worker.lauf_thread.join(timeout=30)


def test_freigaben_nur_fuer_angemeldete_und_entscheiden_nur_admins(nutzer, client):
    from datetime import timedelta

    from stockmaster.db import jetzt_utc, neue_sitzung
    from stockmaster.freigaben import OFFEN
    from stockmaster.modelle import Auftrag, Freigabe

    with neue_sitzung() as db:
        auftrag = Auftrag(art="trading")
        db.add(auftrag)
        db.flush()
        zeile = Freigabe(auftrag_id=auftrag.id, werkzeug="Bash", befehl="date", status=OFFEN,
                         laeuft_ab=jetzt_utc() + timedelta(minutes=3))
        db.add(zeile)
        db.commit()
        fid = zeile.id
    assert nutzer.get("/api/freigaben").status_code == 200  # wie das Log eines Laufs für alle sichtbar
    assert nutzer.post(f"/api/freigaben/{fid}/entscheidung", json={"entscheidung": "erlauben"}).status_code == 404


def test_freigaben_ohne_anmeldung(client):
    assert client.get("/api/freigaben").status_code == 401
    assert client.post("/api/freigaben/x/entscheidung", json={"entscheidung": "erlauben"}).status_code == 401


def test_entscheider_schwaerzt_und_begrenzt(admin):
    from stockmaster import auftraege, claude_lauf, freigaben
    from stockmaster.db import neue_sitzung

    with neue_sitzung() as db:
        auftrag = auftraege.anlegen(db, "trading")
        db.commit()
        auftrag_id = auftrag.id
    zeit = iter(range(0, 10_000, 1000))  # jede Abfrage der Uhr springt weit: die Anfrage verfällt sofort
    entscheiden = freigaben.entscheider_fuer(auftrag_id, claude_lauf.Schwaerzer([TOKEN]), lambda: False,
                                             monoton=lambda: next(zeit), schlafen=lambda _s: None)
    erlaubt, meldung = entscheiden("Bash", {"command": f"echo {TOKEN}"}, f"zeigt {TOKEN}")
    assert (erlaubt, meldung.startswith("Keine Entscheidung")) == (False, True)
    zeile = admin.get("/api/freigaben", params={"lauf": auftrag_id}).json()[0]
    assert TOKEN not in zeile["befehl"] + (zeile["beschreibung"] or "") and "[geheim]" in zeile["befehl"]
    # Andere Werkzeuge sind nie freigebbar.
    assert entscheiden("Write", {"file_path": "/data/portfolios/x", "content": "y"})[1].startswith("Nicht freigebbar")
    for n in range(freigaben.MAX_JE_LAUF):
        entscheiden("Write", {"file_path": f"/data/x{n}"})
    assert entscheiden("Write", {"file_path": "/data/y"}) == (False, "Zu viele Freigabe-Anfragen in diesem Lauf.")


def test_offene_freigaben_werden_beim_dienststart_geschlossen(admin):
    from datetime import timedelta

    from stockmaster import freigaben
    from stockmaster.db import jetzt_utc, neue_sitzung
    from stockmaster.modelle import Auftrag, Freigabe

    with neue_sitzung() as db:
        auftrag = Auftrag(art="trading")
        db.add(auftrag)
        db.flush()
        zeile = Freigabe(auftrag_id=auftrag.id, werkzeug="Bash", befehl="date", status="offen",
                         laeuft_ab=jetzt_utc() + timedelta(minutes=3))
        db.add(zeile)
        db.commit()
        fid = zeile.id
    assert freigaben.schliessen() == 1
    with neue_sitzung() as db:
        assert db.get(Freigabe, fid).status == "abgebrochen"
    assert admin.get("/api/freigaben", params={"offen": "true"}).json() == []


# --------------------------------------------------------------------------
# Automatische Nachbuchung nach Handelsschluss (Entscheidung 38)

UTC_0030 = datetime(2026, 10, 11, 22, 30, tzinfo=UTC)  # 00:30 Uhr deutsche Zeit am 12.10.2026 (Sommerzeit)
NACHBUCHUNG_ABLAUF = [("session", "start"), ("bewertung", "nachbuchen"), ("bewertung", "bericht"), ("pruefe",),
                      ("datenverzeichnis", "commit"), ("session", "ende")]


def _namen(aufrufe, ab=0):
    return [tuple(a[:2]) if a[0] in ("session", "bewertung", "datenverzeichnis") else (a[0],) for a in aufrufe[ab:]]


def test_nachbuchung_nachts_mit_sperre_bericht_pruefung_und_commit(app, werkzeug_attrappe):
    from datetime import timedelta

    from stockmaster.worker import Worker

    w = Worker()
    assert w.nachbuchen(UTC_0030 - timedelta(minutes=20)) is None and werkzeug_attrappe == []  # erst ab 00:30
    meldung = w.nachbuchen(UTC_0030)
    assert meldung == "Nachbuchung: bis 11.10.2026 gebucht; Prüfung bestanden"
    assert _namen(werkzeug_attrappe) == NACHBUCHUNG_ABLAUF
    start = werkzeug_attrappe[0]
    assert start[2:5] == ("--person", start[3], "--art") and start[5] == "nachbuchung"
    assert werkzeug_attrappe[4] == ("datenverzeichnis", "commit", "-m", "session: Nachbuchung bis 2026-10-11 (automatisch)")
    assert w.zustand["nachbuchung_tag"] == "2026-10-12" and w.zustand["nachbuchung_ergebnis"]["ok"] is True
    assert w.zustand["nachbuchung_ergebnis"]["pruefung_ok"] is True
    # Pro Tag einmal.
    werkzeug_attrappe.clear()
    assert w.nachbuchen(UTC_0030 + timedelta(hours=3)) is None and werkzeug_attrappe == []


def test_nachbuchung_wiederholt_nach_fehler_und_gibt_die_sperre_frei(app, werkzeug_attrappe, monkeypatch):
    from datetime import timedelta

    from stockmaster import worker
    from stockmaster.worker import Worker

    attrappe = worker.werkzeug
    ausfall = {"an": True}

    def werkzeug(name, *argumente, **kw):
        ergebnis = attrappe(name, *argumente, **kw)
        if ausfall["an"] and (name, *argumente[:1]) == ("bewertung", "nachbuchen"):
            ergebnis.returncode, ergebnis.stdout = 1, "Fehler: Keine Tagesdaten für ^GSPC"
        return ergebnis

    monkeypatch.setattr(worker, "werkzeug", werkzeug)
    w = Worker()
    assert w.nachbuchen(UTC_0030) == "Nachbuchung: Fehler: Keine Tagesdaten für ^GSPC"
    assert _namen(werkzeug_attrappe) == [("session", "start"), ("bewertung", "nachbuchen"), ("session", "ende")]
    assert w.zustand["nachbuchung_ergebnis"]["ok"] is False and "nachbuchung_tag" not in w.zustand
    werkzeug_attrappe.clear()
    assert w.nachbuchen(UTC_0030 + timedelta(minutes=30)) is None and werkzeug_attrappe == []  # erst nach einer Stunde
    ausfall["an"] = False
    assert w.nachbuchen(UTC_0030 + timedelta(minutes=61)).startswith("Nachbuchung: bis 11.10.2026 gebucht")
    assert w.zustand["nachbuchung_tag"] == "2026-10-12" and w.zustand["nachbuchung_ergebnis"]["ok"] is True


def test_nachbuchung_meldet_pruefung_mit_fehlern_und_bucht_trotzdem(app, werkzeug_attrappe, monkeypatch):
    from stockmaster import worker
    from stockmaster.worker import Worker

    attrappe = worker.werkzeug

    def werkzeug(name, *argumente, **kw):
        ergebnis = attrappe(name, *argumente, **kw)
        if name == "pruefe":
            ergebnis.returncode, ergebnis.stdout = 1, "FEHLER [Cash] Cash stimmt nicht"
        return ergebnis

    monkeypatch.setattr(worker, "werkzeug", werkzeug)
    w = Worker()
    assert "Prüfung mit Fehlern: FEHLER [Cash] Cash stimmt nicht" in w.nachbuchen(UTC_0030)
    assert w.zustand["nachbuchung_ergebnis"]["pruefung_ok"] is False and w.zustand["nachbuchung_tag"] == "2026-10-12"
    assert _namen(werkzeug_attrappe)[-2:] == [("datenverzeichnis", "commit"), ("session", "ende")]


def test_nachbuchung_nicht_waehrend_session_oder_lauf_und_ohne_rueckstand(app, werkzeug_attrappe, monkeypatch):
    from stockmaster import auftraege
    from stockmaster.worker import Worker

    w = Worker()
    monkeypatch.setattr(auftraege, "session_sperre_aktiv", lambda: {"person": "auftraggeber-a", "start": "x"})
    assert w.nachbuchen(UTC_0030) is None and werkzeug_attrappe == [] and "nachbuchung_versuch" not in w.zustand
    monkeypatch.setattr(auftraege, "session_sperre_aktiv", lambda: None)
    monkeypatch.setattr(w, "_nachbuchung_rueckstand", lambda gestern: [])
    assert w.nachbuchen(UTC_0030) is None and werkzeug_attrappe == []
    assert w.zustand["nachbuchung_tag"] == "2026-10-12"  # nichts zu tun gilt als erledigt


def test_nachbuchung_gehoert_zur_schleife(app, werkzeug_attrappe):
    from stockmaster.worker import Worker

    w = Worker()
    w.einmal(UTC_0030)
    assert ("bewertung", "nachbuchen") in [tuple(a[:2]) for a in werkzeug_attrappe]


# --------------------------------------------------------------------------
# Beobachtungsliste nach Handelsschluss (Entscheidung 38)

BEOBACHTUNG_ZEILE = "Beobachtungsliste: 590 von 603 Werten aktualisiert (yfinance), 0 mit altem Stand, 13 ohne Daten."


def _um(tag, uhr):
    """Berliner Ortszeit (Sommerzeit, UTC+2) als UTC-Zeitpunkt."""
    stunde, minute = map(int, uhr.split(":"))
    return datetime(2026, 10, tag, stunde, minute, tzinfo=UTC) - timedelta(hours=2)


@pytest.fixture
def beobachtung_attrappe(werkzeug_attrappe, monkeypatch):
    """Das Werkzeug 'beobachtung' schreibt wie das echte den Zwischenspeicher; `ausfall` schaltet Fehler zu."""
    from stockmaster import worker
    from stockmaster.config import einstellungen

    attrappe = worker.werkzeug
    zustand = {"ausfall": None}
    speicher = einstellungen().daten_pfad / ".cache" / "beobachtung.json"  # das Datenverzeichnis gilt für alle Tests
    vorher = speicher.read_bytes() if speicher.exists() else None
    speicher.unlink(missing_ok=True)

    def werkzeug(name, *argumente, **kw):
        ergebnis = attrappe(name, *argumente, **kw)
        if name == "beobachtung":
            if zustand["ausfall"] == "zeit":
                raise subprocess.TimeoutExpired("beobachtung", 1800)
            if zustand["ausfall"]:
                ergebnis.returncode, ergebnis.stdout = 1, "Fehler: Keine Kursdaten erhalten (Quelle nicht erreichbar?)"
            else:
                ergebnis.stdout = BEOBACHTUNG_ZEILE + "\n  Ohne Daten (Kürzel prüfen oder aus der Liste nehmen): X.DE"
                speicher.parent.mkdir(parents=True, exist_ok=True)
                speicher.write_text("{}", encoding="utf-8")
        return ergebnis

    monkeypatch.setattr(worker, "werkzeug", werkzeug)
    yield zustand
    speicher.unlink(missing_ok=True)
    if vorher is not None:
        speicher.write_bytes(vorher)


def _beobachtung_aufrufe(aufrufe):
    return [a for a in aufrufe if a[0] == "beobachtung"]


def test_beobachtung_einmal_je_handelstag_nach_dem_schluss(app, werkzeug_attrappe, beobachtung_attrappe):
    from stockmaster.worker import Worker

    w = Worker()
    assert w.beobachtung_aktualisieren(_um(12, "23:20")) == BEOBACHTUNG_ZEILE
    assert _beobachtung_aufrufe(werkzeug_attrappe) == [("beobachtung", "aktualisieren")]
    assert w.zustand["beobachtung_tag"] == "2026-10-12" and w.zustand["beobachtung_ergebnis"]["ok"] is True
    assert w.zustand["beobachtung_ergebnis"]["meldung"] == BEOBACHTUNG_ZEILE
    werkzeug_attrappe.clear()
    for zeit in (_um(12, "23:50"), _um(13, "00:40"), _um(13, "12:00"), _um(13, "23:14")):
        assert w.beobachtung_aktualisieren(zeit) is None  # vor 23:15 des nächsten Tages gilt der Stand von gestern
    assert werkzeug_attrappe == []
    assert w.beobachtung_aktualisieren(_um(13, "23:16")) == BEOBACHTUNG_ZEILE
    assert w.zustand["beobachtung_tag"] == "2026-10-13"


def test_beobachtung_am_wochenende_nur_nachholen_nie_neu(app, werkzeug_attrappe, beobachtung_attrappe):
    from stockmaster.worker import Worker

    w = Worker()
    assert w.beobachtung_aktualisieren(_um(16, "23:20")) is not None  # Freitag
    werkzeug_attrappe.clear()
    for zeit in (_um(17, "10:00"), _um(17, "23:30"), _um(18, "23:30"), _um(19, "10:00")):  # Sa, Sa abends, So, Mo früh
        assert w.beobachtung_aktualisieren(zeit) is None
    assert werkzeug_attrappe == []
    assert w.beobachtung_aktualisieren(_um(19, "23:20")) is not None  # Montag nach Schluss
    assert w.zustand["beobachtung_tag"] == "2026-10-19"


def test_beobachtung_bei_fehlendem_stand_sofort_und_nach_ausfall_nachholen(app, werkzeug_attrappe, beobachtung_attrappe):
    from stockmaster.worker import Worker

    w = Worker()
    assert w.beobachtung_aktualisieren(_um(15, "14:00")) == BEOBACHTUNG_ZEILE  # Donnerstag mittags, noch ohne Stand
    assert w.zustand["beobachtung_tag"] == "2026-10-14"  # Mittwochs-Kerzen; der Donnerstag folgt abends
    assert w.beobachtung_aktualisieren(_um(15, "23:20")) is not None
    assert w.zustand["beobachtung_tag"] == "2026-10-15"
    # Dienst lag zwei Tage still: beim Start wird nachgeholt, obwohl 23:15 nicht ist.
    assert w.beobachtung_aktualisieren(_um(20, "09:00")) is not None
    assert w.zustand["beobachtung_tag"] == "2026-10-19"


def test_beobachtung_fehler_stuendlich_wiederholen_und_alten_stand_nicht_ueberschreiben(app, werkzeug_attrappe,
                                                                                         beobachtung_attrappe):
    from stockmaster.worker import Worker

    w = Worker()
    beobachtung_attrappe["ausfall"] = True
    meldung = w.beobachtung_aktualisieren(_um(12, "23:20"))
    assert meldung == "Beobachtungsliste: Fehler: Keine Kursdaten erhalten (Quelle nicht erreichbar?)"
    assert w.zustand["beobachtung_ergebnis"]["ok"] is False and "beobachtung_tag" not in w.zustand
    werkzeug_attrappe.clear()
    assert w.beobachtung_aktualisieren(_um(12, "23:50")) is None and werkzeug_attrappe == []  # erst nach einer Stunde
    assert w.beobachtung_aktualisieren(_um(13, "00:21")) is not None  # zweiter Fehlversuch
    beobachtung_attrappe["ausfall"] = None
    assert w.beobachtung_aktualisieren(_um(13, "01:22")) == BEOBACHTUNG_ZEILE
    assert w.zustand["beobachtung_tag"] == "2026-10-12" and w.zustand["beobachtung_ergebnis"]["ok"] is True


def test_beobachtung_zeitueberschreitung_ist_ein_fehlversuch(app, werkzeug_attrappe, beobachtung_attrappe):
    from stockmaster.worker import Worker

    w = Worker()
    beobachtung_attrappe["ausfall"] = "zeit"
    assert w.beobachtung_aktualisieren(_um(12, "23:20")) == "Beobachtungsliste: Zeitüberschreitung beim Abruf."
    assert w.zustand["beobachtung_ergebnis"]["ok"] is False
    assert w.beobachtung_aktualisieren(_um(12, "23:30")) is None  # kein Dauerfeuer


def test_beobachtung_gehoert_zur_schleife(app, werkzeug_attrappe, beobachtung_attrappe):
    from stockmaster.worker import Worker

    w = Worker()
    assert BEOBACHTUNG_ZEILE in w.einmal(_um(12, "23:20"))
