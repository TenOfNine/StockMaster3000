"""Was ein Mensch für einen Lauf freigeben darf: konservative Prüfung von Shell-Befehlen auf dem Server.

Die Claude-CLI fragt den Worker nur nach Befehlen, die weder erlaubt noch verboten sind (Verbotsregeln und
Positivliste entscheidet sie selbst). Diese Prüfung ist die zweite Schranke vor dem Klick: Was hier nicht
freigebbar ist, lehnt der Worker sofort ab, auch wenn ein Administrator es erlauben wollte.

Leitlinie (Entscheidung 37): Der Spielstand bleibt für Claude schreibgeschützt. Die Schreibverbote der
Einstellungen gelten nur für die Dateiwerkzeuge Edit und Write, nicht für Shell-Befehle; deshalb sind
Shell-Befehle nur freigebbar, wenn sie erkennbar nur lesen. Das ist eine Mustererkennung und kein Beweis:
Daneben bleiben die Verbote der CLI, die Prüfung `pruefe.py` nach jedem Lauf und die Git-Historie des
Datenverzeichnisses.

Wähle im Zweifel die strengere Auslegung: Was nicht sicher als lesend erkennbar ist, ist gesperrt.
"""

from __future__ import annotations

import posixpath
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

MAX_ZEICHEN = 2000
KENNUNG = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# Umleitungen, die nichts schreiben: nach /dev/null und Verdopplung von Dateideskriptoren (2>&1).
HARMLOSE_UMLEITUNG = re.compile(r"(>>?)\s*(?:&(?:\d+|-)|/dev/null)(?=$|[\s;|&])")

# Werkzeuge, die nur lesen (und ausgeben). Weggelassen sind alle, die schreiben oder Programme starten können:
# sed (w/e-Befehle, -i), find (-exec, -delete), tee, xargs, env, sh, bash, python -c, cp, mv, rm, dd, curl ...
LESEND = frozenset({"echo", "printf", "cat", "head", "tail", "wc", "sort", "uniq", "cut", "tr", "grep", "awk",
                    "column", "nl", "tac", "paste", "comm", "diff", "ls", "date", "pwd", "basename", "dirname"})
# awk kann mit system(), getline, print > und print | "…" schreiben und Programme starten und mit ENVIRON
# Umgebungsvariablen (darunter das Claude-Token) lesen.
AWK_VERBOTEN = re.compile(r"system|getline|ENVIRON|@|>|\|\s*\"|\bclose\s*\(|\bfflush\b")


@dataclass(frozen=True)
class Bewertung:
    freigebbar: bool
    grund: str | None = None


class Gesperrt(Exception):
    """Der Befehl ist nicht freigebbar; die Meldung nennt den Grund im Klartext."""


