"""News über RSS mit Fixture-Feeds, ohne Netzwerk."""

import json
from pathlib import Path

import pytest

import gemeinsam as g
import news
import pruefe
from gemeinsam import Fehler

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "news"


@pytest.fixture
def feeds(monkeypatch):
    abrufe = []

    def holen(url, agent, timeout=15.0):
        abrufe.append((url, agent))
        if "tagesschau" in url:
            return (FIXTURES / "tagesschau.xml").read_bytes()
        if "news.google.com" in url:
            return (FIXTURES / "google.xml").read_bytes()
        if "federalreserve" in url:
            return (FIXTURES / "fed.xml").read_bytes()
        raise Fehler("HTTP 404")

    monkeypatch.setattr(news, "HOLEN", holen)
    return abrufe


def konfig(*feeds_):
    basis = news.standard_konfig()
    return {**basis, "feeds": list(feeds_)}


TAGESSCHAU = {"id": "tagesschau-wirtschaft", "name": "Tagesschau Wirtschaft",
              "url": "https://www.tagesschau.de/wirtschaft/index~rss2.xml", "aktiv": True}
FED = {"id": "fed", "name": "Federal Reserve", "url": "https://www.federalreserve.gov/feeds/press_all.xml",
       "aktiv": True}


def test_parsen_kurztext_und_nur_http_links():
    meldungen = news.parsen((FIXTURES / "tagesschau.xml").read_bytes())
    assert [m["titel"] for m in meldungen] == ["DAX schließt mit Gewinnen & neuem Rekord", "Goldman Sachs erhöht Prognose"]
    assert meldungen[0]["kurztext"] == "Der deutsche Leitindex DAX legte am Montag deutlich zu."
    assert meldungen[0]["zeit"] == "2026-10-12T16:45:00+02:00"


def test_kein_feed():
    with pytest.raises(Fehler, match="Kein gültiger"):
        news.parsen(b"<html>keine news</html>")


def test_abruf_speichert_dedupliziert_mit_tickern(projekt, uhr, feeds):
    stand = news.abrufen(konfig(TAGESSCHAU, FED, {"id": "kaputt", "name": "Kaputt",
                                                   "url": "https://example.invalid/feed", "aktiv": True},
                                {"id": "aus", "url": "https://www.tagesschau.de/aus.xml", "aktiv": False}))
    assert stand["neu"] == 3 and stand["fehlerhaft"] == 1 and stand["anzahl_feeds"] == 3
    assert stand["feeds"]["kaputt"]["fehler"] == "HTTP 404"
    datei = projekt / "news" / "2026-10.jsonl"
    zeilen = [json.loads(z) for z in datei.read_text().splitlines()]
    dax = next(z for z in zeilen if z["titel"].startswith("DAX"))
    assert dax["ticker"] == ["^GDAXI"] and dax["quelle"] == "tagesschau-wirtschaft"
    assert dax["link"].startswith("https://") and set(dax) == {"id", "abgerufen", "zeit", "quelle", "quelle_name",
                                                                "titel", "kurztext", "link", "ticker", "herausgeber", "herausgeber_url"}
    goldman = next(z for z in zeilen if z["titel"].startswith("Goldman"))
    assert goldman["ticker"] == []  # "Gold" nur als ganzes Wort
    vorher = datei.read_bytes()
    uhr.stellen("2026-10-12T10:15:00")
    assert news.abrufen(konfig(TAGESSCHAU, FED))["neu"] == 0
    assert datei.read_bytes() == vorher
    assert json.loads((projekt / ".cache" / "news_stand.json").read_text())["neu"] == 0


def test_je_ticker_feeds_aus_dem_universum(projekt, uhr, feeds):
    vorlage = {"id": "yahoo-ticker", "name": "Yahoo", "url": "https://feeds.example/rss?s={ticker}", "je_ticker": True,
               "aktiv": True}
    aufgeloest = news.feeds_aufloesen(konfig(vorlage), ["^GDAXI", "SAP.DE"])
    assert [f["url"] for f in aufgeloest] == ["https://feeds.example/rss?s=%5EGDAXI", "https://feeds.example/rss?s=SAP.DE"]
    assert aufgeloest[0]["ticker"] == ["^GDAXI"] and aufgeloest[0]["id"] == "yahoo-ticker:^GDAXI"


