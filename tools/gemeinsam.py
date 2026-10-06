"""Gemeinsame Hilfsfunktionen für alle Werkzeuge in tools/.

Geldbeträge sind Decimal und auf Cent gerundet, Stückzahlen haben bis zu
6 Nachkommastellen. Zeiten gelten in Europe/Berlin und werden im ISO-Format
mit Zeitzone gespeichert. Alle Schreibvorgänge sind atomar.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import tempfile
from datetime import date, datetime, time, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Berlin")
PROFILE = ("defensiv", "ausgewogen", "aggressiv")
ZERTIFIKATE = ("ko", "faktor")
AKTIEN = ("aktie", "etf")

TRADE_FELDER = [
    "trade_id", "zeit", "order_id", "position_id", "aktion", "typ", "richtung",
    "ticker", "basiswert", "stueck", "kurs", "kurs_basiswert", "hebel",
    "spread_eur", "gebuehr_eur", "betrag_eur", "cash_danach", "kursquelle",
    "kurs_zeit", "journal_id", "grund",
    # Ergänzungen gegenüber AUFTRAG_PHASE1.md (siehe STATUS.md, Entscheidungen):
    "devisenkurs", "stop", "kursziel", "bemerkung",
]

NAV_FELDER = [
    "datum", "cash", "positionswert", "portfoliowert", "hoechststand",
    "drawdown", "drawdown_stufe", "exposure", "cashquote",
    "zertifikate_anteil", "status",
]


class Fehler(Exception):
    """Fachlicher Fehler mit verständlicher deutscher Meldung."""


class KursFehler(Fehler):
    """Kein oder kein verlässlicher Kurs verfügbar."""


# --------------------------------------------------------------------------
# Pfade und Zeit


def root() -> Path:
    """Projektwurzel; in Tests über BOERSE_ROOT umlenkbar."""
    umgebung = os.environ.get("BOERSE_ROOT")
    if umgebung:
        return Path(umgebung)
    return Path(__file__).resolve().parent.parent


def pfad(*teile: str) -> Path:
    return root().joinpath(*teile)


def jetzt() -> datetime:
    """Aktuelle Zeit in Europe/Berlin (Tests ersetzen diese Funktion).

    Bewusst nicht über Umgebung oder Kommandozeile setzbar: kein Backdating.
    """
    return datetime.now(TZ).replace(microsecond=0)


def heute() -> date:
    return jetzt().date()


def iso(zeitpunkt: datetime) -> str:
    return zeitpunkt.astimezone(TZ).isoformat()


def zeit_lesen(text: str) -> datetime:
    zeitpunkt = datetime.fromisoformat(text)
    if zeitpunkt.tzinfo is None:
        zeitpunkt = zeitpunkt.replace(tzinfo=TZ)
    return zeitpunkt.astimezone(TZ)


def datum_lesen(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise Fehler(f"Ungültiges Datum '{text}', erwartet JJJJ-MM-TT.") from exc


def tage(von: date, bis: date):
    """Alle Kalendertage von 'von' bis einschließlich 'bis'."""
    tag = von
    while tag <= bis:
        yield tag
        tag += timedelta(days=1)


def uhrzeit(text: str) -> time:
    stunde, minute = text.split(":")
    return time(int(stunde), int(minute))


# --------------------------------------------------------------------------
# Zahlen


def D(wert) -> Decimal:
    """Wandelt einen Wert verlustfrei in Decimal um (None bleibt None)."""
    if wert is None or wert == "":
        return None
    if isinstance(wert, Decimal):
        return wert
    if isinstance(wert, float):
        return Decimal(repr(wert))
    return Decimal(str(wert))


def geld(wert) -> Decimal:
    """Rundet kaufmännisch auf Cent."""
    return D(wert).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def stueck_runden(wert) -> Decimal:
    """Stückzahl auf 6 Nachkommastellen, abgerundet (nie mehr als bezahlt)."""
    return D(wert).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)


def param(wert) -> Decimal:
    """Rechengrößen wie Basispreise und Faktor-Werte: 8 Nachkommastellen."""
    return D(wert).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)


def text(wert) -> str:
    """Zahl für Dateien als Text (ohne Exponentenschreibweise)."""
    if wert is None:
        return ""
    if isinstance(wert, Decimal):
        return format(wert, "f")
    return str(wert)


# --------------------------------------------------------------------------
# Dateien


def atomar_schreiben(ziel: Path, inhalt: str) -> None:
    ziel = Path(ziel)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=ziel.parent, prefix=f".{ziel.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as datei:
            datei.write(inhalt)
        os.replace(temp, ziel)
    except BaseException:
        if os.path.exists(temp):
            os.unlink(temp)
        raise


def _json_default(wert):
    if isinstance(wert, Decimal):
        return text(wert)
    if isinstance(wert, (date, datetime)):
        return wert.isoformat()
    raise TypeError(f"Nicht serialisierbar: {type(wert)}")


def json_lesen(datei: Path):
    with open(datei, encoding="utf-8") as handle:
        return json.load(handle)


def json_schreiben(datei: Path, daten) -> None:
    atomar_schreiben(datei, json.dumps(daten, ensure_ascii=False, indent=2,
                                       default=_json_default) + "\n")


def csv_lesen(datei: Path) -> list[dict]:
    datei = Path(datei)
    if not datei.exists():
        return []
    with open(datei, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _csv_text(felder: list[str], zeilen: list[dict]) -> str:
    puffer = io.StringIO()
    schreiber = csv.DictWriter(puffer, fieldnames=felder, lineterminator="\n")
    schreiber.writeheader()
    for zeile in zeilen:
        schreiber.writerow({k: text(zeile.get(k)) for k in felder})
    return puffer.getvalue()


def csv_schreiben(datei: Path, felder: list[str], zeilen: list[dict]) -> None:
    atomar_schreiben(datei, _csv_text(felder, zeilen))


def csv_anhaengen(datei: Path, felder: list[str], neue: list[dict]) -> None:
    """Hängt Zeilen an; bestehender Inhalt bleibt Byte für Byte erhalten."""
    datei = Path(datei)
    if datei.exists() and datei.stat().st_size > 0:
        bisher = datei.read_text(encoding="utf-8")
        if not bisher.endswith("\n"):
            bisher += "\n"
        anhang = _csv_text(felder, neue).split("\n", 1)[1]
        atomar_schreiben(datei, bisher + anhang)
    else:
        csv_schreiben(datei, felder, neue)


# --------------------------------------------------------------------------
# Konfiguration


def config(name: str) -> dict:
    return json_lesen(pfad("config", f"{name}.json"))


def limits_fuer(profil: str) -> dict:
    profile = config("profile")["profile"]
    if profil not in profile:
        raise Fehler(f"Unbekanntes Profil '{profil}'. Erlaubt: {', '.join(PROFILE)}.")
    return {k: D(v) for k, v in profile[profil].items()}


def kosten() -> dict:
    return config("kosten")


def projekt() -> dict:
    return config("projekt")


def spread(typ: str) -> Decimal:
    return D(kosten()["spread"][typ])


def gebuehr() -> Decimal:
    return geld(kosten()["gebuehr_je_order"])


# --------------------------------------------------------------------------
# Portfolios und Logbücher


def portfolio_pfad(profil: str) -> Path:
    return pfad("portfolios", f"{profil}.json")


def portfolio_laden(profil: str) -> dict:
    datei = portfolio_pfad(profil)
    if not datei.exists():
        raise Fehler(f"Portfolio '{profil}' ist nicht initialisiert (tools/init.py).")
    return json_lesen(datei)


def portfolio_speichern(portfolio: dict) -> None:
    json_schreiben(portfolio_pfad(portfolio["profil"]), portfolio)


def vorhandene_profile() -> list[str]:
    return [p for p in PROFILE if portfolio_pfad(p).exists()]


def naechste_id(portfolio: dict, art: str) -> str:
    praefix = {"order": "O", "position": "P", "trade": "T"}[art]
    zaehler = portfolio.setdefault("zaehler", {"order": 0, "position": 0, "trade": 0})
    zaehler[art] = int(zaehler.get(art, 0)) + 1
    return f"{praefix}-{zaehler[art]:04d}"


def trades_pfad(profil: str) -> Path:
    return pfad("trades", f"{profil}.csv")


def trades_lesen(profil: str) -> list[dict]:
    return csv_lesen(trades_pfad(profil))


class Buchungslauf:
    """Sammelt Trade-Zeilen und schreibt sie zusammen mit dem Portfolio."""

    def __init__(self, portfolio: dict):
        self.portfolio = portfolio
        self.zeilen: list[dict] = []
        self.limit_eintraege: list[dict] = []
        self.meldungen: list[str] = []

    def trade(self, **felder) -> dict:
        zeile = {k: "" for k in TRADE_FELDER}
        zeile.update({k: v for k, v in felder.items() if v is not None})
        zeile["trade_id"] = naechste_id(self.portfolio, "trade")
        zeile["cash_danach"] = text(geld(self.portfolio["cash"]))
        for schluessel, wert in list(zeile.items()):
            if isinstance(wert, datetime):
                zeile[schluessel] = iso(wert)
            elif isinstance(wert, date):
                zeile[schluessel] = wert.isoformat()
            else:
                zeile[schluessel] = text(wert)
        self.zeilen.append(zeile)
        return zeile

    def limits(self, trade_id: str, zeitpunkt: datetime, kennzahlen: dict, grenzen: dict) -> None:
        """Merkt die bei einer Ausführung geprüften Kennzahlen für data/limits/ vor."""
        self.limit_eintraege.append({"trade_id": trade_id, "zeit": iso(zeitpunkt),
                                     "kennzahlen": kennzahlen, "grenzen": grenzen})

    def speichern(self) -> None:
        profil = self.portfolio["profil"]
        if self.zeilen:
            csv_anhaengen(trades_pfad(profil), TRADE_FELDER, self.zeilen)
        if self.limit_eintraege:
            datei = pfad("data", "limits", f"{profil}.jsonl")
            bisher = datei.read_text(encoding="utf-8") if datei.exists() else ""
            neu = "".join(json.dumps(e, default=_json_default, ensure_ascii=False) + "\n"
                          for e in self.limit_eintraege)
            atomar_schreiben(datei, bisher + neu)
        portfolio_speichern(self.portfolio)
        self.zeilen = []
        self.limit_eintraege = []


def limit_protokoll(profil: str) -> dict[str, dict]:
    datei = pfad("data", "limits", f"{profil}.jsonl")
    if not datei.exists():
        return {}
    eintraege = {}
    for zeile in datei.read_text(encoding="utf-8").splitlines():
        if zeile.strip():
            eintrag = json.loads(zeile)
            eintraege[eintrag["trade_id"]] = eintrag
    return eintraege


def cash(portfolio: dict) -> Decimal:
    return D(portfolio["cash"])


def cash_buchen(portfolio: dict, betrag) -> None:
    portfolio["cash"] = text(geld(cash(portfolio) + geld(betrag)))


# --------------------------------------------------------------------------
# Journal und Session-Sperre

JOURNAL_KOPF = re.compile(r"^###\s+(J-\d{8}-\d{2})\s*\|\s*([^|]+?)\s*\|\s*(.+?)\s*$")
JOURNAL_ZEIT = re.compile(r"^-\s*Zeit:\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})")
JOURNAL_DATEI = re.compile(r"^(\d{4}-\d{2}-\d{2})_([a-z0-9äöüß-]+)\.md$")


def journal_eintraege() -> dict[str, dict]:
    """Liest alle Journal-Einträge: ID -> {datei, person, zeit, portfolio}."""
    eintraege: dict[str, dict] = {}
    ordner = pfad("journal")
    if not ordner.exists():
        return eintraege
    for datei in sorted(ordner.glob("*.md")):
        treffer = JOURNAL_DATEI.match(datei.name)
        person = treffer.group(2) if treffer else None
        aktuell = None
        for zeile in datei.read_text(encoding="utf-8").splitlines():
            kopf = JOURNAL_KOPF.match(zeile.strip())
            if kopf:
                aktuell = {"id": kopf.group(1), "datei": datei.name, "person": person,
                           "portfolio": kopf.group(2).strip().lower(),
                           "instrument": kopf.group(3), "zeit": None,
                           "doppelt": kopf.group(1) in eintraege}
                eintraege.setdefault(kopf.group(1), aktuell)
                if aktuell["doppelt"]:
                    eintraege[kopf.group(1)]["doppelt"] = True
                continue
            if aktuell and aktuell["zeit"] is None:
                zeit = JOURNAL_ZEIT.match(zeile.strip())
                if zeit:
                    aktuell["zeit"] = datetime.fromisoformat(
                        f"{zeit.group(1)}T{zeit.group(2)}").replace(tzinfo=TZ)
    return eintraege


def sperre_pfad() -> Path:
    return pfad("session.lock")


def sperre_lesen() -> dict | None:
    datei = sperre_pfad()
    if not datei.exists():
        return None
    daten = json_lesen(datei)
    daten["start_dt"] = zeit_lesen(daten["start"])
    return daten


def sperre_verwaist(sperre: dict, zeitpunkt: datetime | None = None) -> bool:
    zeitpunkt = zeitpunkt or jetzt()
    stunden = projekt()["sperre_stunden"]
    return zeitpunkt - sperre["start_dt"] >= timedelta(hours=stunden)


def aktive_sperre() -> dict:
    """Gibt die gültige Sperre zurück oder bricht mit Meldung ab."""
    sperre = sperre_lesen()
    if sperre is None:
        raise Fehler("Keine Session aktiv. Zuerst: python tools/session.py start --person <name>")
    if sperre_verwaist(sperre):
        raise Fehler(f"Die Session-Sperre von {sperre['person']} ist verwaist "
                     f"(seit {sperre['start']}). Neue Session starten.")
    return sperre
