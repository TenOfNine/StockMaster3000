#!/usr/bin/env python3
"""Nachbuchung versäumter Tage und Bewertung (regeln.md Abschnitte 2, 6, 7, 8, 9).

`nachbuchen` verarbeitet je Portfolio alle Kalendertage seit
`verarbeitet_bis` bis gestern in der festen Reihenfolge aus regeln.md 6:
vorgemerkte Market-Orders, Limit-Orders, Barrieren/Stops/Kursziele,
Tagesabschluss (Aufzinsung, Faktor-Fortschreibung, Dividenden, Cash-Zins,
Tageswert, Drawdown-Stufe, Portfolio-Stopp).

`bericht` schreibt data/benchmark.csv und ranking.md.
"""

from __future__ import annotations

import argparse
import math
import statistics
import sys
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import buchen
import gemeinsam as g
import kurse
import limits
import produkte
from gemeinsam import D, Fehler

EINS = Decimal("1")
NULL = Decimal("0")


# --------------------------------------------------------------------------
# Tagesdaten


class Tagesdaten:
    """Lädt Tageskerzen je Ticker einmal pro Lauf (aus dem Zwischenspeicher)."""

    VORLAUF = 20

    def __init__(self, start: date, ende: date):
        self.von = start - timedelta(days=self.VORLAUF)
        self.bis = ende
        self.daten: dict[str, dict[date, kurse.Kerze]] = {}

    def kerzen(self, ticker: str) -> dict[date, kurse.Kerze]:
        if ticker not in self.daten:
            self.daten[ticker] = {k.datum: k for k in kurse.historie(ticker, self.von, self.bis)}
        return self.daten[ticker]

    def kerze(self, ticker: str, tag: date) -> kurse.Kerze | None:
        return self.kerzen(ticker).get(tag)

    def letzter_schluss(self, ticker: str, tag: date) -> Decimal | None:
        kandidaten = [d for d in self.kerzen(ticker) if d <= tag]
        if not kandidaten:
            gespeichert = kurse.gespeicherte_historie(ticker)
            kandidaten_alt = [d for d in gespeichert if d <= tag]
            return gespeichert[max(kandidaten_alt)].close if kandidaten_alt else None
        return self.kerzen(ticker)[max(kandidaten)].close

    def letzte_kerze(self, ticker: str, tag: date) -> kurse.Kerze | None:
        kandidaten = [d for d in self.kerzen(ticker) if d <= tag]
        return self.kerzen(ticker)[max(kandidaten)] if kandidaten else None

    def fx(self, tag: date, eroeffnung: bool) -> Decimal:
        ticker = g.projekt()["devisen_ticker"]
        kerze = self.kerze(ticker, tag)
        if kerze is not None:
            return kerze.open if eroeffnung else kerze.close
        vorher = self.letzter_schluss(ticker, tag - timedelta(days=1))
        if vorher is None:
            raise g.KursFehler(f"Kein EURUSD-Kurs bis {tag} verfügbar.")
        return vorher


def braucht_fx(ticker: str) -> bool:
    return kurse.waehrung(ticker) != "EUR"


def markt_am(portfolio: dict, tag: date, daten: Tagesdaten, eroeffnung: bool) -> limits.Markt:
    """Kurse aller Positionen zur Eröffnung (bzw. zum Schluss) des Tages."""
    werte = {}
    for ticker in {p["basiswert"] for p in portfolio["positionen"]}:
        kerze = daten.kerze(ticker, tag)
        if kerze is not None:
            werte[ticker] = kerze.open if eroeffnung else kerze.close
        else:
            vorher = daten.letzter_schluss(ticker, tag)
            if vorher is None:
                raise g.KursFehler(f"Kein Kurs für {ticker} bis {tag}; Bewertung nicht möglich.")
            werte[ticker] = vorher
    eurusd = None
    tickers = set(werte) | {o["basiswert"] for o in portfolio["offene_orders"]}
    if any(braucht_fx(t) for t in tickers):
        eurusd = daten.fx(tag, eroeffnung)
    return limits.Markt(kurse=werte, eurusd=eurusd, datum=tag)


def tagesende(tag: date) -> datetime:
    return datetime.combine(tag, time(23, 59, 59), tzinfo=g.TZ)


# --------------------------------------------------------------------------
# Bausteine eines Tages


def wirksame_grenzen(position: dict, tag: date) -> tuple[Decimal | None, Decimal | None]:
    """Stop/Kursziel, die zu Beginn der Tageskerze galten (Änderungen wirken ab dem Folgetag)."""
    historie = position.get("stop_historie") or [
        {"ab": position["eroeffnet"], "stop": position["stop"], "kursziel": position["kursziel"]}]
    beginn = kurse.kerzen_beginn(position["basiswert"], tag)
    gueltig = [e for e in historie if g.zeit_lesen(e["ab"]) < beginn]
    eintrag = gueltig[-1] if gueltig else historie[0]
    return D(eintrag["stop"]), D(eintrag["kursziel"])