def test_liste_und_nur_anhaengen(projekt, framework, uhr, feeds, capsys):
    from helfer import git_commit, git_init

    git_init(projekt)
    news.abrufen(konfig(TAGESSCHAU))
    git_commit(projekt, "daten: News")
    assert news.main(["liste", "--ticker", "^GDAXI"]) == 0
    ausgabe = capsys.readouterr().out
    assert "DAX schließt" in ausgabe and "Goldman" not in ausgabe and "https://www.tagesschau.de" in ausgabe
    # News sind datierte Quellen: Änderungen an gespeicherten Meldungen fallen auf.
    datei = projekt / "news" / "2026-10.jsonl"
    datei.write_text(datei.read_text().replace("Rekord", "Absturz"))
    assert any(b.pruefung == "Nur anhängen" and "news/2026-10.jsonl" in b.text for b in pruefe.alle_pruefungen())


def test_nur_http_feeds(projekt):
    with pytest.raises(Fehler, match="Nur http"):
        news._holen("file:///etc/passwd", "x")


def test_standard_feeds_vollstaendig():
    ids = {f["id"] for f in news.standard_konfig()["feeds"]}
    assert {"yahoo-ticker", "ezb", "fed", "sec-8k", "tagesschau-wirtschaft"} <= ids
    assert any(i.startswith("google-") for i in ids)
    assert g.config("news")["intervall_minuten"] == 15


GOLD = {"id": "google-gold", "name": "Google News: Goldpreis", "url": "https://news.google.com/rss/search?q=gold",
        "ticker": ["GC=F"], "aktiv": True, "titel_enthaelt": ["Gold", "Goldpreis"],
        "titel_ohne": ["Announces", "Drilling", "Resources"]}


def test_google_herausgeber_statt_umleitung_und_titel_ohne_suffix():
    meldungen = news.parsen((FIXTURES / "google.xml").read_bytes())
    erste = meldungen[0]
    assert erste["titel"] == "Goldpreis steigt auf Rekordhoch"
    assert erste["herausgeber"] == "MarketScreener" and erste["herausgeber_url"] == "https://www.marketscreener.com"
    assert erste["link"].startswith("https://news.google.com/")  # Weiterleitung, deshalb der Herausgeber daneben


def test_filter_dubletten_und_zaehler(projekt, uhr, feeds):
    stand = news.abrufen(konfig(GOLD))
    zeilen = [json.loads(z) for z in (projekt / "news" / "2026-10.jsonl").read_text().splitlines()]
    titel = [z["titel"] for z in zeilen]
    # "Goldman" trifft das Wort "Gold" nicht, die Mining-Pressemitteilung fällt durch titel_ohne,
    # dieselbe Meldung aus der Länderausgabe ist eine Dublette.
    assert sorted(titel) == ["Gold fällt nach starken US-Daten", "Goldpreis steigt auf Rekordhoch"]
    assert stand["feeds"]["google-gold"] == {"name": "Google News: Goldpreis", "ok": True, "fehler": None, "anzahl": 5,
                                             "neu": 2, "gefiltert": 2, "dubletten": 1}
    assert all(z["ticker"] == ["GC=F"] and z["herausgeber"] for z in zeilen)
    # Zweiter Abruf (auch mit anderem Feed) speichert dieselben Meldungen nicht noch einmal.
    anderer = {**GOLD, "id": "google-gold-2"}
    assert news.abrufen(konfig(anderer))["neu"] == 0


def test_liste_zeigt_herausgeber(projekt, uhr, feeds, capsys):
    news.abrufen(konfig(GOLD))
    assert news.main(["liste", "--ticker", "GC=F"]) == 0
    ausgabe = capsys.readouterr().out
    assert "MarketScreener [GC=F] | Goldpreis steigt auf Rekordhoch" in ausgabe and "Reuters" not in ausgabe


def test_standard_feeds_google_gezielt():
    feeds_ = {f["id"]: f for f in news.standard_konfig()["feeds"]}
    assert {"google-gold", "google-oel", "google-msci-world"} <= set(feeds_)
    assert "intitle" in feeds_["google-msci-world"]["url"] or "intitle%3A" in feeds_["google-msci-world"]["url"]
    assert feeds_["google-gold"]["titel_ohne"] and feeds_["google-oel"]["ticker"] == ["BZ=F"]
