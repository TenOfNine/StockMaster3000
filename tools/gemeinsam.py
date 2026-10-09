"""Gemeinsame Hilfsfunktionen für alle Werkzeuge in tools/.

Geldbeträge sind Decimal und auf Cent gerundet, Stückzahlen haben bis zu
6 Nachkommastellen. Zeiten gelten in Europe/Berlin und werden im ISO-Format
mit Zeitzone gespeichert. Alle Schreibvorgänge sind atomar; Anhängen ist über
eine Sperrdatei gegen parallele Prozesse (Session, Hintergrund-Abrufe) geschützt.

Pfade: Spielstand liegt im Datenverzeichnis (pfad(), STOCKMASTER_DATA_DIR),
Konfiguration und Regeln im Framework (framework_pfad()); siehe pfade.py.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import tempfile
import threading
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pfade
from pfade import Fehler

try:  # POSIX; unter Windows ohne Sperre (nur Entwicklung)
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

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


class KursFehler(Fehler):
    """Kein oder kein verlässlicher Kurs verfügbar."""


# --------------------------------------------------------------------------
# Pfade und Zeit


def root() -> Path:
    """Datenverzeichnis mit dem Spielstand (STOCKMASTER_DATA_DIR)."""
    return pfade.daten()


def pfad(*teile: str) -> Path:
    """Pfad im Datenverzeichnis (Spielstand)."""
    return pfade.daten_pfad(*teile)


def framework_pfad(*teile: str) -> Path:
    """Pfad im Framework (config/, regeln.md, STATUS.md, Vorlagen)."""
    return pfade.framework_pfad(*teile)


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


def _umask() -> int:
    maske = os.umask(0)
    os.umask(maske)
    return maske


def atomar_schreiben(ziel: Path, inhalt: str) -> None:
    ziel = Path(ziel)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=ziel.parent, prefix=f".{ziel.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as datei:
            datei.write(inhalt)
        # mkstemp legt 0600 an; Spieldateien sollen wie gewöhnliche Dateien die umask
        # beachten, damit z. B. die Web-UI sie lesend einbinden kann.
        os.chmod(temp, 0o666 & ~_umask())
        os.replace(temp, ziel)
    except BaseException:
        if os.path.exists(temp):
            os.unlink(temp)
        raise


_sperre_lokal = threading.RLock()
_sperre_tiefe = 0


@contextmanager
def schreibsperre():
    """Exklusive Sperre für Lesen-Ändern-Schreiben im Datenverzeichnis.

    Prozessübergreifend über flock auf .schreibsperre, innerhalb eines Prozesses
    wiedereintrittsfähig (verschachtelte Aufrufe blockieren sich nicht).
    """
    global _sperre_tiefe
    with _sperre_lokal:
        if _sperre_tiefe:
            _sperre_tiefe += 1
            try:
                yield
            finally:
                _sperre_tiefe -= 1
            return
        datei = pfad(".schreibsperre")
        datei.parent.mkdir(parents=True, exist_ok=True)
        with open(datei, "a", encoding="utf-8") as handle:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            _sperre_tiefe = 1
            try:
                yield
            finally:
                _sperre_tiefe = 0
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def text_anhaengen(datei: Path, neu: str) -> None:
    """Hängt Text an; bisheriger Inhalt bleibt Byte für Byte erhalten (unter Schreibsperre)."""
    datei = Path(datei)
    with schreibsperre():
        bisher = datei.read_text(encoding="utf-8") if datei.exists() else ""
        if bisher and not bisher.endswith("\n"):
            bisher += "\n"
        atomar_schreiben(datei, bisher + neu)


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
    """Hängt Zeilen an; bestehender Inhalt bleibt Byte für Byte erhalten (unter Schreibsperre)."""
    datei = Path(datei)
    with schreibsperre():
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
    return json_lesen(framework_pfad("config", f"{name}.json"))


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


# Die Vorlage aus init.py trägt diese Zeile; Claude ersetzt sie beim Ausformulieren (AP12 Punkt 2).
RICHTLINIE_VORLAGE_MARKE = "Vorlage aus tools/init.py"


def richtlinie_pfad(profil: str) -> Path:
    return pfad("strategie", f"{profil}.md")


def richtlinie_ausformuliert(profil: str) -> bool:
    """Anlagerichtlinie (regeln.md 11) vorhanden und nicht mehr die leere Vorlage."""
    datei = richtlinie_pfad(profil)
    return datei.exists() and RICHTLINIE_VORLAGE_MARKE not in datei.read_text(encoding="utf-8")


# Version der Standard-Anlagerichtlinien (config/richtlinien/). v2: Handeln ist der Normalfall (Umbau v2).
RICHTLINIE_STANDARD_VERSION = 2
RICHTLINIE_STANDARD_MUSTER = re.compile(r"Standard-Richtlinie(?: v(\d+))? aus config/richtlinien/")
RICHTLINIE_HISTORIE_UNVERAENDERT = ("Spielstart", "Standard-Update")


def richtlinie_standard_version(profil: str) -> int | None:
    """Version der Standard-Richtlinie, auf der strategie/<profil>.md beruht (None: keine Standard-Richtlinie)."""
    datei = richtlinie_pfad(profil)
    if not datei.exists():
        return None
    treffer = RICHTLINIE_STANDARD_MUSTER.search(datei.read_text(encoding="utf-8"))
    return None if treffer is None else int(treffer.group(1) or 1)


def richtlinie_historie(profil: str) -> list[list[str]]:
    """Zeilen der Änderungshistorie (Datum, Anlass, Änderung, Prüfkriterium) aus strategie/<profil>.md."""
    zeilen = []
    for zeile in richtlinie_pfad(profil).read_text(encoding="utf-8").splitlines():
        if re.match(r"^\|\s*\d{4}-\d{2}-\d{2}\s*\|", zeile):
            zeilen.append([z.strip() for z in zeile.strip().strip("|").split("|")])
    return zeilen


def richtlinie_unveraendert(profil: str) -> bool:
    """Reine Standard-Richtlinie: nie von Hand oder von Claude angepasst (nur Standardeinträge in der Historie)."""
    return richtlinie_standard_version(profil) is not None and all(
        len(z) > 1 and z[1] in RICHTLINIE_HISTORIE_UNVERAENDERT for z in richtlinie_historie(profil))


def richtlinien_veraltet() -> list[str]:
    """Unveränderte Standard-Richtlinien einer älteren Version (werden automatisch aktualisiert)."""
    return [p for p in PROFILE if richtlinie_ausformuliert(p) and richtlinie_unveraendert(p)
            and (richtlinie_standard_version(p) or 0) < RICHTLINIE_STANDARD_VERSION]


def richtlinien_offen() -> list[str]:
    """Profile ohne ausformulierte Anlagerichtlinie."""
    return [p for p in PROFILE if not richtlinie_ausformuliert(p)]


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
            neu = "".join(json.dumps(e, default=_json_default, ensure_ascii=False) + "\n"
                          for e in self.limit_eintraege)
            text_anhaengen(pfad("data", "limits", f"{profil}.jsonl"), neu)
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
SESSION_KOPF = re.compile(r"^###\s+(S-\d{8}-\d{2})\s*\|\s*Session\s*\|\s*(.+?)\s*$", re.I)
JOURNAL_ZEIT = re.compile(r"^-\s*Zeit:\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})")
JOURNAL_FELD = re.compile(r"^-\s*([^:]{1,60}):\s*(.*)$")
JOURNAL_DATEI = re.compile(r"^(\d{4}-\d{2}-\d{2})_([a-z0-9äöüß-]+)\.md$")


def _feldname(text: str) -> str:
    return text.strip().lower()


def journal_bloecke() -> list[dict]:
    """Alle Journal- (J-) und Session-Einträge (S-) in Dateireihenfolge.

    Je Eintrag: id, art (J/S), datei, datum, person, portfolio, instrument,
    zeit, felder (Name -> Text, Folgezeilen angehängt), text (Rohtext).
    """
    bloecke: list[dict] = []
    ordner = pfad("journal")
    if not ordner.exists():
        return bloecke
    for datei in sorted(ordner.glob("*.md")):
        treffer = JOURNAL_DATEI.match(datei.name)
        person = treffer.group(2) if treffer else None
        datum = treffer.group(1) if treffer else None
        aktuell = None
        feld = None
        for zeile in datei.read_text(encoding="utf-8").splitlines():
            bereinigt = zeile.strip()
            kopf_j = JOURNAL_KOPF.match(bereinigt)
            kopf_s = None if kopf_j else SESSION_KOPF.match(bereinigt)
            if kopf_j or kopf_s:
                aktuell = {"id": (kopf_j or kopf_s).group(1), "art": "J" if kopf_j else "S",
                           "datei": datei.name, "datum": datum, "person": person,
                           "portfolio": kopf_j.group(2).strip().lower() if kopf_j else None,
                           "instrument": kopf_j.group(3) if kopf_j else None,
                           "auftraggeber": kopf_s.group(2) if kopf_s else None,
                           "zeit": None, "felder": {}, "zeilen": [zeile]}
                bloecke.append(aktuell)
                feld = None
                continue
            if aktuell is None:
                continue
            if bereinigt.startswith("#"):
                aktuell = None  # andere Überschrift beendet den Eintrag
                continue
            aktuell["zeilen"].append(zeile)
            if aktuell["zeit"] is None:
                zeit = JOURNAL_ZEIT.match(bereinigt)
                if zeit:
                    aktuell["zeit"] = datetime.fromisoformat(
                        f"{zeit.group(1)}T{zeit.group(2)}").replace(tzinfo=TZ)
            treffer_feld = JOURNAL_FELD.match(bereinigt) if zeile.startswith("-") else None
            if treffer_feld:
                feld = _feldname(treffer_feld.group(1))
                aktuell["felder"][feld] = treffer_feld.group(2).strip()
            elif feld and bereinigt:
                aktuell["felder"][feld] = (aktuell["felder"][feld] + " " + bereinigt).strip()
    for block in bloecke:
        block["text"] = "\n".join(block.pop("zeilen")).rstrip()
    return bloecke


def journal_eintraege() -> dict[str, dict]:
    """Journal-Einträge (J-) nach ID: {datei, person, zeit, portfolio, felder, doppelt}."""
    eintraege: dict[str, dict] = {}
    for block in journal_bloecke():
        if block["art"] != "J":
            continue
        if block["id"] in eintraege:
            eintraege[block["id"]]["doppelt"] = True
            continue
        eintraege[block["id"]] = dict(block, doppelt=False)
    return eintraege


def session_eintraege() -> list[dict]:
    return [b for b in journal_bloecke() if b["art"] == "S"]


def spiel_pfad() -> Path:
    """spiel.json: Startdatum und Freigabe (geschrieben von tools/init.py)."""
    return pfad("spiel.json")


def spiel_lesen() -> dict:
    datei = spiel_pfad()
    return json_lesen(datei) if datei.exists() else {}


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
