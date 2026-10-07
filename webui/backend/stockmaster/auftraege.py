"""Aufträge an den Hintergrunddienst und die Läufe-API (Claude-Sessions mit Live-Log)."""

from __future__ import annotations

import json
import time
from datetime import timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import appdaten, claude_optionen
from .auth import DB, Angemeldet, Streng, audit, begrenzen
from .db import jetzt_utc, neue_sitzung, utc
from .modelle import Auftrag, Benutzer

LAUFARTEN = ("trading", "review", "testsession")
OFFEN = ("wartet", "laeuft")
LOG_MAX = 256_000


def admin_2fa(benutzer: Angemeldet) -> Benutzer:
    """Schreibende Einrichtung und Läufe: nur Admins mit aktiver Zwei-Faktor-Anmeldung."""
    if not benutzer.ist_admin:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nicht gefunden.")
    if not benutzer.totp_aktiv:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur mit aktiver Zwei-Faktor-Anmeldung.")
    return benutzer


Admin2FA = Annotated[Benutzer, Depends(admin_2fa)]


def log_pfad(auftrag_id: str):
    return appdaten.app_pfad("laeufe", f"{auftrag_id}.log")


def anlegen(db: Session, art: str, parameter: dict | None = None, erstellt_von: str | None = None,
            modell: str | None = None, aufwand: str | None = None, auftraggeber: str | None = None,
            ausloeser: str = "manuell") -> Auftrag:
    auftrag = Auftrag(art=art, parameter=json.dumps(parameter or {}, ensure_ascii=False), erstellt_von=erstellt_von,
                      modell=modell, aufwand=aufwand, auftraggeber=auftraggeber, ausloeser=ausloeser)
    db.add(auftrag)
    db.flush()
    return auftrag


def warten(auftrag_id: str, sekunden: float) -> Auftrag | None:
    """Wartet auf das Ergebnis des Workers (für kurze Verbindungstests)."""
    ende = time.monotonic() + sekunden
    while True:
        with neue_sitzung() as db:
            auftrag = db.get(Auftrag, auftrag_id)
            if auftrag is None or auftrag.status not in OFFEN or time.monotonic() >= ende:
                return auftrag
        time.sleep(0.5)


def warten_bis(auftrag_id: str, sekunden: float, bedingung) -> Auftrag | None:
    """Wartet, bis `bedingung(auftrag)` zutrifft, der Auftrag endet oder die Zeit abläuft."""
    ende = time.monotonic() + sekunden
    while True:
        with neue_sitzung() as db:
            auftrag = db.get(Auftrag, auftrag_id)
            if auftrag is None or auftrag.status not in OFFEN or bedingung(auftrag) or time.monotonic() >= ende:
                return auftrag
        time.sleep(0.5)


def anmeldecode_pfad(auftrag_id: str):
    """Übergabe des Anmeldecodes von der API an den Worker (0600, sofort nach dem Lesen gelöscht)."""
    return appdaten.app_pfad("tmp", f"anmeldung-{auftrag_id}.code")


def als_dict(a: Auftrag) -> dict:
    def zeit(wert):
        return utc(wert).isoformat() if wert else None

    return {"id": a.id, "art": a.art, "status": a.status, "meldung": a.meldung, "modell": a.modell,
            "aufwand": a.aufwand, "auftraggeber": a.auftraggeber, "ausloeser": a.ausloeser,
            "erstellt": zeit(a.erstellt), "begonnen": zeit(a.begonnen), "beendet": zeit(a.beendet),
            "pruefung_ok": a.pruefung_ok, "abbrechen": a.abbrechen,
            "ergebnis": json.loads(a.ergebnis) if a.ergebnis else None,
            "parameter": json.loads(a.parameter) if a.parameter else None}


def offener_lauf(db: Session) -> Auftrag | None:
    return db.scalar(select(Auftrag).where(Auftrag.art.in_(LAUFARTEN), Auftrag.status.in_(OFFEN)))


def letzter_lauf(db: Session) -> dict | None:
    lauf = db.scalar(select(Auftrag).where(Auftrag.art.in_(LAUFARTEN)).order_by(Auftrag.erstellt.desc()).limit(1))
    return als_dict(lauf) if lauf else None


def session_sperre_aktiv() -> dict | None:
    from .spiel import lesen

    sperre = lesen.sperre()
    return sperre if sperre and not sperre["verwaist"] else None


def lauf_pruefen(db: Session, art: str, modell: str, aufwand: str, auftraggeber: str) -> None:
    """Gemeinsame Prüfung für manuelle und geplante Läufe (HTTPException mit Klartext)."""
    from .spiel import lesen

    if art not in LAUFARTEN:
        raise HTTPException(422, "Unbekannte Laufart.")
    fehler = claude_optionen.pruefen(modell, aufwand)
    if fehler:
        raise HTTPException(422, fehler)
    erlaubt = lesen.konfiguration()["projekt"]["auftraggeber"]
    if auftraggeber not in erlaubt:
        raise HTTPException(422, f"Auftraggeber muss eine Kennung aus config/projekt.json sein ({', '.join(erlaubt)}).")
    if not appdaten.geheimnis_info("claude_token")["gesetzt"]:
        raise HTTPException(409, "Kein Claude-Token hinterlegt (Einrichtung → Claude).")
    if offener_lauf(db):
        raise HTTPException(409, "Es läuft bereits ein Claude-Lauf oder einer wartet auf den Start.")
    sperre = session_sperre_aktiv()
    if sperre:
        raise HTTPException(409, f"Session-Sperre von {sperre['person']} seit {sperre['start']} (tools/session.py).")


