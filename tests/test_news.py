"""News über RSS mit Fixture-Feeds, ohne Netzwerk."""

import http.client
import json
import socket
import ssl
import urllib.error
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
    assert stand["feeds"]["google-gold"] == {
        "name": "Google News: Goldpreis", "anzeige": "Google News: Goldpreis", "url": GOLD["url"], "ok": True,
        "fehler": None, "art": None, "hinweis": None, "seit": None, "in_folge": 0,
        "letzter_erfolg": "2026-10-12T10:00:00+02:00", "anzahl": 5, "neu": 2, "gefiltert": 2, "dubletten": 1}
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


# --------------------------------------------------------------------------
# Fehler im Klartext, Verlauf und Zusammenfassung


@pytest.mark.parametrize("code, art, text", [
    (403, "zugriff", "Zugriff verweigert (HTTP 403)"),
    (404, "nicht_gefunden", "nicht gefunden (HTTP 404)"),
    (429, "gedrosselt", "Zu viele Anfragen (HTTP 429)"),
    (503, "server", "Serverfehler beim Anbieter (HTTP 503)"),
    (418, "http", "Unerwartete Antwort (HTTP 418)"),
])
def test_http_fehler_im_klartext(monkeypatch, code, art, text):
    def urlopen(anfrage, timeout):
        raise urllib.error.HTTPError(anfrage.full_url, code, "x", {}, None)

    monkeypatch.setattr(news.urllib.request, "urlopen", urlopen)
    with pytest.raises(news.FeedFehler) as fehler:
        news._holen("https://example.org/feed", "agent")
    assert fehler.value.art == art and text in str(fehler.value) and fehler.value.hinweis


@pytest.mark.parametrize("ausnahme, art, text", [
    (urllib.error.URLError(socket.gaierror(-2, "Name or service not known")), "namensaufloesung", "nicht auflösbar"),
    (urllib.error.URLError(TimeoutError("timed out")), "zeitueberschreitung", "Keine Antwort innerhalb von 15 Sekunden"),
    (TimeoutError("timed out"), "zeitueberschreitung", "Keine Antwort"),
    (urllib.error.URLError(ssl.SSLCertVerificationError("certificate verify failed")), "tls", "TLS"),
    (urllib.error.URLError(ConnectionRefusedError(111, "refused")), "verbindung", "Verbindung abgelehnt"),
    (ConnectionResetError(104, "reset"), "verbindung", "abgebrochen"),
    (http.client.IncompleteRead(b"abc"), "verbindung", "unvollständig"),
    (urllib.error.URLError(OSError("Tunnel connection failed: 403 Forbidden")), "verbindung", "Tunnel connection failed"),
])
def test_verbindungsfehler_im_klartext(monkeypatch, ausnahme, art, text):
    def urlopen(anfrage, timeout):
        raise ausnahme

    monkeypatch.setattr(news.urllib.request, "urlopen", urlopen)
    with pytest.raises(news.FeedFehler) as fehler:
        news._holen("https://example.org/feed", "agent")
    assert fehler.value.art == art and text in str(fehler.value) and fehler.value.hinweis


def test_zu_grosser_feed(monkeypatch):
    class Antwort:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, maximal):
            return b"x" * maximal

    monkeypatch.setattr(news.urllib.request, "urlopen", lambda anfrage, timeout: Antwort())
    with pytest.raises(news.FeedFehler) as fehler:
        news._holen("https://example.org/feed", "agent")
    assert fehler.value.art == "zu_gross" and "2 MB" in str(fehler.value)


def test_webseite_und_leere_antwort_statt_feed():
    with pytest.raises(news.FeedFehler, match="Webseite") as fehler:
        news.parsen(b"\n<!DOCTYPE html><html><body>Bitte Cookies akzeptieren</body></html>")
    assert fehler.value.art == "kein_feed" and "Schutzseite" in fehler.value.hinweis
    with pytest.raises(news.FeedFehler, match="leere Antwort"):
        news.parsen(b"  \n")
    with pytest.raises(news.FeedFehler, match="weder RSS noch Atom|SAXParseException|kein RSS/Atom erkannt") as fehler:
        news.parsen(b"<?xml version='1.0'?><wurzel/>")
    assert fehler.value.art == "kein_feed"


def test_meldungen_bleiben_einzeilig_und_unter_300_zeichen():
    # Der Hintergrunddienst zeigt nur die letzte Zeile (höchstens 300 Zeichen) der Ausgabe von "news test".
    for code in (403, 404, 429, 503, 418):
        fehler = news._http_fehler(code)
        assert "\n" not in f"{fehler} {fehler.hinweis}" and len(f"Fehler: {fehler} {fehler.hinweis}") < 300
    for exc in (socket.gaierror(-2, "x"), TimeoutError(), ssl.SSLError("x"), ConnectionRefusedError(), OSError("y" * 500)):
        fehler = news._verbindungsfehler(urllib.error.URLError(exc), 15.0)
        assert "\n" not in f"{fehler} {fehler.hinweis}" and len(f"Fehler: {fehler} {fehler.hinweis}") < 300