def split_buchen(lauf: g.Buchungslauf, ticker: str, verhaeltnis: Decimal, tag: date) -> None:
    """Split vor allen Ereignissen des Tages anwenden (die Tageskerze ist bereits angepasst)."""
    portfolio = lauf.portfolio

    def teilen(wert):
        return g.text(g.param(D(wert) / verhaeltnis)) if wert not in (None, "") else wert

    for position in portfolio["positionen"]:
        if position["basiswert"] != ticker:
            continue
        parameter = position["parameter"]
        if position["typ"] in g.AKTIEN or position["typ"] == "ko":
            position["stueck"] = g.text(g.stueck_runden(D(position["stueck"]) * verhaeltnis))
            position["einstand"] = teilen(position["einstand"])
        if position["typ"] == "ko":
            for feld in ("basispreis", "barriere", "kurs_kauf", "wert_je_stueck"):
                if feld in parameter:
                    parameter[feld] = teilen(parameter[feld])
        if position["typ"] == "faktor":
            parameter["kurs_ref"] = teilen(parameter["kurs_ref"])
        position["stop"] = teilen(position["stop"])
        position["kursziel"] = teilen(position["kursziel"])
        for eintrag in position.get("stop_historie", []):
            eintrag["stop"] = teilen(eintrag["stop"])
            eintrag["kursziel"] = teilen(eintrag["kursziel"])
        lauf.trade(zeit=kurse.kerzen_beginn(ticker, tag), position_id=position["id"], aktion="split",
                   typ=position["typ"], richtung=position["richtung"], ticker=position["ticker"],
                   basiswert=ticker, stueck=position["stueck"], kurs_basiswert=verhaeltnis,
                   kursquelle="historie:split", kurs_zeit=tag, betrag_eur=Decimal("0.00"),
                   journal_id=position["journal_id"], grund="split", stop=position["stop"],
                   kursziel=position["kursziel"], bemerkung=f"Split-Verhältnis {verhaeltnis}")
        lauf.meldungen.append(f"{portfolio['profil']}: Split {verhaeltnis} bei {ticker} ({position['id']})")
    for order in portfolio["offene_orders"]:
        if order["basiswert"] == ticker:
            for feld in ("limit", "stop", "kursziel"):
                order[feld] = teilen(order.get(feld))


def order_verfallen(lauf: g.Buchungslauf, order: dict, zeit: datetime, grund: str) -> None:
    lauf.portfolio["offene_orders"].remove(order)
    lauf.trade(zeit=zeit, order_id=order["id"], position_id=order.get("position_id"), aktion="verfall",
               typ=order.get("typ"), richtung=order.get("richtung"), ticker=order.get("ticker"),
               basiswert=order.get("basiswert"), journal_id=order["journal_id"], grund="verfall", bemerkung=grund)
    lauf.meldungen.append(f"{lauf.portfolio['profil']}: Order {order['id']} verfallen: {grund}")


def kauforder_ausfuehren(lauf, order, kurs, tag, daten, zeit, kursquelle) -> None:
    portfolio = lauf.portfolio
    plan = limits.kaufplan(order["typ"], order["richtung"], order["basiswert"], D(order["einsatz"]), kurs,
                           hebel=order.get("hebel"), faktor=order.get("faktor"), stop=D(order.get("stop")),
                           kursziel=D(order.get("kursziel")), kauftag=tag)
    markt = markt_am(portfolio, tag, daten, eroeffnung=True)
    markt.kurse[order["basiswert"]] = D(kurs)
    if braucht_fx(order["basiswert"]):
        markt.eurusd = daten.fx(tag, eroeffnung=kursquelle == "historie:open")
    verstoesse, kennzahlen = limits.pruefe_kauf(portfolio, plan, markt)
    if verstoesse:
        order_verfallen(lauf, order, zeit, "Limits bei Ausführung verletzt: " + "; ".join(map(str, verstoesse)))
        return
    portfolio["offene_orders"].remove(order)
    buchen.kauf_ausfuehren(lauf, order, plan, markt, zeit, kursquelle, tag.isoformat(), kennzahlen)


