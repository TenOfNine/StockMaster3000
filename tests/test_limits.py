"""AP4: Je Regel ein Test für Annahme und Ablehnung; Ablehnung nennt Regel, Grenzwert, Istwert."""

from decimal import Decimal

import pytest

import limits
from helfer import aktie, portfolio
from limits import Markt


def zert(id_, typ, richtung, basiswert, stueck, parameter):
    return {"id": id_, "typ": typ, "richtung": richtung, "ticker": f"{typ}-{basiswert}", "basiswert": basiswert,
            "stueck": str(stueck), "einstand": "1", "eroeffnet": "2026-10-01T10:00:00+02:00",
            "parameter": parameter, "stop": None, "kursziel": None, "journal_id": "J-20261001-01",
            "stop_historie": []}


def pruefe(p, typ="aktie", basiswert="SAP.DE", einsatz="100", kurs="100", richtung="long", hebel=None,
           faktor=None, stop="95", kursziel=None, markt=None):
    markt = markt or Markt(kurse={basiswert: Decimal(kurs)}, eurusd=Decimal("1.1"))
    markt.kurse.setdefault(basiswert, Decimal(kurs))
    plan = limits.kaufplan(typ, richtung, basiswert, Decimal(einsatz), Decimal(kurs), hebel=hebel, faktor=faktor,
                           stop=limits.stop_lesen(stop), kursziel=limits.stop_lesen(kursziel))
    verstoesse, kennzahlen = limits.pruefe_kauf(p, plan, markt)
    return {v.regel: v for v in verstoesse}, kennzahlen


def test_annahme_einfacher_kauf(projekt):
    verstoesse, kennzahlen = pruefe(portfolio())
    assert verstoesse == {}
    assert kennzahlen["einsatz"] == Decimal("100.00")


def test_mindestorder(projekt):
    assert "Mindestorder" not in pruefe(portfolio(), einsatz="100")[0]
    v = pruefe(portfolio(), einsatz="99.99")[0]["Mindestorder"]
    assert (v.grenzwert, v.istwert) == ("100.00 EUR", "99.99 EUR")
    assert "Mindestorder: Grenzwert 100.00 EUR, Istwert 99.99 EUR" == str(v)


def test_einzelposition(projekt):
    assert "Einzelposition" not in pruefe(portfolio(), einsatz="240", stop="99")[0]
    v = pruefe(portfolio(), einsatz="260", stop="99")[0]["Einzelposition"]
    assert v.grenzwert == "25.00 %" and v.istwert.startswith("26.")
    # bestehende Position im selben Titel zählt mit
    p = portfolio(cash="850.00", positionen=[aktie("P-0001", "SAP.DE", "1.5")])
    assert "Einzelposition" in pruefe(p, einsatz="120", stop="99")[0]


def test_zertifikate_anteil(projekt):
    # ausgewogen: max 30 %, Hebel 2, Stop weit genug für das Risiko
    assert "Zertifikate-Anteil" not in pruefe(portfolio(profil="aggressiv"), typ="ko", basiswert="^GDAXI",
                                              einsatz="300", kurs="20000", hebel="2", stop="keiner")[0]
    p = portfolio(cash="800.00", positionen=[
        zert("P-0001", "faktor", "long", "^GDAXI", "2", {"faktor": "2", "wert_je_stueck": "100",
                                                          "kurs_ref": "20000", "stand": "2026-10-11"})])
    markt = Markt(kurse={"^GDAXI": Decimal("20000"), "^GSPC": Decimal("5000")}, eurusd=Decimal("1.1"))
    v = pruefe(p, typ="faktor", basiswert="^GSPC", einsatz="150", kurs="5000", faktor="2", stop="4990",
               markt=markt)[0]
    assert v["Zertifikate-Anteil"].grenzwert == "30.00 %"
    assert v["Zertifikate-Anteil"].istwert == "35.03 %"  # (200 + 149,85) / 998,85


