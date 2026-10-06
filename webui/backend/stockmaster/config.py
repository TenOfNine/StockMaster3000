"""Einstellungen aus Umgebungsvariablen (Präfix SM_) bzw. Docker Secrets."""

from __future__ import annotations

import base64
import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PRIVATE_NETZE = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "fc00::/7", "::1/128"]


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
            raise RuntimeError("SM_SCHLUESSEL bzw. SM_SCHLUESSEL_DATEI fehlt (32 Byte, Base64).")
        wert = base64.b64decode(roh)
        if len(wert) != 32:
            raise RuntimeError("Der Schlüssel muss 32 Byte lang sein (Base64).")
        return wert


@lru_cache
def einstellungen() -> Einstellungen:
    return Einstellungen()
