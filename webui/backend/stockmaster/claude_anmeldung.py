"""Anmeldung mit dem Claude-Abo direkt aus der App (`claude setup-token` im Container).

Ablauf (geprüft mit Claude Code 2.1.292): Der Befehl gibt einen Anmeldelink aus und wartet mit
„Paste code here if prompted>“. Nach der Anmeldung im Browser zeigt platform.claude.com einen Code;
mit ihm tauscht der Befehl ein Jahres-Token ein und gibt es aus. Der Prozess muss zwischen Link und
Code laufen bleiben (PKCE: der geheime Prüfwert existiert nur in diesem Prozess).

Der Worker startet den Befehl in einem Pseudo-Terminal, liest den Link aus, reicht den Code aus der UI
durch und speichert das Token sofort verschlüsselt. Ausgaben des Befehls werden nie geloggt oder
gespeichert, weil sie das Token enthalten. Ändert sich das Format der Ausgabe, endet der Ablauf mit
einer klaren Meldung; das manuelle Eintragen des Tokens bleibt immer möglich.
"""

from __future__ import annotations

import fcntl
import os
import re
import select
import signal
import struct
import termios
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from . import claude_lauf

# Hyperlink im Terminal (OSC 8) enthält den vollständigen Link, auch wenn die sichtbare Zeile umbricht.
OSC8_LINK = re.compile(rb"\x1b\]8;[^;\x07\x1b]*;(https://[^\x07\x1b]+)(?:\x07|\x1b\\)")
SICHTBARER_LINK = re.compile(r"https://[^\s\x1b\x07]+/oauth/authorize\?[^\s\x1b\x07]+")
ANSI = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-9;?<>=]*[ -/]*[@-~]|\x1b[@-_]")
TOKEN = re.compile(r"sk-ant-oat[0-9]{2}-[A-Za-z0-9_\-]{20,}")
ERLAUBTE_HOSTS = ("claude.com", "claude.ai", "anthropic.com", "platform.claude.com", "console.anthropic.com")
FEHLER_HINWEISE = re.compile(r"invalid|error|fehler|failed|expired|denied", re.I)
# Eingabeaufforderung „Paste code here if prompted>“ (Leerzeichen sind Cursorbewegungen, daher nur „Paste“).
EINGABE_BEREIT = b"Paste"
# Ink nimmt Eingaben erst kurz nach dem Zeichnen der Aufforderung an (mit der echten CLI geprüft).
EINGABE_VERZOEGERUNG = 1.0
OAUTH_FEHLER = re.compile(r"OAuth error|Press Enter to retry", re.I)
CODE_MUSTER = re.compile(r"^[A-Za-z0-9_\-#.~]{8,512}$")
ZEITLIMIT_SEKUNDEN = 600


class AnmeldeFehler(Exception):
    """Klartext für die UI, nie mit Ausgaben des Befehls (die könnten das Token enthalten)."""


@dataclass
class Ergebnis:
    token: str


def code_pruefen(code: str) -> str:
    code = code.strip()
    if not CODE_MUSTER.match(code):
        raise ValueError("Der Code sieht nicht richtig aus: bitte genau den auf der Anmeldeseite angezeigten Code "
                         "einfügen (ohne Leerzeichen).")
    return code


def link_pruefen(link: str) -> str:
    teile = urlparse(link)
    host = teile.hostname or ""
    if teile.scheme != "https" or not any(host == h or host.endswith("." + h) for h in ERLAUBTE_HOSTS):
        raise AnmeldeFehler("Der Anmeldelink stammt nicht von Anthropic; Vorgang abgebrochen.")
    return link


def link_finden(roh: bytes) -> str | None:
    treffer = OSC8_LINK.search(roh)
    if treffer:
        return treffer.group(1).decode("utf-8", errors="replace")
    sichtbar = ANSI.sub("", roh.decode("utf-8", errors="replace"))
    treffer = SICHTBARER_LINK.search(sichtbar)
    return treffer.group(0) if treffer else None


def token_finden(roh: bytes) -> str | None:
    sichtbar = ANSI.sub("", roh.decode("utf-8", errors="replace"))
    treffer = TOKEN.search(sichtbar)
    return treffer.group(0) if treffer else None


def _breites_terminal(fd: int) -> None:
    """Sehr breite Zeilen, damit Link und Token nicht umbrechen."""
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 1000, 0, 0))


