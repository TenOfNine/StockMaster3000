#!/usr/bin/env python3
"""Kursdaten: aktuelle Kurse mit Protokoll, Tageshistorie mit Zwischenspeicher.

Alle Kurse für Buchungen kommen aus diesem Werkzeug. Aktuelle Abfragen werden
in data/kurse/JJJJ-MM-TT.csv protokolliert, Tagesdaten (OHLC, Dividenden,
Splits) in data/historie/ zwischengespeichert. Der Marktstatus ergibt sich
aus config/universum.json.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import gemeinsam as g
from gemeinsam import D, Fehler, KursFehler

KURS_FELDER = ["zeit", "ticker", "kurs", "waehrung", "quelle", "markt_offen"]
HISTORIE_FELDER = ["datum", "open", "high", "low", "close", "dividende", "split"]


@dataclass
class Kurs:
    ticker: str
    kurs: Decimal
    waehrung: str
    zeit: datetime          # Zeitpunkt der Abfrage (= Protokollzeit)
    quelle: str
    markt_offen: bool
    kurs_zeit: datetime     # Zeitstempel des Kurses laut Quelle


@dataclass
class Kerze:
    datum: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    dividende: Decimal = Decimal("0")
    split: Decimal = Decimal("0")


def _runden(wert) -> Decimal:
    return D(wert).quantize(Decimal("0.000001"))


# --------------------------------------------------------------------------
# Kursquelle (wird in Tests durch eine Attrappe ersetzt)


class YFinanceQuelle:
    """Kursquelle Yahoo Finance über yfinance (verzögert, frei verfügbar)."""

    name = "yfinance"

    def aktuell(self, ticker: str) -> tuple[Decimal, datetime]:
        import yfinance as yf

        objekt = yf.Ticker(ticker)
        try:
            daten = objekt.history(period="5d", interval="1m", auto_adjust=False, prepost=False)
        except Exception as exc:  # Netzwerk- und Quellfehler verständlich melden
            raise KursFehler(f"Kursabfrage für {ticker} fehlgeschlagen: {exc}") from exc
        if daten is not None and not daten.empty:
            zeile = daten.dropna(subset=["Close"]).iloc[-1]
            zeitpunkt = daten.dropna(subset=["Close"]).index[-1].to_pydatetime()
            return _runden(float(zeile["Close"])), zeitpunkt.astimezone(g.TZ)
        raise KursFehler(f"Yahoo Finance liefert keinen aktuellen Kurs für {ticker}.")

    def historie(self, ticker: str, von: date, bis: date) -> list[Kerze]:
        import yfinance as yf

        try:
            daten = yf.Ticker(ticker).history(
                start=von.isoformat(), end=(bis + timedelta(days=1)).isoformat(),
                interval="1d", auto_adjust=False, actions=True)
        except Exception as exc:
            raise KursFehler(f"Historische Kurse für {ticker} nicht abrufbar: {exc}") from exc
        if daten is None or daten.empty:
            return []
        daten = daten.dropna(subset=["Open", "High", "Low", "Close"])
        splits = daten["Stock Splits"] if "Stock Splits" in daten else None
        dividenden = daten["Dividends"] if "Dividends" in daten else None
        # Yahoo passt Kurse rückwirkend an Splits an. Für die Simulation werden
        # die tatsächlich gehandelten Kurse benötigt: Faktor aller Splits, die
        # nach dem jeweiligen Tag liegen (Abruf reicht immer bis heute).
        zeilen = list(daten.iterrows())
        faktoren = [Decimal("1")] * len(zeilen)
        laufend = Decimal("1")
        for i in range(len(zeilen) - 1, -1, -1):
            faktoren[i] = laufend
            if splits is not None and float(zeilen[i][1]["Stock Splits"] or 0) > 0:
                laufend *= D(float(zeilen[i][1]["Stock Splits"]))
        kerzen = []
        for (index, zeile), faktor in zip(zeilen, faktoren):
            kerzen.append(Kerze(
                datum=index.date(),
                open=_runden(D(float(zeile["Open"])) * faktor),
                high=_runden(D(float(zeile["High"])) * faktor),
                low=_runden(D(float(zeile["Low"])) * faktor),
                close=_runden(D(float(zeile["Close"])) * faktor),
                dividende=_runden(D(float(zeile["Dividends"])) * faktor) if dividenden is not None else Decimal("0"),
                split=_runden(float(zeile["Stock Splits"])) if splits is not None else Decimal("0"),
            ))
        return kerzen

    def marktkapitalisierung(self, ticker: str) -> Decimal | None:
        import yfinance as yf

        try:
            wert = yf.Ticker(ticker).fast_info.get("market_cap")
        except Exception:
            wert = None
        return D(float(wert)) if wert else None


QUELLE = YFinanceQuelle()


# --------------------------------------------------------------------------
# Universum und Handelszeiten


def universum() -> dict:
    return g.config("universum")


def boerse_von(ticker: str) -> tuple[str, dict]:
    """Ordnet einen Ticker einer Börse aus config/universum.json zu."""
    uni = universum()
    if ticker in uni["basiswerte"]:
        name = uni["basiswerte"][ticker]["boerse"]
    elif ticker in uni.get("sonstige_ticker", {}):
        name = uni["sonstige_ticker"][ticker]["boerse"]
    elif "." in ticker:
        suffix = "." + ticker.rsplit(".", 1)[1]
        if suffix not in uni["aktien"]["suffix_boerse"]:
            raise Fehler(f"{ticker}: Börse '{suffix}' ist nicht erlaubt (nur Xetra .DE, NYSE, NASDAQ).")
        name = uni["aktien"]["suffix_boerse"][suffix]
    elif any(zeichen in ticker for zeichen in "^=/"):
        raise Fehler(f"{ticker} gehört nicht zum Universum (config/universum.json).")
    else:
        name = uni["aktien"]["ohne_suffix"]
    return name, uni["boersen"][name]


def waehrung(ticker: str) -> str:
    return boerse_von(ticker)[1]["waehrung"]


def ist_handelstag(ticker: str, datum: date) -> bool:
    """Handelstag laut Kalender (Wochentag und Feiertage der Börse)."""
    _, boerse = boerse_von(ticker)
    return datum.weekday() in boerse["handelstage"] and datum.isoformat() not in boerse["feiertage"]


def _boersenzeit(boerse: dict, datum: date, uhr: str) -> datetime:
    zone = ZoneInfo(boerse["zeitzone"])
    return datetime.combine(datum, g.uhrzeit(uhr), tzinfo=zone).astimezone(g.TZ)


def oeffnung(ticker: str, datum: date) -> datetime:
    return _boersenzeit(boerse_von(ticker)[1], datum, boerse_von(ticker)[1]["oeffnung"])


def schluss(ticker: str, datum: date) -> datetime:
    return _boersenzeit(boerse_von(ticker)[1], datum, boerse_von(ticker)[1]["schluss"])


def kerzen_beginn(ticker: str, datum: date) -> datetime:
    """Frühester Zeitpunkt, zu dem die Tageskerze des Datums beginnt.

    Eine vorgemerkte Order darf nur Kerzen nutzen, die nach ihrer Erfassung
    beginnen (kein Backdating).
    """
    _, boerse = boerse_von(ticker)
    if "bar_beginn_vortag" in boerse:
        return _boersenzeit(boerse, datum - timedelta(days=1), boerse["bar_beginn_vortag"])
    return _boersenzeit(boerse, datum, boerse["oeffnung"])


def markt_offen(ticker: str, zeitpunkt: datetime | None = None) -> bool:
    zeitpunkt = (zeitpunkt or g.jetzt()).astimezone(g.TZ)
    _, boerse = boerse_von(ticker)
    lokal = zeitpunkt.astimezone(ZoneInfo(boerse["zeitzone"]))
    if not ist_handelstag(ticker, lokal.date()):
        return False
    return oeffnung(ticker, lokal.date()) <= zeitpunkt < schluss(ticker, lokal.date())


def feiertage_gepflegt(jahr: int) -> list[str]:
    """Börsen mit Feiertagspflicht, für die das Jahr fehlt."""
    fehlend = []
    for name, boerse in universum()["boersen"].items():
        if name in ("xetra", "nyse") and not any(f.startswith(str(jahr)) for f in boerse["feiertage"]):
            fehlend.append(name)
    return fehlend


# --------------------------------------------------------------------------
# Aktuelle Kurse


def kurs_protokoll_pfad(datum: date) -> Path:
    return g.pfad("data", "kurse", f"{datum.isoformat()}.csv")


def aktuell(tickers: list[str]) -> list[Kurs]:
    """Fragt aktuelle Kurse ab und protokolliert jeden einzelnen."""
    ergebnisse = []
    max_alter = timedelta(minutes=g.projekt()["max_kursalter_minuten"])
    for ticker in tickers:
        _, boerse = boerse_von(ticker)
        abfrage = g.jetzt()
        try:
            wert, kurs_zeit = QUELLE.aktuell(ticker)
        except KursFehler:
            raise
        except Exception as exc:
            raise KursFehler(f"Kursabfrage für {ticker} fehlgeschlagen: {exc}") from exc
        if wert is None or D(wert) <= 0:
            raise KursFehler(f"Für {ticker} kam kein gültiger Kurs (Wert: {wert}).")
        offen = markt_offen(ticker, abfrage)
        kurs_zeit = kurs_zeit.astimezone(g.TZ) if kurs_zeit else abfrage
        if offen and abfrage - kurs_zeit > max_alter:
            raise KursFehler(
                f"Kurs für {ticker} ist veraltet ({kurs_zeit.isoformat()}, älter als "
                f"{max_alter.seconds // 60} Minuten) obwohl der Markt offen ist. Kein Handel ohne verlässlichen Kurs.")
        kurs = Kurs(ticker=ticker, kurs=_runden(wert), waehrung=boerse["waehrung"], zeit=abfrage,
                    quelle=QUELLE.name, markt_offen=offen, kurs_zeit=kurs_zeit)
        g.csv_anhaengen(kurs_protokoll_pfad(abfrage.date()), KURS_FELDER, [{
            "zeit": g.iso(kurs.zeit), "ticker": ticker, "kurs": kurs.kurs, "waehrung": kurs.waehrung,
            "quelle": kurs.quelle, "markt_offen": "ja" if offen else "nein"}])
        ergebnisse.append(kurs)
    return ergebnisse


def devisenkurs_aktuell() -> Kurs:
    return aktuell([g.projekt()["devisen_ticker"]])[0]


def in_eur(betrag, waehrung_code: str, eurusd) -> Decimal:
    """Rechnet einen Betrag in EUR um; EURUSD=X ist USD je EUR."""
    if waehrung_code == "EUR":
        return D(betrag)
    if waehrung_code == "USD":
        if eurusd is None or D(eurusd) <= 0:
            raise KursFehler("Für die Umrechnung von USD fehlt ein gültiger EURUSD-Kurs.")
        return D(betrag) / D(eurusd)
    raise Fehler(f"Währung {waehrung_code} wird nicht unterstützt.")


def marktkapitalisierung(ticker: str) -> Decimal | None:
    return QUELLE.marktkapitalisierung(ticker)


# --------------------------------------------------------------------------
# Historie


def _dateiname(ticker: str) -> str:
    return ticker.replace("^", "_").replace("=", "-").replace("/", "-")


def historie_pfad(ticker: str) -> Path:
    return g.pfad("data", "historie", f"{_dateiname(ticker)}.csv")


def _meta_pfad(ticker: str) -> Path:
    return g.pfad("data", "historie", f"{_dateiname(ticker)}.json")


def _kerze_aus_zeile(zeile: dict) -> Kerze:
    return Kerze(datum=date.fromisoformat(zeile["datum"]), open=D(zeile["open"]), high=D(zeile["high"]),
                 low=D(zeile["low"]), close=D(zeile["close"]), dividende=D(zeile["dividende"] or "0"),
                 split=D(zeile["split"] or "0"))


def gespeicherte_historie(ticker: str) -> dict[date, Kerze]:
    return {k.datum: k for k in map(_kerze_aus_zeile, g.csv_lesen(historie_pfad(ticker)))}


def historie(ticker: str, von: date, bis: date) -> list[Kerze]:
    """Tagesdaten für abgeschlossene Tage (vor heute), mit Zwischenspeicher.

    Bereits gespeicherte Tage werden nie überschrieben, damit spätere
    Korrekturen der Quelle bestehende Buchungen nicht verändern.
    """
    boerse_von(ticker)  # prüft Zulässigkeit
    heute = g.heute()
    bis_eff = min(bis, heute - timedelta(days=1))
    if von > bis_eff:
        return []
    gespeichert = gespeicherte_historie(ticker)
    meta_datei = _meta_pfad(ticker)
    meta = g.json_lesen(meta_datei) if meta_datei.exists() else None
    abgedeckt_von = date.fromisoformat(meta["abgedeckt_von"]) if meta else None
    abgedeckt_bis = date.fromisoformat(meta["abgedeckt_bis"]) if meta else None

    abruf_von = None
    if meta is None or von < abgedeckt_von:
        abruf_von = von
    elif bis_eff > abgedeckt_bis:
        abruf_von = abgedeckt_bis + timedelta(days=1)
    if abruf_von is not None:
        try:
            neu = QUELLE.historie(ticker, abruf_von, heute)
        except KursFehler:
            raise
        except Exception as exc:
            raise KursFehler(f"Historische Kurse für {ticker} nicht abrufbar: {exc}") from exc
        neu = [k for k in neu if k.datum < heute]
        hinzu = {k.datum: k for k in neu if k.datum not in gespeichert}
        if hinzu:
            gespeichert.update(hinzu)
            g.csv_schreiben(historie_pfad(ticker), HISTORIE_FELDER, [
                {"datum": k.datum.isoformat(), "open": k.open, "high": k.high, "low": k.low,
                 "close": k.close, "dividende": k.dividende, "split": k.split}
                for k in sorted(gespeichert.values(), key=lambda k: k.datum)])
        letzte = max([k.datum for k in neu], default=None)
        neues_von = min(d for d in (abgedeckt_von, abruf_von) if d is not None)
        kandidaten = [d for d in (abgedeckt_bis, letzte) if d is not None]
        neues_bis = max(kandidaten) if kandidaten else abruf_von - timedelta(days=1)
        g.json_schreiben(meta_datei, {"ticker": ticker, "abgedeckt_von": neues_von.isoformat(),
                                      "abgedeckt_bis": neues_bis.isoformat(),
                                      "abgerufen": g.iso(g.jetzt()), "quelle": QUELLE.name})
    ergebnis = sorted((k for k in gespeichert.values() if von <= k.datum <= bis_eff), key=lambda k: k.datum)
    if not ergebnis and any(ist_handelstag(ticker, d) for d in g.tage(von, bis_eff)):
        raise KursFehler(f"Keine Kursdaten für {ticker} von {von} bis {bis_eff}. "
                         "Ticker prüfen oder später erneut versuchen.")
    return ergebnis


# --------------------------------------------------------------------------
# Kommandozeile


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Kursdaten abrufen und protokollieren.")
    unter = parser.add_subparsers(dest="befehl", required=True)
    p_aktuell = unter.add_parser("aktuell", help="Aktuelle Kurse abfragen und protokollieren")
    p_aktuell.add_argument("ticker", nargs="+", help="Ticker, z. B. SAP.DE AAPL ^GDAXI")
    p_hist = unter.add_parser("historie", help="Tagesdaten mit Dividenden und Splits")
    p_hist.add_argument("ticker", help="Ticker")
    p_hist.add_argument("--von", required=True, help="Startdatum JJJJ-MM-TT")
    p_hist.add_argument("--bis", required=True, help="Enddatum JJJJ-MM-TT")
    args = parser.parse_args(argv)

    try:
        if args.befehl == "aktuell":
            kurse = aktuell(args.ticker)
            fx = None
            if any(k.waehrung == "USD" for k in kurse):
                fx = next((k for k in kurse if k.ticker == g.projekt()["devisen_ticker"]), None) \
                    or devisenkurs_aktuell()
            print(f"{'Ticker':<12} {'Kurs':>14} {'Whg':<4} {'EUR':>14} {'Markt':<8} Kurszeit")
            for k in kurse:
                eur = in_eur(k.kurs, k.waehrung, fx.kurs if fx else None)
                print(f"{k.ticker:<12} {g.text(k.kurs):>14} {k.waehrung:<4} {eur:>14.4f} "
                      f"{'offen' if k.markt_offen else 'zu':<8} {k.kurs_zeit.isoformat()}")
        else:
            kerzen = historie(args.ticker, g.datum_lesen(args.von), g.datum_lesen(args.bis))
            print(",".join(HISTORIE_FELDER))
            for k in kerzen:
                print(",".join(g.text(v) if not isinstance(v, date) else v.isoformat()
                               for v in (k.datum, k.open, k.high, k.low, k.close, k.dividende, k.split)))
    except Fehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
