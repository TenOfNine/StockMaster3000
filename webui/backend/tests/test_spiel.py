"""Lesende Spiel-API gegen das Demo-Repository."""

import re

from conftest import WURZEL  # noqa: F401


def ranking_wert(repo, profil_index: int, zeile: str) -> str:
    for z in (repo / "ranking.md").read_text().splitlines():
        if z.startswith(f"| {zeile} |"):
            return z.strip("|").split("|")[profil_index + 1].strip()
    raise AssertionError(zeile)


def test_ueberblick_stimmt_mit_ranking_ueberein(nutzer, demo_repo):
    daten = nutzer.get("/api/spiel/ueberblick").json()
    assert daten["gestartet"] is True and daten["repo"]["demo"] is True
    for index, profil in enumerate(("defensiv", "ausgewogen", "aggressiv")):
        k = daten["profile"][profil]
        # ranking.md ist für Menschen und nutzt das Dezimalkomma
        assert f"{k['wert']:.2f} EUR".replace(".", ",") == ranking_wert(demo_repo, index, "Portfoliowert")
        assert ranking_wert(demo_repo, index, "Drawdown-Stufe") == str(k["stufe"])
        assert ranking_wert(demo_repo, index, "Abgeschlossene Trades") == str(k["geschlossen"])
    assert daten["letzte_sessions"][0]["art"] == "S"


def test_nav_stimmt_mit_data_nav(nutzer, demo_repo):
    daten = nutzer.get("/api/spiel/nav").json()
    zeilen = (demo_repo / "data" / "nav" / "ausgewogen.csv").read_text().splitlines()
    letzte = zeilen[-1].split(",")
    assert daten["profile"]["ausgewogen"][-1]["datum"] == letzte[0]
    assert f"{daten['profile']['ausgewogen'][-1]['portfoliowert']:.2f}" == letzte[3]
    assert len(daten["benchmark"]) == len(zeilen) - 1


def test_portfolio_und_trades(nutzer):
    daten = nutzer.get("/api/spiel/portfolios/aggressiv").json()
    assert daten["profil"] == "aggressiv"
    assert {a["regel"] for a in daten["auslastung"]} >= {"Zertifikate-Anteil", "Gesamt-Exposure", "Cashquote"}
    assert daten["grenzen"]["max_hebel"] == 10
    for position in daten["positionen"]:
        assert position["wert_eur"] is not None and position["kurs_datum"]
    trades = nutzer.get("/api/spiel/portfolios/aggressiv/trades").json()
    assert trades[0]["trade_id"] == "T-0001"
    assert nutzer.get("/api/spiel/portfolios/unbekannt").status_code == 422


def test_journal_und_akte(nutzer):
    journal = nutzer.get("/api/spiel/journal").json()
    kaeufe = [e for e in journal if e["art"] == "J" and e["status"] in ("offen", "geschlossen")]
    assert kaeufe and all(e["trades"] for e in kaeufe)
    akte = nutzer.get(f"/api/spiel/journal/{kaeufe[0]['id']}").json()
    assert akte["felder"]["these"]
    assert akte["folge"][0]["aktion"] in ("kauf", "vormerkung")
    assert akte["limit_schnappschuesse"]
    schnappschuss = akte["limit_schnappschuesse"][0]
    assert isinstance(schnappschuss["kennzahlen"]["exposure"], float)
    assert isinstance(schnappschuss["grenzen"]["max_exposure"], float)
    assert akte["kerzen"]
    assert any(e["art"] == "S" for e in akte["erwaehnt_in"])
    assert nutzer.get("/api/spiel/journal/J-19990101-01").status_code == 404
    assert nutzer.get("/api/spiel/journal/..%2Fetc").status_code == 404


def test_dokumente_nur_positivliste(nutzer):
    liste = nutzer.get("/api/spiel/dokumente").json()
    assert any(d["pfad"] == "regeln.md" for d in liste)
    assert nutzer.get("/api/spiel/dokument", params={"pfad": "regeln.md"}).json()["inhalt"].startswith("# Spielregeln")
    for pfad in ("../../etc/passwd.md", "tools/gemeinsam.py", "portfolios/defensiv.json", "config/../regeln.md"):
        assert nutzer.get("/api/spiel/dokument", params={"pfad": pfad}).status_code in (404, 422)


def test_status_auswertung(nutzer):
    daten = nutzer.get("/api/spiel/status").json()
    assert any(p["kennung"] == "AP1" and p["erledigt"] for p in daten["arbeitspakete"])
    assert len(daten["auslegungsfragen"]) >= 17
    assert daten["entscheidungen"][0]["nummer"] == 1


