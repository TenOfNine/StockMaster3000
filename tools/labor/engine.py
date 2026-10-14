"""Replay-Engine des Strategie-Labors: Kosten des Spiels, feste Ausführungsregeln, keine Zukunftsdaten.

Zeitmodell: Jeder Handelstag hat zwei Preispunkte, Eröffnung (2*i) und Schluss (2*i+1). Eine Strategie entscheidet an
einem Preispunkt p und sieht nur Daten bis einschließlich p (`Sicht`). Die Order wird frühestens am nächsten
Preispunkt p+1 zu dessen Kurs ausgeführt (Tagesstrategien: Entscheidung zum Schluss, Ausführung zur nächsten
Eröffnung). Der Kurs von p+1 ist zum Zeitpunkt der Entscheidung unbekannt; `lookahead_pruefung` belegt das durch
Veränderung aller späteren Kurse.

Kosten: buchen.kauf_rechnung und verkauf_rechnung (Spread je Seite halb, 1 EUR Gebühr je Order), Mindestorder,
Cash-Zins je Kalendertag, Knock-outs über produkte.py (Aufzinsung, Barriere gegen Eröffnung und Tagesextreme). Faktor-
Zertifikate sind im Labor nicht vorgesehen. Dividenden (Rohkurse) werden gutgeschrieben, wenn die Position vor der
Eröffnung des Ex-Tags bestand.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

import numpy as np

import buchen
import gemeinsam as g
import kurse
import produkte
from gemeinsam import D, Fehler
from kurse import Kerze

from .daten import FX_TICKER, Panel

NULL = Decimal("0")
EINS = Decimal("1")


@dataclass(frozen=True)
class Zielposition:
    """Gewünschte Position: Anteil `gewicht` am Portfoliowert (bei Knock-outs der Einsatz, nicht das Exposure)."""

    ticker: str
    gewicht: float
    typ: str = "etf"
    richtung: str = "long"
    hebel: Decimal | None = None

    def schluessel(self) -> tuple:
        return (self.ticker, self.typ, self.richtung, None if self.hebel is None else str(self.hebel))


class Sicht:
    """Alles, was eine Strategie am Preispunkt `p` wissen darf: Daten bis einschließlich p, nichts danach."""

    def __init__(self, panel: Panel, p: int):
        self._panel = panel
        self.punkt = p
        self.art = "close" if p % 2 else "open"
        self._i = p // 2
        self.tag = panel.tage[self._i]
        self._fertig = self._i + 1 if self.art == "close" else self._i  # Tage mit bekanntem Schluss/Hoch/Tief

    def _reihe(self, ticker: str, feld: str, n: int | None, bis_heute_eroeffnung: bool = False) -> np.ndarray:
        ende = self._i + 1 if bis_heute_eroeffnung else self._fertig
        werte = []
        for k in self._panel.kerzen[ticker][:ende]:
            if k is not None:
                werte.append(float(getattr(k, feld)))
        reihe = np.array(werte, dtype=float)
        return reihe if n is None else reihe[-n:]

    def schluesse(self, ticker: str, n: int | None = None) -> np.ndarray:
        """Schlusskurse abgeschlossener Tage (zum Schluss einschließlich heute)."""
        return self._reihe(ticker, "close", n)

    def eroeffnungen(self, ticker: str, n: int | None = None) -> np.ndarray:
        """Eröffnungskurse bis einschließlich heute (die heutige ist am Eröffnungspunkt bekannt)."""
        return self._reihe(ticker, "open", n, bis_heute_eroeffnung=True)

    def hochs(self, ticker: str, n: int | None = None) -> np.ndarray:
        return self._reihe(ticker, "high", n)

    def tiefs(self, ticker: str, n: int | None = None) -> np.ndarray:
        return self._reihe(ticker, "low", n)

    def letzter_kurs(self, ticker: str) -> Decimal | None:
        return self._panel.preis(ticker, self.punkt)

    def neuer_monat(self) -> bool:
        """Erster Handelstag eines Monats (Kalender ist vorab bekannt, es braucht keinen künftigen Kurs)."""
        return self._i == 0 or self._panel.tage[self._i - 1].month != self.tag.month

    def neue_woche(self) -> bool:
        return self._i == 0 or self._panel.tage[self._i - 1].isocalendar()[:2] != self.tag.isocalendar()[:2]

    def neues_quartal(self) -> bool:
        return self.neuer_monat() and self.tag.month in (1, 4, 7, 10)


class Strategie:
    """Basisklasse. `entscheiden` gibt die Zielpositionen zurück, [] für nur Cash oder None für unverändert."""

    name = "strategie"
    beschreibung = ""
    tickers: tuple[str, ...] = ()
    punkte = ("close",)  # Entscheidungspunkte je Tag: "open", "close"
    aufwaermen = 0       # Handelstage Vorlauf, die die Strategie braucht

    def parameter(self) -> dict:
        return {}

    def entscheiden(self, sicht: Sicht) -> list[Zielposition] | None:  # pragma: no cover - Schnittstelle
        raise NotImplementedError


@dataclass
class Ergebnis:
    strategie: str
    parameter: dict
    tage: list[date] = field(default_factory=list)
    werte: list[Decimal] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)
    gebuehren: Decimal = NULL
    spreads: Decimal = NULL
    zinsen: Decimal = NULL
    dividenden: Decimal = NULL
    umsatz: Decimal = NULL
    kapital: Decimal = NULL

    def renditen(self) -> np.ndarray:
        w = np.array([float(x) for x in [self.kapital, *self.werte]])
        return w[1:] / w[:-1] - 1

    def kosten(self) -> Decimal:
        return self.gebuehren + self.spreads


class Lauf:
    """Eine Wiedergabe von `start` bis `ende` mit einem Kapital und einer Strategie."""

    def __init__(self, panel: Panel, strategie: Strategie, start: date, ende: date | None = None,
                 kapital: Decimal = Decimal("1000.00"), toleranz: float = 0.0):
        fehlend = [t for t in strategie.tickers if t not in panel.tickers]
        if fehlend:
            raise Fehler(f"Im Panel fehlen Ticker der Strategie: {', '.join(fehlend)}")
        if any(kurse.waehrung(t) != "EUR" for t in strategie.tickers) and FX_TICKER not in panel.tickers:
            raise Fehler(f"Für Werte in USD braucht das Panel {FX_TICKER}.")
        self.panel, self.strategie = panel, strategie
        self.start, self.ende = start, ende
        self.kapital = g.geld(kapital)
        self.toleranz = toleranz
        self.mindestorder = D(g.kosten()["mindestorder"])
        self.zinssatz = D(g.kosten()["cash_zins_pa"]) / D(g.kosten()["tage_je_jahr"])
        self.cash = self.kapital
        self.positionen: list[dict] = []
        self.ergebnis = Ergebnis(strategie.name, strategie.parameter(), kapital=self.kapital)
        self._zins_bis: date = date.min
        self._ziel: list[Zielposition] | None = None
        self._ziel_offen = False

    # ----------------------------------------------------------------- Preise

    def _fx(self, p: int) -> Decimal | None:
        return self.panel.preis(FX_TICKER, p) if FX_TICKER in self.panel.tickers else None

    def _mitte_eur(self, pos: dict, p: int) -> Decimal | None:
        kurs = self.panel.preis(pos["ticker"], p)
        if kurs is None:
            return None
        wert = produkte.wert_je_stueck(pos, kurs)
        return kurse.in_eur(wert, kurse.waehrung(pos["ticker"]), self._fx(p))

    def _wert(self, p: int) -> Decimal:
        summe = self.cash
        for pos in self.positionen:
            mitte = self._mitte_eur(pos, p)
            if mitte is not None:
                summe += D(pos["stueck"]) * mitte
        return summe

    # ----------------------------------------------------------------- Buchungen

    def _trade(self, p: int, aktion: str, pos: dict | None, stueck: Decimal, kurs: Decimal, betrag: Decimal,
               gebuehr: Decimal = NULL, spread: Decimal = NULL, grund: str = "order") -> None:
        self.ergebnis.trades.append({
            "punkt": p, "datum": self.panel.tag_von(p).isoformat(), "art": "schluss" if p % 2 else "eroeffnung",
            "aktion": aktion, "ticker": pos["ticker"] if pos else "", "typ": pos["typ"] if pos else "",
            "stueck": str(stueck), "kurs_eur": str(g.param(kurs)), "betrag_eur": str(betrag),
            "gebuehr_eur": str(gebuehr), "spread_eur": str(spread), "grund": grund})
        self.ergebnis.gebuehren += gebuehr
        self.ergebnis.spreads += spread
        self.ergebnis.umsatz += abs(betrag) if aktion in ("kauf", "verkauf") else NULL

    def _verkaufen(self, pos: dict, stueck: Decimal, p: int, grund: str = "order") -> None:
        mitte = self._mitte_eur(pos, p)
        if mitte is None or mitte <= 0:
            if mitte is not None:  # Wert null (ausgeknockt)
                self._ausbuchen(pos, p, "wertlos")
            return
        stueck = min(stueck, D(pos["stueck"]))
        r = buchen.verkauf_rechnung(pos["typ"], mitte, stueck)
        self.cash += r["erloes"] - r["gebuehr"]
        rest = D(pos["stueck"]) - stueck
        if rest <= 0:
            self.positionen.remove(pos)
        else:
            pos["stueck"] = rest
        self._trade(p, "verkauf", pos, stueck, r["kurs"], r["erloes"] - r["gebuehr"], r["gebuehr"], r["spread_eur"], grund)

    def _ausbuchen(self, pos: dict, p: int, grund: str) -> None:
        self.positionen.remove(pos)
        self._trade(p, "ausbuchung", pos, D(pos["stueck"]), NULL, NULL, grund=grund)

    def _kaufen(self, z: Zielposition, einsatz: Decimal, p: int, bestehend: dict | None) -> None:
        kurs = self.panel.preis(z.ticker, p)
        if kurs is None or kurs <= 0:
            return
        tag = self.panel.tag_von(p)
        wert, parameter = produkte.ausgabe(z.typ, z.richtung, kurs, hebel=z.hebel, kauftag=tag)
        gebuehr = g.gebuehr()
        einsatz = min(einsatz, self.cash - gebuehr - Decimal("0.01"))
        if einsatz < self.mindestorder:
            return
        mitte = kurse.in_eur(wert, kurse.waehrung(z.ticker), self._fx(p))
        if mitte <= 0:
            return
        try:
            r = buchen.kauf_rechnung(z.typ, mitte, einsatz)
        except Fehler:
            return
        self.cash -= r["kurswert"] + r["gebuehr"]
        if bestehend is not None and z.typ in g.AKTIEN:
            bestehend["stueck"] = D(bestehend["stueck"]) + r["stueck"]
            pos = bestehend
        else:
            pos = {"ticker": z.ticker, "basiswert": z.ticker, "typ": z.typ, "richtung": z.richtung, "stueck": r["stueck"],
                   "parameter": {k: v for k, v in parameter.items()}, "schluessel": z.schluessel(), "punkt": p}
            if z.typ == "ko":
                pos["parameter"]["stand"] = tag - timedelta(days=1)
            self.positionen.append(pos)
        self._trade(p, "kauf", pos, r["stueck"], r["kurs"], -(r["kurswert"] + r["gebuehr"]), r["gebuehr"], r["spread_eur"])

    def _umschichten(self, ziel: list[Zielposition], p: int) -> None:
        wert = self._wert(p)
        soll = {z.schluessel(): z for z in ziel}
        for pos in list(self.positionen):  # zuerst Verkäufe
            z = soll.get(pos["schluessel"])
            mitte = self._mitte_eur(pos, p)
            if mitte is None:
                continue
            if z is None:
                self._verkaufen(pos, D(pos["stueck"]), p)
                continue
            ist = D(pos["stueck"]) * mitte
            ueber = ist - D(str(z.gewicht)) * wert
            if ueber >= max(self.mindestorder, D(str(self.toleranz)) * wert):
                self._verkaufen(pos, g.stueck_runden(ueber / mitte), p)
        for z in sorted(ziel, key=lambda x: -x.gewicht):  # dann Käufe
            bestehend = next((q for q in self.positionen if q["schluessel"] == z.schluessel()), None)
            mitte = self._mitte_eur(bestehend, p) if bestehend else NULL
            ist = D(bestehend["stueck"]) * mitte if bestehend and mitte else NULL
            fehlt = D(str(z.gewicht)) * wert - ist
            if fehlt >= max(self.mindestorder, D(str(self.toleranz)) * wert):
                self._kaufen(z, fehlt, p, bestehend)

    # ----------------------------------------------------------------- Tagesablauf

    def _dividenden(self, i: int, p: int) -> None:
        for pos in self.positionen:
            if pos["typ"] not in g.AKTIEN or pos["punkt"] > 2 * i:
                continue
            k = self.panel.kerze(pos["ticker"], i)
            if k is not None and k.dividende > 0:
                betrag = g.geld(kurse.in_eur(D(pos["stueck"]) * k.dividende, kurse.waehrung(pos["ticker"]), self._fx(p)))
                self.cash += betrag
                self.ergebnis.dividenden += betrag
                self._trade(p, "dividende", pos, D(pos["stueck"]), k.dividende, betrag, grund="dividende")

    def _knockouts(self, i: int, p: int) -> None:
        for pos in list(self.positionen):
            if pos["typ"] != "ko":
                continue
            k = self.panel.kerze(pos["ticker"], i)
            if k is None:
                continue
            barriere = pos["parameter"]["barriere"]
            if p % 2 == 0:  # Eröffnung: Lücke über die Barriere
                if produkte.ko_ausgeknockt(pos["richtung"], barriere, k.open, k.open):
                    self._ausbuchen(pos, p, "knockout (Eröffnung)")
            elif pos["punkt"] <= 2 * i and produkte.ko_ausgeknockt(pos["richtung"], barriere, k.low, k.high):
                self._ausbuchen(pos, p, "knockout (Tagesverlauf)")

    def _aufzinsen(self, tag: date) -> None:
        for pos in self.positionen:
            if pos["typ"] != "ko":
                continue
            tage = (tag - pos["parameter"]["stand"]).days
            if tage > 0:
                basis = produkte.ko_aufzinsen(pos["richtung"], pos["parameter"]["basispreis"], tage)
                pos["parameter"]["basispreis"] = pos["parameter"]["barriere"] = basis
                pos["parameter"]["stand"] = tag

    def _zins(self, tag: date) -> None:
        for _ in range((tag - self._zins_bis).days):
            zins = g.geld(self.cash * self.zinssatz) if self.cash > 0 else NULL
            self.cash += zins
            self.ergebnis.zinsen += zins
        self._zins_bis = tag

    def ausfuehren(self) -> Ergebnis:
        panel = self.panel
        erstes = next((i for i, t in enumerate(panel.tage) if t >= self.start), None)
        if erstes is None:
            raise Fehler("Der Zeitraum liegt nach den vorhandenen Daten.")
        letzter = len(panel.tage) - 1
        self._zins_bis = panel.tage[erstes] - timedelta(days=1)
        if self.ende is not None:
            letzter = max(i for i, t in enumerate(panel.tage) if t <= self.ende)
        for i in range(erstes, letzter + 1):
            tag = panel.tage[i]
            if any(panel.kerze(t, i) is None for t in self.strategie.tickers):
                continue  # Strategie ohne Daten: noch nicht startfähig
            for art in (0, 1):
                p = 2 * i + art
                if art == 0:
                    self._dividenden(i, p)
                self._knockouts(i, p)
                if self._ziel_offen:  # Order des vorigen Preispunkts: Ausführung zu diesem Kurs
                    self._umschichten(self._ziel or [], p)
                    self._ziel_offen = False
                if art == 1:
                    self._aufzinsen(tag)  # Tagesabschluss wie im Spiel: auch Positionen, die heute zum Schluss kamen
                    self._zins(tag)
                    self.ergebnis.tage.append(tag)
                    self.ergebnis.werte.append(g.geld(self._wert(p)))
                if i - erstes >= 0 and ("open" if art == 0 else "close") in self.strategie.punkte:
                    ziel = self.strategie.entscheiden(Sicht(panel, p))
                    if ziel is not None:
                        self._ziel, self._ziel_offen = ziel, True
        return self.ergebnis


def ausfuehren(panel: Panel, strategie: Strategie, start: date, ende: date | None = None,
               kapital: Decimal = Decimal("1000.00"), toleranz: float = 0.0) -> Ergebnis:
    return Lauf(panel, strategie, start, ende, kapital, toleranz).ausfuehren()


# --------------------------------------------------------------------------
# Look-ahead-Prüfung


def _zerstoeren(panel: Panel, p: int, seed: int) -> Panel:
    """Kopie des Panels, in der alle Kurse nach Preispunkt p zufällig verändert sind (bis p unverändert)."""
    zufall = random.Random(seed)
    i = p // 2
    ersetzt = {}
    for ticker, reihe in panel.kerzen.items():
        neu: list[Kerze | None] = []
        for j, k in enumerate(reihe):
            if k is None or j < i or (j == i and p % 2 == 1):
                neu.append(k)
                continue
            faktor = D(str(zufall.uniform(0.5, 1.5)))
            if j == i:  # p ist die Eröffnung: sie bleibt, Schluss, Hoch und Tief sind Zukunft
                c = g.param(k.open * faktor)
                neu.append(Kerze(k.datum, k.open, max(k.open, c), min(k.open, c), c, k.dividende, k.split))
            else:
                o = g.param(k.open * faktor)
                c = g.param(k.close * D(str(zufall.uniform(0.5, 1.5))))
                neu.append(Kerze(k.datum, o, max(o, c), min(o, c), c, k.dividende, k.split))
        ersetzt[ticker] = neu
    return panel.kopie_mit(ersetzt)


def lookahead_pruefung(fabrik, panel: Panel, punkte: list[int] | None = None, wiederholungen: int = 3,
                       seed: int = 1) -> list[str]:
    """Belegt, dass Entscheidungen nur von Daten bis zum Entscheidungspunkt abhängen.

    `fabrik(panel)` baut eine frische Strategie für ein Panel. Für jeden Prüfpunkt werden alle späteren Kurse zufällig
    verändert; die Entscheidung am Prüfpunkt (nach Wiedergabe aller früheren Punkte) muss gleich bleiben. Gibt eine
    Liste der Verstöße zurück (leer = bestanden).
    """
    if punkte is None:
        n = panel.punkte()
        punkte = list(range(n // 4, n - 2, max(1, n // 40)))
    verstoesse = []
    for p in punkte:
        original = _entscheidungen(fabrik, panel, p)
        for k in range(wiederholungen):
            if _entscheidungen(fabrik, _zerstoeren(panel, p, seed + 7919 * k + p), p) != original:
                verstoesse.append(f"Entscheidung bei Preispunkt {p} ({panel.tag_von(p)}) hängt von späteren Kursen ab")
                break
    return verstoesse


def _entscheidungen(fabrik, panel: Panel, bis: int) -> list:
    strategie = fabrik(panel)
    ergebnis = []
    for p in range(0, bis + 1):
        art = "open" if p % 2 == 0 else "close"
        if art in strategie.punkte:
            ziel = strategie.entscheiden(Sicht(panel, p))
            ergebnis.append(None if ziel is None else [(z.schluessel(), round(z.gewicht, 9)) for z in ziel])
    return ergebnis
