"""Anmeldung, Sitzungen, CSRF, Zwei-Faktor und Konto.

Die Anmeldung braucht nur das Passwort (Umbau v2, Entscheidung 40). Ein TOTP-Code wird nur noch verlangt, wenn ein
Administrator einen neuen Benutzer anlegt (admin.py); dafür richtet der Administrator Zwei-Faktor im Konto ein.
Bereits gespeicherte TOTP-Geheimnisse bleiben gültig.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import sicherheit as s
from .config import einstellungen
from .db import jetzt_utc, sitzung, utc
from .modelle import AuditEintrag, AuthSitzung, Benutzer

Schritt = Literal["passwort_aendern", "fertig"]
LOGIN_FENSTER = (5, 60)  # 5 Versuche je Minute


class Streng(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginDaten(Streng):
    email: str = Field(min_length=3, max_length=254)
    passwort: str = Field(min_length=1, max_length=200)


class CodeDaten(Streng):
    code: str = Field(min_length=6, max_length=8, pattern=r"^[0-9 ]+$")


class PasswortDaten(Streng):
    alt: str = Field(min_length=1, max_length=200)
    neu: str = Field(min_length=1, max_length=200)


class DeaktivierenDaten(Streng):
    passwort: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=6, max_length=8, pattern=r"^[0-9 ]+$")


class BenutzerAntwort(BaseModel):
    id: str
    email: str
    anzeigename: str
    kennung: str
    ist_admin: bool
    totp_aktiv: bool


class SitzungAntwort(BaseModel):
    benutzer: BenutzerAntwort | None
    naechster_schritt: Schritt
    csrf: str


class SitzungsEintrag(BaseModel):
    erstellt: str
    zuletzt_aktiv: str
    user_agent: str
    aktuell: bool


class TotpEinrichtung(BaseModel):
    uri: str
    geheimnis: str


class Ok(BaseModel):
    ok: bool = True


router = APIRouter(prefix="/api/auth", tags=["auth"])
DB = Annotated[Session, Depends(sitzung)]


# --------------------------------------------------------------------------
# Hilfen


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "-"


def audit(db: Session, akteur: str | None, aktion: str, request: Request, ziel: str | None = None,
          meta: dict | None = None) -> None:
    db.add(AuditEintrag(akteur=akteur, aktion=aktion, ziel=ziel, ip_hash=s.ip_hash(client_ip(request)),
                        meta=json.dumps(meta, ensure_ascii=False) if meta else None))


def begrenzen(schluessel: str, anzahl: int, sekunden: int) -> None:
    erlaubt, warten = s.begrenzer.erlaubt(schluessel, anzahl, sekunden)
    if not erlaubt:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Zu viele Anfragen. Bitte später erneut versuchen.",
                            headers={"Retry-After": str(warten)})


def naechster_schritt(sitz: AuthSitzung, benutzer: Benutzer) -> Schritt:
    # Kein Zwei-Faktor-Schritt bei der Anmeldung; `sitz.totp_offen` (Spalte aus früheren Versionen) wird ignoriert.
    if benutzer.passwortwechsel_noetig:
        return "passwort_aendern"
    return "fertig"


def totp_pruefen_fuer(db: Session, benutzer: Benutzer, code: str, request: Request) -> None:
    """Verlangt einen gültigen TOTP-Code des Benutzers (für das Anlegen neuer Benutzer), begrenzt und protokolliert."""
    begrenzen(f"totp:{benutzer.id}", *LOGIN_FENSTER)
    if not benutzer.totp_aktiv or not benutzer.totp_secret_enc:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Zum Anlegen von Benutzern zuerst Zwei-Faktor einrichten (Konto & Sicherheit).")
    geheimnis = s.totp_entschluesseln(benutzer.totp_secret_enc, benutzer.id)
    if not s.totp_pruefen(geheimnis, code.replace(" ", "")):
        audit(db, benutzer.id, "totp_fehlgeschlagen", request)
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Zwei-Faktor-Code ungültig.")  # nicht 401: kein Abmelden


def benutzer_antwort(benutzer: Benutzer) -> BenutzerAntwort:
    return BenutzerAntwort(id=benutzer.id, email=benutzer.email, anzeigename=benutzer.anzeigename,
                           kennung=benutzer.kennung, ist_admin=benutzer.ist_admin, totp_aktiv=benutzer.totp_aktiv)


def cookie_setzen(response: Response, wert: str) -> None:
    e = einstellungen()
    response.set_cookie(e.cookie_name, wert, httponly=True, secure=e.cookie_sicher, samesite="strict", path="/",
                        max_age=e.sitzung_max_stunden * 3600)


def cookie_loeschen(response: Response) -> None:
    e = einstellungen()
    response.delete_cookie(e.cookie_name, path="/", secure=e.cookie_sicher, httponly=True, samesite="strict")


def sitzung_anlegen(db: Session, benutzer: Benutzer, request: Request, response: Response,
                    totp_offen: bool) -> AuthSitzung:
    roh = s.token()
    jetzt = jetzt_utc()
    sitz = AuthSitzung(id_hash=s.sha256(roh), user_id=benutzer.id, csrf=s.token(), totp_offen=totp_offen,
                       erstellt=jetzt, zuletzt_aktiv=jetzt,
                       laeuft_ab=jetzt + timedelta(hours=einstellungen().sitzung_max_stunden),
                       ip_hash=s.ip_hash(client_ip(request)),
                       user_agent=(request.headers.get("user-agent") or "")[:200])
    db.add(sitz)
    cookie_setzen(response, roh)
    return sitz


def sitzung_erneuern(db: Session, alt: AuthSitzung, benutzer: Benutzer, request: Request,
                     response: Response) -> AuthSitzung:
    """Rotation der Sitzungs-ID bei Anmeldung und Rechtewechsel."""
    db.delete(alt)
    neu = sitzung_anlegen(db, benutzer, request, response, totp_offen=False)
    neu.erstellt = alt.erstellt
    neu.laeuft_ab = alt.laeuft_ab
    return neu


def _sitzung_laden(request: Request, db: Session) -> tuple[AuthSitzung, Benutzer]:
    roh = request.cookies.get(einstellungen().cookie_name)
    if not roh or len(roh) > 100:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nicht angemeldet.")
    sitz = db.get(AuthSitzung, s.sha256(roh))
    jetzt = jetzt_utc()
    if sitz is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nicht angemeldet.")
    leerlauf = timedelta(minutes=einstellungen().sitzung_leerlauf_minuten)
    if utc(sitz.laeuft_ab) <= jetzt or utc(sitz.zuletzt_aktiv) + leerlauf <= jetzt:
        db.delete(sitz)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sitzung abgelaufen.")
    benutzer = db.get(Benutzer, sitz.user_id)
    if benutzer is None or not benutzer.aktiv or (benutzer.gesperrt_bis and utc(benutzer.gesperrt_bis) > jetzt):
        db.delete(sitz)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nicht angemeldet.")
    if jetzt - utc(sitz.zuletzt_aktiv) > timedelta(seconds=30):
        sitz.zuletzt_aktiv = jetzt
        db.commit()
    return sitz, benutzer


def csrf_pruefen(request: Request, sitz: AuthSitzung) -> None:
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    origin = request.headers.get("origin")
    if origin:
        erlaubt = set(einstellungen().erlaubte_origins) or {f"{request.url.scheme}://{request.headers.get('host')}"}
        if origin not in erlaubt:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Ungültige Herkunft der Anfrage.")
    if not s.gleich(request.headers.get("x-csrf-token", ""), sitz.csrf):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF-Prüfung fehlgeschlagen.")


def teil_angemeldet(request: Request, db: DB) -> tuple[AuthSitzung, Benutzer]:
    """Sitzung vorhanden (Zwischenschritte erlaubt), CSRF geprüft."""
    sitz, benutzer = _sitzung_laden(request, db)
    csrf_pruefen(request, sitz)
    return sitz, benutzer


def angemeldet(request: Request, db: DB) -> Benutzer:
    """Vollständig angemeldet: Passwort gewechselt (kein Zwei-Faktor-Schritt bei der Anmeldung)."""
    sitz, benutzer = teil_angemeldet(request, db)
    schritt = naechster_schritt(sitz, benutzer)
    if schritt != "fertig":
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Anmeldung unvollständig: {schritt}.")
    request.state.benutzer = benutzer
    return benutzer


Teil = Annotated[tuple[AuthSitzung, Benutzer], Depends(teil_angemeldet)]
Angemeldet = Annotated[Benutzer, Depends(angemeldet)]


# --------------------------------------------------------------------------
# Routen


@router.post("/login", response_model=SitzungAntwort)
def login(daten: LoginDaten, request: Request, response: Response, db: DB) -> SitzungAntwort:
    email = daten.email.lower()
    begrenzen(f"login-ip:{client_ip(request)}", *LOGIN_FENSTER)
    begrenzen(f"login-email:{s.sha256(email)}", *LOGIN_FENSTER)
    benutzer = db.scalar(select(Benutzer).where(Benutzer.email == email))
    jetzt = jetzt_utc()
    if benutzer and benutzer.gesperrt_bis and utc(benutzer.gesperrt_bis) > jetzt:
        s.passwort_pruefen(None, daten.passwort)  # gleiche Laufzeit
        audit(db, benutzer.id, "login_gesperrt", request)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-Mail oder Passwort falsch, oder Konto vorübergehend gesperrt.")
    if not benutzer or not benutzer.aktiv or not s.passwort_pruefen(benutzer.passwort_hash, daten.passwort):
        if benutzer:
            benutzer.fehlversuche += 1
            if benutzer.fehlversuche >= 5:
                minuten = min(2 ** (benutzer.fehlversuche - 5), 60)
                benutzer.gesperrt_bis = jetzt + timedelta(minutes=minuten)
            audit(db, benutzer.id, "login_fehlgeschlagen", request)
            db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-Mail oder Passwort falsch, oder Konto vorübergehend gesperrt.")
    benutzer.fehlversuche = 0
    benutzer.gesperrt_bis = None
    alt = request.cookies.get(einstellungen().cookie_name)
    if alt:
        db.execute(delete(AuthSitzung).where(AuthSitzung.id_hash == s.sha256(alt)))
    sitz = sitzung_anlegen(db, benutzer, request, response, totp_offen=False)
    audit(db, benutzer.id, "login", request)
    db.commit()
    return SitzungAntwort(benutzer=benutzer_antwort(benutzer), naechster_schritt=naechster_schritt(sitz, benutzer),
                          csrf=sitz.csrf)


@router.get("/me", response_model=SitzungAntwort)
def ich(request: Request, db: DB) -> SitzungAntwort:
    sitz, benutzer = _sitzung_laden(request, db)
    return SitzungAntwort(benutzer=benutzer_antwort(benutzer), naechster_schritt=naechster_schritt(sitz, benutzer),
                          csrf=sitz.csrf)


@router.post("/logout", response_model=Ok)
def logout(request: Request, response: Response, db: DB, teil: Teil) -> Ok:
    sitz, benutzer = teil
    db.delete(sitz)
    audit(db, benutzer.id, "logout", request)
    db.commit()
    cookie_loeschen(response)
    return Ok()


@router.post("/logout-alle", response_model=Ok)
def logout_alle(request: Request, response: Response, db: DB, teil: Teil) -> Ok:
    _, benutzer = teil
    db.execute(delete(AuthSitzung).where(AuthSitzung.user_id == benutzer.id))
    audit(db, benutzer.id, "logout_alle", request)
    db.commit()
    cookie_loeschen(response)
    return Ok()


@router.post("/passwort", response_model=SitzungAntwort)
def passwort_aendern(daten: PasswortDaten, request: Request, response: Response, db: DB, teil: Teil) -> SitzungAntwort:
    sitz, benutzer = teil
    begrenzen(f"passwort:{benutzer.id}", *LOGIN_FENSTER)
    if not s.passwort_pruefen(benutzer.passwort_hash, daten.alt):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Das bisherige Passwort stimmt nicht.")
    fehler = s.passwort_regeln(daten.neu)
    if fehler:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, fehler)
    if daten.neu == daten.alt:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Das neue Passwort muss sich vom bisherigen unterscheiden.")
    benutzer.passwort_hash = s.passwort_hash(daten.neu)
    benutzer.passwortwechsel_noetig = False
    db.execute(delete(AuthSitzung).where(AuthSitzung.user_id == benutzer.id, AuthSitzung.id_hash != sitz.id_hash))
    neu = sitzung_erneuern(db, sitz, benutzer, request, response)
    audit(db, benutzer.id, "passwort_geaendert", request)
    db.commit()
    return SitzungAntwort(benutzer=benutzer_antwort(benutzer), naechster_schritt=naechster_schritt(neu, benutzer),
                          csrf=neu.csrf)


@router.post("/totp/einrichten", response_model=TotpEinrichtung)
def totp_einrichten(request: Request, db: DB, teil: Teil) -> TotpEinrichtung:
    _, benutzer = teil
    if benutzer.passwortwechsel_noetig:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Zuerst das Passwort ändern.")
    if benutzer.totp_aktiv:
        raise HTTPException(status.HTTP_409_CONFLICT, "Zwei-Faktor ist bereits aktiv.")
    geheimnis = s.totp_neu()
    benutzer.totp_secret_enc = s.totp_verschluesseln(geheimnis, benutzer.id)
    audit(db, benutzer.id, "totp_einrichtung_begonnen", request)
    db.commit()
    return TotpEinrichtung(uri=s.totp_uri(geheimnis, benutzer.email), geheimnis=geheimnis)


@router.post("/totp/aktivieren", response_model=SitzungAntwort)
def totp_aktivieren(daten: CodeDaten, request: Request, db: DB, teil: Teil) -> SitzungAntwort:
    sitz, benutzer = teil
    begrenzen(f"totp:{benutzer.id}", *LOGIN_FENSTER)
    if benutzer.passwortwechsel_noetig or benutzer.totp_aktiv or not benutzer.totp_secret_enc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Keine Zwei-Faktor-Einrichtung offen.")
    if not s.totp_pruefen(s.totp_entschluesseln(benutzer.totp_secret_enc, benutzer.id), daten.code.replace(" ", "")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Code ungültig. Uhrzeit des Geräts prüfen.")
    benutzer.totp_aktiv = True
    audit(db, benutzer.id, "totp_aktiviert", request)
    db.commit()
    return SitzungAntwort(benutzer=benutzer_antwort(benutzer), naechster_schritt=naechster_schritt(sitz, benutzer),
                          csrf=sitz.csrf)


@router.post("/totp/deaktivieren", response_model=Ok)
def totp_deaktivieren(daten: DeaktivierenDaten, request: Request, db: DB, benutzer: Angemeldet) -> Ok:
    begrenzen(f"totp:{benutzer.id}", *LOGIN_FENSTER)
    geheimnis = s.totp_entschluesseln(benutzer.totp_secret_enc, benutzer.id) if benutzer.totp_secret_enc else ""
    if not s.passwort_pruefen(benutzer.passwort_hash, daten.passwort) or not s.totp_pruefen(geheimnis, daten.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Passwort oder Code ungültig.")
    benutzer.totp_aktiv = False
    benutzer.totp_secret_enc = None
    audit(db, benutzer.id, "totp_deaktiviert", request)
    db.commit()
    return Ok()


@router.get("/sitzungen", response_model=list[SitzungsEintrag])
def sitzungen(request: Request, db: DB, benutzer: Angemeldet) -> list[SitzungsEintrag]:
    eigene = request.cookies.get(einstellungen().cookie_name, "")
    zeilen = db.scalars(select(AuthSitzung).where(AuthSitzung.user_id == benutzer.id)
                        .order_by(AuthSitzung.zuletzt_aktiv.desc())).all()
    return [SitzungsEintrag(erstellt=utc(z.erstellt).isoformat(), zuletzt_aktiv=utc(z.zuletzt_aktiv).isoformat(),
                            user_agent=z.user_agent, aktuell=z.id_hash == s.sha256(eigene)) for z in zeilen]
