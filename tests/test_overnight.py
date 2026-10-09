"""Umbau v2, Punkt 4: Overnight-Rückblick und Kostenrechnung (tools/overnight.py), ohne Netzwerk."""

import random
from datetime import date, timedelta

import pytest

import beobachtung
import gemeinsam as g
import overnight


def kerzen_reihe(start: date, tage: int, nacht_rendite, tag_rendite=0.0, startkurs=100.0):
    """Werktags-Kerzen: jede Nacht `nacht_rendite(i)`, tagsüber `tag_rendite`."""
    reihe, kurs, tag, i = [], startkurs, start, 0
    while len(reihe) < tage:
        if tag.weekday() < 5:
            offen = kurs * (1 + (nacht_rendite(i) if reihe else 0.0))
            schluss = offen * (1 + tag_rendite)
            reihe.append({"datum": tag, "open": offen, "high": max(offen, schluss) * 1.001, "low": min(offen, schluss) * 0.999,
                          "close": schluss, "volume": 1000.0})
            kurs, i = schluss, i + 1
        tag += timedelta(days=1)
    return reihe


def test_kosten_einer_nacht_entsprechen_dem_kostenmodell(framework, projekt):
    etf = overnight.kosten_einer_nacht("etf", 970.0)
    assert etf["gesamt_anteil"] == pytest.approx(2 / 970 + 0.001)
    assert etf["break_even_basiswert"] == pytest.approx(0.0030619, rel=1e-3)  # rund 0,31 % je Nacht
    ko = overnight.kosten_einer_nacht("ko", 300.0, hebel=3)
    assert ko["spread_anteil"] == 0.002
    assert ko["finanzierung_anteil"] == pytest.approx(2 * 0.04 / 365)
    assert ko["break_even_basiswert"] == pytest.approx(ko["gesamt_anteil"] / 3)
    # die festen Gebühren fressen den Hebel: Break-even des Basiswerts liegt trotz Hebel 3 bei rund 0,3 %
    assert 0.0029 < ko["break_even_basiswert"] < 0.0031
    tabelle = overnight.kosten_tabelle()
    assert {z["variante"] for z in tabelle} == {"etf_1", "etf_2", "ko_3"}
    assert next(z for z in tabelle if z["variante"] == "etf_2")["kosten_eur"] == pytest.approx(4.97, abs=0.01)


def test_naechte_wochenende_und_statistik():
    reihe = kerzen_reihe(date(2026, 1, 5), 12, lambda i: 0.001 * (i % 3))
    n = overnight.naechte(reihe)
    assert len(n) == 11 and n[0]["r"] == pytest.approx(reihe[1]["open"] / reihe[0]["close"] - 1)
    assert [x["tage"] for x in n if x["tage"] > 1] == [3, 3]  # zwei Wochenenden
    s = overnight.statistik([-0.01, 0.0, 0.01, 0.02])
    assert s["n"] == 4 and s["mittel"] == pytest.approx(0.005) and s["trefferquote"] == 0.5 and s["minimum"] == -0.01
    assert s["q05"] == pytest.approx(-0.0085)
    assert overnight.statistik([0.1]) is None


def test_netto_haelt_hebel_und_fixe_kosten_auseinander(framework, projekt):
    r = [0.0, 0.01]
    etf = overnight.netto(r, "etf", 1, 970.0)
    assert etf[0] == pytest.approx(-(2 / 970 + 0.001)) and etf[1] == pytest.approx(0.01 - (2 / 970 + 0.001))
    ko = overnight.netto(r, "ko", 3, 300.0, tage=[1, 3])
    assert ko[1] == pytest.approx(3 * 0.01 - 2 / 300 - 0.002 - 2 * 0.04 / 365 * 3)


