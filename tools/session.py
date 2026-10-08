#!/usr/bin/env python3
"""Session-Sperre (regeln.md Abschnitt 12): nie mehr als eine Session gleichzeitig.

`start --person <kennung> [--art testsession]` legt session.lock im Datenverzeichnis
an und committet sie im lokalen Spielstand-Git (ohne Remote, es wird nie gepusht).
Eine Testsession (AP12) schreibt weder Journal noch Orders; für sie entfällt die
Warnung "kein Session-Eintrag". `ende` entfernt die Sperre und committet das. Eine fremde Sperre jünger als
6 Stunden bricht ab; ältere gelten als verwaist und werden übernommen.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

import gemeinsam as g
import termine
from gemeinsam import Fehler

SPERRDATEI = "session.lock"


def _git(*argumente) -> subprocess.CompletedProcess:
    """Git im Datenverzeichnis (lokales Spielstand-Repository)."""
    return subprocess.run(["git", "-c", f"safe.directory={g.root()}", *argumente], cwd=g.root(),
                          capture_output=True, text=True)


def _eigenes_git() -> None:
    """Nie in ein übergeordnetes Repository (z. B. das Framework) committen."""
    if not (g.root() / ".git").exists():
        raise Fehler(f"Das Datenverzeichnis {g.root()} ist kein eigenes Git-Repository "
                     "(python tools/datenverzeichnis.py einrichten).")


def _git_pflicht(*argumente) -> None:
    ergebnis = _git(*argumente)
    if ergebnis.returncode != 0:
        raise Fehler(f"git {' '.join(argumente)} fehlgeschlagen: {ergebnis.stderr.strip() or ergebnis.stdout.strip()}")


def person_pruefen(name: str) -> str:
    person = name.strip().lower()
    erlaubt = g.projekt()["auftraggeber"]
    if person not in erlaubt:
        raise Fehler(f"'{name}' ist kein Auftraggeber ({', '.join(erlaubt)}).")
    return person


ARTEN = ("trading", "testsession", "richtlinien", "review", "nachbuchung")
# Diese Arten schreiben keine Orders und keine Session-Einträge: keine Warnung zum fehlenden Session-Eintrag.
# nachbuchung: der Hintergrunddienst bucht nachts alle Tage bis gestern nach (bewertung.py braucht dafür eine Sperre).
OHNE_SESSION_EINTRAG = ("testsession", "richtlinien", "review", "nachbuchung")


def starten(name: str, git: bool = True, art: str = "trading") -> list[str]:
    person = person_pruefen(name)
    if art not in ARTEN:
        raise Fehler(f"Unbekannte Art '{art}'. Erlaubt: {', '.join(ARTEN)}.")
    meldungen = []
    sperre = g.sperre_lesen()
    if sperre is not None:
        verwaist = g.sperre_verwaist(sperre)
        if sperre["person"] == person and not verwaist:
            return [f"Eigene Sperre von {person} besteht seit {sperre['start']}; Session läuft weiter."]
        if sperre["person"] != person and not verwaist:
            raise Fehler(f"Session von {sperre['person']} läuft seit {sperre['start']} "
                         f"(Sperre noch nicht verwaist). Abbruch: bitte mit {sperre['person']} klären.")
        meldungen.append(f"WARNUNG: verwaiste Sperre von {sperre['person']} seit {sperre['start']} "
                         "wird übernommen.")
    g.json_schreiben(g.sperre_pfad(), {"person": person, "start": g.iso(g.jetzt()), "art": art})
    if git:
        nachricht = f"session: Start {person}"
        try:
            _eigenes_git()
            _git_pflicht("add", SPERRDATEI)
            _git_pflicht("commit", "-q", "-m", nachricht, "--", SPERRDATEI)
        except Fehler:
            g.sperre_pfad().unlink(missing_ok=True)
            raise
        meldungen.append("Sperre im lokalen Spielstand-Git committet.")
    bezeichnung = {"testsession": "Testsession", "richtlinien": "Richtlinien-Session",
                   "review": "Review-Session", "nachbuchung": "Nachbuchung"}.get(art, "Session")
    meldungen.insert(0, f"{bezeichnung} von {person} gestartet ({g.iso(g.jetzt())}).")
    return meldungen + [m for m in termine.meldungen() if m.startswith("FÄLLIG")]


def beenden(git: bool = True) -> list[str]:
    sperre = g.sperre_lesen()
    if sperre is None:
        return ["Keine Sperre vorhanden."]
    hinweise = [] if sperre.get("art") in OHNE_SESSION_EINTRAG else session_eintrag_hinweis(sperre)
    if git and (g.root() / ".git").exists() and _git("ls-files", "--error-unmatch", SPERRDATEI).returncode == 0:
        _git_pflicht("rm", "-q", SPERRDATEI)
        _git_pflicht("commit", "-q", "-m", f"session: Ende {sperre['person']}", "--", SPERRDATEI)
        return hinweise + [f"Sperre von {sperre['person']} entfernt und im lokalen Spielstand-Git committet."]
    g.sperre_pfad().unlink()
    return hinweise + [f"Sperre von {sperre['person']} entfernt."]


def session_eintrag_hinweis(sperre: dict) -> list[str]:
    """Warnt, wenn die Session ohne Session-Eintrag (S-...) endet (regeln.md 10)."""
    beginn = sperre["start_dt"]
    eintraege = [e for e in g.session_eintraege()
                 if e["person"] == sperre["person"] and e["zeit"] and e["zeit"] >= beginn.replace(second=0)]
    if eintraege:
        return []
    return [f"WARNUNG: kein Session-Eintrag (S-...) seit Sessionbeginn {sperre['start']} in "
            f"journal/*_{sperre['person']}.md. Bitte vor dem Ende anhängen (CLAUDE.md, Session-Vorlage)."]


def status() -> list[str]:
    sperre = g.sperre_lesen()
    spiel = g.spiel_lesen()
    start = (f"Spiel gestartet am {spiel['startdatum']}." if spiel.get("startdatum")
             else "Spiel noch nicht gestartet (Startdatum fehlt).")
    if sperre is None:
        return [start, "Keine Session aktiv."] + [m for m in termine.meldungen() if m.startswith("FÄLLIG")]
    zusatz = " (VERWAIST)" if g.sperre_verwaist(sperre) else ""
    art = {"testsession": " (Testsession)", "richtlinien": " (Richtlinien-Session)",
           "review": " (Review-Session)", "nachbuchung": " (automatische Nachbuchung)"}.get(sperre.get("art"), "")
    return [start, f"Session von {sperre['person']} seit {sperre['start']}{zusatz}{art}."] + \
        [m for m in termine.meldungen() if m.startswith("FÄLLIG")]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Session-Sperre setzen, prüfen und entfernen.")
    unter = parser.add_subparsers(dest="befehl", required=True)
    p = unter.add_parser("start", help="Session starten (Sperre anlegen und lokal committen)")
    p.add_argument("--person", required=True, help="Kennung des Auftraggebers aus config/projekt.json")
    p.add_argument("--art", choices=ARTEN, default="trading",
                   help="testsession: Probelauf ohne Orders und Journal (AP12); richtlinien: Anlagerichtlinien "
                        "ausformulieren (AP12 Punkt 2); review: nur Reviews und Bericht; nachbuchung: nächtliche "
                        "Nachbuchung des Hintergrunddienstes; alle ohne Warnung zum Session-Eintrag")
    p.add_argument("--ohne-git", action="store_true", help="nur die Datei anlegen (für Tests)")
    p = unter.add_parser("ende", help="Session beenden (Sperre entfernen und committen)")
    p.add_argument("--ohne-git", action="store_true", help="nur die Datei entfernen (für Tests)")
    unter.add_parser("status", help="Zeigt die aktuelle Sperre")
    args = parser.parse_args(argv)
    try:
        if args.befehl == "start":
            meldungen = starten(args.person, git=not args.ohne_git, art=args.art)
        elif args.befehl == "ende":
            meldungen = beenden(git=not args.ohne_git)
        else:
            meldungen = status()
        for meldung in meldungen:
            print(meldung)
    except Fehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
