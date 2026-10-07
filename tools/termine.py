"""Fällige Reviews nach regeln.md Abschnitt 11 und 7 (Drawdown-Stufe 2).

Reviews richten sich nach der Spielzeit, nicht nach dem Kalender: Ab dem Starttag
(spiel.json) zählen Zeiträume zu 7 Tagen (Woche), 28 Tagen (Monat) und 91 Tagen
(Quartal). Ein Zeitraum ist fällig, sobald sein letzter Tag vergangen ist. Ein Review
gilt als erledigt, wenn die Datei mit dem Datum des letzten Zeitraumtags existiert:

- Wochenreview:   reviews/JJJJ-MM-TT_woche.md    (JJJJ-MM-TT = letzter Tag des Zeitraums)
- Monatsreview:   reviews/JJJJ-MM-TT_monat.md
- Quartalsreview: reviews/JJJJ-MM-TT_quartal.md
- Pflicht-Review Drawdown-Stufe 2: reviews/JJJJ-MM-TT_stufe2_<profil>.md,
  vermerkt mit `python tools/bewertung.py review --profil <p> --datei ...`
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

import gemeinsam as g

ZEITRAEUME = (("woche", 7, "Wochenreview"), ("monat", 28, "Monatsvergleich der Profile"),
              ("quartal", 91, "Quartals-Meta-Review"))


def startdatum() -> date | None:
    profile = g.vorhandene_profile()
    if not profile:
        return None
    return min(date.fromisoformat(g.portfolio_laden(p)["startdatum"]) for p in profile)


def _zeitraeume(start: date, heute: date, tage: int):
    """Abgeschlossene Zeiträume (von, bis) zu je `tage` Tagen seit dem Starttag."""
    von = start
    while von + timedelta(days=tage - 1) < heute:
        yield von, von + timedelta(days=tage - 1)
        von += timedelta(days=tage)


def faellige_reviews(heute: date | None = None) -> list[dict]:
    heute = heute or g.heute()
    start = startdatum()
    if start is None or start > heute:
        return []
    faellig = []
    for art, tage, titel in ZEITRAEUME:
        for von, bis in _zeitraeume(start, heute, tage):
            datei = f"reviews/{bis.isoformat()}_{art}.md"
            if not g.pfad(datei).exists():
                faellig.append({"art": art, "zeitraum": f"{von.isoformat()} bis {bis.isoformat()}", "datei": datei,
                                "text": f"{titel} ({von:%d.%m.} bis {bis:%d.%m.%Y})"})
    for profil in g.vorhandene_profile():
        portfolio = g.portfolio_laden(profil)
        if int(portfolio.get("drawdown_stufe", 0)) == 2 and not portfolio.get("stufe2_review"):
            datei = f"reviews/{heute.isoformat()}_stufe2_{profil}.md"
            faellig.append({"art": "stufe2", "zeitraum": portfolio.get("stufe2_seit") or "", "datei": datei,
                            "text": f"Pflicht-Review Drawdown-Stufe 2 ({profil}, seit {portfolio.get('stufe2_seit')}); "
                                    f"danach: python tools/bewertung.py review --profil {profil} --datei {datei}"})
    return faellig


def meldungen(heute: date | None = None) -> list[str]:
    faellig = faellige_reviews(heute)
    if not faellig:
        return ["Keine Reviews fällig."]
    return [f"FÄLLIG: {f['text']} -> {f['datei']}" for f in faellig]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Fällige Reviews anzeigen (Woche, Monat, Quartal, Drawdown-Stufe 2).")
    parser.parse_args(argv)
    for meldung in meldungen():
        print(meldung)
    return 0


if __name__ == "__main__":
    sys.exit(main())
