"""AP2: Kursdaten, Protokoll, Marktstatus, Umrechnung, Fehlermeldungen."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

import gemeinsam as g
import kurse
from gemeinsam import Fehler, KursFehler


def test_aktueller_kurs_wird_protokolliert(projekt, quelle, uhr):
    uhr.stellen("2026-10-12T10:15:00")
    quelle.kurs("SAP.DE", "200.50")
    ergebnis = kurse.aktuell(["SAP.DE"])[0]
    assert ergebnis.kurs == Decimal("200.5")
    assert ergebnis.waehrung == "EUR"
    assert ergebnis.markt_offen is True
    zeilen = g.csv_lesen(projekt / "data" / "kurse" / "2026-10-12.csv")
    assert zeilen == [{"zeit": "2026-10-12T10:15:00+02:00", "ticker": "SAP.DE", "kurs": "200.500000",
                       "waehrung": "EUR", "quelle": "attrappe", "markt_offen": "ja"}]
    quelle.kurs("AAPL", "180")
    kurse.aktuell(["AAPL"])
    assert len(g.csv_lesen(projekt / "data" / "kurse" / "2026-10-12.csv")) == 2


@pytest.mark.parametrize("ticker,zeit,offen", [
    ("SAP.DE", "2026-10-12T08:59:00", False),
    ("SAP.DE", "2026-10-12T09:00:00", True),
    ("SAP.DE", "2026-10-12T17:29:00", True),
    ("SAP.DE", "2026-10-12T17:30:00", False),
    ("SAP.DE", "2026-10-10T12:00:00", False),       # Samstag
    ("SAP.DE", "2026-12-24T12:00:00", False),       # Feiertag Xetra
    ("^GDAXI", "2026-10-12T12:00:00", True),
    ("AAPL", "2026-10-12T15:29:00", False),         # 09:29 New York
    ("AAPL", "2026-10-12T15:30:00", True),          # 09:30 New York
    ("AAPL", "2026-10-12T21:59:00", True),
    ("AAPL", "2026-10-12T22:00:00", False),
    ("AAPL", "2026-10-26T14:30:00", True),          # EU schon Winterzeit, US noch Sommerzeit: 09:30 New York
    ("AAPL", "2026-10-26T14:29:00", False),
    ("AAPL", "2026-11-26T18:00:00", False),         # Thanksgiving
    ("^GSPC", "2026-10-12T16:00:00", True),
    ("GC=F", "2026-10-12T07:59:00", False),
    ("GC=F", "2026-10-12T08:00:00", True),
    ("BZ=F", "2026-10-12T21:59:00", True),
    ("BZ=F", "2026-10-12T22:00:00", False),
])
def test_marktstatus(projekt, ticker, zeit, offen):
    zeitpunkt = datetime.fromisoformat(zeit).replace(tzinfo=g.TZ)
    assert kurse.markt_offen(ticker, zeitpunkt) is offen


def test_geschlossener_markt_wird_im_protokoll_vermerkt(projekt, quelle, uhr):
    uhr.stellen("2026-10-12T20:00:00")
    quelle.kurs("SAP.DE", "200", zeit=datetime(2026, 10, 12, 17, 29, tzinfo=g.TZ))
    assert kurse.aktuell(["SAP.DE"])[0].markt_offen is False
    assert g.csv_lesen(projekt / "data" / "kurse" / "2026-10-12.csv")[0]["markt_offen"] == "nein"


def test_veralteter_kurs_bei_offenem_markt_abgelehnt(projekt, quelle, uhr):
    uhr.stellen("2026-10-12T12:00:00")
    quelle.kurs("SAP.DE", "200", zeit=datetime(2026, 10, 12, 11, 0, tzinfo=g.TZ))
    with pytest.raises(KursFehler, match="veraltet"):
        kurse.aktuell(["SAP.DE"])


def test_waehrungsumrechnung():
    assert kurse.in_eur(Decimal("110"), "USD", Decimal("1.10")) == Decimal("100")
    assert kurse.in_eur(Decimal("50"), "EUR", None) == Decimal("50")
    with pytest.raises(KursFehler):
        kurse.in_eur(Decimal("1"), "USD", None)


def test_waehrung_je_ticker(projekt):
    assert kurse.waehrung("SAP.DE") == "EUR"
    assert kurse.waehrung("AAPL") == "USD"
    assert kurse.waehrung("^GDAXI") == "EUR"
    assert kurse.waehrung("^NDX") == "USD"
    assert kurse.waehrung("GC=F") == "USD"


def test_nicht_erlaubte_ticker(projekt):
    for ticker in ("VOD.L", "BTC-USD.X", "^N225", "ES=F"):
        with pytest.raises(Fehler):
            kurse.boerse_von(ticker)


def test_keine_daten_verstaendliche_meldung(projekt, quelle, uhr):
    with pytest.raises(KursFehler, match="Keine Daten für XYZ"):
        kurse.aktuell(["XYZ"])
    with pytest.raises(KursFehler, match="Keine Kursdaten für XYZ"):
        kurse.historie("XYZ", date(2026, 10, 5), date(2026, 10, 9))


def test_historie_mit_dividende_und_split_und_zwischenspeicher(projekt, quelle, uhr):
    uhr.stellen("2026-10-12T10:00:00")
    quelle.kerze("AAPL", "2026-10-08", 100, 102, 99, 101)
    quelle.kerze("AAPL", "2026-10-09", 101, 103, 100, 102, dividende="0.25", split=2)
    quelle.kerze("AAPL", "2026-10-12", 51, 52, 50, 51)  # heute: noch nicht abgeschlossen
    kerzen = kurse.historie("AAPL", date(2026, 10, 8), date(2026, 10, 12))
    assert [k.datum for k in kerzen] == [date(2026, 10, 8), date(2026, 10, 9)]
    assert kerzen[1].dividende == Decimal("0.25") and kerzen[1].split == Decimal("2")
    assert (projekt / "data" / "historie" / "AAPL.csv").exists()
    abrufe = len([a for a in quelle.aufrufe if a[0] == "historie"])
    kurse.historie("AAPL", date(2026, 10, 8), date(2026, 10, 9))
    assert len([a for a in quelle.aufrufe if a[0] == "historie"]) == abrufe  # aus dem Speicher


def test_historie_ueberschreibt_gespeicherte_tage_nicht(projekt, quelle, uhr):
    uhr.stellen("2026-10-10T10:00:00")
    quelle.kerze("SAP.DE", "2026-10-09", 200, 201, 199, 200)
    kurse.historie("SAP.DE", date(2026, 10, 9), date(2026, 10, 9))
    quelle.kerze("SAP.DE", "2026-10-09", 999, 999, 999, 999)  # Quelle korrigiert nachträglich
    quelle.kerze("SAP.DE", "2026-10-12", 205)
    uhr.stellen("2026-10-13T10:00:00")
    kerzen = kurse.historie("SAP.DE", date(2026, 10, 9), date(2026, 10, 12))
    assert kerzen[0].close == Decimal("200")
    assert kerzen[1].close == Decimal("205")


@pytest.mark.parametrize("zeit,offen", [
    ("2026-11-27T18:59:00", True),    # Tag nach Thanksgiving: Schluss 13:00 New York = 19:00 Berlin
    ("2026-11-27T19:00:00", False),
    ("2026-12-24T18:30:00", True),
    ("2026-12-24T19:00:00", False),
    ("2026-12-23T21:59:00", True),    # normaler Tag
])
def test_fruehschluss_nyse(projekt, zeit, offen):
    zeitpunkt = datetime.fromisoformat(zeit).replace(tzinfo=g.TZ)
    assert kurse.markt_offen("AAPL", zeitpunkt) is offen


def test_feiertage_bis_2028_gepflegt(projekt):
    for jahr in (2026, 2027, 2028):
        assert kurse.feiertage_gepflegt(jahr) == []
    assert kurse.feiertage_gepflegt(2029) == ["xetra", "nyse"]
