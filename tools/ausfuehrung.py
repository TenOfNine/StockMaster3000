#!/usr/bin/env python3
"""Automatische Ausführung ohne Claude-Lauf (regeln.md Abschnitte 5 und 6).

Der Hintergrunddienst ruft `tick` im Takt und zu Börsenöffnung und -schluss auf. Der Tick führt zu protokollierten
Kursen (tools/kurse.py) während der Handelszeit aus, was vorher erfasst wurde:

- vorgemerkte Market-Orders (außerhalb der Handelszeit erfasst) zur Eröffnung,
- Limit-Orders bei Berührung des Limits,
- Stop, Kursziel und Knock-out-Barrieren offener Positionen.

Rechnen, Limits und Buchung sind dieselben Funktionen wie in buchen.py und bewertung.py; die Ausführung läuft
unter der Buchungssperre (gemeinsam.buchungssperre) über den ganzen Vorgang, lädt das Portfolio erst in der Sperre
und führt eine Order höchstens einmal aus. Jede Buchung trägt die ursprüngliche Journal-ID und in der Bemerkung
`automatisch (Auslöser: …)`. Ohne verlässlichen Kurs wird nicht ausgeführt; der nächste Tick versucht es erneut.
Die nächtliche Nachbuchung (bewertung.py) bleibt der Abgleich: Sie holt nach, was kein Tick erfasst hat
(Tageshoch und -tief, Eröffnungskurs), und nimmt dabei die ungünstigere Annahme.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

import bewertung
import buchen
import gemeinsam as g
import kurse
import limits
import produkte
from gemeinsam import D, Fehler

EINS = Decimal("1")
STANDARD = {"takt_minuten": 5, "wiederholung_minuten": 1, "nach_oeffnung_minuten": 1, "vor_schluss_minuten": 2,
            "eroeffnung_fenster_minuten": 30, "sperre_wartezeit_sekunden": 20}


def einstellungen() -> dict:
    return {**STANDARD, **g.projekt().get("ausfuehrung", {})}


# --------------------------------------------------------------------------
# Uhr: wann ist ein Tick fällig?


def ereignisse(von: datetime, bis: datetime) -> list[dict]:
    """Ereignisse im Zeitraum (von, bis]: kurz nach der Eröffnung und kurz vor dem Schluss jeder Börse.

    Zeitzonen, Sommerzeit, Feiertage und verkürzte Handelstage kommen aus config/universum.json.
    """
    einst = einstellungen()
    nach, vor = timedelta(minutes=einst["nach_oeffnung_minuten"]), timedelta(minutes=einst["vor_schluss_minuten"])
    gefunden = []
    tag = von.astimezone(g.TZ).date() - timedelta(days=1)
    ende = bis.astimezone(g.TZ).date() + timedelta(days=1)
    while tag <= ende:
        for name in kurse.handelsboersen():
            fenster = kurse.boersen_fenster(name, tag)
            if fenster is None:
                continue
            for art, zeit in (("eroeffnung", fenster[0] + nach), ("schluss", fenster[1] - vor)):
                if von < zeit <= bis:
                    gefunden.append({"zeit": zeit, "art": art, "boerse": name})
        tag += timedelta(days=1)
    return sorted(gefunden, key=lambda e: e["zeit"])


def irgendeine_boerse_offen(jetzt: datetime) -> bool:
    tag = jetzt.astimezone(g.TZ).date()
    for name in kurse.handelsboersen():
        for d in (tag - timedelta(days=1), tag, tag + timedelta(days=1)):
            fenster = kurse.boersen_fenster(name, d)
            if fenster and fenster[0] <= jetzt < fenster[1]:
                return True
    return False


def faellig(zuletzt: datetime | None, jetzt: datetime, wiederholen: bool = False) -> str | None:
    """Auslöser des nächsten Ticks (`eroeffnung`, `schluss`, `takt`) oder None.

    Ein Ereignis (Öffnung, Schluss) seit dem letzten Tick löst sofort aus; sonst gilt bei offenem Markt der Takt
    (bei `wiederholen`, etwa nach fehlendem Kurs oder belegter Sperre, die kürzere Wiederholung).
    """
    einst = einstellungen()
    ereignis = ereignisse(zuletzt or jetzt - timedelta(minutes=10), jetzt)
    if ereignis:
        return ereignis[-1]["art"]
    if not irgendeine_boerse_offen(jetzt):
        return None
    minuten = einst["wiederholung_minuten"] if wiederholen else einst["takt_minuten"]
    if zuletzt is None or jetzt - zuletzt >= timedelta(minutes=minuten):
        return "takt"
    return None


# --------------------------------------------------------------------------
# Hilfen


def _aktive_portfolios() -> dict[str, dict]:
    daten = {}
    for profil in g.vorhandene_profile():
        portfolio = g.portfolio_laden(profil)
        if portfolio.get("status") == "aktiv":
            daten[profil] = portfolio
    return daten


def _bedarf(portfolio: dict, jetzt: datetime) -> tuple[set[str], set[str]]:
    """(Ticker mit offenem Markt, die etwas auslösen können; weitere Ticker für die Bewertung bei Käufen)."""
    ausloeser = {x["basiswert"] for x in portfolio["offene_orders"] + portfolio["positionen"]
                 if kurse.markt_offen(x["basiswert"], jetzt)}
    kauf_faellig = any(o["aktion"] == "kauf" and kurse.markt_offen(o["basiswert"], jetzt)
                       for o in portfolio["offene_orders"])
    bewertung_ = {p["basiswert"] for p in portfolio["positionen"]} if kauf_faellig else set()
    return ausloeser, bewertung_ - ausloeser


def _gebuchte_order_ids(profil: str) -> set[str]:
    """Orders, die laut trades/ schon einen Endzustand haben (Ausführung, Verfall, Storno)."""
    return {z["order_id"] for z in g.trades_lesen(profil)
            if z["order_id"] and z["aktion"] in ("kauf", "verkauf", "verfall", "storno", "knockout")}


def _markt(portfolio: dict, quotes: dict, fx, zusaetzlich: str, heute: date) -> limits.Markt:
    tickers = {p["basiswert"] for p in portfolio["positionen"]} | {zusaetzlich}
    fehlend = sorted(t for t in tickers if t not in quotes)
    if fehlend:
        raise g.KursFehler(f"Für {', '.join(fehlend)} liegt kein verlässlicher Kurs vor.")
    eurusd = None
    if any(kurse.waehrung(t) == "USD" for t in tickers):
        if fx is None:
            raise g.KursFehler("Für den Devisenkurs liegt kein verlässlicher Kurs vor.")
        eurusd = fx.kurs
    return limits.Markt(kurse={t: quotes[t].kurs for t in tickers}, eurusd=eurusd, datum=heute)


def _fx_fuer(ticker: str, fx) -> Decimal | None:
    if not bewertung.braucht_fx(ticker):
        return None
    if fx is None:
        raise g.KursFehler("Für den Devisenkurs liegt kein verlässlicher Kurs vor.")
    return fx.kurs


# --------------------------------------------------------------------------
# Ein Portfolio


class _Ctx:
    def __init__(self, bericht: dict, quotes: dict, fx, jetzt: datetime):
        self.bericht, self.quotes, self.fx, self.jetzt = bericht, quotes, fx, jetzt
        self.einst = einstellungen()

    def uebersprungen(self, profil: str, text: str, wiederholen: bool = False, protokoll: bool = False) -> None:
        self.bericht["uebersprungen"].append({"profil": profil, "text": text})
        if protokoll:
            self.bericht["probleme"].append({"profil": profil, "text": text})
        if wiederholen:
            self.bericht["wiederholen"] = True


def _orders(lauf: g.Buchungslauf, ctx: _Ctx, bereits: set[str]) -> None:
    portfolio = lauf.portfolio
    profil = portfolio["profil"]
    for order in sorted(portfolio["offene_orders"], key=lambda o: o["erfasst"]):
        ticker = order["basiswert"]
        if order["id"] in bereits:
            ctx.uebersprungen(profil, f"Order {order['id']} hat laut trades/ schon eine Endbuchung und wird nicht "
                                      "erneut ausgeführt (pruefe.py).", protokoll=True)
            continue
        if not kurse.markt_offen(ticker, ctx.jetzt):
            continue  # wartet auf die Eröffnung
        q = ctx.quotes.get(ticker)
        if q is None:
            ctx.uebersprungen(profil, f"{order['id']}: kein verlässlicher Kurs für {ticker}; nächster Versuch folgt.",
                              wiederholen=True)
            continue
        erfasst = g.zeit_lesen(order["erfasst"])
        if q.kurs_zeit <= erfasst:
            ctx.uebersprungen(profil, f"{order['id']}: der Kurs ({q.kurs_zeit:%H:%M}) ist nicht neuer als die Order "
                                      f"({erfasst:%d.%m. %H:%M}); eine Order gilt erst ab ihrer Erfassung.",
                              wiederholen=True)
            continue
        if order["art"] == "market":
            oeffnung = kurse.oeffnung(ticker, kurse.boersentag(ticker, ctx.jetzt))
            if erfasst < oeffnung:
                if q.kurs_zeit < oeffnung:
                    ctx.uebersprungen(profil, f"{order['id']}: der Kurs liegt vor der Eröffnung; nächster Versuch folgt.",
                                      wiederholen=True)
                    continue
                if q.kurs_zeit - oeffnung > timedelta(minutes=ctx.einst["eroeffnung_fenster_minuten"]):
                    ctx.uebersprungen(profil, f"{order['id']}: Eröffnungsfenster ({ctx.einst['eroeffnung_fenster_minuten']} "
                                              "Minuten) verpasst; die Nachbuchung führt sie zum Eröffnungskurs aus.",
                                      protokoll=True)
                    continue
                ausloeser, detail = "Eröffnung", f"erster Kurs {q.kurs} ({q.kurs_zeit:%H:%M}) nach Eröffnung {oeffnung:%H:%M}"
            else:
                ausloeser, detail = "Markt", f"Kurs {q.kurs}"
        else:
            limit = D(order["limit"])
            long = order["richtung"] == "long"
            if not (q.kurs <= limit if long else q.kurs >= limit):
                continue  # Limit nicht erreicht
            ausloeser, detail = "Limit", f"Kurs {q.kurs} {'<=' if long else '>='} Limit {limit}"
        zusatz = g.automatisch_text(ausloeser, detail)
        try:
            if order["aktion"] == "kauf":
                _kauf(lauf, ctx, order, q, zusatz)
            else:
                _verkauf(lauf, ctx, order, q, zusatz)
        except g.KursFehler as exc:
            ctx.uebersprungen(profil, f"{order['id']}: {exc}", wiederholen=True)


def _kauf(lauf: g.Buchungslauf, ctx: _Ctx, order: dict, q: kurse.Kurs, zusatz: str) -> None:
    portfolio = lauf.portfolio
    markt = _markt(portfolio, ctx.quotes, ctx.fx, order["basiswert"], ctx.jetzt.date())
    plan = limits.kaufplan(order["typ"], order["richtung"], order["basiswert"], D(order["einsatz"]), q.kurs,
                           hebel=order.get("hebel"), faktor=order.get("faktor"), stop=D(order.get("stop")),
                           kursziel=D(order.get("kursziel")), kauftag=q.zeit.date())
    verstoesse, kennzahlen = limits.pruefe_kauf(portfolio, plan, markt)
    if verstoesse:
        bewertung.order_verfallen(lauf, order, q.zeit,
                                  f"{zusatz}; Limits bei Ausführung verletzt: " + "; ".join(map(str, verstoesse)))
        return
    portfolio["offene_orders"].remove(order)
    buchen.kauf_ausfuehren(lauf, order, plan, markt, q.zeit, "kurse", g.iso(q.zeit), kennzahlen, zusatz=zusatz)


def _verkauf(lauf: g.Buchungslauf, ctx: _Ctx, order: dict, q: kurse.Kurs, zusatz: str) -> None:
    portfolio = lauf.portfolio
    position = next((p for p in portfolio["positionen"] if p["id"] == order.get("position_id")), None)
    if position is None:
        bewertung.order_verfallen(lauf, order, q.zeit, f"{zusatz}; Position besteht nicht mehr")
        return
    eurusd = _fx_fuer(order["basiswert"], ctx.fx)
    portfolio["offene_orders"].remove(order)
    buchen.verkauf_ausfuehren(lauf, position, D(order["anteil"]), q.kurs, eurusd, q.zeit, q.zeit.date(), "kurse",
                              g.iso(q.zeit), "order", order_id=order["id"], journal_id=order["journal_id"],
                              zusatz=zusatz)


def _positionen(lauf: g.Buchungslauf, ctx: _Ctx) -> None:
    """Knock-out vor Stop vor Kursziel, jeweils gegen den protokollierten Kurs dieses Ticks."""
    portfolio = lauf.portfolio
    profil = portfolio["profil"]
    for position in list(portfolio["positionen"]):
        ticker = position["basiswert"]
        if not kurse.markt_offen(ticker, ctx.jetzt):
            continue
        q = ctx.quotes.get(ticker)
        if q is None:
            ctx.uebersprungen(profil, f"{position['id']}: kein verlässlicher Kurs für {ticker}; Stop, Kursziel und "
                                      "Barriere werden beim nächsten Versuch geprüft.", wiederholen=True)
            continue
        if q.kurs_zeit <= g.zeit_lesen(position["eroeffnet"]):
            continue  # Kurs nicht neuer als der Kauf
        long = position["richtung"] == "long"
        stop, ziel = D(position["stop"]), D(position["kursziel"])
        barriere = D(position["parameter"]["barriere"]) if position["typ"] == "ko" else None
        try:
            eurusd = _fx_fuer(ticker, ctx.fx)
        except g.KursFehler as exc:
            ctx.uebersprungen(profil, f"{position['id']}: {exc}", wiederholen=True)
            continue
        if barriere is not None and produkte.ko_ausgeknockt(position["richtung"], barriere, q.kurs, q.kurs):
            buchen.wertlos_ausbuchen(lauf, position, q.kurs, q.zeit, "kurse", g.iso(q.zeit), g.automatisch_text(
                "Knock-out", f"Kurs {q.kurs} jenseits der Barriere {barriere}"), eurusd)
        elif stop is not None and (q.kurs <= stop if long else q.kurs >= stop):
            buchen.verkauf_ausfuehren(lauf, position, EINS, q.kurs, eurusd, q.zeit, q.zeit.date(), "kurse",
                                      g.iso(q.zeit), "stop", zusatz=g.automatisch_text(
                                          "Stop", f"Kurs {q.kurs} {'<=' if long else '>='} Stop {stop}"))
        elif ziel is not None and (q.kurs >= ziel if long else q.kurs <= ziel):
            buchen.verkauf_ausfuehren(lauf, position, EINS, q.kurs, eurusd, q.zeit, q.zeit.date(), "kurse",
                                      g.iso(q.zeit), "kursziel", zusatz=g.automatisch_text(
                                          "Kursziel", f"Kurs {q.kurs} {'>=' if long else '<='} Kursziel {ziel}"))


def _profil(profil: str, ctx: _Ctx) -> None:
    portfolio = g.portfolio_laden(profil)  # frisch, innerhalb der Buchungssperre
    if portfolio.get("status") != "aktiv":
        return
    if date.fromisoformat(portfolio["verarbeitet_bis"]) < ctx.jetzt.date() - timedelta(days=1):
        ctx.uebersprungen(profil, f"Nachbuchung steht aus (verarbeitet bis {portfolio['verarbeitet_bis']}); die "
                                  "Ausführung wartet, damit die Reihenfolge der Tage stimmt.", protokoll=True)
        ctx.bericht["rueckstand_nachbuchung"] = True
        return
    lauf = g.Buchungslauf(portfolio)
    _orders(lauf, ctx, _gebuchte_order_ids(profil))
    _positionen(lauf, ctx)
    if lauf.zeilen:
        zeilen = list(lauf.zeilen)
        lauf.speichern()
        ctx.bericht["ausgefuehrt"] += [{"profil": profil, "trade_id": z["trade_id"], "aktion": z["aktion"],
                                        "ticker": z["ticker"], "order_id": z["order_id"], "position_id": z["position_id"],
                                        "bemerkung": z["bemerkung"]} for z in zeilen]
        ctx.bericht["meldungen"] += lauf.meldungen
    ctx.bericht["offen"] += len(portfolio["offene_orders"])
    ctx.bericht["rueckstand"] += sum(1 for o in portfolio["offene_orders"]
                                     if o["art"] == "market" and kurse.markt_offen(o["basiswert"], ctx.jetzt))


# --------------------------------------------------------------------------
# Tick


def tick(ausloeser: str = "takt", jetzt: datetime | None = None) -> dict:
    """Ein Durchlauf für alle aktiven Portfolios. Gibt den Bericht zurück (JSON-fähig)."""
    jetzt = jetzt or g.jetzt()
    einst = einstellungen()
    bericht: dict = {"zeit": g.iso(jetzt), "ausloeser": ausloeser, "ausgefuehrt": [], "uebersprungen": [],
                     "probleme": [], "fehler": [], "meldungen": [], "offen": 0, "rueckstand": 0,
                     "wiederholen": False, "rueckstand_nachbuchung": False, "hinweis": ""}
    if not g.spiel_lesen().get("startdatum"):
        bericht["hinweis"] = "Spiel noch nicht gestartet."
        return bericht
    portfolios = _aktive_portfolios()
    ausloesende: set[str] = set()
    weitere: set[str] = set()
    for portfolio in portfolios.values():
        a, w = _bedarf(portfolio, jetzt)
        ausloesende |= a
        weitere |= w
    if not ausloesende:
        bericht["offen"] = sum(len(p["offene_orders"]) for p in portfolios.values())
        bericht["hinweis"] = "Kein offener Markt mit Orders oder Positionen."
        return bericht
    quotes: dict = {}
    for ticker in sorted(ausloesende | weitere):
        try:
            quotes[ticker] = kurse.aktuell([ticker])[0]
        except Fehler as exc:
            bericht["fehler"].append({"ticker": ticker, "text": str(exc)[:300]})
            bericht["wiederholen"] = True
    fx = None
    if any(bewertung.braucht_fx(t) for t in ausloesende | weitere):
        try:
            fx = kurse.devisenkurs_aktuell()
        except Fehler as exc:
            bericht["fehler"].append({"ticker": g.projekt()["devisen_ticker"], "text": str(exc)[:300]})
            bericht["wiederholen"] = True
    ctx = _Ctx(bericht, quotes, fx, jetzt)
    for profil in portfolios:
        try:
            with g.buchungssperre(einst["sperre_wartezeit_sekunden"]):
                _profil(profil, ctx)
        except g.BuchungssperreBelegt as exc:
            ctx.uebersprungen(profil, f"Buchungssperre belegt, nächster Versuch folgt: {exc}", wiederholen=True)
            bericht["probleme"].append({"profil": profil, "text": "Buchungssperre belegt."})
        except Fehler as exc:
            bericht["fehler"].append({"profil": profil, "text": str(exc)[:300]})
            bericht["wiederholen"] = True
    _protokollieren(bericht)
    return bericht


def _protokollieren(bericht: dict) -> None:
    """Hängt Ticks mit Buchung, Problem oder Fehler an data/ausfuehrung/JJJJ-MM-TT.jsonl an (nur anhängen)."""
    if not (bericht["ausgefuehrt"] or bericht["probleme"] or bericht["fehler"]):
        return
    tag = bericht["zeit"][:10]
    zeile = json.dumps({k: bericht[k] for k in ("zeit", "ausloeser", "ausgefuehrt", "probleme", "fehler")},
                       ensure_ascii=False) + "\n"
    g.text_anhaengen(g.pfad("data", "ausfuehrung", f"{tag}.jsonl"), zeile)


# --------------------------------------------------------------------------
# Kommandozeile


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Automatische Ausführung ohne Claude-Lauf.")
    unter = parser.add_subparsers(dest="befehl", required=True)
    p = unter.add_parser("tick", help="Einen Durchlauf ausführen")
    p.add_argument("--ausloeser", default="takt", choices=["takt", "eroeffnung", "schluss"])
    p.add_argument("--json", action="store_true", help="Bericht als eine JSON-Zeile ausgeben")
    p = unter.add_parser("ereignisse", help="Eröffnungs- und Schlussereignisse eines Tages anzeigen")
    p.add_argument("--tag", help="JJJJ-MM-TT (Standard: heute)")
    args = parser.parse_args(argv)
    try:
        if args.befehl == "tick":
            bericht = tick(args.ausloeser)
            if args.json:
                print(json.dumps(bericht, ensure_ascii=False))
            else:
                for meldung in bericht["meldungen"]:
                    print(meldung)
                print(f"Ausführung ({bericht['ausloeser']}): {len(bericht['ausgefuehrt'])} Buchungen, "
                      f"{len(bericht['uebersprungen'])} übersprungen, {len(bericht['fehler'])} Fehler, "
                      f"{bericht['offen']} Orders offen.")
        else:
            tag = g.datum_lesen(args.tag) if args.tag else g.heute()
            beginn = datetime.combine(tag, datetime.min.time(), tzinfo=g.TZ)
            for e in ereignisse(beginn, beginn + timedelta(days=1)):
                print(f"{e['zeit']:%Y-%m-%d %H:%M} {e['art']:<10} {e['boerse']}")
    except Fehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
