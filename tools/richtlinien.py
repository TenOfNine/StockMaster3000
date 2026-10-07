#!/usr/bin/env python3
"""Anlagerichtlinien (regeln.md Abschnitt 11, AP12 Punkt 2): Stand und Vorlage.

    python tools/richtlinien.py status            welche strategie/<profil>.md sind noch offen (JSON)
    python tools/richtlinien.py vorlage --profil  Vorlage mit den verbindlichen Limits aus config/profile.json
    python tools/richtlinien.py standard          Standard-Anlagerichtlinien (config/richtlinien/) übernehmen,
                                                  wo strategie/<profil>.md noch fehlt oder die Vorlage ist

Die Limits stehen in der Vorlage, weil sie aus config/profile.json kommen (Rechnen macht Code).
Die Standard-Anlagerichtlinien (config/richtlinien/<profil>.md) sind ausformuliert und gelten ab
Spielstart; Claude prüft sie und ändert sie nur mit Datum, Anlass und Prüfkriterium (regeln.md 11).
Eine bereits ausformulierte Richtlinie überschreibt `standard` nie.
"""

from __future__ import annotations

import argparse
import json
import sys

import gemeinsam as g
import init
from gemeinsam import Fehler


def status() -> dict:
    spiel = g.spiel_lesen()
    return {"startdatum": spiel.get("startdatum"),
            "profile": {p: {"vorhanden": g.richtlinie_pfad(p).exists(), "ausformuliert": g.richtlinie_ausformuliert(p)}
                        for p in g.PROFILE},
            "offen": g.richtlinien_offen()}


def vorlage_text(profil: str) -> str:
    if profil not in g.PROFILE:
        raise Fehler(f"Unbekanntes Profil '{profil}'. Erlaubt: {', '.join(g.PROFILE)}.")
    return init.vorlage(profil, g.heute())


def standard_uebernehmen() -> list[str]:
    """Übernimmt die Standard-Richtlinie für alle Profile, die fehlen oder noch die Vorlage sind."""
    meldungen = []
    for profil in g.richtlinien_offen():
        g.atomar_schreiben(g.richtlinie_pfad(profil), init.standard_text(profil, g.heute()))
        meldungen.append(f"strategie/{profil}.md aus der Standard-Anlagerichtlinie übernommen.")
    return meldungen or ["Alle Anlagerichtlinien sind bereits ausformuliert; nichts geändert."]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Anlagerichtlinien: Stand und Vorlage.")
    unter = parser.add_subparsers(dest="befehl", required=True)
    unter.add_parser("status", help="offene Richtlinien als JSON")
    unter.add_parser("standard", help="Standard-Anlagerichtlinien übernehmen (nur wo noch die Vorlage steht)")
    p = unter.add_parser("vorlage", help="Vorlage mit den verbindlichen Limits ausgeben")
    p.add_argument("--profil", required=True, choices=g.PROFILE)
    args = parser.parse_args(argv)
    try:
        if args.befehl == "status":
            print(json.dumps(status(), ensure_ascii=False, indent=2))
        elif args.befehl == "standard":
            print("\n".join(standard_uebernehmen()))
        else:
            print(vorlage_text(args.profil))
    except Fehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
