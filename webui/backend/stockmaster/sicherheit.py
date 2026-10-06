"""Passwörter, Tokens, Verschlüsselung und Rate-Limiting."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import string
import threading
import time
from collections import deque

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import einstellungen

_hasher = PasswordHasher()  # Argon2id mit den Standardparametern von argon2-cffi
_DUMMY_HASH = _hasher.hash("dummy-passwort-fuer-gleichmaessige-laufzeit")

MIN_PASSWORT = 12


def passwort_hash(passwort: str) -> str:
    return _hasher.hash(passwort)


def passwort_pruefen(hash_wert: str | None, passwort: str) -> bool:
    try:
        return _hasher.verify(hash_wert or _DUMMY_HASH, passwort) and hash_wert is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def passwort_regeln(passwort: str) -> str | None:
    """Fehlermeldung oder None."""
    if len(passwort) < MIN_PASSWORT:
        return f"Das Passwort braucht mindestens {MIN_PASSWORT} Zeichen."
    if len(passwort) > 200:
        return "Das Passwort ist zu lang."
    if len(set(passwort)) < 5:
        return "Das Passwort ist zu einfach."
    return None


def einmalpasswort() -> str:
    alphabet = string.ascii_letters + string.digits
    return "-".join("".join(secrets.choice(alphabet) for _ in range(5)) for _ in range(4))


def neue_kennung() -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "a-" + "".join(secrets.choice(alphabet) for _ in range(4))


def token() -> str:
    return secrets.token_urlsafe(32)  # 256 Bit


def sha256(wert: str) -> str:
    return hashlib.sha256(wert.encode()).hexdigest()


def ip_hash(ip: str | None) -> str:
    """IP-Adressen nur gehasht speichern (Schlüssel aus dem Geheimnis)."""
    return hmac.new(einstellungen().schluessel_bytes(), (ip or "-").encode(), hashlib.sha256).hexdigest()


def gleich(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


# --------------------------------------------------------------------------
# TOTP


def totp_verschluesseln(geheimnis: str, user_id: str) -> str:
    nonce = secrets.token_bytes(12)
    daten = AESGCM(einstellungen().schluessel_bytes()).encrypt(nonce, geheimnis.encode(), user_id.encode())
    return "v1:" + base64.b64encode(nonce + daten).decode()


def totp_entschluesseln(wert: str, user_id: str) -> str:
    roh = base64.b64decode(wert.split(":", 1)[1])
    return AESGCM(einstellungen().schluessel_bytes()).decrypt(roh[:12], roh[12:], user_id.encode()).decode()


def totp_neu() -> str:
    return pyotp.random_base32()


def totp_pruefen(geheimnis: str, code: str) -> bool:
    code = code.strip().replace(" ", "")
    return code.isdigit() and len(code) == 6 and pyotp.TOTP(geheimnis).verify(code, valid_window=1)


def totp_uri(geheimnis: str, email: str) -> str:
    return pyotp.TOTP(geheimnis).provisioning_uri(name=email, issuer_name="StockMaster 3000")


# --------------------------------------------------------------------------
# Rate-Limiting (Sliding Window im Prozess; ein API-Prozess, Redis folgt in Stufe 2)


class Begrenzer:
    def __init__(self):
        self._fenster: dict[str, deque] = {}
        self._sperre = threading.Lock()

    def erlaubt(self, schluessel: str, anzahl: int, sekunden: int) -> tuple[bool, int]:
        """(erlaubt, Sekunden bis zum nächsten Versuch)."""
        jetzt = time.monotonic()
        with self._sperre:
            fenster = self._fenster.setdefault(schluessel, deque())
            while fenster and fenster[0] <= jetzt - sekunden:
                fenster.popleft()
            if len(fenster) >= anzahl:
                return False, max(1, int(fenster[0] + sekunden - jetzt) + 1)
            fenster.append(jetzt)
            return True, 0

    def leeren(self) -> None:
        with self._sperre:
            self._fenster.clear()


begrenzer = Begrenzer()