def bewerten(werkzeug: str, eingabe: dict, daten_pfad: Path, framework_pfad: Path) -> Bewertung:
    """Darf diese Anfrage einem Menschen zur Freigabe vorgelegt werden?"""
    if werkzeug != "Bash":
        return Bewertung(False, f"Nur Shell-Befehle sind freigebbar, nicht „{werkzeug}“.")
    befehl = eingabe.get("command")
    if not isinstance(befehl, str) or not befehl.strip():
        return Bewertung(False, "Kein Befehl angegeben.")
    if len(befehl) > MAX_ZEICHEN or "\0" in befehl:
        return Bewertung(False, f"Befehl zu lang oder ungültig (höchstens {MAX_ZEICHEN} Zeichen).")
    # Unsichtbare Zeichen und Umkehr der Schreibrichtung könnten dem Menschen vor dem Klick etwas anderes zeigen.
    if any(unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp", "Co", "Cn") and c not in "\n\t" for c in befehl):
        return Bewertung(False, "Der Befehl enthält Steuerzeichen oder unsichtbare Zeichen.")
    try:
        _pruefen(_zerlegen(befehl), (daten_pfad, framework_pfad))
    except Gesperrt as grund:
        return Bewertung(False, str(grund))
    return Bewertung(True)


# --------------------------------------------------------------------------
# Zerlegen: Anführungszeichen, Trenner und alles, was die Shell sonst auswertet


def _zerlegen(befehl: str) -> list[list[tuple[str, list[str]]]]:
    """Befehl in Segmente (getrennt durch ; | || && Zeilenumbruch) aus Wörtern (Text, verwendete Variablen)."""
    segmente: list[list[tuple[str, list[str]]]] = []
    aktuell: list[tuple[str, list[str]]] = []
    wort: list[str] = []
    refs: list[str] = []
    im_wort = False
    anfuehrung: str | None = None
    i, n = 0, len(befehl)

    def wort_ende() -> None:
        nonlocal wort, refs, im_wort
        if im_wort:
            aktuell.append(("".join(wort), refs))
        wort, refs, im_wort = [], [], False

    def segment_ende() -> None:
        wort_ende()
        if aktuell:
            segmente.append(list(aktuell))
            aktuell.clear()

    def variable(ab: int) -> str:
        treffer = KENNUNG.match(befehl, ab + 1)
        if not treffer:
            raise Gesperrt("Shell-Ersetzungen mit $ sind nicht freigebbar (erlaubt: Schleifenvariablen wie $t).")
        return treffer.group()

    while i < n:
        c = befehl[i]
        if anfuehrung == "'":
            if c == "'":
                anfuehrung = None
            else:
                wort.append(c)
            i += 1
            continue
        if anfuehrung == '"':
            if c == '"':
                anfuehrung = None
            elif c == "\\":
                if i + 1 < n and befehl[i + 1] in '"\\':
                    wort.append(befehl[i + 1])
                    i += 1
                else:
                    raise Gesperrt("Backslash in Anführungszeichen ist nicht freigebbar.")
            elif c == "`":
                raise Gesperrt("Befehlsersetzung (Backticks) ist nicht freigebbar.")
            elif c == "$":
                name = variable(i)
                refs.append(name)
                wort.append("$" + name)
                i += len(name)
            else:
                wort.append(c)
            i += 1
            continue
        if c in "'\"":
            anfuehrung, im_wort = c, True
        elif c in " \t":
            wort_ende()
        elif c in ";\n":
            segment_ende()
        elif c == "|":
            segment_ende()
            i += 1 if befehl[i : i + 2] == "||" else 0
        elif c == "&":
            if befehl[i : i + 2] != "&&":
                raise Gesperrt("Hintergrundprozesse (&) sind nicht freigebbar.")
            segment_ende()
            i += 1
        elif c == ">":
            if im_wort and "".join(wort).isdigit():  # Dateideskriptor wie bei 2>/dev/null
                wort, refs, im_wort = [], [], False
            else:
                wort_ende()
            treffer = HARMLOSE_UMLEITUNG.match(befehl, i)
            if not treffer:
                raise Gesperrt("Umleitung in eine Datei (>) ist nicht freigebbar: Der Spielstand bleibt "
                               "schreibgeschützt.")
            i = treffer.end() - 1
        elif c == "<":
            raise Gesperrt("Eingabeumleitung, Heredoc und Prozess-Ersetzung sind nicht freigebbar.")
        elif c in "(){}`":
            raise Gesperrt("Unterschalen, Gruppen und Befehlsersetzung sind nicht freigebbar.")
        elif c == "\\":
            raise Gesperrt("Backslash ist nicht freigebbar.")
        elif c == "#" and not im_wort:
            raise Gesperrt("Kommentare im Befehl sind nicht freigebbar.")
        elif c == "$":
            name = variable(i)
            refs.append(name)
            wort.append("$" + name)
            im_wort = True
            i += len(name)
        else:
            wort.append(c)
            im_wort = True
        i += 1
    if anfuehrung:
        raise Gesperrt("Anführungszeichen nicht geschlossen.")
    segment_ende()
    return segmente


# --------------------------------------------------------------------------
# Prüfen: nur lesende Werkzeuge, nur Pfade im Spielstand- und Framework-Verzeichnis


def _pruefen(segmente: list[list[tuple[str, list[str]]]], wurzeln: tuple[Path, ...]) -> None:
    variablen: set[str] = set()
    tiefe = 0
    erwarte_do = False
    for segment in segmente:
        if erwarte_do:
            if segment[0][0] != "do":
                raise Gesperrt("Schleife ohne „do“.")
            segment, erwarte_do = segment[1:], False
        elif segment[0][0] == "do":
            raise Gesperrt("„do“ ohne Schleife.")
        if not segment:
            continue
        erstes = segment[0][0]
        if erstes == "for":
            if len(segment) < 4 or segment[2][0] != "in" or not KENNUNG.fullmatch(segment[1][0]):
                raise Gesperrt("Nur Schleifen der Form „for name in wort …; do …; done“ sind freigebbar.")
            for text, refs in segment[3:]:
                _variablen_pruefen(refs, variablen)
                _pfad_pruefen(text, wurzeln)
            variablen.add(segment[1][0])
            tiefe += 1
            erwarte_do = True
            continue
        if erstes == "done":
            tiefe -= 1
            if tiefe < 0 or len(segment) != 1:
                raise Gesperrt("Schleife nicht vollständig.")
            continue
        _befehl_pruefen(segment, variablen, wurzeln)
    if erwarte_do or tiefe != 0:
        raise Gesperrt("Schleife nicht vollständig.")


def _variablen_pruefen(refs: list[str], bekannt: set[str]) -> None:
    for name in refs:
        if name not in bekannt:
            raise Gesperrt(f"Die Variable ${name} ist nicht freigebbar (erlaubt sind nur Schleifenvariablen).")


def _pfad_pruefen(text: str, wurzeln: tuple[Path, ...]) -> None:
    """Pfade nur innerhalb von Datenverzeichnis und Framework: kein ~, kein .., nichts aus /data-app, /proc, /etc."""
    for teil in {text, text.partition("=")[2]}:
        if not teil:
            continue
        if teil.startswith("~"):
            raise Gesperrt("Pfade mit ~ sind nicht freigebbar.")
        if ".." in teil.split("/"):
            raise Gesperrt("Pfade mit .. sind nicht freigebbar.")
        if teil.startswith("/") and teil != "/dev/null":
            norm = posixpath.normpath(teil)
            if not any(norm == str(w) or norm.startswith(str(w).rstrip("/") + "/") for w in wurzeln):
                raise Gesperrt(f"Der Pfad {teil[:80]} liegt außerhalb von Spielstand und Framework.")


def _befehl_pruefen(segment: list[tuple[str, list[str]]], variablen: set[str], wurzeln: tuple[Path, ...]) -> None:
    name, argumente = segment[0][0], segment[1:]
    for _, refs in segment:
        _variablen_pruefen(refs, variablen)
    texte = [text for text, _ in argumente]
    ausnahme = None  # Index eines Arguments, das kein Pfad ist (awk-Programm)
    if name in ("python", "python3"):
        ziel = texte[0] if texte else ""
        if not (ziel.startswith("tools/") and ziel.endswith(".py")):
            raise Gesperrt("Python ist nur für Skripte unter tools/ freigebbar (nicht -c oder -m).")
    elif name in LESEND:
        ausnahme = _lesend_pruefen(name, texte)
    else:
        raise Gesperrt(f"Der Befehl „{name[:40]}“ ist nicht freigebbar. Freigebbar sind nur lesende Werkzeuge "
                       f"({', '.join(sorted(LESEND))}) und python tools/….")
    for index, text in enumerate(texte):
        if index != ausnahme:
            _pfad_pruefen(text, wurzeln)


def _kurz(optionen: list[str], buchstaben: str) -> bool:
    """Kurze Optionen lassen sich bündeln (-uo datei): ein Buchstabe irgendwo im Bündel genügt."""
    return any(not o.startswith("--") and any(b in o[1:] for b in buchstaben) for o in optionen)


def _lesend_pruefen(name: str, texte: list[str]) -> int | None:
    """Sonderfälle lesender Werkzeuge, die mit bestimmten Optionen doch schreiben oder ausführen."""
    optionen = [t for t in texte if t.startswith("-") and t != "-"]
    stellung = [t for t in texte if not t.startswith("-")]
    if name == "awk":
        return _awk_pruefen(texte)
    if name == "sort" and (_kurz(optionen, "oT") or any(o.startswith(("--output", "--compress-program",
                                                                      "--temporary-directory")) for o in optionen)):
        raise Gesperrt("sort mit Ausgabedatei oder Hilfsprogramm ist nicht freigebbar.")
    if name == "uniq" and len(stellung) > 1:
        raise Gesperrt("uniq mit Ausgabedatei ist nicht freigebbar.")
    if name == "tail" and (_kurz(optionen, "fF") or any(o.startswith(("--follow", "--retry")) for o in optionen)):
        raise Gesperrt("tail -f läuft endlos und ist nicht freigebbar.")
    if name == "date" and (_kurz(optionen, "s") or any(o.startswith("--set") for o in optionen)):
        raise Gesperrt("date mit Zeitänderung ist nicht freigebbar.")
    return None


def _awk_pruefen(texte: list[str]) -> int | None:
    """Erlaubt sind -F, -v und ein Programm ohne system(), getline, Umleitung, Pipe oder ENVIRON."""
    i = 0
    while i < len(texte):
        text = texte[i]
        if text in ("-F", "-v"):
            i += 2
        elif text.startswith(("-F", "-v")) and text != "--":
            i += 1
        elif text.startswith("-"):
            raise Gesperrt(f"awk-Option {text[:20]} ist nicht freigebbar (erlaubt: -F und -v).")
        else:
            break
    if i >= len(texte):
        raise Gesperrt("awk ohne Programm.")
    if AWK_VERBOTEN.search(texte[i]):
        raise Gesperrt("Das awk-Programm enthält Konstrukte, die schreiben, Programme starten oder die Umgebung lesen "
                       "könnten (system, getline, >, |, ENVIRON, @); bitte ohne diese formulieren.")
    return i
