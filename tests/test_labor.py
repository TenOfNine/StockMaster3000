"""Strategie-Labor: Engine mit handgerechneten Fällen, Look-ahead-Test, Strategien, Berichte (ohne Netzwerk)."""

import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pytest

import backtest
import buchen
import gemeinsam as g
from kurse import Kerze
from labor import bericht, daten, engine, strategien
from labor.engine import Strategie, Zielposition

D = Decimal


def werktage(start: date, n: int) -> list[date]:
    tage, t = [], start
    while len(tage) < n:
        if t.weekday() < 5:
            tage.append(t)
        t += timedelta(days=1)
    return tage


def panel_aus(reihen: dict[str, list[tuple]], start=date(2026, 1, 5)) -> daten.Panel:
    """reihen: Ticker -> Liste von (open, high, low, close) je Handelstag."""
    serien = {}
    for ticker, zeilen in reihen.items():
        tage = werktage(start, len(zeilen))
        serien[ticker] = [Kerze(t, D(str(o)), D(str(h)), D(str(l)), D(str(c))) for t, (o, h, l, c) in zip(tage, zeilen)]
    return daten.Panel(serien)


def flach(n, kurs=100):
    return [(kurs, kurs, kurs, kurs)] * n


def zufall(n, seed=1, start=100.0, drift=0.0003, vola=0.01):
    r = np.random.default_rng(seed).normal(drift, vola, n)
    c = start * np.cumprod(1 + r)
    o = np.concatenate([[start], c[:-1]]) * (1 + np.random.default_rng(seed + 100).normal(0, 0.002, n))
    return [(round(float(a), 4), round(float(max(a, b) * 1.003), 4), round(float(min(a, b) * 0.997), 4), round(float(b), 4))
            for a, b in zip(o, c)]


# ----------------------------------------------------------------------------- Ausführung und Kosten


def test_buy_and_hold_ausfuehrung_zur_naechsten_eroeffnung_mit_kosten(projekt):
    reihe = [(100, 100, 100, 100), (101, 101, 101, 101)] + flach(3, 101)
    panel = panel_aus({"AAA.DE": reihe})
    erg = engine.ausfuehren(panel, strategien.BuyAndHold("AAA.DE"), panel.tage[0])
    kauf = next(t for t in erg.trades if t["aktion"] == "kauf")
    assert kauf["punkt"] == 2 and kauf["art"] == "eroeffnung"  # Entscheidung zum Schluss von Tag 0, Ausführung zur Eröffnung von Tag 1
    assert D(kauf["kurs_eur"]) == D("101") * D("1.0005")      # Eröffnung des nächsten Tages plus halber Spread
    # Wert Tag 0: 1000 + Zins für einen Kalendertag; Einsatz = Wert - Gebühr - 0,01
    einsatz = D("1000.05") - D("1.00") - D("0.01")
    stueck = g.stueck_runden(einsatz / (D("101") * D("1.0005")))
    assert D(kauf["stueck"]) == stueck
    assert erg.gebuehren == D("1.00")
    assert erg.spreads == g.geld(stueck * D("101") * D("0.0005"))
    # Wert nach dem Kauf = Wert vorher - Gebühr - Spread (zu Mitte bewertet), bis auf Cent-Rundung
    assert abs(erg.werte[1] - (D("999.05") - erg.spreads)) <= D("0.02")


def test_kosten_stimmen_mit_der_buchungsrechnung(projekt):
    panel = panel_aus({"AAA.DE": flach(4)})
    erg = engine.ausfuehren(panel, strategien.BuyAndHold("AAA.DE"), panel.tage[0])
    r = buchen.kauf_rechnung("etf", D("100"), D(erg.trades[0]["betrag_eur"]).copy_abs() - D("1.00"))
    assert D(erg.trades[0]["stueck"]) == r["stueck"] and erg.trades[0]["gebuehr_eur"] == str(r["gebuehr"])


def test_kosten_aus_der_konfiguration(projekt, framework):
    import json as _j
    datei = framework / "config" / "kosten.json"
    k = _j.loads(datei.read_text(encoding="utf-8"))
    k["gebuehr_je_order"] = "5.00"
    datei.write_text(_j.dumps(k), encoding="utf-8")
    panel = panel_aus({"AAA.DE": flach(4)})
    erg = engine.ausfuehren(panel, strategien.BuyAndHold("AAA.DE"), panel.tage[0])
    assert erg.gebuehren == D("5.00")