def ausfuehren(link_melden: Callable[[str], None], code_holen: Callable[[], str | None],
               abbrechen: Callable[[], bool], umgebung: dict, arbeitsverzeichnis: Path,
               zeitlimit: float = ZEITLIMIT_SEKUNDEN, befehl: tuple[str, ...] = ("claude", "setup-token")) -> Ergebnis:
    """Führt `claude setup-token` interaktiv aus und gibt das Token zurück (oder AnmeldeFehler)."""
    import pty
    import subprocess

    # Popen statt pty.fork: der Worker hat Threads, fork ohne sofortiges exec wäre dort unsicher.
    fd, kind_fd = pty.openpty()
    try:
        _breites_terminal(fd)
    except OSError:
        pass
    try:
        prozess = subprocess.Popen(list(befehl), stdin=kind_fd, stdout=kind_fd, stderr=kind_fd, cwd=arbeitsverzeichnis,
                                   env=umgebung, start_new_session=True, close_fds=True)
    finally:
        os.close(kind_fd)
    puffer = b""
    link = None
    bereit_seit = None
    code_gesendet = False
    nach_code = b""
    beginn = time.monotonic()
    try:
        while True:
            if abbrechen():
                raise AnmeldeFehler("Anmeldung abgebrochen.")
            if time.monotonic() - beginn > zeitlimit:
                raise AnmeldeFehler(f"Keine Anmeldung innerhalb von {int(zeitlimit // 60)} Minuten; bitte neu starten.")
            lesbar, _, _ = select.select([fd], [], [], 0.5)
            if lesbar:
                try:
                    daten = os.read(fd, 65536)
                except OSError:
                    daten = b""
                if not daten:
                    break  # Prozess beendet
                if code_gesendet:
                    nach_code += daten
                    token = token_finden(nach_code)
                    if token:
                        return Ergebnis(token=token)
                    if OAUTH_FEHLER.search(ANSI.sub("", nach_code.decode("utf-8", errors="replace"))):
                        raise AnmeldeFehler("Der Code wurde abgelehnt (abgelaufen, schon benutzt oder falsch kopiert). "
                                            "Bitte die Anmeldung neu starten.")
                else:
                    puffer = (puffer + daten)[-200_000:]
                    if link is None:
                        gefunden = link_finden(puffer)
                        if gefunden:
                            link = link_pruefen(gefunden)
                            link_melden(link)
                    if bereit_seit is None and EINGABE_BEREIT in puffer:
                        bereit_seit = time.monotonic()
            if link and bereit_seit is not None and not code_gesendet \
                    and time.monotonic() - bereit_seit >= EINGABE_VERZOEGERUNG:
                code = code_holen()
                if code:
                    os.write(fd, code.encode())
                    time.sleep(0.3)
                    os.write(fd, b"\r")
                    code_gesendet = True
        # Prozess hat sich beendet, ohne ein Token auszugeben.
        sichtbar = ANSI.sub("", nach_code.decode("utf-8", errors="replace"))
        token = TOKEN.search(sichtbar)
        if token:
            return Ergebnis(token=token.group(0))
        if not link:
            raise AnmeldeFehler("Claude Code hat keinen Anmeldelink ausgegeben (Ausgabeformat geändert?). Token bitte "
                                "manuell mit `claude setup-token` erzeugen und eintragen.")
        if code_gesendet and FEHLER_HINWEISE.search(sichtbar):
            raise AnmeldeFehler("Der Code wurde abgelehnt (abgelaufen oder falsch kopiert). Bitte neu starten.")
        raise AnmeldeFehler("Die Anmeldung wurde ohne Token beendet. Bitte neu starten.")
    finally:
        if prozess.poll() is None:
            try:
                os.killpg(prozess.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        prozess.wait()
        os.close(fd)


def umgebung(temp: Path) -> dict:
    """Minimale Umgebung ohne Token (die Anmeldung erzeugt erst eins)."""
    werte = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"), "HOME": str(temp / "home"),
             "CLAUDE_CONFIG_DIR": str(temp / "claude"), "LANG": "C.UTF-8", "TERM": "xterm-256color",
             "DISABLE_AUTOUPDATER": "1", "BROWSER": "/bin/true"}
    for name in claude_lauf.DURCHREICHEN:
        if os.environ.get(name):
            werte[name] = os.environ[name]
    return werte
