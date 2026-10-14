"""Deklarative Strategien des Labors. Jede entscheidet nur aus `Sicht` (Daten bis zum Entscheidungspunkt)."""

from __future__ import annotations

from decimal import Decimal

import numpy as np

from .engine import Sicht, Strategie, Zielposition

STANDARD_BENCHMARK = "EUNL.DE"  # iShares Core MSCI World (config/projekt.json, benchmark_ticker)


class BuyAndHold(Strategie):
    """Einmal zum ersten möglichen Zeitpunkt kaufen und halten (Benchmark und passive Kontrolle)."""

    name = "buyhold"
    beschreibung = "Einmal kaufen und halten (Benchmark)."

    def __init__(self, ticker: str = STANDARD_BENCHMARK, gewicht: float = 1.0):
        self.ticker, self.gewicht = ticker, gewicht
        self.tickers = (ticker,)
        self._fertig = False

    def parameter(self) -> dict:
        return {"ticker": self.ticker, "gewicht": self.gewicht}

    def entscheiden(self, sicht: Sicht):
        if self._fertig:
            return None
        self._fertig = True
        return [Zielposition(self.ticker, self.gewicht)]


class Gemischt(Strategie):
    """Feste Gewichte mit Rebalancing (60/40: Aktien-ETF und Anleihen-ETF)."""

    name = "gemischt"
    beschreibung = "Feste Gewichte (Standard 60/40) mit regelmäßigem Rebalancing; Rest ist Cash."

    def __init__(self, gewichte: dict[str, float] | None = None, rebalancing: str = "quartal", toleranz: float = 0.0):
        self.gewichte = gewichte or {STANDARD_BENCHMARK: 0.6, "EUNH.DE": 0.4}
        self.rebalancing = rebalancing
        self.tickers = tuple(self.gewichte)
        self._erst = True

    def parameter(self) -> dict:
        return {"gewichte": self.gewichte, "rebalancing": self.rebalancing}

    def entscheiden(self, sicht: Sicht):
        faellig = self._erst or {"monat": sicht.neuer_monat, "quartal": sicht.neues_quartal,
                                 "woche": sicht.neue_woche}[self.rebalancing]()
        if not faellig:
            return None
        self._erst = False
        return [Zielposition(t, w) for t, w in self.gewichte.items()]


class Trendfolge(Strategie):
    """Investiert, solange der Schluss über dem gleitenden Durchschnitt liegt, sonst Cash (Standard 200 Tage)."""

    name = "trend"
    beschreibung = "Trendfolge: Schluss über dem gleitenden Durchschnitt (Standard 200 Tage) = investiert, sonst Cash."

    def __init__(self, ticker: str = STANDARD_BENCHMARK, tage: int = 200, pruefung: str = "monat"):
        self.ticker, self.tage, self.pruefung = ticker, int(tage), pruefung
        self.tickers = (ticker,)
        self.aufwaermen = self.tage
        self._zustand: bool | None = None

    def parameter(self) -> dict:
        return {"ticker": self.ticker, "tage": self.tage, "pruefung": self.pruefung}

    def entscheiden(self, sicht: Sicht):
        if self.pruefung == "monat" and not sicht.neuer_monat():
            return None
        schluesse = sicht.schluesse(self.ticker)
        if len(schluesse) < self.tage:
            return None
        investiert = bool(schluesse[-1] > schluesse[-self.tage:].mean())
        if investiert == self._zustand:
            return None
        self._zustand = investiert
        return [Zielposition(self.ticker, 1.0)] if investiert else []


