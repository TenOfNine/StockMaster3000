"""Administration: nur für Admins; alle anderen erhalten 404."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import sicherheit as s
from .auth import DB, Streng, angemeldet, audit, begrenzen
from .db import jetzt_utc, utc
from .modelle import AuditEintrag, AuthSitzung, Benutzer


def admin_benutzer(benutzer: Annotated[Benutzer, Depends(angemeldet)]) -> Benutzer:
    if not benutzer.ist_admin:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nicht gefunden.")
    return benutzer


Admin = Annotated[Benutzer, Depends(admin_benutzer)]
router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(admin_benutzer)])


class BenutzerZeile(BaseModel):
    id: str
    email: str
    anzeigename: str
    kennung: str
    ist_admin: bool
    aktiv: bool
    totp_aktiv: bool
    passwortwechsel_noetig: bool
    gesperrt_bis: str | None
    erstellt: str


class NeuerBenutzer(Streng):
    email: EmailStr
    anzeigename: str = Field(min_length=1, max_length=80)
    passwort: str = Field(min_length=1, max_length=200, description="Passwort des Admins zur Bestätigung")


class Bestaetigung(Streng):
    passwort: str = Field(min_length=1, max_length=200)


class AdminRolle(Streng):
    passwort: str = Field(min_length=1, max_length=200)
    ist_admin: bool


class Aktiv(Streng):
    passwort: str = Field(min_length=1, max_length=200)
    aktiv: bool


class Einmalpasswort(BaseModel):
    benutzer: BenutzerZeile
    einmalpasswort: str


class AuditZeile(BaseModel):
    zeit: str
    akteur: str | None
    aktion: str
    ziel: str | None


def zeile(b: Benutzer) -> BenutzerZeile:
    return BenutzerZeile(id=b.id, email=b.email, anzeigename=b.anzeigename, kennung=b.kennung, ist_admin=b.ist_admin,
                         aktiv=b.aktiv, totp_aktiv=b.totp_aktiv, passwortwechsel_noetig=b.passwortwechsel_noetig,
                         gesperrt_bis=utc(b.gesperrt_bis).isoformat() if b.gesperrt_bis else None,
                         erstellt=utc(b.erstellt).isoformat())


def bestaetigen(admin: Benutzer, passwort: str) -> None:
    """Erneute Anmeldung (Passwort) für kritische Aktionen."""
    begrenzen(f"admin-bestaetigung:{admin.id}", 10, 60)
    if not s.passwort_pruefen(admin.passwort_hash, passwort):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Passwort zur Bestätigung ist falsch.")


def ziel_laden(db: Session, user_id: str) -> Benutzer:
    benutzer = db.get(Benutzer, user_id)
    if benutzer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Benutzer nicht gefunden.")
    return benutzer


def eindeutige_kennung(db: Session) -> str:
    while True:
        kennung = s.neue_kennung()
        if not db.scalar(select(Benutzer).where(Benutzer.kennung == kennung)):
            return kennung


@router.get("/benutzer", response_model=list[BenutzerZeile])
def benutzer_liste(db: DB) -> list[BenutzerZeile]:
    return [zeile(b) for b in db.scalars(select(Benutzer).order_by(Benutzer.erstellt)).all()]


@router.post("/benutzer", response_model=Einmalpasswort, status_code=201)
def benutzer_anlegen(daten: NeuerBenutzer, request: Request, db: DB, admin: Admin) -> Einmalpasswort:
    bestaetigen(admin, daten.passwort)
    email = daten.email.lower()
    if db.scalar(select(Benutzer).where(Benutzer.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Diese E-Mail-Adresse ist bereits vergeben.")
    passwort = s.einmalpasswort()
    neu = Benutzer(email=email, anzeigename=daten.anzeigename, kennung=eindeutige_kennung(db),
                   passwort_hash=s.passwort_hash(passwort), passwortwechsel_noetig=True)
    db.add(neu)
    db.flush()
    audit(db, admin.id, "benutzer_angelegt", request, ziel=neu.id)
    db.commit()
    return Einmalpasswort(benutzer=zeile(neu), einmalpasswort=passwort)


@router.post("/benutzer/{user_id}/passwort-zuruecksetzen", response_model=Einmalpasswort)
def passwort_zuruecksetzen(user_id: str, daten: Bestaetigung, request: Request, db: DB, admin: Admin) -> Einmalpasswort:
    bestaetigen(admin, daten.passwort)
    ziel = ziel_laden(db, user_id)
    passwort = s.einmalpasswort()
    ziel.passwort_hash = s.passwort_hash(passwort)
    ziel.passwortwechsel_noetig = True
    ziel.fehlversuche = 0
    ziel.gesperrt_bis = None
    db.execute(delete(AuthSitzung).where(AuthSitzung.user_id == ziel.id))
    audit(db, admin.id, "passwort_zurueckgesetzt", request, ziel=ziel.id)
    db.commit()
    return Einmalpasswort(benutzer=zeile(ziel), einmalpasswort=passwort)


@router.post("/benutzer/{user_id}/zwei-faktor-zuruecksetzen", response_model=BenutzerZeile)
def totp_zuruecksetzen(user_id: str, daten: Bestaetigung, request: Request, db: DB, admin: Admin) -> BenutzerZeile:
    bestaetigen(admin, daten.passwort)
    ziel = ziel_laden(db, user_id)
    ziel.totp_aktiv = False
    ziel.totp_secret_enc = None
    db.execute(delete(AuthSitzung).where(AuthSitzung.user_id == ziel.id))
    audit(db, admin.id, "zwei_faktor_zurueckgesetzt", request, ziel=ziel.id)
    db.commit()
    return zeile(ziel)


@router.post("/benutzer/{user_id}/aktiv", response_model=BenutzerZeile)
def aktiv_setzen(user_id: str, daten: Aktiv, request: Request, db: DB, admin: Admin) -> BenutzerZeile:
    bestaetigen(admin, daten.passwort)
    ziel = ziel_laden(db, user_id)
    if ziel.id == admin.id and not daten.aktiv:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Das eigene Konto kann nicht gesperrt werden.")
    ziel.aktiv = daten.aktiv
    if not daten.aktiv:
        db.execute(delete(AuthSitzung).where(AuthSitzung.user_id == ziel.id))
    audit(db, admin.id, "benutzer_aktiviert" if daten.aktiv else "benutzer_gesperrt", request, ziel=ziel.id)
    db.commit()
    return zeile(ziel)


@router.post("/benutzer/{user_id}/admin", response_model=BenutzerZeile)
def admin_rolle(user_id: str, daten: AdminRolle, request: Request, db: DB, admin: Admin) -> BenutzerZeile:
    bestaetigen(admin, daten.passwort)
    ziel = ziel_laden(db, user_id)
    if ziel.id == admin.id and not daten.ist_admin:
        anzahl = db.scalar(select(func.count()).select_from(Benutzer).where(Benutzer.ist_admin, Benutzer.aktiv))
        if anzahl <= 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Der letzte Administrator kann die Rolle nicht abgeben.")
    ziel.ist_admin = daten.ist_admin
    db.execute(delete(AuthSitzung).where(AuthSitzung.user_id == ziel.id))  # Rechtewechsel: neu anmelden
    audit(db, admin.id, "admin_rolle_" + ("vergeben" if daten.ist_admin else "entzogen"), request, ziel=ziel.id)
    db.commit()
    return zeile(ziel)


@router.get("/audit", response_model=list[AuditZeile])
def audit_log(db: DB, anzahl: int = 200) -> list[AuditZeile]:
    anzahl = max(1, min(anzahl, 1000))
    zeilen = db.scalars(select(AuditEintrag).order_by(AuditEintrag.id.desc()).limit(anzahl)).all()
    return [AuditZeile(zeit=utc(z.zeit).isoformat(), akteur=z.akteur, aktion=z.aktion, ziel=z.ziel) for z in zeilen]


@router.get("/system")
def system(db: DB) -> dict:
    from .spiel import lesen

    return {"benutzer": db.scalar(select(func.count()).select_from(Benutzer)),
            "aktive_sitzungen": db.scalar(select(func.count()).select_from(AuthSitzung)
                                          .where(AuthSitzung.laeuft_ab > jetzt_utc())),
            "repository": lesen.repo_info()}
