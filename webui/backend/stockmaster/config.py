"""Einstellungen aus Umgebungsvariablen (Präfix SM_) bzw. Docker Secrets."""

from __future__ import annotations

import base64
import logging
import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("stockmaster")

PRIVATE_NETZE = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "fc00::/7", "::1/128"]
SCHLUESSEL_HINWEIS = "Neu erzeugen mit: openssl rand -base64 32 (44 Zeichen, endet auf '=')."


class SchluesselFehler(RuntimeError):
    """SM_SCHLUESSEL fehlt oder ist ungültig. Die Meldung nennt nie den Wert selbst."""


@lru_cache(maxsize=4)
def schluessel_dekodieren(roh: str) -> bytes:
    """Base64-Schlüssel mit genau 32 Byte.

    Zuerst gilt das bisherige Verfahren unverändert: Bestehende Schlüssel müssen dieselben Bytes liefern
    wie bisher, sonst würden gespeicherte Zwei-Faktor-Geheimnisse ungültig. Nur wenn das scheitert, wird
    nachsichtig geprüft, was beim Kopieren und Einfügen schiefgeht: Leerraum, Anführungszeichen, die
    URL-sichere Schreibweise und ein fehlendes Padding ('=' am Ende).
    """
    try:
        wert = base64.b64decode(roh)
        if len(wert) == 32:
            return wert
    except ValueError:  # binascii.Error ist eine ValueError
        pass
    text = "".join(roh.split()).strip("\"'")
    text = text.replace("-", "+").replace("_", "/").rstrip("=")
    try:
        wert = base64.b64decode(text + "=" * (-len(text) % 4), validate=True)
    except ValueError:
        raise SchluesselFehler(
            f"SM_SCHLUESSEL ist kein gültiges Base64 ({len(roh.strip())} Zeichen). {SCHLUESSEL_HINWEIS}"
        ) from None
    if len(wert) != 32:
        raise SchluesselFehler(f"SM_SCHLUESSEL hat {len(wert)} statt 32 Byte. {SCHLUESSEL_HINWEIS}")
    log.warning("SM_SCHLUESSEL hatte ein fehlerhaftes Format (Anführungszeichen, Leerraum oder fehlendes '=') "
                "und wurde korrigiert. Bitte den Wert in der Konfiguration ersetzen. %s", SCHLUESSEL_HINWEIS)
    return wert


class Einstellungen(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SM_", extra="ignore")

    datenbank_url: str = "sqlite:///./stockmaster.db"
    datenbank_url_datei: Path | None = None
    # Alternative zur URL: einzelne Teile, das Passwort darf beliebige Zeichen enthalten
    # (wird beim Bauen der URL korrekt maskiert).
    datenbank_host: str | None = None
    datenbank_port: int = 5432
    datenbank_benutzer: str = "stockmaster"
    datenbank_name: str = "stockmaster"
    datenbank_passwort: str | None = None
    repo_pfad: Path = Path("/repo")
    schluessel: str | None = None
    schluessel_datei: Path | None = None
    cookie_sicher: bool = True
    erlaubte_netze: list[str] = Field(default_factory=lambda: list(PRIVATE_NETZE))
    erlaubte_origins: list[str] = Field(default_factory=list)
    sitzung_leerlauf_minuten: int = 30
    sitzung_max_stunden: int = 12
    api_doku: bool = False
    pruefung_timeout_sekunden: int = 120

    @property
    def cookie_name(self) -> str:
        # __Host- verlangt Secure; ohne HTTPS (nur Entwicklung) ein einfacher Name.
        return "__Host-sid" if self.cookie_sicher else "sm_sid"

    def db_url(self) -> str:
        if self.datenbank_host:
            from sqlalchemy.engine import URL

            return URL.create("postgresql+psycopg", username=self.datenbank_benutzer,
                              password=self.datenbank_passwort, host=self.datenbank_host,
                              port=self.datenbank_port, database=self.datenbank_name
                              ).render_as_string(hide_password=False)
        if self.datenbank_url_datei and self.datenbank_url_datei.exists():
            return self.datenbank_url_datei.read_text(encoding="utf-8").strip()
        return self.datenbank_url

    def schluessel_bytes(self) -> bytes:
        """32-Byte-Schlüssel für die Verschlüsselung von TOTP-Geheimnissen."""
        roh = None
        if self.schluessel_datei and self.schluessel_datei.exists():
            roh = self.schluessel_datei.read_text(encoding="utf-8").strip()
        elif self.schluessel:
            roh = self.schluessel
        if not roh:
            if os.environ.get("SM_ENTWICKLUNG") == "1":
                return b"\x00" * 32
            raise SchluesselFehler(f"SM_SCHLUESSEL bzw. SM_SCHLUESSEL_DATEI fehlt (32 Byte, Base64). {SCHLUESSEL_HINWEIS}")
        return schluessel_dekodieren(roh)


@lru_cache
def einstellungen() -> Einstellungen:
    return Einstellungen()
