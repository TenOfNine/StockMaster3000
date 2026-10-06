"""AP5: Orders und Buchung."""

from decimal import Decimal

import pytest

import buchen
import gemeinsam as g
from helfer import journal, laden, portfolio, sperre


@pytest.fixture
def bereit(projekt, quelle, uhr):
    uhr.stellen("2026-10-12T10:05:00")
    portfolio()
    journal(projekt, eintraege=(("01", "10:00", "ausgewogen", "SAP.DE"), ("02", "10:01", "ausgewogen", "DAX KO"),
                                ("03", "10:02", "ausgewogen", "SAP.DE Verkauf"),
                                ("04", "10:03", "ausgewogen", "AAPL")))
    sperre(projekt)
    quelle.kurs("SAP.DE", "200")
    quelle.kurs("^GDAXI", "20000")
    quelle.kurs("AAPL", "220")
    quelle.kurs("EURUSD=X", "1.10")
    return projekt


def kaufen(*extra, profil="ausgewogen", journal_id="J-20261012-01", ticker="SAP.DE", einsatz="200", stop="190",
           kursziel="230"):
    argv = ["kaufen", "--profil", profil, "--typ", "aktie", "--ticker", ticker, "--einsatz", einsatz,
            "--stop", stop, "--kursziel", kursziel, "--journal-id", journal_id, *extra]
    return buchen.main(argv)


def test_sofortige_ausfuehrung_bei_offenem_markt(bereit):
    assert kaufen() == 0
    p = laden()
    # Kaufkurs 200 * 1,0005 = 200,10; Stück = 200 / 200,10 = 0,999500 (abgerundet)
    position = p["positionen"][0]
    assert position["stueck"] == "0.999500"
    assert Decimal(position["einstand"]) == Decimal("200.1")
    kurswert = (Decimal("0.9995") * Decimal("200.1")).quantize(Decimal("0.01"))
    assert Decimal(p["cash"]) == Decimal("1000") - kurswert - 1
    zeilen = g.trades_lesen("ausgewogen")
    assert len(zeilen) == 1
    zeile = zeilen[0]
    assert zeile["aktion"] == "kauf" and zeile["grund"] == "order" and zeile["journal_id"] == "J-20261012-01"
    assert zeile["kursquelle"] == "kurse" and zeile["kurs_basiswert"] == "200.000000"
    assert Decimal(zeile["betrag_eur"]) == -(kurswert + 1)
    assert zeile["cash_danach"] == p["cash"]
    assert Decimal(zeile["spread_eur"]) == Decimal("0.10")
    # Kurs ist protokolliert
    protokoll = g.csv_lesen(bereit / "data" / "kurse" / "2026-10-12.csv")
    assert any(r["ticker"] == "SAP.DE" and r["zeit"] == zeile["kurs_zeit"] for r in protokoll)
    # Limitprotokoll vorhanden
    assert zeile["trade_id"] in g.limit_protokoll("ausgewogen")


def test_vormerkung_ausserhalb_der_handelszeit(bereit, uhr):
    uhr.stellen("2026-10-12T19:00:00")
    sperre(bereit, start="2026-10-12T18:00:00+02:00")
    assert kaufen() == 0
    p = laden()
    assert p["positionen"] == []
    assert p["cash"] == "1000.00"
    assert len(p["offene_orders"]) == 1
    order = p["offene_orders"][0]
    assert order["art"] == "market" and order["erfasst"] == "2026-10-12T19:00:00+02:00"
    assert g.trades_lesen("ausgewogen")[0]["aktion"] == "vormerkung"


def test_ablehnung_ohne_journal_eintrag(bereit):
    assert kaufen(journal_id="J-20261012-99") == 2
    assert laden()["positionen"] == []
    assert g.trades_lesen("ausgewogen") == []


def test_ablehnung_journal_in_der_zukunft(bereit, uhr):
    uhr.stellen("2026-10-12T10:00:30")
    assert kaufen(journal_id="J-20261012-02") == 2  # Eintrag 10:01


def test_ablehnung_fremde_sperre(bereit, projekt):
    sperre(projekt, person="auftraggeber-b")
    assert kaufen() == 2


def test_ablehnung_ohne_sperre(bereit, projekt):
    (projekt / "session.lock").unlink()
    assert kaufen() == 2


def test_journal_id_nur_einmal(bereit):
    assert kaufen() == 0
    assert kaufen(einsatz="100") == 2


def test_limitverletzung_wird_abgelehnt(bereit):
    assert kaufen(einsatz="400") == 1  # Einzelposition > 25 %
    assert laden()["positionen"] == []


