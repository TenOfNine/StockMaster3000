#!/usr/bin/env python3
"""Schattenbuch (Strategie-Labor L2): was aus geprüften, aber nicht gekauften Kandidaten geworden wäre.

Im Session-Eintrag nennt die Zeile `- Verworfen: [<portfolio>:]<ticker>=<Grund>; …` die Kandidaten, die geprüft und
nicht gekauft wurden. Dieses Werkzeug hält den protokollierten Kurs zum Zeitpunkt des Eintrags fest (nur Kurse aus dem
Kursprotokoll, kein Backdating) und bewertet jeden Kandidaten nach 5, 20 und 60 Handelstagen (config/projekt.json,
`schattenbuch.horizonte`), als hätte man `schattenbuch.einsatz` EUR gekauft: Kauf zum Kurs plus halbem Spread, 1 EUR
Gebühr je Order, Verkauf zum Schlusskurs minus halbem Spread (config/kosten.json). Verglichen werden verworfene und
tatsächlich gekaufte Werte im selben Fenster und mit derselben Bewertung.

Das Schattenbuch bucht nie: es liest Journal und Kurse und schreibt nur data/schattenbuch.json.
Grenzen: Renditen in der Kurswährung (kein Devisenanteil), keine Dividenden, Kurslücke am Bewertungstag =
ungünstigerer Nachbarkurs (niedrigerer). Überlappende Fenster derselben Aktie zählen mehrfach.

    python tools/schattenbuch.py auswerten [--netz] [--json]
    python tools/schattenbuch.py liste
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from decimal import Decimal

import gemeinsam as g
import kurse
import prognosen
import zeitreihen
from gemeinsam import D, Fehler

VERWORFEN_EINTRAG = re.compile(r"^(?:(?P<profil>[a-zäöüß]+)\s*:\s*)?(?P<ticker>[^=\s:]+)\s*=\s*(?P<grund>.*)$", re.I)
MIN_AUSSAGE = 30


def ergebnis_pfad():
    return g.pfad("data", "schattenbuch.json")


def einstellungen() -> dict:
    return {"beginn": "9999-12-31", "einsatz": "100.00", "horizonte": [5, 20, 60], **g.projekt().get("schattenbuch", {})}


def verworfen_lesen(text: str) -> tuple[list[dict], list[str]]:
    """Liest die Verworfen-Zeile. Gibt (Kandidaten, Fehler) zurück; ungültige Teile gehen nur in die Fehlerliste."""
    kandidaten, fehler = [], []
    profile = set(g.profile())
    for teil in (text or "").split(";"):
        teil = teil.strip()
        if not teil or teil.lower() in ("keine", "-", "–"):
            continue
        treffer = VERWORFEN_EINTRAG.match(teil)
        if not treffer or not treffer.group("grund").strip():
            fehler.append(f"'{teil}' passt nicht zu [portfolio:]ticker=Grund")
            continue
        profil = (treffer.group("profil") or "").lower() or None
        if profil and profil not in profile:
            fehler.append(f"'{teil}': Portfolio {profil} unbekannt")
            continue
        ticker = treffer.group("ticker")
        try:
            kurse.boerse_von(ticker)
        except Fehler as exc:
            fehler.append(str(exc))
            continue
        kandidaten.append({"profil": profil, "ticker": ticker, "grund": treffer.group("grund").strip()})
    return kandidaten, fehler


def spread() -> Decimal:
    return D(g.kosten()["spread"]["aktie"])


def nettorendite(kauf: Decimal, verkauf: Decimal) -> float:
    """Rendite nach Kosten für `einsatz` EUR: Kauf zum Kurs + halber Spread, Verkauf zum Kurs - halber Spread, 2 Gebühren."""
    einsatz = D(einstellungen()["einsatz"])
    gebuehr = D(g.kosten()["gebuehr_je_order"])
    halb = spread() / 2
    stueck = (einsatz - gebuehr) / (kauf * (1 + halb))
    erloes = stueck * verkauf * (1 - halb) - gebuehr
    return float(erloes / einsatz - 1)


def bewerten(ticker: str, zeit, heute: date, netz: bool = False) -> dict:
    """Einstieg (protokollierter Kurs ab `zeit`) und Ergebnis je Horizont."""
    einstieg = zeitreihen.protokollkurs(ticker, zeit)
    if einstieg is None:
        return {"einstieg": None, "horizonte": {}, "status": "kein_kurs"}
    kurs, kurs_zeit = einstieg
    tag = kurs_zeit.astimezone(g.TZ).date()
    ergebnis = {"einstieg": {"kurs": float(kurs), "zeit": g.iso(kurs_zeit)}, "horizonte": {}, "status": "bewertet"}
    for n in einstellungen()["horizonte"]:
        ende = zeitreihen.handelstag_nach(ticker, tag, int(n))
        if ende >= heute:
            ergebnis["horizonte"][str(n)] = {"ende": ende.isoformat(), "status": "offen"}
            continue
        gefunden = zeitreihen.kurs_am(ticker, ende, None, netz)
        if gefunden is None:
            ergebnis["horizonte"][str(n)] = {"ende": ende.isoformat(), "status": "luecke"}
            continue
        ergebnis["horizonte"][str(n)] = {"ende": ende.isoformat(), "status": "bewertet", "kurs": float(gefunden[0]),
                                         "quelle": gefunden[1], "rendite": nettorendite(kurs, gefunden[0])}
    return ergebnis


def sammeln() -> tuple[list[dict], list[dict], list[dict]]:
    """(verworfen, gekauft, ungültig): Kandidaten aus Session-Einträgen ab `beginn`, Käufe aus Journal-Einträgen ab `beginn`."""
    beginn = einstellungen()["beginn"]
    verworfen, gekauft, ungueltig = [], [], []
    for block in g.journal_bloecke():
        if not block["zeit"] or (block["datum"] or "") < beginn:
            continue
        if block["art"] == "S":
            text = block["felder"].get("verworfen")
            if text is None:
                continue
            kandidaten, fehler = verworfen_lesen(text)
            for f in fehler:
                ungueltig.append({"id": block["id"], "fehler": f})
            for k in kandidaten:
                verworfen.append({"id": block["id"], "zeit": block["zeit"], **k})
        elif not prognosen.ausgenommen(block):
            ticker = None
            text = block["felder"].get("prognose")
            if text:
                p, _ = prognosen.block_lesen(text)
                ticker = p["ticker"] if p else None
            if ticker is None and re.fullmatch(r"[A-Za-z0-9.\-]+", block["instrument"] or ""):
                ticker = block["instrument"]
            if ticker:
                gekauft.append({"id": block["id"], "zeit": block["zeit"], "profil": block["portfolio"], "ticker": ticker})
    return verworfen, gekauft, ungueltig


def vergleich(eintraege: list[dict], horizonte: list[int]) -> dict:
    ergebnis = {}
    for n in horizonte:
        renditen = [e["horizonte"][str(n)]["rendite"] for e in eintraege
                    if e["horizonte"].get(str(n), {}).get("status") == "bewertet"]
        ergebnis[str(n)] = {"n": len(renditen),
                            "mittel": sum(renditen) / len(renditen) if renditen else None,
                            "trefferquote": sum(1 for r in renditen if r > 0) / len(renditen) if renditen else None}
    return ergebnis


def auswerten(heute: date | None = None, netz: bool = False, schreiben: bool = True) -> dict:
    heute = heute or g.heute()
    einst = einstellungen()
    horizonte = [int(n) for n in einst["horizonte"]]
    verworfen, gekauft, ungueltig = sammeln()
    ergebnis_v, ergebnis_g = [], []
    for quelle, ziel in ((verworfen, ergebnis_v), (gekauft, ergebnis_g)):
        for e in quelle:
            ziel.append({**{k: v for k, v in e.items() if k != "zeit"}, "zeit": g.iso(e["zeit"]),
                         **bewerten(e["ticker"], e["zeit"], heute, netz)})
    profile = sorted({e["profil"] for e in ergebnis_v + ergebnis_g if e["profil"]})
    ergebnis = {"zeit": g.iso(g.jetzt()), "beginn": einst["beginn"], "einsatz": einst["einsatz"], "horizonte": horizonte,
                "ungueltig": ungueltig, "verworfen": ergebnis_v, "gekauft": ergebnis_g,
                "vergleich": {"verworfen": vergleich(ergebnis_v, horizonte), "gekauft": vergleich(ergebnis_g, horizonte),
                              "je_profil": {p: {"verworfen": vergleich([e for e in ergebnis_v if e["profil"] == p], horizonte),
                                                "gekauft": vergleich([e for e in ergebnis_g if e["profil"] == p], horizonte)}
                                            for p in profile}},
                "ohne_kurs": sum(1 for e in ergebnis_v + ergebnis_g if e["status"] == "kein_kurs")}
    if schreiben:
        g.json_schreiben(ergebnis_pfad(), ergebnis)
    return ergebnis


def lesen() -> dict | None:
    datei = ergebnis_pfad()
    return json.loads(datei.read_text(encoding="utf-8")) if datei.exists() else None


# --------------------------------------------------------------------------
# Prüfung und Anzeige


def pruef_hinweise() -> list[str]:
    """Session-Einträge ab `beginn` ohne Verworfen-Zeile und ungültige Teile (nur Warnungen)."""
    beginn = einstellungen()["beginn"]
    hinweise = []
    for block in g.journal_bloecke():
        if block["art"] != "S":
            continue
        ort = f"{block['id']} ({block['datei']})"
        text = block["felder"].get("verworfen")
        if text is None:
            if (block["datum"] or "") >= beginn:
                hinweise.append(f"{ort}: die Zeile 'Verworfen' fehlt (geprüfte, nicht gekaufte Kandidaten oder 'keine').")
            continue
        _, fehler = verworfen_lesen(text)
        hinweise += [f"{ort}: Verworfen: {f}" for f in fehler]
    return hinweise


def _p(wert: float | None, stellen: int = 1) -> str:
    return "–" if wert is None else f"{wert * 100:.{stellen}f} %".replace(".", ",")


def ranking_abschnitt(ergebnis: dict | None) -> list[str]:
    zeilen = ["## Schattenbuch", ""]
    if not ergebnis or not (ergebnis["verworfen"] or ergebnis["gekauft"]):
        return zeilen + ["Noch keine verworfenen Kandidaten im Session-Eintrag (Zeile 'Verworfen', CLAUDE.md).", ""]
    zeilen += ["Nettorendite nach Kosten bei gleichem Einsatz, gleiche Bewertung für verworfene und gekaufte Werte.", "",
               "| Horizont | verworfen n | verworfen Ø | verworfen Treffer | gekauft n | gekauft Ø | gekauft Treffer |",
               "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for n in ergebnis["horizonte"]:
        v, k = ergebnis["vergleich"]["verworfen"][str(n)], ergebnis["vergleich"]["gekauft"][str(n)]
        zeilen.append(f"| {n} Handelstage | {v['n']} | {_p(v['mittel'])} | {_p(v['trefferquote'], 0)} | {k['n']} | "
                      f"{_p(k['mittel'])} | {_p(k['trefferquote'], 0)} |")
    if min(ergebnis["vergleich"]["verworfen"][str(n)]["n"] for n in ergebnis["horizonte"]) < MIN_AUSSAGE:
        zeilen += ["", f"Weniger als {MIN_AUSSAGE} bewertete verworfene Kandidaten je Horizont: kaum belastbar."]
    zeilen.append("")
    return zeilen


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Schattenbuch der verworfenen Kandidaten (bucht nie).")
    unter = parser.add_subparsers(dest="befehl", required=True)
    p = unter.add_parser("auswerten", help="bewerten und data/schattenbuch.json schreiben")
    p.add_argument("--netz", action="store_true")
    p.add_argument("--json", action="store_true")
    unter.add_parser("liste", help="alle Kandidaten mit Stand")
    args = parser.parse_args(argv)
    try:
        ergebnis = auswerten(netz=getattr(args, "netz", False), schreiben=args.befehl == "auswerten")
        if args.befehl == "liste":
            for e in ergebnis["verworfen"]:
                print(f"{e['id']} {e['profil'] or '-'} {e['ticker']}: {e['status']} " + ", ".join(
                    f"{n}T {_p(h.get('rendite'))}" if h["status"] == "bewertet" else f"{n}T {h['status']}"
                    for n, h in e["horizonte"].items()))
            for f in ergebnis["ungueltig"]:
                print(f"{f['id']}: UNGÜLTIG {f['fehler']}")
        elif args.json:
            print(json.dumps(ergebnis, ensure_ascii=False, indent=1))
        else:
            print("\n".join(ranking_abschnitt(ergebnis)))
    except Fehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