def orders_verarbeiten(lauf: g.Buchungslauf, tag: date, daten: Tagesdaten) -> None:
    portfolio = lauf.portfolio
    orders = sorted(portfolio["offene_orders"], key=lambda o: o["erfasst"])
    # Schritt 1: vorgemerkte Market-Orders zum Eröffnungskurs
    for order in [o for o in orders if o["art"] == "market"]:
        kerze = daten.kerze(order["basiswert"], tag)
        beginn = kurse.kerzen_beginn(order["basiswert"], tag)
        if kerze is None or g.zeit_lesen(order["erfasst"]) >= beginn:
            continue
        if order["aktion"] == "kauf":
            kauforder_ausfuehren(lauf, order, kerze.open, tag, daten, beginn, "historie:open")
        else:
            position = next((p for p in portfolio["positionen"] if p["id"] == order["position_id"]), None)
            if position is None:
                order_verfallen(lauf, order, beginn, "Position besteht nicht mehr")
                continue
            portfolio["offene_orders"].remove(order)
            eurusd = daten.fx(tag, True) if braucht_fx(order["basiswert"]) else None
            buchen.verkauf_ausfuehren(lauf, position, D(order["anteil"]), kerze.open, eurusd, beginn, tag,
                                      "historie:open", tag.isoformat(), "order", order_id=order["id"],
                                      journal_id=order["journal_id"])
    # Schritt 2: Limit-Orders (Eröffnung jenseits des Limits -> Eröffnung, sonst bei Berührung zum Limit)
    for order in [o for o in orders if o["art"] == "limit" and o in portfolio["offene_orders"]]:
        kerze = daten.kerze(order["basiswert"], tag)
        beginn = kurse.kerzen_beginn(order["basiswert"], tag)
        if kerze is None or g.zeit_lesen(order["erfasst"]) >= beginn:
            continue
        limit = D(order["limit"])
        long = order["richtung"] == "long"
        if (long and kerze.open <= limit) or (not long and kerze.open >= limit):
            kauforder_ausfuehren(lauf, order, kerze.open, tag, daten, beginn, "historie:open")
        elif (long and kerze.low <= limit) or (not long and kerze.high >= limit):
            kauforder_ausfuehren(lauf, order, limit, tag, daten, kurse.schluss(order["basiswert"], tag),
                                 "historie:intraday")


def positionen_pruefen(lauf: g.Buchungslauf, tag: date, daten: Tagesdaten) -> None:
    """Schritt 3: Barriere, Stop, Kursziel (Eröffnung zuerst, sonst schlechtestes Ergebnis)."""
    for position in list(lauf.portfolio["positionen"]):
        ticker = position["basiswert"]
        kerze = daten.kerze(ticker, tag)
        if kerze is None:
            continue
        long = position["richtung"] == "long"
        beginn = kurse.kerzen_beginn(ticker, tag)
        kauftag = g.zeit_lesen(position["eroeffnet"]) >= beginn
        stop, ziel = wirksame_grenzen(position, tag)
        if kauftag:
            # Konservativ: am Kauftag zählt der Stop gegen das ganze Tageshoch/-tief (regeln.md 4),
            # das Kursziel dagegen nicht, weil das Hoch vor dem Kauf gelegen haben kann.
            ziel = None
        barriere = D(position["parameter"]["barriere"]) if position["typ"] == "ko" else None
        schluss_zeit = kurse.schluss(ticker, tag)
        fx_auf = daten.fx(tag, True) if braucht_fx(ticker) else None
        fx_tag = daten.fx(tag, False) if braucht_fx(ticker) else None

        def jenseits(grenze, kurs, unten):
            return grenze is not None and (kurs <= grenze if unten else kurs >= grenze)

        o = kerze.open
        if jenseits(barriere, o, long):
            buchen.wertlos_ausbuchen(lauf, position, o, beginn, "historie:open", tag.isoformat(),
                                     "Knock-out durch Eröffnungskurs", fx_auf)
        elif jenseits(stop, o, long):
            buchen.verkauf_ausfuehren(lauf, position, EINS, o, fx_auf, beginn, tag, "historie:open",
                                      tag.isoformat(), "stop")
        elif jenseits(ziel, o, not long):
            buchen.verkauf_ausfuehren(lauf, position, EINS, o, fx_auf, beginn, tag, "historie:open",
                                      tag.isoformat(), "kursziel")
        elif barriere is not None and produkte.ko_ausgeknockt(position["richtung"], barriere, kerze.low, kerze.high):
            buchen.wertlos_ausbuchen(lauf, position, barriere, schluss_zeit, "historie:intraday", tag.isoformat(),
                                     "Knock-out im Tagesverlauf", fx_tag)
        elif jenseits(stop, kerze.low if long else kerze.high, long):
            buchen.verkauf_ausfuehren(lauf, position, EINS, stop, fx_tag, schluss_zeit, tag, "historie:intraday",
                                      tag.isoformat(), "stop")
        elif jenseits(ziel, kerze.high if long else kerze.low, not long):
            buchen.verkauf_ausfuehren(lauf, position, EINS, ziel, fx_tag, schluss_zeit, tag, "historie:intraday",
                                      tag.isoformat(), "kursziel")