def test_ko_kauf_und_verkauf(bereit):
    assert buchen.main(["kaufen", "--profil", "ausgewogen", "--typ", "ko", "--basiswert", "^GDAXI",
                        "--einsatz", "100", "--hebel", "5", "--stop", "19600", "--kursziel", "21000",
                        "--journal-id", "J-20261012-02"]) == 0
    p = laden()
    position = p["positionen"][0]
    assert position["typ"] == "ko" and Decimal(position["parameter"]["basispreis"]) == Decimal("16000")
    # Wert 4000 je Stück, Kaufkurs 4000 * 1,001 = 4004 -> 0,024975 Stück
    assert position["stueck"] == "0.024975"
    assert Decimal(p["cash"]) == Decimal("1000") - Decimal("100.00") - 1
    bereit_kurs = Decimal("20100")
    from attrappe import AttrappenQuelle  # noqa: F401
    import kurse
    kurse.QUELLE.kurs("^GDAXI", bereit_kurs)
    assert buchen.main(["verkaufen", "--profil", "ausgewogen", "--position-id", position["id"],
                        "--journal-id", "J-20261012-03"]) == 0
    p = laden()
    assert p["positionen"] == []
    # Wert 4100 * 0,999 = 4095,90 * 0,024975 = 102,29
    erloes = (Decimal("0.024975") * Decimal("4095.9")).quantize(Decimal("0.01"))
    assert Decimal(p["cash"]) == Decimal("899.00") + erloes - 1


def test_usd_aktie_vor_us_handelsbeginn_vorgemerkt(bereit):
    # NYSE um 10:05 deutscher Zeit geschlossen -> Vormerkung
    assert kaufen(ticker="AAPL", journal_id="J-20261012-04", stop="210", kursziel="250") == 0
    p = laden()
    assert p["positionen"] == []
    assert p["offene_orders"][0]["basiswert"] == "AAPL"


def test_usd_aktie_sofort(bereit, uhr, quelle):
    uhr.stellen("2026-10-12T16:00:00")
    sperre(bereit, start="2026-10-12T15:00:00+02:00")
    assert kaufen(ticker="AAPL", journal_id="J-20261012-04", stop="210", kursziel="250") == 0
    p = laden()
    position = p["positionen"][0]
    # 220 USD / 1,10 = 200 EUR; Kaufkurs 200,10 EUR
    assert Decimal(position["einstand"]) == Decimal("200.1")
    zeile = g.trades_lesen("ausgewogen")[0]
    assert zeile["devisenkurs"] == "1.100000"


def test_aendern_und_storno(bereit, uhr):
    assert kaufen() == 0
    pid = laden()["positionen"][0]["id"]
    assert buchen.main(["aendern", "--profil", "ausgewogen", "--position-id", pid, "--stop", "195",
                        "--journal-id", "J-20261012-01"]) == 0
    position = laden()["positionen"][0]
    assert position["stop"] == "195" and position["kursziel"] == "230"
    assert len(position["stop_historie"]) == 2
    # Stop über Kurs: abgelehnt
    assert buchen.main(["aendern", "--profil", "ausgewogen", "--position-id", pid, "--stop", "201",
                        "--journal-id", "J-20261012-01"]) == 1
    uhr.stellen("2026-10-12T19:00:00")
    sperre(bereit, start="2026-10-12T18:00:00+02:00")
    assert buchen.main(["verkaufen", "--profil", "ausgewogen", "--position-id", pid,
                        "--journal-id", "J-20261012-03"]) == 0
    order = laden()["offene_orders"][0]
    assert order["aktion"] == "verkauf"
    assert buchen.main(["storno", "--profil", "ausgewogen", "--order-id", order["id"],
                        "--journal-id", "J-20261012-03"]) == 0
    assert laden()["offene_orders"] == []
    assert [z["aktion"] for z in g.trades_lesen("ausgewogen")] == ["kauf", "aenderung", "vormerkung", "storno"]


def test_limit_order_vorgemerkt_wenn_nicht_erreicht(bereit):
    assert kaufen("--limit", "195") == 0
    p = laden()
    assert p["positionen"] == [] and p["offene_orders"][0]["art"] == "limit"
    # Limit über Kurs: sofort zum aktuellen Kurs
    assert kaufen("--limit", "205", journal_id="J-20261012-03") == 0  # Journal 03 gilt für ausgewogen
    assert len(laden()["positionen"]) == 1


def test_nicht_nachgebuchte_tage_blockieren(bereit, uhr):
    uhr.stellen("2026-10-14T10:05:00")
    assert kaufen() == 2
