#!/usr/bin/env python3
"""News-Speicher über RSS/Atom (feedparser): datierte Quellen für Sessions und Web-UI.

    python tools/news.py abrufen [--konfig <json>]     Feeds abrufen, neue Meldungen anhängen
    python tools/news.py liste [--tage 3] [--ticker X] [--anzahl 50] [--json]
    python tools/news.py test --url <feed-url>         Feed prüfen, ohne zu speichern

Gespeichert werden nur Titel, Kurztext (gekürzt) und Link mit Quelle, Datum und
Ticker-Zuordnung in news/JJJJ-MM.jsonl im Datenverzeichnis (nur anhängen,
dedupliziert). News sind keine Kurse: Kurse kommen nur aus tools/kurse.py.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urlparse

import gemeinsam as g
import pfade
from gemeinsam import Fehler

MAX_BYTES = 2_000_000
MONATE_FUER_DUPLIKATE = 3


def standard_konfig() -> dict:
    return g.config("news")


def _holen(url: str, user_agent: str, timeout: float = 15.0) -> bytes:
    if urlparse(url).scheme not in ("http", "https"):
        raise Fehler("Nur http- und https-Feeds sind erlaubt.")
    anfrage = urllib.request.Request(url, headers={"User-Agent": user_agent,
                                                   "Accept": "application/rss+xml, application/atom+xml, */*"})
    try:
        with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:  # noqa: S310 - Schema oben geprüft
            daten = antwort.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise Fehler(f"HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise Fehler(f"nicht erreichbar ({getattr(exc, 'reason', exc)})") from None
    if len(daten) > MAX_BYTES:
        raise Fehler("Feed größer als 2 MB.")
    return daten


HOLEN = _holen  # in Tests ersetzt (kein Netzwerk)


def _kurztext(roh: str, maximal: int) -> str:
    text = re.sub(r"<[^>]+>", " ", roh or "")
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text if len(text) <= maximal else text[: maximal - 1].rstrip() + "…"


def _zeit(eintrag) -> str | None:
    for feld in ("published_parsed", "updated_parsed"):
        wert = eintrag.get(feld)
        if wert:
            return datetime(*wert[:6], tzinfo=UTC).astimezone(g.TZ).isoformat()
    return None


def _id(eintrag) -> str:
    schluessel = eintrag.get("id") or eintrag.get("link") or eintrag.get("title") or ""
    return "N-" + hashlib.sha256(schluessel.strip().encode("utf-8")).hexdigest()[:12]


def _schlagwort_treffer(text: str, schlagworte: dict[str, list[str]]) -> list[str]:
    treffer = []
    for ticker, worte in schlagworte.items():
        if any(re.search(rf"(?<![\w-]){re.escape(wort)}(?![\w-])", text) for wort in worte):
            treffer.append(ticker)
    return treffer


def titel_schluessel(titel: str) -> str:
    """Normalisierter Titel zum Erkennen von Dubletten (gleiche Meldung aus mehreren Feeds oder Länderausgaben)."""
    return re.sub(r"[\W_]+", " ", titel.casefold()).strip()


def _passt(text: str, worte: list[str]) -> bool:
    """Eines der Wörter kommt als ganzes Wort vor (Groß-/Kleinschreibung egal; "Gold" trifft nicht "Goldman")."""
    return any(re.search(rf"(?<!\w){re.escape(wort)}(?!\w)", text, re.I) for wort in worte)


def filtern(meldung: dict, feed: dict) -> bool:
    """Wendet titel_enthaelt (mindestens ein Wort) und titel_ohne (keines) des Feeds an."""
    titel = meldung["titel"]
    if feed.get("titel_enthaelt") and not _passt(titel, feed["titel_enthaelt"]):
        return False
    return not (feed.get("titel_ohne") and _passt(titel, feed["titel_ohne"]))


def parsen(daten: bytes, maximal: int = 300) -> list[dict]:
    """Feed-Inhalt in Meldungen (ohne Speicherung). Links nur http(s).

    Bei Sammeldiensten wie Google News steht der eigentliche Herausgeber im Feld "source"; er wird als
    herausgeber (und herausgeber_url) übernommen und aus dem Titel entfernt ("Titel - Herausgeber").
    """
    import feedparser

    feed = feedparser.parse(daten)
    if not feed.entries and (feed.bozo or not feed.get("version")):
        grund = type(feed.bozo_exception).__name__ if feed.bozo else "kein RSS/Atom erkannt"
        raise Fehler(f"Kein gültiger RSS/Atom-Feed ({grund}).")
    meldungen = []
    for eintrag in feed.entries:
        link = eintrag.get("link") or ""
        if urlparse(link).scheme not in ("http", "https"):
            continue
        titel = _kurztext(eintrag.get("title", ""), 300)
        quelle = eintrag.get("source") or {}
        herausgeber = _kurztext(quelle.get("title", ""), 80) or None
        herausgeber_url = quelle.get("href") if urlparse(quelle.get("href") or "").scheme in ("http", "https") else None
        if herausgeber and titel.endswith(f" - {herausgeber}"):
            titel = titel[: -len(herausgeber) - 3].rstrip()
        if not titel:
            continue
        meldungen.append({"id": _id(eintrag), "zeit": _zeit(eintrag), "titel": titel, "link": link,
                          "kurztext": _kurztext(eintrag.get("summary", ""), maximal),
                          "herausgeber": herausgeber, "herausgeber_url": herausgeber_url})
    return meldungen


def feeds_aufloesen(konfig: dict, tickers: list[str]) -> list[dict]:
    """Aktive Feeds; Vorlagen mit {ticker} werden je Wert des Universums aufgelöst."""
    ergebnis = []
    for feed in konfig.get("feeds", []):
        if not feed.get("aktiv", True):
            continue
        if feed.get("je_ticker"):
            for ticker in tickers:
                ergebnis.append({**feed, "id": f"{feed['id']}:{ticker}", "url": feed["url"].replace(
                    "{ticker}", quote(ticker, safe="")), "ticker": [ticker], "je_ticker": False})
        else:
            ergebnis.append(feed)
    return ergebnis


def _speicher_dateien() -> list[Path]:
    return sorted(g.pfad("news").glob("*.jsonl")) if g.pfad("news").exists() else []


def gespeicherte(tage: int | None = None) -> list[dict]:
    grenze = g.jetzt() - timedelta(days=tage) if tage else None
    meldungen = []
    for datei in _speicher_dateien():
        for zeile in datei.read_text(encoding="utf-8").splitlines():
            if not zeile.strip():
                continue
            eintrag = json.loads(zeile)
            stichtag = g.zeit_lesen(eintrag.get("zeit") or eintrag["abgerufen"])
            if grenze is None or stichtag >= grenze:
                meldungen.append(eintrag)
    meldungen.sort(key=lambda e: e.get("zeit") or e["abgerufen"], reverse=True)
    return meldungen


def _bekannte_ids() -> set[str]:
    """IDs und Titelschlüssel der letzten Monate (ältere Einträge ohne Herausgeber eingeschlossen)."""
    ids = set()
    for datei in _speicher_dateien()[-MONATE_FUER_DUPLIKATE:]:
        for zeile in datei.read_text(encoding="utf-8").splitlines():
            if zeile.strip():
                eintrag = json.loads(zeile)
                ids.add(eintrag["id"])
                ids.add("T:" + titel_schluessel(eintrag["titel"]))
    return ids


def stand_pfad() -> Path:
    return pfade.cache_pfad("news_stand.json")


def abrufen(konfig: dict | None = None) -> dict:
    """Ruft alle aktiven Feeds ab und hängt neue Meldungen an news/JJJJ-MM.jsonl an."""
    import kurse

    konfig = konfig or standard_konfig()
    maximal = int(konfig.get("kurztext_max_zeichen", 300))
    agent = konfig.get("user_agent") or standard_konfig()["user_agent"]
    schlagworte = konfig.get("schlagworte", standard_konfig().get("schlagworte", {}))
    feeds = feeds_aufloesen(konfig, kurse.markt_tickers())
    abruf = g.jetzt()
    bekannt = _bekannte_ids()
    neu, status = [], {}
    for feed in feeds:
        try:
            meldungen = parsen(HOLEN(feed["url"], agent), maximal)
        except Fehler as exc:
            status[feed["id"]] = {"name": feed.get("name"), "ok": False, "fehler": str(exc)[:200], "anzahl": 0}
            continue
        except Exception as exc:  # ein kaputter Feed stoppt die anderen nicht
            status[feed["id"]] = {"name": feed.get("name"), "ok": False,
                                  "fehler": f"{type(exc).__name__}: {str(exc)[:160]}", "anzahl": 0}
            continue
        zaehler = gefiltert = dubletten = 0
        for meldung in meldungen:
            if meldung["id"] in bekannt:
                continue
            if not filtern(meldung, feed):
                gefiltert += 1
                continue
            titel_key = "T:" + titel_schluessel(meldung["titel"])
            if titel_key in bekannt:
                dubletten += 1
                continue
            bekannt.update((meldung["id"], titel_key))
            ticker = list(dict.fromkeys([*feed.get("ticker", []),
                                         *_schlagwort_treffer(meldung["titel"], schlagworte)]))
            neu.append({"id": meldung["id"], "abgerufen": g.iso(abruf), "zeit": meldung["zeit"],
                        "quelle": feed["id"], "quelle_name": feed.get("name", feed["id"]), "titel": meldung["titel"],
                        "kurztext": meldung["kurztext"], "link": meldung["link"], "ticker": ticker,
                        "herausgeber": meldung["herausgeber"], "herausgeber_url": meldung["herausgeber_url"]})
            zaehler += 1
        status[feed["id"]] = {"name": feed.get("name"), "ok": True, "fehler": None, "anzahl": len(meldungen),
                              "neu": zaehler, "gefiltert": gefiltert, "dubletten": dubletten}
    if neu:
        g.text_anhaengen(g.pfad("news", f"{abruf:%Y-%m}.jsonl"),
                         "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in neu))
    stand = {"zeit": g.iso(abruf), "neu": len(neu), "feeds": status,
             "fehlerhaft": sum(1 for s in status.values() if not s["ok"]), "anzahl_feeds": len(status)}
    g.json_schreiben(stand_pfad(), stand)
    return stand


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="News aus RSS-Feeds (nur Titel, Kurztext, Link).")
    unter = parser.add_subparsers(dest="befehl", required=True)
    p = unter.add_parser("abrufen", help="aktive Feeds abrufen und neue Meldungen speichern")
    p.add_argument("--konfig", help="JSON mit wirksamer Feed-Konfiguration (Standard: config/news.json)")
    p = unter.add_parser("liste", help="gespeicherte Meldungen (neueste zuerst)")
    p.add_argument("--tage", type=int, default=3)
    p.add_argument("--ticker")
    p.add_argument("--anzahl", type=int, default=50)
    p.add_argument("--json", action="store_true")
    p = unter.add_parser("test", help="einen Feed abrufen und prüfen, ohne zu speichern")
    p.add_argument("--url", required=True)
    args = parser.parse_args(argv)
    try:
        if args.befehl == "abrufen":
            konfig = g.json_lesen(Path(args.konfig)) if args.konfig else None
            stand = abrufen(konfig)
            print(f"News: {stand['neu']} neue Meldungen aus {stand['anzahl_feeds']} Feeds "
                  f"({stand['fehlerhaft']} mit Fehler).")
            for kennung, s in stand["feeds"].items():
                if not s["ok"]:
                    print(f"  {kennung}: {s['fehler']}")
        elif args.befehl == "liste":
            meldungen = [m for m in gespeicherte(args.tage) if not args.ticker or args.ticker in m["ticker"]]
            meldungen = meldungen[: args.anzahl]
            if args.json:
                print(json.dumps(meldungen, ensure_ascii=False, indent=1))
            for m in [] if args.json else meldungen:
                zeit = (m.get("zeit") or m["abgerufen"])[:16].replace("T", " ")
                ticker = f" [{', '.join(m['ticker'])}]" if m["ticker"] else ""
                von = m.get("herausgeber") or m["quelle_name"]
                print(f"{m['id']} | {zeit} | {von}{ticker} | {m['titel']} | {m['link']}")
        else:
            agent = standard_konfig()["user_agent"]
            meldungen = parsen(HOLEN(args.url, agent))
            print(f"Feed gültig: {len(meldungen)} Meldungen.")
            for m in meldungen[:5]:
                print(f"- {m['titel']}")
    except Fehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
