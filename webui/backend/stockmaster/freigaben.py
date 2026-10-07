"""Freigaben (Entscheidung 37): Die Claude-CLI fragt, ob ein Befehl laufen darf; ein Administrator entscheidet in der Web-UI.

Ablauf: Der Worker legt je Anfrage eine Zeile an und wartet auf die Entscheidung. Die Anfrage verfällt nach
`freigabe_wartezeit_sekunden` (Standard drei Minuten) und gilt dann als abgelehnt, damit auch Läufe ohne
Bedienung (Zeitplan) nie hängen bleiben. Was die Regeln in `freigabe_regeln` nie freigeben, lehnt der Worker
sofort ab; die Zeile bleibt als Nachweis (Status "gesperrt").
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select, update

from . import freigabe_regeln
from .auftraege import Admin2FA
from .auth import DB, Angemeldet, Streng, audit, begrenzen
from .config import einstellungen
from .db import jetzt_utc, neue_sitzung, utc
from .modelle import Freigabe

TAKT_SEKUNDEN = 1.0  # wie oft der Worker nach der Entscheidung schaut (Tests verkürzen das)
MAX_JE_LAUF = 100
BEFEHL_MAX = 2000
BESCHREIBUNG_MAX = 300
OFFEN, ERLAUBT, ABGELEHNT, ABGELAUFEN, GESPERRT, ABGEBROCHEN = ("offen", "erlaubt", "abgelehnt", "abgelaufen",
                                                                 "gesperrt", "abgebrochen")


# --------------------------------------------------------------------------
# Worker-Seite: eine Anfrage stellen und auf die Entscheidung warten


def _anzeige(werkzeug: str, eingabe: dict) -> str:
    """Befehl im Klartext für die Oberfläche; bei anderen Werkzeugen die Eingabe, gekürzt."""
    befehl = eingabe.get("command")
    if werkzeug == "Bash" and isinstance(befehl, str):
        return befehl[:BEFEHL_MAX]
    return " ".join(f"{k}={v}" for k, v in eingabe.items())[:BEFEHL_MAX] or "(ohne Angaben)"


def _setzen(fid: str, von: str, nach: str, **felder) -> bool:
    """Status nur ändern, solange er noch `von` ist (Entscheidung und Ablauf können gleichzeitig eintreffen)."""
    with neue_sitzung() as db:
        treffer = db.execute(update(Freigabe).where(Freigabe.id == fid, Freigabe.status == von)
                             .values(status=nach, entschieden=jetzt_utc(), **felder)
                             .execution_options(synchronize_session=False)).rowcount
        db.commit()
    return bool(treffer)


def entscheider_fuer(auftrag_id: str, schwaerzen: Callable[[str], str], abbrechen: Callable[[], bool],
                     monoton: Callable[[], float] = time.monotonic,
                     schlafen: Callable[[float], None] = time.sleep) -> Callable[..., tuple[bool, str]]:
    """Entscheider für `claude_lauf.ausfuehren`: (Werkzeug, Eingabe, Beschreibung) -> (erlaubt, Meldung an Claude)."""
    e = einstellungen()
    wartezeit = e.freigabe_wartezeit_sekunden
    bekannt: dict[str, str] = {}  # schon abgelehnte Befehle dieses Laufs: eine Wiederholung wartet nicht erneut
    zaehler = 0

    def entscheiden(werkzeug: str, eingabe: dict, beschreibung: str | None = None) -> tuple[bool, str]:
        nonlocal zaehler
        schluessel = f"{werkzeug}\0{_anzeige(werkzeug, eingabe)}"
        if schluessel in bekannt:
            return False, f"Bereits abgelehnt ({bekannt[schluessel]}). Nicht erneut versuchen."
        zaehler += 1
        if zaehler > MAX_JE_LAUF:
            return False, "Zu viele Freigabe-Anfragen in diesem Lauf."
        bewertung = freigabe_regeln.bewerten(werkzeug, eingabe, e.daten_pfad, e.framework_pfad)
        jetzt = jetzt_utc()
        zeile = Freigabe(auftrag_id=auftrag_id, werkzeug=werkzeug[:60], befehl=schwaerzen(_anzeige(werkzeug, eingabe)),
                         beschreibung=schwaerzen(beschreibung or "")[:BESCHREIBUNG_MAX] or None,
                         status=OFFEN if bewertung.freigebbar else GESPERRT, grund=bewertung.grund,
                         erstellt=jetzt, laeuft_ab=jetzt + timedelta(seconds=wartezeit),
                         entschieden=None if bewertung.freigebbar else jetzt)
        with neue_sitzung() as db:
            db.add(zeile)
            db.commit()
            fid = zeile.id
        if not bewertung.freigebbar:
            bekannt[schluessel] = "nicht freigebbar"
            return False, f"Nicht freigebbar: {bewertung.grund}"
        ende = monoton() + wartezeit
        while True:
            with neue_sitzung() as db:
                aktuell = db.get(Freigabe, fid).status
            if aktuell == ERLAUBT:
                return True, ""
            if aktuell == ABGELEHNT:
                bekannt[schluessel] = "von einem Administrator abgelehnt"
                return False, "Von einem Administrator abgelehnt."
            if abbrechen() and _setzen(fid, OFFEN, ABGEBROCHEN, grund="Lauf abgebrochen"):
                return False, "Lauf abgebrochen."
            if monoton() >= ende and _setzen(fid, OFFEN, ABGELAUFEN, grund=f"Keine Entscheidung in {wartezeit} s"):
                bekannt[schluessel] = "keine Entscheidung rechtzeitig"
                dauer = f"{wartezeit // 60} Minuten" if wartezeit % 60 == 0 else f"{wartezeit} Sekunden"
                return False, f"Keine Entscheidung innerhalb von {dauer}; automatisch abgelehnt."
            schlafen(TAKT_SEKUNDEN)

    return entscheiden


# --------------------------------------------------------------------------
# API


router = APIRouter(prefix="/api/freigaben", tags=["freigaben"])


class Entscheidung(Streng):
    entscheidung: Literal["erlauben", "ablehnen"]


def als_dict(f: Freigabe) -> dict:
    jetzt = jetzt_utc()
    rest = max(0, int((utc(f.laeuft_ab) - jetzt).total_seconds())) if f.status == OFFEN else 0
    return {"id": f.id, "lauf": f.auftrag_id, "werkzeug": f.werkzeug, "befehl": f.befehl,
            "beschreibung": f.beschreibung, "status": f.status, "grund": f.grund,
            "erstellt": utc(f.erstellt).isoformat(), "laeuft_ab": utc(f.laeuft_ab).isoformat(),
            "entschieden": utc(f.entschieden).isoformat() if f.entschieden else None,
            "entscheidbar": f.status == OFFEN and rest > 0, "sekunden_rest": rest}


@router.get("")
def liste(db: DB, _benutzer: Angemeldet, lauf: Annotated[str | None, Query(max_length=36)] = None,
          offen: bool = False, anzahl: Annotated[int, Query(ge=1, le=200)] = 100) -> list[dict]:
    """Freigaben, neueste zuerst; `offen` nur die noch nicht entschiedenen, `lauf` nur die eines Laufs."""
    abfrage = select(Freigabe).order_by(Freigabe.erstellt.desc()).limit(anzahl)
    if lauf:
        abfrage = abfrage.where(Freigabe.auftrag_id == lauf)
    if offen:
        abfrage = abfrage.where(Freigabe.status == OFFEN, Freigabe.laeuft_ab > jetzt_utc())
    return [als_dict(f) for f in db.scalars(abfrage)]


@router.post("/{freigabe_id}/entscheidung")
def entscheiden(freigabe_id: str, daten: Entscheidung, request: Request, db: DB, admin: Admin2FA) -> dict:
    begrenzen(f"freigabe:{admin.id}", 60, 60)
    zeile = db.get(Freigabe, freigabe_id)
    if zeile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nicht gefunden.")
    neu = ERLAUBT if daten.entscheidung == "erlauben" else ABGELEHNT
    jetzt = jetzt_utc()
    # Nur eine noch offene, nicht abgelaufene Anfrage lässt sich entscheiden (kein Nachholen, keine Umentscheidung).
    treffer = db.execute(update(Freigabe).where(Freigabe.id == freigabe_id, Freigabe.status == OFFEN,
                                                Freigabe.laeuft_ab > jetzt)
                         .values(status=neu, entschieden=jetzt, entschieden_von=admin.id)
                         .execution_options(synchronize_session=False)).rowcount
    if not treffer:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Die Anfrage ist nicht mehr offen (entschieden, abgelaufen "
                                                      "oder der Lauf wurde beendet).")
    audit(db, admin.id, f"freigabe_{neu}", request, ziel=freigabe_id,
          meta={"lauf": zeile.auftrag_id, "werkzeug": zeile.werkzeug})
    db.commit()
    db.refresh(zeile)
    return als_dict(zeile)


def schliessen(auftrag_id: str | None = None) -> int:
    """Noch offene Anfragen schließen: eines beendeten Laufs, oder (ohne Angabe) nach dem Start des Dienstes alle.

    Die Claude-CLI, die auf die Antwort wartete, gibt es dann nicht mehr; eine späte Entscheidung wäre wirkungslos.
    """
    bedingung = [Freigabe.status == OFFEN] + ([Freigabe.auftrag_id == auftrag_id] if auftrag_id else [])
    with neue_sitzung() as db:
        treffer = db.execute(update(Freigabe).where(*bedingung)
                             .values(status=ABGEBROCHEN, grund="Lauf beendet", entschieden=jetzt_utc())
                             .execution_options(synchronize_session=False)).rowcount
        db.commit()
    return treffer
