"""Datenbanktabellen (nur Metadaten; Spieldaten liegen im Git-Repository)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Basis, jetzt_utc


def _uuid() -> str:
    return str(uuid.uuid4())


class Benutzer(Basis):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    anzeigename: Mapped[str] = mapped_column(String(80))
    kennung: Mapped[str] = mapped_column(String(20), unique=True)
    passwort_hash: Mapped[str] = mapped_column(String(255))
    ist_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    aktiv: Mapped[bool] = mapped_column(Boolean, default=True)
    totp_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_aktiv: Mapped[bool] = mapped_column(Boolean, default=False)
    passwortwechsel_noetig: Mapped[bool] = mapped_column(Boolean, default=True)
    fehlversuche: Mapped[int] = mapped_column(Integer, default=0)
    gesperrt_bis: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    erstellt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=jetzt_utc)


class AuthSitzung(Basis):
    __tablename__ = "auth_sessions"

    id_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf: Mapped[str] = mapped_column(String(64))
    totp_offen: Mapped[bool] = mapped_column(Boolean, default=False)
    erstellt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=jetzt_utc)
    zuletzt_aktiv: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=jetzt_utc)
    laeuft_ab: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ip_hash: Mapped[str] = mapped_column(String(64))
    user_agent: Mapped[str] = mapped_column(String(200))


class AuditEintrag(Basis):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    akteur: Mapped[str | None] = mapped_column(String(36), nullable=True)
    aktion: Mapped[str] = mapped_column(String(60))
    ziel: Mapped[str | None] = mapped_column(String(120), nullable=True)
    zeit: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=jetzt_utc)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta: Mapped[str | None] = mapped_column(Text, nullable=True)


class Auftrag(Basis):
    """Auftrag an den Hintergrunddienst (Worker): Claude-Läufe und Verbindungstests.

    Die API hat keinen Internetzugang; alles, was nach außen geht, erledigt der Worker. Wer einen
    Lauf gestartet hat, steht nur hier und im Audit-Log, nie im Spielstand (Entscheidung 9).
    """

    __tablename__ = "auftraege"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    art: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True, default="wartet")
    parameter: Mapped[str | None] = mapped_column(Text, nullable=True)
    ergebnis: Mapped[str | None] = mapped_column(Text, nullable=True)
    meldung: Mapped[str | None] = mapped_column(Text, nullable=True)
    modell: Mapped[str | None] = mapped_column(String(100), nullable=True)
    aufwand: Mapped[str | None] = mapped_column(String(20), nullable=True)
    auftraggeber: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ausloeser: Mapped[str] = mapped_column(String(20), default="manuell")
    erstellt_von: Mapped[str | None] = mapped_column(String(36), nullable=True)
    erstellt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=jetzt_utc, index=True)
    begonnen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    beendet: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    abbrechen: Mapped[bool] = mapped_column(Boolean, default=False)
    pruefung_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class Freigabe(Basis):
    """Anfrage der Claude-CLI an einen Menschen (Entscheidung 37): Befehl, der weder erlaubt noch verboten ist.

    Entschieden wird in der Web-UI. Wer entschieden hat, steht nur hier und im Audit-Log, nie im Spielstand.
    Status: offen, erlaubt, abgelehnt, abgelaufen (keine Entscheidung rechtzeitig), gesperrt (vom Server nie
    freigebbar, ohne Rückfrage abgelehnt), abgebrochen (Lauf wurde beendet).
    """

    __tablename__ = "freigaben"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    auftrag_id: Mapped[str] = mapped_column(String(36), ForeignKey("auftraege.id", ondelete="CASCADE"), index=True)
    werkzeug: Mapped[str] = mapped_column(String(60))
    befehl: Mapped[str] = mapped_column(Text)
    beschreibung: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True, default="offen")
    grund: Mapped[str | None] = mapped_column(Text, nullable=True)
    erstellt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=jetzt_utc, index=True)
    laeuft_ab: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    entschieden: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entschieden_von: Mapped[str | None] = mapped_column(String(36), nullable=True)
