"""App-Konfiguration und Secrets im App-Verzeichnis (Standard /data-app), getrennt vom Spielstand.

- master.key (0600): 32 Byte, beim ersten Start zufällig erzeugt oder einmalig aus SM_SCHLUESSEL
  übernommen. Verschlüsselt TOTP-Geheimnisse und App-Secrets.
- einstellungen.json: alles, was ein Admin einstellen kann (ohne Secrets).
- geheimnisse.json: Secrets (Claude-Token, Kurs-API-Keys), je Wert AES-256-GCM mit einem aus dem
  Master-Schlüssel abgeleiteten Schlüssel (HKDF) und dem Namen als Zusatzdaten.

Secrets verlassen dieses Modul nur entschlüsselt an den Worker (für einen Lauf) und sonst nur als
"gesetzt/nicht gesetzt" mit den letzten vier Zeichen. Sie stehen nie im Spielstand-Git, im Export
(außer ausdrücklich passwortverschlüsselt), im Audit-Log oder in Logs.
"""

from __future__ import annotations

import base64
import copy
import json
import logging
import os
import secrets
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .config import SchluesselFehler, einstellungen, schluessel_dekodieren

log = logging.getLogger("stockmaster")

GEHEIMNISSE = {
    "claude_token": "Claude-Token",
    "kurs_key_finnhub": "Finnhub-API-Key",
    "kurs_key_twelvedata": "Twelve-Data-API-Key",
}
# Umgebungsvariablen, die beim Start einmalig übernommen werden (falls in der App noch nichts steht).
UMGEBUNG = {
    "claude_token": ("CLAUDE_CODE_OAUTH_TOKEN", "SM_CLAUDE_TOKEN"),
    "kurs_key_finnhub": ("FINNHUB_API_KEY", "SM_FINNHUB_KEY"),
    "kurs_key_twelvedata": ("TWELVEDATA_API_KEY", "TWELVE_DATA_API_KEY", "SM_TWELVEDATA_KEY"),
}
# Nach der Übernahme überflüssige Variablen im Stack (Hinweis in der UI).
UEBERFLUESSIG = ("SM_SCHLUESSEL", "SM_SCHLUESSEL_DATEI", "SPIEL_REPO", "SM_REPO_PFAD",
                 *[name for namen in UMGEBUNG.values() for name in namen])

VORGABEN_PROFILE = ("defensiv", "ausgewogen", "aggressiv")
VORGABEN_MAX_ZEICHEN = 4000
VORGABEN_HISTORIE_MAX = 300

STANDARD = {
    "version": 1,
    "claude": {
        "voreinstellungen": {"trading": {"modell": "opus", "aufwand": "high"},
                             "review": {"modell": "sonnet", "aufwand": "medium"}},
        "letzter_test": None,
    },
    "kursdaten": {"anbieter": "keiner", "intervall_offen_minuten": 5, "intervall_geschlossen_minuten": 60,
                  "letzter_test": None},
    "news": {"aktiv": True, "intervall_minuten": 15, "deaktiviert": [], "eigene": [], "user_agent": ""},
    "zeitplan": {"automatik": False, "zeitzone": "Europe/Berlin", "auftraggeber": "auftraggeber-a",
                 "termine": [{"wochentage": [0, 1, 2, 3, 4], "uhrzeit": "09:35", "art": "trading"},
                             {"wochentage": [0, 1, 2, 3, 4], "uhrzeit": "21:30", "art": "trading"}]},
    "migration": {"aus_umgebung": []},
    # Vorgaben der Auftraggeber je Portfolio (Entscheidung 39): weicher Text, sofort wirksam, jede Änderung eine Version.
    "vorgaben": {"profile": {p: {"text": "", "version": 0, "zeit": None, "von": None} for p in VORGABEN_PROFILE},
                 "historie": []},
}

_sperre = threading.RLock()


# --------------------------------------------------------------------------
# Dateien


def app_pfad(*teile: str) -> Path:
    return einstellungen().app_pfad.joinpath(*teile)


def _atomar(ziel: Path, inhalt: bytes, modus: int = 0o600) -> None:
    ziel.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=ziel.parent, prefix=f".{ziel.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as datei:
            datei.write(inhalt)
        os.chmod(temp, modus)
        os.replace(temp, ziel)
    except BaseException:
        if os.path.exists(temp):
            os.unlink(temp)
        raise


def _json_lesen(datei: Path) -> dict:
    if not datei.exists():
        return {}
    return json.loads(datei.read_text(encoding="utf-8"))


def _json_schreiben(datei: Path, daten: dict, modus: int = 0o600) -> None:
    _atomar(datei, (json.dumps(daten, ensure_ascii=False, indent=2) + "\n").encode("utf-8"), modus)


# --------------------------------------------------------------------------
# Master-Schlüssel