def test_hebel(projekt):
    assert "Hebel je Zertifikat" not in pruefe(portfolio(), typ="ko", basiswert="^GDAXI", einsatz="100",
                                               kurs="20000", hebel="5", stop="19900")[0]
    v = pruefe(portfolio(), typ="ko", basiswert="^GDAXI", einsatz="100", kurs="20000", hebel="6",
               stop="19900")[0]["Hebel je Zertifikat"]
    assert (v.grenzwert, v.istwert) == ("5.00x", "6.00x")
    v = pruefe(portfolio(), typ="faktor", basiswert="^GDAXI", einsatz="100", kurs="20000", faktor="8",
               stop="19900")[0]["Hebel je Zertifikat"]
    assert v.istwert == "8.00x"


def test_gesamt_exposure(projekt):
    # defensiv: max 1,2x. Bestehende Aktien 900 EUR -> Exposure 0,9; Faktor 3 mit 100 EUR -> +0,3
    p = portfolio(profil="defensiv", cash="1000.00", positionen=[aktie("P-0001", "SAP.DE", "1")])
    markt = Markt(kurse={"SAP.DE": Decimal("100"), "^GDAXI": Decimal("20000")})
    v, k = pruefe(p, typ="aktie", basiswert="ALV.DE", einsatz="100", kurs="300", stop="299", markt=markt)
    assert "Gesamt-Exposure" not in v
    p = portfolio(profil="defensiv", cash="100.00", positionen=[aktie("P-0001", "SAP.DE", "9")])
    markt = Markt(kurse={"SAP.DE": Decimal("100")})
    v = pruefe(p, typ="faktor", basiswert="^GDAXI", einsatz="100", kurs="20000", faktor="3", stop="19990",
               markt=markt)[0]
    assert v["Gesamt-Exposure"].grenzwert == "1.20x"
    assert v["Gesamt-Exposure"].istwert == "1.21x"  # 1,2004 von der Grenze weg gerundet


def test_mindest_cashquote(projekt):
    p = portfolio(profil="defensiv", cash="300.00", positionen=[aktie("P-0001", "SAP.DE", "7")])
    markt = Markt(kurse={"SAP.DE": Decimal("100")})
    assert "Mindest-Cashquote" not in pruefe(p, basiswert="ALV.DE", einsatz="190", stop="99.5", markt=markt)[0]
    p = portfolio(profil="defensiv", cash="300.00", positionen=[aktie("P-0001", "SAP.DE", "7")])
    v = pruefe(p, basiswert="ALV.DE", einsatz="200", stop="99.5", markt=markt)[0]["Mindest-Cashquote"]
    assert v.grenzwert == "10.00 %" and v.istwert.startswith("9.")


def test_risiko_je_trade_inklusive_kosten(projekt):
    # ausgewogen: 2 % von 1000 = 20 EUR. Einsatz 200, Stop -8 % -> 16 + 2 Gebühren + 0,20 Spread = 18,20
    v, k = pruefe(portfolio(), einsatz="200", stop="92")
    assert "Risiko je Trade" not in v
    assert k["risiko_eur"] == Decimal("18.20")
    # Stop -9 % -> 18 + 2 + 0,20 = 20,20 > 20
    r = pruefe(portfolio(), einsatz="200", stop="91")[0]["Risiko je Trade"]
    assert (r.grenzwert, r.istwert) == ("2.00 %", "2.02 %")


def test_risiko_ohne_stop(projekt):
    # Aktie ohne Stop: 20 % Verlust angenommen -> 100 EUR Einsatz = 20 + 2 + 0,1 > 20
    assert "Risiko je Trade" in pruefe(portfolio(), einsatz="100", stop="keiner")[0]
    # Zertifikat ohne Stop: 100 % -> aggressiv 5 % = 50 EUR erlaubt bei 45 EUR? Mindestorder 100 -> abgelehnt
    v, k = pruefe(portfolio(profil="aggressiv"), typ="ko", basiswert="^GDAXI", einsatz="100", kurs="20000",
                  hebel="5", stop="keiner")
    assert k["verlust_bis_stop"] == Decimal("1")
    assert "Risiko je Trade" in v