def tagesabschluss(lauf: g.Buchungslauf, tag: date, daten: Tagesdaten) -> None:
    """Schritt 4: Aufzinsen, Faktor fortschreiben, Dividenden, Cash-Zins."""
    portfolio = lauf.portfolio
    for position in list(portfolio["positionen"]):
        parameter = position["parameter"]
        ticker = position["basiswert"]
        kerze = daten.kerze(ticker, tag)
        if position["typ"] == "ko":
            # je Kalendertag, auch am Kauftag und am Wochenende
            k = produkte.ko_aufzinsen(position["richtung"], parameter["basispreis"], 1)
            parameter["basispreis"] = parameter["barriere"] = g.text(k)
            parameter["stand"] = tag.isoformat()
            schluss = kerze.close if kerze else daten.letzter_schluss(ticker, tag)
            if schluss is not None:
                parameter["wert_je_stueck"] = g.text(g.param(produkte.ko_wert(position["richtung"], schluss, k)))
        elif position["typ"] == "faktor" and kerze is not None:
            kostentage = (tag - date.fromisoformat(parameter["stand"])).days
            wert = produkte.faktor_fortschreiben(position["richtung"], parameter["faktor"],
                                                 parameter["wert_je_stueck"], parameter["kurs_ref"], kerze.close,
                                                 kostentage)
            parameter.update({"wert_je_stueck": g.text(wert), "kurs_ref": g.text(kerze.close),
                              "stand": tag.isoformat()})
            if wert <= 0:
                buchen.wertlos_ausbuchen(lauf, position, kerze.close, kurse.schluss(ticker, tag),
                                         "historie:close", tag.isoformat(), "Faktor-Wert null",
                                         daten.fx(tag, False) if braucht_fx(ticker) else None)
        elif position["typ"] in g.AKTIEN and kerze is not None and kerze.dividende > 0:
            # Anspruch nur, wenn die Position vor Beginn des Ex-Tags bestand.
            if g.zeit_lesen(position["eroeffnet"]) < kurse.kerzen_beginn(ticker, tag):
                fx = daten.fx(tag, False) if braucht_fx(ticker) else None
                betrag = g.geld(kurse.in_eur(D(position["stueck"]) * kerze.dividende, kurse.waehrung(ticker), fx))
                g.cash_buchen(portfolio, betrag)
                lauf.trade(zeit=tagesende(tag), position_id=position["id"], aktion="dividende",
                           typ=position["typ"], richtung="long", ticker=position["ticker"], basiswert=ticker,
                           stueck=position["stueck"], kurs_basiswert=kerze.dividende,
                           kursquelle="historie:dividende", kurs_zeit=tag, betrag_eur=betrag,
                           journal_id=position["journal_id"], grund="dividende", devisenkurs=fx)
                lauf.meldungen.append(f"{portfolio['profil']}: Dividende {betrag} EUR aus {ticker}")
    satz = D(g.kosten()["cash_zins_pa"]) / D(g.kosten()["tage_je_jahr"])
    zins = g.geld(g.cash(portfolio) * satz) if g.cash(portfolio) > 0 else Decimal("0.00")
    if zins != 0:
        g.cash_buchen(portfolio, zins)
        lauf.trade(zeit=tagesende(tag), aktion="zins", betrag_eur=zins, grund="zins",
                   bemerkung=f"Cash-Zins {tag.isoformat()}")


def drawdown_fortschreiben(portfolio: dict, nav: Decimal, tag: date, meldungen: list) -> Decimal:
    limits_profil = g.limits_fuer(portfolio["profil"])
    s1, s2 = limits_profil["drawdown_stufe1"], limits_profil["drawdown_stufe2"]
    hoch = max(D(portfolio["hoechststand"]), nav)
    portfolio["hoechststand"] = g.text(g.geld(hoch))
    drawdown = nav / hoch - EINS if hoch > 0 else NULL
    stufe = int(portfolio.get("drawdown_stufe", 0))
    neu = stufe
    if drawdown <= s2:
        neu = 2
        if stufe < 2:
            portfolio["stufe2_seit"] = tag.isoformat()
            portfolio["stufe2_review"] = None
    elif stufe == 2:
        if drawdown > s2 / 2 and portfolio.get("stufe2_review"):
            neu = 1 if drawdown <= s1 / 2 else 0
    elif drawdown <= s1:
        neu = 1
    elif stufe == 1 and drawdown > s1 / 2:
        neu = 0
    if neu != stufe:
        meldungen.append(f"{portfolio['profil']}: Drawdown-Stufe {stufe} -> {neu} am {tag} "
                         f"(Drawdown {drawdown * 100:.2f} %)" + (" – Pflicht-Review!" if neu == 2 else ""))
    portfolio["drawdown_stufe"] = neu
    return drawdown