def schluessel_einrichten(totp_vorhanden: bool) -> list[str]:
    """Legt master.key an, falls es ihn nicht gibt. Gibt Meldungen für das Log zurück (ohne Werte).

    Reihenfolge: vorhandene Datei > SM_SCHLUESSEL/SM_SCHLUESSEL_DATEI (Migration, damit
    gespeicherte Zwei-Faktor-Geheimnisse gültig bleiben) > neuer Zufallsschlüssel. Gibt es
    Zwei-Faktor-Geheimnisse, aber keinen Schlüssel, wird kein neuer erzeugt (sonst wären alle
    Zugänge verloren), sondern der Start mit Erklärung abgebrochen.
    """
    e = einstellungen()
    datei = e.master_schluessel_datei
    if datei.exists():
        schluessel_dekodieren(datei.read_text(encoding="utf-8").strip())  # prüft Format
        if os.stat(datei).st_mode & 0o077:
            os.chmod(datei, 0o600)
        return []
    roh = None
    if e.schluessel_datei and e.schluessel_datei.exists():
        roh = e.schluessel_datei.read_text(encoding="utf-8").strip()
    elif e.schluessel:
        roh = e.schluessel
    if roh:
        wert = schluessel_dekodieren(roh)
        meldung = ("Master-Schlüssel aus SM_SCHLUESSEL in das App-Verzeichnis übernommen. Die Variable kann jetzt "
                   "aus dem Stack entfernt werden.")
    elif totp_vorhanden:
        raise SchluesselFehler(
            "Es gibt gespeicherte Zwei-Faktor-Geheimnisse, aber keinen Master-Schlüssel im App-Verzeichnis. "
            "SM_SCHLUESSEL einmalig mit dem bisherigen Wert setzen; er wird dann übernommen.")
    else:
        wert = secrets.token_bytes(32)
        meldung = "Neuer Master-Schlüssel im App-Verzeichnis erzeugt (Rechte 0600)."
    inhalt = (base64.b64encode(wert).decode() + "\n").encode()
    datei.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=datei.parent, prefix=".master.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(inhalt)
        os.chmod(temp, 0o600)
        try:
            os.link(temp, datei)  # atomar und nur, wenn noch niemand anderes den Schlüssel angelegt hat
        except FileExistsError:
            return []
    finally:
        os.unlink(temp)
    return [meldung]


def _app_schluessel() -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=b"stockmaster-app-geheimnisse-v1").derive(einstellungen().schluessel_bytes())


# --------------------------------------------------------------------------
# Einstellungen (ohne Secrets)


def _zusammenfuehren(basis: dict, wert: dict) -> dict:
    ergebnis = copy.deepcopy(basis)
    for schluessel, inhalt in wert.items():
        if isinstance(inhalt, dict) and isinstance(ergebnis.get(schluessel), dict):
            ergebnis[schluessel] = _zusammenfuehren(ergebnis[schluessel], inhalt)
        else:
            ergebnis[schluessel] = copy.deepcopy(inhalt)
    return ergebnis


def laden() -> dict:
    with _sperre:
        return _zusammenfuehren(STANDARD, _json_lesen(app_pfad("einstellungen.json")))


def bereich_speichern(bereich: str, werte: dict) -> dict:
    """Ersetzt die Felder eines Bereichs (nur übergebene Felder) und speichert atomar."""
    with _sperre:
        gespeichert = _json_lesen(app_pfad("einstellungen.json"))
        gespeichert[bereich] = {**gespeichert.get(bereich, {}), **copy.deepcopy(werte)}
        _json_schreiben(app_pfad("einstellungen.json"), gespeichert)
        return laden()


def vorgaben_aendern(profil: str, text: str, von: str) -> dict | None:
    """Neue Version der Vorgabe eines Portfolios; None, wenn der Text unverändert ist.

    Gilt sofort: Der nächste Lauf liest den Text beim Start. Die Historie behält die letzten Versionen mit Text,
    Zeitpunkt und Kennung (nie Name) des Administrators.
    """
    if profil not in VORGABEN_PROFILE:
        raise KeyError(profil)
    with _sperre:
        vorgaben = laden()["vorgaben"]
        aktuell = vorgaben["profile"][profil]
        if text == aktuell["text"]:
            return None
        eintrag = {"profil": profil, "version": aktuell["version"] + 1, "text": text,
                   "zeit": datetime.now(UTC).isoformat(timespec="seconds"), "von": von}
        profile = {**vorgaben["profile"], profil: {k: eintrag[k] for k in ("text", "version", "zeit", "von")}}
        bereich_speichern("vorgaben", {"profile": profile,
                                       "historie": (vorgaben["historie"] + [eintrag])[-VORGABEN_HISTORIE_MAX:]})
        return eintrag


def alles_ersetzen(daten: dict) -> None:
    """Nur für die Wiederherstellung einer Sicherung (ohne Secrets)."""
    with _sperre:
        _json_schreiben(app_pfad("einstellungen.json"), {k: v for k, v in daten.items() if k in STANDARD})


# --------------------------------------------------------------------------
# Secrets


