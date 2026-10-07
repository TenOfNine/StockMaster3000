"""Lesedienst: liest Framework und Datenverzeichnis ausschließlich lesend.

Framework (STOCKMASTER_FRAMEWORK_DIR): Werkzeuge, Regeln, config/, Doku.
Datenverzeichnis (STOCKMASTER_DATA_DIR): Spielstand mit lokalem Git.
Berechnungen (Kennzahlen, Bewertung, Fälligkeiten, Zertifikate) kommen aus
den Werkzeugen in tools/; die Web-UI rechnet nicht selbst. Kurse und News
liest sie nur aus dem, was der Hintergrunddienst gespeichert hat; die API
selbst ruft nichts aus dem Netz ab.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import re
import subprocess
import sys
import threading
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import ModuleType

from ..config import einstellungen

TICKER_MUSTER = re.compile(r"^[A-Z0-9^=.\-]{1,20}$")
ID_MUSTER = re.compile(r"^[JS]-\d{8}-\d{2}$")
FRAMEWORK_DOKUMENTE = ("README.md", "CLAUDE.md", "regeln.md", "STATUS.md", "KONZEPT.md", "AUFTRAG_PHASE1.md",
                       "AUFTRAG_WEBUI.md")
DATEN_DOKUMENTE = ("lessons.md", "ranking.md", "DEMO.md")


class NichtGefunden(Exception):
    pass


# --------------------------------------------------------------------------
# Werkzeuge laden


class _NurSpeicher:
    """Kursquelle ohne Netzwerk: die Web-UI darf keine Kurse abrufen."""

    name = "nur-speicher"

    def aktuell(self, ticker):
        from gemeinsam import KursFehler
        raise KursFehler("Die Web-UI ruft keine Kurse ab.")

    def historie(self, ticker, von, bis):
        return []

    def marktkapitalisierung(self, ticker):
        return None


_module: dict[str, ModuleType] = {}


def framework() -> Path:
    return einstellungen().framework_pfad.resolve()


def daten() -> Path:
    return einstellungen().daten_pfad.resolve()


def repo() -> Path:
    """Spielstand-Repository (Datenverzeichnis); Name aus Stufe 1 beibehalten."""
    return daten()


_ladesperre = threading.Lock()


def werkzeuge() -> dict[str, ModuleType]:
    """Importiert die Werkzeuge des Spiel-Repositorys (einmal je Prozess, threadsicher)."""
    if _module:
        return _module
    with _ladesperre:
        if not _module:
            sys.dont_write_bytecode = True  # das Spiel-Repository bleibt unverändert
            pfad = str(framework() / "tools")
            os.environ["STOCKMASTER_FRAMEWORK_DIR"] = str(framework())
            os.environ["STOCKMASTER_DATA_DIR"] = str(daten())
            if pfad not in sys.path:
                sys.path.insert(0, pfad)
            geladen = {name: importlib.import_module(name)
                       for name in ("gemeinsam", "kurse", "produkte", "limits", "bewertung", "termine",
                                    "datenverzeichnis", "news", "richtlinien")}
            geladen["kurse"].QUELLE = _NurSpeicher()
            _module.update(geladen)
    return _module


def zuruecksetzen() -> None:
    """Für Tests: Werkzeuge neu laden (anderes Repository)."""
    for name in list(sys.modules):
        if name in ("gemeinsam", "kurse", "produkte", "limits", "bewertung", "termine", "buchen", "pruefe", "init",
                    "session", "pfade", "news", "datenverzeichnis", "migriere", "richtlinien"):
            del sys.modules[name]
    _module.clear()


def zahl(wert):
    """Decimal und Datum für JSON; die Anzeige formatiert das Frontend."""
    if isinstance(wert, Decimal):
        return float(wert) if wert.is_finite() else None
    if isinstance(wert, dict):
        return {k: zahl(v) for k, v in wert.items()}
    if isinstance(wert, (list, tuple)):
        return [zahl(v) for v in wert]
    if isinstance(wert, date):
        return wert.isoformat()
    return wert


def _num(text: str | None):
    if text in (None, ""):
        return None
    try:
        return float(text)
    except ValueError:
        return text


# --------------------------------------------------------------------------
# Repository, Status


def _git(*argumente: str) -> str:
    """Lesender Git-Aufruf; ohne Git oder ohne Repository leer statt Fehler."""
    try:
        ergebnis = subprocess.run(["git", "-c", f"safe.directory={repo()}", *argumente], cwd=repo(),
                                  capture_output=True, text=True, timeout=20)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return ergebnis.stdout if ergebnis.returncode == 0 else ""


def repo_info() -> dict:
    kopf = _git("log", "-1", "--format=%H%x1f%h%x1f%aI%x1f%s").strip().split("\x1f")
    return {
        "pfad_name": daten().name,
        "commit": kopf[1] if len(kopf) > 1 else None,
        "commit_zeit": kopf[2] if len(kopf) > 2 else None,
        "commit_text": kopf[3] if len(kopf) > 3 else None,
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD").strip() or None,
        "demo": (repo() / "DEMO.md").exists(),
    }


def _abschnitte(text: str) -> list[tuple[str, list[str]]]:
    abschnitte: list[tuple[str, list[str]]] = [("", [])]
    for zeile in text.splitlines():
        if zeile.startswith("## "):
            abschnitte.append((zeile[3:].strip(), []))
        else:
            abschnitte[-1][1].append(zeile)
    return abschnitte


def _nummerierte_liste(zeilen: list[str]) -> list[dict]:
    eintraege, aktuell = [], None
    for zeile in zeilen:
        treffer = re.match(r"^(\d+)\.\s+(.*)$", zeile)
        if treffer:
            aktuell = {"nummer": int(treffer.group(1)), "text": treffer.group(2).strip()}
            eintraege.append(aktuell)
        elif aktuell and zeile.startswith("   ") and zeile.strip():
            aktuell["text"] += ("\n" if zeile.strip().startswith("-") else " ") + zeile.strip()
        elif aktuell and not zeile.strip():
            continue
        elif aktuell and not zeile.startswith(" "):
            aktuell = None
    return eintraege


def status() -> dict:
    datei = framework() / "STATUS.md"
    text = datei.read_text(encoding="utf-8") if datei.exists() else ""
    kopf = {}
    pakete, entscheidungen, fragen = [], [], []
    for titel, zeilen in _abschnitte(text):
        if titel == "":
            for zeile in zeilen:
                treffer = re.match(r"^- (Phase|Startdatum des Spiels|Letzte Session):\s*(.*)$", zeile)
                if treffer:
                    kopf[{"Phase": "phase", "Startdatum des Spiels": "startdatum",
                          "Letzte Session": "letzte_session"}[treffer.group(1)]] = treffer.group(2)
        if titel.startswith("Arbeitspakete"):
            for zeile in zeilen:
                treffer = re.match(r"^- (?:\[( |x|X)\] )?((?:AP|W)\d+[^ ]*(?: bis W\d+)?)\s+(.*)$", zeile)
                if treffer:
                    pakete.append({"gruppe": titel, "kennung": treffer.group(2), "titel": treffer.group(3),
                                   "erledigt": (treffer.group(1) or "").lower() == "x",
                                   "offen_markiert": treffer.group(1) == " "})
        elif titel == "Entscheidungen":
            entscheidungen = _nummerierte_liste(zeilen)
        elif "Auslegungsfragen" in titel:
            for eintrag in _nummerierte_liste(zeilen):
                eintrag["abschnitt"] = titel
                eintrag["entschieden"] = "entschieden" in titel.lower() or "Entschieden:" in eintrag["text"]
                fragen.append(eintrag)
    # Startdatum und letzte Session sind Spielstand (Datenverzeichnis), nicht Framework.
    spiel = werkzeuge()["gemeinsam"].spiel_lesen()
    # AP12 (Testsession, Anlagerichtlinien, Freigabe, Start) gehört zur Instanz: der Stand folgt dem Datenverzeichnis.
    offen = werkzeuge()["gemeinsam"].richtlinien_offen()
    for paket in pakete:
        if paket["kennung"] == "AP12":
            paket["instanz"] = True
            paket["erledigt"] = bool(spiel.get("startdatum")) and not offen
            paket["offen_markiert"] = not paket["erledigt"]
            teile = []
            if spiel.get("startdatum"):
                teile.append(f"gestartet {spiel['startdatum']}, Freigabe {spiel.get('freigabe_ap12') or 'unbekannt'}")
            else:
                teile.append("Spiel noch nicht gestartet")
            teile.append("Anlagerichtlinien ausformuliert" if not offen else f"Anlagerichtlinien offen: {', '.join(offen)}")
            paket["detail"] = "; ".join(teile)
    kopf["startdatum"] = spiel.get("startdatum") or "noch nicht gestartet"
    sessions = werkzeuge()["gemeinsam"].session_eintraege()
    kopf["letzte_session"] = (f"{sessions[-1]['id']} ({sessions[-1]['auftraggeber']})" if sessions else "keine")
    return {"kopf": kopf, "arbeitspakete": pakete, "entscheidungen": entscheidungen, "auslegungsfragen": fragen,
            "spiel": spiel}


# --------------------------------------------------------------------------
# Portfolios und Kennzahlen


def benchmark() -> list[dict]:
    """data/benchmark.csv (geschrieben von tools/bewertung.py bericht)."""
    w = werkzeuge()
    zeilen = w["gemeinsam"].csv_lesen(repo() / "data" / "benchmark.csv")
    return [{k: (Decimal(v) if k != "datum" and v else v) for k, v in z.items()} for z in zeilen]


def profile() -> list[str]:
    return werkzeuge()["gemeinsam"].vorhandene_profile()


def _profil_pruefen(profil: str) -> None:
    if profil not in profile():
        raise NichtGefunden(f"Portfolio {profil} gibt es nicht.")


def kennzahlen(profil: str, bench: list[dict] | None = None) -> dict:
    w = werkzeuge()
    k = w["bewertung"].kennzahlen(profil, benchmark() if bench is None else bench)
    k = dict(k)
    portfolio = k.pop("portfolio")
    k["startdatum"] = portfolio["startdatum"]
    k["verarbeitet_bis"] = portfolio["verarbeitet_bis"]
    k["hoechststand"] = portfolio["hoechststand"]
    k["anzahl_positionen"] = len(portfolio["positionen"])
    k["offene_orders"] = len(portfolio["offene_orders"])
    return zahl(k)


def nav_reihen() -> dict:
    w = werkzeuge()
    reihen = {}
    for profil in profile():
        reihen[profil] = [{k: (_num(v) if k not in ("datum", "status") else v) for k, v in z.items()}
                          for z in w["bewertung"].nav_lesen(profil)]
    bench = [{k: (_num(v) if k != "datum" else v) for k, v in z.items()}
             for z in w["gemeinsam"].csv_lesen(repo() / "data" / "benchmark.csv")]
    return {"profile": reihen, "benchmark": bench}


def _markt_aus_speicher(portfolio: dict):
    """Letzte gespeicherte Schlusskurse bis zum Verarbeitungsstand (keine Abfrage)."""
    w = werkzeuge()
    kurse, limits, g = w["kurse"], w["limits"], w["gemeinsam"]
    stand = date.fromisoformat(portfolio["verarbeitet_bis"])
    preise, datum_je_ticker = {}, {}
    benoetigt = {p["basiswert"] for p in portfolio["positionen"]}
    if any(kurse.waehrung(t) != "EUR" for t in benoetigt):
        benoetigt.add(g.projekt()["devisen_ticker"])
    for ticker in benoetigt:
        kerzen = kurse.gespeicherte_historie(ticker)
        tage = [d for d in kerzen if d <= stand]
        if tage:
            preise[ticker] = kerzen[max(tage)].close
            datum_je_ticker[ticker] = max(tage).isoformat()
    eurusd = preise.get(g.projekt()["devisen_ticker"])
    return limits.Markt(kurse=preise, eurusd=eurusd, datum=stand + timedelta(days=1)), datum_je_ticker


def portfolio(profil: str) -> dict:
    _profil_pruefen(profil)
    w = werkzeuge()
    g, limits = w["gemeinsam"], w["limits"]
    daten = g.portfolio_laden(profil)
    grenzen = {k: float(v) for k, v in g.limits_fuer(profil).items()}
    markt, kursdatum = _markt_aus_speicher(daten)
    bewertung = None
    try:
        bewertung = limits.portfolio_bewerten(daten, markt)
    except Exception:  # fehlende Kurse: Positionen ohne Marktwert anzeigen
        bewertung = None
    positionen = []
    for position in daten["positionen"]:
        bewertet = next((p for p in (bewertung or {}).get("positionen", []) if p["id"] == position["id"]), None)
        positionen.append({
            **zahl(position),
            "kurs": zahl(bewertet["kurs"]) if bewertet else None,
            "kurs_datum": kursdatum.get(position["basiswert"]),
            "wert_eur": zahl(bewertet["wert_eur"]) if bewertet else None,
            "hebel_aktuell": zahl(bewertet["hebel"]) if bewertet else None,
            "einsatz_eur": _num(position.get("einsatz")),
        })
    nav = w["bewertung"].nav_lesen(profil)
    letzter = nav[-1] if nav else {}
    einzel = {}
    if bewertung:
        for p in bewertung["positionen"]:
            einzel[p["schluessel"]] = einzel.get(p["schluessel"], Decimal(0)) + p["wert_eur"]
    groesste = max(einzel.values(), default=Decimal(0))
    nav_wert = bewertung["nav"] if bewertung else None
    drawdown = _num(letzter.get("drawdown")) or 0.0
    auslastung = [
        {"regel": "Zertifikate-Anteil", "ist": _num(letzter.get("zertifikate_anteil")) or 0.0,
         "grenze": grenzen["max_anteil_zertifikate"], "art": "max", "einheit": "%"},
        {"regel": "Gesamt-Exposure", "ist": _num(letzter.get("exposure")) or 0.0,
         "grenze": grenzen["max_exposure"], "art": "max", "einheit": "x"},
        {"regel": "Größte Einzelposition", "ist": float(groesste / nav_wert) if nav_wert else 0.0,
         "grenze": grenzen["max_einzelposition"], "art": "max", "einheit": "%"},
        {"regel": "Cashquote", "ist": _num(letzter.get("cashquote")) if letzter else 1.0,
         "grenze": grenzen["min_cashquote"], "art": "min", "einheit": "%"},
        {"regel": "Drawdown (Stufe 1)", "ist": abs(drawdown), "grenze": abs(grenzen["drawdown_stufe1"]),
         "art": "max", "einheit": "%"},
        {"regel": "Drawdown (Stufe 2)", "ist": abs(drawdown), "grenze": abs(grenzen["drawdown_stufe2"]),
         "art": "max", "einheit": "%"},
    ]
    strategie = repo() / "strategie" / f"{profil}.md"
    return {
        "profil": profil,
        "portfolio": {k: zahl(v) for k, v in daten.items() if k not in ("positionen",)},
        "positionen": positionen,
        "bewertung": zahl({k: v for k, v in bewertung.items() if k != "positionen"}) if bewertung else None,
        "kennzahlen": kennzahlen(profil),
        "grenzen": grenzen,
        "auslastung": auslastung,
        "max_risiko_trade": grenzen["max_risiko_trade"] / (2 if int(daten.get("drawdown_stufe", 0)) >= 1 else 1),
        "letzter_tageswert": {k: _num(v) if k not in ("datum", "status") else v for k, v in letzter.items()},
        "strategie": strategie.read_text(encoding="utf-8") if strategie.exists() else None,
    }


def trades(profil: str) -> list[dict]:
    _profil_pruefen(profil)
    w = werkzeuge()
    zahlen = {"stueck", "kurs", "kurs_basiswert", "hebel", "spread_eur", "gebuehr_eur", "betrag_eur", "cash_danach",
              "devisenkurs", "stop", "kursziel"}
    return [{k: (_num(v) if k in zahlen else v) for k, v in z.items()} | {"profil": profil}
            for z in w["gemeinsam"].trades_lesen(profil)]


def alle_trades() -> list[dict]:
    zeilen = []
    for profil in profile():
        zeilen += trades(profil)
    return zeilen


def limit_protokoll() -> dict[str, dict]:
    w = werkzeuge()
    alle = {}
    for profil in profile():
        for trade_id, eintrag in w["gemeinsam"].limit_protokoll(profil).items():
            alle[f"{profil}:{trade_id}"] = eintrag
    return alle


# --------------------------------------------------------------------------
# Journal und Entscheidungen


def _block(block: dict) -> dict:
    return {**{k: v for k, v in block.items() if k != "zeit"},
            "zeit": block["zeit"].isoformat() if block.get("zeit") else None}


def journal() -> list[dict]:
    w = werkzeuge()
    bloecke = w["gemeinsam"].journal_bloecke()
    zeilen = alle_trades()
    je_journal: dict[str, list[dict]] = {}
    for zeile in zeilen:
        if zeile["journal_id"]:
            je_journal.setdefault(zeile["journal_id"], []).append(zeile)
    offen = {(p, pos["id"]) for p in profile() for pos in w["gemeinsam"].portfolio_laden(p)["positionen"]}
    marktwerte = _marktwerte_offen()
    orders = {(p, o["journal_id"]) for p in profile() for o in w["gemeinsam"].portfolio_laden(p)["offene_orders"]}
    ergebnis = []
    for block in bloecke:
        eintrag = _block(block)
        eintrag["verweise"] = sorted(set(re.findall(r"J-\d{8}-\d{2}", block["text"])) - {block["id"]})
        if block["art"] == "J":
            eigene = je_journal.get(block["id"], [])
            eintrag["trades"] = [z["trade_id"] for z in eigene]
            eintrag["status"] = _status(block, eigene, offen, orders)
            eintrag["ergebnis_eur"], eintrag["ergebnis_art"] = _ergebnis(eigene, zeilen, marktwerte)
        ergebnis.append(eintrag)
    return ergebnis


def _status(block: dict, eigene: list[dict], offen: set, orders: set) -> str:
    profil = block.get("portfolio")
    if (profil, block["id"]) in orders:
        return "vorgemerkt"
    kaeufe = [z for z in eigene if z["aktion"] == "kauf"]
    verkaeufe = [z for z in eigene if z["aktion"] == "verkauf" and z["grund"] == "order"]
    if kaeufe:
        if any((z["profil"], z["position_id"]) in offen for z in kaeufe):
            return "offen"
        return "geschlossen"
    if verkaeufe:
        return "verkauf"
    if any(z["aktion"] in ("verfall",) for z in eigene):
        return "verfallen"
    if any(z["aktion"] in ("storno",) for z in eigene):
        return "storniert"
    if any(z["aktion"] == "aenderung" for z in eigene):
        return "änderung"
    return "ohne ausführung"


def _marktwerte_offen() -> dict[tuple[str, str], float]:
    """Marktwerte offener Positionen (Bewertung durch tools/limits.py zum letzten Schlusskurs)."""
    werte = {}
    for profil in profile():
        daten = werkzeuge()["gemeinsam"].portfolio_laden(profil)
        if not daten["positionen"]:
            continue
        try:
            markt, _ = _markt_aus_speicher(daten)
            bewertung = werkzeuge()["limits"].portfolio_bewerten(daten, markt)
        except Exception:  # fehlende Kurse: kein unrealisiertes Ergebnis
            logging.getLogger("stockmaster").warning("Bewertung offener Positionen von %s nicht möglich", profil)
            continue
        for position in bewertung["positionen"]:
            werte[(profil, position["id"])] = float(position["wert_eur"])
    return werte


def _ergebnis(eigene: list[dict], alle: list[dict], marktwerte: dict) -> tuple[float | None, str | None]:
    """Realisiert (Summe der Zahlungen) bzw. unrealisiert (zuzüglich Marktwert offener Positionen)."""
    positionen = {(z["profil"], z["position_id"]) for z in eigene if z["aktion"] == "kauf"}
    if not positionen:
        return None, None
    summe = sum(z["betrag_eur"] or 0 for z in alle if (z["profil"], z["position_id"]) in positionen
                and z["aktion"] in ("kauf", "verkauf", "dividende", "knockout"))
    offen = [marktwerte[p] for p in positionen if p in marktwerte]
    if offen:
        return round(summe + sum(offen), 2), "unrealisiert"
    return round(summe, 2), "realisiert"


def journal_eintrag(eintrag_id: str) -> dict:
    if not ID_MUSTER.match(eintrag_id):
        raise NichtGefunden("Ungültige ID.")
    alle = journal()
    eintrag = next((e for e in alle if e["id"] == eintrag_id), None)
    if eintrag is None:
        raise NichtGefunden(f"{eintrag_id} nicht gefunden.")
    zeilen = alle_trades()
    eigene = [z for z in zeilen if z["journal_id"] == eintrag_id]
    positionen = {(z["profil"], z["position_id"]) for z in eigene if z["aktion"] == "kauf"}
    folge = [z for z in zeilen if (z["profil"], z["position_id"]) in positionen and z["journal_id"] != eintrag_id
             or z["journal_id"] == eintrag_id]
    folge.sort(key=lambda z: z["zeit"])
    protokoll = limit_protokoll()
    def zahlen(werte: dict) -> dict:
        return {k: (v if isinstance(v, bool) else _num(v) if isinstance(v, str) else v) for k, v in werte.items()}

    schnappschuesse = []
    for z in eigene:
        pruef = protokoll.get(f"{z['profil']}:{z['trade_id']}")
        if pruef:
            schnappschuesse.append({"trade_id": z["trade_id"], "profil": z["profil"], "zeit": pruef["zeit"],
                                    "kennzahlen": zahlen(pruef["kennzahlen"]), "grenzen": zahlen(pruef["grenzen"])})
    erwaehnt_in = [{"id": e["id"], "art": e["art"], "datei": e["datei"], "zeit": e["zeit"]}
                   for e in alle if eintrag_id in e.get("verweise", [])]
    reviews_mit = [r for r in reviews() if eintrag_id in (repo() / r["pfad"]).read_text(encoding="utf-8")]
    lessons_mit = [lesson for lesson in lessons() if eintrag_id in lesson["text"]]
    basiswert = next((z["basiswert"] for z in eigene if z["basiswert"]), None)
    kerzen = []
    if basiswert and eintrag.get("zeit"):
        start = date.fromisoformat(eintrag["zeit"][:10]) - timedelta(days=45)
        kerzen = [k for k in historie(basiswert) if k["datum"] >= start.isoformat()]
    position = None
    for profil, pid in positionen:
        offene = werkzeuge()["gemeinsam"].portfolio_laden(profil)["positionen"]
        position = next((zahl(p) for p in offene if p["id"] == pid), position)
    return {**eintrag, "folge": folge, "limit_schnappschuesse": schnappschuesse, "erwaehnt_in": erwaehnt_in,
            "reviews": reviews_mit, "lessons": lessons_mit, "basiswert": basiswert, "kerzen": kerzen,
            "position": position}


# --------------------------------------------------------------------------
# Dokumente, Reviews, Lessons, Konfiguration


def _erlaubte_dokumente() -> dict[str, Path]:
    erlaubt = {}
    for wurzel, namen in ((framework(), FRAMEWORK_DOKUMENTE), (daten(), DATEN_DOKUMENTE)):
        for name in namen:
            pfad = wurzel / name
            if pfad.is_file():
                erlaubt[name] = pfad
    for ordner in ("strategie", "reviews"):
        for pfad in sorted((daten() / ordner).glob("*.md")):
            erlaubt[f"{ordner}/{pfad.name}"] = pfad
    return erlaubt


def dokumente() -> list[dict]:
    return [{"pfad": name, "titel": _titel(pfad), "groesse": pfad.stat().st_size}
            for name, pfad in _erlaubte_dokumente().items()]


def _titel(pfad: Path) -> str:
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        if zeile.startswith("# "):
            return zeile[2:].strip()
    return pfad.stem


def dokument(name: str) -> dict:
    erlaubt = _erlaubte_dokumente()
    if name not in erlaubt:
        raise NichtGefunden("Dokument nicht gefunden.")
    pfad = erlaubt[name].resolve()
    if not any(wurzel in pfad.parents for wurzel in (framework(), daten())) or erlaubt[name].is_symlink():
        raise NichtGefunden("Dokument nicht gefunden.")
    return {"pfad": name, "titel": _titel(pfad), "inhalt": pfad.read_text(encoding="utf-8")}


def reviews() -> list[dict]:
    ergebnis = []
    for pfad in sorted((repo() / "reviews").glob("*.md"), reverse=True):
        name = pfad.stem
        art = next((a for a in ("woche", "monat", "quartal", "stufe2") if a in name), "sonstige")
        ergebnis.append({"pfad": f"reviews/{pfad.name}", "titel": _titel(pfad), "art": art,
                         "zeitraum": name.split("_")[0]})
    return ergebnis


def lessons() -> list[dict]:
    datei = daten() / "lessons.md"
    if not datei.exists():
        return []
    eintraege, aktuell = [], None
    for zeile in datei.read_text(encoding="utf-8").splitlines():
        treffer = re.match(r"^## (L-\d{3})\s+(.*)$", zeile)
        if treffer:
            aktuell = {"id": treffer.group(1), "titel": treffer.group(2), "felder": {}, "text": zeile}
            eintraege.append(aktuell)
            continue
        if aktuell is None:
            continue
        aktuell["text"] += "\n" + zeile
        feld = re.match(r"^- ([^:]+):\s*(.*)$", zeile)
        if feld:
            aktuell["felder"][feld.group(1).strip().lower()] = feld.group(2).strip()
    return eintraege


def konfiguration() -> dict:
    ergebnis = {}
    for name in ("profile", "kosten", "universum", "projekt"):
        datei = framework() / "config" / f"{name}.json"
        ergebnis[name] = json.loads(datei.read_text(encoding="utf-8")) if datei.exists() else None
    return ergebnis


def sperre() -> dict | None:
    g = werkzeuge()["gemeinsam"]
    daten = g.sperre_lesen()
    if not daten:
        return None
    return {"person": daten["person"], "start": daten["start"], "verwaist": g.sperre_verwaist(daten)}


def termine() -> list[dict]:
    return werkzeuge()["termine"].faellige_reviews()


# --------------------------------------------------------------------------
# Kurse, Rechner, Git, Prüfung


def kurs_ticker() -> list[dict]:
    w = werkzeuge()
    uni = w["kurse"].universum()
    namen = {**{t: v["name"] for t, v in uni["basiswerte"].items()},
             **{t: v["name"] for t, v in uni.get("sonstige_ticker", {}).items()}}
    ergebnis = []
    for meta in sorted((repo() / "data" / "historie").glob("*.json")):
        daten = json.loads(meta.read_text(encoding="utf-8"))
        ergebnis.append({"ticker": daten["ticker"], "name": namen.get(daten["ticker"]),
                         "bis": daten.get("abgedeckt_bis"), "von": daten.get("abgedeckt_von")})
    return ergebnis


def historie(ticker: str) -> list[dict]:
    if not TICKER_MUSTER.match(ticker):
        raise NichtGefunden("Ungültiger Ticker.")
    kurse = werkzeuge()["kurse"]
    if not kurse.historie_pfad(ticker).exists():
        raise NichtGefunden(f"Keine gespeicherten Kurse für {ticker}.")
    return [{"datum": k.datum.isoformat(), "open": float(k.open), "high": float(k.high), "low": float(k.low),
             "close": float(k.close), "dividende": float(k.dividende), "split": float(k.split)}
            for k in sorted(kurse.gespeicherte_historie(ticker).values(), key=lambda k: k.datum)]


def rechner_ko(richtung: str, kurs: Decimal, hebel: Decimal) -> dict:
    produkte = werkzeuge()["produkte"]
    k = produkte.ko_basispreis(richtung, kurs, hebel)
    wert = produkte.ko_wert(richtung, kurs, k)
    szenarien = []
    for prozent in (-10, -5, -2, -1, 0, 1, 2, 5, 10):
        s = kurs * (1 + Decimal(prozent) / 100)
        w = produkte.ko_wert(richtung, s, k)
        szenarien.append({"bewegung": prozent, "basiswert": s, "wert": w,
                          "veraenderung": (w / wert - 1) if wert else None,
                          "ausgeknockt": produkte.ko_ausgeknockt(richtung, k, s, s)})
    return zahl({"basispreis": k, "barriere": k, "wert": wert, "hebel": produkte.ko_hebel(richtung, kurs, k),
                 "abstand_barriere": abs(kurs - k) / kurs, "szenarien": szenarien,
                 "aufzinsung_30_tage": produkte.ko_aufzinsen(richtung, k, 30)})


def rechner_faktor(richtung: str, faktor: Decimal, kurse: list[Decimal]) -> dict:
    produkte = werkzeuge()["produkte"]
    werte = [Decimal("100")]
    for alt, neu in zip(kurse, kurse[1:], strict=False):
        werte.append(produkte.faktor_fortschreiben(richtung, faktor, werte[-1], alt, neu))
    basis = [kurs / kurse[0] * 100 for kurs in kurse]
    return zahl({"werte": werte, "basiswert_index": basis})


def git_log(anzahl: int = 100) -> list[dict]:
    roh = _git("log", f"-n{max(1, min(anzahl, 500))}", "--format=%x1e%H%x1f%h%x1f%aI%x1f%s", "--shortstat")
    eintraege = []
    for teil in roh.split("\x1e")[1:]:
        kopf, _, rest = teil.partition("\n")
        felder = kopf.split("\x1f")
        statistik = rest.strip()
        eintraege.append({"hash": felder[0], "kurz": felder[1], "zeit": felder[2], "text": felder[3],
                          "statistik": statistik})
    return eintraege


def git_commit(hash_wert: str) -> dict:
    if not re.match(r"^[0-9a-f]{7,40}$", hash_wert):
        raise NichtGefunden("Ungültiger Commit.")
    kopf = _git("show", "-s", "--format=%H%x1f%aI%x1f%B", hash_wert).split("\x1f")
    if len(kopf) < 3:
        raise NichtGefunden("Commit nicht gefunden.")
    diff = _git("show", "--format=", "--stat", "--patch", "--no-color", hash_wert)
    return {"hash": kopf[0], "zeit": kopf[1], "text": kopf[2].strip(), "diff": diff[:200_000],
            "gekuerzt": len(diff) > 200_000}


def pruefung() -> dict:
    """Führt tools/pruefe.py lesend in einem eigenen Prozess aus (Positivliste, Zeitlimit)."""
    umgebung = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "STOCKMASTER_DATA_DIR": str(daten()),
                "STOCKMASTER_FRAMEWORK_DIR": str(framework()), "HOME": "/tmp",  # noqa: S108 - leeres HOME für den Prüfprozess
                "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "safe.directory", "GIT_CONFIG_VALUE_0": str(daten()),
                "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        ergebnis = subprocess.run([sys.executable, "-E", "-s", str(framework() / "tools" / "pruefe.py")], cwd=daten(),
                                  capture_output=True, text=True, env=umgebung,
                                  timeout=einstellungen().pruefung_timeout_sekunden)
    except subprocess.TimeoutExpired:
        return {"ok": False, "befunde": [], "zusammenfassung": "Zeitlimit überschritten."}
    befunde = []
    for zeile in ergebnis.stdout.splitlines():
        treffer = re.match(r"^(FEHLER|WARNUNG) \[([^\]]+)\] (.*)$", zeile)
        if treffer:
            befunde.append({"stufe": treffer.group(1), "pruefung": treffer.group(2), "text": treffer.group(3)})
    zeilen = [z for z in ergebnis.stdout.splitlines() if z.startswith("Prüfung")]
    return {"ok": ergebnis.returncode == 0, "befunde": befunde,
            "zusammenfassung": zeilen[-1] if zeilen else (ergebnis.stderr.strip()[-500:] or "Keine Ausgabe.")}


# --------------------------------------------------------------------------
# Marktübersicht und News (geschrieben vom Hintergrunddienst über tools/kurse.py und tools/news.py)


def _cache_json(name: str) -> dict:
    datei = daten() / ".cache" / name
    if not datei.exists():
        return {}
    try:
        return json.loads(datei.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def markt() -> dict:
    stand = _cache_json("markt.json")
    eintraege = []
    for e in stand.get("eintraege", []):
        eintraege.append({**e, **{k: _num(e.get(k)) for k in ("kurs", "vortag", "veraenderung")}})
    return {"zeit": stand.get("zeit"), "quelle_konfiguriert": stand.get("quelle_konfiguriert"),
            "erfolgreich": stand.get("erfolgreich", 0), "anzahl": stand.get("anzahl", 0), "eintraege": eintraege}


def news(ticker: str | None = None, anzahl: int = 50, tage: int = 30) -> dict:
    if ticker is not None and not TICKER_MUSTER.match(ticker):
        raise NichtGefunden("Ungültiger Ticker.")
    meldungen = werkzeuge()["news"].gespeicherte(tage)
    if ticker:
        meldungen = [m for m in meldungen if ticker in m.get("ticker", [])]
    return {"stand": _cache_json("news_stand.json").get("zeit"), "meldungen": meldungen[:anzahl]}