def test_auswerten_verlangt_genug_naechte_und_trennt_training_und_test(framework, projekt):
    kurz = kerzen_reihe(date(2026, 1, 5), 50, lambda i: 0.0)
    assert overnight.auswerten("X", kurz) is None
    # stabile Nachtrendite von 0,5 % pro Nacht: nach Kosten (rund 0,31 %) positiv in Training und Test
    gut = kerzen_reihe(date(2025, 1, 6), 260, lambda i: 0.005)
    a = overnight.auswerten("GUT", gut)
    assert a["varianten"]["etf_1"]["positiv_in_beiden"] is True
    assert a["training"]["n"] > a["test"]["n"] and a["wochenende"]["n"] > 0 and a["wochentag"]["n"] > 0
    # Nachtrendite von 0,03 % (Größenordnung, die man für breite Indizes erwartet): nach Kosten negativ
    schlecht = kerzen_reihe(date(2025, 1, 6), 260, lambda i: 0.0003)
    b = overnight.auswerten("SCHLECHT", schlecht)
    assert b["varianten"]["etf_1"]["positiv_in_beiden"] is False and b["varianten"]["etf_1"]["test_netto"] < 0
    # Kandidat nur, wenn auch der Test positiv ist: erst gut, dann schlecht
    wechsel = kerzen_reihe(date(2025, 1, 6), 260, lambda i: 0.005 if i < 180 else -0.002)
    c = overnight.auswerten("WECHSEL", wechsel)
    assert c["varianten"]["etf_1"]["training_netto"] > 0 and c["varianten"]["etf_1"]["positiv_in_beiden"] is False


def test_us_korrelation_fuer_xetra_werte(framework, projekt):
    zufall = random.Random(3)
    us = kerzen_reihe(date(2025, 1, 6), 260, lambda i: 0.0, tag_rendite=0.0)
    for k in us:  # US-Sitzung mit Zufallsbewegung
        k["close"] = k["open"] * (1 + zufall.uniform(-0.01, 0.01))
    bewegung = {k["datum"]: k["close"] / k["open"] - 1 for k in us}
    xetra = kerzen_reihe(date(2025, 1, 6), 260, lambda i: 0.0)
    datum = [k["datum"] for k in xetra]
    # die Nacht nach Tag t folgt der US-Sitzung von t mit Faktor 0,8
    for i in range(len(xetra) - 1):
        xetra[i + 1]["open"] = xetra[i]["close"] * (1 + 0.8 * bewegung[datum[i]])
    w = overnight.auswerten("DAX.DE", xetra, us)
    assert w["us_korrelation"] > 0.95
    assert "us_korrelation" not in overnight.auswerten("AAPL", xetra, us)  # nur Xetra-Werte


def test_analyse_ausfuehren_speichert_ergebnis_und_zeigt_es_an(framework, projekt, uhr, monkeypatch, capsys):
    def holen(tickers):
        zufall = random.Random(1)
        return {t: kerzen_reihe(date(2025, 1, 6), 260, lambda i: zufall.uniform(-0.004, 0.005)) for t in tickers[:40]}

    monkeypatch.setattr(beobachtung, "HOLEN", holen)
    assert overnight.main(["analyse", "--liste", "dax40"]) == 0
    assert "Werten ausgewertet" in capsys.readouterr().out
    e = overnight.ergebnis_lesen()
    assert e["ausgewertet"] > 0 and set(e["zusammenfassung"]) >= {"etf_1", "etf_2", "ko_3", "brutto"}
    assert overnight.main(["ergebnis"]) == 0
    text = capsys.readouterr().out
    assert "Break-even" in text and "etf_1: Median der Netto-Rendite je Nacht im Test" in text and "Zufallstreffer" in text
    assert overnight.main(["kosten"]) == 0


def test_ergebnis_ohne_analyse_und_ohne_daten_meldet_klar(framework, projekt, monkeypatch, capsys):
    assert overnight.main(["ergebnis"]) == 1 and "Noch keine Overnight-Analyse" in capsys.readouterr().err
    monkeypatch.setattr(beobachtung, "HOLEN", lambda tickers: {})
    assert overnight.main(["analyse"]) == 1 and "Keine Kursdaten" in capsys.readouterr().err
