"""Tageskerzen für das Labor: eigener Zwischenspeicher, nie der Spielstand (data/historie bleibt unberührt)."""

from __future__ import annotations

import bisect
from datetime import date, timedelta
from decimal import Decimal

import gemeinsam as g
import kurse
from gemeinsam import D, Fehler
from kurse import Kerze

FELDER = ["datum", "open", "high", "low", "close", "dividende", "split"]
FX_TICKER = "EURUSD=X"


def cache_datei(ticker: str):
    return g.pfad("labor", "daten", f"{kurse._dateiname(ticker)}.csv")


def laden(ticker: str) -> list[Kerze]:
    return sorted((kurse._kerze_aus_zeile(z) for z in g.csv_lesen(cache_datei(ticker))), key=lambda k: k.datum)


def holen(ticker: str, von: date, bis: date) -> int:
    """Holt Tageskerzen über die Kursquelle (Netzwerk) und ergänzt den Zwischenspeicher; vorhandene Tage bleiben.

    Gibt die Zahl neuer Tage zurück. Nur abgeschlossene Tage (vor heute).
    """
    kurse.boerse_von(ticker)
    bis = min(bis, g.heute() - timedelta(days=1))
    vorhanden = {k.datum: k for k in laden(ticker)}
    try:
        geholt = kurse.QUELLE.historie(ticker, von, bis)
    except Fehler:
        raise
    except Exception as exc:  # Netzwerk- und Quellfehler verständlich melden
        raise Fehler(f"Historische Kurse für {ticker} nicht abrufbar: {exc}") from exc
    neu = [k for k in geholt if k.datum <= bis and k.datum not in vorhanden]
    if not vorhanden and not neu:
        raise Fehler(f"Keine Kursdaten für {ticker} von {von} bis {bis}.")
    vorhanden.update({k.datum: k for k in neu})
    g.csv_schreiben(cache_datei(ticker), FELDER, [
        {"datum": k.datum.isoformat(), "open": k.open, "high": k.high, "low": k.low, "close": k.close,
         "dividende": k.dividende, "split": k.split} for k in sorted(vorhanden.values(), key=lambda k: k.datum)])
    return len(neu)


class Panel:
    """Kurse mehrerer Ticker auf gemeinsamem Kalender. Jeder Tag hat zwei Preispunkte: 2*i = Eröffnung, 2*i+1 = Schluss.

    Fehlt ein Tag bei einem Ticker (andere Börse, Feiertag), gilt der letzte Schluss; vor dem ersten Tag eines Tickers
    gibt es keinen Preis (None). Dividenden und Splits bleiben am Originaltag.
    """

    def __init__(self, serien: dict[str, list[Kerze]]):
        if not serien:
            raise Fehler("Das Panel braucht mindestens einen Ticker.")
        self.tickers = list(serien)
        self.tage: list[date] = sorted({k.datum for reihe in serien.values() for k in reihe})
        index = {t: i for i, t in enumerate(self.tage)}
        self.kerzen: dict[str, list[Kerze | None]] = {}
        for ticker, reihe in serien.items():
            je_tag = {k.datum: k for k in reihe}
            fest: list[Kerze | None] = []
            letzte: Kerze | None = None
            for tag in self.tage:
                if tag in je_tag:
                    letzte = je_tag[tag]
                    fest.append(letzte)
                elif letzte is None:
                    fest.append(None)
                else:
                    c = letzte.close
                    fest.append(Kerze(tag, c, c, c, c))
            self.kerzen[ticker] = fest
        self._index = index

    @classmethod
    def aus_cache(cls, tickers: list[str], von: date | None = None, bis: date | None = None) -> "Panel":
        serien = {}
        for t in tickers:
            reihe = [k for k in laden(t) if (von is None or k.datum >= von) and (bis is None or k.datum <= bis)]
            if not reihe:
                raise Fehler(f"Keine Daten für {t} im Zwischenspeicher des Labors (python tools/backtest.py daten).")
            serien[t] = reihe
        return cls(serien)

    def punkte(self) -> int:
        return 2 * len(self.tage)

    def tag_von(self, p: int) -> date:
        return self.tage[p // 2]

    def punkt_von_tag(self, tag: date, schluss: bool = False) -> int:
        return 2 * bisect.bisect_left(self.tage, tag) + (1 if schluss else 0)

    def preis(self, ticker: str, p: int) -> Decimal | None:
        k = self.kerzen[ticker][p // 2]
        if k is None:
            return None
        return k.close if p % 2 else k.open

    def kerze(self, ticker: str, i: int) -> Kerze | None:
        return self.kerzen[ticker][i]

    def kopie_mit(self, ersetzt: dict[str, list[Kerze | None]]) -> "Panel":
        neu = object.__new__(Panel)
        neu.tickers, neu.tage, neu._index = self.tickers, self.tage, self._index
        neu.kerzen = {**self.kerzen, **ersetzt}
        return neu


def fx_noetig(tickers: list[str]) -> bool:
    return any(kurse.waehrung(t) != "EUR" for t in tickers)