def portfolio_stoppen(lauf: g.Buchungslauf, tag: date, daten: Tagesdaten) -> None:
    """Portfolio unter 200 EUR: alle Positionen zum Schlusskurs schließen, Orders verfallen."""
    portfolio = lauf.portfolio
    for position in list(portfolio["positionen"]):
        ticker = position["basiswert"]
        kerze = daten.letzte_kerze(ticker, tag)
        if kerze is None:
            raise g.KursFehler(f"Kein Schlusskurs für {ticker} bis {tag}; Portfolio-Stopp nicht buchbar.")
        fx = daten.fx(kerze.datum, False) if braucht_fx(ticker) else None
        buchen.verkauf_ausfuehren(lauf, position, EINS, kerze.close, fx, tagesende(tag), tag, "historie:close",
                                  kerze.datum.isoformat(), "portfoliostopp")
    for order in list(portfolio["offene_orders"]):
        order_verfallen(lauf, order, tagesende(tag), "Portfolio-Stopp")
    portfolio["status"] = "geschlossen"
    lauf.meldungen.append(f"{portfolio['profil']}: PORTFOLIO-STOPP am {tag} (unter "
                          f"{g.projekt()['portfolio_stopp']} EUR). Portfolio geschlossen; Neustart nur mit "
                          "Zustimmung beider Auftraggeber.")


def tageswert(lauf: g.Buchungslauf, tag: date, daten: Tagesdaten) -> dict:
    portfolio = lauf.portfolio
    bewertung = limits.portfolio_bewerten(portfolio, markt_am(portfolio, tag, daten, eroeffnung=False))
    nav = bewertung["nav"]
    drawdown = drawdown_fortschreiben(portfolio, nav, tag, lauf.meldungen)
    if nav < D(g.projekt()["portfolio_stopp"]) and portfolio["status"] == "aktiv":
        portfolio_stoppen(lauf, tag, daten)
        bewertung = limits.portfolio_bewerten(portfolio, markt_am(portfolio, tag, daten, eroeffnung=False))
        nav = bewertung["nav"]
    return {
        "datum": tag.isoformat(), "cash": g.geld(bewertung["cash"]),
        "positionswert": g.geld(bewertung["positionswert"]), "portfoliowert": g.geld(nav),
        "hoechststand": portfolio["hoechststand"], "drawdown": round(drawdown, 6),
        "drawdown_stufe": portfolio["drawdown_stufe"], "exposure": round(bewertung["exposure"], 4),
        "cashquote": round(bewertung["cashquote"], 4), "zertifikate_anteil": round(bewertung["zertifikate_anteil"], 4),
        "status": portfolio["status"],
    }


def abgleich_automatisch(profil: str, tag: date, daten: Tagesdaten, warnungen: list) -> None:
    """Abgleich: Liegt der Kurs einer automatischen Ausführung des Tages in der Tageskerze (kleine Toleranz)?

    Die Nachbuchung ändert nie eine vorhandene Buchung (Nur-Anhängen); Abweichungen werden gemeldet.
    """
    toleranz = Decimal("0.002")
    for zeile in g.trades_lesen(profil):
        if not g.AUTOMATISCH_MUSTER.match(zeile["bemerkung"] or "") or zeile["zeit"][:10] != tag.isoformat() \
                or not zeile["kurs_basiswert"]:
            continue
        kerze = daten.kerze(zeile["basiswert"], tag)
        kurs = D(zeile["kurs_basiswert"])
        if kerze is not None and not (kerze.low * (1 - toleranz) <= kurs <= kerze.high * (1 + toleranz)):
            warnungen.append(f"{profil} {zeile['trade_id']}: Kurs {kurs} der automatischen Ausführung liegt "
                             f"außerhalb der Tageskerze {zeile['basiswert']} {tag} (Tief {kerze.low}, Hoch "
                             f"{kerze.high}); Abgleich prüfen.")


def tag_verarbeiten(lauf: g.Buchungslauf, tag: date, daten: Tagesdaten, nav_zeilen: list, warnungen: list) -> None:
    portfolio = lauf.portfolio
    tickers = {p["basiswert"] for p in portfolio["positionen"]} | {o["basiswert"] for o in portfolio["offene_orders"]}
    for ticker in sorted(tickers):
        kerze = daten.kerze(ticker, tag)
        if kerze is None and kurse.ist_handelstag(ticker, tag):
            warnungen.append(f"{portfolio['profil']}: keine Kursdaten für {ticker} am {tag} (laut Kalender "
                             "Handelstag); Tag ohne Ereignisse für diesen Wert verarbeitet.")
        if kerze is not None and kerze.split > 0 and kerze.split != 1:
            split_buchen(lauf, ticker, kerze.split, tag)
    orders_verarbeiten(lauf, tag, daten)
    positionen_pruefen(lauf, tag, daten)
    abgleich_automatisch(portfolio["profil"], tag, daten, warnungen)
    tagesabschluss(lauf, tag, daten)
    if daten.kerze(g.projekt()["benchmark_ticker"], tag) is not None:
        nav_zeilen.append(tageswert(lauf, tag, daten))


def nav_pfad(profil: str):
    return g.pfad("data", "nav", f"{profil}.csv")


def nav_lesen(profil: str) -> list[dict]:
    return g.csv_lesen(nav_pfad(profil))


