#!/usr/bin/env python3
"""Initialisierung des Spiels (AUFTRAG_PHASE1.md AP11).

Nur wenn AP1 bis AP10 in STATUS.md abgehakt sind und das Startdatum heute
oder in der Zukunft liegt (kein Backdating). Legt die drei Portfolios mit je
1.000 EUR an, leere Logbücher und Anlagerichtlinien-Vorlagen in strategie/.
Der Benchmark startet mit dem ersten Schlusskurs ab Startdatum
(tools/bewertung.py bericht).
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import timedelta

import gemeinsam as g
import kurse
from gemeinsam import Fehler

VORAUSSETZUNG = [f"AP{n}" for n in range(1, 11)]

VORLAGE = """# Anlagerichtlinie {titel}

Stand: Vorlage aus tools/init.py ({datum}). Wird in AP12 ausformuliert;
Änderungen später nur mit Datum, Anlass und Prüfkriterium (regeln.md 11).

## Ziel
(Renditeziel gegen den Benchmark, Rolle des Portfolios im Experiment)

## Risikobudget (regeln.md Abschnitt 7, verbindlich)
- Max. Anteil Zertifikate am Portfoliowert: {max_anteil_zertifikate}
- Max. Hebel je Zertifikat beim Kauf: {max_hebel}
- Max. Gesamt-Exposure: {max_exposure}
- Max. Einzelposition: {max_einzelposition}
- Mindest-Cashquote: {min_cashquote}
- Max. Risiko je Trade: {max_risiko_trade}
- Drawdown-Bremse: Stufe 1 bei {drawdown_stufe1}, Stufe 2 bei {drawdown_stufe2}

## Horizont
(typische Haltedauer, Session-Rhythmus)

## Erlaubte Instrumente
(Aktien/ETFs, Knock-outs, Faktor-Zertifikate; Einschränkungen dieses Profils)

## Benchmark
{benchmark}

## Ausgangsstrategie
(Strategie mit Begründung und aktueller Marktsicht, Quellen mit URL und Datum)

## Änderungshistorie
| Datum | Anlass | Änderung | Prüfkriterium |
| --- | --- | --- | --- |
"""


def status_pruefen() -> None:
    text = g.pfad("STATUS.md").read_text(encoding="utf-8")
    fehlend = [ap for ap in VORAUSSETZUNG if not re.search(rf"^- \[x\] {ap} ", text, re.M | re.I)]
    if fehlend:
        raise Fehler(f"Initialisierung erst nach Abschluss von AP1 bis AP10; offen: {', '.join(fehlend)}.")


def _prozent(wert) -> str:
    return f"{g.D(wert) * 100:.0f} %"


def vorlage(profil: str, datum) -> str:
    limits = g.limits_fuer(profil)
    etf = limits["benchmark_etf_anteil"]
    werte = {k: _prozent(v) for k, v in limits.items()}
    werte["max_hebel"] = f"{limits['max_hebel']}x"
    werte["max_exposure"] = f"{limits['max_exposure']}x"
    return VORLAGE.format(
        titel=profil.capitalize(), datum=datum.isoformat(), **werte,
        benchmark=f"{_prozent(etf)} iShares Core MSCI World (EUNL.DE) / {_prozent(1 - etf)} Cash mit 2 % p. a., "
                  "Aufteilung zum ersten Schlusskurs ab Startdatum, ohne Rebalancing und Kosten.")


def initialisieren(startdatum_text: str) -> list[str]:
    status_pruefen()
    startdatum = g.datum_lesen(startdatum_text)
    if startdatum < g.heute():
        raise Fehler(f"Startdatum {startdatum} liegt in der Vergangenheit (heute {g.heute()}). Kein Backdating.")
    benchmark = g.projekt()["benchmark_ticker"]
    if not kurse.ist_handelstag(benchmark, startdatum):
        raise Fehler(f"{startdatum} ist kein Xetra-Handelstag. Bitte einen Handelstag wählen.")
    if g.vorhandene_profile():
        raise Fehler(f"Bereits initialisiert ({', '.join(g.vorhandene_profile())}). Neustart nur mit "
                     "Zustimmung beider Auftraggeber und ohne Löschen der Historie.")
    kapital = g.text(g.geld(g.projekt()["startkapital"]))
    meldungen = []
    for profil in g.PROFILE:
        g.portfolio_speichern({
            "profil": profil, "startdatum": startdatum.isoformat(), "cash": kapital,
            "verarbeitet_bis": (startdatum - timedelta(days=1)).isoformat(), "hoechststand": kapital,
            "drawdown_stufe": 0, "status": "aktiv", "positionen": [], "offene_orders": [],
            "zaehler": {"order": 0, "position": 0, "trade": 0}, "stufe2_seit": None, "stufe2_review": None,
        })
        g.csv_schreiben(g.trades_pfad(profil), g.TRADE_FELDER, [])
        g.csv_schreiben(g.pfad("data", "nav", f"{profil}.csv"), g.NAV_FELDER, [])
        strategie = g.pfad("strategie", f"{profil}.md")
        if not strategie.exists():
            g.atomar_schreiben(strategie, vorlage(profil, g.heute()))
            meldungen.append(f"strategie/{profil}.md als Vorlage angelegt.")
        meldungen.append(f"Portfolio {profil}: {kapital} EUR ab {startdatum}.")
    g.csv_schreiben(g.pfad("data", "benchmark.csv"), ["datum", "etf_kurs", *g.PROFILE], [])
    for ordner in ("journal", "reviews", "data/kurse", "data/historie", "data/limits"):
        g.pfad(ordner).mkdir(parents=True, exist_ok=True)
    status = g.pfad("STATUS.md")
    text = status.read_text(encoding="utf-8")
    neu = re.sub(r"^- Startdatum des Spiels:.*$",
                 f"- Startdatum des Spiels: {startdatum.isoformat()} (gesetzt am {g.heute().isoformat()} "
                 "durch tools/init.py)", text, count=1, flags=re.M)
    g.atomar_schreiben(status, neu)
    meldungen.append(f"Benchmark {benchmark}: Basis ist der erste Schlusskurs ab {startdatum}.")
    meldungen.append("STATUS.md: Startdatum eingetragen. Jetzt prüfen, committen und pushen.")
    return meldungen


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Spiel initialisieren: drei Portfolios mit je 1.000 EUR.")
    parser.add_argument("--startdatum", required=True, help="erster Handelstag, JJJJ-MM-TT (heute oder später)")
    args = parser.parse_args(argv)
    try:
        for meldung in initialisieren(args.startdatum):
            print(meldung)
    except Fehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