# --------------------------------------------------------------------------
# Läufe-API

router = APIRouter(prefix="/api/laeufe", tags=["laeufe"])


class LaufStart(Streng):
    art: Literal["trading", "review", "testsession"]
    auftraggeber: str = Field(max_length=40)
    modell: str | None = Field(default=None, max_length=100)
    aufwand: str | None = Field(default=None, max_length=20)
    bestaetigt: bool


@router.get("")
def liste(db: DB, _benutzer: Angemeldet, anzahl: Annotated[int, Query(ge=1, le=200)] = 30) -> list[dict]:
    laeufe = db.scalars(select(Auftrag).where(Auftrag.art.in_(LAUFARTEN)).order_by(Auftrag.erstellt.desc())
                        .limit(anzahl)).all()
    return [als_dict(a) for a in laeufe]


@router.get("/{auftrag_id}")
def einzeln(auftrag_id: str, db: DB, _benutzer: Angemeldet) -> dict:
    auftrag = db.get(Auftrag, auftrag_id)
    if auftrag is None or auftrag.art not in LAUFARTEN:
        raise HTTPException(404, "Lauf nicht gefunden.")
    return als_dict(auftrag)


@router.get("/{auftrag_id}/log")
def log(auftrag_id: str, db: DB, _benutzer: Angemeldet, ab: Annotated[int, Query(ge=0)] = 0) -> dict:
    auftrag = db.get(Auftrag, auftrag_id)
    if auftrag is None or auftrag.art not in LAUFARTEN:
        raise HTTPException(404, "Lauf nicht gefunden.")
    datei = log_pfad(auftrag_id)
    text, naechstes = "", ab
    if datei.exists():
        with open(datei, "rb") as handle:
            handle.seek(ab)
            roh = handle.read(LOG_MAX)
        # Nur vollständige UTF-8-Zeichen ausliefern.
        while roh:
            try:
                text = roh.decode("utf-8")
                break
            except UnicodeDecodeError:
                roh = roh[:-1]
        naechstes = ab + len(roh)
    return {"text": text, "naechstes": naechstes, "status": auftrag.status, "fertig": auftrag.status not in OFFEN}


@router.post("", status_code=201)
def starten(daten: LaufStart, request: Request, db: DB, admin: Admin2FA) -> dict:
    begrenzen(f"lauf:{admin.id}", 10, 3600)
    if not daten.bestaetigt:
        raise HTTPException(422, "Start bitte ausdrücklich bestätigen.")
    zweck = claude_optionen.optionen()["laufarten"][daten.art]["zweck"]
    vorgabe = appdaten.laden()["claude"]["voreinstellungen"][zweck]
    modell = daten.modell or vorgabe["modell"]
    aufwand = vorgabe["aufwand"] if daten.aufwand is None else daten.aufwand
    lauf_pruefen(db, daten.art, modell, aufwand, daten.auftraggeber)
    auftrag = anlegen(db, daten.art, {"einmalig_ueberschrieben": daten.modell is not None or daten.aufwand is not None},
                      erstellt_von=admin.id, modell=modell, aufwand=aufwand, auftraggeber=daten.auftraggeber)
    audit(db, admin.id, "lauf_gestartet", request, ziel=auftrag.id,
          meta={"art": daten.art, "modell": modell, "aufwand": aufwand or "standard", "auftraggeber": daten.auftraggeber})
    db.commit()
    return als_dict(auftrag)


@router.post("/{auftrag_id}/abbrechen")
def abbrechen(auftrag_id: str, request: Request, db: DB, admin: Admin2FA) -> dict:
    auftrag = db.get(Auftrag, auftrag_id)
    if auftrag is None or auftrag.art not in LAUFARTEN:
        raise HTTPException(404, "Lauf nicht gefunden.")
    if auftrag.status not in OFFEN:
        raise HTTPException(409, "Der Lauf ist bereits beendet.")
    if auftrag.status == "wartet":
        auftrag.status, auftrag.beendet, auftrag.meldung = "abgebrochen", jetzt_utc(), "Vor dem Start abgebrochen."
    auftrag.abbrechen = True
    audit(db, admin.id, "lauf_abgebrochen", request, ziel=auftrag.id)
    db.commit()
    return als_dict(auftrag)


def verwaiste_aufraeumen(db: Session, stunden: int = 3) -> int:
    """Läufe, deren Worker verschwunden ist (z. B. Neustart), als abgebrochen markieren."""
    grenze = jetzt_utc() - timedelta(hours=stunden)
    anzahl = 0
    for auftrag in db.scalars(select(Auftrag).where(Auftrag.status == "laeuft")).all():
        if utc(auftrag.begonnen) and utc(auftrag.begonnen) < grenze:
            auftrag.status, auftrag.beendet = "abgebrochen", jetzt_utc()
            auftrag.meldung = "Hintergrunddienst neu gestartet; Lauf abgebrochen."
            anzahl += 1
    db.commit()
    return anzahl
