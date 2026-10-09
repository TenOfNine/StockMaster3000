#!/usr/bin/env python3
"""Daueranweisung (Overnight-Zyklus, regeln.md Abschnitte 5, 6, 7 und 12).

Claude setzt in einer Session eine Daueranweisung für ein Profil mit Zyklus "naechtlich" (config/profile.json,
Profil Overnight): Instrumente mit Gewichten, Einsatz, Gültigkeit und Aussetzkriterien, mit Journal-ID wie bei jeder
Order. Der Hintergrunddienst führt sie ohne Claude-Lauf aus (tools/ausfuehrung.py):

- **Kauf zum Schlusskurs:** nach dem Handelsschluss der Börse, zum ersten protokollierten Kurs, dessen Quellzeit
  (Beginn der letzten Minutenkerze) höchstens zwei Minuten vor dem Schluss liegt (der Schlusskurs, soweit die Quelle ihn liefert; die Nachbuchung gleicht ihn mit der Tageskerze
  ab), nur während die Anweisung gültig und nicht ausgesetzt ist.
- **Verkauf zur Eröffnung:** am nächsten Handelstag zum ersten protokollierten Kurs nach der Eröffnung (innerhalb
  des Eröffnungsfensters); sonst verkauft die Nachbuchung zum Eröffnungskurs der Tageskerze.

Ohne gültige Anweisung geschieht nichts. Kosten, Spreads und Limits sind unverändert (tools/limits.py prüft jeden
Kauf). Jede Änderung der Anweisung steht im Protokoll data/daueranweisung/<profil>.jsonl (nur anhängen) und als
Trade-Zeile `aenderung` mit Journal-ID.

    python tools/daueranweisung.py setzen --profil overnight --journal-id J-... --gueltig-bis JJJJ-MM-TT
        --instrument etf:EUNL.DE:1.0 [--instrument ko:^GSPC:0.3:3] [--einsatz-anteil 0.97] [--stop-abstand 0.03]
        [--nur-lange-naechte] [--aussetzen-stufe 1] [--aussetzen-verluste 5] [--aussetzen-unter 800] [--nur-pruefen]
    python tools/daueranweisung.py beenden --profil overnight --journal-id J-... [--positionen-behalten]
    python tools/daueranweisung.py fortsetzen --profil overnight --journal-id J-...
    python tools/daueranweisung.py status [--profil overnight]
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

import buchen
import gemeinsam as g
import kurse
import limits
from gemeinsam import D, Fehler

EINS = Decimal("1")
PLAN_MUSTER = re.compile(r"Daueranweisung\)?:? (D-\d{4})")
INSTRUMENT_TYPEN = ("etf", "aktie", "ko")
STANDARD = {"max_tage": 90, "max_instrumente": 3, "schluss_abstand_minuten": 5, "schluss_fenster_minuten": 90,
            "schluss_toleranz_minuten": 2}


def einstellungen() -> dict:
    return {**STANDARD, **g.projekt().get("daueranweisung", {})}


def zyklus_profile() -> dict[str, str]:
    """Profile mit Daueranweisung und ihr Zyklus (config/profile.json)."""
    return dict(g.config("profile").get("daueranweisung", {}))


def plan_aktiv(portfolio: dict) -> dict | None:
    plan = portfolio.get("daueranweisung")
    return plan if plan and plan.get("status") == "aktiv" else None


def protokoll_pfad(profil: str):
    return g.pfad("data", "daueranweisung", f"{profil}.jsonl")


def protokollieren(profil: str, plan_id: str, ereignis: str, text: str, **zusatz) -> None:
    zeile = {"zeit": g.iso(g.jetzt()), "plan": plan_id, "ereignis": ereignis, "text": text, **zusatz}
    g.text_anhaengen(protokoll_pfad(profil), json.dumps(zeile, ensure_ascii=False, default=str) + "\n")


def protokoll_lesen(profil: str) -> list[dict]:
    datei = protokoll_pfad(profil)
    if not datei.exists():
        return []
    return [json.loads(z) for z in datei.read_text(encoding="utf-8").splitlines() if z.strip()]


def plan_historie(profil: str) -> dict[str, dict]:
    """Plan-ID -> Ereignis `gesetzt` (Zeit, Journal-ID, gültig bis) aus dem Protokoll."""
    return {z["plan"]: z for z in protokoll_lesen(profil) if z["ereignis"] == "gesetzt"}


# --------------------------------------------------------------------------
# Eingaben


def instrument_lesen(text: str, stop_abstand: Decimal) -> dict:
    """`typ:ticker:gewicht[:hebel]`, z. B. `etf:EUNL.DE:1.0` oder `ko:^GSPC:0.3:3`."""
    teile = text.split(":")
    if len(teile) not in (3, 4) or teile[0] not in INSTRUMENT_TYPEN:
        raise Fehler(f"Instrument '{text}': erwartet typ:ticker:gewicht[:hebel] mit typ aus {', '.join(INSTRUMENT_TYPEN)}.")
    typ, ticker = teile[0], teile[1]
    gewicht = D(teile[2])
    if gewicht is None or not (Decimal("0") < gewicht <= EINS):
        raise Fehler(f"Instrument '{text}': Gewicht muss größer 0 und höchstens 1 sein.")
    hebel = teile[3] if len(teile) == 4 else None
    if typ == "ko" and not hebel:
        raise Fehler(f"Instrument '{text}': Knock-out braucht einen Hebel (typ:basiswert:gewicht:hebel).")
    if typ != "ko" and hebel:
        raise Fehler(f"Instrument '{text}': nur Knock-out-Zertifikate haben einen Hebel.")
    return {"typ": typ, "ticker": ticker, "richtung": "long", "gewicht": g.text(gewicht), "hebel": hebel,
            "stop_abstand": g.text(stop_abstand)}


def plan_aus_argumenten(args, profil: str) -> dict:
    heute = g.heute()
    einst = einstellungen()
    bis = g.datum_lesen(args.gueltig_bis)
    if bis < heute:
        raise Fehler(f"--gueltig-bis {bis} liegt vor heute ({heute}).")
    if bis > heute + timedelta(days=int(einst["max_tage"])):
        raise Fehler(f"Eine Daueranweisung gilt höchstens {einst['max_tage']} Tage (bis {heute + timedelta(days=int(einst['max_tage']))}); "
                     "danach braucht sie eine neue, dokumentierte Entscheidung.")
    stop_abstand = D(args.stop_abstand)
    if not (Decimal("0") < stop_abstand < Decimal("0.5")):
        raise Fehler("--stop-abstand muss zwischen 0 und 0,5 liegen (Anteil unter dem Kaufkurs).")
    instrumente = [instrument_lesen(t, stop_abstand) for t in args.instrument]
    if not 1 <= len(instrumente) <= int(einst["max_instrumente"]):
        raise Fehler(f"Eine Daueranweisung braucht 1 bis {einst['max_instrumente']} Instrumente.")
    if sum(D(i["gewicht"]) for i in instrumente) > EINS:
        raise Fehler("Die Gewichte der Instrumente ergeben zusammen mehr als 1.")
    anteil = D(args.einsatz_anteil)
    if not (Decimal("0") < anteil <= EINS):
        raise Fehler("--einsatz-anteil muss größer 0 und höchstens 1 sein.")
    return {
        "id": None, "profil": profil, "journal_id": args.journal_id, "gueltig_bis": bis.isoformat(),
        "instrumente": instrumente, "einsatz_anteil": g.text(anteil), "nur_lange_naechte": bool(args.nur_lange_naechte),
        "aussetzen": {"ab_drawdown_stufe": int(args.aussetzen_stufe), "nach_verlustnaechten": int(args.aussetzen_verluste),
                      "unter_portfoliowert": g.text(g.geld(args.aussetzen_unter)) if args.aussetzen_unter else None},
        "status": "aktiv", "status_grund": "", "naechte": 0, "verlustnaechte_in_folge": 0, "ergebnis_eur": "0.00",
        "letzter_kauf": {}, "zyklen": [],
    }


# --------------------------------------------------------------------------
# Kauf zum Schlusskurs


def _tickers(plan: dict) -> list[str]:
    return [i["ticker"] for i in plan["instrumente"]]


def schlussfenster(ticker: str, jetzt: datetime) -> tuple[datetime, datetime] | None:
    """Fenster, in dem der Kauf zum Schlusskurs möglich ist: (Schluss plus Abstand, Schluss plus Fenster)."""
    tag = kurse.boersentag(ticker, jetzt)
    if not kurse.ist_handelstag(ticker, tag):
        return None
    einst = einstellungen()
    schluss = kurse.schluss(ticker, tag)
    return (schluss + timedelta(minutes=int(einst["schluss_abstand_minuten"])),
            schluss + timedelta(minutes=int(einst["schluss_fenster_minuten"])))


def kauf_zu_planen(plan: dict, instrument: dict, jetzt: datetime) -> str:
    """Leer, wenn der Kauf jetzt fällig ist, sonst der Grund (nur zur Anzeige und für das Protokoll)."""
    ticker = instrument["ticker"]
    fenster = schlussfenster(ticker, jetzt)
    if fenster is None:
        return "kein Handelstag"
    if jetzt < fenster[0]:
        return "vor dem Schlusskurs"
    if jetzt > fenster[1]:
        return "Schlussfenster vorbei"
    tag = kurse.boersentag(ticker, jetzt)
    if g.zeit_lesen(plan["erfasst"]) > kurse.schluss(ticker, tag):
        return "nach dem Schlusskurs erfasst (eine Anweisung gilt erst ab ihrer Erfassung)"
    if plan["letzter_kauf"].get(ticker) == tag.isoformat():
        return "heute schon gekauft"
    if tag > date.fromisoformat(plan["gueltig_bis"]):
        return "Gültigkeit abgelaufen"
    if plan["nur_lange_naechte"] and (kurse.naechster_handelstag(ticker, tag) - tag).days < 3:
        return "kurze Nacht (nur lange Nächte)"
    return ""


def kurs_ist_schlusskurs(ticker: str, jetzt: datetime, kurs_zeit: datetime) -> bool:
    """Liefert die Quelle den Kurs des Handelsschlusses? Die Quellzeit ist bei Minutenkerzen der Beginn der letzten
    Minute, deshalb gilt sie ab zwei Minuten vor dem Schluss (Einstellung `schluss_toleranz_minuten`)."""
    tag = kurse.boersentag(ticker, jetzt)
    toleranz = timedelta(minutes=int(einstellungen()["schluss_toleranz_minuten"]))
    return kurs_zeit >= kurse.schluss(ticker, tag) - toleranz


def bedarf(portfolio: dict, jetzt: datetime) -> set[str]:
    """Ticker, deren Kurse die Daueranweisung jetzt braucht (Kauf im Schlussfenster)."""
    plan = plan_aktiv(portfolio)
    if plan is None:
        return set()
    faellig = {i["ticker"] for i in plan["instrumente"] if kauf_zu_planen(plan, i, jetzt) == ""}
    return faellig


def aussetzgrund(portfolio: dict, plan: dict, nav) -> str:
    """Grund, die Anweisung auszusetzen (leer: weiter), nach den Kriterien der Anweisung und den Portfolio-Regeln."""
    kriterien = plan["aussetzen"]
    if portfolio.get("status") != "aktiv":
        return f"Portfolio {portfolio.get('status')}"
    stufe = int(portfolio.get("drawdown_stufe", 0))
    if stufe >= int(kriterien["ab_drawdown_stufe"]):
        return f"Drawdown-Stufe {stufe} (Kriterium: ab Stufe {kriterien['ab_drawdown_stufe']})"
    if kriterien["nach_verlustnaechten"] and plan["verlustnaechte_in_folge"] >= int(kriterien["nach_verlustnaechten"]):
        return (f"{plan['verlustnaechte_in_folge']} Verlustnächte in Folge "
                f"(Kriterium: {kriterien['nach_verlustnaechten']})")
    if kriterien["unter_portfoliowert"] and nav < D(kriterien["unter_portfoliowert"]):
        return f"Portfoliowert {g.geld(nav)} EUR unter {kriterien['unter_portfoliowert']} EUR"
    return ""


def abrechnen(portfolio: dict, plan: dict, ungebucht: list[dict] | tuple = ()) -> list[str]:
    """Rechnet beendete Zyklen (alle Positionen der Nacht verkauft oder ausgebucht) aus trades/ ab.

    Das Nachtergebnis (Summe der Beträge inklusive Gebühren) zählt Nächte und Verlustnächte in Folge. Es kommt aus den
    Trade-Zeilen, damit jeder Verkaufsweg (Eröffnung, Stop, Knock-out, Nachbuchung) gleich zählt. `ungebucht` sind die
    Zeilen des laufenden Buchungslaufs, die noch nicht in trades/ stehen.
    """
    offen = {p["id"] for p in portfolio["positionen"]}
    zeilen = None
    meldungen = []
    for zyklus in plan["zyklen"]:
        if zyklus["abgerechnet"] or any(pid in offen for pid in zyklus["positionen"]):
            continue
        if zeilen is None:
            zeilen = g.trades_lesen(portfolio["profil"]) + list(ungebucht)
        ergebnis = sum((D(z["betrag_eur"] or 0) for z in zeilen if z["position_id"] in zyklus["positionen"]
                        and z["aktion"] in ("kauf", "verkauf", "knockout")), Decimal("0"))
        zyklus.update(abgerechnet=True, ergebnis=g.text(g.geld(ergebnis)))
        plan["naechte"] += 1
        plan["verlustnaechte_in_folge"] = plan["verlustnaechte_in_folge"] + 1 if ergebnis < 0 else 0
        plan["ergebnis_eur"] = g.text(g.geld(D(plan["ergebnis_eur"]) + ergebnis))
        meldungen.append(f"{portfolio['profil']}: Nacht {zyklus['datum']} abgerechnet, Ergebnis {g.geld(ergebnis)} EUR "
                         f"(Verlustnächte in Folge: {plan['verlustnaechte_in_folge']}).")
        protokollieren(portfolio["profil"], plan["id"], "nacht", meldungen[-1], datum=zyklus["datum"],
                       ergebnis=g.text(g.geld(ergebnis)))
    return meldungen


def aussetzen(portfolio: dict, plan: dict, grund: str, meldungen: list[str] | None = None) -> None:
    plan["status"], plan["status_grund"] = "ausgesetzt", grund
    protokollieren(portfolio["profil"], plan["id"], "ausgesetzt", grund)
    if meldungen is not None:
        meldungen.append(f"{portfolio['profil']}: Daueranweisung {plan['id']} ausgesetzt: {grund}")


def kaeufe_planen(portfolio: dict, plan: dict, markt: limits.Markt, instrumente: list[dict], kurse_je_ticker: dict,
                  jetzt: datetime) -> list[dict]:
    """Berechnet die Käufe einer Nacht nacheinander (jeder Kauf ändert Cash, Positionen und Limits des nächsten).

    Arbeitet auf einer Kopie des Portfolios; gibt je Instrument Kaufplan, Verstöße und Kennzahlen zurück. Die
    Ausführung nutzt dieselbe Rechnung (Rechnen macht Code, ein Pfad für Prüfung und Buchung).
    """
    kopie = copy.deepcopy(portfolio)
    lauf = g.Buchungslauf(kopie)
    bewertet = limits.portfolio_bewerten(kopie, markt)
    nav = bewertet["nav"]
    anteil = D(plan["einsatz_anteil"])
    ergebnisse = []
    for instrument in instrumente:
        kurs = kurse_je_ticker[instrument["ticker"]].kurs
        stop = g.param(kurs * (EINS - D(instrument["stop_abstand"])))
        einsatz = g.geld(nav * anteil * D(instrument["gewicht"]))
        plan_kauf = limits.kaufplan(instrument["typ"], instrument["richtung"], instrument["ticker"], einsatz, kurs,
                                    hebel=instrument["hebel"], faktor=None, stop=stop, kursziel=None, kauftag=jetzt.date())
        verstoesse, kennzahlen = limits.pruefe_kauf(kopie, plan_kauf, markt)
        ergebnis = {"instrument": instrument, "plan": plan_kauf, "verstoesse": verstoesse, "kennzahlen": kennzahlen,
                    "einsatz": einsatz}
        ergebnisse.append(ergebnis)
        if not verstoesse:  # nur zulässige Käufe verändern den Zustand für die folgenden
            order = {"id": "O-trocken", "journal_id": plan["journal_id"]}
            buchen.kauf_ausfuehren(lauf, order, plan_kauf, markt, jetzt, "kurse", g.iso(jetzt), kennzahlen)
    return ergebnisse


def kauf_ausfuehren(lauf: g.Buchungslauf, plan: dict, ergebnis: dict, markt: limits.Markt, q: kurse.Kurs) -> dict:
    """Bucht einen geprüften Kauf der Nacht zum protokollierten Schlusskurs und markiert die Position."""
    portfolio = lauf.portfolio
    instrument = ergebnis["instrument"]
    order = {"id": g.naechste_id(portfolio, "order"), "journal_id": plan["journal_id"]}
    tag = kurse.boersentag(instrument["ticker"], q.zeit)
    zusatz = g.automatisch_text("Daueranweisung", f"{plan['id']} Kauf zum Schlusskurs {q.kurs} "
                                                  f"(Quellzeit {q.kurs_zeit:%H:%M}) für die Nacht auf "
                                                  f"{kurse.naechster_handelstag(instrument['ticker'], tag):%d.%m.}")
    position = buchen.kauf_ausfuehren(lauf, order, ergebnis["plan"], markt, q.zeit, "kurse", g.iso(q.zeit),
                                      ergebnis["kennzahlen"], zusatz=zusatz)
    position["daueranweisung"] = plan["id"]
    position["zyklus"] = tag.isoformat()
    plan["letzter_kauf"][instrument["ticker"]] = tag.isoformat()
    zyklus = next((z for z in plan["zyklen"] if z["datum"] == tag.isoformat() and not z["abgerechnet"]), None)
    if zyklus is None:
        zyklus = {"datum": tag.isoformat(), "positionen": [], "abgerechnet": False, "ergebnis": None}
        plan["zyklen"].append(zyklus)
    zyklus["positionen"].append(position["id"])
    protokollieren(portfolio["profil"], plan["id"], "kauf", zusatz, position=position["id"], order=order["id"])
    return position


# --------------------------------------------------------------------------
# Verkauf zur Eröffnung


def verkauf_faellig(position: dict, jetzt: datetime) -> bool:
    """Positionen einer Daueranweisung werden am nächsten Handelstag zur Eröffnung verkauft."""
    if not position.get("daueranweisung"):
        return False
    ticker = position["basiswert"]
    tag = kurse.boersentag(ticker, jetzt)
    if not kurse.ist_handelstag(ticker, tag) or not kurse.markt_offen(ticker, jetzt):
        return False
    return g.zeit_lesen(position["eroeffnet"]) < kurse.oeffnung(ticker, tag)


def verkauf_zusatz(position: dict, q: kurse.Kurs) -> str:
    oeffnung = kurse.oeffnung(position["basiswert"], kurse.boersentag(position["basiswert"], q.zeit))
    return g.automatisch_text("Daueranweisung", f"{position['daueranweisung']} Verkauf zur Eröffnung: erster Kurs {q.kurs} "
                                                f"({q.kurs_zeit:%H:%M}) nach Eröffnung {oeffnung:%H:%M}")


# --------------------------------------------------------------------------
# Befehle


def _session_pruefen(profil: str, journal_id: str, eindeutig: bool) -> dict:
    if profil not in zyklus_profile():
        raise Fehler(f"Das Profil '{profil}' hat keine Daueranweisung (Profile mit Zyklus: "
                     f"{', '.join(zyklus_profile()) or 'keine'}).")
    portfolio = buchen.portfolio_pruefen(profil)
    buchen.journal_pruefen(journal_id, profil, eindeutig=eindeutig)
    return portfolio


@g.mit_buchungssperre
def setzen(args) -> list[str]:
    portfolio = _session_pruefen(args.profil, args.journal_id, eindeutig=True)
    plan = plan_aus_argumenten(args, args.profil)
    tickers = _tickers(plan)
    markt, abgefragt = limits.aktueller_markt(portfolio, tickers)
    # Trockenlauf: Käufe auf einem Portfolio ohne Positionen, so wie es nach dem Verkauf zur Eröffnung aussieht.
    leer = copy.deepcopy(portfolio)
    leer["positionen"] = []
    markt_leer = limits.Markt(kurse={t: markt.kurse[t] for t in tickers}, eurusd=markt.eurusd, datum=markt.datum)
    jetzt = g.jetzt()
    ergebnisse = kaeufe_planen(leer, plan, markt_leer, plan["instrumente"], {t: abgefragt[t] for t in tickers}, jetzt)
    fehler = [f"{e['instrument']['typ']}:{e['instrument']['ticker']} (Einsatz {e['einsatz']} EUR): {v}"
              for e in ergebnisse for v in e["verstoesse"]]
    if fehler:
        raise buchen.Abgelehnt(fehler)
    zeilen = [f"{e['instrument']['typ']}:{e['instrument']['ticker']}: Einsatz {e['einsatz']} EUR, Risiko je Trade "
              f"{limits.fmt_prozent(e['kennzahlen']['risiko_quote'], True)} (Grenze "
              f"{limits.fmt_prozent(e['kennzahlen']['risiko_grenze'])}), Einzelposition "
              f"{limits.fmt_prozent(e['kennzahlen']['einzelposition'], True)}" for e in ergebnisse]
    if args.nur_pruefen:
        return ["Trockenlauf bestanden (alle Limits bei den heutigen Kursen eingehalten):"] + zeilen
    alt = portfolio.get("daueranweisung")
    meldungen = []
    lauf = g.Buchungslauf(portfolio)
    if alt and alt["status"] in ("aktiv", "ausgesetzt"):
        alt["status"], alt["status_grund"] = "ersetzt", f"ersetzt durch eine neue Anweisung ({args.journal_id})"
        protokollieren(args.profil, alt["id"], "beendet", alt["status_grund"])
        meldungen.append(f"{args.profil}: Daueranweisung {alt['id']} ersetzt.")
    plan["id"] = g.naechste_id(portfolio, "plan")
    plan["erfasst"] = g.iso(jetzt)
    plan["person"] = g.aktive_sperre()["person"]
    plan["zyklen"] = alt["zyklen"] if alt and alt.get("zyklen") else []  # offene Nächte der alten Anweisung bleiben im Blick
    for zyklus in plan["zyklen"]:
        zyklus["plan_alt"] = zyklus.get("plan_alt") or alt["id"]
    portfolio["daueranweisung"] = plan
    beschreibung = (f"Daueranweisung {plan['id']} gesetzt: {', '.join(args.instrument)}, Einsatz "
                    f"{plan['einsatz_anteil']} des Portfoliowerts, gültig bis {plan['gueltig_bis']}"
                    + (", nur lange Nächte" if plan["nur_lange_naechte"] else "")
                    + f"; aussetzen ab Stufe {plan['aussetzen']['ab_drawdown_stufe']}, nach "
                      f"{plan['aussetzen']['nach_verlustnaechten']} Verlustnächten"
                    + (f", unter {plan['aussetzen']['unter_portfoliowert']} EUR" if plan["aussetzen"]["unter_portfoliowert"] else ""))
    lauf.trade(zeit=jetzt, aktion="aenderung", journal_id=args.journal_id, grund="order", bemerkung=beschreibung)
    lauf.meldungen.append(f"{args.profil}: {beschreibung}")
    protokollieren(args.profil, plan["id"], "gesetzt", beschreibung, journal_id=args.journal_id,
                   gueltig_bis=plan["gueltig_bis"], erfasst=plan["erfasst"], instrumente=plan["instrumente"])
    lauf.speichern()
    return meldungen + lauf.meldungen + ["Trockenlauf bestanden:"] + zeilen


@g.mit_buchungssperre
def beenden(args) -> list[str]:
    portfolio = _session_pruefen(args.profil, args.journal_id, eindeutig=False)
    plan = portfolio.get("daueranweisung")
    if not plan or plan["status"] not in ("aktiv", "ausgesetzt"):
        raise Fehler(f"Im Portfolio {args.profil} gibt es keine laufende Daueranweisung.")
    plan["status"], plan["status_grund"] = "beendet", f"beendet mit {args.journal_id}"
    meldungen = []
    if args.positionen_behalten:
        for position in portfolio["positionen"]:
            if position.get("daueranweisung") == plan["id"]:
                position.pop("daueranweisung")
                meldungen.append(f"{args.profil}: {position['id']} bleibt im Bestand (nicht mehr automatisch verkauft).")
    text = f"Daueranweisung {plan['id']} beendet" + ("; Positionen bleiben im Bestand" if args.positionen_behalten else
                                                       "; offene Positionen werden zur nächsten Eröffnung verkauft")
    lauf = g.Buchungslauf(portfolio)
    lauf.trade(zeit=g.jetzt(), aktion="storno", journal_id=args.journal_id, grund="order", bemerkung=text)
    lauf.meldungen.append(f"{args.profil}: {text}.")
    protokollieren(args.profil, plan["id"], "beendet", text, journal_id=args.journal_id)
    lauf.speichern()
    return meldungen + lauf.meldungen


@g.mit_buchungssperre
def fortsetzen(args) -> list[str]:
    portfolio = _session_pruefen(args.profil, args.journal_id, eindeutig=False)
    plan = portfolio.get("daueranweisung")
    if not plan or plan["status"] != "ausgesetzt":
        raise Fehler(f"Im Portfolio {args.profil} gibt es keine ausgesetzte Daueranweisung.")
    if date.fromisoformat(plan["gueltig_bis"]) < g.heute():
        raise Fehler("Die Gültigkeit ist abgelaufen; eine neue Anweisung setzen.")
    bewertet = limits.portfolio_bewerten(portfolio, limits.aktueller_markt(portfolio)[0])
    grund = aussetzgrund(portfolio, {**plan, "verlustnaechte_in_folge": 0}, bewertet["nav"])
    if grund:
        raise Fehler(f"Fortsetzen nicht möglich, das Kriterium gilt weiter: {grund}.")
    plan["status"], plan["status_grund"], plan["verlustnaechte_in_folge"] = "aktiv", "", 0
    text = f"Daueranweisung {plan['id']} fortgesetzt ({args.journal_id}); Verlustserie zurückgesetzt"
    lauf = g.Buchungslauf(portfolio)
    lauf.trade(zeit=g.jetzt(), aktion="aenderung", journal_id=args.journal_id, grund="order", bemerkung=text)
    lauf.meldungen.append(f"{args.profil}: {text}.")
    protokollieren(args.profil, plan["id"], "fortgesetzt", text, journal_id=args.journal_id)
    lauf.speichern()
    return lauf.meldungen


def status(profil: str | None = None) -> list[dict]:
    ergebnis = []
    for p in zyklus_profile():
        if profil and p != profil or not g.portfolio_pfad(p).exists():
            continue
        portfolio = g.portfolio_laden(p)
        plan = portfolio.get("daueranweisung")
        ergebnis.append({"profil": p, "plan": plan, "positionen": [
            {"id": x["id"], "ticker": x["ticker"], "eroeffnet": x["eroeffnet"], "plan": x.get("daueranweisung")}
            for x in portfolio["positionen"] if x.get("daueranweisung")]})
    return ergebnis


def parser_bauen() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Daueranweisung (Overnight-Zyklus) setzen, beenden, fortsetzen, anzeigen.")
    unter = parser.add_subparsers(dest="befehl", required=True)
    p = unter.add_parser("setzen", help="Daueranweisung setzen (ersetzt eine laufende)")
    p.add_argument("--profil", required=True, choices=sorted(zyklus_profile()) or None)
    p.add_argument("--journal-id", required=True)
    p.add_argument("--gueltig-bis", required=True, help="letzter Tag des Kaufs zum Schlusskurs, JJJJ-MM-TT")
    p.add_argument("--instrument", action="append", required=True, help="typ:ticker:gewicht[:hebel], mehrfach")
    p.add_argument("--einsatz-anteil", default="0.97", help="Anteil des Portfoliowerts je Nacht (Standard 0,97)")
    p.add_argument("--stop-abstand", default="0.03", help="Stop unter dem Kaufkurs als Anteil (Standard 0,03)")
    p.add_argument("--nur-lange-naechte", action="store_true", help="nur vor Wochenende und Feiertagen kaufen")
    p.add_argument("--aussetzen-stufe", default="1", help="aussetzen ab dieser Drawdown-Stufe (Standard 1)")
    p.add_argument("--aussetzen-verluste", default="5", help="aussetzen nach so vielen Verlustnächten in Folge (0: nie)")
    p.add_argument("--aussetzen-unter", help="aussetzen, wenn der Portfoliowert unter diesen Betrag fällt (EUR)")
    p.add_argument("--nur-pruefen", action="store_true", help="Trockenlauf: Limits mit den heutigen Kursen prüfen")
    p = unter.add_parser("beenden", help="Daueranweisung beenden")
    p.add_argument("--profil", required=True, choices=sorted(zyklus_profile()) or None)
    p.add_argument("--journal-id", required=True)
    p.add_argument("--positionen-behalten", action="store_true",
                   help="offene Positionen nicht zur nächsten Eröffnung verkaufen")
    p = unter.add_parser("fortsetzen", help="ausgesetzte Daueranweisung fortsetzen")
    p.add_argument("--profil", required=True, choices=sorted(zyklus_profile()) or None)
    p.add_argument("--journal-id", required=True)
    p = unter.add_parser("status", help="Stand der Daueranweisung (JSON)")
    p.add_argument("--profil")
    return parser


def main(argv=None) -> int:
    args = parser_bauen().parse_args(argv)
    try:
        if args.befehl == "status":
            print(json.dumps(status(args.profil), ensure_ascii=False, indent=2, default=str))
            return 0
        meldungen = {"setzen": setzen, "beenden": beenden, "fortsetzen": fortsetzen}[args.befehl](args)
        for meldung in meldungen:
            print(meldung)
    except buchen.Abgelehnt as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Fehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
