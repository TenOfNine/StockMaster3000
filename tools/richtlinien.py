#!/usr/bin/env python3
"""Anlagerichtlinien (regeln.md Abschnitt 11, AP12 Punkt 2): Stand und Vorlage.

    python tools/richtlinien.py status            welche strategie/<profil>.md sind noch offen (JSON)
    python tools/richtlinien.py vorlage --profil  Vorlage mit den verbindlichen Limits aus config/profile.json
    python tools/richtlinien.py standard          Standard-Anlagerichtlinien (config/richtlinien/) übernehmen,
                                                  wo strategie/<profil>.md noch fehlt oder die Vorlage ist, und
                                                  unveränderte ältere Standard-Versionen aktualisieren

Die Limits stehen in der Vorlage, weil sie aus config/profile.json kommen (Rechnen macht Code).
Die Standard-Anlagerichtlinien (config/richtlinien/<profil>.md) sind ausformuliert und gelten ab
Spielstart; Claude prüft sie und ändert sie nur mit Datum, Anlass und Prüfkriterium (regeln.md 11).
Eine angepasste Richtlinie überschreibt `standard` nie; nur eine unveränderte Standard-Richtlinie einer älteren
Version wird aktualisiert (die bisherige Historie bleibt, dazu kommt ein Eintrag "Standard-Update").
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
                        for p in g.profile()},
            "offen": g.richtlinien_offen(), "veraltet": g.richtlinien_veraltet(),
            "standard_version": g.RICHTLINIE_STANDARD_VERSION}


def vorlage_text(profil: str) -> str:
    if profil not in g.profile():
        raise Fehler(f"Unbekanntes Profil '{profil}'. Erlaubt: {', '.join(g.profile())}.")
    return init.vorlage(profil, g.heute())


def _aktualisiert(profil: str) -> str:
    """Neuer Text einer unveränderten Standard-Richtlinie: neue Fassung, bisherige Historie plus Eintrag."""
    alt_version = g.richtlinie_standard_version(profil) or 1
    historie = g.richtlinie_historie(profil)
    neu = init.standard_text(profil, g.heute())
    zeilen = neu.splitlines()
    kopf = next(i for i, z in enumerate(zeilen) if z.startswith("| --- "))
    zeilen = zeilen[: kopf + 1] + ["| " + " | ".join(z) + " |" for z in historie] + [
        f"| {g.heute().isoformat()} | Standard-Update | Standard-Richtlinie v{alt_version} → "
        f"v{g.RICHTLINIE_STANDARD_VERSION}: Handeln ist der Normalfall, Cash die Ausnahme (regeln.md v1.4) "
        "| Quartals-Review: Cashquote nahe der Mindestquote, Ausnahmen belegt |"]
    return "\n".join(zeilen) + "\n"


def standard_uebernehmen() -> list[str]:
    """Übernimmt die Standard-Richtlinie für fehlende oder noch leere Profile und aktualisiert unveränderte ältere.

    Eine angepasste Richtlinie bleibt unberührt; ist sie älter als die Standardversion, nennt die Meldung das.
    """
    meldungen = []
    for profil in g.richtlinien_offen():
        g.atomar_schreiben(g.richtlinie_pfad(profil), init.standard_text(profil, g.heute()))
        meldungen.append(f"strategie/{profil}.md aus der Standard-Anlagerichtlinie übernommen.")
    for profil in g.richtlinien_veraltet():
        g.atomar_schreiben(g.richtlinie_pfad(profil), _aktualisiert(profil))
        meldungen.append(f"strategie/{profil}.md auf Standard-Richtlinie v{g.RICHTLINIE_STANDARD_VERSION} aktualisiert "
                         "(bisherige Historie bleibt).")
    for profil in g.profile():
        version = g.richtlinie_standard_version(profil)
        if (g.richtlinie_ausformuliert(profil) and version is not None and not g.richtlinie_unveraendert(profil)
                and version < g.RICHTLINIE_STANDARD_VERSION):
            meldungen.append(f"Hinweis: strategie/{profil}.md ist angepasst und älter als Standard-Richtlinie "
                             f"v{g.RICHTLINIE_STANDARD_VERSION}; Änderungen (Handeln als Normalfall) in einer "
                             "Richtlinien-Session mit Datum, Anlass und Prüfkriterium übernehmen.")
    return meldungen or ["Alle Anlagerichtlinien sind ausformuliert und aktuell; nichts geändert."]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Anlagerichtlinien: Stand und Vorlage.")
    unter = parser.add_subparsers(dest="befehl", required=True)
    unter.add_parser("status", help="offene Richtlinien als JSON")
    unter.add_parser("standard", help="Standard-Anlagerichtlinien übernehmen (nur wo noch die Vorlage steht)")
    p = unter.add_parser("vorlage", help="Vorlage mit den verbindlichen Limits ausgeben")
    p.add_argument("--profil", required=True, choices=g.profile())
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
