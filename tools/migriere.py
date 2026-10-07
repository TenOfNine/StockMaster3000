#!/usr/bin/env python3
"""Einmalige Migration: Spielstand aus dem alten Layout (Spielstand im Repository) übernehmen.

    python tools/migriere.py --von <pfad-alte-arbeitskopie> [--ziel <datenverzeichnis>]

Kopiert portfolios/, trades/, data/, journal/, reviews/, strategie/, news/,
lessons.md, ranking.md und session.lock aus der alten Arbeitskopie ins
Datenverzeichnis. Das Startdatum stand früher in STATUS.md und wird nach
spiel.json übernommen. Der erste Commit im Datenverzeichnis trägt einen
Herkunftsvermerk (Quellverzeichnis, Commit der alten Arbeitskopie). Die alte
Arbeitskopie wird nicht verändert; ihre Git-Historie bleibt die Prüfspur für
die Zeit vor der Migration.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import datenverzeichnis as dv
import pfade
from pfade import Fehler

TZ = ZoneInfo("Europe/Berlin")


def _git_kopf(quelle: Path) -> str | None:
    ergebnis = subprocess.run(["git", "-c", f"safe.directory={quelle}", "-C", str(quelle), "log", "-1",
                               "--format=%H %aI"], capture_output=True, text=True)
    return ergebnis.stdout.strip() if ergebnis.returncode == 0 and ergebnis.stdout.strip() else None


def _hat_spielstand(ziel: Path) -> bool:
    """Echter Spielstand: Portfolios oder Journal-Dateien (nicht nur die leere Vorlage)."""
    return any((ziel / "portfolios").glob("*.json")) or any((ziel / "journal").glob("*.md")) or \
        (ziel / "spiel.json").exists()


def _startdatum_aus_status(quelle: Path) -> str | None:
    datei = quelle / "STATUS.md"
    if not datei.exists():
        return None
    treffer = re.search(r"^- Startdatum des Spiels:\s*(\d{4}-\d{2}-\d{2})", datei.read_text(encoding="utf-8"), re.M)
    return treffer.group(1) if treffer else None


def _startdatum_aus_portfolios(quelle: Path) -> str | None:
    for datei in sorted((quelle / "portfolios").glob("*.json")):
        wert = json.loads(datei.read_text(encoding="utf-8")).get("startdatum")
        if wert:
            return wert
    return None


def migrieren(quelle: Path, ziel: Path | None = None) -> list[str]:
    quelle = Path(quelle).resolve()
    ziel = Path(ziel).resolve() if ziel else pfade.daten()
    if not quelle.is_dir():
        raise Fehler(f"Quelle {quelle} ist kein Verzeichnis.")
    if quelle == ziel:
        raise Fehler("Quelle und Ziel sind gleich.")
    if ziel.exists() and dv.ist_eingerichtet(ziel) and _hat_spielstand(ziel):
        raise Fehler(f"{ziel} enthält bereits Spielstand. Migration nur in ein leeres oder frisch aus der Vorlage "
                     "angelegtes Datenverzeichnis.")
    if not dv.ist_eingerichtet(ziel):
        dv.einrichten(ziel)

    meldungen = []
    for name in pfade.SPIELSTAND:
        if name == "spiel.json":
            continue
        herkunft = quelle / name
        if not herkunft.exists():
            continue
        if herkunft.is_dir():
            shutil.copytree(herkunft, ziel / name, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__", "*.tmp", ".*.tmp"))
        else:
            shutil.copy2(herkunft, ziel / name)
        meldungen.append(f"übernommen: {name}")

    startdatum = _startdatum_aus_status(quelle) or _startdatum_aus_portfolios(quelle)
    if (quelle / "spiel.json").exists():
        shutil.copy2(quelle / "spiel.json", ziel / "spiel.json")
    elif startdatum:
        (ziel / "spiel.json").write_text(json.dumps({
            "startdatum": startdatum, "initialisiert": None, "freigabe_ap12": None,
            "werkzeug": "tools/migriere.py (Startdatum aus STATUS.md bzw. portfolios/)",
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        meldungen.append(f"Startdatum {startdatum} nach spiel.json übernommen.")

    kopf = _git_kopf(quelle)
    zeit = datetime.now(TZ).replace(microsecond=0).isoformat()
    nachricht = (f"aufbau: Spielstand aus alter Arbeitskopie übernommen\n\n"
                 f"Herkunft: Verzeichnis '{quelle.name}', Commit {kopf or 'unbekannt (kein Git)'}\n"
                 f"Migriert am {zeit} mit tools/migriere.py. Die Prüfspur vor diesem Commit liegt in der "
                 f"Git-Historie der alten Arbeitskopie.")
    hash_wert = dv.commit(nachricht, ziel)
    meldungen.append(f"Lokal committet: {hash_wert}" if hash_wert else "Kein Spielstand gefunden; nichts zu committen.")
    meldungen.append("Danach prüfen: python tools/pruefe.py")
    return meldungen


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Spielstand aus dem alten Repository-Layout übernehmen (einmalig).")
    parser.add_argument("--von", required=True, help="Pfad der alten Arbeitskopie (Spielstand im Repository)")
    parser.add_argument("--ziel", help="Datenverzeichnis (Standard: STOCKMASTER_DATA_DIR)")
    args = parser.parse_args(argv)
    try:
        for meldung in migrieren(Path(args.von), Path(args.ziel) if args.ziel else None):
            print(meldung)
    except Fehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
