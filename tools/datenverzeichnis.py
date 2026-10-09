#!/usr/bin/env python3
"""Datenverzeichnis (Spielstand) einrichten, lokal committen und prüfen.

Das Datenverzeichnis ist ein eigenes Git-Repository ohne Remote. Werkzeuge und
Sessions committen dort; gepusht wird nie.

    python tools/datenverzeichnis.py einrichten [--ziel <pfad>]
    python tools/datenverzeichnis.py commit -m "session: ..."
    python tools/datenverzeichnis.py status
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pfade
from pfade import Fehler

VORLAGE = ("vorlagen", "datenverzeichnis")
PRAEFIXE = ("aufbau:", "session:", "review:", "fix:", "daten:")
# Neutrale Identität für lokale Commits (keine Namen oder E-Mail-Adressen, CLAUDE.md Grundsatz 5).
GIT_NAME = "StockMaster"
GIT_EMAIL = "stockmaster@localhost.invalid"
IGNORIEREN = {"lost+found"}


def git(ziel: Path, *argumente: str, pruefen: bool = True) -> subprocess.CompletedProcess:
    ergebnis = subprocess.run(["git", "-c", f"safe.directory={ziel}", *argumente], cwd=ziel,
                              capture_output=True, text=True)
    if pruefen and ergebnis.returncode != 0:
        raise Fehler(f"git {' '.join(argumente)} fehlgeschlagen: {(ergebnis.stderr or ergebnis.stdout).strip()}")
    return ergebnis


def ist_leer(ziel: Path) -> bool:
    return not ziel.exists() or not any(p.name not in IGNORIEREN for p in ziel.iterdir())


def ist_eingerichtet(ziel: Path) -> bool:
    return (ziel / ".git").exists() and git(ziel, "rev-parse", "--verify", "HEAD", pruefen=False).returncode == 0


def git_vorbereiten(ziel: Path) -> None:
    """Lokales Repository ohne Remote mit neutraler Identität."""
    if not (ziel / ".git").exists():
        git(ziel, "init", "-q", "-b", "main")
    for schluessel, wert in (("user.name", GIT_NAME), ("user.email", GIT_EMAIL), ("commit.gpgsign", "false"),
                             ("core.fileMode", "false")):
        git(ziel, "config", schluessel, wert)
    for remote in git(ziel, "remote").stdout.split():
        git(ziel, "remote", "remove", remote)


def framework_version() -> str:
    version = os.environ.get("SM_VERSION")
    if version:
        return version
    ergebnis = subprocess.run(["git", "-C", str(pfade.framework()), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True)
    return ergebnis.stdout.strip() if ergebnis.returncode == 0 and ergebnis.stdout.strip() else "unbekannt"


def einrichten(ziel: Path | None = None) -> list[str]:
    """Legt das Datenverzeichnis aus der Vorlage an (nur wenn es leer ist)."""
    ziel = Path(ziel) if ziel else pfade.daten()
    if ist_eingerichtet(ziel):
        git_vorbereiten(ziel)
        return [f"Datenverzeichnis {ziel} ist bereits eingerichtet."]
    if not ist_leer(ziel):
        raise Fehler(f"{ziel} ist nicht leer und kein Spielstand-Repository. Vorhandenen Spielstand mit "
                     "python tools/migriere.py --von <alte-arbeitskopie> übernehmen oder ein leeres Verzeichnis wählen.")
    ziel.mkdir(parents=True, exist_ok=True)
    vorlage = pfade.framework_pfad(*VORLAGE)
    for eintrag in vorlage.iterdir():
        if eintrag.is_dir():
            shutil.copytree(eintrag, ziel / eintrag.name, dirs_exist_ok=True)
        else:
            shutil.copy2(eintrag, ziel / eintrag.name)
    git_vorbereiten(ziel)
    git(ziel, "add", "-A")
    git(ziel, "commit", "-q", "-m", f"aufbau: Datenverzeichnis aus Vorlage angelegt (Framework {framework_version()})")
    return [f"Datenverzeichnis {ziel} aus der Vorlage angelegt und lokal committet."]


def ignore_ergaenzen(ziel: Path) -> bool:
    """Trägt Sperrdateien neuerer Werkzeug-Versionen in die .gitignore bestehender Datenverzeichnisse nach.

    Idempotent; ältere Instanzen (ohne `.buchungssperre`) bekommen die Zeile beim nächsten Commit, bevor die Sperrdatei
    versehentlich in die Prüfspur gelangt. Bestehende Zeilen bleiben unverändert.
    """
    datei = ziel / ".gitignore"
    text = datei.read_text(encoding="utf-8") if datei.exists() else ""
    fehlend = [z for z in pfade.NICHT_VERSIONIERT if z not in {x.strip().rstrip("/") for x in text.splitlines()}]
    if not fehlend:
        return False
    zusatz = ("" if text.endswith("\n") or not text else "\n") + "\n".join(
        f"{z}/" if z == ".cache" else z for z in fehlend) + "\n"
    datei.write_text(text + zusatz, encoding="utf-8")
    return True


def commit(nachricht: str, ziel: Path | None = None) -> str:
    """Committet alle Änderungen im Datenverzeichnis lokal. Gibt den Commit oder '' (nichts zu tun) zurück."""
    ziel = Path(ziel) if ziel else pfade.daten()
    if not nachricht.startswith(PRAEFIXE):
        raise Fehler(f"Commit-Nachricht braucht ein Präfix ({', '.join(PRAEFIXE)}).")
    if not ist_eingerichtet(ziel):
        raise Fehler(f"{ziel} ist kein eingerichtetes Datenverzeichnis (python tools/datenverzeichnis.py einrichten).")
    ignore_ergaenzen(ziel)
    git(ziel, "add", "-A")
    if not git(ziel, "status", "--porcelain").stdout.strip():
        return ""
    git(ziel, "commit", "-q", "-m", nachricht)
    return git(ziel, "rev-parse", "--short", "HEAD").stdout.strip()


def status(ziel: Path | None = None) -> dict:
    ziel = Path(ziel) if ziel else pfade.daten()
    ergebnis = {"pfad": str(ziel), "vorhanden": ziel.exists(), "git": False, "commits": 0, "letzter_commit": None,
                "offene_aenderungen": 0, "remotes": [], "beschreibbar": ziel.exists() and os.access(ziel, os.W_OK)}
    if not ist_eingerichtet(ziel):
        return ergebnis
    kopf = git(ziel, "log", "-1", "--format=%h%x1f%aI%x1f%s").stdout.strip().split("\x1f")
    ergebnis.update({
        "git": True,
        "commits": int(git(ziel, "rev-list", "--count", "HEAD").stdout.strip() or 0),
        "letzter_commit": {"hash": kopf[0], "zeit": kopf[1], "text": kopf[2]} if len(kopf) == 3 else None,
        "offene_aenderungen": len([z for z in git(ziel, "status", "--porcelain").stdout.splitlines() if z.strip()]),
        "remotes": git(ziel, "remote").stdout.split(),
    })
    return ergebnis


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Datenverzeichnis (Spielstand, lokales Git ohne Remote).")
    unter = parser.add_subparsers(dest="befehl", required=True)
    p = unter.add_parser("einrichten", help="aus vorlagen/datenverzeichnis anlegen (nur wenn leer)")
    p.add_argument("--ziel", help="Pfad (Standard: STOCKMASTER_DATA_DIR)")
    p = unter.add_parser("commit", help="alle Änderungen lokal committen (nie pushen)")
    p.add_argument("-m", "--nachricht", required=True)
    unter.add_parser("status", help="Zustand des Datenverzeichnisses als JSON")
    args = parser.parse_args(argv)
    try:
        if args.befehl == "einrichten":
            for meldung in einrichten(Path(args.ziel) if args.ziel else None):
                print(meldung)
        elif args.befehl == "commit":
            hash_wert = commit(args.nachricht)
            print(f"Lokal committet: {hash_wert}" if hash_wert else "Keine Änderungen zu committen.")
        else:
            print(json.dumps(status(), ensure_ascii=False, indent=2))
    except Fehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
