"""Claude-Code-Läufe im Container: Befehl, Leitplanken, Umgebung, Log mit geschwärzten Secrets.

Arbeitsverzeichnis ist das Framework (CLAUDE.md, tools/, regeln.md, nur lesend), das Datenverzeichnis
wird mit --add-dir freigegeben. Das Token kommt aus der App-Konfiguration und steht nur in der
Umgebung dieses einen Prozesses; ANTHROPIC_API_KEY und ähnliche Variablen werden nie weitergegeben.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from . import appdaten, claude_optionen
from .config import einstellungen

TOKEN_MUSTER = re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}")
LIMIT_MUSTER = re.compile(r"usage limit|limit reached|rate.?limit|5-hour limit|weekly limit|out of (extra )?usage", re.I)
AUTH_MUSTER = re.compile(r"invalid api key|authentication|unauthori[sz]ed|401|oauth token|please run /login|not logged in",
                         re.I)
MODELL_MUSTER = re.compile(r"model|effort", re.I)
DURCHREICHEN = ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy", "no_proxy", "SSL_CERT_FILE",
                "NODE_EXTRA_CA_CERTS", "TZ", "SM_VERSION")
ERGEBNIS_MAX = 100_000
ERLAUBTE_WERKZEUGE = ["Read", "Glob", "Grep", "Edit", "Write", "WebSearch", "WebFetch", "TodoWrite",
                      "Bash(python tools/*)", "Bash(python3 tools/*)", "Bash(git status*)", "Bash(git log*)",
                      "Bash(git diff*)", "Bash(git show*)", "Bash(date*)", "Bash(ls*)",
                      # Das Datenverzeichnis ist ein eigenes Repository: Claude ruft git dort oft mit -C auf.
                      "Bash(git -C * log*)", "Bash(git -C * status*)", "Bash(git -C * diff*)", "Bash(git -C * show*)"]


class Schwaerzer:
    """Ersetzt alle bekannten Secrets (und Token-Muster) in Logtexten."""

    def __init__(self, geheimnisse: list[str]):
        self.werte = sorted({g for g in geheimnisse if g and len(g) >= 8}, key=len, reverse=True)

    def __call__(self, text: str) -> str:
        for wert in self.werte:
            text = text.replace(wert, "[geheim]")
        return TOKEN_MUSTER.sub("[geheim]", text)


def _abs(pfad: Path) -> str:
    """Absoluter Pfad in der Schreibweise der Claude-Code-Berechtigungen (//pfad)."""
    return "/" + str(pfad.resolve())


def einstellungen_json() -> str:
    """Verwaltete Leitplanken (AUFTRAG_WEBUI.md 4.6): keine Hand-Änderung an Spielstand-Rechendaten."""
    e = einstellungen()
    daten, framework, app = _abs(e.daten_pfad), _abs(e.framework_pfad), _abs(e.app_pfad)
    verboten = []
    for ziel in (f"{daten}/portfolios/**", f"{daten}/trades/**", f"{daten}/data/**", f"{daten}/news/**",
                 f"{daten}/spiel.json", f"{daten}/session.lock", f"{daten}/.git/**", f"{framework}/**"):
        verboten += [f"Edit({ziel})", f"Write({ziel})"]
    verboten += [f"Read({app}/**)", f"Edit({app}/**)", f"Write({app}/**)", "Read(//proc/**)",
                 "Bash(env*)", "Bash(printenv*)", "Bash(curl*)", "Bash(wget*)",
               # git nie pushen oder umkonfigurieren, auch nicht mit -C <pfad> davor
               "Bash(git push*)", "Bash(git * push*)", "Bash(git remote*)", "Bash(git * remote*)",
               "Bash(git config*)", "Bash(git * config*)", "Bash(git reset*)", "Bash(git * reset*)"]
    return json.dumps({"permissions": {"deny": verboten}, "env": {"DISABLE_AUTOUPDATER": "1"}})


def prompt(art: str, auftrag) -> str:
    e = einstellungen()
    aufwand = auftrag.aufwand or "Standard der CLI"
    gemeinsam = (
        f"Datenverzeichnis (Spielstand): {e.daten_pfad}. Alle Spielstand-Pfade aus CLAUDE.md (journal/, reviews/, "
        f"strategie/, lessons.md, ranking.md, portfolios/, trades/, data/, news/) beziehen sich darauf; die Werkzeuge "
        f"finden es über STOCKMASTER_DATA_DIR. Kein git pull und kein git push: Am Ende lokal committen mit "
        f"`python tools/datenverzeichnis.py commit -m \"session: ...\"`. Auftraggeber: {auftrag.auftraggeber} "
        f"(Schritt 1 entfällt). Setup dieses Laufs: Modell {auftrag.modell}, Aufwand {aufwand}, Lauf {auftrag.id}, "
        f"gestartet {'per Zeitplan' if auftrag.ausloeser == 'zeitplan' else 'manuell'} über die Web-UI."
    )
    if art == "trading":
        return ("Führe eine Trading-Session nach CLAUDE.md (Trading-Modus) durch. " + gemeinsam +
                " Prüfe zuerst `python tools/richtlinien.py status`: Sind Anlagerichtlinien offen, handle nicht und "
                "melde das. Trage Modell und Aufwand im Session-Eintrag in der Zeile '- Setup:' ein. Nutze "
                "zusätzlich zur Web-Suche den News-Speicher (`python tools/news.py liste --tage 3`) als datierte Quelle.")
    if art == "review":
        return ("Erstelle nur die fälligen Reviews und den Bericht (CLAUDE.md, Schritte 2 bis 5, 10 bis 12), "
                "ohne Orders: `python tools/buchen.py` nicht aufrufen. Starte die Sperre mit "
                "`python tools/session.py start --person <kennung> --art review`. " + gemeinsam +
                " Vermerke Modell und Aufwand im Review unter 'Setup'.")
    if art == "richtlinien":
        return ("Formuliere die Anlagerichtlinien aus (AP12 Punkt 2, regeln.md Abschnitt 11): strategie/defensiv.md, "
                "strategie/ausgewogen.md und strategie/aggressiv.md. Starte die Sperre mit "
                "`python tools/session.py start --person <kennung> --art richtlinien`. Hole je Profil die Vorlage mit "
                "den verbindlichen Limits über `python tools/richtlinien.py vorlage --profil <profil>` (Abschnitt "
                "Risikobudget unverändert übernehmen) und schreibe die Datei neu: Ziel (Rendite gegen die "
                "Benchmark, Rolle im Experiment), Horizont und Session-Rhythmus, erlaubte Instrumente mit "
                "Einschränkungen dieses Profils, Benchmark und die Ausgangsstrategie mit Begründung und aktueller "
                "Marktsicht (Kurse nur aus tools/kurse.py, News aus dem News-Speicher oder der Web-Suche, jeweils "
                "mit URL und Datum; Fakten und Einschätzungen trennen, Unsicherheit benennen). Die drei Profile "
                "sollen sich im Risiko deutlich unterscheiden, aber alle Limits einhalten. Ersetze die Zeile "
                "'Stand: Vorlage aus tools/init.py …' durch den heutigen Stand und trage in der Änderungshistorie "
                "Datum, Anlass und Prüfkriterium ein. Erfasse keine Orders und keine Journal-Einträge; "
                "`python tools/buchen.py` nicht aufrufen. Prüfe am Ende mit `python tools/richtlinien.py status`, "
                "dass keine Richtlinie mehr offen ist. " + gemeinsam)
    return ("Testsession ohne Trades (AP12): Spiele den Ablauf einmal vollständig durch (Sperre mit "
            "`python tools/session.py start --person <kennung> --art testsession`, Nachbuchen, Prüfen, "
            "Marktüberblick mit tools/kurse.py und dem News-Speicher, Bericht), aber erfasse keine Orders und "
            "schreibe keine Journal-Einträge; `python tools/buchen.py` nicht aufrufen. Fasse am Ende zusammen, ob "
            "alle Werkzeuge funktionieren und was vor der Freigabe zu klären ist. " + gemeinsam)


def umgebung(token: str, temp: Path) -> dict:
    e = einstellungen()
    werte = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(temp / "home"),
        "CLAUDE_CONFIG_DIR": str(temp / "claude"),
        "LANG": "C.UTF-8",
        "CLAUDE_CODE_OAUTH_TOKEN": token,
        "DISABLE_AUTOUPDATER": "1",
        "STOCKMASTER_DATA_DIR": str(e.daten_pfad),
        "STOCKMASTER_FRAMEWORK_DIR": str(e.framework_pfad),
        "STOCKMASTER_APP_DIR": str(e.app_pfad),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    werte.update(kurs_umgebung())
    for name in DURCHREICHEN:
        if os.environ.get(name):
            werte[name] = os.environ[name]
    return werte


def kurs_umgebung() -> dict:
    """Kursanbieter für tools/kurse.py (nur für Kindprozesse, nie im Stack)."""
    kurs = appdaten.laden()["kursdaten"]
    anbieter = kurs.get("anbieter", "keiner")
    key = appdaten.geheimnis(f"kurs_key_{anbieter}") if anbieter != "keiner" else None
    return {"STOCKMASTER_KURSANBIETER": anbieter, "STOCKMASTER_KURSANBIETER_KEY": key} if key else {}


def befehl(prompt_text: str, modell: str, aufwand: str, json_ausgabe: bool = False, nur_test: bool = False) -> list[str]:
    e = einstellungen()
    argumente = ["claude", "-p", prompt_text, *claude_optionen.cli_argumente(modell, aufwand),
                 "--no-session-persistence", "--permission-prompts", "none"]
    if nur_test:
        return argumente + ["--output-format", "json", "--max-turns", "1", "--tools", ""]
    return argumente + ["--output-format", "stream-json", "--verbose", "--permission-mode", "acceptEdits",
                        "--add-dir", str(e.daten_pfad), "--settings", einstellungen_json(),
                        "--allowedTools", *ERLAUBTE_WERKZEUGE]


def fehler_einordnen(text: str) -> tuple[str, str]:
    """(status, Klartext) für einen abgebrochenen Lauf."""
    if LIMIT_MUSTER.search(text):
        return "limit", ("Das Nutzungskontingent des Claude-Abos ist erschöpft. Der Lauf wurde sauber beendet; "
                         "nach dem Zurücksetzen des Kontingents erneut starten.")
    if AUTH_MUSTER.search(text):
        return "fehler", ("Anmeldung bei Claude abgelehnt: Token ungültig oder abgelaufen. Mit `claude setup-token` "
                          "ein neues Token erzeugen und in der Einrichtung eintragen.")
    if MODELL_MUSTER.search(text):
        return "fehler", f"Modell oder Aufwand wird nicht unterstützt: {text.strip()[:300]}"
    return "fehler", f"Claude-Lauf fehlgeschlagen: {text.strip()[:300] or 'ohne Meldung'}"


def _kurz(wert, laenge: int = 160) -> str:
    text = wert if isinstance(wert, str) else json.dumps(wert, ensure_ascii=False)
    text = " ".join(text.split())
    return text if len(text) <= laenge else text[: laenge - 1] + "…"


def ereignis_text(ereignis: dict) -> list[str]:
    """Lesbare Logzeilen aus einem stream-json-Ereignis."""
    art = ereignis.get("type")
    zeilen = []
    if art == "system" and ereignis.get("subtype") == "init":
        zeilen.append(f"Start: Modell {ereignis.get('model', '?')}, Claude Code {ereignis.get('claude_code_version', '')}"
                      .strip())
    elif art == "assistant":
        for teil in ereignis.get("message", {}).get("content", []):
            if teil.get("type") == "text" and teil.get("text", "").strip():
                zeilen.append(f"Claude: {teil['text'].strip()}")
            elif teil.get("type") == "tool_use":
                eingabe = teil.get("input", {})
                kern = eingabe.get("command") or eingabe.get("file_path") or eingabe.get("query") or eingabe.get("url") \
                    or eingabe.get("pattern") or eingabe
                zeilen.append(f"→ {teil.get('name')}: {_kurz(kern)}")
    elif art == "user":
        for teil in ereignis.get("message", {}).get("content", []):
            if isinstance(teil, dict) and teil.get("type") == "tool_result":
                inhalt = teil.get("content")
                if isinstance(inhalt, list):
                    inhalt = " ".join(t.get("text", "") for t in inhalt if isinstance(t, dict))
                zeilen.append(f"  {'✗' if teil.get('is_error') else '←'} {_kurz(inhalt or '', 300)}")
    elif art == "result":
        # Das Ergebnis vollständig und mit Zeilenumbrüchen (Markdown, Tabellen); nur gegen Ausreißer begrenzt.
        ergebnis = str(ereignis.get("result", ""))
        if len(ergebnis) > ERGEBNIS_MAX:
            ergebnis = ergebnis[:ERGEBNIS_MAX] + "\n[… gekürzt]"
        zeilen.append(f"Ende ({ereignis.get('subtype')}, {ereignis.get('num_turns', '?')} Schritte, "
                      f"{int(ereignis.get('duration_ms', 0) / 1000)} s):")
        zeilen.extend(ergebnis.splitlines() or [""])
    return zeilen


def ausfuehren(befehl_liste: list[str], env: dict, cwd: Path, log: Path, schwaerzen: Schwaerzer,
               abbrechen: Callable[[], bool], zeitlimit_s: int, starter=subprocess.Popen) -> dict:
    """Startet den Lauf, schreibt das Log live (geschwärzt) und liefert das Ergebnis."""
    log.parent.mkdir(parents=True, exist_ok=True)
    ergebnis: dict = {"result": None, "is_error": None}
    beginn = time.monotonic()
    with open(log, "a", encoding="utf-8") as ausgabe:
        def schreiben(zeile: str) -> None:
            ausgabe.write(schwaerzen(zeile) + "\n")
            ausgabe.flush()

        prozess = starter(befehl_liste, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, bufsize=1)
        abgebrochen = None
        for roh in prozess.stdout:
            roh = roh.rstrip("\n")
            try:
                ereignis = json.loads(roh)
            except ValueError:
                if roh.strip():
                    schreiben(roh)
                    ergebnis.setdefault("ausgabe", "")
                    ergebnis["ausgabe"] = (ergebnis["ausgabe"] + "\n" + roh)[-2000:]
                ereignis = None
            if ereignis:
                for zeile in ereignis_text(ereignis):
                    schreiben(zeile)
                if ereignis.get("type") == "result":
                    ergebnis.update({k: ereignis.get(k) for k in ("result", "is_error", "subtype", "num_turns",
                                                                   "duration_ms", "total_cost_usd")})
            if abbrechen():
                abgebrochen = "abgebrochen"
            elif time.monotonic() - beginn > zeitlimit_s:
                abgebrochen = "zeitlimit"
            if abgebrochen:
                prozess.terminate()
                try:
                    prozess.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    prozess.kill()
                schreiben("Lauf abgebrochen (Benutzer)." if abgebrochen == "abgebrochen"
                          else f"Lauf nach {zeitlimit_s // 60} Minuten abgebrochen (Zeitlimit).")
                break
        rueckgabe = prozess.wait()
        prozess.stdout.close()
    ergebnis["rueckgabe"] = rueckgabe
    ergebnis["abgebrochen"] = abgebrochen
    for schluessel in ("result", "ausgabe"):
        if isinstance(ergebnis.get(schluessel), str):
            ergebnis[schluessel] = schwaerzen(ergebnis[schluessel])
    return ergebnis


class TempVerzeichnis:
    """Eigenes HOME und CLAUDE_CONFIG_DIR je Lauf, danach gelöscht (Transkripte bleiben nicht liegen)."""

    def __enter__(self) -> Path:
        self.pfad = Path(tempfile.mkdtemp(prefix="claude-lauf-"))
        (self.pfad / "home").mkdir()
        (self.pfad / "claude").mkdir()
        return self.pfad

    def __exit__(self, *_):
        shutil.rmtree(self.pfad, ignore_errors=True)


def verbindung_testen(token: str, modell: str, aufwand: str, starter=subprocess.run) -> dict:
    """Kurzer Testaufruf (eine Runde, keine Werkzeuge). Ergebnis im Klartext, ohne Secrets."""
    schwaerzen = Schwaerzer([token])
    with TempVerzeichnis() as temp:
        env = umgebung(token, temp)
        env.pop("STOCKMASTER_KURSANBIETER_KEY", None)
        beginn = time.monotonic()
        try:
            lauf = starter(befehl("Antworte nur mit dem Wort OK.", modell, aufwand, nur_test=True), cwd=temp, env=env,
                           capture_output=True, text=True, timeout=120)
        except FileNotFoundError:
            return {"ok": False, "meldung": "Claude Code CLI ist im Container nicht installiert (Befehl 'claude')."}
        except subprocess.TimeoutExpired:
            return {"ok": False, "meldung": "Keine Antwort von Claude innerhalb von 120 Sekunden."}
    dauer = round(time.monotonic() - beginn, 1)
    try:
        daten = json.loads(lauf.stdout.strip().splitlines()[-1]) if lauf.stdout.strip() else {}
    except ValueError:
        daten = {}
    text = schwaerzen(str(daten.get("result") or lauf.stderr or lauf.stdout or ""))
    if lauf.returncode == 0 and not daten.get("is_error"):
        return {"ok": True, "meldung": f"Verbindung in Ordnung ({modell}, Aufwand {aufwand or 'Standard'}, {dauer} s).",
                "antwort": text[:80]}
    status, meldung = fehler_einordnen(text)
    return {"ok": False, "meldung": meldung, "limit": status == "limit"}
