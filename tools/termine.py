#!/usr/bin/env python3
"""Fällige Reviews nach regeln.md Abschnitt 11 und 7 (Drawdown-Stufe 2).

Ein Review gilt als erledigt, wenn in reviews/ eine Datei mit dem
festgelegten Namensanfang liegt:

- Wochenreview:  reviews/JJJJ-KWnn_woche.md   (ISO-Kalenderwoche der Vorwoche)
- Monatsreview:  reviews/JJJJ-MM_monat.md
- Quartalsreview: reviews/JJJJ-Qn_quartal.md
- Pflicht-Review Drawdown-Stufe 2: reviews/JJJJ-MM-TT_stufe2_<profil>.md,
  vermerkt mit `python tools/bewertung.py review --profil <p> --datei ...`

Fällig sind alle abgeschlossenen Zeiträume seit dem Startdatum, für die
noch keine Datei existiert.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

import gemeinsam as g


def _vorhanden(praefix: str) -> bool:
    ordner = g.pfad("reviews")
    return ordner.exists() and any(ordner.glob(f"{praefix}*.md"))


def startdatum() -> date | None:
    profile = g.vorhandene_profile()
    if not profile:
        return None
    return min(date.fromisoformat(g.portfolio_laden(p)["startdatum"]) for p in profile)


def _wochen(start: date, heute: date):
    montag = start - timedelta(days=start.weekday())
    aktuelle = heute - timedelta(days=heute.weekday())
    while montag < aktuelle:
        jahr, woche, _ = montag.isocalendar()
        yield f"{jahr}-KW{woche:02d}", montag, montag + timedelta(days=6)
        montag += timedelta(days=7)


def _monate(start: date, heute: date):
    jahr, monat = start.year, start.month
    while (jahr, monat) < (heute.year, heute.month):
        yield f"{jahr}-{monat:02d}", jahr, monat
        jahr, monat = (jahr + 1, 1) if monat == 12 else (jahr, monat + 1)


def _quartale(start: date, heute: date):
    jahr, quartal = start.year, (start.month - 1) // 3 + 1
    while (jahr, quartal) < (heute.year, (heute.month - 1) // 3 + 1):
        yield f"{jahr}-Q{quartal}", jahr, quartal
        jahr, quartal = (jahr + 1, 1) if quartal == 4 else (jahr, quartal + 1)


def faellige_reviews(heute: date | None = None) -> list[dict]:
    heute = heute or g.heute()
    start = startdatum()
    if start is None or start > heute:
        return []
    faellig = []
    for name, von, bis in _wochen(start, heute):
        if not _vorhanden(name):
            faellig.append({"art": "woche", "zeitraum": name, "datei": f"reviews/{name}_woche.md",
                            "text": f"Wochenreview {name} ({von:%d.%m.} bis {bis:%d.%m.%Y})"})
    for name, _, _ in _monate(start, heute):
        if not _vorhanden(name + "_"):
            faellig.append({"art": "monat", "zeitraum": name, "datei": f"reviews/{name}_monat.md",
                            "text": f"Monatsvergleich der Profile {name}"})
    for name, _, _ in _quartale(start, heute):
        if not _vorhanden(name):
            faellig.append({"art": "quartal", "zeitraum": name, "datei": f"reviews/{name}_quartal.md",
                            "text": f"Quartals-Meta-Review {name}"})
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