def test_risiko_ko_mit_stop(projekt):
    # Long KO Hebel 5 auf 20000: K=16000, Wert 4000; Stop 19600 -> Wert 3600 -> 10 % Verlust
    v, k = pruefe(portfolio(), typ="ko", basiswert="^GDAXI", einsatz="100", kurs="20000", hebel="5", stop="19600")
    assert k["verlust_bis_stop"] == Decimal("0.1")
    assert "Risiko je Trade" not in v


def test_drawdown_stufe(projekt):
    # Stufe 1: Risiko halbiert (1 % statt 2 %)
    v = pruefe(portfolio(stufe=1), einsatz="200", stop="95")[0]
    assert v["Risiko je Trade (Drawdown-Stufe 1: halbiert)"].grenzwert == "1.00 %"
    assert pruefe(portfolio(stufe=1), einsatz="100", stop="95")[0] == {}
    # Stufe 2: keine neuen Zertifikate, Aktien erlaubt
    v = pruefe(portfolio(stufe=2), typ="ko", basiswert="^GDAXI", einsatz="100", kurs="20000", hebel="2",
               stop="19900")[0]
    assert v["Drawdown-Stufe 2"].istwert == "Stufe 2"
    assert pruefe(portfolio(stufe=2), einsatz="100", stop="98")[0] == {}


def test_stop_auf_falscher_seite(projekt):
    assert "Stop" in pruefe(portfolio(), einsatz="100", stop="101")[0]
    assert "Kursziel" in pruefe(portfolio(), einsatz="100", stop="95", kursziel="99")[0]
    assert "Stop" not in pruefe(portfolio(), typ="ko", richtung="short", basiswert="^GDAXI", einsatz="100",
                                kurs="20000", hebel="2", stop="20100")[0]


def test_universum(projekt, quelle):
    assert "Universum" in pruefe(portfolio(), basiswert="VOD.L", einsatz="100")[0]
    assert "Universum (Mindestkurs)" in pruefe(portfolio(), basiswert="PENNY", kurs="0.5", stop="0.49")[0]
    quelle.marktkap["AAPL"] = Decimal("3e12")
    quelle.marktkap["KLEIN"] = Decimal("5e9")
    markt = Markt(kurse={"AAPL": Decimal("200")}, eurusd=Decimal("1.1"))
    assert pruefe(portfolio(), typ="ko", basiswert="AAPL", einsatz="100", kurs="200", hebel="2", stop="199",
                  markt=markt)[0] == {}
    v = pruefe(portfolio(), typ="ko", basiswert="KLEIN", einsatz="100", kurs="50", hebel="2", stop="49.9")[0]
    assert "Universum (Marktkapitalisierung Basiswert)" in v


def test_portfolio_geschlossen(projekt):
    assert "Portfolio-Status" in pruefe(portfolio(status="geschlossen"))[0]


def test_kein_kredit(projekt):
    v = pruefe(portfolio(profil="aggressiv", cash="150.00", positionen=[aktie("P-0001", "SAP.DE", "8.5")]),
               einsatz="150", stop="99", markt=Markt(kurse={"SAP.DE": Decimal("100")}))[0]
    assert v["Kein Kredit"].istwert == "-1.00 EUR"


def test_kennzahlen_protokoll_konsistent(projekt):
    _, kennzahlen = pruefe(portfolio(), einsatz="200", stop="92")
    assert limits.kennzahlen_einhalten(kennzahlen, limits.grenzen("ausgewogen")) == []
    kennzahlen["exposure"] = Decimal("2.5")
    assert limits.kennzahlen_einhalten(kennzahlen, limits.grenzen("ausgewogen")) == ["Gesamt-Exposure"]
