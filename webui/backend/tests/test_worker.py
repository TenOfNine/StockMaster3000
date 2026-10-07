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

