#!/usr/bin/env python3
"""Beobachtungsliste und Screener: Kennzahlen aus Tagesdaten für viele Aktien und ETFs.

    python tools/beobachtung.py aktualisieren [--liste <id>]      Tageskerzen holen (yfinance), Kennzahlen berechnen
    python tools/beobachtung.py kandidaten [--anzahl 8] [--liste <id>] [--json]
    python tools/beobachtung.py liste [--sortiert <kennzahl>] [--aufsteigend] [--anzahl 30] [--liste <id>] [--json]
    python tools/beobachtung.py werte <ticker> ...                 Kennzahlen einzelner Werte
    python tools/beobachtung.py pruefen                            Werte ohne Kursdaten, Stand der Listen

Warum: Handelbar ist jede Aktie und jeder ETF an Xetra, NYSE und NASDAQ (regeln.md Abschnitt 3), aber der
Marktüberblick zeigt nur wenige Werte. Der Screener rechnet (Rechnen macht Code) aus den Tagesschlusskursen
Kennzahlen für die Listen in config/beobachtung.json und nennt Kandidaten, die Claude dann prüft.

Die Kennzahlen sind Orientierung, keine Kurse im Sinne von regeln.md Abschnitt 5: Gebucht wird nur zu
protokollierten Kursen (python tools/kurse.py aktuell <ticker>), nie zu Werten aus dieser Datei. Der Stand liegt
im Zwischenspeicher (.cache/beobachtung.json), nicht im Spielstand. Den Abruf übernimmt der Hintergrunddienst
nach Handelsschluss; die Befehle zum Lesen brauchen kein Netzwerk.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from datetime import date, datetime, timedelta

import gemeinsam as g
import kurse
import pfade
from gemeinsam import D, Fehler

BLOCK = 80  # Werte je Abruf bei yfinance
HANDELSTAGE_JAHR = 252
VERALTET_TAGE = 4  # Wochenende plus ein Feiertag

# Kennzahl -> (Überschrift, Art der Anzeige)
KENNZAHLEN = {
    "kurs": ("Kurs", "preis"),
    "rendite_1t": ("1 Tag", "prozent"),
    "rendite_5t": ("5 Tage", "prozent"),
    "rendite_20t": ("20 Tage", "prozent"),
    "rendite_60t": ("60 Tage", "prozent"),
    "abstand_hoch": ("zum 52-Wochen-Hoch", "prozent"),
    "abstand_tief": ("zum 52-Wochen-Tief", "prozent"),
    "sma20_abstand": ("zum 20-Tage-Schnitt", "prozent"),
    "sma50_abstand": ("zum 50-Tage-Schnitt", "prozent"),
    "gap_1t": ("Eröffnungslücke", "prozent"),
    "volumen_relativ_1t": ("Volumen zum 20-Tage-Schnitt", "faktor"),
    "volatilitaet_20t": ("Schwankung (20 Tage, p. a.)", "prozent_abs"),
}


def standard_konfig() -> dict:
    return g.config("beobachtung")


def stand_pfad():
    return pfade.cache_pfad("beobachtung.json")


# --------------------------------------------------------------------------
# Abruf (yfinance gebündelt); in Tests ersetzt (kein Netzwerk)


def _teilframe(daten, ticker: str, einzeln: bool):
    """Teil einer yfinance-Antwort für einen Wert, egal in welcher Reihenfolge die Spaltenebenen liegen."""
    spalten = daten.columns
    if getattr(spalten, "nlevels", 1) == 2:
        for ebene in (0, 1):
            if ticker in spalten.get_level_values(ebene):
                return daten.xs(ticker, axis=1, level=ebene)
        return None
    return daten if einzeln else None


def _kerzen_aus_frame(frame) -> list[dict]:
    spalten = {"Open", "High", "Low", "Close"}
    if not spalten <= set(frame.columns):
        return []
    frame = frame.dropna(subset=list(spalten))
    kerzen = []
    for index, zeile in frame.iterrows():
        volumen = zeile["Volume"] if "Volume" in frame.columns else 0
        kerzen.append({"datum": index.date(), "open": float(zeile["Open"]), "high": float(zeile["High"]),
                       "low": float(zeile["Low"]), "close": float(zeile["Close"]),
                       "volume": 0.0 if volumen != volumen else float(volumen)})
    return kerzen


def _yfinance_holen(tickers: list[str], block: int = BLOCK) -> dict[str, list[dict]]:
    """Tageskerzen eines Jahres je Wert. Ein fehlgeschlagener Block lässt nur seine Werte fehlen."""
    import yfinance as yf

    ergebnis: dict[str, list[dict]] = {}
    for beginn in range(0, len(tickers), block):
        teil = tickers[beginn:beginn + block]
        try:
            daten = yf.download(teil, period="1y", interval="1d", auto_adjust=False, group_by="ticker",
                                progress=False, threads=True, timeout=30)
        except Exception:  # Netzwerk- und Quellfehler: dieser Block fehlt, die übrigen laufen weiter
            continue
        if daten is None or daten.empty:
            continue
        for ticker in teil:
            frame = _teilframe(daten, ticker, len(teil) == 1)
            kerzen = _kerzen_aus_frame(frame) if frame is not None else []
            if kerzen:
                ergebnis[ticker] = kerzen
        time.sleep(1.0)  # Yahoo nicht bedrängen
    return ergebnis


HOLEN = _yfinance_holen  # in Tests ersetzt


# --------------------------------------------------------------------------
# Kennzahlen (reine Rechnung auf Tageskerzen)


def _anteil(neu: float, alt: float) -> float | None:
    return round(neu / alt - 1, 6) if alt else None


def kennzahlen(kerzen: list[dict]) -> dict | None:
    """Kennzahlen aus aufsteigend sortierten Tageskerzen (datum, open, high, low, close, volume).

    Anteile sind Brüche (0,0123 = 1,23 %). Fehlt Historie für eine Kennzahl, ist sie None.
    """
    kerzen = sorted(kerzen, key=lambda k: k["datum"])
    n = len(kerzen)
    if n < 2 or kerzen[-1]["close"] <= 0:
        return None
    schluss = [k["close"] for k in kerzen]
    kurs, vortag = schluss[-1], schluss[-2]

    def rendite(tage: int) -> float | None:
        return _anteil(kurs, schluss[-1 - tage]) if n > tage and schluss[-1 - tage] > 0 else None

    jahr = kerzen[-HANDELSTAGE_JAHR:]
    hoch, tief = max(k["high"] for k in jahr), min(k["low"] for k in jahr)
    tagesrenditen = [schluss[i] / schluss[i - 1] - 1 for i in range(n - 20, n)] if n > 20 else []
    schwankung = (round(statistics.stdev(tagesrenditen) * math.sqrt(HANDELSTAGE_JAHR), 4)
                  if len(tagesrenditen) == 20 else None)
    volumen = [k["volume"] for k in kerzen[-21:-1]] if n > 20 else []
    schnitt_vol = sum(volumen) / len(volumen) if volumen else 0
    return {
        "datum": kerzen[-1]["datum"].isoformat(), "kurs": round(kurs, 4), "tage": n,
        "rendite_1t": _anteil(kurs, vortag), "rendite_5t": rendite(5), "rendite_20t": rendite(20),
        "rendite_60t": rendite(60),
        "abstand_hoch": _anteil(kurs, hoch), "abstand_tief": _anteil(kurs, tief) if tief > 0 else None,
        "sma20_abstand": _anteil(kurs, sum(schluss[-20:]) / 20) if n >= 20 else None,
        "sma50_abstand": _anteil(kurs, sum(schluss[-50:]) / 50) if n >= 50 else None,
        "gap_1t": _anteil(kerzen[-1]["open"], vortag),
        "volumen_relativ_1t": round(kerzen[-1]["volume"] / schnitt_vol, 3) if schnitt_vol > 0 else None,
        "volatilitaet_20t": schwankung,
    }


# --------------------------------------------------------------------------
# Listen und Stand


def werte_der_listen(konfig: dict, nur: str | None = None) -> dict[str, dict]:
    """ticker -> {name, listen} über alle (oder eine) Listen; ein Wert in mehreren Listen erscheint einmal."""
    listen = konfig["listen"]
    if nur is not None and nur not in listen:
        raise Fehler(f"Unbekannte Liste '{nur}'. Vorhanden: {', '.join(listen)}.")
    werte: dict[str, dict] = {}
    for kennung, liste in listen.items():
        if nur is not None and kennung != nur:
            continue
        for ticker in liste["ticker"]:
            eintrag = werte.setdefault(ticker, {"name": None, "listen": []})
            eintrag["name"] = eintrag["name"] or liste.get("namen", {}).get(ticker)
            eintrag["listen"].append(kennung)
    return werte


def _handelbar(ticker: str, kurs: float, mindestkurs) -> tuple[bool, str | None, str | None]:
    """(handelbar, Währung, Grund) nach regeln.md Abschnitt 3: erlaubte Börse und Kurs mindestens 1."""
    try:
        waehrung = kurse.waehrung(ticker)
    except Fehler:
        return False, None, "Börse nicht erlaubt (nur Xetra .DE, NYSE, NASDAQ)"
    if D(str(kurs)) < mindestkurs:
        return False, waehrung, f"Kurs unter {mindestkurs} {waehrung}"
    return True, waehrung, None


def _markt_offen(ticker: str, zeitpunkt: datetime) -> bool:
    try:
        return kurse.markt_offen(ticker, zeitpunkt)
    except Fehler:
        return False


def vorheriger_stand() -> dict:
    try:
        return g.json_lesen(stand_pfad())
    except (OSError, ValueError):
        return {}


def aktualisieren(konfig: dict | None = None, nur: str | None = None) -> dict:
    """Holt die Tageskerzen aller Werte, berechnet Kennzahlen und schreibt den Stand (.cache/beobachtung.json)."""
    konfig = konfig or standard_konfig()
    werte = werte_der_listen(konfig, nur)
    mindestkurs = D(str(kurse.universum()["aktien"]["mindestkurs"]))
    jetzt = g.jetzt()
    roh = HOLEN(sorted(werte))
    if not roh:
        raise Fehler("Keine Kursdaten erhalten (Quelle nicht erreichbar?); der bisherige Stand bleibt erhalten.")
    alt = vorheriger_stand().get("eintraege", {})
    eintraege: dict[str, dict] = {}
    ohne_daten, uebernommen = [], []
    for ticker, info in sorted(werte.items()):
        kerzen = roh.get(ticker) or []
        # Der laufende Handelstag ist noch keine fertige Tageskerze.
        if kerzen and kerzen[-1]["datum"] == jetzt.date() and _markt_offen(ticker, jetzt):
            kerzen = kerzen[:-1]
        zahlen = kennzahlen(kerzen) if kerzen else None
        if zahlen is None:
            if ticker in alt:  # Abruf lückenhaft: alter Stand bleibt sichtbar, gekennzeichnet
                eintraege[ticker] = {**alt[ticker], "listen": info["listen"], "veraltet": True}
                uebernommen.append(ticker)
            else:
                ohne_daten.append(ticker)
            continue
        handelbar, waehrung, grund = _handelbar(ticker, zahlen["kurs"], mindestkurs)
        eintraege[ticker] = {"name": info["name"], "listen": info["listen"], "waehrung": waehrung,
                             "handelbar": handelbar, "grund": grund, **zahlen}
    listen = {}
    for kennung, liste in konfig["listen"].items():
        if nur is not None and kennung != nur:
            continue
        ticker = liste["ticker"]
        listen[kennung] = {"name": liste["name"], "anzahl": len(ticker),
                           "mit_daten": sum(1 for t in ticker if t in eintraege)}
    stand = {"zeit": g.iso(jetzt), "quelle": "yfinance", "anzahl": len(werte), "mit_daten": len(eintraege),
             "aktuell": len(eintraege) - len(uebernommen), "listen": listen, "ohne_daten": ohne_daten,
             "veraltet": uebernommen, "eintraege": eintraege}
    g.json_schreiben(stand_pfad(), stand)
    return stand


def stand_lesen() -> dict:
    stand = vorheriger_stand()
    if not stand.get("eintraege"):
        raise Fehler("Noch keine Daten in der Beobachtungsliste. Der Hintergrunddienst holt sie nach Handelsschluss; "
                     "von Hand: python tools/beobachtung.py aktualisieren (braucht Netzwerk).")
    return stand


# --------------------------------------------------------------------------
# Auswahl und Anzeige


def auswahl(stand: dict, liste: str | None = None, nur_handelbar: bool = True) -> list[tuple[str, dict]]:
    if liste is not None and liste not in stand["listen"]:
        raise Fehler(f"Unbekannte Liste '{liste}'. Vorhanden: {', '.join(stand['listen'])}.")
    zeilen = []
    for ticker, e in stand["eintraege"].items():
        if liste is not None and liste not in e["listen"]:
            continue
        if nur_handelbar and not e.get("handelbar"):
            continue
        if e.get("veraltet"):
            continue
        zeilen.append((ticker, e))
    return zeilen


def sortieren(zeilen: list[tuple[str, dict]], schluessel: str, absteigend: bool = True) -> list[tuple[str, dict]]:
    mit = [z for z in zeilen if z[1].get(schluessel) is not None]
    return sorted(mit, key=lambda z: (z[1][schluessel], z[0]), reverse=absteigend)


def _zahl(wert: float, stellen: int = 2) -> str:
    return f"{wert:,.{stellen}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def _prozent(wert: float | None, vorzeichen: bool = True) -> str:
    if wert is None:
        return "–"
    text = _zahl(wert * 100, 2)
    return (("+" if wert > 0 else "") + text if vorzeichen else text) + " %"


def zeile_text(ticker: str, e: dict) -> str:
    name = f" {e['name']}" if e.get("name") else ""
    faktor = f"{_zahl(e['volumen_relativ_1t'], 1)}x" if e.get("volumen_relativ_1t") is not None else "–"
    return (f"{ticker:<9}{_zahl(e['kurs']):>11} {e.get('waehrung') or '':<3} 1T {_prozent(e['rendite_1t']):>9} "
            f"5T {_prozent(e['rendite_5t']):>9} 20T {_prozent(e['rendite_20t']):>9} Hoch {_prozent(e['abstand_hoch']):>9} "
            f"Vol. {faktor:>6} Schw. {_prozent(e['volatilitaet_20t'], False):>8}{name}")


def kopfzeile(stand: dict, liste: str | None) -> list[str]:
    zeit = g.zeit_lesen(stand["zeit"])
    text = [f"Beobachtungsliste{f' {liste}' if liste else ''}: {stand['mit_daten']} von {stand['anzahl']} Werten mit Daten, "
            f"Stand {zeit:%d.%m.%Y %H:%M} (Tagesschlusskurse, {stand.get('quelle', 'yfinance')}). Nur zur Orientierung: "
            "gebucht wird zu protokollierten Kursen (python tools/kurse.py aktuell <ticker>)."]
    if g.jetzt() - zeit > timedelta(days=VERALTET_TAGE):
        text.append(f"WARNUNG: Der Stand ist älter als {VERALTET_TAGE} Tage; der Hintergrunddienst aktualisiert nach "
                    "Handelsschluss (Systemstatus prüfen).")
    return text


KANDIDATENBLOECKE = [
    ("Stärkste Tagesbewegung nach oben", "rendite_1t", True, None),
    ("Stärkste Tagesbewegung nach unten", "rendite_1t", False, None),
    ("Stärkster 5-Tage-Trend", "rendite_5t", True, None),
    ("Schwächster 5-Tage-Trend", "rendite_5t", False, None),
    ("Stärkster 20-Tage-Trend", "rendite_20t", True, None),
    ("Nahe am 52-Wochen-Hoch", "abstand_hoch", True, None),
    ("Auffälliges Volumen bei steigendem Kurs", "volumen_relativ_1t", True, ("rendite_1t", 0)),
    ("Eröffnungslücke nach oben", "gap_1t", True, None),
]


def kandidaten(stand: dict, anzahl: int = 8, liste: str | None = None) -> list[dict]:
    zeilen = auswahl(stand, liste)
    bloecke = []
    for titel, schluessel, absteigend, bedingung in KANDIDATENBLOECKE:
        kandidaten_ = [z for z in zeilen if bedingung is None or (z[1].get(bedingung[0]) or 0) > bedingung[1]]
        bloecke.append({"titel": titel, "kennzahl": schluessel,
                        "werte": [{"ticker": t, **e} for t, e in sortieren(kandidaten_, schluessel, absteigend)[:anzahl]]})
    return bloecke


# --------------------------------------------------------------------------
# Kommandozeile


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Beobachtungsliste und Screener (Kennzahlen aus Tagesdaten).")
    unter = parser.add_subparsers(dest="befehl", required=True)
    p = unter.add_parser("aktualisieren", help="Tageskerzen holen und Kennzahlen berechnen (braucht Netzwerk)")
    p.add_argument("--liste", help="nur diese Liste aus config/beobachtung.json")
    p = unter.add_parser("kandidaten", help="Auffällige Werte in mehreren Kategorien")
    p.add_argument("--anzahl", type=int, default=8)
    p.add_argument("--liste")
    p.add_argument("--json", action="store_true")
    p = unter.add_parser("liste", help="Werte nach einer Kennzahl sortiert")
    p.add_argument("--sortiert", choices=sorted(KENNZAHLEN), default="rendite_5t")
    p.add_argument("--aufsteigend", action="store_true")
    p.add_argument("--anzahl", type=int, default=30)
    p.add_argument("--liste")
    p.add_argument("--json", action="store_true")
    p = unter.add_parser("werte", help="Kennzahlen einzelner Werte")
    p.add_argument("ticker", nargs="+")
    unter.add_parser("pruefen", help="Werte ohne Kursdaten und Stand der Listen")
    args = parser.parse_args(argv)
    try:
        if args.befehl == "aktualisieren":
            stand = aktualisieren(nur=args.liste)
            print(f"Beobachtungsliste: {stand['aktuell']} von {stand['anzahl']} Werten aktualisiert "
                  f"({stand['quelle']}), {len(stand['veraltet'])} mit altem Stand, {len(stand['ohne_daten'])} ohne Daten.")
            if stand["ohne_daten"]:
                print("  Ohne Daten (Kürzel prüfen oder aus der Liste nehmen): " + ", ".join(stand["ohne_daten"][:30])
                      + (" …" if len(stand["ohne_daten"]) > 30 else ""))
        elif args.befehl == "kandidaten":
            stand = stand_lesen()
            bloecke = kandidaten(stand, args.anzahl, args.liste)
            if args.json:
                print(json.dumps(bloecke, ensure_ascii=False, indent=1))
            else:
                print("\n".join(kopfzeile(stand, args.liste)))
                for block in bloecke:
                    print(f"\n== {block['titel']}")
                    for e in block["werte"]:
                        print(zeile_text(e["ticker"], e))
        elif args.befehl == "liste":
            stand = stand_lesen()
            zeilen = sortieren(auswahl(stand, args.liste), args.sortiert, not args.aufsteigend)[:args.anzahl]
            if args.json:
                print(json.dumps([{"ticker": t, **e} for t, e in zeilen], ensure_ascii=False, indent=1))
            else:
                print("\n".join(kopfzeile(stand, args.liste)))
                print(f"\n== Sortiert nach {KENNZAHLEN[args.sortiert][0]} ({'aufsteigend' if args.aufsteigend else 'absteigend'})")
                for t, e in zeilen:
                    print(zeile_text(t, e))
        elif args.befehl == "werte":
            stand = stand_lesen()
            for ticker in args.ticker:
                e = stand["eintraege"].get(ticker)
                if e is None:
                    print(f"{ticker}: nicht in der Beobachtungsliste (Kurs über python tools/kurse.py aktuell {ticker}).")
                    continue
                print(zeile_text(ticker, e) + (" [alter Stand]" if e.get("veraltet") else "")
                      + ("" if e.get("handelbar") else f" [nicht handelbar: {e.get('grund')}]"))
        else:
            stand = stand_lesen()
            print("\n".join(kopfzeile(stand, None)))
            for kennung, liste in stand["listen"].items():
                print(f"  {liste['name']}: {liste['mit_daten']} von {liste['anzahl']} mit Daten")
            if stand["ohne_daten"]:
                print("Ohne Daten: " + ", ".join(stand["ohne_daten"]))
            if stand["veraltet"]:
                print("Alter Stand (Abruf lückenhaft): " + ", ".join(stand["veraltet"]))
            nicht = [t for t, e in stand["eintraege"].items() if not e.get("handelbar")]
            if nicht:
                print("Nicht handelbar: " + ", ".join(nicht))
    except Fehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