def test_kurse_rechner_git_pruefung(nutzer):
    ticker = nutzer.get("/api/spiel/kurse").json()
    assert any(t["ticker"] == "^GDAXI" for t in ticker)
    kerzen = nutzer.get("/api/spiel/kurse/%5EGDAXI").json()
    assert kerzen[0]["open"] > 0
    assert nutzer.get("/api/spiel/kurse/..%2F..").status_code == 404
    ko = nutzer.get("/api/spiel/rechner/ko", params={"richtung": "long", "kurs": "20000", "hebel": "5"}).json()
    assert ko["basispreis"] == 16000 and ko["hebel"] == 5
    faktor = nutzer.get("/api/spiel/rechner/faktor", params={"richtung": "long", "faktor": "3",
                                                            "kurse": "100;105;100;105;100"}).json()
    assert faktor["werte"][-1] < 100
    assert nutzer.get("/api/spiel/rechner/ko", params={"richtung": "long", "kurs": "-1", "hebel": "5"}).status_code == 422
    log = nutzer.get("/api/spiel/git").json()
    assert log and re.match(r"^[0-9a-f]{40}$", log[0]["hash"])
    commit = nutzer.get(f"/api/spiel/git/{log[0]['kurz']}").json()
    assert commit["diff"]
    pruefung = nutzer.post("/api/spiel/pruefung").json()
    assert pruefung["ok"] is True, pruefung


def test_sicherheits_header(nutzer):
    antwort = nutzer.get("/api/spiel/ueberblick")
    assert antwort.headers["x-content-type-options"] == "nosniff"
    assert antwort.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in antwort.headers["content-security-policy"]


def test_heimnetz_schranke(app, monkeypatch):
    from fastapi.testclient import TestClient

    from stockmaster import config, main

    monkeypatch.setenv("SM_ERLAUBTE_NETZE", '["192.168.0.0/16"]')
    config.einstellungen.cache_clear()
    anwendung = main.app_erstellen()
    with TestClient(anwendung, client=("203.0.113.9", 5000)) as extern:
        assert extern.get("/api/health").status_code == 403
    with TestClient(anwendung, client=("192.168.1.20", 5000)) as intern:
        assert intern.get("/api/health").status_code == 200


def _eintrag(kurs=100.0, **zahlen):
    basis = {"name": None, "listen": ["dax40"], "waehrung": "EUR", "handelbar": True, "grund": None,
             "datum": "2026-10-09", "kurs": kurs, "tage": 252, "rendite_1t": 0.01, "rendite_5t": 0.02,
             "rendite_20t": 0.03, "rendite_60t": 0.04, "abstand_hoch": -0.05, "abstand_tief": 0.3,
             "sma20_abstand": 0.01, "sma50_abstand": 0.02, "gap_1t": 0.0, "volumen_relativ_1t": 1.0,
             "volatilitaet_20t": 0.25}
    return {**basis, **zahlen}


BEOBACHTUNG_STAND = {
    "zeit": "2026-10-12T23:20:00+02:00", "quelle": "yfinance", "anzahl": 6, "mit_daten": 5, "aktuell": 5,
    "listen": {"dax40": {"name": "DAX 40", "anzahl": 3, "mit_daten": 3}, "sp500": {"name": "S&P 500", "anzahl": 2,
                                                                                 "mit_daten": 2}},
    "ohne_daten": ["X.DE"], "veraltet": [],
    "eintraege": {"SAP.DE": _eintrag(name="SAP SE", rendite_1t=0.03, volumen_relativ_1t=2.5),
                  "SIE.DE": _eintrag(name="Siemens", rendite_1t=-0.02, volumen_relativ_1t=None),
                  "BAS.DE": _eintrag(0.5, name="BASF", rendite_1t=0.09, handelbar=False, grund="Kurs unter 1 EUR"),
                  "AAPL": _eintrag(name="Apple", listen=["sp500"], waehrung="USD", rendite_1t=0.01),
                  "MSFT": _eintrag(name="Microsoft", listen=["sp500"], waehrung="USD", rendite_1t=0.04)},
}


def _mit_beobachtung(monkeypatch, stand):
    from stockmaster.spiel import lesen

    original = lesen._cache_json
    monkeypatch.setattr(lesen, "_cache_json", lambda name: stand if name == "beobachtung.json" else original(name))


def test_beobachtung_ohne_daten(nutzer, monkeypatch):
    _mit_beobachtung(monkeypatch, {})
    daten = nutzer.get("/api/spiel/beobachtung").json()
    assert daten["zeit"] is None and daten["eintraege"] == [] and daten["gesamt"] == 0
    assert [k["id"] for k in daten["kennzahlen"]][:2] == ["kurs", "rendite_1t"]
    assert nutzer.get("/api/spiel/beobachtung/kandidaten").json() == {"zeit": None, "bloecke": []}


