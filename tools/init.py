#!/usr/bin/env python3
"""Initialisierung des Spiels (AUFTRAG_PHASE1.md AP11).

Nur wenn AP1 bis AP10 in STATUS.md (Framework) abgehakt sind und ein Auftraggeber
die Freigabe nach AP12 erteilt (regeln.md Abschnitt 2). Das Spiel beginnt beim Start
(Startdatum ohne Angabe: heute); es gibt keinen festen Starttermin und kein Enddatum, ein
Datum vor heute ist Backdating und abgelehnt. Legt im Datenverzeichnis die drei
Portfolios mit je 1.000 EUR an, leere Logbücher, die Standard-Anlagerichtlinien in
strategie/ und spiel.json (Startdatum, Freigabe). Der Benchmark startet mit dem
ersten Schlusskurs ab Startdatum (tools/bewertung.py bericht).
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, timedelta

import gemeinsam as g
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
    text = g.framework_pfad("STATUS.md").read_text(encoding="utf-8")
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


def standard_text(profil: str, datum) -> str:
    """Standard-Anlagerichtlinie aus config/richtlinien/<profil>.md mit den verbindlichen Limits."""
    quelle = g.framework_pfad("config", "richtlinien", f"{profil}.md")
    limits = g.limits_fuer(profil)
    etf = limits["benchmark_etf_anteil"]
    werte = {k: _prozent(v) for k, v in limits.items()}
    werte["max_hebel"] = f"{limits['max_hebel']}x"
    werte["max_exposure"] = f"{limits['max_exposure']}x"
    return quelle.read_text(encoding="utf-8").format(
        datum=datum.isoformat(), version=g.RICHTLINIE_STANDARD_VERSION, **werte,
        benchmark=f"{_prozent(etf)} iShares Core MSCI World (EUNL.DE) / {_prozent(1 - etf)} Cash mit 2 % p. a., "
                  "Aufteilung zum ersten Schlusskurs ab Starttag, ohne Rebalancing und Kosten.")


def initialisieren(startdatum_text: str | None, freigabe: str, ausloeser: str = "kommandozeile") -> list[str]:
    status_pruefen()
    erlaubt = g.projekt()["auftraggeber"]
    if freigabe not in erlaubt:
        raise Fehler(f"Freigabe nach AP12 nur durch einen Auftraggeber ({', '.join(erlaubt)}), nicht '{freigabe}'.")
    if g.spiel_lesen().get("startdatum"):
        raise Fehler(f"Das Spiel ist bereits gestartet (Startdatum {g.spiel_lesen()['startdatum']}).")
    # Kein vorab festgelegter Termin: Ohne Angabe beginnt das Spiel heute (regeln.md Abschnitt 2).
    startdatum = g.datum_lesen(startdatum_text) if startdatum_text else g.heute()
    if startdatum < g.heute():
        raise Fehler(f"Startdatum {startdatum} liegt in der Vergangenheit (heute {g.heute()}). Kein Backdating.")
    benchmark = g.projekt()["benchmark_ticker"]
    if g.vorhandene_profile():
        raise Fehler(f"Bereits initialisiert ({', '.join(g.vorhandene_profile())}). Neustart nur mit "
                     "Zustimmung beider Auftraggeber und ohne Löschen der Historie.")
    kapital = g.text(g.geld(g.projekt()["startkapital"]))
    meldungen = []
    for profil in g.profile():
        meldungen += profil_anlegen(profil, startdatum, kapital)
    g.csv_schreiben(g.pfad("data", "benchmark.csv"), ["datum", "etf_kurs", *g.profile()], [])
    for ordner in ("journal", "reviews", "data/kurse", "data/historie", "data/limits"):
        g.pfad(ordner).mkdir(parents=True, exist_ok=True)
    g.json_schreiben(g.spiel_pfad(), {
        "startdatum": startdatum.isoformat(), "initialisiert": g.iso(g.jetzt()),
        "freigabe_ap12": freigabe, "werkzeug": "tools/init.py", "ausloeser": ausloeser,
    })
    meldungen.append(f"Benchmark {benchmark}: Basis ist der erste Schlusskurs ab {startdatum}.")
    meldungen.append("spiel.json: Startdatum und Freigabe eingetragen. Jetzt prüfen und im Datenverzeichnis "
                     "committen (python tools/datenverzeichnis.py commit).")
    return meldungen


LESSON_OVERNIGHT = """
## H-OVERNIGHT-1 (Hypothese, {datum})
Die durchschnittliche Rendite breiter Indizes zwischen Handelsschluss und nächster Eröffnung liegt nach allgemeiner
Erwartung (hier noch nicht überprüft) bei wenigen hundertstel Prozent je Nacht und damit eine Größenordnung unter den
Kosten einer Nacht im Spiel (0,31 % bei einer ETF-Position und 1.000 EUR: 2 EUR Gebühr plus 0,10 % Spread).
Prüfkriterium: `python tools/overnight.py ergebnis` zeigt für ein Instrument im Testzeitraum eine mittlere Netto-Rendite
je Nacht über null; sonst gilt für das Overnight-Portfolio Ausnahme (a) aus regeln.md 12 mit Zahlen. Aus einzelnen
Nächten folgt nichts (Glück ist kein Können).
"""


def profil_anlegen(profil: str, startdatum: date, kapital: str) -> list[str]:
    """Portfolio, Trades, NAV und Standard-Anlagerichtlinie eines Profils (Start und Ergänzung teilen den Code)."""
    g.portfolio_speichern({
        "profil": profil, "startdatum": startdatum.isoformat(), "cash": kapital,
        "verarbeitet_bis": (startdatum - timedelta(days=1)).isoformat(), "hoechststand": kapital,
        "drawdown_stufe": 0, "status": "aktiv", "positionen": [], "offene_orders": [],
        "zaehler": {"order": 0, "position": 0, "trade": 0}, "stufe2_seit": None, "stufe2_review": None,
    })
    g.csv_schreiben(g.trades_pfad(profil), g.TRADE_FELDER, [])
    g.csv_schreiben(g.pfad("data", "nav", f"{profil}.csv"), g.NAV_FELDER, [])
    meldungen = []
    if not g.richtlinie_ausformuliert(profil):
        g.atomar_schreiben(g.pfad("strategie", f"{profil}.md"), standard_text(profil, g.heute()))
        meldungen.append(f"strategie/{profil}.md aus der Standard-Anlagerichtlinie angelegt.")
    if profil == "overnight":
        lessons = g.pfad("lessons.md")
        if "H-OVERNIGHT-1" not in (lessons.read_text(encoding="utf-8") if lessons.exists() else ""):
            g.text_anhaengen(lessons, LESSON_OVERNIGHT.format(datum=g.heute().isoformat()))
            meldungen.append("lessons.md: Hypothese H-OVERNIGHT-1 eingetragen.")
    meldungen.append(f"Portfolio {profil}: {kapital} EUR ab {startdatum}.")
    return meldungen


def profile_ergaenzen(ausloeser: str = "migration") -> list[str]:
    """Ergänzt Profile aus config/profile.json, die im laufenden Spiel noch fehlen (Migration, regeln.md Abschnitt 7).

    Das neue Portfolio startet am heutigen Tag mit dem Startkapital (nie rückwirkend); die vorhandenen Portfolios,
    ihre Trades, Journal und Historie bleiben unberührt. Idempotent: fehlt nichts, geschieht nichts. Vor dem Spielstart
    legt `initialisieren` alle Profile an.
    """
    if not g.spiel_lesen().get("startdatum"):
        return []
    with g.buchungssperre():
        fehlend = [p for p in g.profile() if not g.portfolio_pfad(p).exists()]
        if not fehlend:
            return []
        if g.sperre_lesen() is not None and not g.sperre_verwaist(g.sperre_lesen()):
            raise Fehler("Eine Session läuft (Session-Sperre). Die Profile werden danach ergänzt.")
        kapital = g.text(g.geld(g.projekt()["startkapital"]))
        meldungen = []
        for profil in fehlend:
            meldungen += profil_anlegen(profil, g.heute(), kapital)
        benchmark = g.pfad("data", "benchmark.csv")
        if not g.csv_lesen(benchmark):  # nur eine leere Datei bekommt die neue Spalte sofort; sonst schreibt der Bericht sie
            g.csv_schreiben(benchmark, ["datum", "etf_kurs", *g.profile()], [])
        spiel = g.spiel_lesen()
        spiel.setdefault("profile_ergaenzt", []).extend(
            {"profil": p, "datum": g.heute().isoformat(), "ausloeser": ausloeser, "zeit": g.iso(g.jetzt())}
            for p in fehlend)
        g.json_schreiben(g.spiel_pfad(), spiel)
        meldungen.append("Jetzt prüfen und im Datenverzeichnis committen (python tools/datenverzeichnis.py commit).")
        return meldungen


def vorziehen_pruefen(neu: date) -> None:
    """Prüft, ob das Startdatum vorgezogen werden darf (sonst Fehler mit Grund).

    Erlaubt nur, solange nichts passiert ist: keine Buchung, keine Order, keine Position, keine
    Nachbuchung, keine Bewertung. Dann ändert das Vorziehen keine Historie. Ein Datum vor heute
    ist Backdating und bleibt verboten.
    """
    spiel = g.spiel_lesen()
    alt = spiel.get("startdatum")
    if not alt:
        raise Fehler("Das Spiel ist noch nicht gestartet; das Startdatum wird beim Spielstart gesetzt.")
    if neu >= g.datum_lesen(alt):
        raise Fehler(f"Das neue Startdatum {neu} liegt nicht vor dem bisherigen ({alt}).")
    if neu < g.heute():
        raise Fehler(f"Startdatum {neu} liegt in der Vergangenheit (heute {g.heute()}). Kein Backdating.")
    if g.sperre_lesen() is not None and not g.sperre_verwaist(g.sperre_lesen()):
        raise Fehler("Eine Session läuft (Session-Sperre). Das Startdatum lässt sich erst danach ändern.")
    profile = g.vorhandene_profile()
    if not profile:
        raise Fehler("Es sind keine Portfolios angelegt.")
    for profil in profile:
        portfolio = g.portfolio_laden(profil)
        unberuehrt = (not g.trades_lesen(profil) and not portfolio["positionen"] and not portfolio["offene_orders"]
                      and not g.csv_lesen(g.pfad("data", "nav", f"{profil}.csv"))
                      and portfolio["verarbeitet_bis"] == (g.datum_lesen(alt) - timedelta(days=1)).isoformat()
                      and portfolio["status"] == "aktiv")
        if not unberuehrt:
            raise Fehler(f"Das Portfolio {profil} hat schon Buchungen, Orders oder Bewertungen. Ein Vorziehen "
                         "würde die Historie ändern und ist nicht erlaubt.")
    if g.csv_lesen(g.pfad("data", "benchmark.csv")):
        raise Fehler("Die Benchmark hat schon Werte; ein Vorziehen würde die Historie ändern.")


def vorziehen(neu_text: str) -> list[str]:
    """Zieht ein noch unberührtes Startdatum vor (frühestens heute, nie rückwirkend)."""
    neu = g.datum_lesen(neu_text) if neu_text else g.heute()
    vorziehen_pruefen(neu)
    alt = g.spiel_lesen()["startdatum"]
    with g.schreibsperre():
        for profil in g.vorhandene_profile():
            portfolio = g.portfolio_laden(profil)
            portfolio["startdatum"] = neu.isoformat()
            portfolio["verarbeitet_bis"] = (neu - timedelta(days=1)).isoformat()
            g.portfolio_speichern(portfolio)
        spiel = g.spiel_lesen()
        spiel.setdefault("startdatum_vorher", []).append({"datum": alt, "geaendert": g.iso(g.jetzt())})
        spiel["startdatum"] = neu.isoformat()
        g.json_schreiben(g.spiel_pfad(), spiel)
    return [f"Startdatum von {alt} auf {neu.isoformat()} vorgezogen (es gab noch keine Buchung).",
            "Jetzt prüfen und im Datenverzeichnis committen (python tools/datenverzeichnis.py commit)."]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Spiel initialisieren: ein Portfolio je Profil mit je 1.000 EUR.")
    parser.add_argument("--startdatum", help="JJJJ-MM-TT, nicht vor heute; ohne Angabe: heute (kein fester Starttermin)")
    parser.add_argument("--ausloeser", choices=["kommandozeile", "einrichtung", "lauf", "migration"], default="kommandozeile",
                        help="wer den Start auslöst (nur zur Dokumentation in spiel.json): Einrichtung der Web-UI "
                             "oder der erste Trading-Lauf")
    parser.add_argument("--freigabe",
                        help="Kennung des Auftraggebers, der AP12 freigegeben hat (config/projekt.json)")
    parser.add_argument("--profile-ergaenzen", action="store_true",
                        help="Profile aus config/profile.json ergänzen, die im laufenden Spiel fehlen (Migration; "
                             "Start heute, Historie unberührt)")
    parser.add_argument("--vorziehen", action="store_true",
                        help="bereits gesetztes, noch unberührtes Startdatum auf ein früheres (frühestens heute) "
                             "vorziehen; nichts darf gebucht sein")
    args = parser.parse_args(argv)
    try:
        if args.profile_ergaenzen:
            meldungen = profile_ergaenzen(args.ausloeser if args.ausloeser != "kommandozeile" else "migration") \
                or ["Alle Profile sind vorhanden; nichts geändert."]
        elif args.vorziehen:
            meldungen = vorziehen(args.startdatum)
        elif not args.freigabe:
            parser.error("--freigabe ist beim Spielstart nötig")
        else:
            meldungen = initialisieren(args.startdatum, args.freigabe, args.ausloeser)
        for meldung in meldungen:
            print(meldung)
    except Fehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
