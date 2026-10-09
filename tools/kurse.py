#!/usr/bin/env python3
"""Kursdaten: aktuelle Kurse mit Protokoll, Tageshistorie mit Zwischenspeicher.

Alle Kurse für Buchungen kommen aus diesem Werkzeug. Aktuelle Abfragen werden
in data/kurse/JJJJ-MM-TT.csv protokolliert, Tagesdaten (OHLC, Dividenden,
Splits) in data/historie/ zwischengespeichert. Der Marktstatus ergibt sich
aus config/universum.json.

Kursquellen (config/kursquellen.json): Ist ein Anbieter konfiguriert
(Umgebung STOCKMASTER_KURSANBIETER und STOCKMASTER_KURSANBIETER_KEY, gesetzt
vom Hintergrunddienst aus der App-Konfiguration), wird er zuerst gefragt, dann
yfinance. `markt` erzeugt die Marktübersicht für die Web-UI; fällt jede Quelle
aus, zeigt sie den letzten bekannten Kurs mit Kennzeichnung "veraltet". Solche
Kurse werden nie protokolliert und nie gebucht.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
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


class NichtUnterstuetzt(Exception):
    """Der Anbieter führt diesen Ticker nicht (oder nicht als dasselbe Instrument): nächste Quelle fragen."""


def _http_json(url: str, kopfzeilen: dict, timeout: float = 10.0):
    anfrage = urllib.request.Request(url, headers={"User-Agent": "StockMaster3000/1.0", "Accept": "application/json",
                                                   **kopfzeilen})
    try:
        with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:  # noqa: S310 - feste https-URL aus config
            return json.loads(antwort.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise KursFehler(f"HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise KursFehler(f"nicht erreichbar ({getattr(exc, 'reason', exc)})") from None
    except ValueError:
        raise KursFehler("ungültige Antwort (kein JSON)") from None


class Kontingent:
    """Zählt Anfragen je Anbieter (Minute und Tag) prozessübergreifend im Zwischenspeicher."""

    def __init__(self, name: str, je_minute: int | None, je_tag: int | None):
        self.name, self.je_minute, self.je_tag = name, je_minute, je_tag

    def _datei(self) -> Path:
        from pfade import cache_pfad
        return cache_pfad(f"kontingent_{self.name}.json")

    def reservieren(self, anzahl: int = 1) -> bool:
        """Bucht `anzahl` Anfragen, wenn das Kontingent reicht; sonst False (dann übernimmt die nächste Quelle)."""
        jetzt_s = time.time()
        with g.schreibsperre():
            datei = self._datei()
            try:
                stand = g.json_lesen(datei) if datei.exists() else {}
            except (OSError, ValueError):
                stand = {}
            zeiten = [t for t in stand.get("zeiten", []) if jetzt_s - t < 86400]
            minute = sum(1 for t in zeiten if jetzt_s - t < 60)
            if self.je_minute and minute + anzahl > self.je_minute:
                return False
            if self.je_tag and len(zeiten) + anzahl > self.je_tag:
                return False
            zeiten += [jetzt_s] * anzahl
            g.json_schreiben(datei, {"anbieter": self.name, "zeiten": zeiten})
        return True


class AnbieterQuelle:
    """Kurs-API eines Anbieters (Finnhub, Twelve Data). Der Key steht nie in URLs oder Meldungen."""

    def __init__(self, kennung: str, key: str, konfig: dict, http=_http_json):
        self.kennung, self._key, self.konfig, self._http = kennung, key, konfig, http
        self.name = kennung
        self.kontingent = Kontingent(kennung, konfig.get("max_pro_minute"), konfig.get("max_pro_tag"))
        self._puffer: dict[str, tuple[Decimal, datetime, float]] = {}
        self._puffer_sekunden = 60

    def symbol(self, ticker: str) -> str | None:
        """Symbol beim Anbieter oder None, wenn es dort kein identisches Instrument gibt."""
        if ticker in self.konfig.get("symbole", {}):
            return self.konfig["symbole"][ticker]
        if any(zeichen in ticker for zeichen in "^=/"):
            return None
        if "." in ticker:
            basis, suffix = ticker.rsplit(".", 1)
            ziel = self.konfig.get("suffix", {}).get("." + suffix)
            return basis + ziel if ziel else None
        return ticker

    def _kopf(self) -> dict:
        if self.kennung == "finnhub":
            return {"X-Finnhub-Token": self._key}
        return {"Authorization": f"apikey {self._key}"}

    def _anfragen(self, symbole: list[str]) -> dict:
        if not self.kontingent.reservieren(len(symbole)):
            raise KursFehler(f"Kontingent von {self.konfig['name']} ausgeschöpft")
        from urllib.parse import quote
        url = f"{self.konfig['url']}?symbol={quote(','.join(symbole), safe=',:/')}"
        daten = self._http(url, self._kopf())
        if self.kennung == "finnhub":
            return {symbole[0]: daten}
        if isinstance(daten, dict) and daten.get("status") == "error":
            raise KursFehler(f"{self.konfig['name']}: {str(daten.get('message', 'Fehler'))[:160]}")
        return daten if len(symbole) > 1 else {symbole[0]: daten}

    def _auswerten(self, symbol: str, daten) -> tuple[Decimal, datetime]:
        if not isinstance(daten, dict) or daten.get("status") == "error":
            meldung = daten.get("message", "kein Kurs") if isinstance(daten, dict) else "kein Kurs"
            raise KursFehler(f"{self.konfig['name']} liefert für {symbol} keinen Kurs ({str(meldung)[:120]})")
        if self.kennung == "finnhub":
            wert, stempel = daten.get("c"), daten.get("t")
        else:
            wert = daten.get("close")
            stempel = daten.get("last_quote_at") or daten.get("timestamp")
        try:
            wert = D(str(wert)) if wert not in (None, "") else None
            stempel = int(stempel) if stempel else None
        except (ArithmeticError, ValueError, TypeError):
            wert = None
        if not wert or wert <= 0 or not stempel:
            raise KursFehler(f"{self.konfig['name']} liefert für {symbol} keinen gültigen Kurs")
        return _runden(wert), datetime.fromtimestamp(stempel, tz=g.TZ)

    def vorladen(self, tickers: list[str]) -> None:
        """Batch-Abfrage (Twelve Data) für alle zuordenbaren Ticker; Ergebnis kurz zwischengespeichert."""
        if not self.konfig.get("batch"):
            return
        symbole = sorted({s for s in (self.symbol(t) for t in tickers) if s} -
                         {s for s, (_, _, t) in self._puffer.items() if time.time() - t < self._puffer_sekunden})
        groesse = int(self.konfig.get("batch_groesse", 8))
        for i in range(0, len(symbole), groesse):
            teil = symbole[i:i + groesse]
            try:
                antwort = self._anfragen(teil)
            except KursFehler:
                return  # Einzelabfragen bzw. nächste Quelle übernehmen
            for symbol in teil:
                try:
                    wert, zeit = self._auswerten(symbol, antwort.get(symbol))
                except KursFehler:
                    continue
                self._puffer[symbol] = (wert, zeit, time.time())

    def aktuell(self, ticker: str) -> tuple[Decimal, datetime]:
        symbol = self.symbol(ticker)
        if symbol is None:
            raise NichtUnterstuetzt(ticker)
        gepuffert = self._puffer.get(symbol)
        if gepuffert and time.time() - gepuffert[2] < self._puffer_sekunden:
            return gepuffert[0], gepuffert[1]
        antwort = self._anfragen([symbol])
        wert, zeit = self._auswerten(symbol, antwort.get(symbol))
        self._puffer[symbol] = (wert, zeit, time.time())
        return wert, zeit

    def historie(self, ticker, von, bis):
        raise NichtUnterstuetzt(ticker)

    def marktkapitalisierung(self, ticker):
        return None


class KursKette:
    """Fallback-Kette: konfigurierter Anbieter, dann die bestehende Quelle (yfinance).

    Historie und Marktkapitalisierung kommen weiter aus der bestehenden Quelle, damit
    gespeicherte Tagesdaten einheitlich bleiben (Split-Rückrechnung in YFinanceQuelle).
    """

    name = "kette"

    def __init__(self, quellen: list):
        self.quellen = quellen
        self.basis = quellen[-1]

    def vorladen(self, tickers: list[str]) -> None:
        for quelle in self.quellen:
            if hasattr(quelle, "vorladen"):
                quelle.vorladen(tickers)

    def aktuell(self, ticker: str):
        return _ueber_quellen(ticker, self.quellen, None)[:2]

    def historie(self, ticker, von, bis):
        return self.basis.historie(ticker, von, bis)

    def marktkapitalisierung(self, ticker):
        return self.basis.marktkapitalisierung(ticker)


def anbieter_konfig() -> dict:
    return g.config("kursquellen")


def quelle_aus_umgebung():
    """Quelle laut Umgebung (vom Hintergrunddienst aus der App-Konfiguration gesetzt)."""
    kennung = os.environ.get("STOCKMASTER_KURSANBIETER", "").strip().lower()
    key = os.environ.get("STOCKMASTER_KURSANBIETER_KEY", "").strip()
    if not kennung or kennung == "keiner" or not key:
        return YFinanceQuelle()
    try:
        konfig = anbieter_konfig()["anbieter"][kennung]
    except (KeyError, OSError, ValueError):
        return YFinanceQuelle()
    return KursKette([AnbieterQuelle(kennung, key, konfig), YFinanceQuelle()])


QUELLE = quelle_aus_umgebung()


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
    """Handelsschluss; an Tagen mit verkürztem Handel (fruehschluss) früher."""
    _, boerse = boerse_von(ticker)
    uhr = boerse.get("fruehschluss", {}).get(datum.isoformat(), boerse["schluss"])
    return _boersenzeit(boerse, datum, uhr)


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


def boersentag(ticker: str, zeitpunkt: datetime | None = None) -> date:
    """Kalendertag an der Börse des Tickers (Ortszeit der Börse) zum Zeitpunkt."""
    zone = ZoneInfo(boerse_von(ticker)[1]["zeitzone"])
    return (zeitpunkt or g.jetzt()).astimezone(zone).date()


def naechster_handelstag(ticker: str, datum: date) -> date:
    """Der nächste Handelstag nach `datum` (Wochenende und Feiertage der Börse übersprungen)."""
    tag = datum + timedelta(days=1)
    for _ in range(14):
        if ist_handelstag(ticker, tag):
            return tag
        tag += timedelta(days=1)
    return tag


def im_handelsfenster(ticker: str, zeitpunkt: datetime, nachlauf_minuten: int = 0) -> bool:
    """Liegt der Zeitpunkt zwischen Eröffnung und Schluss (plus Nachlauf) eines Handelstags der Börse?"""
    zeitpunkt = zeitpunkt.astimezone(g.TZ)
    tag = boersentag(ticker, zeitpunkt)
    if not ist_handelstag(ticker, tag):
        return False
    return oeffnung(ticker, tag) <= zeitpunkt < schluss(ticker, tag) + timedelta(minutes=nachlauf_minuten)


def boersen_fenster(name: str, datum: date) -> tuple[datetime, datetime] | None:
    """Handelsfenster (Eröffnung, Schluss; deutsche Zeit) der Börse `name` am Börsentag `datum`, sonst None.

    Berücksichtigt Zeitzone samt Sommerzeitumstellung, Feiertage und verkürzte Handelstage der Börse.
    """
    boerse = universum()["boersen"][name]
    if datum.weekday() not in boerse["handelstage"] or datum.isoformat() in boerse["feiertage"]:
        return None
    uhr = boerse.get("fruehschluss", {}).get(datum.isoformat(), boerse["schluss"])
    return (_boersenzeit(boerse, datum, boerse["oeffnung"]), _boersenzeit(boerse, datum, uhr))


def handelsboersen() -> list[str]:
    """Börsen mit echten Handelszeiten (ohne Devisen, die praktisch durchgehend gehandelt werden)."""
    return [name for name in universum()["boersen"] if name != "devisen"]


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


def _ueber_quellen(ticker: str, quellen: list, abfrage: datetime | None) -> tuple[Decimal, datetime, str]:
    """Fragt die Quellen der Reihe nach; ein unbrauchbarer Kurs führt zur nächsten Quelle.

    Unbrauchbar: Fehler, kein positiver Wert oder (bei offenem Markt) älter als das
    maximale Kursalter. Scheitern alle, gilt die ungünstigere Annahme: kein Kurs.
    """
    gruende = []
    for quelle in quellen:
        try:
            wert, kurs_zeit = quelle.aktuell(ticker)[:2]
        except NichtUnterstuetzt:
            continue
        except KursFehler as exc:
            gruende.append((quelle.name, str(exc)))
            continue
        except Exception as exc:
            gruende.append((quelle.name, f"Kursabfrage für {ticker} fehlgeschlagen: {exc}"))
            continue
        if wert is None or D(wert) <= 0:
            gruende.append((quelle.name, f"Für {ticker} kam kein gültiger Kurs (Wert: {wert})."))
            continue
        if abfrage is not None:
            kurs_zeit = kurs_zeit.astimezone(g.TZ) if kurs_zeit else abfrage
            max_alter = timedelta(minutes=g.projekt()["max_kursalter_minuten"])
            if markt_offen(ticker, abfrage) and abfrage - kurs_zeit > max_alter:
                gruende.append((quelle.name, (
                    f"Kurs für {ticker} ist veraltet ({kurs_zeit.isoformat()}, älter als "
                    f"{max_alter.seconds // 60} Minuten) obwohl der Markt offen ist. "
                    "Kein Handel ohne verlässlichen Kurs.")))
                continue
        return D(wert), kurs_zeit, quelle.name
    if len(gruende) == 1:
        raise KursFehler(gruende[0][1])
    if not gruende:
        raise KursFehler(f"Keine Kursquelle führt {ticker}.")
    raise KursFehler(f"Kein verlässlicher Kurs für {ticker}: " + " | ".join(f"{n}: {t}" for n, t in gruende))


def aktuell(tickers: list[str]) -> list[Kurs]:
    """Fragt aktuelle Kurse ab und protokolliert jeden einzelnen (mit der tatsächlich genutzten Quelle)."""
    ergebnisse = []
    quellen = getattr(QUELLE, "quellen", [QUELLE])
    if hasattr(QUELLE, "vorladen"):
        QUELLE.vorladen(list(tickers))
    for ticker in tickers:
        _, boerse = boerse_von(ticker)
        abfrage = g.jetzt()
        wert, kurs_zeit, quelle_name = _ueber_quellen(ticker, quellen, abfrage)
        offen = markt_offen(ticker, abfrage)
        kurs_zeit = kurs_zeit.astimezone(g.TZ) if kurs_zeit else abfrage
        kurs = Kurs(ticker=ticker, kurs=_runden(wert), waehrung=boerse["waehrung"], zeit=abfrage,
                    quelle=quelle_name, markt_offen=offen, kurs_zeit=kurs_zeit)
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
        neu = [Kerze(k.datum, _runden(k.open), _runden(k.high), _runden(k.low), _runden(k.close),
                     _runden(k.dividende), _runden(k.split)) for k in neu if k.datum < heute]
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
# Marktübersicht für die Web-UI (Hintergrunddienst); bucht nichts


def markt_tickers() -> list[str]:
    """Basiswerte, Benchmark, Devisen und alle Werte in den Portfolios."""
    uni = universum()
    tickers = list(uni["basiswerte"]) + list(uni.get("sonstige_ticker", {}))
    try:
        for profil in g.vorhandene_profile():
            for position in g.portfolio_laden(profil)["positionen"]:
                tickers.append(position["basiswert"])
            for order in g.portfolio_laden(profil)["offene_orders"]:
                if order.get("basiswert") or order.get("ticker"):
                    tickers.append(order.get("basiswert") or order.get("ticker"))
    except Fehler:
        pass
    return list(dict.fromkeys(t for t in tickers if t))


def letzter_bekannter(ticker: str, tage: int = 14) -> dict | None:
    """Letzter protokollierter Kurs (data/kurse/) bzw. letzter Schlusskurs (data/historie/)."""
    heute = g.heute()
    for abstand in range(tage + 1):
        zeilen = [z for z in g.csv_lesen(kurs_protokoll_pfad(heute - timedelta(days=abstand))) if z["ticker"] == ticker]
        if zeilen:
            zeile = zeilen[-1]
            return {"kurs": D(zeile["kurs"]), "zeit": zeile["zeit"], "quelle": zeile["quelle"]}
    kerzen = gespeicherte_historie(ticker)
    if kerzen:
        letzte = max(kerzen)
        return {"kurs": kerzen[letzte].close, "zeit": schluss(ticker, letzte).isoformat(), "quelle": "historie:close"}
    return None


def _vortagesschluss(ticker: str, tag: date) -> Decimal | None:
    kerzen = gespeicherte_historie(ticker)
    frueher = [d for d in kerzen if d < tag]
    return kerzen[max(frueher)].close if frueher else None


def markt_pfad() -> Path:
    from pfade import cache_pfad
    return cache_pfad("markt.json")


def markt(tickers: list[str] | None = None, historie_auffrischen: bool = False) -> dict:
    """Fragt alle Ticker ab (protokolliert über aktuell()) und speichert die Übersicht.

    Fällt jede Quelle aus, steht dort der letzte bekannte Kurs mit veraltet=True.
    Solche Werte sind nur Anzeige: nicht protokolliert, nie für Buchungen.
    """
    tickers = tickers or markt_tickers()
    namen = {**{t: v["name"] for t, v in universum()["basiswerte"].items()},
             **{t: v["name"] for t, v in universum().get("sonstige_ticker", {}).items()}}
    fehler_historie = {}
    if historie_auffrischen:
        for ticker in tickers:
            try:
                historie(ticker, g.heute() - timedelta(days=400), g.heute() - timedelta(days=1))
            except Fehler as exc:
                fehler_historie[ticker] = str(exc)[:200]
    if hasattr(QUELLE, "vorladen"):
        QUELLE.vorladen(list(tickers))
    eintraege = []
    for ticker in tickers:
        try:
            boerse_name, boerse = boerse_von(ticker)
        except Fehler:
            continue
        eintrag = {"ticker": ticker, "name": namen.get(ticker), "boerse": boerse_name, "waehrung": boerse["waehrung"],
                   "markt_offen": markt_offen(ticker)}
        try:
            kurs = aktuell([ticker])[0]
            eintrag.update({"kurs": kurs.kurs, "kurs_zeit": g.iso(kurs.kurs_zeit), "abfrage": g.iso(kurs.zeit),
                            "quelle": kurs.quelle, "veraltet": False, "grund": None,
                            "verzoegerung_minuten": max(0, int((kurs.zeit - kurs.kurs_zeit).total_seconds() // 60))})
            stichtag = kurs.kurs_zeit.astimezone(g.TZ).date()
        except Fehler as exc:
            letzter = letzter_bekannter(ticker)
            eintrag.update({"veraltet": True, "grund": str(exc)[:300], "kurs": letzter["kurs"] if letzter else None,
                            "kurs_zeit": letzter["zeit"] if letzter else None,
                            "quelle": f"letzter bekannter Kurs ({letzter['quelle']})" if letzter else None,
                            "abfrage": g.iso(g.jetzt()), "verzoegerung_minuten": None})
            stichtag = g.zeit_lesen(letzter["zeit"]).date() if letzter else g.heute()
        vortag = _vortagesschluss(ticker, stichtag)
        eintrag["vortag"] = vortag
        eintrag["veraenderung"] = (eintrag["kurs"] / vortag - 1) if eintrag.get("kurs") and vortag else None
        if ticker in fehler_historie:
            eintrag["fehler_historie"] = fehler_historie[ticker]
        eintraege.append(eintrag)
    stand = {"zeit": g.iso(g.jetzt()), "quelle_konfiguriert": getattr(QUELLE, "quellen", [QUELLE])[0].name,
             "erfolgreich": sum(1 for e in eintraege if not e["veraltet"]), "anzahl": len(eintraege),
             "eintraege": eintraege}
    g.json_schreiben(markt_pfad(), stand)
    return stand


def verbindung_testen(kennung: str) -> dict:
    """Ein Testkurs von genau dieser Quelle (Key aus STOCKMASTER_KURSANBIETER_KEY); nicht protokolliert."""
    if kennung == "yfinance":
        quelle, ticker = YFinanceQuelle(), g.projekt()["benchmark_ticker"]
    else:
        konfig = anbieter_konfig()["anbieter"].get(kennung)
        if konfig is None:
            raise Fehler(f"Unbekannter Kursanbieter '{kennung}'.")
        key = os.environ.get("STOCKMASTER_KURSANBIETER_KEY", "").strip()
        if not key:
            raise Fehler("Kein API-Key übergeben.")
        quelle, ticker = AnbieterQuelle(kennung, key, konfig), konfig.get("test_ticker", "AAPL")
    beginn = time.monotonic()
    try:
        wert, zeit = quelle.aktuell(ticker)[:2]
    except NichtUnterstuetzt:
        return {"ok": False, "meldung": f"{ticker} wird von {kennung} nicht geführt."}
    except Exception as exc:  # noqa: BLE001 - Klartext für die Einrichtungsseite
        return {"ok": False, "meldung": f"{kennung}: {exc}"[:300]}
    alter = int((g.jetzt() - zeit.astimezone(g.TZ)).total_seconds() // 60)
    return {"ok": True, "ticker": ticker, "kurs": g.text(_runden(wert)), "kurs_zeit": g.iso(zeit),
            "alter_minuten": alter, "dauer_ms": int((time.monotonic() - beginn) * 1000),
            "meldung": f"{ticker}: {g.text(_runden(wert))} (Kurszeit {zeit.astimezone(g.TZ):%d.%m. %H:%M}, "
                       f"vor {alter} Min.)"}


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
    p_markt = unter.add_parser("markt", help="Marktübersicht für die Web-UI (alle Werte des Universums)")
    p_markt.add_argument("--historie", action="store_true", help="zusätzlich Tagesdaten (400 Tage) ergänzen")
    p_markt.add_argument("ticker", nargs="*", help="nur diese Ticker (Standard: Universum und Portfolios)")
    p_test = unter.add_parser("test", help="Verbindung zu einer Kursquelle prüfen (ohne Protokoll, bucht nichts)")
    p_test.add_argument("--anbieter", required=True, help="finnhub, twelvedata oder yfinance")
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
        elif args.befehl == "test":
            print(json.dumps(verbindung_testen(args.anbieter), ensure_ascii=False))
        elif args.befehl == "markt":
            stand = markt(args.ticker or None, historie_auffrischen=args.historie)
            print(f"Marktübersicht: {stand['erfolgreich']} von {stand['anzahl']} Kursen aktuell "
                  f"(Quelle zuerst: {stand['quelle_konfiguriert']}).")
            for e in stand["eintraege"]:
                kennz = "VERALTET" if e["veraltet"] else e["quelle"]
                print(f"{e['ticker']:<12} {g.text(e['kurs']) if e['kurs'] is not None else '–':>14} "
                      f"{e['waehrung']:<4} {kennz}")
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