def test_beobachtung_sortieren_filtern_blaettern(nutzer, monkeypatch):
    _mit_beobachtung(monkeypatch, BEOBACHTUNG_STAND)
    daten = nutzer.get("/api/spiel/beobachtung").json()
    assert [e["ticker"] for e in daten["eintraege"]] == ["MSFT", "SAP.DE", "AAPL", "SIE.DE"]  # BAS.DE nicht handelbar
    assert daten["gesamt"] == 4 and daten["anzahl"] == 6 and daten["mit_daten"] == 5 and daten["ohne_daten"] == ["X.DE"]
    assert [(x["id"], x["name"]) for x in daten["listen"]] == [("dax40", "DAX 40"), ("sp500", "S&P 500")]
    assert daten["kennzahlen"][1] == {"id": "rendite_1t", "titel": "1 Tag", "art": "prozent"}

    auf = nutzer.get("/api/spiel/beobachtung", params={"aufsteigend": "true"}).json()
    assert [e["ticker"] for e in auf["eintraege"]] == ["SIE.DE", "AAPL", "SAP.DE", "MSFT"]
    alle = nutzer.get("/api/spiel/beobachtung", params={"nur_handelbar": "false"}).json()
    assert alle["gesamt"] == 5 and alle["eintraege"][0]["ticker"] == "BAS.DE"
    assert alle["eintraege"][0]["grund"] == "Kurs unter 1 EUR"
    sp = nutzer.get("/api/spiel/beobachtung", params={"liste": "sp500"}).json()
    assert [e["ticker"] for e in sp["eintraege"]] == ["MSFT", "AAPL"]
    for nadel, erwartet in (("sie", ["SIE.DE"]), ("MICRO", ["MSFT"]), (".de", ["SAP.DE", "SIE.DE"])):
        treffer = nutzer.get("/api/spiel/beobachtung", params={"suche": nadel}).json()
        assert [e["ticker"] for e in treffer["eintraege"]] == erwartet
    seite = nutzer.get("/api/spiel/beobachtung", params={"anzahl": 2, "offset": 1}).json()
    assert [e["ticker"] for e in seite["eintraege"]] == ["SAP.DE", "AAPL"] and seite["gesamt"] == 4


def test_beobachtung_werte_ohne_kennzahl_stehen_am_ende(nutzer, monkeypatch):
    _mit_beobachtung(monkeypatch, BEOBACHTUNG_STAND)
    daten = nutzer.get("/api/spiel/beobachtung", params={"sortiert": "volumen_relativ_1t"}).json()
    assert [e["ticker"] for e in daten["eintraege"]] == ["SAP.DE", "MSFT", "AAPL", "SIE.DE"]  # SIE.DE hat keinen Wert
    daten = nutzer.get("/api/spiel/beobachtung", params={"sortiert": "volumen_relativ_1t", "aufsteigend": "true"}).json()
    assert daten["eintraege"][-1]["ticker"] == "SIE.DE"


def test_beobachtung_eingaben_werden_geprueft(nutzer, monkeypatch):
    _mit_beobachtung(monkeypatch, BEOBACHTUNG_STAND)
    assert nutzer.get("/api/spiel/beobachtung", params={"sortiert": "gibt_es_nicht"}).status_code == 404
    assert nutzer.get("/api/spiel/beobachtung", params={"liste": "nasdaq"}).status_code == 404
    assert nutzer.get("/api/spiel/beobachtung", params={"liste": "../x"}).status_code == 422
    assert nutzer.get("/api/spiel/beobachtung", params={"anzahl": 500}).status_code == 422
    assert nutzer.get("/api/spiel/beobachtung", params={"offset": -1}).status_code == 422
    assert nutzer.get("/api/spiel/beobachtung/kandidaten", params={"liste": "nasdaq"}).status_code == 404
    assert nutzer.get("/api/spiel/beobachtung/kandidaten", params={"anzahl": 0}).status_code == 422


def test_beobachtung_kandidaten(nutzer, monkeypatch):
    _mit_beobachtung(monkeypatch, BEOBACHTUNG_STAND)
    daten = nutzer.get("/api/spiel/beobachtung/kandidaten", params={"anzahl": 2}).json()
    assert daten["zeit"] == BEOBACHTUNG_STAND["zeit"] and len(daten["bloecke"]) == 8
    oben = daten["bloecke"][0]
    assert oben["titel"] == "Stärkste Tagesbewegung nach oben" and oben["kennzahl"] == "rendite_1t"
    assert [w["ticker"] for w in oben["werte"]] == ["MSFT", "SAP.DE"]  # BAS.DE nicht handelbar
    sp = nutzer.get("/api/spiel/beobachtung/kandidaten", params={"liste": "sp500", "anzahl": 1}).json()
    assert [w["ticker"] for w in sp["bloecke"][0]["werte"]] == ["MSFT"]


def test_beobachtung_nur_angemeldet(client):
    assert client.get("/api/spiel/beobachtung").status_code == 401
    assert client.get("/api/spiel/beobachtung/kandidaten").status_code == 401
