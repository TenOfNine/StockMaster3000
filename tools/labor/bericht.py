"""Kennzahlen, In-/Out-of-Sample, Walk-forward, Deflated Sharpe und Berichte des Labors."""

from __future__ import annotations

import itertools
import json
import math
from datetime import date
from decimal import Decimal
from statistics import NormalDist

import numpy as np

import gemeinsam as g
import statistik

from . import engine
from .daten import Panel
from .strategien import BuyAndHold, REGISTER, STANDARD_BENCHMARK

EULER = 0.5772156649015329
MIN_JAHRE = 3
DSR_SCHWELLE = 0.95
GRENZEN = [
    "Survivorship Bias: Der Datensatz enthält nur Werte, die es heute noch gibt und die wir kennen; gescheiterte Titel "
    "fehlen, Ergebnisse für Einzelaktien sind tendenziell zu gut.",
    "Datenqualität: yfinance-Rohkurse (ohne Anpassung für Dividenden bei Aktien), Fehler und Lücken sind möglich; "
    "Ergebnisse gelten nur für die zwischengespeicherten Daten.",
    "Tagesdaten: Ausführung zu Eröffnung oder Schluss des nächsten Preispunkts, keine Intraday-Wirkung außer Barrieren "
    "von Knock-outs; kein Slippage über den Spread des Spiels hinaus, keine Marktwirkung.",
    "Diskretionäres Claude-Trading wird nicht zurückgerechnet: Das Modell kennt die Vergangenheit aus dem Training "
    "(Look-ahead). Nur regelbasierte Strategien lassen sich ehrlich prüfen.",
    "Vergangene Ergebnisse sind keine Prognose; je mehr Varianten getestet wurden, desto größer der Zufallstreffer-Anteil "
    "(siehe Deflated Sharpe).",
]


def pfad_labor(*teile: str):
    return g.pfad("labor", *teile)


# --------------------------------------------------------------------------
# Versuche (Mehrfachtests) und Deflated Sharpe


def versuche_datei():
    return pfad_labor("versuche.jsonl")


def versuch_loggen(strategie: str, parameter: dict, von: date, bis: date, sharpe_tag: float | None) -> None:
    """Hängt einen getesteten Variantenlauf an (nur anhängen): Grundlage der Mehrfachtest-Korrektur."""
    datei = versuche_datei()
    datei.parent.mkdir(parents=True, exist_ok=True)
    zeile = {"zeit": g.iso(g.jetzt()), "strategie": strategie, "parameter": parameter, "von": von.isoformat(),
             "bis": bis.isoformat(), "sharpe_tag": sharpe_tag}
    with datei.open("a", encoding="utf-8") as f:
        f.write(json.dumps(zeile, ensure_ascii=False, sort_keys=True) + "\n")


def versuche_lesen() -> list[dict]:
    datei = versuche_datei()
    if not datei.exists():
        return []
    return [json.loads(z) for z in datei.read_text(encoding="utf-8").splitlines() if z.strip()]


def deflated_sharpe(sr: float, n: int, schiefe: float, kurtosis: float, trial_sharpes: list[float]) -> float | None:
    """Deflated Sharpe Ratio (Bailey und López de Prado): Wahrscheinlichkeit, dass der wahre Sharpe über 0 liegt,
    nachdem die Zahl der getesteten Varianten berücksichtigt ist. Alle Sharpe-Werte pro Handelstag (nicht annualisiert).
    """
    if n < 3:
        return None
    nenner = 1 - schiefe * sr + (kurtosis - 1) / 4 * sr ** 2
    if nenner <= 0:
        return None
    normal = NormalDist()
    sr0 = 0.0
    anzahl = len(trial_sharpes)
    if anzahl >= 2:
        sigma = float(np.std(trial_sharpes, ddof=1))
        sr0 = sigma * ((1 - EULER) * normal.inv_cdf(1 - 1 / anzahl) + EULER * normal.inv_cdf(1 - 1 / (anzahl * math.e)))
    return normal.cdf((sr - sr0) * math.sqrt(n - 1) / math.sqrt(nenner))