def test_fehlerverlauf_seit_wann_und_in_folge(projekt, uhr, feeds, monkeypatch):
    normal = news.HOLEN  # Attrappe der Fixture "feeds"
    ausfall = {"fed": False}

    def holen(url, agent, timeout=15.0):
        if ausfall["fed"] and "federalreserve" in url:
            raise news._http_fehler(403)
        return normal(url, agent, timeout)

    monkeypatch.setattr(news, "HOLEN", holen)
    stand = news.abrufen(konfig(TAGESSCHAU, FED))
    assert stand["fehlerhaft"] == 0 and stand["feeds"]["fed"]["in_folge"] == 0
    erfolg = stand["feeds"]["fed"]["letzter_erfolg"]
    assert erfolg == "2026-10-12T10:00:00+02:00"

    ausfall["fed"] = True
    uhr.stellen("2026-10-12T10:15:00")
    erste = news.abrufen(konfig(TAGESSCHAU, FED))["feeds"]["fed"]
    assert (erste["ok"], erste["art"], erste["in_folge"]) == (False, "zugriff", 1)
    assert erste["seit"] == "2026-10-12T10:15:00+02:00" and erste["letzter_erfolg"] == erfolg
    assert erste["anzeige"] == "Federal Reserve" and erste["url"] == FED["url"] and erste["hinweis"]
    uhr.stellen("2026-10-12T10:30:00")
    zweite = news.abrufen(konfig(TAGESSCHAU, FED))["feeds"]["fed"]
    assert zweite["in_folge"] == 2 and zweite["seit"] == erste["seit"] and zweite["letzter_erfolg"] == erfolg

    ausfall["fed"] = False
    uhr.stellen("2026-10-12T10:45:00")
    wieder = news.abrufen(konfig(TAGESSCHAU, FED))["feeds"]["fed"]
    assert wieder["ok"] and wieder["in_folge"] == 0 and wieder["seit"] is None
    assert wieder["letzter_erfolg"] == "2026-10-12T10:45:00+02:00"


def test_unerwarteter_fehler_stoppt_die_anderen_nicht(projekt, uhr, monkeypatch):
    def holen(url, agent, timeout=15.0):
        if "federalreserve" in url:
            raise ValueError("kaputt")
        return (FIXTURES / "tagesschau.xml").read_bytes()

    monkeypatch.setattr(news, "HOLEN", holen)
    stand = news.abrufen(konfig(TAGESSCHAU, FED))
    assert stand["neu"] == 2 and stand["feeds"]["fed"]["art"] == "intern"
    assert "ValueError: kaputt" in stand["feeds"]["fed"]["fehler"]


def test_zusammenfassung_nennt_feed_und_grund(projekt, uhr, feeds):
    kaputt = {"id": "kaputt", "name": "Kaputt", "url": "https://example.invalid/feed", "aktiv": True}
    stand = news.abrufen(konfig(TAGESSCHAU, FED, kaputt))
    assert news.zusammenfassung(stand) == "News: 3 neue Meldungen aus 3 Feeds, 1 mit Fehler – Kaputt: HTTP 404."
    assert news.zusammenfassung(news.abrufen(konfig(TAGESSCHAU))) == "News: 0 neue Meldungen aus 1 Feeds."
    viele = {"neu": 0, "anzahl_feeds": 5, "feeds": {f"f{i}": {"name": f"F{i}", "ok": False, "fehler": "HTTP 500."}
                                                   for i in range(5)}}
    assert news.zusammenfassung(viele) == ("News: 0 neue Meldungen aus 5 Feeds, 5 mit Fehler – F0: HTTP 500; "
                                            "F1: HTTP 500; F2: HTTP 500; und 2 weitere.")


def test_ticker_vorlage_im_anzeigenamen(projekt, uhr, feeds):
    vorlage = {"id": "yahoo-ticker", "name": "Yahoo Finance", "url": "https://feeds.example/rss?s={ticker}",
               "je_ticker": True, "aktiv": True}
    stand = news.abrufen(konfig(vorlage))
    assert {s["anzeige"] for s in stand["feeds"].values()} >= {"Yahoo Finance (^GDAXI)"}
    assert all(s["name"] == "Yahoo Finance" for s in stand["feeds"].values())


def test_abrufen_ausgabe_mit_fehlern(projekt, uhr, capsys, tmp_path, monkeypatch):
    sec = {"id": "sec-8k", "name": "SEC 8-K", "url": "https://www.sec.gov/feed", "aktiv": True}
    datei = tmp_path / "konfig.json"
    datei.write_text(json.dumps(konfig(TAGESSCHAU, sec)))

    def holen(url, agent, timeout=15.0):
        if "sec.gov" in url:
            raise news._http_fehler(403)
        return (FIXTURES / "tagesschau.xml").read_bytes()

    monkeypatch.setattr(news, "HOLEN", holen)
    assert news.main(["abrufen", "--konfig", str(datei)]) == 0
    uhr.stellen("2026-10-12T10:15:00")
    assert news.main(["abrufen", "--konfig", str(datei)]) == 0
    zeilen = capsys.readouterr().out.splitlines()
    assert zeilen[0] == "News: 2 neue Meldungen aus 2 Feeds, 1 mit Fehler – SEC 8-K: Zugriff verweigert (HTTP 403)."
    assert zeilen[1].startswith("  sec-8k: Zugriff verweigert (HTTP 403). Hinweis: ") and "Abrufe in Folge" not in zeilen[1]
    assert zeilen[2].startswith("News: 0 neue Meldungen aus 2 Feeds, 1 mit Fehler")
    assert "(2 Abrufe in Folge, seit 2026-10-12 10:00)" in zeilen[3]


def test_feed_test_zeigt_fehler_mit_hinweis(monkeypatch, capsys):
    def holen(url, agent, timeout=15.0):
        raise news._http_fehler(404)

    monkeypatch.setattr(news, "HOLEN", holen)
    assert news.main(["test", "--url", "https://example.org/feed"]) == 1
    fehler = capsys.readouterr().err.strip()
    assert fehler.startswith("Fehler: Feed-Adresse nicht gefunden (HTTP 404). Der Feed existiert")
