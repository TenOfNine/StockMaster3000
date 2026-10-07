#!/usr/bin/env python3
"""Unabhängige Kontrolle des Spielstands. Rückgabewert 1 bei Fehlern.

Prüft:
- Cash und Positionen lassen sich aus trades/ vollständig nachrechnen.
- Jede Order verweist auf einen Journal-Eintrag, der vor ihr erfasst wurde.
- Jeder Kurs in trades/ findet sich in data/kurse/ bzw. data/historie/.
- trades/, journal/, data/kurse/, data/limits/, news/ werden nur angehängt
  (gegenüber dem letzten Commit bzw. mit --historie über alle Commits des
  lokalen Spielstand-Gits im Datenverzeichnis).
- Limits waren bei jeder Ausführung eingehalten (data/limits/).
- config/profile.json stimmt mit der Tabelle in regeln.md überein.
- Warnung bei verwaister Session-Sperre und fehlenden Feiertagen.
- Warnung, wenn das Spielstand-Git ein Remote hat (Spielstand bleibt lokal).

Spielstand kommt aus dem Datenverzeichnis (STOCKMASTER_DATA_DIR), regeln.md und
config/ aus dem Framework.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import gemeinsam as g
import kurse
import limits
from gemeinsam import D

NUR_ANHAENGEN = ("trades", "journal", "data/kurse", "data/limits", "news")
ORDER_AKTIONEN = ("kauf", "verkauf", "vormerkung", "aenderung", "storno")


@dataclass
class Befund:
    stufe: str      # FEHLER oder WARNUNG
    pruefung: str
    text: str

    def __str__(self) -> str:
        return f"{self.stufe} [{self.pruefung}] {self.text}"


def fehler(pruefung, text) -> Befund:
    return Befund("FEHLER", pruefung, text)


def warnung(pruefung, text) -> Befund:
    return Befund("WARNUNG", pruefung, text)


# --------------------------------------------------------------------------
# Nachrechnung


def pruefe_nachrechnung(profil: str) -> list[Befund]:
    name = "Nachrechnung"
    befunde = []
    portfolio = g.portfolio_laden(profil)
    zeilen = g.trades_lesen(profil)
    cash = g.geld(g.projekt()["startkapital"])
    bestand: dict[str, Decimal] = {}
    for nummer, zeile in enumerate(zeilen, start=1):
        ort = f"{profil} {zeile['trade_id']}"
        if zeile["trade_id"] != f"T-{nummer:04d}":
            befunde.append(fehler(name, f"{ort}: Trade-ID nicht fortlaufend (erwartet T-{nummer:04d})."))
        betrag = D(zeile["betrag_eur"] or "0")
        cash = g.geld(cash + betrag)
        if D(zeile["cash_danach"]) != cash:
            befunde.append(fehler(name, f"{ort}: cash_danach {zeile['cash_danach']} passt nicht zur "
                                        f"Summe der Beträge ({cash})."))
        aktion, pid = zeile["aktion"], zeile["position_id"]
        stueck = D(zeile["stueck"] or "0")
        if aktion in ("kauf", "verkauf"):
            gebuehr = D(zeile["gebuehr_eur"] or "0")
            kurswert = (-betrag - gebuehr) if aktion == "kauf" else (betrag + gebuehr)
            if abs(kurswert - stueck * D(zeile["kurs"])) > Decimal("0.011"):
                befunde.append(fehler(name, f"{ort}: Betrag {betrag} passt nicht zu Stück x Kurs."))
        if aktion == "kauf":
            if pid in bestand:
                befunde.append(fehler(name, f"{ort}: Position {pid} doppelt eröffnet."))
            bestand[pid] = stueck
        elif aktion in ("verkauf", "knockout", "split"):
            if pid not in bestand:
                befunde.append(fehler(name, f"{ort}: Position {pid} existiert nicht."))
                continue
            if aktion == "verkauf":
                bestand[pid] -= stueck
            elif aktion == "knockout":
                bestand[pid] = Decimal("0")
            else:
                bestand[pid] = stueck
            if bestand[pid] <= 0:
                del bestand[pid]
        elif aktion in ("vormerkung", "storno", "verfall", "aenderung") and betrag != 0:
            befunde.append(fehler(name, f"{ort}: {aktion} darf keinen Betrag haben."))
    if cash != g.geld(portfolio["cash"]):
        befunde.append(fehler(name, f"{profil}: Cash im Portfolio {portfolio['cash']} EUR, nachgerechnet {cash} EUR."))
    im_portfolio = {p["id"]: D(p["stueck"]) for p in portfolio["positionen"]}
    if im_portfolio != bestand:
        befunde.append(fehler(name, f"{profil}: Positionen im Portfolio {sorted(im_portfolio.items())} weichen "
                                    f"von trades/ ab {sorted(bestand.items())}."))
    zaehler = int(portfolio.get("zaehler", {}).get("trade", 0))
    if zaehler != len(zeilen):
        befunde.append(fehler(name, f"{profil}: Zähler {zaehler} Trades, trades/ enthält {len(zeilen)} Zeilen."))
    if D(portfolio["cash"]) < 0:
        befunde.append(warnung(name, f"{profil}: negativer Cash-Bestand {portfolio['cash']} EUR."))
    return befunde


# --------------------------------------------------------------------------
# Journal


def pruefe_journal(profil: str, eintraege: dict | None = None) -> list[Befund]:
    name = "Journal"
    befunde = []
    eintraege = g.journal_eintraege() if eintraege is None else eintraege
    for zeile in g.trades_lesen(profil):
        ort = f"{profil} {zeile['trade_id']}"
        jid = zeile["journal_id"]
        if zeile["aktion"] in ORDER_AKTIONEN and not jid:
            befunde.append(fehler(name, f"{ort}: {zeile['aktion']} ohne Journal-ID."))
            continue
        if not jid:
            continue
        eintrag = eintraege.get(jid)
        if eintrag is None:
            befunde.append(fehler(name, f"{ort}: Journal-Eintrag {jid} fehlt."))
            continue
        if eintrag.get("doppelt"):
            befunde.append(fehler(name, f"{ort}: Journal-ID {jid} ist mehrfach vergeben."))
        if zeile["grund"] == "order":
            if eintrag["zeit"] is None:
                befunde.append(fehler(name, f"{ort}: Journal-Eintrag {jid} ohne Zeit."))
            elif eintrag["zeit"] > g.zeit_lesen(zeile["zeit"]):
                befunde.append(fehler(name, f"{ort}: Journal-Eintrag {jid} ({eintrag['zeit']:%Y-%m-%d %H:%M}) "
                                            f"wurde nach der Order ({zeile['zeit']}) erfasst."))
            if eintrag["portfolio"] != profil:
                befunde.append(fehler(name, f"{ort}: Journal-Eintrag {jid} betrifft '{eintrag['portfolio']}'."))
    return befunde


J_PFLICHTFELDER = {
    "zeit": "Zeit", "aktion": "Aktion", "these": "These", "szenarien": "Szenarien",
    "katalysator": "Katalysator und Zeithorizont", "einstieg": "Einstieg, Stop, Kursziel",
    "positionsgröße": "Positionsgröße und Risikorechnung", "quellen": "Quellen", "unsicherheiten": "Unsicherheiten",
}
S_PFLICHTFELDER = {"zeit": "Zeit", "marktlage": "Marktlage", "offene punkte": "Offene Punkte"}


def _hat_feld(felder: dict, praefix: str) -> str | None:
    for name, wert in felder.items():
        if name.startswith(praefix):
            return wert
    return None


def pruefe_journal_vollstaendigkeit(bloecke: list[dict] | None = None) -> list[Befund]:
    """Warnungen für unvollständige Journal- und Session-Einträge (Vorlagen in CLAUDE.md)."""
    name = "Journal-Vorlage"
    befunde = []
    bloecke = g.journal_bloecke() if bloecke is None else bloecke
    profile = g.vorhandene_profile() or list(g.PROFILE)
    for block in bloecke:
        ort = f"{block['id']} ({block['datei']})"
        pflicht = J_PFLICHTFELDER if block["art"] == "J" else dict(
            S_PFLICHTFELDER, **{p: p.capitalize() for p in profile})
        fehlend = [titel for praefix, titel in pflicht.items() if not (_hat_feld(block["felder"], praefix) or "").strip()]
        if fehlend:
            befunde.append(warnung(name, f"{ort}: es fehlt {', '.join(fehlend)}."))
        if block["art"] == "J":
            quellen = _hat_feld(block["felder"], "quellen") or ""
            if quellen and "http" not in quellen:
                befunde.append(warnung(name, f"{ort}: Quellen ohne URL."))
            szenarien = _hat_feld(block["felder"], "szenarien") or ""
            if szenarien and "%" not in szenarien:
                befunde.append(warnung(name, f"{ort}: Szenarien ohne Wahrscheinlichkeiten in %."))
    return befunde


def pruefe_session_eintraege(bloecke: list[dict] | None = None) -> list[Befund]:
    """Jede Session (Journal-Datei) endet mit einem Session-Eintrag S-... (regeln.md 10)."""
    bloecke = g.journal_bloecke() if bloecke is None else bloecke
    sperre = g.sperre_lesen()
    laufend = f"{g.heute().isoformat()}_{sperre['person']}.md" if sperre and not g.sperre_verwaist(sperre) else None
    befunde = []
    ordner = g.pfad("journal")
    dateien = sorted(d.name for d in ordner.glob("*.md")) if ordner.exists() else []
    mit_session = {b["datei"] for b in bloecke if b["art"] == "S"}
    for datei in dateien:
        if datei not in mit_session and datei != laufend:
            befunde.append(warnung("Session-Eintrag", f"journal/{datei}: kein Session-Eintrag (S-...)."))
    ids = [b["id"] for b in bloecke if b["art"] == "S"]
    for doppelt in sorted({i for i in ids if ids.count(i) > 1}):
        befunde.append(fehler("Session-Eintrag", f"Session-ID {doppelt} ist mehrfach vergeben."))
    return befunde


# --------------------------------------------------------------------------
# Kursbelege


def _kursprotokoll(datum: str, cache: dict) -> list[dict]:
    if datum not in cache:
        cache[datum] = g.csv_lesen(g.pfad("data", "kurse", f"{datum}.csv"))
    return cache[datum]


def _fx_belegt(wert: Decimal, tag: date, eroeffnung: bool, historien: dict) -> bool:
    ticker = g.projekt()["devisen_ticker"]
    kerzen = historien.setdefault(ticker, kurse.gespeicherte_historie(ticker))
    kerze = kerzen.get(tag)
    if kerze is not None:
        return wert == (kerze.open if eroeffnung else kerze.close)
    frueher = [d for d in kerzen if d < tag]
    return bool(frueher) and kerzen[max(frueher)].close == wert


def pruefe_kurse(profil: str) -> list[Befund]:
    name = "Kursbelege"
    befunde = []
    protokolle: dict = {}
    historien: dict = {}
    for zeile in g.trades_lesen(profil):
        quelle = zeile["kursquelle"]
        if not quelle:
            continue
        ort = f"{profil} {zeile['trade_id']}"
        ticker = zeile["basiswert"]
        kurs = D(zeile["kurs_basiswert"])
        fx = D(zeile["devisenkurs"]) if zeile["devisenkurs"] else None
        if quelle == "kurse":
            zeit = zeile["kurs_zeit"]
            protokoll = _kursprotokoll(zeit[:10], protokolle)
            if not any(r["ticker"] == ticker and r["zeit"] == zeit and D(r["kurs"]) == kurs for r in protokoll):
                befunde.append(fehler(name, f"{ort}: Kurs {kurs} für {ticker} um {zeit} nicht in data/kurse/."))
            if fx is not None and not any(r["ticker"] == g.projekt()["devisen_ticker"] and D(r["kurs"]) == fx
                                          for r in protokoll):
                befunde.append(fehler(name, f"{ort}: Devisenkurs {fx} nicht in data/kurse/{zeit[:10]}.csv."))
            continue
        if not quelle.startswith("historie:"):
            befunde.append(fehler(name, f"{ort}: unbekannte Kursquelle '{quelle}'."))
            continue
        art = quelle.split(":", 1)[1]
        tag = date.fromisoformat(zeile["kurs_zeit"][:10])
        kerzen = historien.setdefault(ticker, kurse.gespeicherte_historie(ticker))
        kerze = kerzen.get(tag)
        if kerze is None:
            befunde.append(fehler(name, f"{ort}: keine Tageskerze {ticker} {tag} in data/historie/."))
            continue
        belegt = {
            "open": kurs == kerze.open,
            "close": kurs == kerze.close,
            "intraday": kerze.low <= kurs <= kerze.high,
            "dividende": kurs == kerze.dividende,
            "split": kurs == kerze.split,
        }.get(art)
        if belegt is None:
            befunde.append(fehler(name, f"{ort}: unbekannte Kursquelle '{quelle}'."))
        elif not belegt:
            befunde.append(fehler(name, f"{ort}: Kurs {kurs} ({art}) passt nicht zur Tageskerze {ticker} {tag} "
                                        f"(O {kerze.open} H {kerze.high} L {kerze.low} C {kerze.close})."))
        if fx is not None and not _fx_belegt(fx, tag, art == "open", historien):
            befunde.append(fehler(name, f"{ort}: Devisenkurs {fx} am {tag} nicht in data/historie/ belegt."))
    return befunde


# --------------------------------------------------------------------------
# Nur anhängen (Git)


def _git(*argumente, pruefen=True) -> subprocess.CompletedProcess:
    """Git im Datenverzeichnis (lokales Spielstand-Repository)."""
    return subprocess.run(["git", "-c", f"safe.directory={g.root()}", *argumente], cwd=g.root(),
                          capture_output=True, check=pruefen)


def ist_git() -> bool:
    """Das Datenverzeichnis ist selbst die Wurzel eines Git-Repositorys mit mindestens einem Commit."""
    if not (g.root() / ".git").exists():
        return False
    try:
        return _git("rev-parse", "--verify", "HEAD", pruefen=False).returncode == 0
    except FileNotFoundError:
        return False


def pruefe_remote() -> list[Befund]:
    if not ist_git():
        return []
    remotes = _git("remote", pruefen=False).stdout.decode().split()
    if remotes:
        return [warnung("Spielstand-Git", f"Das Datenverzeichnis hat ein Remote ({', '.join(remotes)}). "
                                          "Spielstand bleibt lokal; Werkzeuge pushen nie.")]
    return []


def _inhalt(ref: str, datei: str) -> bytes | None:
    ergebnis = _git("show", f"{ref}:{datei}", pruefen=False)
    return ergebnis.stdout if ergebnis.returncode == 0 else None


def _nur_angehaengt(alt: bytes, neu: bytes | None) -> bool:
    return neu is not None and neu.startswith(alt)


def pruefe_anhaengen(basis: str = "HEAD") -> list[Befund]:
    """Arbeitsverzeichnis gegenüber dem letzten Commit."""
    name = "Nur anhängen"
    if not ist_git():
        return [warnung(name, "Kein Git-Repository mit Commit gefunden; Prüfung übersprungen.")]
    befunde = []
    dateien = _git("ls-tree", "-r", "--name-only", basis, "--", *NUR_ANHAENGEN).stdout.decode().split()
    for datei in dateien:
        alt = _inhalt(basis, datei)
        pfad = g.pfad(datei)
        neu = pfad.read_bytes() if pfad.exists() else None
        if not _nur_angehaengt(alt, neu):
            befunde.append(fehler(name, f"{datei}: bisheriger Inhalt gegenüber {basis} verändert oder gelöscht."))
    return befunde


def pruefe_anhaengen_historie() -> list[Befund]:
    """Jeder Commit gegenüber jedem seiner Eltern (für die GitHub Action)."""
    name = "Nur anhängen"
    if not ist_git():
        return [warnung(name, "Kein Git-Repository mit Commit gefunden; Prüfung übersprungen.")]
    befunde = []
    for zeile in _git("rev-list", "--reverse", "--parents", "HEAD").stdout.decode().splitlines():
        commit, *eltern = zeile.split()
        for elter in eltern:
            geaendert = _git("diff", "--name-only", "--no-renames", elter, commit, "--",
                             *NUR_ANHAENGEN).stdout.decode().split()
            for datei in geaendert:
                alt = _inhalt(elter, datei)
                if alt is None:
                    continue  # neue Datei
                if not _nur_angehaengt(alt, _inhalt(commit, datei)):
                    befunde.append(fehler(name, f"{datei}: in Commit {commit[:8]} gegenüber {elter[:8]} verändert "
                                                "oder gelöscht."))
    return befunde + pruefe_anhaengen("HEAD")


# --------------------------------------------------------------------------
# Limits


def pruefe_limits(profil: str) -> list[Befund]:
    name = "Limits"
    befunde = []
    protokoll = g.limit_protokoll(profil)
    aktuell = limits.grenzen(profil)
    for zeile in g.trades_lesen(profil):
        if zeile["aktion"] != "kauf":
            continue
        ort = f"{profil} {zeile['trade_id']}"
        eintrag = protokoll.get(zeile["trade_id"])
        if eintrag is None:
            befunde.append(fehler(name, f"{ort}: keine Limitprüfung in data/limits/ protokolliert."))
            continue
        verletzt = limits.kennzahlen_einhalten(eintrag["kennzahlen"], eintrag["grenzen"])
        if verletzt:
            befunde.append(fehler(name, f"{ort}: bei Ausführung verletzt: {', '.join(verletzt)}."))
        if eintrag["grenzen"] != aktuell:
            befunde.append(warnung(name, f"{ort}: protokollierte Grenzen weichen von config/profile.json ab."))
        kennzahlen = eintrag["kennzahlen"]
        kurswert = -D(zeile["betrag_eur"]) - D(zeile["gebuehr_eur"])
        einsatz = D(kennzahlen["einsatz"])
        if not (Decimal("0") <= einsatz - kurswert <= D(zeile["kurs"]) * Decimal("0.000001") + Decimal("0.01")):
            befunde.append(fehler(name, f"{ort}: Kurswert {kurswert} passt nicht zum geprüften Einsatz {einsatz}."))
        if D(kennzahlen["hebel"]) != D(zeile["hebel"]).quantize(Decimal("0.000001")):
            befunde.append(fehler(name, f"{ort}: Hebel {zeile['hebel']} weicht vom geprüften {kennzahlen['hebel']} ab."))
    return befunde


# --------------------------------------------------------------------------
# Konfiguration gegen regeln.md

REGEL_ZEILEN = {
    "Max. Anteil Zertifikate am Portfoliowert": "max_anteil_zertifikate",
    "Max. Hebel je Zertifikat (beim Kauf)": "max_hebel",
    "Max. Gesamt-Exposure": "max_exposure",
    "Max. Einzelposition (Marktwert)": "max_einzelposition",
    "Mindest-Cashquote": "min_cashquote",
    "Max. Risiko je Trade": "max_risiko_trade",
    "Drawdown-Bremse Stufe 1": "drawdown_stufe1",
    "Drawdown-Bremse Stufe 2": "drawdown_stufe2",
    "Benchmark": "benchmark_etf_anteil",
}


def _regelwert(text: str) -> Decimal:
    roh = text.strip().replace(",", ".").replace("−", "-")
    treffer = re.match(r"^(-?\d+(?:\.\d+)?)\s*(%|x)?", roh)
    if not treffer:
        raise ValueError(text)
    zahl = D(treffer.group(1))
    return zahl / 100 if treffer.group(2) == "%" else zahl


def regeln_tabelle() -> dict[str, dict[str, Decimal]]:
    text = g.framework_pfad("regeln.md").read_text(encoding="utf-8")
    abschnitt = re.search(r"^## 7\..*?$(.*?)^## ", text, re.S | re.M)
    if not abschnitt:
        raise ValueError("Abschnitt 7 in regeln.md nicht gefunden")
    zeilen = [z.strip() for z in abschnitt.group(1).splitlines() if z.strip().startswith("|")]
    kopf = [z.strip().lower() for z in zeilen[0].strip("|").split("|")]
    profile = kopf[1:]
    tabelle: dict[str, dict[str, Decimal]] = {p: {} for p in profile}
    for zeile in zeilen[2:]:
        zellen = [z.strip() for z in zeile.strip("|").split("|")]
        schluessel = REGEL_ZEILEN.get(zellen[0])
        if schluessel is None:
            tabelle.setdefault("_unbekannt", {})[zellen[0]] = Decimal("0")
            continue
        for profil, zelle in zip(profile, zellen[1:]):
            tabelle[profil][schluessel] = _regelwert(zelle)
    return tabelle


def pruefe_config_regeln() -> list[Befund]:
    name = "Konfiguration"
    befunde = []
    try:
        tabelle = regeln_tabelle()
    except (ValueError, IndexError) as exc:
        return [fehler(name, f"Tabelle in regeln.md Abschnitt 7 nicht lesbar: {exc}")]
    for unbekannt in tabelle.pop("_unbekannt", {}):
        befunde.append(fehler(name, f"regeln.md Abschnitt 7: unbekannte Zeile '{unbekannt}'."))
    config = g.config("profile")["profile"]
    if set(tabelle) != set(config):
        befunde.append(fehler(name, f"Profile in regeln.md {sorted(tabelle)} und config {sorted(config)} verschieden."))
    for profil, werte in tabelle.items():
        for schluessel in REGEL_ZEILEN.values():
            if schluessel not in werte:
                befunde.append(fehler(name, f"regeln.md: Wert {schluessel} für {profil} fehlt."))
                continue
            ist = config.get(profil, {}).get(schluessel)
            if ist is None or D(ist) != werte[schluessel]:
                befunde.append(fehler(name, f"config/profile.json {profil}.{schluessel} = {ist}, regeln.md = "
                                            f"{g.text(werte[schluessel])}."))
    return befunde


# --------------------------------------------------------------------------
# Sperre und Kalender


def pruefe_sperre() -> list[Befund]:
    sperre = g.sperre_lesen()
    if sperre and g.sperre_verwaist(sperre):
        return [warnung("Session-Sperre", f"Verwaiste Sperre von {sperre['person']} seit {sperre['start']} "
                                          f"(älter als {g.projekt()['sperre_stunden']} Stunden).")]
    return []


def pruefe_richtlinien() -> list[Befund]:
    """Nach dem Spielstart braucht jedes Portfolio eine ausformulierte Anlagerichtlinie (regeln.md 11)."""
    if not g.spiel_lesen().get("startdatum"):
        return []
    return [warnung("Anlagerichtlinie", f"strategie/{profil}.md ist noch die Vorlage aus tools/init.py; vor der ersten "
                                        "Trading-Session ausformulieren (AP12 Punkt 2).")
            for profil in g.vorhandene_profile() if not g.richtlinie_ausformuliert(profil)]


def pruefe_kalender() -> list[Befund]:
    heute = g.heute()
    jahre = [heute.year] + ([heute.year + 1] if heute.month >= 11 else [])
    befunde = []
    for jahr in jahre:
        for boerse in kurse.feiertage_gepflegt(jahr):
            befunde.append(warnung("Kalender", f"Feiertage {jahr} für {boerse} fehlen in config/universum.json."))
    return befunde


# --------------------------------------------------------------------------


def alle_pruefungen(historie: bool = False) -> list[Befund]:
    befunde = pruefe_config_regeln() + pruefe_sperre() + pruefe_kalender() + pruefe_remote() + pruefe_richtlinien()
    befunde += pruefe_anhaengen_historie() if historie else pruefe_anhaengen()
    bloecke = g.journal_bloecke()
    befunde += pruefe_journal_vollstaendigkeit(bloecke) + pruefe_session_eintraege(bloecke)
    eintraege = g.journal_eintraege()
    for profil in g.vorhandene_profile():
        befunde += pruefe_nachrechnung(profil)
        befunde += pruefe_journal(profil, eintraege)
        befunde += pruefe_kurse(profil)
        befunde += pruefe_limits(profil)
    return befunde


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Spielstand unabhängig prüfen (Rückgabewert 1 bei Fehlern).")
    parser.add_argument("--historie", action="store_true",
                        help="Nur-Anhängen über alle Commits des lokalen Spielstand-Gits prüfen")
    args = parser.parse_args(argv)
    try:
        befunde = alle_pruefungen(historie=args.historie)
    except g.Fehler as exc:
        print(f"FEHLER [Prüfskript] {exc}")
        return 1
    for befund in befunde:
        print(befund)
    anzahl_fehler = sum(1 for b in befunde if b.stufe == "FEHLER")
    anzahl_warnungen = len(befunde) - anzahl_fehler
    profile = g.vorhandene_profile()
    if anzahl_fehler:
        print(f"Prüfung FEHLGESCHLAGEN: {anzahl_fehler} Fehler, {anzahl_warnungen} Warnungen.")
        return 1
    print(f"Prüfung bestanden ({len(profile)} Portfolios, {anzahl_warnungen} Warnungen).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