def momente(r: np.ndarray) -> tuple[float, float]:
    """Schiefe und Kurtosis (nicht überschüssig) einer Renditereihe."""
    s = r.std()
    if s == 0 or len(r) < 4:
        return 0.0, 3.0
    z = (r - r.mean()) / s
    return float((z ** 3).mean()), float((z ** 4).mean())


# --------------------------------------------------------------------------
# Auswertung eines Laufs


def _einstellungen() -> dict:
    return {**statistik.einstellungen(), "resamples": 1000}


def kennzahlen_fenster(r: np.ndarray, b: np.ndarray | None, rf: float) -> dict:
    return statistik.kennzahlen_reihe(r, b, b, rf, _einstellungen())


def auswerten_lauf(erg: engine.Ergebnis, bench: engine.Ergebnis, is_anteil: float = 0.7) -> dict:
    """Kennzahlen gesamt, In-Sample (erste `is_anteil` der Tage) und Out-of-Sample für den Lauf und seine Benchmark."""
    w_s = {t: float(w) for t, w in zip(erg.tage, erg.werte)}
    w_b = {t: float(w) for t, w in zip(bench.tage, bench.werte)}
    tage, (r, b) = statistik.ausrichten(w_s, w_b)
    rf = float(g.D(g.projekt()["risikofreier_zins_pa"])) / statistik.TAGE_JE_JAHR
    n_is = int(len(tage) * is_anteil)
    ergebnis = {"zeitraum": {"von": tage[0].isoformat() if tage else None, "bis": tage[-1].isoformat() if tage else None,
                             "tage": len(tage)},
                "in_sample": {"bis": tage[n_is - 1].isoformat() if n_is else None, "tage": n_is},
                "out_of_sample": {"von": tage[n_is].isoformat() if n_is < len(tage) else None, "tage": len(tage) - n_is},
                "gesamt": kennzahlen_fenster(r, b, rf), "is": kennzahlen_fenster(r[:n_is], b[:n_is], rf),
                "oos": kennzahlen_fenster(r[n_is:], b[n_is:], rf),
                "benchmark": kennzahlen_fenster(b, None, rf)}
    ergebnis["_reihen"] = (tage, r, b)
    return ergebnis


def urteil(auswertung: dict, dsr: float | None, jahre: float) -> dict:
    """Nur Überlebende werden Vorschläge: Out-of-Sample unterscheidbar besser als die Benchmark, Deflated Sharpe hoch genug,
    mindestens drei Jahre Daten."""
    gruende = []
    oos = auswertung["oos"]
    if not oos.get("genug_daten"):
        gruende.append("Out-of-Sample: zu wenige Handelstage")
    elif oos.get("abstand") != "besser":
        gruende.append("Out-of-Sample: Überrendite nicht als besser von der Benchmark unterscheidbar")
    if dsr is None or dsr < DSR_SCHWELLE:
        gruende.append(f"Deflated Sharpe {_de(dsr)} unter {_de(DSR_SCHWELLE)}")
    if jahre < MIN_JAHRE:
        gruende.append(f"Zeitraum {_de(jahre, 1)} Jahre, weniger als {MIN_JAHRE}")
    return {"vorschlag": not gruende, "gruende": gruende,
            "text": "Kandidat für einen Vorschlag an die Auftraggeber" if not gruende else "kein Vorschlag"}


def kurve(tage: list[date], erg: engine.Ergebnis, bench: engine.Ergebnis) -> dict:
    s = {t: float(w) for t, w in zip(erg.tage, erg.werte)}
    b = {t: float(w) for t, w in zip(bench.tage, bench.werte)}
    gemeinsam = [t for t in tage if t in s and t in b]
    return {"tage": [t.isoformat() for t in gemeinsam],
            "strategie": [round(100 * s[t] / float(erg.kapital), 4) for t in gemeinsam],
            "benchmark": [round(100 * b[t] / float(bench.kapital), 4) for t in gemeinsam]}