def nav_schreiben(profil: str, neue: list[dict]) -> None:
    if not neue:
        return
    zeilen = {z["datum"]: z for z in nav_lesen(profil)}
    for zeile in neue:
        zeilen[zeile["datum"]] = zeile
    g.csv_schreiben(nav_pfad(profil), g.NAV_FELDER, [zeilen[d] for d in sorted(zeilen)])


@g.mit_buchungssperre
def nachbuchen_profil(profil: str) -> list[str]:
    portfolio = g.portfolio_laden(profil)
    if portfolio["status"] != "aktiv":
        return [f"{profil}: Portfolio {portfolio['status']}, keine Nachbuchung."]
    start = date.fromisoformat(portfolio["verarbeitet_bis"]) + timedelta(days=1)
    ende = g.heute() - timedelta(days=1)
    if start > ende:
        return [f"{profil}: bereits bis {portfolio['verarbeitet_bis']} verarbeitet, nichts nachzubuchen."]
    daten = Tagesdaten(start, ende)
    daten.kerzen(g.projekt()["benchmark_ticker"])
    lauf = g.Buchungslauf(portfolio)
    nav_zeilen: list[dict] = []
    warnungen: list[str] = []
    for tag in g.tage(start, ende):
        tag_verarbeiten(lauf, tag, daten, nav_zeilen, warnungen)
        portfolio["verarbeitet_bis"] = tag.isoformat()
        if portfolio["status"] != "aktiv":
            portfolio["verarbeitet_bis"] = ende.isoformat()
            break
    lauf.speichern()
    nav_schreiben(profil, nav_zeilen)
    return lauf.meldungen + [f"WARNUNG {w}" for w in warnungen] + [
        f"{profil}: nachgebucht {start} bis {ende}, Cash {portfolio['cash']} EUR, "
        f"{len(portfolio['positionen'])} Positionen, {len(portfolio['offene_orders'])} offene Orders."]


def nachbuchen() -> list[str]:
    g.aktive_sperre()
    profile = g.vorhandene_profile()
    if not profile:
        return ["Keine Portfolios initialisiert – nichts nachzubuchen."]
    meldungen = []
    for profil in profile:
        meldungen += nachbuchen_profil(profil)
    return meldungen


def review_vermerken(profil: str, datei: str) -> list[str]:
    g.aktive_sperre()
    portfolio = g.portfolio_laden(profil)
    if int(portfolio.get("drawdown_stufe", 0)) != 2:
        raise Fehler(f"{profil} ist nicht in Drawdown-Stufe 2.")
    pfad = g.pfad(datei)
    if not pfad.exists() or pfad.parent.resolve() != g.pfad("reviews").resolve():
        raise Fehler(f"Review-Datei {datei} nicht gefunden (erwartet in reviews/).")
    portfolio["stufe2_review"] = {"datei": datei, "zeit": g.iso(g.jetzt())}
    g.portfolio_speichern(portfolio)
    return [f"{profil}: Pflicht-Review {datei} vermerkt. Stufe 2 endet, sobald der Drawdown unter der Hälfte "
            "der Schwelle liegt."]


# --------------------------------------------------------------------------
# Bericht


def startdatum() -> date | None:
    profile = g.vorhandene_profile()
    if not profile:
        return None
    return min(date.fromisoformat(g.portfolio_laden(p)["startdatum"]) for p in profile)


def benchmark_berechnen() -> list[dict]:
    """Benchmark je Profil: ETF-Anteil zum ersten Schlusskurs ab Startdatum, Rest Cash mit Zins."""
    start = startdatum()
    if start is None:
        return []
    bis = max(date.fromisoformat(g.portfolio_laden(p)["verarbeitet_bis"]) for p in g.vorhandene_profile())
    if bis < start:
        return []
    ticker = g.projekt()["benchmark_ticker"]
    kerzen = [k for k in kurse.historie(ticker, start, bis)]
    if not kerzen:
        return []
    kapital = D(g.projekt()["startkapital"])
    satz = D(g.kosten()["cash_zins_pa"]) / D(g.kosten()["tage_je_jahr"])
    basis = kerzen[0].close
    profile = {p: D(w["benchmark_etf_anteil"]) for p, w in g.config("profile")["profile"].items()}
    anteile = {p: kapital * w / basis for p, w in profile.items()}
    cash = {p: g.geld(kapital * (EINS - w)) for p, w in profile.items()}
    nach_datum = {k.datum: k for k in kerzen}
    zeilen = []
    for tag in g.tage(start, bis):
        for p in profile:
            if cash[p] > 0:
                cash[p] += g.geld(cash[p] * satz)
        if tag in nach_datum and tag >= kerzen[0].datum:
            zeile = {"datum": tag.isoformat(), "etf_kurs": nach_datum[tag].close}
            for p in profile:
                zeile[p] = g.geld(anteile[p] * nach_datum[tag].close + cash[p])
            zeilen.append(zeile)
    return zeilen


