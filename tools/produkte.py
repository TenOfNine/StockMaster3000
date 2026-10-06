#!/usr/bin/env python3
"""Synthetische Zertifikate nach regeln.md Abschnitt 4.

Alle Werte sind in der Währung des Basiswerts; die Umrechnung in EUR erfolgt
beim Aufrufer über EURUSD=X. Reine Rechenfunktionen ohne Dateizugriff.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from decimal import Decimal

import gemeinsam as g
from gemeinsam import D, Fehler

EINS = Decimal("1")
NULL = Decimal("0")


def _tagessatz(schluessel: str) -> Decimal:
    kosten = g.kosten()
    return D(kosten[schluessel]) / D(kosten["tage_je_jahr"])


def _pruefe_richtung(richtung: str) -> None:
    if richtung not in ("long", "short"):
        raise Fehler(f"Richtung '{richtung}' unbekannt (long oder short).")


# --------------------------------------------------------------------------
# Knock-out


def ko_basispreis(richtung: str, kurs, hebel) -> Decimal:
    """Basispreis beim Kauf: Long K = S*(1-1/L), Short K = S*(1+1/L); Barriere = K."""
    _pruefe_richtung(richtung)
    kurs, hebel = D(kurs), D(hebel)
    if hebel <= EINS:
        raise Fehler("Der Hebel eines Knock-outs muss größer als 1 sein.")
    if richtung == "long":
        return g.param(kurs * (EINS - EINS / hebel))
    return g.param(kurs * (EINS + EINS / hebel))


def ko_aufzinsen(richtung: str, basispreis, kalendertage: int = 1) -> Decimal:
    """Long: K * (1 + 0,04/365) je Kalendertag; Short: K bleibt konstant."""
    _pruefe_richtung(richtung)
    satz = _tagessatz("ko_long_aufzinsung_pa" if richtung == "long" else "ko_short_aufzinsung_pa")
    return g.param(D(basispreis) * (EINS + satz) ** int(kalendertage))


def ko_wert(richtung: str, kurs, basispreis) -> Decimal:
    """Wert je Stück: Long S - K, Short K - S, nie negativ."""
    _pruefe_richtung(richtung)
    differenz = D(kurs) - D(basispreis) if richtung == "long" else D(basispreis) - D(kurs)
    return max(NULL, differenz)


def ko_ausgeknockt(richtung: str, barriere, tief, hoch) -> bool:
    """Long: Tagestief <= Barriere; Short: Tageshoch >= Barriere."""
    _pruefe_richtung(richtung)
    if richtung == "long":
        return D(tief) <= D(barriere)
    return D(hoch) >= D(barriere)


def ko_hebel(richtung: str, kurs, basispreis) -> Decimal | None:
    """Hebel S/(S-K) bzw. S/(K-S); None, wenn ausgeknockt."""
    wert = ko_wert(richtung, kurs, basispreis)
    if wert <= 0:
        return None
    return D(kurs) / wert


# --------------------------------------------------------------------------
# Faktor


def faktor_fortschreiben(richtung: str, faktor, wert, kurs_alt, kurs_neu, kostentage: int = 1) -> Decimal:
    """V_t = V_(t-1) * max(0, 1 + F*R - 0,02/365 * Tage), Short mit -F.

    Konservative Auslegung (regeln.md 4 nennt nur den Tagesschritt): die
    Kosten von 0,02/365 fallen je Kalendertag an, über ein Wochenende also
    dreifach. Siehe STATUS.md, Entscheidungen.
    """
    _pruefe_richtung(richtung)
    f = D(faktor) if richtung == "long" else -D(faktor)
    rendite = D(kurs_neu) / D(kurs_alt) - EINS
    kosten = _tagessatz("faktor_kosten_pa") * int(kostentage)
    return g.param(D(wert) * max(NULL, EINS + f * rendite - kosten))


# --------------------------------------------------------------------------
# Ausgabe, Bewertung, Hebel einer Position


def ausgabe(typ: str, richtung: str, kurs, hebel=None, faktor=None, kauftag: date | None = None) -> tuple[Decimal, dict]:
    """Wert je Stück (Basiswertwährung) und Parameter beim Kauf."""
    kurs = D(kurs)
    if typ in g.AKTIEN:
        if richtung != "long":
            raise Fehler("Aktien und ETFs nur Long (kein Direkt-Leerverkauf).")
        return kurs, {}
    if typ == "ko":
        if hebel is None:
            raise Fehler("Für Knock-outs ist --hebel erforderlich.")
        basispreis = ko_basispreis(richtung, kurs, hebel)
        return ko_wert(richtung, kurs, basispreis), {
            "basispreis": basispreis, "barriere": basispreis, "hebel_kauf": D(hebel),
            "kurs_kauf": kurs}
    if typ == "faktor":
        if faktor is None:
            raise Fehler("Für Faktor-Zertifikate ist --faktor erforderlich.")
        _pruefe_richtung(richtung)
        if D(faktor) < 1:
            raise Fehler("Der Faktor muss mindestens 1 sein.")
        startwert = D(g.kosten()["faktor_startwert"])
        stand = (kauftag - timedelta(days=1)).isoformat() if kauftag else None
        return startwert, {"faktor": D(faktor), "wert_je_stueck": startwert, "kurs_ref": kurs,
                           "stand": stand}
    raise Fehler(f"Unbekannter Typ '{typ}' (aktie, etf, ko, faktor).")


def wert_je_stueck(position: dict, kurs, datum: date | None = None) -> Decimal:
    """Aktueller Wert je Stück (Basiswertwährung) zum Basiswertkurs.

    Faktor: Fortschreibung vom letzten Stand bis zum Kurs; Kosten für
    Kalendertage nach dem letzten Stand, aber ohne den laufenden Tag.
    """
    typ = position["typ"]
    kurs = D(kurs)
    if typ in g.AKTIEN:
        return kurs
    parameter = position["parameter"]
    if typ == "ko":
        return ko_wert(position["richtung"], kurs, parameter["basispreis"])
    if typ == "faktor":
        kostentage = 0
        if datum is not None and parameter.get("stand"):
            kostentage = max(0, (datum - timedelta(days=1) - date.fromisoformat(parameter["stand"])).days)
        return faktor_fortschreiben(position["richtung"], parameter["faktor"], parameter["wert_je_stueck"],
                                    parameter["kurs_ref"], kurs, kostentage)
    raise Fehler(f"Unbekannter Typ '{typ}'.")


def hebel(position: dict, kurs) -> Decimal:
    """Aktueller Hebel einer Position (Aktien/ETF 1, Faktor F, Knock-out S/(S-K))."""
    typ = position["typ"]
    if typ in g.AKTIEN:
        return EINS
    parameter = position["parameter"]
    if typ == "faktor":
        return D(parameter["faktor"])
    wert = ko_hebel(position["richtung"], kurs, parameter["basispreis"])
    return wert if wert is not None else NULL


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Rechner für synthetische Zertifikate (nur Anzeige).")
    unter = parser.add_subparsers(dest="befehl", required=True)
    p_ko = unter.add_parser("ko", help="Knock-out berechnen")
    p_ko.add_argument("--richtung", choices=["long", "short"], required=True)
    p_ko.add_argument("--kurs", required=True, help="Basiswertkurs")
    p_ko.add_argument("--hebel", required=True, help="Zielhebel beim Kauf")
    p_f = unter.add_parser("faktor", help="Faktor-Wert fortschreiben")
    p_f.add_argument("--richtung", choices=["long", "short"], required=True)
    p_f.add_argument("--faktor", required=True)
    p_f.add_argument("--wert", default="100")
    p_f.add_argument("--kurse", nargs="+", required=True, help="Schlusskurse des Basiswerts")
    args = parser.parse_args(argv)
    try:
        if args.befehl == "ko":
            k = ko_basispreis(args.richtung, args.kurs, args.hebel)
            print(f"Basispreis/Barriere: {k}  Wert je Stück: {ko_wert(args.richtung, args.kurs, k)}  "
                  f"Hebel: {ko_hebel(args.richtung, args.kurs, k):.4f}")
        else:
            wert = D(args.wert)
            for alt, neu in zip(args.kurse, args.kurse[1:]):
                wert = faktor_fortschreiben(args.richtung, args.faktor, wert, alt, neu)
                print(f"{alt} -> {neu}: {wert}")
    except Fehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