def lauf_bericht(panel: Panel, strategie: engine.Strategie, start: date, ende: date | None = None,
                 kapital: Decimal = Decimal("1000.00"), benchmark: str = STANDARD_BENCHMARK, is_anteil: float = 0.7,
                 toleranz: float = 0.0, loggen: bool = True) -> dict:
    erg = engine.ausfuehren(panel, strategie, start, ende, kapital, toleranz)
    bench_strategie = BuyAndHold(benchmark)
    bench = engine.ausfuehren(panel, bench_strategie, start, ende, kapital)
    a = auswerten_lauf(erg, bench, is_anteil)
    tage, r, b = a.pop("_reihen")
    rf = float(g.D(g.projekt()["risikofreier_zins_pa"])) / statistik.TAGE_JE_JAHR
    sr_tag = float(((r - rf).mean() / (r - rf).std(ddof=1))) if len(r) > 2 and (r - rf).std(ddof=1) > 0 else None
    if loggen and tage:
        versuch_loggen(strategie.name, strategie.parameter(), tage[0], tage[-1], sr_tag)
    versuche = [v["sharpe_tag"] for v in versuche_lesen() if v.get("sharpe_tag") is not None]
    schiefe, kurtosis = momente(r - rf) if len(r) else (0.0, 3.0)
    dsr = deflated_sharpe(sr_tag, len(r), schiefe, kurtosis, versuche) if sr_tag is not None else None
    jahre = len(tage) / statistik.TAGE_JE_JAHR
    return {"strategie": strategie.name, "parameter": strategie.parameter(), "beschreibung": strategie.beschreibung,
            "erstellt": g.iso(g.jetzt()), "kapital": str(kapital), "benchmark_ticker": benchmark,
            "kosten": {"gebuehren": str(erg.gebuehren), "spreads": str(erg.spreads), "zinsen": str(erg.zinsen),
                       "dividenden": str(erg.dividenden), "umsatz": str(erg.umsatz),
                       "orders": sum(1 for t in erg.trades if t["aktion"] in ("kauf", "verkauf")),
                       "endwert": str(erg.werte[-1]) if erg.werte else None},
            **a, "kurve": kurve(tage, erg, bench),
            "versuche": {"anzahl": len(versuche), "deflated_sharpe": dsr, "sharpe_tag": sr_tag},
            "urteil": urteil(a, dsr, jahre), "grenzen": GRENZEN}


# --------------------------------------------------------------------------
# Walk-forward


def walk_forward(panel: Panel, name: str, gitter: dict[str, list], fest: dict, start: date, ende: date | None = None,
                 train_tage: int = 504, test_tage: int = 126, kapital: Decimal = Decimal("1000.00")) -> dict:
    """Wählt je Fenster die Parameter mit dem besten Sharpe im Training und wendet sie im folgenden Testfenster an.

    Die Testfenster werden aneinandergehängt: das ist die ehrliche Out-of-Sample-Reihe (jede Auswahl nutzt nur
    Daten vor ihrem Testfenster). Gibt Kennzahlen der Reihe und die gewählten Parameter je Fenster zurück.
    """
    klasse = REGISTER[name]
    tage = [t for t in panel.tage if t >= start and (ende is None or t <= ende)]
    kombis = [dict(zip(gitter, werte)) for werte in itertools.product(*gitter.values())] or [{}]
    rf = float(g.D(g.projekt()["risikofreier_zins_pa"])) / statistik.TAGE_JE_JAHR
    fenster, reihe_r, i = [], [], 0
    while i + train_tage + test_tage <= len(tage):
        t0, t1, t2 = tage[i], tage[i + train_tage - 1], tage[i + train_tage + test_tage - 1]
        beste, bester_sr = None, -math.inf
        for k in kombis:
            erg = engine.ausfuehren(panel, klasse(**fest, **k), t0, t1, kapital)
            r = erg.renditen()
            s = (r - rf).std(ddof=1) if len(r) > 2 else 0
            sr = float((r - rf).mean() / s) if s > 0 else -math.inf
            if sr > bester_sr:
                beste, bester_sr = k, sr
        test = engine.ausfuehren(panel, klasse(**fest, **beste), tage[i + train_tage], t2, kapital)
        r_test = test.renditen()
        reihe_r.append(r_test)
        fenster.append({"training": [t0.isoformat(), t1.isoformat()], "test": [tage[i + train_tage].isoformat(), t2.isoformat()],
                        "parameter": beste, "sharpe_training_tag": bester_sr})
        i += test_tage
    if not reihe_r:
        return {"fenster": [], "kennzahlen": {"genug_daten": False, "tage": 0}}
    r = np.concatenate(reihe_r)
    return {"fenster": fenster, "kennzahlen": kennzahlen_fenster(r, None, rf), "tage": int(len(r))}


