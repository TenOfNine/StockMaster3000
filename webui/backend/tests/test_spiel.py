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
