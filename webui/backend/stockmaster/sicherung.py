"""Sicherung und Wiederherstellung des Datenverzeichnisses (tar.gz inklusive lokalem Git).

Inhalt einer Sicherung:
- MANIFEST.json (Format, Zeit, Framework-Version, Spielstand-Commit)
- spielstand/ (das Datenverzeichnis mit .git, ohne Zwischenspeicher)
- app/einstellungen.json (Einstellungen ohne Secrets)
- nur auf ausdrücklichen Wunsch: app/geheimnisse.enc.json (Secrets, mit einem Sicherungspasswort per
  scrypt und AES-256-GCM verschlüsselt). Der Master-Schlüssel ist nie enthalten.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import secrets
import shutil
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import Field

from . import appdaten, auftraege
from .auftraege import AdminPflicht, admin_pflicht
from .auth import DB, Streng, audit, begrenzen
from .config import einstellungen

FORMAT = "stockmaster-sicherung"
VERSION = 1
AUSGESCHLOSSEN = {".cache", ".schreibsperre"}
RESTORE_PFAD = "/api/sicherung/wiederherstellen"
ERLAUBT = ("MANIFEST.json", "spielstand", "app/einstellungen.json", "app/geheimnisse.enc.json")
MAX_ENTPACKT = 8 * 1024 * 1024 * 1024
SCRYPT = {"n": 2**15, "r": 8, "p": 1}


class SicherungsFehler(Exception):
    pass


# --------------------------------------------------------------------------
# Verschlüsselung der optionalen Secrets


def _passwort_schluessel(passwort: str, salz: bytes) -> bytes:
    return hashlib.scrypt(passwort.encode("utf-8"), salt=salz, n=SCRYPT["n"], r=SCRYPT["r"], p=SCRYPT["p"],
                          maxmem=128 * 1024 * 1024, dklen=32)


def geheimnisse_verschluesseln(werte: dict[str, str], passwort: str) -> dict:
    salz, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    chiffrat = AESGCM(_passwort_schluessel(passwort, salz)).encrypt(
        nonce, json.dumps(werte).encode("utf-8"), FORMAT.encode())
    return {"kdf": "scrypt", **SCRYPT, "salz": base64.b64encode(salz).decode(), "nonce": base64.b64encode(nonce).decode(),
            "daten": base64.b64encode(chiffrat).decode()}


def geheimnisse_entschluesseln(paket: dict, passwort: str) -> dict[str, str]:
    try:
        schluessel = _passwort_schluessel(passwort, base64.b64decode(paket["salz"]))
        roh = AESGCM(schluessel).decrypt(base64.b64decode(paket["nonce"]), base64.b64decode(paket["daten"]),
                                         FORMAT.encode())
    except Exception:  # noqa: BLE001 - falsches Passwort oder beschädigt: keine Details
        raise SicherungsFehler("Sicherungspasswort falsch oder Secrets beschädigt.") from None
    return json.loads(roh)


# --------------------------------------------------------------------------
# Export


def _git_kopf(ordner: Path) -> str | None:
    ergebnis = subprocess.run(["git", "-c", f"safe.directory={ordner}", "-C", str(ordner), "rev-parse", "HEAD"],
                              capture_output=True, text=True)
    return ergebnis.stdout.strip() if ergebnis.returncode == 0 else None


def _filter(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    teile = Path(info.name).parts
    if len(teile) > 1 and teile[1] in AUSGESCHLOSSEN:
        return None
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    return info


def exportieren(ziel: Path, mit_geheimnissen: bool = False, passwort: str | None = None) -> dict:
    """Schreibt eine Sicherung nach `ziel`. Secrets nur mit Passwort (mindestens 12 Zeichen)."""
    e = einstellungen()
    if mit_geheimnissen and (not passwort or len(passwort) < 12):
        raise SicherungsFehler("Für eine Sicherung mit Secrets ist ein Sicherungspasswort mit mindestens 12 Zeichen nötig.")
    manifest = {"format": FORMAT, "version": VERSION, "erstellt": datetime.now(UTC).isoformat(timespec="seconds"),
                "framework_version": os.environ.get("SM_VERSION", "unbekannt"),
                "spielstand_commit": _git_kopf(e.daten_pfad), "mit_geheimnissen": mit_geheimnissen}
    ziel.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(ziel, "w:gz") as tar:
        def datei(name: str, inhalt: bytes) -> None:
            info = tarfile.TarInfo(name)
            info.size, info.mtime, info.mode = len(inhalt), int(datetime.now(UTC).timestamp()), 0o600
            tar.addfile(info, io.BytesIO(inhalt))

        datei("MANIFEST.json", json.dumps(manifest, indent=2).encode())
        tar.add(e.daten_pfad, arcname="spielstand", filter=_filter)
        einstellungen_app = {k: v for k, v in appdaten.laden().items()}
        datei("app/einstellungen.json", json.dumps(einstellungen_app, ensure_ascii=False, indent=2).encode())
        if mit_geheimnissen:
            paket = geheimnisse_verschluesseln(appdaten.geheimnisse_export(), passwort or "")
            datei("app/geheimnisse.enc.json", json.dumps(paket).encode())
    return manifest


# --------------------------------------------------------------------------
# Wiederherstellung


def _pruefen(tar: tarfile.TarFile) -> dict:
    manifest = None
    gesamt = 0
    for info in tar.getmembers():
        name = info.name
        pfad = Path(name)
        if pfad.is_absolute() or ".." in pfad.parts or name.startswith("/"):
            raise SicherungsFehler(f"Unzulässiger Pfad in der Sicherung: {name[:120]}")
        if not (info.isfile() or info.isdir()):
            raise SicherungsFehler(f"Unzulässiger Eintrag (nur Dateien und Ordner): {name[:120]}")
        if not any(name == e or name.startswith(e + "/") for e in ERLAUBT):
            raise SicherungsFehler(f"Unbekannter Eintrag in der Sicherung: {name[:120]}")
        gesamt += info.size
        if gesamt > MAX_ENTPACKT:
            raise SicherungsFehler("Die Sicherung ist entpackt zu groß.")
        if name == "MANIFEST.json":
            manifest = json.loads(tar.extractfile(info).read())
    if not manifest or manifest.get("format") != FORMAT:
        raise SicherungsFehler("Keine StockMaster-Sicherung (MANIFEST.json fehlt oder ist unbekannt).")
    if int(manifest.get("version", 0)) > VERSION:
        raise SicherungsFehler("Die Sicherung stammt aus einer neueren Version.")
    return manifest


def _leeren(ordner: Path) -> None:
    for eintrag in ordner.iterdir():
        if eintrag.name == "lost+found":
            continue
        if eintrag.is_dir() and not eintrag.is_symlink():
            shutil.rmtree(eintrag)
        else:
            eintrag.unlink()


def wiederherstellen(quelle: Path, einstellungen_uebernehmen: bool = True, geheimnisse_passwort: str | None = None) -> dict:
    """Ersetzt das Datenverzeichnis durch die Sicherung. Vorher wird der aktuelle Stand gesichert."""
    e = einstellungen()
    if auftraege.session_sperre_aktiv():
        raise SicherungsFehler("Eine Session läuft (Session-Sperre). Wiederherstellung erst danach.")
    zeitstempel = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    arbeit = appdaten.app_pfad("tmp", f"wiederherstellung-{zeitstempel}")
    arbeit.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(quelle, "r:gz") as tar:
            manifest = _pruefen(tar)
            tar.extractall(arbeit, filter="data")  # noqa: S202 - Einträge oben geprüft
        neu = arbeit / "spielstand"
        if not (neu / ".git").is_dir():
            raise SicherungsFehler("Die Sicherung enthält kein Spielstand-Git (spielstand/.git).")
        geheimnisse = None
        if geheimnisse_passwort and (arbeit / "app" / "geheimnisse.enc.json").exists():
            geheimnisse = geheimnisse_entschluesseln(
                json.loads((arbeit / "app" / "geheimnisse.enc.json").read_text()), geheimnisse_passwort)
        vorher = appdaten.app_pfad("sicherungen", f"vor-wiederherstellung-{zeitstempel}.tar.gz")
        appdaten.zustand_schreiben("wartung", {"seit": zeitstempel, "grund": "Wiederherstellung"})
        try:
            exportieren(vorher)
            _leeren(e.daten_pfad)
            for eintrag in neu.iterdir():
                shutil.move(str(eintrag), str(e.daten_pfad / eintrag.name))
            if einstellungen_uebernehmen and (arbeit / "app" / "einstellungen.json").exists():
                appdaten.alles_ersetzen(json.loads((arbeit / "app" / "einstellungen.json").read_text()))
            for name, wert in (geheimnisse or {}).items():
                if name in appdaten.GEHEIMNISSE:
                    appdaten.geheimnis_setzen(name, wert, quelle="sicherung")
        finally:
            appdaten.zustand_schreiben("wartung", {})
    finally:
        shutil.rmtree(arbeit, ignore_errors=True)
    return {"manifest": manifest, "vorher_gesichert": vorher.name, "geheimnisse": sorted(geheimnisse or {})}


# --------------------------------------------------------------------------
# API

router = APIRouter(prefix="/api/sicherung", tags=["sicherung"], dependencies=[Depends(admin_pflicht)])


class ExportDaten(Streng):
    mit_geheimnissen: bool = False
    sicherungs_passwort: str | None = Field(default=None, max_length=200)
    bestaetigt: bool = False


def _aufraeumen(pfad: Path) -> None:
    pfad.unlink(missing_ok=True)


@router.post("/export")
def export(daten: ExportDaten, request: Request, db: DB, admin: AdminPflicht, hinterher: BackgroundTasks) -> FileResponse:
    begrenzen(f"sicherung:{admin.id}", 10, 3600)
    if daten.mit_geheimnissen and not daten.bestaetigt:
        raise HTTPException(422, "Eine Sicherung mit Secrets bitte ausdrücklich bestätigen.")
    appdaten.app_pfad("tmp").mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=appdaten.app_pfad("tmp"), suffix=".tar.gz")
    os.close(fd)
    ziel = Path(name)
    try:
        manifest = exportieren(ziel, daten.mit_geheimnissen, daten.sicherungs_passwort)
    except SicherungsFehler as exc:
        ziel.unlink(missing_ok=True)
        raise HTTPException(422, str(exc)) from None
    audit(db, admin.id, "sicherung_export", request, meta={"mit_geheimnissen": daten.mit_geheimnissen,
                                                           "commit": manifest["spielstand_commit"]})
    db.commit()
    hinterher.add_task(_aufraeumen, ziel)
    datum = datetime.now(UTC).strftime("%Y-%m-%d")
    return FileResponse(ziel, media_type="application/gzip",
                        filename=f"stockmaster-sicherung-{datum}{'-mit-secrets' if daten.mit_geheimnissen else ''}.tar.gz")


@router.post("/wiederherstellen")
async def wiederherstellen_api(request: Request, db: DB, admin: AdminPflicht, einstellungen_uebernehmen: bool = True) -> dict:
    from .admin import bestaetigen

    begrenzen(f"wiederherstellung:{admin.id}", 10, 3600)
    bestaetigen(admin, request.headers.get("x-bestaetigung-passwort", ""))
    if auftraege.offener_lauf(db):
        raise HTTPException(409, "Ein Claude-Lauf ist aktiv. Wiederherstellung erst danach.")
    grenze = einstellungen().sicherung_max_mb * 1024 * 1024
    appdaten.app_pfad("tmp").mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=appdaten.app_pfad("tmp"), suffix=".upload.tar.gz")
    groesse = 0
    try:
        with os.fdopen(fd, "wb") as handle:
            async for stueck in request.stream():
                groesse += len(stueck)
                if groesse > grenze:
                    raise HTTPException(413, "Die Sicherung ist zu groß.")
                handle.write(stueck)
        try:
            ergebnis = wiederherstellen(Path(name), einstellungen_uebernehmen,
                                        request.headers.get("x-sicherung-passwort") or None)
        except (SicherungsFehler, tarfile.TarError, OSError, ValueError) as exc:
            meldung = str(exc) if isinstance(exc, SicherungsFehler) else "Die Datei ist keine gültige Sicherung (tar.gz)."
            raise HTTPException(422, meldung) from None
    finally:
        Path(name).unlink(missing_ok=True)
    from .spiel import lesen

    lesen.zuruecksetzen()
    audit(db, admin.id, "sicherung_wiederhergestellt", request,
          meta={"commit": ergebnis["manifest"].get("spielstand_commit"), "einstellungen": einstellungen_uebernehmen,
                "geheimnisse": len(ergebnis["geheimnisse"])})
    db.commit()
    return {"ok": True, **ergebnis}
