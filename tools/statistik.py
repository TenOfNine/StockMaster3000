#!/usr/bin/env python3
"""Ehrliche Statistik (Strategie-Labor L3): Kennzahlen mit Unsicherheit statt Punktwerten.

Alle Kennzahlen kommen mit einem 95-%-Intervall aus einem Block-Bootstrap über die Tagesrenditen (zirkuläre Blöcke der
Länge n^(1/3), feste Zufallszahlen: gleiche Daten ergeben immer dieselben Intervalle). Eine Rendite ist erst dann "vom
Benchmark unterscheidbar", wenn das Intervall der Überrendite die 0 nicht enthält; bis dahin steht im Bericht "noch nicht
vom Benchmark unterscheidbar". Das ist Statistik zur Orientierung, kein Beweis: mit wenigen Monaten Daten und einer
Handvoll Trades bleiben fast alle Intervalle breit (für einen Sharpe-Unterschied von 0,5 braucht es rund 15 Jahre).

Kennzahlen: Rendite p. a., Sharpe, Überrendite gegen die Benchmark des Profils, Trefferquote (Anteil der Tage über der
Benchmark), Alpha und Beta gegen den Weltaktien-ETF (Regression der Überrenditen über dem risikofreien Zins), Information
Ratio, Sortino, Calmar. Marktphasen: Trend (Benchmark über oder unter ihrer 200-Tage-Linie, Stand des Vortags) und
Schwankung (rollende Streuung hoch oder niedrig gegen den Median der gespeicherten Historie; beschreibend).

    python tools/statistik.py berechnen [--json]   data/statistik.json schreiben
    python tools/statistik.py anzeigen             gespeichertes Ergebnis zeigen
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import sys
from datetime import date

import numpy as np

import gemeinsam as g
import kurse
from gemeinsam import Fehler

TAGE_JE_JAHR = 252
HINWEIS_UNSICHER = "noch nicht vom Benchmark unterscheidbar"


def ergebnis_pfad():
    return g.pfad("data", "statistik.json")


def einstellungen() -> dict:
    return {"seed": 3000, "resamples": 2000, "konfidenz": 0.95, "min_tage": 20, "trend_tage": 200, "vola_fenster": 20,
            **g.projekt().get("statistik", {})}


# --------------------------------------------------------------------------
# Kennzahlen (vektorisiert über die letzte Achse: eine Reihe oder viele Neuziehungen auf einmal)


def rendite_pa(r: np.ndarray) -> np.ndarray:
    n = r.shape[-1]
    return np.expm1(np.log1p(np.clip(r, -0.999999, None)).sum(axis=-1) * TAGE_JE_JAHR / n)


def sharpe(r: np.ndarray, rf: float) -> np.ndarray:
    ueber = r - rf
    s = ueber.std(axis=-1, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(s > 0, ueber.mean(axis=-1) / s * math.sqrt(TAGE_JE_JAHR), np.nan)


def ueberrendite_pa(r: np.ndarray, b: np.ndarray) -> np.ndarray:
    return rendite_pa(r) - rendite_pa(b)


def trefferquote(r: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (r > b).mean(axis=-1)


def beta_alpha(r: np.ndarray, markt: np.ndarray, rf: float) -> tuple[np.ndarray, np.ndarray]:
    """Beta und Alpha p. a. aus der Regression der Überrendite des Portfolios auf die des Marktes."""
    y, x = r - rf, markt - rf
    xm, ym = x.mean(axis=-1), y.mean(axis=-1)
    varianz = ((x - xm[..., None]) ** 2).mean(axis=-1)
    with np.errstate(divide="ignore", invalid="ignore"):
        beta = np.where(varianz > 0, ((x - xm[..., None]) * (y - ym[..., None])).mean(axis=-1) / varianz, np.nan)
    return beta, (ym - beta * xm) * TAGE_JE_JAHR


def information_ratio(r: np.ndarray, b: np.ndarray) -> np.ndarray:
    aktiv = r - b
    s = aktiv.std(axis=-1, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(s > 0, aktiv.mean(axis=-1) / s * math.sqrt(TAGE_JE_JAHR), np.nan)


def sortino(r: np.ndarray, rf: float) -> np.ndarray:
    ueber = r - rf
    unten = np.sqrt((np.minimum(ueber, 0) ** 2).mean(axis=-1))
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(unten > 0, ueber.mean(axis=-1) / unten * math.sqrt(TAGE_JE_JAHR), np.nan)


def max_drawdown(r: np.ndarray) -> np.ndarray:
    verlauf = np.cumprod(1 + r, axis=-1)
    spitze = np.maximum.accumulate(np.concatenate([np.ones(verlauf.shape[:-1] + (1,)), verlauf], axis=-1), axis=-1)[..., 1:]
    return (verlauf / spitze - 1).min(axis=-1)


def calmar(r: np.ndarray) -> np.ndarray:
    dd = max_drawdown(r)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(dd < 0, rendite_pa(r) / np.abs(dd), np.nan)


def alpha_t(r: np.ndarray, markt: np.ndarray, rf: float) -> float:
    """t-Wert des Alphas (gewöhnliche Regression); |t| unter etwa 2 heißt: nicht von 0 zu unterscheiden."""
    y, x = r - rf, markt - rf
    n = len(y)
    if n < 4 or x.std() == 0:
        return float("nan")
    beta, alpha_pa = beta_alpha(y + rf, x + rf, rf)
    alpha = float(alpha_pa) / TAGE_JE_JAHR
    rest = y - alpha - float(beta) * x
    se = math.sqrt(rest.var(ddof=2) * (1 / n + x.mean() ** 2 / ((x - x.mean()) ** 2).sum()))
    return alpha / se if se > 0 else float("nan")


# --------------------------------------------------------------------------
# Block-Bootstrap


def blocklaenge(n: int) -> int:
    return max(1, round(n ** (1 / 3)))


def ziehungen(n: int, anzahl: int, seed: int) -> np.ndarray:
    """Indexmatrix (anzahl x n) für den zirkulären Block-Bootstrap; dieselben Indizes für alle gemeinsam gezogenen Reihen."""
    laenge = blocklaenge(n)
    bloecke = math.ceil(n / laenge)
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, size=(anzahl, bloecke))
    return ((starts[:, :, None] + np.arange(laenge)[None, None, :]) % n).reshape(anzahl, bloecke * laenge)[:, :n]


def intervall(werte: np.ndarray, konfidenz: float) -> list[float] | None:
    werte = werte[np.isfinite(werte)]
    if len(werte) < 10:
        return None
    unten = (1 - konfidenz) / 2
    return [float(np.quantile(werte, unten)), float(np.quantile(werte, 1 - unten))]


def mit_intervall(wert, ziehung: np.ndarray | None, konfidenz: float) -> dict:
    wert = float(wert)
    return {"wert": None if math.isnan(wert) else wert,
            "ci": intervall(ziehung, konfidenz) if ziehung is not None else None}


def kennzahlen_reihe(r: np.ndarray, b: np.ndarray | None, markt: np.ndarray | None, rf: float, einst: dict,
                     mit_ci: bool = True) -> dict:
    """Alle Kennzahlen einer Reihe von Tagesrenditen. `b`: Benchmark des Profils, `markt`: Weltaktien-ETF."""
    n = len(r)
    ergebnis: dict = {"tage": n}
    if n < int(einst["min_tage"]):
        return {**ergebnis, "genug_daten": False}
    idx = ziehungen(n, int(einst["resamples"]), int(einst["seed"])) if mit_ci else None
    kz = float(einst["konfidenz"])

    def ci(funktion, *reihen):
        return funktion(*(x[idx] for x in reihen)) if idx is not None else None

    ergebnis["genug_daten"] = True
    ergebnis["rendite_pa"] = mit_intervall(rendite_pa(r), ci(rendite_pa, r), kz)
    ergebnis["sharpe"] = mit_intervall(sharpe(r, rf), ci(lambda x: sharpe(x, rf), r), kz)
    ergebnis["sortino"] = mit_intervall(sortino(r, rf), ci(lambda x: sortino(x, rf), r), kz)
    ergebnis["calmar"] = mit_intervall(calmar(r), ci(calmar, r), kz)
    ergebnis["max_drawdown"] = float(max_drawdown(r))
    if b is not None:
        ergebnis["ueberrendite_pa"] = mit_intervall(ueberrendite_pa(r, b), ci(ueberrendite_pa, r, b), kz)
        ergebnis["trefferquote"] = mit_intervall(trefferquote(r, b), ci(trefferquote, r, b), kz)
        ergebnis["information_ratio"] = mit_intervall(information_ratio(r, b), ci(information_ratio, r, b), kz)
        ue = ergebnis["ueberrendite_pa"]
        ergebnis["unterscheidbar"] = None if ue["ci"] is None else not (ue["ci"][0] <= 0 <= ue["ci"][1])
        ergebnis["abstand"] = None if not ergebnis["unterscheidbar"] else ("besser" if ue["ci"][0] > 0 else "schlechter")
    if markt is not None:
        beta, alpha = beta_alpha(r, markt, rf)
        ergebnis["beta"] = mit_intervall(beta, ci(lambda x, m: beta_alpha(x, m, rf)[0], r, markt), kz)
        ergebnis["alpha_pa"] = mit_intervall(alpha, ci(lambda x, m: beta_alpha(x, m, rf)[1], r, markt), kz)
        ergebnis["alpha_t"] = alpha_t(r, markt, rf)
    return ergebnis


# --------------------------------------------------------------------------
# Daten und Marktphasen


def _werte(zeilen: list[dict], feld: str) -> dict[str, float]:
    return {z["datum"]: float(z[feld]) for z in zeilen if z.get(feld) not in (None, "")}


def ausrichten(*reihen: dict[str, float]) -> tuple[list[str], list[np.ndarray]]:
    """Tagesrenditen auf den gemeinsamen Daten; Lücken (Wochenende, Feiertag) werden zu Mehrtagesrenditen."""
    tage = sorted(set.intersection(*(set(r) for r in reihen)))
    renditen = []
    for r in reihen:
        w = np.array([r[t] for t in tage], dtype=float)
        renditen.append(w[1:] / w[:-1] - 1)
    return tage[1:], renditen


def phasen_je_tag(tage: list[str], einst: dict) -> dict[str, dict[str, str]] | None:
    """Marktphase je Tag aus der gespeicherten Historie des Benchmark-ETF (Stand des Vortags, ohne Netzwerk)."""
    ticker = g.projekt()["benchmark_ticker"]
    kerzen = sorted(kurse.gespeicherte_historie(ticker).values(), key=lambda k: k.datum)
    trend_tage, fenster = int(einst["trend_tage"]), int(einst["vola_fenster"])
    if len(kerzen) < trend_tage + 1:
        return None
    schluss = np.array([float(k.close) for k in kerzen])
    daten = [k.datum.isoformat() for k in kerzen]
    ret = np.diff(schluss) / schluss[:-1]
    ruhe = [np.nan] * fenster + [ret[i - fenster:i].std(ddof=1) for i in range(fenster, len(ret) + 1)]  # Streuung bis Index i
    vola = np.array(ruhe[:len(schluss)])  # vola[i]: Streuung der Renditen bis zum Schluss von daten[i]
    median = np.nanmedian(vola)
    phasen = {}
    for t in tage:
        i = bisect.bisect_left(daten, t) - 1  # letzter Schluss vor dem Tag
        if i < trend_tage - 1:
            continue
        eintrag = {"trend": "ueber" if schluss[i] > schluss[i - trend_tage + 1:i + 1].mean() else "unter"}
        if not np.isnan(vola[i]):
            eintrag["vola"] = "hoch" if vola[i] > median else "niedrig"
        phasen[t] = eintrag
    return phasen


def phasen_kennzahlen(tage: list[str], r: np.ndarray, b: np.ndarray, rf: float, einst: dict) -> dict:
    phasen = phasen_je_tag(tage, einst)
    if phasen is None:
        return {"hinweis": f"Historie des Benchmark-ETF kürzer als {einst['trend_tage']} Handelstage: keine Marktphasen."}
    ergebnis = {}
    for art, werte in (("trend", ("ueber", "unter")), ("vola", ("hoch", "niedrig"))):
        for wert in werte:
            maske = np.array([phasen.get(t, {}).get(art) == wert for t in tage])
            if maske.sum() < int(einst["min_tage"]):
                ergebnis[f"{art}_{wert}"] = {"tage": int(maske.sum()), "genug_daten": False}
                continue
            k = kennzahlen_reihe(r[maske], b[maske], None, rf, einst)
            ergebnis[f"{art}_{wert}"] = k
    return ergebnis


# --------------------------------------------------------------------------
# Auswertung der Profile


def profil_auswerten(profil: str, benchmark: list[dict], einst: dict) -> dict:
    import bewertung  # erst hier: bewertung importiert dieses Modul für den Bericht

    nav = _werte(bewertung.nav_lesen(profil), "portfoliowert")
    bench = _werte(benchmark, profil)
    markt = _werte(benchmark, "etf_kurs")
    if len(nav) < 2 or len(bench) < 2:
        return {"profil": profil, "tage": 0, "genug_daten": False}
    tage, (r, b, m) = ausrichten(nav, bench, markt)
    rf = float(g.D(g.projekt()["risikofreier_zins_pa"])) / TAGE_JE_JAHR
    ergebnis = {"profil": profil, "von": tage[0] if tage else None, "bis": tage[-1] if tage else None,
                **kennzahlen_reihe(r, b, m, rf, einst)}
    if ergebnis.get("genug_daten"):
        ergebnis["phasen"] = phasen_kennzahlen(tage, r, b, rf, einst)
        ergebnis["belastbar"] = len(tage) >= int(g.projekt()["sharpe_min_handelstage"])
        ergebnis["hinweis"] = HINWEIS_UNSICHER if ergebnis.get("unterscheidbar") is not True else None
    return ergebnis


def berechnen(schreiben: bool = True, benchmark: list[dict] | None = None) -> dict:
    import bewertung

    einst = einstellungen()
    if benchmark is None:
        benchmark = g.csv_lesen(g.pfad("data", "benchmark.csv"))
    profile = {p: profil_auswerten(p, benchmark, einst) for p in g.vorhandene_profile()}
    rang = sorted((p for p, k in profile.items() if k.get("genug_daten") and "information_ratio" in k
                   and k["information_ratio"]["wert"] is not None),
                  key=lambda p: profile[p]["information_ratio"]["wert"], reverse=True)
    ergebnis = {"zeit": g.iso(g.jetzt()), "einstellungen": einst, "profile": profile, "rang_information_ratio": rang,
                "hinweise": ["Intervalle: zirkulärer Block-Bootstrap, feste Zufallszahlen, 95 %.",
                             "Rendite allein ist kein Rangkriterium; maßgeblich sind Überrendite und Information Ratio "
                             "mit ihrem Intervall."]}
    if schreiben:
        g.json_schreiben(ergebnis_pfad(), ergebnis)
    return ergebnis


def lesen() -> dict | None:
    datei = ergebnis_pfad()
    return json.loads(datei.read_text(encoding="utf-8")) if datei.exists() else None


# --------------------------------------------------------------------------
# Anzeige


def _de(text: str) -> str:
    return text.replace(".", ",")


def _z(k: dict | None, faktor: float = 1.0, stellen: int = 2, einheit: str = "", vorzeichen: bool = False) -> str:
    if not k or k.get("wert") is None:
        return "–"
    form = f"{{:{'+' if vorzeichen else ''}.{stellen}f}}"
    text = form.format(k["wert"] * faktor) + einheit
    if k.get("ci"):
        text += f" [{form.format(k['ci'][0] * faktor)}; {form.format(k['ci'][1] * faktor)}]".replace("+", "")
    return _de(text)


def einordnung(k: dict) -> str:
    if k.get("hinweis"):
        return HINWEIS_UNSICHER
    return f"vom Benchmark unterscheidbar ({k['abstand']})" if k.get("abstand") else "–"


def ranking_abschnitt(ergebnis: dict | None) -> list[str]:
    zeilen = ["## Statistik mit Unsicherheit", ""]
    profile = (ergebnis or {}).get("profile", {})
    if not any(k.get("genug_daten") for k in profile.values()):
        return zeilen + ["Noch zu wenige Handelstage für Kennzahlen mit Intervall "
                         f"(mindestens {einstellungen()['min_tage']} Tagesrenditen).", ""]
    namen = [p for p in profile if profile[p].get("genug_daten")]
    zeilen += ["In eckigen Klammern das 95-%-Intervall (Block-Bootstrap). Rangfolge nach Information Ratio, nicht nach "
               "Rohrendite.", "",
               "| Kennzahl | " + " | ".join(p.capitalize() for p in namen) + " |", "| --- |" + " ---: |" * len(namen)]
    reihen = [("Handelstage", lambda k: str(k["tage"])),
              ("Rendite p. a. (%)", lambda k: _z(k["rendite_pa"], 100, 1)),
              ("Überrendite p. a. gegen Benchmark (%)", lambda k: _z(k["ueberrendite_pa"], 100, 1, vorzeichen=True)),
              ("Sharpe Ratio", lambda k: _z(k["sharpe"])),
              ("Information Ratio", lambda k: _z(k["information_ratio"])),
              ("Alpha p. a. gegen MSCI World (%)", lambda k: _z(k["alpha_pa"], 100, 1, vorzeichen=True)),
              ("Beta gegen MSCI World", lambda k: _z(k["beta"])),
              ("Sortino", lambda k: _z(k["sortino"])),
              ("Calmar", lambda k: _z(k["calmar"])),
              ("Trefferquote (Tage über Benchmark, %)", lambda k: _z(k["trefferquote"], 100, 0)),
              ("Einordnung", einordnung)]
    for name, f in reihen:
        zeilen.append(f"| {name} | " + " | ".join(f(profile[p]) for p in namen) + " |")
    rang = [p for p in (ergebnis or {}).get("rang_information_ratio", []) if p in namen]
    if rang:
        zeilen += ["", "Rang nach Information Ratio: " + " > ".join(p.capitalize() for p in rang) + "."]
    kurz = [p for p in namen if not profile[p].get("belastbar")]
    if kurz:
        zeilen += ["", "Weniger als " + str(g.projekt()["sharpe_min_handelstage"]) + " Handelstage (kaum belastbar): "
                   + ", ".join(p.capitalize() for p in kurz) + "."]
    zeilen.append("")
    return zeilen


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Kennzahlen mit Konfidenzintervall (Block-Bootstrap).")
    unter = parser.add_subparsers(dest="befehl", required=True)
    p = unter.add_parser("berechnen", help="data/statistik.json schreiben")
    p.add_argument("--json", action="store_true")
    unter.add_parser("anzeigen", help="gespeichertes Ergebnis zeigen")
    args = parser.parse_args(argv)
    try:
        ergebnis = berechnen() if args.befehl == "berechnen" else lesen()
        if ergebnis is None:
            print("Noch kein Ergebnis (python tools/statistik.py berechnen).")
        elif getattr(args, "json", False):
            print(json.dumps(ergebnis, ensure_ascii=False, indent=1))
        else:
            print("\n".join(ranking_abschnitt(ergebnis)))
    except Fehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