def kennzahlen(profil: str, benchmark: list[dict]) -> dict:
    portfolio = g.portfolio_laden(profil)
    kapital = D(g.projekt()["startkapital"])
    nav = nav_lesen(profil)
    trades = g.trades_lesen(profil)
    werte = [D(z["portfoliowert"]) for z in nav]
    letzter = nav[-1] if nav else None
    wert = D(letzter["portfoliowert"]) if letzter else D(portfolio["cash"])
    rendite = wert / kapital - EINS
    bench = {z["datum"]: D(z[profil]) for z in benchmark}
    bench_rendite = (bench[letzter["datum"]] / kapital - EINS) if letzter and letzter["datum"] in bench else None
    hoch, max_dd = kapital, NULL
    for w in werte:
        hoch = max(hoch, w)
        max_dd = min(max_dd, w / hoch - EINS)
    min_tage = g.projekt()["sharpe_min_handelstage"]
    sharpe = None
    if len(werte) >= min_tage:
        reihe = [kapital] + werte
        renditen = [float(b / a - 1) for a, b in zip(reihe, reihe[1:]) if a > 0]
        rf = float(D(g.projekt()["risikofreier_zins_pa"])) / 252
        ueber = [r - rf for r in renditen]
        streuung = statistics.stdev(ueber) if len(ueber) > 1 else 0.0
        sharpe = (statistics.mean(ueber) / streuung * math.sqrt(252)) if streuung > 0 else None
    offene_ids = {p["id"] for p in portfolio["positionen"]}
    ergebnisse: dict[str, Decimal] = {}
    for zeile in trades:
        if zeile["position_id"] and zeile["aktion"] in ("kauf", "verkauf", "dividende", "knockout"):
            ergebnisse[zeile["position_id"]] = ergebnisse.get(zeile["position_id"], NULL) + D(zeile["betrag_eur"] or 0)
    geschlossen = {pid: e for pid, e in ergebnisse.items() if pid not in offene_ids}
    gewinne = [e for e in geschlossen.values() if e > 0]
    verluste = [e for e in geschlossen.values() if e <= 0]
    kosten = sum((D(z["gebuehr_eur"] or 0) + D(z["spread_eur"] or 0) for z in trades), NULL)
    payoff = None
    if gewinne and verluste and sum(verluste) != 0:
        payoff = (sum(gewinne) / len(gewinne)) / abs(sum(verluste) / len(verluste))
    return {
        "portfolio": portfolio, "stand": letzter["datum"] if letzter else portfolio["verarbeitet_bis"],
        "wert": wert, "rendite": rendite, "bench_rendite": bench_rendite,
        "gegen_bench": rendite - bench_rendite if bench_rendite is not None else None,
        "max_dd": max_dd, "sharpe": sharpe, "handelstage": len(werte), "min_tage": min_tage,
        "geschlossen": len(geschlossen), "trefferquote": D(len(gewinne)) / len(geschlossen) if geschlossen else None,
        "payoff": payoff, "kostenquote": kosten / kapital,
        "exposure": D(letzter["exposure"]) if letzter else NULL,
        "cashquote": D(letzter["cashquote"]) if letzter else EINS,
        "stufe": portfolio.get("drawdown_stufe", 0), "status": portfolio["status"],
    }


def _de(text) -> str:
    """Dezimalkomma für den Bericht (ranking.md ist für Menschen; Daten und Dateien bleiben mit Punkt)."""
    return str(text).replace(".", ",")


def _p(wert) -> str:
    return "–" if wert is None else _de(f"{D(wert) * 100:+.2f} %".replace("+-", "-"))


def _q(wert) -> str:
    return "–" if wert is None else _de(f"{D(wert) * 100:.1f} %")


