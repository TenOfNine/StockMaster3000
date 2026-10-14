"""Statistik mit Unsicherheit: synthetische Reihen, handgerechnete Kennzahlen, Bootstrap, Phasen, Bericht (ohne Netzwerk)."""

import math
from datetime import date, timedelta

import numpy as np
import pytest

import gemeinsam as g
import kurse
import statistik
from test_prognosen import kerzen_schreiben


@pytest.fixture
def einst():
    return {"seed": 3000, "resamples": 500, "konfidenz": 0.95, "min_tage": 20, "trend_tage": 200, "vola_fenster": 20}


def markt_reihe(n=500, seed=1):
    return np.random.default_rng(seed).normal(0.0004, 0.01, n)


def test_rendite_pa_handgerechnet():
    # 252 Tage mit je +0,1 % -> 1,001^252 - 1
    assert statistik.rendite_pa(np.full(252, 0.001)) == pytest.approx(1.001 ** 252 - 1)
    # 126 Tage mit +1 % und 126 Tage -1 % : (1,01*0,99)^126 - 1
    r = np.array([0.01, -0.01] * 126)
    assert statistik.rendite_pa(r) == pytest.approx((1.01 * 0.99) ** 126 - 1)


def test_sharpe_sortino_calmar_drawdown_handgerechnet():
    r = np.array([0.01, -0.02, 0.03, 0.0])
    ueber = r
    assert statistik.sharpe(r, 0.0) == pytest.approx(ueber.mean() / ueber.std(ddof=1) * math.sqrt(252))
    assert statistik.sortino(r, 0.0) == pytest.approx(r.mean() / math.sqrt((0.02 ** 2) / 4) * math.sqrt(252))
    # Verlauf 1,01 / 0,9898 / 1,019494 / 1,019494: tiefster Stand gegen Spitze 1,01
    assert statistik.max_drawdown(r) == pytest.approx(0.9898 / 1.01 - 1)
    assert statistik.calmar(r) == pytest.approx(statistik.rendite_pa(r) / abs(0.9898 / 1.01 - 1))


def test_beta_zwei_wird_erkannt():
    m = markt_reihe()
    r = 2 * m + np.random.default_rng(2).normal(0, 0.002, len(m))
    beta, alpha = statistik.beta_alpha(r, m, 0.0)
    assert float(beta) == pytest.approx(2.0, abs=0.05)
    k = statistik.kennzahlen_reihe(r, m, m, 0.0, {"seed": 3000, "resamples": 500, "konfidenz": 0.95, "min_tage": 20})
    assert k["beta"]["ci"][0] < 2.0 < k["beta"]["ci"][1] or abs(k["beta"]["wert"] - 2) < 0.05


def test_reines_rauschen_hat_kein_signifikantes_alpha(einst):
    m = markt_reihe()
    k = statistik.kennzahlen_reihe(np.random.default_rng(11).normal(0, 0.01, len(m)), m, m, 0.0, einst)
    assert abs(k["alpha_t"]) < 2
    assert k["alpha_pa"]["ci"][0] <= 0 <= k["alpha_pa"]["ci"][1]
    assert k["ueberrendite_pa"]["ci"][0] <= 0 <= k["ueberrendite_pa"]["ci"][1]
    assert k["unterscheidbar"] is False


def test_falsch_positiv_rate_bei_rauschen_ist_klein():
    """Bei reinem Rauschen liegt |t| nur selten über 2 (erwartet rund 5 %, hier großzügig unter 15 %)."""
    m = markt_reihe()
    treffer = sum(abs(statistik.alpha_t(np.random.default_rng(s).normal(0, 0.01, len(m)), m, 0.0)) > 2 for s in range(60))
    assert treffer / 60 < 0.15


def test_deutlich_besser_ist_unterscheidbar(einst):
    rng = np.random.default_rng(3)
    b = rng.normal(0.0, 0.005, 500)
    r = b + 0.002 + rng.normal(0, 0.0005, 500)
    k = statistik.kennzahlen_reihe(r, b, b, 0.0, einst)
    assert k["unterscheidbar"] is True and k["ueberrendite_pa"]["ci"][0] > 0 and k["abstand"] == "besser"
    assert statistik.einordnung({"hinweis": None, "abstand": "schlechter"}) == "vom Benchmark unterscheidbar (schlechter)"
    k2 = statistik.kennzahlen_reihe(b - 0.002 + np.random.default_rng(4).normal(0, 0.0005, 500), b, b, 0.0, einst)
    assert k2["abstand"] == "schlechter"
    assert k["trefferquote"]["wert"] > 0.9