# --------------------------------------------------------------------------
# Berichte schreiben


def _de(wert, stellen: int = 2) -> str:
    return "–" if wert is None else format(wert, f".{stellen}f").replace(".", ",")


def _mi(k: dict | None, faktor: float = 1.0, stellen: int = 2, einheit: str = "") -> str:
    if not k or k.get("wert") is None:
        return "–"
    text = _de(k["wert"] * faktor, stellen) + einheit
    if k.get("ci"):
        text += f" [{_de(k['ci'][0] * faktor, stellen)}; {_de(k['ci'][1] * faktor, stellen)}]"
    return text


def markdown(b: dict) -> str:
    z = b["zeitraum"]
    zeilen = [f"# Strategie-Labor: {b['strategie']}", "", b["beschreibung"], "",
              f"Parameter: `{json.dumps(b['parameter'], ensure_ascii=False, sort_keys=True)}`  ",
              f"Zeitraum: {z['von']} bis {z['bis']} ({z['tage']} Handelstage), Kapital {b['kapital']} EUR, Benchmark "
              f"{b['benchmark_ticker']} (Buy & Hold, gleiche Kosten).  ",
              f"In-Sample bis {b['in_sample']['bis']} ({b['in_sample']['tage']} Tage), Out-of-Sample ab "
              f"{b['out_of_sample']['von']} ({b['out_of_sample']['tage']} Tage). Erstellt {b['erstellt'][:16]}.", "",
              f"**Ergebnis: {b['urteil']['text']}**", ""]
    if b["urteil"]["gruende"]:
        zeilen += ["Gründe:", ""] + [f"- {x}" for x in b["urteil"]["gruende"]] + [""]
    zeilen += ["In eckigen Klammern das 95-%-Intervall (Block-Bootstrap).", "",
               "| Kennzahl | gesamt | In-Sample | Out-of-Sample |", "| --- | ---: | ---: | ---: |"]
    for name, schluessel, faktor, einheit in [
            ("Rendite p. a. (%)", "rendite_pa", 100, ""), ("Überrendite p. a. gegen Benchmark (%)", "ueberrendite_pa", 100, ""),
            ("Sharpe Ratio", "sharpe", 1, ""), ("Information Ratio", "information_ratio", 1, ""),
            ("Alpha p. a. (%)", "alpha_pa", 100, ""), ("Beta", "beta", 1, ""), ("Sortino", "sortino", 1, ""),
            ("Calmar", "calmar", 1, "")]:
        zeilen.append(f"| {name} | " + " | ".join(_mi(b[f].get(schluessel), faktor, 2) for f in ("gesamt", "is", "oos")) + " |")
    zeilen.append("| Max. Drawdown (%) | " + " | ".join(_de(100 * b[f]["max_drawdown"], 1) if b[f].get("max_drawdown") is not None
                                                      else "–" for f in ("gesamt", "is", "oos")) + " |")
    k = b["kosten"]
    zeilen += ["", f"Kosten: Gebühren {k['gebuehren']} EUR, Spreads {k['spreads']} EUR, Umsatz {k['umsatz']} EUR, "
                   f"{k['orders']} Orders; Zinsen {k['zinsen']} EUR, Dividenden {k['dividenden']} EUR; Endwert {k['endwert']} EUR.",
               f"Getestete Varianten insgesamt: {b['versuche']['anzahl']}; Deflated Sharpe: {_de(b['versuche']['deflated_sharpe'])} "
               f"(Wahrscheinlichkeit, dass der wahre Sharpe über 0 liegt, nach Korrektur für die Zahl der Versuche; "
               f"Vorschlag ab {_de(DSR_SCHWELLE)}).", "", "## Grenzen", ""]
    zeilen += [f"- {x}" for x in b["grenzen"]]
    return "\n".join(zeilen) + "\n"