def test_cash_zins_je_kalendertag(projekt):
    class NichtsTun(Strategie):
        name, tickers = "nichts", ("AAA.DE",)

        def entscheiden(self, sicht):
            return None

    panel = panel_aus({"AAA.DE": flach(6)})  # Mo bis Mo: 5 Kalendertage mit Wochenende dazwischen
    erg = engine.ausfuehren(panel, NichtsTun(), panel.tage[0])
    # 1000 * 0,02 / 365 = 0,0548 -> 0,05 je Tag (Rundung je Tag): 6 Handelstage, 8 Kalendertage
    assert (panel.tage[-1] - panel.tage[0]).days + 1 == 8
    assert erg.zinsen == D("0.40") and erg.werte[-1] == D("1000.40")


def test_rebalancing_stellt_gewichte_wieder_her(projekt):
    """50/50 aus zwei Werten; A steigt stark, zum Monatsanfang wird auf 50/50 zurückgestellt (Mindestorder 100 EUR)."""
    n = 60
    panel = panel_aus({"AAA.DE": [(100 + 4 * i,) * 4 for i in range(n)], "BBB.DE": flach(n)}, start=date(2026, 1, 5))
    s = strategien.Gemischt({"AAA.DE": 0.5, "BBB.DE": 0.5}, rebalancing="monat")
    erster_monat = next(i for i in range(1, n) if panel.tage[i].month != panel.tage[i - 1].month)
    lauf = engine.Lauf(panel, s, panel.tage[0], panel.tage[erster_monat + 1])
    erg = lauf.ausfuehren()
    kaeufe = [t for t in erg.trades if t["aktion"] == "kauf"]
    verkaeufe = [t for t in erg.trades if t["aktion"] == "verkauf"]
    assert len(kaeufe) >= 3 and verkaeufe  # Erstkauf beider, Umschichtung A -> B
    assert all(D(t["betrag_eur"]).copy_abs() >= 100 for t in kaeufe + verkaeufe)  # Mindestorder gilt auch hier
    p = 2 * (erster_monat + 1) + 1
    wert = lauf._wert(p)
    gewichte = {q["ticker"]: float(D(q["stueck"]) * lauf._mitte_eur(q, p) / wert) for q in lauf.positionen}
    assert abs(gewichte["AAA.DE"] - 0.5) < 0.02


def test_kleine_gewichtsabweichung_loest_keine_order_aus(projekt):
    """Unter der Mindestorder (100 EUR) wird nicht umgeschichtet: Kosten schlagen den Nutzen."""
    n = 60
    panel = panel_aus({"AAA.DE": [(100 + 0.5 * i,) * 4 for i in range(n)], "BBB.DE": flach(n)})
    erg = engine.ausfuehren(panel, strategien.Gemischt({"AAA.DE": 0.5, "BBB.DE": 0.5}, rebalancing="monat"), panel.tage[0])
    assert [t["aktion"] for t in erg.trades] == ["kauf", "kauf"]


def test_zu_kleine_orders_werden_ausgelassen(projekt):
    panel = panel_aus({"AAA.DE": flach(5)})

    class Klein(Strategie):
        name, tickers = "klein", ("AAA.DE",)
        _ok = False

        def entscheiden(self, sicht):
            if self._ok:
                return None
            self._ok = True
            return [Zielposition("AAA.DE", 0.05)]  # 50 EUR < Mindestorder 100

    erg = engine.ausfuehren(panel, Klein(), panel.tage[0])
    assert erg.trades == []


# ----------------------------------------------------------------------------- Overnight und Knock-out


