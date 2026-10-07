"""Kursquellen-Kette (Anbieter → yfinance → letzter Kurs nur zur Anzeige), ohne Netzwerk."""

from datetime import datetime

import pytest

import gemeinsam as g
import kurse
from gemeinsam import D, KursFehler


class FalscheHttp:
    """Ersetzt _http_json: liefert vorbereitete Antworten und merkt sich die Aufrufe."""

    def __init__(self, antworten):
        self.antworten = antworten
        self.aufrufe = []

    def __call__(self, url, kopf):
        self.aufrufe.append((url, kopf))
        antwort = self.antworten(url) if callable(self.antworten) else self.antworten
        if isinstance(antwort, Exception):
            raise antwort
        return antwort


def _anbieter(kennung, http):
    konfig = g.config("kursquellen")["anbieter"][kennung]
    return kurse.AnbieterQuelle(kennung, "geheimer-key-1234", konfig, http=http)


def test_zuordnung_nur_fuer_identische_instrumente(projekt):
    td = _anbieter("twelvedata", FalscheHttp({}))
    assert td.symbol("AAPL") == "AAPL"
    assert td.symbol("SAP.DE") == "SAP:XETR"
    assert td.symbol("EURUSD=X") == "EUR/USD"
    assert td.symbol("^GDAXI") is None and td.symbol("GC=F") is None
    fh = _anbieter("finnhub", FalscheHttp({}))
    assert fh.symbol("SAP.DE") is None and fh.symbol("MSFT") == "MSFT"


def test_anbieter_zuerst_key_nur_im_kopf(projekt, uhr, quelle):
    stempel = int(uhr().timestamp()) - 120
    http = FalscheHttp({"symbol": "AAPL", "close": "231.5", "timestamp": stempel})
    kurse.QUELLE = kurse.KursKette([_anbieter("twelvedata", http), quelle])
    quelle.kurs("AAPL", "999")
    uhr.stellen("2026-10-12T17:00:00")  # NYSE offen
    http.antworten = {"symbol": "AAPL", "close": "231.5", "timestamp": int(uhr().timestamp()) - 120}
    ergebnis = kurse.aktuell(["AAPL"])[0]
    assert ergebnis.kurs == D("231.5") and ergebnis.quelle == "twelvedata"
    url, kopf = http.aufrufe[0]
    assert "geheimer-key" not in url and kopf["Authorization"] == "apikey geheimer-key-1234"
    zeile = g.csv_lesen(g.pfad("data", "kurse", "2026-10-12.csv"))[-1]
    assert zeile["quelle"] == "twelvedata" and zeile["kurs"] == "231.500000"


def test_fallback_auf_bestehende_quelle(projekt, uhr, quelle):
    http = FalscheHttp(KursFehler("HTTP 429"))
    kurse.QUELLE = kurse.KursKette([_anbieter("finnhub", http), quelle])
    quelle.kurs("MSFT", "410")
    k = kurse.aktuell(["MSFT"])[0]
    assert k.quelle == "attrappe" and k.kurs == D("410")


def test_veralteter_anbieterkurs_fuehrt_zur_naechsten_quelle(projekt, uhr, quelle):
    uhr.stellen("2026-10-12T17:00:00")
    alt = int(uhr().timestamp()) - 3 * 3600
    kurse.QUELLE = kurse.KursKette([_anbieter("finnhub", FalscheHttp({"c": 300.0, "t": alt})), quelle])
    quelle.kurs("MSFT", "410")
    assert kurse.aktuell(["MSFT"])[0].quelle == "attrappe"


def test_alle_quellen_scheitern_kein_kurs(projekt, uhr, quelle):
    kurse.QUELLE = kurse.KursKette([_anbieter("finnhub", FalscheHttp(KursFehler("HTTP 500"))), quelle])
    with pytest.raises(KursFehler, match="Kein verlässlicher Kurs für MSFT"):
        kurse.aktuell(["MSFT"])
    assert g.csv_lesen(g.pfad("data", "kurse", "2026-10-12.csv")) == []


def test_kontingent_wird_eingehalten(projekt, uhr, quelle):
    stempel = int(datetime.now().timestamp())
    http = FalscheHttp({"c": 100.0, "t": stempel})
    anbieter = _anbieter("finnhub", http)
    anbieter.kontingent.je_minute = 2
    anbieter._puffer_sekunden = 0
    kurse.QUELLE = kurse.KursKette([anbieter, quelle])
    quelle.kurs("AAPL", "222")
    quellen = [kurse.aktuell(["AAPL"])[0].quelle for _ in range(3)]
    assert quellen == ["finnhub", "finnhub", "attrappe"] and len(http.aufrufe) == 2


def test_batch_abfrage_twelvedata(projekt, uhr, quelle):
    stempel = int(uhr().timestamp())

    def antworten(url):
        return {"AAPL": {"close": "230", "timestamp": stempel}, "SAP:XETR": {"close": "240", "timestamp": stempel}}

    http = FalscheHttp(antworten)
    kurse.QUELLE = kurse.KursKette([_anbieter("twelvedata", http), quelle])
    werte = kurse.aktuell(["AAPL", "SAP.DE"])
    assert [k.quelle for k in werte] == ["twelvedata", "twelvedata"]
    assert len(http.aufrufe) == 1 and "AAPL,SAP:XETR" in http.aufrufe[0][0]


def test_quelle_aus_umgebung(projekt, monkeypatch):
    monkeypatch.delenv("STOCKMASTER_KURSANBIETER", raising=False)
    assert isinstance(kurse.quelle_aus_umgebung(), kurse.YFinanceQuelle)
    monkeypatch.setenv("STOCKMASTER_KURSANBIETER", "finnhub")
    monkeypatch.setenv("STOCKMASTER_KURSANBIETER_KEY", "abc")
    kette = kurse.quelle_aus_umgebung()
    assert [q.name for q in kette.quellen] == ["finnhub", "yfinance"]


def test_markt_mit_veraltet_kennzeichnung(projekt, uhr, quelle):
    quelle.kurs("EUNL.DE", "105")
    quelle.kerze("EUNL.DE", "2026-10-09", 100)
    quelle.kerze("^GDAXI", "2026-10-09", 24000)
    kurse.historie("^GDAXI", g.datum_lesen("2026-10-01"), g.datum_lesen("2026-10-11"))
    kurse.historie("EUNL.DE", g.datum_lesen("2026-10-01"), g.datum_lesen("2026-10-11"))
    stand = kurse.markt(["EUNL.DE", "^GDAXI"])
    eunl, dax = stand["eintraege"]
    assert not eunl["veraltet"] and eunl["kurs"] == D("105") and eunl["veraenderung"] == D("0.05")
    assert eunl["quelle"] == "attrappe" and eunl["verzoegerung_minuten"] == 0
    assert dax["veraltet"] and dax["kurs"] == D("24000") and dax["quelle"].startswith("letzter bekannter Kurs")
    assert stand["erfolgreich"] == 1
    gespeichert = g.json_lesen(kurse.markt_pfad())
    assert gespeichert["eintraege"][1]["veraltet"] is True
    # Der veraltete Kurs wurde nicht protokolliert (nie Grundlage einer Buchung).
    assert [z["ticker"] for z in g.csv_lesen(g.pfad("data", "kurse", "2026-10-12.csv"))] == ["EUNL.DE"]
