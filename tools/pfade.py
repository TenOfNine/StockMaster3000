"""Zentrale Pfadauflösung: Framework und Datenverzeichnis sind getrennt.

- Framework: Code, regeln.md, config/, CLAUDE.md, STATUS.md, Vorlagen. Kommt aus dem
  Git-Repository bzw. dem Image und wird von den Werkzeugen nur gelesen.
- Datenverzeichnis (STOCKMASTER_DATA_DIR, im Container /data): der gesamte Spielstand
  (portfolios/, trades/, data/, journal/, reviews/, strategie/, news/, lessons.md,
  ranking.md, session.lock, spiel.json). Es ist ein eigenes Git-Repository ohne Remote.

Spielstand wird nie relativ zum Framework gelesen oder geschrieben.
"""

from __future__ import annotations

import os
from pathlib import Path

DATEN_VARIABLE = "STOCKMASTER_DATA_DIR"
FRAMEWORK_VARIABLE = "STOCKMASTER_FRAMEWORK_DIR"

# Alles, was im Spiel entsteht (Reihenfolge = Anzeige in Migration und Export).
SPIELSTAND = ("portfolios", "trades", "data", "journal", "reviews", "strategie", "news",
              "lessons.md", "ranking.md", "session.lock", "spiel.json")
# Nicht versioniert, nicht exportiert: Zwischenspeicher und Sperrdatei.
NICHT_VERSIONIERT = (".cache", ".schreibsperre")


class Fehler(Exception):
    """Fachlicher Fehler mit verständlicher deutscher Meldung."""


def framework() -> Path:
    """Wurzel des Frameworks (Standard: Verzeichnis über tools/)."""
    wert = os.environ.get(FRAMEWORK_VARIABLE)
    return Path(wert).resolve() if wert else Path(__file__).resolve().parent.parent


def daten() -> Path:
    """Datenverzeichnis mit dem Spielstand (Pflicht: STOCKMASTER_DATA_DIR)."""
    wert = os.environ.get(DATEN_VARIABLE)
    if not wert:
        raise Fehler(f"{DATEN_VARIABLE} ist nicht gesetzt. Der Spielstand liegt in einem eigenen Datenverzeichnis "
                     "(im Container /data). Lokal anlegen mit: python tools/datenverzeichnis.py einrichten "
                     "--ziel <pfad>; danach export STOCKMASTER_DATA_DIR=<pfad>.")
    pfad = Path(wert).resolve()
    if pfad == framework():
        raise Fehler(f"{DATEN_VARIABLE} zeigt auf das Framework ({pfad}). Spielstand gehört in ein eigenes "
                     "Verzeichnis außerhalb des Repositorys.")
    return pfad


def framework_pfad(*teile: str) -> Path:
    return framework().joinpath(*teile)


def daten_pfad(*teile: str) -> Path:
    return daten().joinpath(*teile)


def cache_pfad(*teile: str) -> Path:
    """Zwischenspeicher im Datenverzeichnis (nicht versioniert, nicht im Export)."""
    return daten().joinpath(".cache", *teile)