def test_overnight_handgerechnet(projekt):
    # Tag 0: Eröffnung 100 / Schluss 101 -> Kauf zum Schluss 101; Tag 1: Eröffnung 102 -> Verkauf
    reihe = [(100, 101, 100, 101), (102, 103, 101, 101), (101, 101, 101, 101)]
    panel = panel_aus({"AAA.DE": reihe})
    erg = engine.ausfuehren(panel, strategien.Overnight("AAA.DE", gewicht=0.97), panel.tage[0])
    kauf, verkauf = [t for t in erg.trades if t["aktion"] in ("kauf", "verkauf")][:2]
    assert (kauf["punkt"], verkauf["punkt"]) == (1, 2)  # Schluss Tag 0, Eröffnung Tag 1
    einsatz = g.geld(D("0.97") * D("1000.00"))  # Wert vor dem Zins des Tages
    r_k = buchen.kauf_rechnung("etf", D("101"), einsatz)
    r_v = buchen.verkauf_rechnung("etf", D("102"), r_k["stueck"])
    assert D(kauf["betrag_eur"]) == -(r_k["kurswert"] + r_k["gebuehr"])
    assert D(verkauf["betrag_eur"]) == r_v["erloes"] - r_v["gebuehr"]
    # Brutto 102/101 - 1 = +0,99 % auf rund 970 EUR = +9,60 EUR; Kosten: 2 Gebühren und 0,1 % Spread (0,97 EUR)
    netto = D(verkauf["betrag_eur"]) + D(kauf["betrag_eur"])
    assert float(netto) == pytest.approx(970 * (102 / 101 - 1) - 2 - 0.97, abs=0.3)


def test_overnight_stimmt_mit_der_kostenrechnung_von_overnight_py_ueberein(projekt):
    """Eine Nacht im Labor kostet dasselbe wie die Nettorechnung in tools/overnight.py (Gebühren plus Spread)."""
    import overnight

    reihe = [(100, 101, 100, 100), (101, 102, 100, 101), (101, 101, 101, 101)]
    panel = panel_aus({"AAA.DE": reihe})
    erg = engine.ausfuehren(panel, strategien.Overnight("AAA.DE", gewicht=0.97), panel.tage[0])
    kauf, verkauf = [t for t in erg.trades if t["aktion"] in ("kauf", "verkauf")][:2]
    einsatz = -float(D(kauf["betrag_eur"])) - 1.0   # Kurswert ohne Gebühr
    pnl = float(D(verkauf["betrag_eur"]) + D(kauf["betrag_eur"]))
    erwartet = overnight.netto([101 / 100 - 1], "etf", 1, einsatz)[0] * einsatz
    assert pnl == pytest.approx(erwartet, abs=0.05)


def test_knockout_im_tagesverlauf(projekt):
    class KoKauf(Strategie):
        name, tickers, _ok = "ko", ("AAA.DE",), False

        def entscheiden(self, sicht):
            if self._ok:
                return None
            self._ok = True
            return [Zielposition("AAA.DE", 0.3, typ="ko", hebel=D(5))]

    # Kauf zur Eröffnung von Tag 1 bei 100: Basispreis 80; Tag 1 fällt bis 79 -> ausgeknockt
    reihe = [(100, 100, 100, 100), (100, 100, 79, 90), (90, 90, 90, 90), (90, 90, 90, 90)]
    panel = panel_aus({"AAA.DE": reihe})
    lauf = engine.Lauf(panel, KoKauf(), panel.tage[0])
    erg = lauf.ausfuehren()
    kauf = next(t for t in erg.trades if t["aktion"] == "kauf")
    assert D(kauf["stueck"]) > 0
    aus = next(t for t in erg.trades if t["aktion"] == "ausbuchung")
    assert "Tagesverlauf" in aus["grund"] and lauf.positionen == []
    verlust = D(kauf["betrag_eur"])  # Einsatz inklusive Gebühr geht verloren
    assert float(erg.werte[-1]) == pytest.approx(float(D("1000.05") + verlust), abs=0.3)