def _geheim_datei() -> Path:
    return app_pfad("geheimnisse.json")


def geheimnis_setzen(name: str, wert: str, quelle: str = "app") -> None:
    if name not in GEHEIMNISSE:
        raise KeyError(name)
    nonce = secrets.token_bytes(12)
    chiffrat = AESGCM(_app_schluessel()).encrypt(nonce, wert.encode("utf-8"), name.encode())
    with _sperre:
        alle = _json_lesen(_geheim_datei())
        alle[name] = {"wert": "v1:" + base64.b64encode(nonce + chiffrat).decode(), "quelle": quelle,
                      "geaendert": datetime.now(UTC).isoformat(timespec="seconds")}
        _json_schreiben(_geheim_datei(), alle)


def geheimnis_loeschen(name: str) -> bool:
    with _sperre:
        alle = _json_lesen(_geheim_datei())
        if name not in alle:
            return False
        del alle[name]
        _json_schreiben(_geheim_datei(), alle)
        return True


def geheimnis(name: str) -> str | None:
    """Klartext, nur für den Worker bzw. Verbindungstests. Nie an Clients ausliefern oder loggen."""
    eintrag = _json_lesen(_geheim_datei()).get(name)
    if not eintrag:
        return None
    roh = base64.b64decode(eintrag["wert"].split(":", 1)[1])
    return AESGCM(_app_schluessel()).decrypt(roh[:12], roh[12:], name.encode()).decode("utf-8")


def geheimnis_info(name: str) -> dict:
    """Nur 'gesetzt' und die letzten 4 Zeichen."""
    eintrag = _json_lesen(_geheim_datei()).get(name)
    if not eintrag:
        return {"gesetzt": False, "letzte4": None, "geaendert": None, "quelle": None}
    try:
        wert = geheimnis(name) or ""
    except Exception:  # noqa: BLE001 - z. B. anderer Schlüssel nach Wiederherstellung
        return {"gesetzt": True, "letzte4": None, "geaendert": eintrag.get("geaendert"), "quelle": eintrag.get("quelle"),
                "unlesbar": True}
    return {"gesetzt": True, "letzte4": wert[-4:] if len(wert) >= 8 else None, "geaendert": eintrag.get("geaendert"),
            "quelle": eintrag.get("quelle")}


def alle_geheimnisse_klartext() -> dict[str, str]:
    """Für die Redaktion von Logs und die Prüfung vor Commits im Spielstand-Git."""
    ergebnis = {}
    for name in GEHEIMNISSE:
        try:
            wert = geheimnis(name)
        except Exception:  # noqa: BLE001
            wert = None
        if wert:
            ergebnis[name] = wert
    return ergebnis


def geheimnisse_export() -> dict[str, str]:
    """Rohdaten für den passwortverschlüsselten Export."""
    return alle_geheimnisse_klartext()


# --------------------------------------------------------------------------
# Migration aus Umgebungsvariablen


def aus_umgebung_uebernehmen() -> list[str]:
    """Übernimmt gesetzte Umgebungsvariablen einmalig, wenn in der App noch nichts steht. Meldungen ohne Werte."""
    meldungen, uebernommen = [], []
    for name, variablen in UMGEBUNG.items():
        wert = next((os.environ[v].strip() for v in variablen if os.environ.get(v, "").strip()), None)
        if not wert or geheimnis_info(name)["gesetzt"]:
            continue
        geheimnis_setzen(name, wert, quelle="umgebung")
        uebernommen.append(name)
        meldungen.append(f"{GEHEIMNISSE[name]} aus der Umgebung in die App-Konfiguration übernommen; "
                         "die Variable kann aus dem Stack entfernt werden.")
        if name.startswith("kurs_key_") and laden()["kursdaten"]["anbieter"] == "keiner":
            bereich_speichern("kursdaten", {"anbieter": name.removeprefix("kurs_key_")})
    if uebernommen:
        bisher = laden()["migration"]["aus_umgebung"]
        bereich_speichern("migration", {"aus_umgebung": sorted(set(bisher) | set(uebernommen))})
    return meldungen


def ueberfluessige_variablen() -> list[str]:
    """Gesetzte Umgebungsvariablen, die nicht mehr gelten (nur Namen, nie Werte)."""
    namen = [n for n in UEBERFLUESSIG if os.environ.get(n)]
    if einstellungen().master_schluessel_datei.exists():
        return namen
    return [n for n in namen if n not in ("SM_SCHLUESSEL", "SM_SCHLUESSEL_DATEI")]


# --------------------------------------------------------------------------
# Kleine Zustandsdateien (Worker-Herzschlag, letzte Tests)


def zustand_lesen(name: str) -> dict:
    try:
        return _json_lesen(app_pfad("zustand", f"{name}.json"))
    except (OSError, ValueError):
        return {}


def zustand_schreiben(name: str, daten: dict) -> None:
    _json_schreiben(app_pfad("zustand", f"{name}.json"), daten)