def ranking_text(alle: dict, erstellt: datetime) -> str:
    profile = list(alle)
    zeilen = ["# Ranking", "",
              f"Erstellt: {erstellt.strftime('%Y-%m-%d %H:%M')} (automatisch durch tools/bewertung.py bericht; "
              "nicht von Hand bearbeiten)", ""]
    if not profile:
        return "\n".join(zeilen + ["Das Spiel ist noch nicht initialisiert (tools/init.py).", ""])
    kopf = "| Kennzahl | " + " | ".join(p.capitalize() for p in profile) + " |"
    stand = ", ".join(f"{p} {alle[p]['stand']}" for p in profile)
    zeilen += [f"Stand der Bewertung: {stand}", "",
               kopf, "| --- |" + " ---: |" * len(profile)]

    def reihe(name, funktion):
        zeilen.append(f"| {name} | " + " | ".join(funktion(alle[p]) for p in profile) + " |")

    reihe("Portfoliowert", lambda k: _de(f"{g.geld(k['wert'])} EUR"))
    reihe("Rendite", lambda k: _p(k["rendite"]))
    reihe("Benchmark-Rendite", lambda k: _p(k["bench_rendite"]))
    reihe("Rendite gegen Benchmark", lambda k: _p(k["gegen_bench"]))
    reihe("Max. Drawdown", lambda k: _p(k["max_dd"]))
    reihe("Sharpe Ratio", lambda k: _de(f"{k['sharpe']:.2f}") if k["sharpe"] is not None and k["handelstage"] >= k["min_tage"]
          else ("zu wenig Daten" + f" ({k['handelstage']}/{k['min_tage']} Handelstage)"
                if k["handelstage"] < k["min_tage"] else "–"))
    reihe("Abgeschlossene Trades", lambda k: str(k["geschlossen"]))
    reihe("Trefferquote", lambda k: _q(k["trefferquote"]))
    reihe("Payoff-Ratio", lambda k: "–" if k["payoff"] is None else _de(f"{k['payoff']:.2f}"))
    reihe("Kostenquote (in % des Startkapitals)", lambda k: _q(k["kostenquote"]))
    reihe("Exposure", lambda k: _de(f"{k['exposure']:.2f}x"))
    reihe("Cashquote", lambda k: _q(k["cashquote"]))
    reihe("Drawdown-Stufe", lambda k: str(k["stufe"]))
    reihe("Status", lambda k: k["status"])
    zeilen.append("")
    for profil in profile:
        portfolio = alle[profil]["portfolio"]
        zeilen += [f"## {profil.capitalize()}", ""]
        if portfolio["positionen"]:
            zeilen += ["| Position | Typ | Instrument | Stück | Einstand EUR | Stop | Kursziel | eröffnet |",
                       "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |"]
            for p in portfolio["positionen"]:
                zeilen.append(f"| {p['id']} | {p['typ']} {p['richtung']} | {p['ticker']} | {_de(p['stueck'])} | "
                              f"{_de(g.geld(p['einstand']))} | {_de(p['stop'] or '–')} | {_de(p['kursziel'] or '–')} | "
                              f"{p['eroeffnet'][:16]} |")
        else:
            zeilen.append("Keine offenen Positionen.")
        if portfolio["offene_orders"]:
            zeilen += ["", "Offene Orders:", ""]
            for o in portfolio["offene_orders"]:
                zeilen.append(f"- {o['id']}: {o['aktion']} {o['art']} {o.get('ticker') or o.get('basiswert')}"
                              + (f", Limit {_de(o['limit'])}" if o.get("limit") else "")
                              + (f", Einsatz {_de(o['einsatz'])} EUR" if o.get("einsatz") else "")
                              + f" (erfasst {o['erfasst'][:16]}, {o['journal_id']})")
        zeilen.append("")
    zeilen += ["Benchmarks: iShares Core MSCI World (EUNL.DE) und Cash (2 % p. a.), Aufteilung je Profil "
               "laut regeln.md Abschnitt 7, ohne Rebalancing und Kosten. Zahlen mit Dezimalkomma.", ""]
    return "\n".join(zeilen)


def bericht() -> list[str]:
    g.aktive_sperre()
    benchmark = benchmark_berechnen()
    if benchmark:
        g.csv_schreiben(g.pfad("data", "benchmark.csv"), ["datum", "etf_kurs", *g.PROFILE], benchmark)
    alle = {p: kennzahlen(p, benchmark) for p in g.vorhandene_profile()}
    g.atomar_schreiben(g.pfad("ranking.md"), ranking_text(alle, g.jetzt()))
    meldungen = ["ranking.md aktualisiert."]
    for profil, k in alle.items():
        meldungen.append(f"{profil}: {g.geld(k['wert'])} EUR ({_p(k['rendite'])}, gegen Benchmark "
                         f"{_p(k['gegen_bench'])}), Drawdown-Stufe {k['stufe']}, {k['status']}")
    return meldungen


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Nachbuchung und Bewertung der Portfolios.")
    unter = parser.add_subparsers(dest="befehl", required=True)
    unter.add_parser("nachbuchen", help="Alle Tage seit der letzten Verarbeitung nachbuchen")
    unter.add_parser("bericht", help="data/benchmark.csv und ranking.md schreiben")
    p = unter.add_parser("review", help="Pflicht-Review bei Drawdown-Stufe 2 vermerken")
    p.add_argument("--profil", required=True, choices=g.PROFILE)
    p.add_argument("--datei", required=True, help="Pfad der Review-Datei, z. B. reviews/2026-10-20_stufe2.md")
    args = parser.parse_args(argv)
    try:
        if args.befehl == "nachbuchen":
            meldungen = nachbuchen()
        elif args.befehl == "bericht":
            meldungen = bericht()
        else:
            meldungen = review_vermerken(args.profil, args.datei)
        for meldung in meldungen:
            print(meldung)
    except Fehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