def test_knockout_durch_eroeffnungsluecke_und_aufzinsung(projekt):
    class KoKauf(Strategie):
        name, tickers, _ok = "ko", ("AAA.DE",), False

        def entscheiden(self, sicht):
            if self._ok:
                return None
            self._ok = True
            return [Zielposition("AAA.DE", 0.3, typ="ko", hebel=D(5))]

    reihe = [(100, 100, 100, 100), (100, 101, 100, 101), (101, 101, 101, 101), (70, 70, 70, 70), (70, 70, 70, 70)]
    panel = panel_aus({"AAA.DE": reihe})
    lauf = engine.Lauf(panel, KoKauf(), panel.tage[0])
    erg = lauf.ausfuehren()
    assert any("Eröffnung" in t["grund"] for t in erg.trades if t["aktion"] == "ausbuchung")
    # Zwischenstand: Barriere wurde je Kalendertag aufgezinst (4 % p. a. auf den Basispreis 80)
    lauf2 = engine.Lauf(panel, KoKauf(), panel.tage[0], panel.tage[2])
    lauf2.ausfuehren()
    pos = lauf2.positionen[0]
    kalendertage = (panel.tage[2] - panel.tage[1]).days + 1  # Kauftag 1 (Eröffnung) bis Tag 2
    erwartet = D(80)
    for _ in range(kalendertage):
        erwartet *= 1 + D("0.04") / 365
    assert float(pos["parameter"]["basispreis"]) == pytest.approx(float(erwartet), rel=1e-6)


# ----------------------------------------------------------------------------- Look-ahead


class Betrueger(Strategie):
    """Schaut in die Zukunft: kauft, wenn der Schluss des nächsten Tages höher liegt."""

    name, punkte = "betrueger", ("close",)

    def __init__(self, panel):
        self.panel, self.tickers = panel, ("AAA.DE",)

    def entscheiden(self, sicht):
        i = sicht.punkt // 2
        if i + 1 >= len(self.panel.tage):
            return None
        return [Zielposition("AAA.DE", 1.0)] if self.panel.kerzen["AAA.DE"][i + 1].close > self.panel.kerzen["AAA.DE"][i].close else []


def test_lookahead_pruefung_erkennt_betrueger(projekt):
    panel = panel_aus({"AAA.DE": zufall(60)})
    assert engine.lookahead_pruefung(Betrueger, panel, punkte=list(range(20, 100, 6)))


@pytest.mark.parametrize("fabrik", [
    lambda p: strategien.BuyAndHold("AAA.DE"),
    lambda p: strategien.Gemischt({"AAA.DE": 0.6, "BBB.DE": 0.4}, rebalancing="woche"),
    lambda p: strategien.Trendfolge("AAA.DE", tage=15, pruefung="taeglich"),
    lambda p: strategien.Momentum(["AAA.DE", "BBB.DE", "CCC.DE"], top_n=2, rueckblick=30, ueberspringen=5),
    lambda p: strategien.Volatilitaetsziel("AAA.DE", fenster=10),
    lambda p: strategien.Overnight("AAA.DE"),
])
def test_eingebaute_strategien_ohne_lookahead(projekt, fabrik):
    panel = panel_aus({"AAA.DE": zufall(120, 1), "BBB.DE": zufall(120, 2), "CCC.DE": zufall(120, 3)})
    assert engine.lookahead_pruefung(fabrik, panel, punkte=list(range(40, 230, 7))) == []


def test_sicht_zeigt_nur_bekanntes(projekt):
    panel = panel_aus({"AAA.DE": [(10, 12, 9, 11), (20, 22, 19, 21), (30, 32, 29, 31)]})
    eroeffnung = engine.Sicht(panel, 2)  # Eröffnung von Tag 1
    assert list(eroeffnung.schluesse("AAA.DE")) == [11.0] and list(eroeffnung.eroeffnungen("AAA.DE")) == [10.0, 20.0]
    assert list(eroeffnung.hochs("AAA.DE")) == [12.0]
    schluss = engine.Sicht(panel, 3)
    assert list(schluss.schluesse("AAA.DE")) == [11.0, 21.0] and eroeffnung.letzter_kurs("AAA.DE") == D(20)


# ----------------------------------------------------------------------------- Strategien


def test_trendfolge_investiert_nur_ueber_der_linie(projekt):
    auf = [(100 + i,) * 4 for i in range(40)]
    ab = [(140 - 2 * i,) * 4 for i in range(40)]
    panel = panel_aus({"AAA.DE": auf + ab})
    erg = engine.ausfuehren(panel, strategien.Trendfolge("AAA.DE", tage=10, pruefung="taeglich"), panel.tage[0])
    arten = [t["aktion"] for t in erg.trades]
    assert arten[0] == "kauf" and "verkauf" in arten  # rein im Aufwärtstrend, raus im Abwärtstrend
    verkauf = next(t for t in erg.trades if t["aktion"] == "verkauf")
    assert panel.tage.index(date.fromisoformat(verkauf["datum"])) >= 40


