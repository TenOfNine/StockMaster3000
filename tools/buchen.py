#!/usr/bin/env python3
"""Orders erfassen und buchen: kaufen, verkaufen, aendern, storno.

Jede Order braucht eine Journal-ID (vorher erfasster Eintrag der Person, die
die Session-Sperre hält) und besteht die Limitprüfung. Ist der Markt offen,
wird eine Market-Order sofort zum protokollierten Kurs inklusive Spread und
Gebühr ausgeführt, sonst vorgemerkt und beim Nachbuchen zum nächsten
Eröffnungskurs ausgeführt.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

import gemeinsam as g
import kurse
import limits
import produkte
from gemeinsam import D, Fehler

EINS = Decimal("1")


# --------------------------------------------------------------------------
# Prüfungen vor jeder Order


def journal_pruefen(journal_id: str, profil: str, eindeutig: bool) -> dict:
    """Journal-Eintrag existiert, gehört zur Sperr-Person, liegt nicht in der Zukunft."""
    sperre = g.aktive_sperre()
    if not journal_id:
        raise Fehler("Ohne Journal-ID wird keine Order gebucht (regeln.md Abschnitt 10).")
    eintraege = g.journal_eintraege()
    if journal_id not in eintraege:
        raise Fehler(f"Journal-Eintrag {journal_id} nicht gefunden. Erst den Eintrag in "
                     f"journal/JJJJ-MM-TT_<person>.md schreiben, dann buchen.")
    eintrag = eintraege[journal_id]
    if eintrag.get("doppelt"):
        raise Fehler(f"Journal-ID {journal_id} kommt mehrfach vor.")
    if eintrag["person"] != sperre["person"]:
        raise Fehler(f"Journal-Eintrag {journal_id} liegt in {eintrag['datei']}, die Session-Sperre gehört "
                     f"aber {sperre['person']}.")
    if eintrag["portfolio"] != profil:
        raise Fehler(f"Journal-Eintrag {journal_id} betrifft Portfolio '{eintrag['portfolio']}', nicht '{profil}'.")
    if eintrag["zeit"] is None:
        raise Fehler(f"Journal-Eintrag {journal_id} hat keine Zeile '- Zeit: JJJJ-MM-TT HH:MM'.")
    if eintrag["zeit"] > g.jetzt():
        raise Fehler(f"Journal-Eintrag {journal_id} trägt eine Zeit in der Zukunft ({eintrag['zeit']}).")
    if eindeutig and journal_id in verwendete_journal_ids():
        raise Fehler(f"Journal-ID {journal_id} wurde bereits für eine Order verwendet; je Order ein Eintrag.")
    return eintrag


def verwendete_journal_ids() -> set[str]:
    ids = set()
    for profil in g.vorhandene_profile():
        for zeile in g.trades_lesen(profil):
            if zeile["grund"] == "order" and (zeile["aktion"] in ("kauf", "verkauf", "vormerkung") or (
                    zeile["aktion"] == "aenderung" and zeile["bemerkung"].startswith("Daueranweisung ")
                    and " gesetzt" in zeile["bemerkung"])):
                ids.add(zeile["journal_id"])
        for order in g.portfolio_laden(profil)["offene_orders"]:
            ids.add(order["journal_id"])
    return ids


def portfolio_pruefen(profil: str) -> dict:
    portfolio = g.portfolio_laden(profil)
    if portfolio.get("status") != "aktiv":
        raise Fehler(f"Portfolio {profil} ist {portfolio.get('status')}; keine Orders möglich.")
    if date.fromisoformat(portfolio["verarbeitet_bis"]) < g.heute() - timedelta(days=1):
        raise Fehler("Es gibt nicht nachgebuchte Tage. Zuerst: python tools/bewertung.py nachbuchen")
    return portfolio


def ist_long_seite(richtung: str) -> bool:
    return richtung == "long"


def position_finden(portfolio: dict, position_id: str) -> dict:
    for position in portfolio["positionen"]:
        if position["id"] == position_id:
            return position
    raise Fehler(f"Position {position_id} gibt es im Portfolio {portfolio['profil']} nicht.")


# --------------------------------------------------------------------------
# Ausführung (auch von bewertung.py genutzt)


def kauf_ausfuehren(lauf: g.Buchungslauf, order: dict, plan: limits.Kaufplan, markt: limits.Markt,
                    zeit: datetime, kursquelle: str, kurs_zeit: str, kennzahlen: dict, zusatz: str = "") -> dict:
    portfolio = lauf.portfolio
    satz = g.spread(plan.typ)
    mitte_eur = markt.in_eur(plan.wert_je_stueck, plan.basiswert)
    kaufkurs = mitte_eur * (EINS + satz / 2)
    stueck = g.stueck_runden(plan.einsatz / kaufkurs)
    if stueck <= 0:
        raise Fehler("Einsatz reicht für keine Stückzahl.")
    kurswert = g.geld(stueck * kaufkurs)
    spread_eur = g.geld(stueck * mitte_eur * satz / 2)
    gebuehr = g.gebuehr()
    g.cash_buchen(portfolio, -(kurswert + gebuehr))
    position_id = g.naechste_id(portfolio, "position")
    parameter = dict(plan.parameter)
    if plan.typ == "ko":
        parameter["wert_je_stueck"] = g.param(plan.wert_je_stueck)
        parameter["stand"] = zeit.date().isoformat()
    position = {
        "id": position_id, "typ": plan.typ, "richtung": plan.richtung, "ticker": plan.ticker,
        "basiswert": plan.basiswert, "stueck": g.text(stueck), "einstand": g.text(g.param(kaufkurs)),
        "einsatz": g.text(kurswert), "eroeffnet": g.iso(zeit),
        "parameter": {k: g.text(v) if isinstance(v, Decimal) else v for k, v in parameter.items()},
        "stop": g.text(plan.stop) if plan.stop is not None else None,
        "kursziel": g.text(plan.kursziel) if plan.kursziel is not None else None,
        "journal_id": order["journal_id"], "order_id": order["id"],
        "stop_historie": [{"ab": g.iso(zeit), "stop": g.text(plan.stop) if plan.stop is not None else None,
                           "kursziel": g.text(plan.kursziel) if plan.kursziel is not None else None}],
    }
    portfolio["positionen"].append(position)
    zeile = lauf.trade(
        zeit=zeit, order_id=order["id"], position_id=position_id, aktion="kauf", typ=plan.typ,
        richtung=plan.richtung, ticker=plan.ticker, basiswert=plan.basiswert, stueck=stueck,
        kurs=g.param(kaufkurs), kurs_basiswert=plan.kurs, hebel=plan.hebel, spread_eur=spread_eur,
        gebuehr_eur=gebuehr, betrag_eur=-(kurswert + gebuehr), kursquelle=kursquelle, kurs_zeit=kurs_zeit,
        journal_id=order["journal_id"], grund="order",
        devisenkurs=markt.eurusd if kurse.waehrung(plan.basiswert) != "EUR" else None,
        stop=plan.stop, kursziel=plan.kursziel,
        bemerkung=_bemerkung(zusatz, _parameter_text(plan)))
    lauf.limits(zeile["trade_id"], zeit, kennzahlen, limits.grenzen(portfolio["profil"]))
    lauf.meldungen.append(
        f"{portfolio['profil']}: Kauf {g.text(stueck)} {plan.ticker} zu {g.param(kaufkurs)} EUR "
        f"(Basiswert {plan.kurs}), Betrag {kurswert} EUR + {gebuehr} EUR Gebühr -> {position_id}")
    return position


def _bemerkung(zusatz: str, text: str) -> str:
    """Bemerkung einer Buchung; `zusatz` ist bei automatischer Ausführung die Kennzeichnung samt Auslöser."""
    return f"{zusatz}; {text}" if zusatz and text else (zusatz or text)


def _parameter_text(plan: limits.Kaufplan) -> str:
    if plan.typ == "ko":
        return f"Basispreis/Barriere {g.param(plan.parameter['basispreis'])}"
    if plan.typ == "faktor":
        return f"Faktor {plan.parameter['faktor']}, Startwert {plan.parameter['wert_je_stueck']}"
    return ""


def verkauf_ausfuehren(lauf: g.Buchungslauf, position: dict, anteil: Decimal, kurs, eurusd, zeit: datetime,
                       datum: date, kursquelle: str, kurs_zeit: str, grund: str, order_id: str = "",
                       journal_id: str | None = None, zusatz: str = "") -> Decimal:
    """Verkauft (Teil-)Position zum Basiswertkurs; gibt den Nettoerlös zurück."""
    portfolio = lauf.portfolio
    kurs = D(kurs)
    wert = produkte.wert_je_stueck(position, kurs, datum)
    if wert <= 0:
        return wertlos_ausbuchen(lauf, position, kurs, zeit, kursquelle, kurs_zeit,
                                 _bemerkung(zusatz, "Wert null beim Verkauf"), eurusd)
    waehrung = kurse.waehrung(position["basiswert"])
    mitte_eur = kurse.in_eur(wert, waehrung, eurusd)
    satz = g.spread(position["typ"])
    hebel_jetzt = produkte.hebel(position, kurs)
    verkaufskurs = mitte_eur * (EINS - satz / 2)
    bestand = D(position["stueck"])
    stueck = bestand if anteil >= EINS else g.stueck_runden(bestand * anteil)
    erloes = g.geld(stueck * verkaufskurs)
    spread_eur = g.geld(stueck * mitte_eur * satz / 2)
    gebuehr = g.gebuehr()
    g.cash_buchen(portfolio, erloes - gebuehr)
    rest = bestand - stueck
    if rest <= 0:
        portfolio["positionen"].remove(position)
    else:
        position["stueck"] = g.text(rest)
    lauf.trade(
        zeit=zeit, order_id=order_id, position_id=position["id"], aktion="verkauf", typ=position["typ"],
        richtung=position["richtung"], ticker=position["ticker"], basiswert=position["basiswert"], stueck=stueck,
        kurs=g.param(verkaufskurs), kurs_basiswert=kurs, hebel=hebel_jetzt,
        spread_eur=spread_eur, gebuehr_eur=gebuehr, betrag_eur=erloes - gebuehr, kursquelle=kursquelle,
        kurs_zeit=kurs_zeit, journal_id=journal_id or position["journal_id"], grund=grund,
        devisenkurs=eurusd if waehrung != "EUR" else None,
        bemerkung=_bemerkung(zusatz, "Teilverkauf" if rest > 0 else ""))
    lauf.meldungen.append(f"{portfolio['profil']}: Verkauf ({grund}) {g.text(stueck)} {position['ticker']} zu "
                          f"{g.param(verkaufskurs)} EUR (Basiswert {kurs}), netto {erloes - gebuehr} EUR")
    return erloes - gebuehr


def wertlos_ausbuchen(lauf: g.Buchungslauf, position: dict, kurs, zeit: datetime, kursquelle: str,
                      kurs_zeit: str, bemerkung: str, eurusd=None) -> Decimal:
    """Knock-out bzw. Faktor-Wert null: Position wertlos, keine Gebühr."""
    portfolio = lauf.portfolio
    portfolio["positionen"].remove(position)
    lauf.trade(
        zeit=zeit, position_id=position["id"], aktion="knockout", typ=position["typ"],
        richtung=position["richtung"], ticker=position["ticker"], basiswert=position["basiswert"],
        stueck=position["stueck"], kurs=Decimal("0"), kurs_basiswert=D(kurs), spread_eur=Decimal("0.00"),
        gebuehr_eur=Decimal("0.00"), betrag_eur=Decimal("0.00"), kursquelle=kursquelle, kurs_zeit=kurs_zeit,
        journal_id=position["journal_id"], grund="knockout",
        devisenkurs=eurusd if kurse.waehrung(position["basiswert"]) != "EUR" else None, bemerkung=bemerkung)
    lauf.meldungen.append(f"{portfolio['profil']}: KNOCK-OUT {position['ticker']} ({position['id']}) bei "
                          f"Basiswert {kurs}; Position wertlos")
    return Decimal("0")


def order_vormerken(lauf: g.Buchungslauf, order: dict, kurs_info: kurse.Kurs | None, hinweis: str) -> None:
    portfolio = lauf.portfolio
    portfolio["offene_orders"].append(order)
    lauf.trade(
        zeit=order["erfasst"], order_id=order["id"], position_id=order.get("position_id"), aktion="vormerkung",
        typ=order.get("typ"), richtung=order.get("richtung"), ticker=order.get("ticker"),
        basiswert=order.get("basiswert"), kurs_basiswert=kurs_info.kurs if kurs_info else None,
        kursquelle="kurse" if kurs_info else None, kurs_zeit=g.iso(kurs_info.zeit) if kurs_info else None,
        journal_id=order["journal_id"], grund="order", stop=order.get("stop"), kursziel=order.get("kursziel"),
        bemerkung=f"{order['aktion']} {order['art']}" + (f" Limit {order['limit']}" if order.get("limit") else "")
        + (f" Einsatz {order['einsatz']}" if order.get("einsatz") else "")
        + (f" Anteil {order['anteil']}" if order.get("anteil") else ""))
    lauf.meldungen.append(f"{portfolio['profil']}: Order {order['id']} vorgemerkt ({hinweis}).")


# --------------------------------------------------------------------------
# Befehle


@g.mit_buchungssperre
def kaufen(args) -> list[str]:
    portfolio = portfolio_pruefen(args.profil)
    journal_pruefen(args.journal_id, args.profil, eindeutig=True)
    if args.typ in g.AKTIEN:
        if not args.ticker or args.basiswert:
            raise Fehler("Bei Aktien und ETFs --ticker angeben (nicht --basiswert).")
        basiswert = args.ticker
    else:
        if not args.basiswert or args.ticker:
            raise Fehler("Bei Zertifikaten --basiswert angeben (nicht --ticker).")
        basiswert = args.basiswert
    if args.typ == "ko" and not args.hebel:
        raise Fehler("Knock-out ohne --hebel.")
    if args.typ == "faktor" and not args.faktor:
        raise Fehler("Faktor-Zertifikat ohne --faktor.")
    stop = limits.stop_lesen(args.stop)
    kursziel = limits.stop_lesen(args.kursziel)
    limit = limits.stop_lesen(args.limit) if args.limit else None

    markt, abgefragt = limits.aktueller_markt(portfolio, [basiswert])
    kurs_info = abgefragt[basiswert]
    plan = limits.kaufplan(args.typ, args.richtung, basiswert, D(args.einsatz), kurs_info.kurs,
                           hebel=args.hebel, faktor=args.faktor, stop=stop, kursziel=kursziel,
                           kauftag=g.heute())
    verstoesse, kennzahlen = limits.pruefe_kauf(portfolio, plan, markt)
    if verstoesse:
        raise Abgelehnt(verstoesse)

    zeit = g.jetzt()
    lauf = g.Buchungslauf(portfolio)
    order = {
        "id": g.naechste_id(portfolio, "order"), "art": "limit" if limit else "market", "aktion": "kauf",
        "typ": args.typ, "richtung": args.richtung, "ticker": plan.ticker, "basiswert": basiswert,
        "einsatz": g.text(plan.einsatz), "hebel": args.hebel, "faktor": args.faktor,
        "stop": g.text(stop) if stop else None, "kursziel": g.text(kursziel) if kursziel else None,
        "limit": g.text(limit) if limit else None, "erfasst": g.iso(zeit), "journal_id": args.journal_id,
    }
    ausfuehrbar = limit is None or (kurs_info.kurs <= limit if ist_long_seite(args.richtung)
                                    else kurs_info.kurs >= limit)
    if kurs_info.markt_offen and ausfuehrbar:
        kauf_ausfuehren(lauf, order, plan, markt, zeit, "kurse", g.iso(kurs_info.zeit), kennzahlen)
    else:
        grund = "Markt geschlossen, Ausführung zum nächsten Eröffnungskurs" if not kurs_info.markt_offen \
            else f"Limit {limit} nicht erreicht (Kurs {kurs_info.kurs})"
        order_vormerken(lauf, order, kurs_info, grund)
    lauf.speichern()
    return lauf.meldungen


@g.mit_buchungssperre
def verkaufen(args) -> list[str]:
    portfolio = portfolio_pruefen(args.profil)
    journal_pruefen(args.journal_id, args.profil, eindeutig=True)
    position = position_finden(portfolio, args.position_id)
    anteil = D(args.anteil)
    if not (Decimal("0") < anteil <= EINS):
        raise Fehler("--anteil muss größer 0 und höchstens 1 sein.")
    if any(o.get("position_id") == position["id"] and o["aktion"] == "verkauf" for o in portfolio["offene_orders"]):
        raise Fehler(f"Für {position['id']} ist bereits ein Verkauf vorgemerkt.")
    markt, abgefragt = limits.aktueller_markt(portfolio, [position["basiswert"]])
    kurs_info = abgefragt[position["basiswert"]]
    if anteil < EINS:
        # Konservative Auslegung: Mindestorder gilt auch für Teilverkäufe (Komplettverkauf immer erlaubt).
        bewertung = limits.portfolio_bewerten(portfolio, markt)
        wert = next(p["wert_eur"] for p in bewertung["positionen"] if p["id"] == position["id"])
        if wert * anteil < D(g.kosten()["mindestorder"]):
            raise Abgelehnt([limits.Verstoss("Mindestorder (Teilverkauf)", f"{g.kosten()['mindestorder']} EUR",
                                             f"{g.geld(wert * anteil)} EUR")])
    zeit = g.jetzt()
    lauf = g.Buchungslauf(portfolio)
    order_id = g.naechste_id(portfolio, "order")
    if kurs_info.markt_offen:
        verkauf_ausfuehren(lauf, position, anteil, kurs_info.kurs, markt.eurusd, zeit, zeit.date(), "kurse",
                           g.iso(kurs_info.zeit), "order", order_id=order_id, journal_id=args.journal_id)
    else:
        order = {"id": order_id, "art": "market", "aktion": "verkauf", "typ": position["typ"],
                 "richtung": position["richtung"], "ticker": position["ticker"], "basiswert": position["basiswert"],
                 "position_id": position["id"], "anteil": g.text(anteil), "erfasst": g.iso(zeit),
                 "journal_id": args.journal_id}
        order_vormerken(lauf, order, kurs_info, "Markt geschlossen, Ausführung zum nächsten Eröffnungskurs")
    lauf.speichern()
    return lauf.meldungen


@g.mit_buchungssperre
def aendern(args) -> list[str]:
    portfolio = portfolio_pruefen(args.profil)
    journal_pruefen(args.journal_id, args.profil, eindeutig=False)
    position = position_finden(portfolio, args.position_id)
    if args.stop is None and args.kursziel is None:
        raise Fehler("Mindestens --stop oder --kursziel angeben.")
    stop = limits.stop_lesen(args.stop) if args.stop is not None else (D(position["stop"]) if position["stop"] else None)
    ziel = limits.stop_lesen(args.kursziel) if args.kursziel is not None else \
        (D(position["kursziel"]) if position["kursziel"] else None)
    markt, abgefragt = limits.aktueller_markt(portfolio, [position["basiswert"]])
    kurs = abgefragt[position["basiswert"]].kurs
    long = position["richtung"] == "long"
    if stop is not None and ((long and stop >= kurs) or (not long and stop <= kurs)):
        raise Abgelehnt([limits.Verstoss("Stop", f"{'unter' if long else 'über'} dem Kurs {kurs}", g.text(stop))])
    if ziel is not None and ((long and ziel <= kurs) or (not long and ziel >= kurs)):
        raise Abgelehnt([limits.Verstoss("Kursziel", f"{'über' if long else 'unter'} dem Kurs {kurs}", g.text(ziel))])
    zeit = g.jetzt()
    position["stop"] = g.text(stop) if stop is not None else None
    position["kursziel"] = g.text(ziel) if ziel is not None else None
    # Änderungen wirken ab dem nächsten Handelstag, dessen Kerze nach der Änderung beginnt.
    position.setdefault("stop_historie", []).append({"ab": g.iso(zeit), "stop": position["stop"],
                                                     "kursziel": position["kursziel"]})
    lauf = g.Buchungslauf(portfolio)
    lauf.trade(zeit=zeit, position_id=position["id"], aktion="aenderung", typ=position["typ"],
               richtung=position["richtung"], ticker=position["ticker"], basiswert=position["basiswert"],
               kurs_basiswert=kurs, kursquelle="kurse", kurs_zeit=g.iso(abgefragt[position["basiswert"]].zeit),
               journal_id=args.journal_id, grund="order", stop=stop, kursziel=ziel)
    lauf.meldungen.append(f"{portfolio['profil']}: {position['id']} Stop {position['stop']}, "
                          f"Kursziel {position['kursziel']} (wirksam ab dem nächsten Handelstag)")
    lauf.speichern()
    return lauf.meldungen


@g.mit_buchungssperre
def storno(args) -> list[str]:
    portfolio = portfolio_pruefen(args.profil)
    journal_pruefen(args.journal_id, args.profil, eindeutig=False)
    order = next((o for o in portfolio["offene_orders"] if o["id"] == args.order_id), None)
    if order is None:
        raise Fehler(f"Offene Order {args.order_id} gibt es im Portfolio {args.profil} nicht.")
    portfolio["offene_orders"].remove(order)
    lauf = g.Buchungslauf(portfolio)
    lauf.trade(zeit=g.jetzt(), order_id=order["id"], position_id=order.get("position_id"), aktion="storno",
               typ=order.get("typ"), richtung=order.get("richtung"), ticker=order.get("ticker"),
               basiswert=order.get("basiswert"), journal_id=args.journal_id, grund="order",
               bemerkung=f"storniert: {order['aktion']} {order['art']}")
    lauf.meldungen.append(f"{portfolio['profil']}: Order {order['id']} storniert.")
    lauf.speichern()
    return lauf.meldungen


class Abgelehnt(Fehler):
    def __init__(self, verstoesse):
        self.verstoesse = verstoesse
        super().__init__("Order abgelehnt:\n" + "\n".join(f"- {v}" for v in verstoesse))


def parser_bauen() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Orders erfassen und buchen (Spielgeld).")
    unter = parser.add_subparsers(dest="befehl", required=True)

    p = unter.add_parser("kaufen", help="Kauforder erfassen")
    p.add_argument("--profil", required=True, choices=g.profile())
    p.add_argument("--typ", required=True, choices=["aktie", "etf", "ko", "faktor"])
    p.add_argument("--richtung", default="long", choices=["long", "short"], help="Standard: long")
    p.add_argument("--ticker", help="Ticker bei Aktien und ETFs, z. B. SAP.DE")
    p.add_argument("--basiswert", help="Basiswert bei Zertifikaten, z. B. ^GDAXI")
    p.add_argument("--einsatz", required=True, help="Einsatz in EUR inkl. Spread, ohne Gebühr (min. 100)")
    p.add_argument("--hebel", help="Zielhebel beim Kauf (Knock-out)")
    p.add_argument("--faktor", help="Faktor (Faktor-Zertifikat)")
    p.add_argument("--stop", required=True, help="Stop auf den Basiswert oder 'keiner'")
    p.add_argument("--kursziel", required=True, help="Kursziel auf den Basiswert oder 'keiner'")
    p.add_argument("--limit", help="Limit auf den Basiswert (Limit-Order)")
    p.add_argument("--journal-id", required=True, help="ID des vorher geschriebenen Journal-Eintrags")

    p = unter.add_parser("verkaufen", help="Position (teilweise) verkaufen")
    p.add_argument("--profil", required=True, choices=g.profile())
    p.add_argument("--position-id", required=True)
    p.add_argument("--anteil", default="1", help="Anteil der Position, 0 < Anteil <= 1 (Standard 1)")
    p.add_argument("--journal-id", required=True)

    p = unter.add_parser("aendern", help="Stop und/oder Kursziel einer Position ändern")
    p.add_argument("--profil", required=True, choices=g.profile())
    p.add_argument("--position-id", required=True)
    p.add_argument("--stop", help="neuer Stop oder 'keiner'")
    p.add_argument("--kursziel", help="neues Kursziel oder 'keiner'")
    p.add_argument("--journal-id", required=True)

    p = unter.add_parser("storno", help="Offene Order stornieren")
    p.add_argument("--profil", required=True, choices=g.profile())
    p.add_argument("--order-id", required=True)
    p.add_argument("--journal-id", required=True)
    return parser


def main(argv=None) -> int:
    args = parser_bauen().parse_args(argv)
    befehle = {"kaufen": kaufen, "verkaufen": verkaufen, "aendern": aendern, "storno": storno}
    try:
        for meldung in befehle[args.befehl](args):
            print(meldung)
    except Abgelehnt as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Fehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
