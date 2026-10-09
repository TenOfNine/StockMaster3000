#!/usr/bin/env python3
"""Overnight: Kostenrechnung und Rückblick (Backtest) auf Schlusskurs → nächste Eröffnung.

    python tools/overnight.py kosten [--nav 1000] [--einsatz-anteil 0.97]    Kosten und Break-even je Nacht (ohne Netz)
    python tools/overnight.py analyse [--liste ID] [--ticker T ...]            Rückblick auf Tageskerzen (Netzwerk)
    python tools/overnight.py ergebnis [--anzahl 10] [--json]                  letzte Analyse lesen (ohne Netz)

Warum: Das Overnight-Portfolio kauft zum Schlusskurs und verkauft zur nächsten Eröffnung (tools/daueranweisung.py). Ob
das nach Kosten lohnt, ist eine Zahlenfrage (Rechnen macht Code): Die Kosten stehen fest (regeln.md 5), die Rendite
zwischen Schluss und Eröffnung messen wir aus den Tageskerzen der Werte in config/beobachtung.json.

Methode: Je Wert und Nacht r = Open(t+1) / Close(t) - 1 aus den Rohkursen des letzten Jahres (yfinance, wie der
Screener). Zeitlich aufgeteilt: die ersten 70 % der Nächte sind Training, der Rest Test. Netto = Bruttorendite abzüglich
der Kosten einer Nacht im Spiel (2 Gebühren plus Spread, bei Knock-outs plus Finanzierung; Hebel multipliziert die
Bruttorendite, nicht die festen Gebühren). Kandidaten müssen in Training UND Test netto positiv sein. Grenzen: Rohkurse
enthalten Dividendenabschläge (Aktien wirken schlechter, ETFs nicht), ein Jahr ist kurz, und bei rund 600 Werten ist
mit Zufallstreffern zu rechnen; ein Ergebnis ist eine Hypothese, kein Beleg (regeln.md 11).
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import date

import beobachtung
import gemeinsam as g
import kurse
import pfade
from gemeinsam import D, Fehler

TRAININGSANTEIL = 0.7
MIN_NAECHTE = 120          # darunter keine Aussage über einen Wert
MIN_TEST_NAECHTE = 30
US_REFERENZ = "^GSPC"
XETRA_INDIZES = ("^GDAXI", "^STOXX50E")
VARIANTEN = {  # Name -> (Typ, Hebel, Anteil am Portfoliowert je Position, Anzahl Positionen)
    "etf_1": ("etf", 1, 0.97, 1),
    "etf_2": ("etf", 1, 0.485, 2),
    "ko_3": ("ko", 3, 0.30, 1),
}


def ergebnis_pfad():
    return pfade.cache_pfad("overnight_analyse.json")


# --------------------------------------------------------------------------
# Kosten (ohne Netz)


def kosten_einer_nacht(typ: str, einsatz: float, hebel: float = 1, nacht_tage: int = 1) -> dict:
    """Kosten einer Nacht für eine Position: Gebühren (Kauf und Verkauf), Spread (gesamt) und Finanzierung (KO long)."""
    gebuehr = float(g.gebuehr())
    spread = float(g.spread(typ))
    finanzierung = 0.0
    if typ == "ko" and hebel > 1:  # Basispreis wird mit ko_long_aufzinsung_pa aufgezinst (Hebel-1 mal der Wert)
        finanzierung = (hebel - 1) * float(D(g.kosten()["ko_long_aufzinsung_pa"])) / g.kosten()["tage_je_jahr"] * nacht_tage
    gebuehren_anteil = 2 * gebuehr / einsatz
    return {"gebuehr_anteil": gebuehren_anteil, "spread_anteil": spread, "finanzierung_anteil": finanzierung,
            "gesamt_anteil": gebuehren_anteil + spread + finanzierung,
            "break_even_basiswert": (gebuehren_anteil + spread + finanzierung) / hebel}


def kosten_tabelle(nav: float = 1000.0, einsatz_anteil: float = 0.97) -> list[dict]:
    zeilen = []
    for name, (typ, hebel, anteil, anzahl) in VARIANTEN.items():
        einsatz = nav * anteil if name != "etf_1" else nav * einsatz_anteil
        k = kosten_einer_nacht(typ, einsatz, hebel)
        zeilen.append({"variante": name, "typ": typ, "hebel": hebel, "positionen": anzahl, "einsatz_eur": round(einsatz, 2),
                       "kosten_eur": round(anzahl * 2 * float(g.gebuehr()) + anzahl * einsatz * k["spread_anteil"]
                                           + anzahl * einsatz * k["finanzierung_anteil"], 2), **k})
    return zeilen


# --------------------------------------------------------------------------
# Rückblick (reine Rechnung auf Tageskerzen)


def naechte(kerzen: list[dict]) -> list[dict]:
    """Nächte zwischen aufeinanderfolgenden Handelstagen: r = Open(t+1)/Close(t) - 1, mit Abstand in Kalendertagen."""
    ergebnis = []
    for heute, morgen in zip(kerzen, kerzen[1:]):
        if heute["close"] > 0:
            ergebnis.append({"datum": heute["datum"], "r": morgen["open"] / heute["close"] - 1,
                             "tage": (morgen["datum"] - heute["datum"]).days})
    return ergebnis


def _quantil(werte: list[float], q: float) -> float:
    reihe = sorted(werte)
    stelle = q * (len(reihe) - 1)
    unten, oben = math.floor(stelle), math.ceil(stelle)
    return reihe[unten] + (reihe[oben] - reihe[unten]) * (stelle - unten)


def statistik(renditen: list[float]) -> dict | None:
    if len(renditen) < 2:
        return None
    return {"n": len(renditen), "mittel": statistics.fmean(renditen), "median": statistics.median(renditen),
            "trefferquote": sum(1 for r in renditen if r > 0) / len(renditen), "q05": _quantil(renditen, 0.05),
            "streuung": statistics.stdev(renditen), "minimum": min(renditen)}


def netto(renditen: list[float], typ: str, hebel: float, einsatz: float, tage: list[int] | None = None) -> list[float]:
    """Nettorenditen je Nacht nach Kosten des Spiels (Hebel gilt für die Bruttorendite, Gebühren sind fix)."""
    kosten = kosten_einer_nacht(typ, einsatz, hebel)
    ergebnis = []
    for i, r in enumerate(renditen):
        nacht = (tage[i] if tage else 1)
        fin = kosten["finanzierung_anteil"] * nacht
        ergebnis.append(hebel * r - kosten["gebuehr_anteil"] - kosten["spread_anteil"] - fin)
    return ergebnis


def korrelation(a: list[float], b: list[float]) -> float | None:
    if len(a) < 20 or len(a) != len(b):
        return None
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    zaehler = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    nenner = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return zaehler / nenner if nenner else None


def us_abhaengigkeit(kerzen: list[dict], us: list[dict]) -> float | None:
    """Korrelation der Nachtrendite eines Xetra-Werts mit der US-Sitzung des Tages (S&P 500, Open bis Close)."""
    us_tag = {k["datum"]: k["close"] / k["open"] - 1 for k in us if k["open"] > 0}
    a, b = [], []
    for n in naechte(kerzen):
        if n["datum"] in us_tag:
            a.append(n["r"])
            b.append(us_tag[n["datum"]])
    return korrelation(a, b)


def auswerten(ticker: str, kerzen: list[dict], us: list[dict] | None = None) -> dict | None:
    nachtreihe = naechte(kerzen)
    if len(nachtreihe) < MIN_NAECHTE:
        return None
    schnitt = int(len(nachtreihe) * TRAININGSANTEIL)
    training, test = nachtreihe[:schnitt], nachtreihe[schnitt:]
    werte = {"n": len(nachtreihe), "von": nachtreihe[0]["datum"].isoformat(), "bis": nachtreihe[-1]["datum"].isoformat(),
             "alle": statistik([n["r"] for n in nachtreihe]),
             "wochenende": statistik([n["r"] for n in nachtreihe if n["tage"] >= 3]),
             "wochentag": statistik([n["r"] for n in nachtreihe if n["tage"] < 3]),
             "training": statistik([n["r"] for n in training]), "test": statistik([n["r"] for n in test])}
    varianten = {}
    for name, (typ, hebel, anteil, _) in VARIANTEN.items():
        einsatz = 1000 * anteil
        tr = netto([n["r"] for n in training], typ, hebel, einsatz, [n["tage"] for n in training])
        te = netto([n["r"] for n in test], typ, hebel, einsatz, [n["tage"] for n in test])
        varianten[name] = {"training_netto": statistics.fmean(tr), "test_netto": statistics.fmean(te) if te else None,
                           "positiv_in_beiden": bool(te) and statistics.fmean(tr) > 0 and statistics.fmean(te) > 0
                           and len(te) >= MIN_TEST_NAECHTE}
    werte["varianten"] = varianten
    if us and (ticker.endswith(".DE") or ticker in XETRA_INDIZES):
        werte["us_korrelation"] = us_abhaengigkeit(kerzen, us)
    return werte


def analysieren(roh: dict[str, list[dict]]) -> dict:
    us = roh.get(US_REFERENZ)
    je_wert = {}
    for ticker, kerzen in sorted(roh.items()):
        auswertung = auswerten(ticker, kerzen, us)
        if auswertung:
            je_wert[ticker] = auswertung
    ergebnis = {"zeit": g.iso(g.jetzt()), "quelle": "yfinance (Rohkurse, 1 Jahr)", "angefragt": len(roh),
                "ausgewertet": len(je_wert), "split": TRAININGSANTEIL, "kosten": kosten_tabelle(), "werte": je_wert}
    zusammenfassung = {}
    for name in VARIANTEN:
        netto_test = [w["varianten"][name]["test_netto"] for w in je_wert.values()
                      if w["varianten"][name]["test_netto"] is not None]
        kandidaten = sorted(((t, w["varianten"][name]["test_netto"]) for t, w in je_wert.items()
                             if w["varianten"][name]["positiv_in_beiden"]), key=lambda x: -x[1])
        zusammenfassung[name] = {
            "werte": len(netto_test), "median_test_netto": statistics.median(netto_test) if netto_test else None,
            "bester_test_netto": max(netto_test) if netto_test else None,
            "anzahl_positiv_in_beiden": len(kandidaten), "kandidaten": [t for t, _ in kandidaten[:20]]}
    alle_mittel = [w["alle"]["mittel"] for w in je_wert.values() if w["alle"]]
    wochenende = [w["wochenende"]["mittel"] for w in je_wert.values() if w["wochenende"]]
    wochentag = [w["wochentag"]["mittel"] for w in je_wert.values() if w["wochentag"]]
    zusammenfassung["brutto"] = {
        "median_mittel_je_nacht": statistics.median(alle_mittel) if alle_mittel else None,
        "median_mittel_wochenende": statistics.median(wochenende) if wochenende else None,
        "median_mittel_wochentag": statistics.median(wochentag) if wochentag else None}
    ergebnis["zusammenfassung"] = zusammenfassung
    return ergebnis


def analyse_ausfuehren(liste: str | None = None, tickers: list[str] | None = None) -> dict:
    konfig = beobachtung.standard_konfig()
    werte = list(beobachtung.werte_der_listen(konfig, liste))
    werte += [t for t in (tickers or []) if t not in werte]
    zusatz = [US_REFERENZ, g.projekt()["benchmark_ticker"], *XETRA_INDIZES]
    gesamt = sorted(set(werte) | set(zusatz))
    roh = beobachtung.HOLEN(gesamt)
    if not roh:
        raise Fehler("Keine Kursdaten erhalten (Quelle nicht erreichbar?); die bisherige Analyse bleibt erhalten.")
    ergebnis = analysieren(roh)
    g.json_schreiben(ergebnis_pfad(), ergebnis)
    return ergebnis


# --------------------------------------------------------------------------
# Anzeige


def _p(wert: float | None, stellen: int = 3, vorzeichen: bool = True) -> str:
    return "–" if wert is None else f"{wert * 100:{'+' if vorzeichen else ''}.{stellen}f} %".replace(".", ",")


def kosten_text(zeilen: list[dict]) -> list[str]:
    ausgabe = ["Kosten einer Nacht bei 1.000 EUR (regeln.md 5: 1 EUR je Order, Spread ETF 0,10 %, Zertifikat 0,20 %):", "",
               "| Variante | Einsatz | Kosten je Nacht | in % des Einsatzes | Break-even der Basiswert-Rendite je Nacht |",
               "| --- | ---: | ---: | ---: | ---: |"]
    for z in zeilen:
        ausgabe.append(f"| {z['variante']} ({z['typ']}, Hebel {z['hebel']}, {z['positionen']} Pos.) | {z['einsatz_eur']:.2f} EUR | "
                       f"{z['kosten_eur']:.2f} EUR | {_p(z['gesamt_anteil'], 2, False)} | {_p(z['break_even_basiswert'], 2, False)} |")
    ausgabe += ["", "Die Basiswert-Rendite zwischen Schluss und Eröffnung muss im Schnitt mindestens den Break-even "
                    "erreichen, damit eine Nacht nach Kosten nicht im Erwartungswert verliert."]
    return ausgabe


def ergebnis_text(e: dict, anzahl: int = 10) -> list[str]:
    z = e["zusammenfassung"]
    ausgabe = [f"Overnight-Analyse vom {e['zeit'][:16]} ({e['quelle']}): {e['ausgewertet']} von {e['angefragt']} Werten "
               f"ausgewertet, Training {int(e['split'] * 100)} % / Test {100 - int(e['split'] * 100)} %.", ""]
    ausgabe += kosten_text(e["kosten"]) + [""]
    b = z["brutto"]
    ausgabe.append(f"Brutto (Median über alle Werte): Mittel je Nacht {_p(b['median_mittel_je_nacht'])}, vor einem "
                   f"Wochenende/Feiertag {_p(b['median_mittel_wochenende'])}, sonst {_p(b['median_mittel_wochentag'])}.")
    for name in VARIANTEN:
        v = z[name]
        ausgabe.append(f"- {name}: Median der Netto-Rendite je Nacht im Test {_p(v['median_test_netto'])} (bester Wert "
                       f"{_p(v['bester_test_netto'])}); {v['anzahl_positiv_in_beiden']} von {v['werte']} Werten netto positiv "
                       "in Training und Test" + (": " + ", ".join(v["kandidaten"][:anzahl]) if v["kandidaten"] else "."))
    ausgabe += ["", "Hinweis: Bei vielen Werten sind Zufallstreffer zu erwarten; ein Kandidat ist eine Hypothese, "
                    "kein Beleg. Rohkurse enthalten Dividendenabschläge (Aktien wirken schlechter, ETFs nicht)."]
    breit = [(t, w) for t, w in e["werte"].items() if t in (US_REFERENZ, g.projekt()["benchmark_ticker"], *XETRA_INDIZES)]
    for t, w in breit:
        alle = w["alle"]
        ausgabe.append(f"  {t}: Mittel {_p(alle['mittel'])}, Median {_p(alle['median'])}, Trefferquote "
                       f"{alle['trefferquote'] * 100:.0f} %, 5-%-Quantil {_p(alle['q05'])}, Streuung {_p(alle['streuung'])}, "
                       f"Wochenende {_p((w['wochenende'] or {}).get('mittel'))}"
                       + (f", Korrelation mit der US-Sitzung {w['us_korrelation']:.2f}" if w.get("us_korrelation") is not None
                          else "") + f", Netto etf_1 im Test {_p(w['varianten']['etf_1']['test_netto'])}")
    return ausgabe


def ergebnis_lesen() -> dict:
    datei = ergebnis_pfad()
    if not datei.exists():
        raise Fehler("Noch keine Overnight-Analyse. Der Hintergrunddienst erstellt sie wöchentlich; von Hand: "
                     "python tools/overnight.py analyse (braucht Netzwerk).")
    return json.loads(datei.read_text(encoding="utf-8"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Overnight: Kostenrechnung und Rückblick.")
    unter = parser.add_subparsers(dest="befehl", required=True)
    p = unter.add_parser("kosten", help="Kosten und Break-even je Nacht (ohne Netz)")
    p.add_argument("--nav", type=float, default=1000.0)
    p.add_argument("--einsatz-anteil", type=float, default=0.97)
    p = unter.add_parser("analyse", help="Rückblick auf Tageskerzen (braucht Netzwerk)")
    p.add_argument("--liste", help="nur diese Liste aus config/beobachtung.json")
    p.add_argument("--ticker", action="append", default=[], help="zusätzlicher Wert")
    p = unter.add_parser("ergebnis", help="letzte Analyse anzeigen (ohne Netz)")
    p.add_argument("--anzahl", type=int, default=10)
    p.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.befehl == "kosten":
            print("\n".join(kosten_text(kosten_tabelle(args.nav, args.einsatz_anteil))))
        elif args.befehl == "analyse":
            e = analyse_ausfuehren(args.liste, args.ticker)
            print(f"Overnight-Analyse: {e['ausgewertet']} von {e['angefragt']} Werten ausgewertet.")
        else:
            e = ergebnis_lesen()
            print(json.dumps(e, ensure_ascii=False, indent=1) if args.json else "\n".join(ergebnis_text(e, args.anzahl)))
    except Fehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
