#!/usr/bin/env python3
"""Limitprüfung nach regeln.md Abschnitt 7 und Portfolio-Kennzahlen.

Prüft eine geplante Kauforder gegen Mindestorder, Einzelposition,
Zertifikate-Anteil, Hebel, Gesamt-Exposure, Cashquote, Risiko je Trade
(inklusive Kosten), Drawdown-Stufe, Universum und Portfolio-Status. Jede
Ablehnung nennt Regel, Grenzwert und Istwert.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

import gemeinsam as g
import kurse
import produkte
from gemeinsam import D, Fehler

EINS = Decimal("1")
NULL = Decimal("0")


@dataclass
class Verstoss:
    regel: str
    grenzwert: str
    istwert: str

    def __str__(self) -> str:
        return f"{self.regel}: Grenzwert {self.grenzwert}, Istwert {self.istwert}"


@dataclass
class Markt:
    """Kurse zu einem Zeitpunkt: Basiswert/Ticker -> Kurs in Originalwährung."""

    kurse: dict = field(default_factory=dict)
    eurusd: Decimal | None = None
    datum: date | None = None

    def kurs(self, ticker: str) -> Decimal:
        if ticker not in self.kurse:
            raise g.KursFehler(f"Für {ticker} liegt kein Kurs vor; Bewertung nicht möglich.")
        return D(self.kurse[ticker])

    def in_eur(self, betrag, ticker: str) -> Decimal:
        return kurse.in_eur(betrag, kurse.waehrung(ticker), self.eurusd)


@dataclass
class Kaufplan:
    typ: str
    richtung: str
    ticker: str          # Instrument (bei Zertifikaten synthetischer Name)
    basiswert: str       # Kursticker: bei Aktien/ETFs = ticker
    einsatz: Decimal     # Kurswert inklusive Spread, ohne Gebühr
    kurs: Decimal        # Basiswertkurs in Originalwährung
    wert_je_stueck: Decimal   # in Originalwährung (Mitte, ohne Spread)
    hebel: Decimal
    parameter: dict
    stop: Decimal | None
    kursziel: Decimal | None

    @property
    def ist_zertifikat(self) -> bool:
        return self.typ in g.ZERTIFIKATE


def _runden_weg(wert: Decimal, aufrunden: bool | None) -> Decimal:
    """Istwerte werden von der Grenze weg gerundet, damit eine Ablehnung nie
    wie der Grenzwert aussieht (Obergrenze: auf-, Untergrenze: abrunden)."""
    if aufrunden is None or not wert.is_finite():
        return wert.quantize(Decimal("0.01")) if wert.is_finite() else wert
    return wert.quantize(Decimal("0.01"), rounding=ROUND_CEILING if aufrunden else ROUND_FLOOR)


def fmt_prozent(wert, aufrunden: bool | None = None) -> str:
    return f"{_runden_weg(D(wert) * 100, aufrunden)} %"


def fmt_faktor(wert, aufrunden: bool | None = None) -> str:
    return f"{_runden_weg(D(wert), aufrunden)}x"


def stop_lesen(wert) -> Decimal | None:
    if wert is None:
        return None
    if str(wert).strip().lower() in ("keiner", "kein", "keins", "-", "none"):
        return None
    try:
        zahl = D(str(wert).replace(",", "."))
    except Exception as exc:
        raise Fehler(f"Ungültiger Wert '{wert}'.") from exc
    if zahl <= 0:
        raise Fehler(f"Ungültiger Wert '{wert}' (muss positiv sein).")
    return zahl


def zertifikat_name(typ: str, richtung: str, basiswert: str) -> str:
    return f"{typ.upper()}-{richtung.upper()}-{basiswert}"


def positions_schluessel(typ: str, richtung: str, basiswert: str) -> tuple:
    """Zusammenfassung für das Einzelpositions-Limit: gleiches Instrument."""
    if typ in g.AKTIEN:
        return ("aktie", basiswert)
    return (typ, richtung, basiswert)


def kaufplan(typ, richtung, basiswert, einsatz, kurs, hebel=None, faktor=None, stop=None,
             kursziel=None, kauftag: date | None = None) -> Kaufplan:
    wert, parameter = produkte.ausgabe(typ, richtung, kurs, hebel=hebel, faktor=faktor, kauftag=kauftag)
    if typ in g.AKTIEN:
        hebel_wert, ticker = EINS, basiswert
    elif typ == "ko":
        # Maßgeblich ist der Zielhebel beim Kauf (Rundung des Basispreises bleibt außen vor).
        hebel_wert, ticker = D(hebel), zertifikat_name(typ, richtung, basiswert)
    else:
        hebel_wert, ticker = D(faktor), zertifikat_name(typ, richtung, basiswert)
    return Kaufplan(typ=typ, richtung=richtung, ticker=ticker, basiswert=basiswert, einsatz=g.geld(einsatz),
                    kurs=D(kurs), wert_je_stueck=wert, hebel=hebel_wert, parameter=parameter,
                    stop=stop, kursziel=kursziel)


# --------------------------------------------------------------------------
# Bewertung


def portfolio_bewerten(portfolio: dict, markt: Markt) -> dict:
    """Marktwerte (Mitte, ohne Spread), Exposure und Quoten des Portfolios."""
    positionen = []
    for position in portfolio["positionen"]:
        kurs = markt.kurs(position["basiswert"])
        wert = produkte.wert_je_stueck(position, kurs, markt.datum)
        wert_eur = markt.in_eur(wert * D(position["stueck"]), position["basiswert"])
        hebel = produkte.hebel(position, kurs)
        positionen.append({
            "id": position["id"], "typ": position["typ"], "richtung": position["richtung"],
            "basiswert": position["basiswert"], "kurs": kurs,
            "schluessel": positions_schluessel(position["typ"], position["richtung"], position["basiswert"]),
            "wert_eur": wert_eur, "hebel": hebel, "exposure_eur": wert_eur * hebel,
            "zertifikat": position["typ"] in g.ZERTIFIKATE})
    cash = g.cash(portfolio)
    positionswert = sum((p["wert_eur"] for p in positionen), NULL)
    nav = cash + positionswert
    zert = sum((p["wert_eur"] for p in positionen if p["zertifikat"]), NULL)
    exposure = sum((p["exposure_eur"] for p in positionen), NULL)
    return {
        "cash": cash, "positionswert": positionswert, "nav": nav, "positionen": positionen,
        "zertifikate_wert": zert, "exposure_eur": exposure,
        "zertifikate_anteil": zert / nav if nav > 0 else NULL,
        "exposure": exposure / nav if nav > 0 else NULL,
        "cashquote": cash / nav if nav > 0 else NULL,
    }


def relativer_verlust_bis_stop(plan: Kaufplan) -> Decimal:
    """Relativer Verlust des Einsatzes, wenn der Stop (auf den Basiswert) greift."""
    typ_schluessel = "aktie" if plan.typ in g.AKTIEN else plan.typ
    if plan.stop is None:
        return D(g.kosten()["verlust_ohne_stop"][typ_schluessel])
    s, stop = plan.kurs, plan.stop
    if plan.typ in g.AKTIEN:
        return max(NULL, (s - stop) / s)
    if plan.typ == "ko":
        wert_stop = produkte.ko_wert(plan.richtung, stop, plan.parameter["basispreis"])
        return min(EINS, max(NULL, EINS - wert_stop / plan.wert_je_stueck))
    f = plan.hebel if plan.richtung == "long" else -plan.hebel
    return min(EINS, max(NULL, EINS - max(NULL, EINS + f * (stop / s - EINS))))


# --------------------------------------------------------------------------
# Prüfung


def pruefe_universum(plan: Kaufplan) -> list[Verstoss]:
    uni = kurse.universum()
    verstoesse = []
    try:
        kurse.boerse_von(plan.basiswert)
    except Fehler as exc:
        return [Verstoss("Universum", "Xetra, NYSE, NASDAQ bzw. Basiswertliste", str(exc))]
    if plan.typ in g.AKTIEN:
        if plan.basiswert in uni["basiswerte"] or plan.basiswert == g.projekt()["devisen_ticker"]:
            verstoesse.append(Verstoss("Universum", "Aktie oder ETF", f"{plan.basiswert} ist kein Wertpapier"))
        mindestkurs = D(uni["aktien"]["mindestkurs"])
        if plan.kurs < mindestkurs:
            verstoesse.append(Verstoss("Universum (Mindestkurs)", f"{mindestkurs} {kurse.waehrung(plan.basiswert)}",
                                       f"{plan.kurs}"))
    else:
        if plan.basiswert not in uni["basiswerte"]:
            if plan.basiswert in uni.get("sonstige_ticker", {}):
                verstoesse.append(Verstoss("Universum (Basiswert)", "erlaubte Basiswertliste", plan.basiswert))
            else:
                grenze = D(uni["aktien_als_basiswert"]["min_marktkapitalisierung"])
                kap = kurse.marktkapitalisierung(plan.basiswert)
                # Konservativ: unbekannte Marktkapitalisierung gilt als zu klein.
                if kap is None or kap <= grenze:
                    verstoesse.append(Verstoss("Universum (Marktkapitalisierung Basiswert)",
                                               f"> {grenze:,.0f}", "unbekannt" if kap is None else f"{kap:,.0f}"))
    return verstoesse


def pruefe_stop_ziel(plan: Kaufplan) -> list[Verstoss]:
    verstoesse = []
    long = plan.richtung == "long"
    if plan.stop is not None and ((long and plan.stop >= plan.kurs) or (not long and plan.stop <= plan.kurs)):
        verstoesse.append(Verstoss("Stop", f"{'unter' if long else 'über'} dem Kurs {plan.kurs}", f"{plan.stop}"))
    if plan.kursziel is not None and ((long and plan.kursziel <= plan.kurs) or
                                      (not long and plan.kursziel >= plan.kurs)):
        verstoesse.append(Verstoss("Kursziel", f"{'über' if long else 'unter'} dem Kurs {plan.kurs}",
                                   f"{plan.kursziel}"))
    return verstoesse


def pruefe_kauf(portfolio: dict, plan: Kaufplan, markt: Markt) -> tuple[list[Verstoss], dict]:
    """Prüft alle Limits; liefert Verstöße und die Kennzahlen für das Protokoll."""
    limits = g.limits_fuer(portfolio["profil"])
    kosten = g.kosten()
    verstoesse: list[Verstoss] = []

    if portfolio.get("status", "aktiv") != "aktiv":
        verstoesse.append(Verstoss("Portfolio-Status", "aktiv", portfolio.get("status")))

    verstoesse += pruefe_universum(plan)
    verstoesse += pruefe_stop_ziel(plan)

    stufe = int(portfolio.get("drawdown_stufe", 0))
    if stufe >= 2 and plan.ist_zertifikat:
        verstoesse.append(Verstoss("Drawdown-Stufe 2", "keine neuen Zertifikate", f"Stufe {stufe}"))

    mindestorder = g.geld(kosten["mindestorder"])
    if plan.einsatz < mindestorder:
        verstoesse.append(Verstoss("Mindestorder", f"{mindestorder} EUR", f"{plan.einsatz} EUR"))

    if plan.ist_zertifikat and plan.hebel > limits["max_hebel"]:
        verstoesse.append(Verstoss("Hebel je Zertifikat", fmt_faktor(limits["max_hebel"]), fmt_faktor(plan.hebel, True)))

    vorher = portfolio_bewerten(portfolio, markt)
    gebuehr = g.gebuehr()
    spread_satz = g.spread(plan.typ)
    spread_kauf = g.geld(plan.einsatz * (spread_satz / 2) / (EINS + spread_satz / 2))
    neuwert = plan.einsatz - spread_kauf
    nav_vorher = vorher["nav"]
    nav_nachher = nav_vorher - gebuehr - spread_kauf
    cash_nachher = vorher["cash"] - plan.einsatz - gebuehr
    schluessel = positions_schluessel(plan.typ, plan.richtung, plan.basiswert)
    gleiche = sum((p["wert_eur"] for p in vorher["positionen"] if p["schluessel"] == schluessel), NULL)
    einzel = (gleiche + neuwert) / nav_nachher if nav_nachher > 0 else Decimal("Infinity")
    zert = (vorher["zertifikate_wert"] + (neuwert if plan.ist_zertifikat else NULL)) / nav_nachher \
        if nav_nachher > 0 else Decimal("Infinity")
    exposure = (vorher["exposure_eur"] + neuwert * plan.hebel) / nav_nachher \
        if nav_nachher > 0 else Decimal("Infinity")
    cashquote = cash_nachher / nav_nachher if nav_nachher > 0 else NULL

    verlust_rel = relativer_verlust_bis_stop(plan)
    risiko_eur = plan.einsatz * verlust_rel + 2 * gebuehr + plan.einsatz * spread_satz
    risiko_quote = risiko_eur / nav_vorher if nav_vorher > 0 else Decimal("Infinity")
    risiko_grenze = limits["max_risiko_trade"] / (2 if stufe >= 1 else 1)

    if cash_nachher < 0:
        verstoesse.append(Verstoss("Kein Kredit", "Cash nach Order >= 0,00 EUR", f"{g.geld(cash_nachher)} EUR"))
    if einzel > limits["max_einzelposition"]:
        verstoesse.append(Verstoss("Einzelposition", fmt_prozent(limits["max_einzelposition"]), fmt_prozent(einzel, True)))
    if zert > limits["max_anteil_zertifikate"]:
        verstoesse.append(Verstoss("Zertifikate-Anteil", fmt_prozent(limits["max_anteil_zertifikate"]),
                                   fmt_prozent(zert, True)))
    if exposure > limits["max_exposure"]:
        verstoesse.append(Verstoss("Gesamt-Exposure", fmt_faktor(limits["max_exposure"]), fmt_faktor(exposure, True)))
    if cashquote < limits["min_cashquote"]:
        verstoesse.append(Verstoss("Mindest-Cashquote", fmt_prozent(limits["min_cashquote"]), fmt_prozent(cashquote, False)))
    if risiko_quote > risiko_grenze:
        zusatz = " (Drawdown-Stufe 1: halbiert)" if stufe >= 1 else ""
        verstoesse.append(Verstoss("Risiko je Trade" + zusatz, fmt_prozent(risiko_grenze), fmt_prozent(risiko_quote, True)))

    kennzahlen = {
        "nav_vorher": g.geld(nav_vorher), "nav_nachher": g.geld(nav_nachher), "einsatz": plan.einsatz,
        "gebuehr": gebuehr, "spread_kauf": spread_kauf, "cash_nachher": g.geld(cash_nachher),
        "einzelposition": _r6(einzel), "zertifikate_anteil": _r6(zert),
        "exposure": _r6(exposure), "cashquote": _r6(cashquote), "hebel": _r6(plan.hebel),
        "verlust_bis_stop": _r6(verlust_rel), "risiko_eur": g.geld(risiko_eur),
        "risiko_quote": _r6(risiko_quote), "risiko_grenze": risiko_grenze, "drawdown_stufe": stufe,
        "zertifikat": plan.ist_zertifikat,
    }
    return verstoesse, kennzahlen


def _r6(wert) -> Decimal:
    return round(wert, 6) if D(wert).is_finite() else wert


def grenzen(profil: str) -> dict:
    return {k: g.text(v) for k, v in g.limits_fuer(profil).items()}


def kennzahlen_einhalten(kennzahlen: dict, grenzwerte: dict) -> list[str]:
    """Prüft protokollierte Kennzahlen gegen die protokollierten Grenzen (für pruefe.py)."""
    k = {s: D(v) if not isinstance(v, bool) else v for s, v in kennzahlen.items()}
    gw = {s: D(v) for s, v in grenzwerte.items()}
    fehler = []
    stufe = int(k["drawdown_stufe"])
    if k["einsatz"] < D(g.kosten()["mindestorder"]):
        fehler.append("Mindestorder")
    if k["einzelposition"] > gw["max_einzelposition"]:
        fehler.append("Einzelposition")
    if k["zertifikate_anteil"] > gw["max_anteil_zertifikate"]:
        fehler.append("Zertifikate-Anteil")
    if k["exposure"] > gw["max_exposure"]:
        fehler.append("Gesamt-Exposure")
    if k["cashquote"] < gw["min_cashquote"]:
        fehler.append("Mindest-Cashquote")
    if k["cash_nachher"] < 0:
        fehler.append("Kein Kredit")
    if k["risiko_quote"] > gw["max_risiko_trade"] / (2 if stufe >= 1 else 1):
        fehler.append("Risiko je Trade")
    if k["zertifikat"] and k["hebel"] > gw["max_hebel"]:
        fehler.append("Hebel je Zertifikat")
    if k["zertifikat"] and stufe >= 2:
        fehler.append("Drawdown-Stufe 2")
    return fehler


# --------------------------------------------------------------------------
# Aktueller Markt für Buchungen und Prüfungen


def aktueller_markt(portfolio: dict, zusaetzlich: list[str] = ()) -> tuple[Markt, dict]:
    """Fragt alle benötigten Kurse aktuell ab (protokolliert)."""
    tickers = []
    for ticker in [p["basiswert"] for p in portfolio["positionen"]] + list(zusaetzlich):
        if ticker not in tickers:
            tickers.append(ticker)
    abgefragt = {k.ticker: k for k in kurse.aktuell(tickers)} if tickers else {}
    eurusd = None
    if any(kurse.waehrung(t) == "USD" for t in tickers):
        fx = kurse.devisenkurs_aktuell()
        abgefragt[fx.ticker] = fx
        eurusd = fx.kurs
    markt = Markt(kurse={t: k.kurs for t, k in abgefragt.items()}, eurusd=eurusd, datum=g.heute())
    return markt, abgefragt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Geplante Kauforder gegen die Limits prüfen (ohne Buchung).")
    unter = parser.add_subparsers(dest="befehl", required=True)
    p = unter.add_parser("pruefen", help="Kauforder prüfen")
    p.add_argument("--profil", required=True, choices=g.profile())
    p.add_argument("--typ", required=True, choices=["aktie", "etf", "ko", "faktor"])
    p.add_argument("--richtung", default="long", choices=["long", "short"])
    p.add_argument("--ticker", help="Ticker bei Aktien und ETFs")
    p.add_argument("--basiswert", help="Basiswert bei Zertifikaten")
    p.add_argument("--einsatz", required=True, help="Einsatz in EUR (inkl. Spread, ohne Gebühr)")
    p.add_argument("--hebel", help="Zielhebel bei Knock-outs")
    p.add_argument("--faktor", help="Faktor bei Faktor-Zertifikaten")
    p.add_argument("--stop", default="keiner", help="Stop auf den Basiswert oder 'keiner'")
    p.add_argument("--kursziel", default="keiner", help="Kursziel auf den Basiswert oder 'keiner'")
    args = parser.parse_args(argv)
    try:
        portfolio = g.portfolio_laden(args.profil)
        basiswert = args.ticker if args.typ in g.AKTIEN else args.basiswert
        if not basiswert:
            raise Fehler("--ticker (Aktie/ETF) bzw. --basiswert (Zertifikat) fehlt.")
        markt, _ = aktueller_markt(portfolio, [basiswert])
        plan = kaufplan(args.typ, args.richtung, basiswert, D(args.einsatz), markt.kurs(basiswert),
                        hebel=args.hebel, faktor=args.faktor, stop=stop_lesen(args.stop),
                        kursziel=stop_lesen(args.kursziel), kauftag=g.heute())
        verstoesse, kennzahlen = pruefe_kauf(portfolio, plan, markt)
        for schluessel, wert in kennzahlen.items():
            print(f"{schluessel:<20} {g.text(wert) if not isinstance(wert, bool) else wert}")
        if verstoesse:
            print("\nABGELEHNT:")
            for v in verstoesse:
                print(f"- {v}")
            return 1
        print("\nAlle Limits eingehalten.")
    except Fehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