def speichern(b: dict, heute: date | None = None) -> tuple:
    heute = heute or g.heute()
    ordner = pfad_labor()
    ordner.mkdir(parents=True, exist_ok=True)
    stamm = f"{b['strategie']}_{heute.isoformat()}"
    json_datei, md_datei = ordner / f"{stamm}.json", ordner / f"{stamm}.md"
    g.json_schreiben(json_datei, b)
    g.atomar_schreiben(md_datei, markdown(b))
    return json_datei, md_datei


def berichte_liste() -> list[dict]:
    ordner = pfad_labor()
    if not ordner.exists():
        return []
    liste = []
    for datei in sorted(ordner.glob("*.json"), reverse=True):
        try:
            b = json.loads(datei.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if "strategie" in b and "urteil" in b:
            liste.append({"datei": datei.name, "strategie": b["strategie"], "erstellt": b["erstellt"],
                          "urteil": b["urteil"]["text"], "zeitraum": b["zeitraum"], "parameter": b["parameter"]})
    return liste


# --------------------------------------------------------------------------
# Kostenvarianten (Auslegungsfrage Kapital und Gebühren)

KOSTEN_VARIANTEN = [
    # Name, Startkapital, Gebührenfunktion (None = feste Gebühr je Order aus config/kosten.json, also heute)
    ("heute: 1.000 EUR, 1 EUR je Order", Decimal("1000"), None),
    ("1.000 EUR, 0,1 % mit Mindestgebühr 1 EUR", Decimal("1000"), (Decimal("0.001"), Decimal("1"))),
    ("50.000 EUR, 1 EUR je Order", Decimal("50000"), None),
    ("50.000 EUR, 0,1 % mit Mindestgebühr 1 EUR", Decimal("50000"), (Decimal("0.001"), Decimal("1"))),
    ("100.000 EUR, 1 EUR je Order", Decimal("100000"), None),
    ("100.000 EUR, 0,1 % mit Mindestgebühr 1 EUR", Decimal("100000"), (Decimal("0.001"), Decimal("1"))),
]


def _gebuehr_prozent(satz: Decimal, minimum: Decimal):
    return lambda betrag: max(minimum, abs(betrag) * satz)


def kostenvergleich(panel: Panel, strategien: dict, start: date, ende: date | None = None) -> list[dict]:
    """Kosten je Strategie und Variante auf denselben Kursen: wie viel Rendite p. a. frisst die Kostenstruktur?

    `strategien`: Name -> Funktion ohne Argument, die eine frische Strategie baut. Gibt je Zeile Kosten in EUR und in
    Prozent des Kapitals p. a., Orders und Endwert zurück; `ohne_kosten` ist derselbe Lauf ohne Gebühren und Spread.
    """
    zeilen = []
    for name, fabrik in strategien.items():
        for variante, kapital, gebuehr in KOSTEN_VARIANTEN:
            funktion = _gebuehr_prozent(*gebuehr) if gebuehr else None
            erg = engine.ausfuehren(panel, fabrik(), start, ende, kapital, gebuehr=funktion)
            jahre = max(len(erg.tage) / statistik.TAGE_JE_JAHR, 1e-9)
            orders = sum(1 for t in erg.trades if t["aktion"] in ("kauf", "verkauf"))
            zeilen.append({"strategie": name, "variante": variante, "kapital": str(kapital), "orders": orders,
                           "gebuehren": str(erg.gebuehren), "spreads": str(erg.spreads),
                           "kosten_pa": float(erg.kosten() / kapital) / jahre, "endwert": str(erg.werte[-1]),
                           "rendite": float(erg.werte[-1] / kapital - 1), "jahre": jahre})
    return zeilen