def test_bootstrap_ist_deterministisch(einst):
    r = markt_reihe(200)
    a = statistik.kennzahlen_reihe(r, None, None, 0.0, einst)
    b = statistik.kennzahlen_reihe(r, None, None, 0.0, einst)
    assert a == b
    anders = statistik.kennzahlen_reihe(r, None, None, 0.0, {**einst, "seed": 4})
    assert anders["sharpe"]["ci"] != a["sharpe"]["ci"] and anders["sharpe"]["wert"] == a["sharpe"]["wert"]


def test_bloecke_zirkulaer_und_gleiche_laenge():
    assert statistik.blocklaenge(1000) == 10 and statistik.blocklaenge(8) == 2
    idx = statistik.ziehungen(50, 20, 1)
    assert idx.shape == (20, 50) and idx.min() >= 0 and idx.max() < 50
    # innerhalb eines Blocks laufen die Indizes aufeinander folgend (modulo n)
    laenge = statistik.blocklaenge(50)
    assert np.all((idx[:, 1:laenge] - idx[:, 0:laenge - 1]) % 50 == 1)


def test_intervall_wird_mit_mehr_daten_enger(einst):
    breit = statistik.kennzahlen_reihe(markt_reihe(60), None, None, 0.0, einst)["sharpe"]["ci"]
    eng = statistik.kennzahlen_reihe(markt_reihe(1200), None, None, 0.0, einst)["sharpe"]["ci"]
    assert eng[1] - eng[0] < breit[1] - breit[0]


def test_zu_wenig_daten(einst):
    k = statistik.kennzahlen_reihe(markt_reihe(10), None, None, 0.0, einst)
    assert k == {"tage": 10, "genug_daten": False}


def test_ausrichten_mehrtagesrenditen():
    tage, (a, b) = statistik.ausrichten({"2026-10-02": 100.0, "2026-10-03": 101.0, "2026-10-05": 103.02},
                                        {"2026-10-02": 50.0, "2026-10-05": 55.0, "2026-10-09": 1.0})
    assert tage == ["2026-10-05"] and a[0] == pytest.approx(0.0302) and b[0] == pytest.approx(0.1)


def historie_schreiben(tage=260, trend="auf"):
    start = date(2025, 10, 1)
    schluesse, kurs, d = {}, 100.0, start
    while len(schluesse) < tage:
        if d.weekday() < 5:
            kurs *= 1.002 if (trend == "auf" or len(schluesse) < 200) else 0.99
            schluesse[d.isoformat()] = f"{kurs:.4f}"
        d += timedelta(days=1)
    kerzen_schreiben("EUNL.DE", schluesse)
    return sorted(schluesse)


def test_marktphasen_trend_ohne_look_ahead(projekt, einst):
    daten = historie_schreiben(260, "ab")
    phasen = statistik.phasen_je_tag(daten[205:215], einst)
    assert phasen[daten[205]]["trend"] in ("ueber", "unter")
    # der Tag vor dem Einbruch gilt noch als Aufwärtstrend; nach einigen Verlusttagen kippt es
    assert phasen[daten[205]]["trend"] == "ueber"
    spaet = statistik.phasen_je_tag(daten[250:260], einst)
    assert spaet[daten[259]]["trend"] == "unter"
    # Tage ohne 200 Tage Vorlauf bekommen keine Phase
    assert daten[100] not in (statistik.phasen_je_tag(daten[100:101], einst) or {})


def test_marktphasen_ohne_historie(projekt, einst):
    assert statistik.phasen_je_tag(["2026-10-01"], einst) is None


def spiel_daten(projekt, tage=40, vorsprung=0.0):
    """NAV-Dateien und benchmark.csv für zwei Profile über aufeinander folgende Wochentage."""
    kopf = ["datum", "cash", "positionswert", "portfoliowert", "hoechststand", "drawdown", "drawdown_stufe", "exposure",
            "cashquote", "zertifikate_anteil", "status"]
    rng = np.random.default_rng(5)
    markt = np.cumprod(1 + rng.normal(0.0003, 0.008, tage)) * 100
    d, daten = date(2026, 8, 3), []
    while len(daten) < tage:
        if d.weekday() < 5:
            daten.append(d.isoformat())
        d += timedelta(days=1)
    bench = [{"datum": t, "etf_kurs": f"{m:.4f}", **{p: f"{1000 * m / markt[0]:.2f}" for p in g.profile()}}
             for t, m in zip(daten, markt)]
    g.csv_schreiben(g.pfad("data", "benchmark.csv"), ["datum", "etf_kurs", *g.profile()], bench)
    for profil in ("defensiv", "ausgewogen"):
        werte = [1000 * m / markt[0] * (1 + vorsprung) ** i for i, m in enumerate(markt)]
        g.csv_schreiben(g.pfad("data", "nav", f"{profil}.csv"), kopf, [
            {"datum": t, "cash": "0", "positionswert": "0", "portfoliowert": f"{w:.2f}", "hoechststand": f"{w:.2f}",
             "drawdown": "0", "drawdown_stufe": "0", "exposure": "0", "cashquote": "1", "zertifikate_anteil": "0",
             "status": "aktiv"} for t, w in zip(daten, werte)])
    return daten