def test_momentum_waehlt_die_staerksten(projekt):
    n = 70
    panel = panel_aus({"AAA.DE": [(100 + 2 * i,) * 4 for i in range(n)], "BBB.DE": [(100 + i,) * 4 for i in range(n)],
                       "CCC.DE": [(100 - i * 0.5,) * 4 for i in range(n)]})
    s = strategien.Momentum(["AAA.DE", "BBB.DE", "CCC.DE"], top_n=2, rueckblick=30, ueberspringen=5)
    erg = engine.ausfuehren(panel, s, panel.tage[31])
    gekauft = {t["ticker"] for t in erg.trades if t["aktion"] == "kauf"}
    assert gekauft == {"AAA.DE", "BBB.DE"}


def test_volatilitaetsziel_senkt_gewicht_bei_hoher_schwankung(projekt):
    ruhig = panel_aus({"AAA.DE": zufall(60, 1, vola=0.002)})
    wild = panel_aus({"AAA.DE": zufall(60, 1, vola=0.03)})
    gewicht = {}
    for name, panel in (("ruhig", ruhig), ("wild", wild)):
        s = strategien.Volatilitaetsziel("AAA.DE", ziel=0.10, fenster=10)
        ziele = [s.entscheiden(engine.Sicht(panel, p)) for p in range(31, 120, 2)]
        gewicht[name] = [z[0].gewicht for z in ziele if z]
    assert gewicht["ruhig"][0] == 1.0 and gewicht["wild"][0] < 0.5


# ----------------------------------------------------------------------------- Bericht


def test_in_und_out_of_sample_getrennt(projekt):
    panel = panel_aus({"EUNL.DE": zufall(300, 5)})
    b = bericht.lauf_bericht(panel, strategien.BuyAndHold("EUNL.DE"), panel.tage[0], loggen=False)
    z = b["zeitraum"]
    assert b["in_sample"]["tage"] == int(z["tage"] * 0.7) and b["out_of_sample"]["tage"] == z["tage"] - b["in_sample"]["tage"]
    assert b["in_sample"]["bis"] < b["out_of_sample"]["von"]
    assert b["is"]["tage"] == b["in_sample"]["tage"] and b["oos"]["tage"] == b["out_of_sample"]["tage"]
    assert b["urteil"]["vorschlag"] is False and any("weniger als" in x for x in b["urteil"]["gruende"])
    assert "Survivorship" in "".join(b["grenzen"])


def test_deflated_sharpe():
    assert bericht.deflated_sharpe(0.0, 500, 0.0, 3.0, []) == pytest.approx(0.5)
    einzeln = bericht.deflated_sharpe(0.15, 500, 0.0, 3.0, [0.15])
    viele = bericht.deflated_sharpe(0.15, 500, 0.0, 3.0, list(np.linspace(-0.1, 0.1, 100)))
    assert einzeln > 0.99 and viele < einzeln
    assert bericht.deflated_sharpe(0.1, 2, 0, 3, []) is None


def test_versuche_werden_angehaengt(projekt):
    bericht.versuch_loggen("trend", {"tage": 100}, date(2020, 1, 1), date(2021, 1, 1), 0.05)
    bericht.versuch_loggen("trend", {"tage": 200}, date(2020, 1, 1), date(2021, 1, 1), 0.02)
    assert [v["parameter"]["tage"] for v in bericht.versuche_lesen()] == [100, 200]


def test_walk_forward_fenster(projekt):
    panel = panel_aus({"EUNL.DE": zufall(600, 7)})
    ergebnis = bericht.walk_forward(panel, "trend", {"tage": [10, 20]}, {"ticker": "EUNL.DE", "pruefung": "taeglich"},
                                    panel.tage[0], train_tage=200, test_tage=100)
    f = ergebnis["fenster"]
    assert len(f) == 4 and all(x["parameter"]["tage"] in (10, 20) for x in f)
    # Testfenster sind lückenlos und überschneiden sich nicht; jedes beginnt nach seinem Training
    for a, b in zip(f, f[1:]):
        assert a["test"][1] < b["test"][0]
    assert all(x["training"][1] < x["test"][0] for x in f)
    assert ergebnis["tage"] == 400


