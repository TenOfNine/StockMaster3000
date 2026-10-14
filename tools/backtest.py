#!/usr/bin/env python3
"""Strategie-Labor: Rückblick auf Tagesdaten mit den Kosten des Spiels (L4). Bucht nie, ändert keinen Spielstand.

    python tools/backtest.py liste                                         verfügbare Strategien
    python tools/backtest.py daten [--ticker EUNL.DE ...] [--von 2010-01-01] [--bis JJJJ-MM-TT]   (Netzwerk; Standard config/labor.json)
    python tools/backtest.py ausfuehren --strategie trend [--parameter tage=100,200] [--fest ticker=EUNL.DE]
                             [--von JJJJ-MM-TT] [--bis JJJJ-MM-TT] [--kapital 1000] [--is-anteil 0.7] [--json]
    python tools/backtest.py walkforward --strategie trend --parameter tage=100,150,200 [--training 504] [--test 126]
    python tools/backtest.py berichte                                      gespeicherte Berichte (labor/*.json)
    python tools/backtest.py kosten [--synthetisch] [--tage 500] [--seeds 10]   Kapital und Gebührenmodell vergleichen

`--parameter name=wert1,wert2` ist ein Gitter: jede Kombination ist eine Variante, jede wird in labor/versuche.jsonl
vermerkt (Mehrfachtest, Deflated Sharpe). Aus dem Gitter gewinnt die Variante mit dem besten Sharpe im In-Sample-Teil;
der Bericht zeigt ihren Out-of-Sample-Teil getrennt. Listenwerte schreibst du mit `|` (`universum=A.DE|B.DE`), Gewichte
als `gewichte=EUNL.DE:0.6|EUNH.DE:0.4`. Daten kommen aus labor/daten/ (Zwischenspeicher, reproduzierbar); `daten` füllt ihn.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from datetime import date, timedelta
from decimal import Decimal

import gemeinsam as g
from gemeinsam import Fehler
from labor import bericht, daten, engine, strategien
from labor.strategien import REGISTER, STANDARD_BENCHMARK


def wert_lesen(text: str, name: str):
    def einzeln(t: str):
        for typ in (int, float):
            try:
                return typ(t)
            except ValueError:
                pass
        return {"true": True, "false": False, "none": None}.get(t.lower(), t)

    if name == "gewichte":
        return {k: float(v) for k, v in (p.split(":") for p in text.split("|"))}
    if "|" in text:
        return [einzeln(t) for t in text.split("|")]
    return einzeln(text)


def parameter_lesen(eintraege: list[str] | None, gitter: bool) -> dict:
    ergebnis = {}
    for e in eintraege or []:
        if "=" not in e:
            raise Fehler(f"Parameter '{e}' hat nicht die Form name=wert.")
        name, text = e.split("=", 1)
        if gitter:
            ergebnis[name] = [wert_lesen(t, name) for t in text.split(",")]
        else:
            ergebnis[name] = wert_lesen(text, name)
    return ergebnis


def strategie_bauen(name: str, fest: dict, variante: dict):
    if name not in REGISTER:
        raise Fehler(f"Unbekannte Strategie '{name}' (verfügbar: {', '.join(REGISTER)}).")
    try:
        return REGISTER[name](**fest, **variante)
    except TypeError as exc:
        raise Fehler(f"Parameter passen nicht zur Strategie {name}: {exc}") from exc


def fruehester_start(panel: daten.Panel, strategie: engine.Strategie, benchmark: str) -> date:
    erste = max(next(i for i, k in enumerate(panel.kerzen[t]) if k is not None)
                for t in {*strategie.tickers, benchmark})
    return panel.tage[min(len(panel.tage) - 1, erste + strategie.aufwaermen)]


def panel_fuer(strategie: engine.Strategie, benchmark: str) -> daten.Panel:
    tickers = list({*strategie.tickers, benchmark})
    import kurse
    if any(kurse.waehrung(t) != "EUR" for t in tickers):
        tickers.append(daten.FX_TICKER)
    return daten.Panel.aus_cache(tickers)


def ausfuehren(args) -> dict:
    fest = parameter_lesen(args.fest, gitter=False)
    gitter = parameter_lesen(args.parameter, gitter=True)
    kombis = [dict(zip(gitter, w)) for w in itertools.product(*gitter.values())] or [{}]
    erste = strategie_bauen(args.strategie, fest, kombis[0])
    panel = panel_fuer(erste, args.benchmark)
    start = date.fromisoformat(args.von) if args.von else fruehester_start(panel, erste, args.benchmark)
    ende = date.fromisoformat(args.bis) if args.bis else None
    berichte = []
    for k in kombis:
        berichte.append(bericht.lauf_bericht(panel, strategie_bauen(args.strategie, fest, k), start, ende,
                                             Decimal(args.kapital), args.benchmark, args.is_anteil))
    def sharpe_is(b):
        wert = (b["is"].get("sharpe") or {}).get("wert")
        return wert if wert is not None else float("-inf")

    gewinner = max(berichte, key=sharpe_is)
    # Die Versuche aller Varianten stehen jetzt im Protokoll: Deflated Sharpe des Gewinners neu rechnen.
    if len(berichte) > 1:
        gewinner = bericht.lauf_bericht(panel, strategie_bauen(args.strategie, fest, kombis[berichte.index(gewinner)]),
                                        start, ende, Decimal(args.kapital), args.benchmark, args.is_anteil, loggen=False)
    gewinner["varianten"] = [{"parameter": b["parameter"], "sharpe_in_sample": (b["is"].get("sharpe") or {}).get("wert"),
                              "sharpe_out_of_sample": (b["oos"].get("sharpe") or {}).get("wert")} for b in berichte]
    bericht.speichern(gewinner)
    return gewinner


def kostenbericht(args) -> str:
    """Tabelle der Kostenvarianten; synthetisch gemittelt über mehrere Zufallsreihen ohne Vorteil."""
    import numpy as np
    from kurse import Kerze

    fabriken = {
        "overnight (ETF)": lambda: strategien.Overnight(args.ticker),
        "trend 20 Tage (täglich geprüft)": lambda: strategien.Trendfolge(args.ticker, tage=20, pruefung="taeglich"),
        "60/40 monatlich": lambda: strategien.Gemischt({args.ticker: 0.6, "EUNH.DE": 0.4}, rebalancing="monat"),
    }
    runs = []
    if args.synthetisch:
        tage = []
        t = date(2024, 1, 1)
        while len(tage) < args.tage:
            if t.weekday() < 5:
                tage.append(t)
            t += timedelta(days=1)
        for seed in range(args.seeds):
            serien = {}
            for i, ticker in enumerate((args.ticker, "EUNH.DE")):
                rng = np.random.default_rng(seed * 10 + i)
                c = 100 * np.cumprod(1 + rng.normal(0.0, 0.01, len(tage)))
                o = np.concatenate([[100.0], c[:-1]]) * (1 + rng.normal(0, 0.002, len(tage)))
                serien[ticker] = [Kerze(d, Decimal(f"{a:.4f}"), Decimal(f"{max(a, b) * 1.003:.4f}"),
                                        Decimal(f"{min(a, b) * 0.997:.4f}"), Decimal(f"{b:.4f}")) for d, a, b in zip(tage, o, c)]
            runs.append(daten.Panel(serien))
    else:
        runs.append(daten.Panel.aus_cache([args.ticker, "EUNH.DE"]))
    zeilen: dict[tuple, list[dict]] = {}
    for panel in runs:
        for z in bericht.kostenvergleich(panel, fabriken, panel.tage[0]):
            zeilen.setdefault((z["strategie"], z["variante"]), []).append(z)
    kopf = ["| Strategie | Variante | Orders | Kosten p. a. (% des Kapitals) | Rendite im Zeitraum (%) |", "| --- | --- | ---: | ---: | ---: |"]
    for (name, variante), liste in zeilen.items():
        mittel = lambda f: sum(x[f] for x in liste) / len(liste)  # noqa: E731
        kopf.append(f"| {name} | {variante} | {mittel('orders'):.0f} | {str(round(100 * mittel('kosten_pa'), 2)).replace('.', ',')} | "
                    f"{str(round(100 * mittel('rendite'), 2)).replace('.', ',')} |")
    hinweis = ("Zufallskurse ohne Vorteil: die Rendite zeigt nur die Kosten, nicht eine Strategie." if args.synthetisch
               else "Echte Tagesdaten aus labor/daten/.")
    return "\n".join(kopf) + f"\n\n{hinweis} Mittel über {len(runs)} Reihe(n), {runs[0].tage[0]} bis {runs[0].tage[-1]}."


def zeigen(b: dict) -> str:
    return bericht.markdown(b)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Strategie-Labor: Rückblick auf Tagesdaten (bucht nie).")
    unter = parser.add_subparsers(dest="befehl", required=True)
    unter.add_parser("liste", help="verfügbare Strategien")
    k = unter.add_parser("kosten", help="Kostenvarianten (Kapital und Gebührenmodell) auf denselben Kursen vergleichen")
    k.add_argument("--synthetisch", action="store_true", help="Zufallskurse ohne Vorteil (zeigt nur die Kosten)")
    k.add_argument("--tage", type=int, default=500)
    k.add_argument("--seeds", type=int, default=10, help="Zahl der Zufallsreihen, über die gemittelt wird")
    k.add_argument("--ticker", default=STANDARD_BENCHMARK)
    unter.add_parser("berichte", help="gespeicherte Berichte")
    d = unter.add_parser("daten", help="Tageskerzen holen und zwischenspeichern (Netzwerk)")
    d.add_argument("--ticker", action="append", help="Standard: Liste aus config/labor.json")
    d.add_argument("--von", help="Standard: config/labor.json")
    d.add_argument("--bis")
    for name in ("ausfuehren", "walkforward"):
        p = unter.add_parser(name)
        p.add_argument("--strategie", required=True)
        p.add_argument("--parameter", action="append", help="Gitter: name=wert1,wert2")
        p.add_argument("--fest", action="append", help="feste Parameter: name=wert")
        p.add_argument("--von")
        p.add_argument("--bis")
        p.add_argument("--kapital", default="1000.00")
        p.add_argument("--benchmark", default=STANDARD_BENCHMARK)
        p.add_argument("--is-anteil", type=float, default=0.7)
        p.add_argument("--json", action="store_true")
        if name == "walkforward":
            p.add_argument("--training", type=int, default=504)
            p.add_argument("--test", type=int, default=126)
    args = parser.parse_args(argv)
    try:
        if args.befehl == "liste":
            for name, klasse in REGISTER.items():
                print(f"{name}: {klasse.beschreibung}")
        elif args.befehl == "kosten":
            print(kostenbericht(args))
        elif args.befehl == "berichte":
            for b in bericht.berichte_liste():
                print(f"{b['datei']}: {b['urteil']} ({b['zeitraum']['von']} bis {b['zeitraum']['bis']})")
        elif args.befehl == "daten":
            konfig = g.config("labor")
            fehler = []
            for t in args.ticker or konfig["ticker"]:
                try:
                    neu = daten.holen(t, date.fromisoformat(args.von or konfig["von"]),
                                      date.fromisoformat(args.bis) if args.bis else g.heute())
                    print(f"{t}: {neu} neue Tage im Zwischenspeicher.")
                except Fehler as exc:
                    fehler.append(f"{t}: {exc}")
                    print(f"{t}: FEHLER {exc}", file=sys.stderr)
            if fehler:
                return 1
        elif args.befehl == "ausfuehren":
            b = ausfuehren(args)
            print(json.dumps(b, ensure_ascii=False, indent=1) if args.json else zeigen(b))
        else:
            fest = parameter_lesen(args.fest, gitter=False)
            gitter = parameter_lesen(args.parameter, gitter=True)
            erste = strategie_bauen(args.strategie, fest, {k: v[0] for k, v in gitter.items()})
            panel = panel_fuer(erste, args.benchmark)
            start = date.fromisoformat(args.von) if args.von else fruehester_start(panel, erste, args.benchmark)
            ergebnis = bericht.walk_forward(panel, args.strategie, gitter, fest, start,
                                            date.fromisoformat(args.bis) if args.bis else None, args.training, args.test,
                                            Decimal(args.kapital))
            print(json.dumps(ergebnis, ensure_ascii=False, indent=1))
    except Fehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
