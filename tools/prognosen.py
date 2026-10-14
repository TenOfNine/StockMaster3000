#!/usr/bin/env python3
"""Strukturierte Prognosen und Kalibrierung (Strategie-Labor L1).

Jeder Kauf-Eintrag im Journal trägt neben den Szenarien in Freitext einen maschinenlesbaren Prognose-Block:

    - Prognose: ticker=SAP.DE; horizont=20; bull=0.30@112; base=0.50@104; bear=0.20@93; start=101.5

- `ticker`: Kursticker der Prognose (bei Aktien und ETFs das Instrument, bei Zertifikaten der Basiswert).
- `horizont`: Handelstage ab dem Tag des Eintrags (1 bis 260).
- `bull`, `base`, `bear`: `Wahrscheinlichkeit@Kurs`; Bull ist das hohe, Bear das tiefe Kursziel (unabhängig von der
  Richtung der Position). Die Wahrscheinlichkeiten summieren sich zu 1 (Toleranz 0,005).
- `start` (optional): Kurs bei Erfassung; sonst der erste protokollierte Kurs des Tickers ab der Eintragszeit, sonst der
  letzte Schlusskurs davor.

Ausgewertet wird, sobald der Horizont vorbei ist: Der Schlusskurs am Horizontende (bei Kurslücke die ungünstigere
Annahme, siehe zeitreihen.kurs_am) gehört zu dem Szenario, dessen Ziel ihm am nächsten liegt. Kennzahlen: Brier-Score
(Summe der quadrierten Abweichungen über die drei Szenarien, 0 ist perfekt, 0,667 entspricht dem Raten mit 1/3), Kalibrierung
(angegebene Wahrscheinlichkeit gegen Trefferhäufigkeit in Klassen von 10 Prozentpunkten), Richtungstrefferquote und der
Fehler des erwarteten Kurses. Je Profil und gesamt.

    python tools/prognosen.py auswerten [--netz] [--json]   Kennzahlen berechnen, data/prognosen.json schreiben
    python tools/prognosen.py liste                         alle Prognosen mit Stand
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime, timedelta

import gemeinsam as g
import kurse
import zeitreihen
from gemeinsam import D, Fehler

SZENARIEN = ("bull", "base", "bear")
MAX_HORIZONT = 260
TOLERANZ_SUMME = 0.005
BRIER_RATEN = 2 / 3
MIN_AUSSAGE = 30  # darunter sind Kennzahlen kaum belastbar
PROFIL_GESAMT = "gesamt"


def ergebnis_pfad():
    return g.pfad("data", "prognosen.json")


def einstellungen() -> dict:
    return {"pflicht_ab": "9999-12-31", **g.projekt().get("prognosen", {})}


# --------------------------------------------------------------------------
# Block lesen


def _zahl(text: str) -> float:
    return float(text.strip().replace(",", "."))


def block_lesen(text: str) -> tuple[dict | None, list[str]]:
    """Liest einen Prognose-Block. Gibt (Prognose, Fehler) zurück; bei Fehlern ist die Prognose None."""
    fehler: list[str] = []
    werte: dict[str, str] = {}
    for teil in (text or "").split(";"):
        if not teil.strip():
            continue
        if "=" not in teil:
            fehler.append(f"'{teil.strip()}' ist kein Schlüssel=Wert")
            continue
        schluessel, wert = teil.split("=", 1)
        schluessel = schluessel.strip().lower()
        if schluessel in werte:
            fehler.append(f"'{schluessel}' kommt doppelt vor")
        werte[schluessel] = wert.strip()
    unbekannt = sorted(set(werte) - {"ticker", "horizont", "start", *SZENARIEN})
    if unbekannt:
        fehler.append("unbekannte Felder: " + ", ".join(unbekannt))
    ticker = werte.get("ticker", "")
    if not ticker:
        fehler.append("ticker fehlt")
    else:
        try:
            kurse.boerse_von(ticker)
        except Fehler:
            fehler.append(f"ticker {ticker} ist nicht im Universum")
    horizont = None
    try:
        horizont = int(werte["horizont"])
        if not 1 <= horizont <= MAX_HORIZONT:
            fehler.append(f"horizont {horizont} außerhalb 1 bis {MAX_HORIZONT} Handelstage")
    except (KeyError, ValueError):
        fehler.append("horizont fehlt oder ist keine ganze Zahl")
    wahrsch: dict[str, float] = {}
    ziele: dict[str, float] = {}
    for name in SZENARIEN:
        roh = werte.get(name)
        if roh is None:
            fehler.append(f"{name} fehlt (Form Wahrscheinlichkeit@Kurs)")
            continue
        if "@" not in roh:
            fehler.append(f"{name} ist nicht lesbar ({roh}; Form Wahrscheinlichkeit@Kurs)")
            continue
        try:
            p, kurs = (_zahl(x) for x in roh.split("@", 1))
        except ValueError:
            fehler.append(f"{name} ist nicht lesbar ({roh})")
            continue
        if not 0 < p < 1:
            fehler.append(f"{name}: Wahrscheinlichkeit {p} muss zwischen 0 und 1 liegen")
        if kurs <= 0:
            fehler.append(f"{name}: Ziel {kurs} muss positiv sein")
        wahrsch[name], ziele[name] = p, kurs
    start = None
    if "start" in werte:
        try:
            start = _zahl(werte["start"])
            if start <= 0:
                fehler.append("start muss positiv sein")
                start = None
        except ValueError:
            fehler.append("start ist keine Zahl")
    if len(wahrsch) == 3:
        if abs(sum(wahrsch.values()) - 1) > TOLERANZ_SUMME:
            fehler.append(f"Wahrscheinlichkeiten summieren sich zu {sum(wahrsch.values()):.3f}, nicht zu 1")
        if not ziele["bull"] > ziele["bear"] or not ziele["bear"] <= ziele["base"] <= ziele["bull"]:
            fehler.append("Ziele unplausibel: erwartet bear <= base <= bull und bear < bull")
        if start is not None and any(not 0.2 <= z / start <= 5 for z in ziele.values()):
            fehler.append("Ziele unplausibel: mehr als das Fünffache oder weniger als ein Fünftel des Startkurses")
    if fehler:
        return None, fehler
    return {"ticker": ticker, "horizont": horizont, "wahrscheinlichkeit": wahrsch, "ziel": ziele, "start": start}, []


# --------------------------------------------------------------------------
# Sammeln und auswerten


def ausgenommen(block: dict) -> bool:
    """Kein Prognose-Block nötig: Verkäufe, Änderungen und Portfolios mit Daueranweisung (kein Einzelurteil je Order)."""
    aktion = (block["felder"].get("aktion") or "").strip().lower()
    zyklus = g.config("profile").get("daueranweisung", {})
    return not aktion.startswith("kauf") or block["portfolio"] in zyklus


def sammeln() -> tuple[list[dict], list[dict]]:
    """Alle Journal-Einträge mit Prognose-Block. Gibt (gültige, ungültige) zurück."""
    gueltig, ungueltig = [], []
    for block in g.journal_bloecke():
        if block["art"] != "J":
            continue
        text = block["felder"].get("prognose")
        if text is None:
            continue
        prognose, fehler = block_lesen(text)
        eintrag = {"id": block["id"], "profil": block["portfolio"], "datei": block["datei"],
                   "zeit": g.iso(block["zeit"]) if block["zeit"] else None}
        if prognose is None or block["zeit"] is None:
            ungueltig.append({**eintrag, "fehler": fehler or ["Journal-Eintrag ohne Zeit"]})
        else:
            gueltig.append({**eintrag, **prognose, "_zeit": block["zeit"]})
    return gueltig, ungueltig


def start_kurs(p: dict, netz: bool = False) -> tuple[float | None, str]:
    if p["start"] is not None:
        return p["start"], "angegeben"
    gefunden = zeitreihen.protokollkurs(p["ticker"], p["_zeit"])
    if gefunden:
        return float(gefunden[0]), "protokoll"
    schluss = zeitreihen.letzter_schluss_vor(p["ticker"], p["_zeit"].date(), netz)
    return (float(schluss), "schluss") if schluss is not None else (None, "fehlt")


def erwartung(p: dict) -> float:
    return sum(p["wahrscheinlichkeit"][n] * p["ziel"][n] for n in SZENARIEN)


def tatsaechliches_szenario(p: dict, kurs: float) -> str:
    """Szenario, dessen Ziel dem tatsächlichen Kurs (logarithmisch) am nächsten liegt; bei Gleichstand base."""
    abstand = {n: abs(math.log(kurs / p["ziel"][n])) for n in SZENARIEN}
    bester = min(abstand.values())
    if abstand["base"] <= bester + 1e-12:
        return "base"
    return min(abstand, key=abstand.get)


def auswerten_eine(p: dict, heute: date | None = None, netz: bool = False) -> dict:
    heute = heute or g.heute()
    ende = zeitreihen.handelstag_nach(p["ticker"], p["_zeit"].date(), p["horizont"])
    ergebnis = {k: v for k, v in p.items() if k != "_zeit"}
    ergebnis["ende"] = ende.isoformat()
    start, start_quelle = start_kurs(p, netz)
    ergebnis.update(start=start, start_quelle=start_quelle, erwartet=erwartung(p))
    if ende >= heute:
        return {**ergebnis, "status": "offen"}
    gefunden = zeitreihen.kurs_am(p["ticker"], ende, D(str(erwartung(p))), netz)
    if gefunden is None:
        return {**ergebnis, "status": "luecke"}
    kurs, quelle = float(gefunden[0]), gefunden[1]
    szenario = tatsaechliches_szenario(p, kurs)
    brier = sum((p["wahrscheinlichkeit"][n] - (1.0 if n == szenario else 0.0)) ** 2 for n in SZENARIEN)
    ergebnis.update(status="ausgewertet", kurs_ende=kurs, kurs_quelle=quelle, szenario=szenario, brier=brier)
    if start is not None:
        erwartet_dir = (ergebnis["erwartet"] > start) - (ergebnis["erwartet"] < start)
        echt_dir = (kurs > start) - (kurs < start)
        ergebnis["richtung_treffer"] = erwartet_dir != 0 and erwartet_dir == echt_dir
        ergebnis["fehler_erwartung"] = (ergebnis["erwartet"] - kurs) / start
    return ergebnis


def kennzahlen(liste: list[dict]) -> dict:
    ok = [e for e in liste if e["status"] == "ausgewertet"]
    ergebnis = {"anzahl": len(liste), "ausgewertet": len(ok),
                "offen": sum(1 for e in liste if e["status"] == "offen"),
                "luecke": sum(1 for e in liste if e["status"] == "luecke"),
                "luecke_im_ergebnis": sum(1 for e in ok if e.get("kurs_quelle") == "luecke"),
                "brier": None, "brier_skill": None, "richtung_trefferquote": None, "fehler_erwartung_mittel": None,
                "fehler_erwartung_betrag": None, "kalibrierung": [], "belastbar": len(ok) >= MIN_AUSSAGE}
    if not ok:
        return ergebnis
    brier = sum(e["brier"] for e in ok) / len(ok)
    ergebnis["brier"] = brier
    ergebnis["brier_skill"] = 1 - brier / BRIER_RATEN
    mit_richtung = [e for e in ok if "richtung_treffer" in e]
    if mit_richtung:
        ergebnis["richtung_trefferquote"] = sum(1 for e in mit_richtung if e["richtung_treffer"]) / len(mit_richtung)
        fehler = [e["fehler_erwartung"] for e in mit_richtung]
        ergebnis["fehler_erwartung_mittel"] = sum(fehler) / len(fehler)
        ergebnis["fehler_erwartung_betrag"] = sum(abs(f) for f in fehler) / len(fehler)
    klassen = [[] for _ in range(10)]
    for e in ok:
        for n in SZENARIEN:
            p = e["wahrscheinlichkeit"][n]
            klassen[min(9, int(p * 10))].append((p, 1.0 if e["szenario"] == n else 0.0))
    for i, werte in enumerate(klassen):
        if werte:
            ergebnis["kalibrierung"].append({
                "klasse": f"{i / 10:.1f}-{(i + 1) / 10:.1f}", "n": len(werte),
                "mittel_p": sum(w[0] for w in werte) / len(werte), "trefferquote": sum(w[1] for w in werte) / len(werte)})
    return ergebnis


def auswerten(heute: date | None = None, netz: bool = False, schreiben: bool = True) -> dict:
    gueltig, ungueltig = sammeln()
    liste = [auswerten_eine(p, heute, netz) for p in gueltig]
    profile = sorted({e["profil"] for e in liste})
    ergebnis = {"zeit": g.iso(g.jetzt()), "stichtag": einstellungen()["pflicht_ab"], "ungueltig": ungueltig,
                "gesamt": kennzahlen(liste), "profile": {p: kennzahlen([e for e in liste if e["profil"] == p]) for p in profile},
                "prognosen": liste}
    if schreiben:
        g.json_schreiben(ergebnis_pfad(), ergebnis)
    return ergebnis


def lesen() -> dict | None:
    datei = ergebnis_pfad()
    return json.loads(datei.read_text(encoding="utf-8")) if datei.exists() else None


# --------------------------------------------------------------------------
# Prüfung (für pruefe.py): Warnungen, nie Fehler


def pruef_hinweise() -> list[str]:
    """Kauf-Einträge ab dem Stichtag ohne gültigen Prognose-Block; ungültige Blöcke zählen immer."""
    stichtag = einstellungen()["pflicht_ab"]
    hinweise = []
    for block in g.journal_bloecke():
        if block["art"] != "J":
            continue
        ort = f"{block['id']} ({block['datei']})"
        text = block["felder"].get("prognose")
        if text is not None:
            prognose, fehler = block_lesen(text)
            if prognose is None:
                hinweise.append(f"{ort}: ungültige Prognose: " + "; ".join(fehler))
            continue
        if (block["datum"] or "") >= stichtag and not ausgenommen(block):
            hinweise.append(f"{ort}: die Zeile 'Prognose' fehlt (ticker, horizont, bull/base/bear mit Wahrscheinlichkeit@Kurs).")
    return hinweise


# --------------------------------------------------------------------------
# Anzeige


def _p(wert: float | None, stellen: int = 1) -> str:
    return "–" if wert is None else f"{wert * 100:.{stellen}f} %".replace(".", ",")


def _z(wert: float | None, stellen: int = 3) -> str:
    return "–" if wert is None else f"{wert:.{stellen}f}".replace(".", ",")


def zeilen_text(ergebnis: dict) -> list[str]:
    zeilen = []
    for name, k in [(PROFIL_GESAMT, ergebnis["gesamt"]), *ergebnis["profile"].items()]:
        hinweis = "" if k["belastbar"] else f" (erst {k['ausgewertet']} von mindestens {MIN_AUSSAGE}: kaum belastbar)"
        zeilen.append(f"{name}: {k['anzahl']} Prognosen, {k['ausgewertet']} ausgewertet, {k['offen']} offen, {k['luecke']} mit "
                      f"Kurslücke; Brier {_z(k['brier'])} (Raten 0,667), Skill {_z(k['brier_skill'], 2)}, Richtung "
                      f"{_p(k['richtung_trefferquote'], 0)}, Fehler des erwarteten Kurses {_p(k['fehler_erwartung_mittel'])} "
                      f"(Betrag {_p(k['fehler_erwartung_betrag'])}){hinweis}")
    return zeilen


def ranking_abschnitt(ergebnis: dict | None) -> list[str]:
    """Abschnitt für ranking.md (Dezimalkomma)."""
    zeilen = ["## Prognosegüte", ""]
    if not ergebnis or not ergebnis["gesamt"]["anzahl"]:
        return zeilen + ["Noch keine Prognosen mit Block im Journal (Format: CLAUDE.md, Journal-Vorlage).", ""]
    zeilen += ["| Gruppe | Prognosen | ausgewertet | Brier | Skill | Richtung | Fehler Erwartung |",
               "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for name, k in [(PROFIL_GESAMT, ergebnis["gesamt"]), *ergebnis["profile"].items()]:
        zeilen.append(f"| {name.capitalize()} | {k['anzahl']} | {k['ausgewertet']} | {_z(k['brier'])} | {_z(k['brier_skill'], 2)} | "
                      f"{_p(k['richtung_trefferquote'], 0)} | {_p(k['fehler_erwartung_mittel'])} |")
    if not ergebnis["gesamt"]["belastbar"]:
        zeilen += ["", f"Weniger als {MIN_AUSSAGE} ausgewertete Prognosen: die Zahlen sind noch kaum belastbar. "
                       "Brier 0,667 entspricht dem Raten, Skill über 0 ist besser als Raten."]
    zeilen.append("")
    return zeilen


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Strukturierte Prognosen auswerten (Brier, Kalibrierung).")
    unter = parser.add_subparsers(dest="befehl", required=True)
    p = unter.add_parser("auswerten", help="Kennzahlen berechnen und data/prognosen.json schreiben")
    p.add_argument("--netz", action="store_true", help="fehlende Tageskerzen über kurse.py holen")
    p.add_argument("--json", action="store_true")
    unter.add_parser("liste", help="alle Prognosen mit Stand")
    args = parser.parse_args(argv)
    try:
        ergebnis = auswerten(netz=getattr(args, "netz", False), schreiben=args.befehl == "auswerten")
        if args.befehl == "liste":
            for e in ergebnis["prognosen"]:
                print(f"{e['id']} {e['profil']} {e['ticker']} bis {e['ende']}: {e['status']}"
                      + (f", Kurs {e['kurs_ende']:.2f} -> {e['szenario']}, Brier {e['brier']:.3f}" if e["status"] == "ausgewertet" else ""))
            for e in ergebnis["ungueltig"]:
                print(f"{e['id']}: UNGÜLTIG " + "; ".join(e["fehler"]))
        elif args.json:
            print(json.dumps(ergebnis, ensure_ascii=False, indent=1))
        else:
            print("\n".join(zeilen_text(ergebnis)))
    except Fehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