def test_berechnen_und_bericht(projekt, uhr, einst):
    from helfer import portfolio

    portfolio("defensiv")
    portfolio("ausgewogen")
    spiel_daten(projekt)
    e = statistik.berechnen()
    k = e["profile"]["ausgewogen"]
    assert k["genug_daten"] and k["tage"] == 39 and k["belastbar"] is False
    assert k["beta"]["wert"] == pytest.approx(1.0, abs=0.05)
    assert k["hinweis"] == statistik.HINWEIS_UNSICHER  # Überrendite 0: nicht unterscheidbar
    assert "phasen" in k and "hinweis" in k["phasen"]  # keine 200 Tage Historie
    assert statistik.ergebnis_pfad().exists()
    text = "\n".join(statistik.ranking_abschnitt(e))
    assert "noch nicht vom Benchmark unterscheidbar" in text and "Information Ratio" in text and "[" in text
    assert "kaum belastbar" in text  # unter 60 Handelstagen


def test_ueberrendite_mit_vorsprung_ist_unterscheidbar(projekt, uhr):
    from helfer import portfolio

    portfolio("defensiv")
    portfolio("ausgewogen")
    spiel_daten(projekt, tage=80, vorsprung=0.002)
    k = statistik.berechnen()["profile"]["ausgewogen"]
    assert k["unterscheidbar"] is True and k["hinweis"] is None


def test_bericht_ohne_daten(projekt, uhr):
    assert "Noch zu wenige Handelstage" in "\n".join(statistik.ranking_abschnitt(statistik.berechnen()))


def test_hebel_ist_kein_koennen_beta_angepasste_benchmark(einst):
    """Doppelter Markt: roh deutlich über der Benchmark, gegen die beta-angepasste Benchmark kein Vorsprung."""
    m = np.random.default_rng(1).normal(0.0015, 0.008, 750)
    r = 2 * m + np.random.default_rng(2).normal(0, 0.0005, 750)
    k = statistik.kennzahlen_reihe(r, m, m, 0.0, einst)
    assert k["ueberrendite_pa"]["ci"][0] > 0 and k["abstand"] == "besser"           # roh: scheinbar besser
    assert k["ueberrendite_beta_pa"]["ci"][1] < 0.02  # beta-angepasst: kein Vorsprung (nur etwas Volatilitätsabzug)
    assert abs(k["ueberrendite_beta_pa"]["wert"]) < 0.1 * abs(k["ueberrendite_pa"]["wert"])
    assert abs(k["ueberrendite_vola_pa"]["wert"]) < 0.1 * abs(k["ueberrendite_pa"]["wert"])


def test_echtes_alpha_bleibt_nach_beta_anpassung(einst):
    m = np.random.default_rng(1).normal(0.0015, 0.008, 750)
    r = 2 * m + 0.0008 + np.random.default_rng(2).normal(0, 0.0005, 750)  # zusätzlich +0,08 % je Tag
    k = statistik.kennzahlen_reihe(r, m, m, 0.0, einst)
    assert k["ueberrendite_beta_pa"]["ci"][0] > 0.1 and k["alpha_pa"]["ci"][0] > 0.1


def test_ranking_nach_beta_angepasster_ueberrendite(projekt, uhr):
    from helfer import portfolio

    portfolio("defensiv")
    portfolio("ausgewogen")
    spiel_daten(projekt, tage=80, vorsprung=0.002)
    e = statistik.berechnen()
    assert e["rang_beta_angepasst"] and set(e["rang_beta_angepasst"]) <= {"defensiv", "ausgewogen"}
    text = "\n".join(statistik.ranking_abschnitt(e))
    assert "beta-angepasste Benchmark" in text and "gleicher Schwankung" in text