def test_labor_aendert_keinen_spielstand(projekt, quelle, uhr):
    from helfer import portfolio

    portfolio()
    (projekt / "data" / "historie").mkdir(exist_ok=True)

    def stand():
        return {str(p): hashlib.sha1(p.read_bytes()).hexdigest() for d in ("portfolios", "trades", "journal", "data")
                for p in (projekt / d).rglob("*") if p.is_file()}

    vorher = stand()
    panel = panel_aus({"EUNL.DE": zufall(120, 9)})
    b = bericht.lauf_bericht(panel, strategien.Trendfolge("EUNL.DE", tage=10), panel.tage[0])
    bericht.speichern(b)
    assert stand() == vorher
    assert (projekt / "labor" / f"trend_{g.heute().isoformat()}.json").exists()


def test_cli_ende_zu_ende(projekt, quelle, uhr, capsys):
    uhr.stellen("2027-06-01T10:00")
    tage = werktage(date(2026, 1, 5), 330)
    for t, (o, h, l, c) in zip(tage, zufall(330, 3)):
        quelle.kerze("EUNL.DE", t, o, h, l, c)
    assert backtest.main(["daten", "--ticker", "EUNL.DE", "--von", "2026-01-05"]) == 0
    assert (projekt / "labor" / "daten" / "EUNL.DE.csv").exists()
    assert backtest.main(["ausfuehren", "--strategie", "trend", "--parameter", "tage=10,20", "--fest", "pruefung=taeglich",
                          "--json"]) == 0
    assert '"strategie": "trend"' in capsys.readouterr().out
    datei = projekt / "labor" / f"trend_{g.heute().isoformat()}.json"
    b = json.loads(datei.read_text(encoding="utf-8"))
    assert len(b["varianten"]) == 2 and b["versuche"]["anzahl"] == 2
    assert (projekt / "labor" / f"trend_{g.heute().isoformat()}.md").read_text(encoding="utf-8").startswith("# Strategie-Labor")
    assert backtest.main(["berichte"]) == 0
    assert backtest.main(["ausfuehren", "--strategie", "gibtesnicht"]) == 1


def test_kostenvarianten_gebuehrenmodell(projekt):
    """Bei kleinem Kapital zählt die Mindestgebühr (beide Modelle gleich), bei großem Kapital kostet 0,1 % deutlich mehr."""
    panel = panel_aus({"EUNL.DE": zufall(120, 4), "EUNH.DE": zufall(120, 5)})
    zeilen = bericht.kostenvergleich(panel, {"trend": lambda: strategien.Trendfolge("EUNL.DE", tage=10, pruefung="taeglich")},
                                     panel.tage[0])
    je = {z["variante"]: z for z in zeilen}
    assert je["heute: 1.000 EUR, 1 EUR je Order"]["gebuehren"] == je["1.000 EUR, 0,1 % mit Mindestgebühr 1 EUR"]["gebuehren"]
    fest, prozent = je["100.000 EUR, 1 EUR je Order"], je["100.000 EUR, 0,1 % mit Mindestgebühr 1 EUR"]
    assert D(fest["gebuehren"]) == fest["orders"] * D("1.00")
    assert D(prozent["gebuehren"]) > 20 * D(fest["gebuehren"])  # Orders über 90.000 EUR: rund 90 EUR statt 1 EUR
    assert prozent["kosten_pa"] > fest["kosten_pa"]


def test_cli_kostenvergleich_synthetisch(projekt, capsys):
    assert backtest.main(["kosten", "--synthetisch", "--tage", "80", "--seeds", "1"]) == 0
    ausgabe = capsys.readouterr().out
    assert "| Strategie | Variante |" in ausgabe and "100.000 EUR, 0,1 %" in ausgabe and "Zufallskurse ohne Vorteil" in ausgabe