class Momentum(Strategie):
    """12-1-Momentum: die besten N nach Rendite der letzten 12 Monate ohne den letzten, monatlich gleich gewichtet."""

    name = "momentum"
    beschreibung = "12-1-Momentum: Top N nach Rendite über 252 Tage ohne die letzten 21, monatlich, gleich gewichtet."

    def __init__(self, universum: tuple[str, ...] | list[str], top_n: int = 3, rueckblick: int = 252,
                 ueberspringen: int = 21, nur_positive: bool = True):
        self.universum = tuple(universum)
        self.top_n, self.rueckblick, self.ueberspringen = int(top_n), int(rueckblick), int(ueberspringen)
        self.nur_positive = nur_positive
        self.tickers = self.universum
        self.aufwaermen = self.rueckblick + 1

    def parameter(self) -> dict:
        return {"universum": list(self.universum), "top_n": self.top_n, "rueckblick": self.rueckblick,
                "ueberspringen": self.ueberspringen, "nur_positive": self.nur_positive}

    def entscheiden(self, sicht: Sicht):
        if not sicht.neuer_monat():
            return None
        wertung = {}
        for t in self.universum:
            s = sicht.schluesse(t)
            if len(s) <= self.rueckblick:
                return None
            wertung[t] = s[-1 - self.ueberspringen] / s[-1 - self.rueckblick] - 1
        beste = sorted(wertung, key=lambda t: (-wertung[t], t))[: self.top_n]
        if self.nur_positive:
            beste = [t for t in beste if wertung[t] > 0]
        return [Zielposition(t, 1.0 / self.top_n) for t in beste]


class Volatilitaetsziel(Strategie):
    """Gewicht = Zielschwankung / realisierte Schwankung (begrenzt), wöchentlich angepasst."""

    name = "volziel"
    beschreibung = "Volatilitätsziel: Gewicht = Ziel (Standard 10 % p. a.) / realisierte Schwankung, höchstens 100 %."

    def __init__(self, ticker: str = STANDARD_BENCHMARK, ziel: float = 0.10, fenster: int = 20, max_gewicht: float = 1.0,
                 schritt: float = 0.1):
        self.ticker, self.ziel, self.fenster = ticker, float(ziel), int(fenster)
        self.max_gewicht, self.schritt = float(max_gewicht), float(schritt)
        self.tickers = (ticker,)
        self.aufwaermen = self.fenster + 1
        self._gewicht: float | None = None

    def parameter(self) -> dict:
        return {"ticker": self.ticker, "ziel": self.ziel, "fenster": self.fenster, "max_gewicht": self.max_gewicht,
                "schritt": self.schritt}

    def entscheiden(self, sicht: Sicht):
        if not sicht.neue_woche():
            return None
        s = sicht.schluesse(self.ticker, self.fenster + 1)
        if len(s) < self.fenster + 1:
            return None
        vola = float(np.std(np.diff(s) / s[:-1], ddof=1) * np.sqrt(252))
        gewicht = self.max_gewicht if vola <= 0 else min(self.max_gewicht, self.ziel / vola)
        gewicht = round(gewicht / self.schritt) * self.schritt  # gröbere Stufen sparen Kosten
        if self._gewicht is not None and abs(gewicht - self._gewicht) < 1e-9:
            return None
        self._gewicht = gewicht
        return [Zielposition(self.ticker, gewicht)] if gewicht > 0 else []


class Overnight(Strategie):
    """Kauf zum Schluss, Verkauf zur nächsten Eröffnung (Daueranweisung des Portfolios Overnight)."""

    name = "overnight"
    beschreibung = "Overnight: Kauf zum Schluss, Verkauf zur nächsten Eröffnung; ETF oder Knock-out mit Hebel."
    punkte = ("open", "close")

    def __init__(self, ticker: str = STANDARD_BENCHMARK, typ: str = "etf", hebel: int | None = None,
                 gewicht: float = 0.97, nur_lange_naechte: bool = False):
        self.ticker, self.typ, self.hebel, self.gewicht = ticker, typ, hebel, float(gewicht)
        self.nur_lange_naechte = nur_lange_naechte
        self.tickers = (ticker,)

    def parameter(self) -> dict:
        return {"ticker": self.ticker, "typ": self.typ, "hebel": self.hebel, "gewicht": self.gewicht,
                "nur_lange_naechte": self.nur_lange_naechte}

    def entscheiden(self, sicht: Sicht):
        if sicht.art == "close":
            return []  # bis zur nächsten Eröffnung gehalten, dann verkauft
        if self.nur_lange_naechte and sicht.tag.weekday() not in (4,):
            return None
        hebel = Decimal(str(self.hebel)) if self.hebel else None
        return [Zielposition(self.ticker, self.gewicht, typ=self.typ, hebel=hebel)]


REGISTER = {"buyhold": BuyAndHold, "gemischt": Gemischt, "trend": Trendfolge, "momentum": Momentum,
            "volziel": Volatilitaetsziel, "overnight": Overnight}
