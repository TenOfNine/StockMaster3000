"""Optionen für Claude-Läufe aus config/claude.json (Framework), nicht aus dem Frontend-Code."""

from __future__ import annotations

import json
import re

from .config import einstellungen


def optionen() -> dict:
    datei = einstellungen().framework_pfad / "config" / "claude.json"
    return json.loads(datei.read_text(encoding="utf-8"))


def modell_aliase() -> list[str]:
    return [m["wert"] for m in optionen()["modelle"]]


def pruefen(modell: str, aufwand: str) -> str | None:
    """Fehlermeldung, wenn Modell oder Aufwand nicht unterstützt werden (vor dem Speichern bzw. Start)."""
    konfig = optionen()
    if not modell:
        return "Bitte ein Modell wählen."
    if modell not in modell_aliase() and not re.fullmatch(konfig["eigene_modell_id_muster"], modell):
        return (f"Unbekanntes Modell '{modell[:80]}'. Erlaubt sind die Aliase "
                f"{', '.join(modell_aliase())} oder eine volle Modell-ID (z. B. claude-opus-...).")
    stufen = [a["wert"] for a in konfig["aufwand"]]
    if aufwand not in stufen:
        return f"Unbekannter Aufwand '{aufwand[:20]}'. Erlaubt: {', '.join(s or 'Standard' for s in stufen)}."
    for regel in konfig.get("unvertraeglich", []):
        if regel["modell"] == modell and aufwand in regel["aufwand"]:
            return f"{modell} unterstützt den Aufwand '{aufwand}' nicht: {regel['grund']}"
    return None


def cli_argumente(modell: str, aufwand: str) -> list[str]:
    konfig = optionen()
    argumente = [konfig["modell_flag"], modell]
    if aufwand:
        argumente += [konfig["aufwand_flag"], aufwand]
    return argumente
