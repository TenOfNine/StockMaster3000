"""Lesende Spiel-API (Stufe 1). Alle Routen verlangen eine vollständige Anmeldung."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth import DB, Angemeldet, angemeldet, begrenzen
from . import lesen

router = APIRouter(prefix="/api/spiel", tags=["spiel"], dependencies=[Depends(angemeldet)])
Profil = Annotated[str, Query(pattern=r"^(defensiv|ausgewogen|aggressiv)$")]


def _404(funktion, *argumente):
    try:
        return funktion(*argumente)
    except lesen.NichtGefunden as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/ueberblick")
def ueberblick(db: DB) -> dict:
    from ..auftraege import letzter_lauf
    from ..einrichtung import pflichtschritte

    bench = lesen.benchmark()
    profile = lesen.profile()
    journal = lesen.journal()
    sessions = [e for e in journal if e["art"] == "S"][-5:][::-1]
    return {
        "einrichtung_offen": pflichtschritte(),
        "letzter_lauf": letzter_lauf(db),
        "news": lesen.news(anzahl=8)["meldungen"],
        "repo": lesen.repo_info(),
        "status": lesen.status()["kopf"],
        "sperre": lesen.sperre(),
        "termine": lesen.termine(),
        "profile": {p: lesen.kennzahlen(p, bench) for p in profile},
        "letzte_sessions": sessions,
        "letzte_entscheidungen": [e for e in journal if e["art"] == "J"][-6:][::-1],
        "gestartet": bool(profile),
    }


@router.get("/nav")
def nav() -> dict:
    return lesen.nav_reihen()


@router.get("/portfolios/{profil}")
def portfolio(profil: Literal["defensiv", "ausgewogen", "aggressiv"]) -> dict:
    return _404(lesen.portfolio, profil)


@router.get("/portfolios/{profil}/trades")
def trades(profil: Literal["defensiv", "ausgewogen", "aggressiv"]) -> list[dict]:
    return _404(lesen.trades, profil)


@router.get("/journal")
def journal() -> list[dict]:
    return lesen.journal()


@router.get("/journal/{eintrag_id}")
def journal_eintrag(eintrag_id: str) -> dict:
    return _404(lesen.journal_eintrag, eintrag_id)


@router.get("/status")
def status_md() -> dict:
    return lesen.status()


@router.get("/dokumente")
def dokumente() -> list[dict]:
    return lesen.dokumente()


@router.get("/dokument")
def dokument(pfad: Annotated[str, Query(max_length=120, pattern=r"^[A-Za-z0-9_./-]+\.md$")]) -> dict:
    return _404(lesen.dokument, pfad)


@router.get("/reviews")
def reviews() -> list[dict]:
    return lesen.reviews()


@router.get("/lessons")
def lessons() -> list[dict]:
    return lesen.lessons()


@router.get("/konfiguration")
def konfiguration() -> dict:
    return lesen.konfiguration()


@router.get("/termine")
def termine() -> list[dict]:
    return lesen.termine()


@router.get("/kurse")
def kurs_ticker() -> list[dict]:
    return lesen.kurs_ticker()


@router.get("/markt")
def markt() -> dict:
    return lesen.markt()


@router.get("/news")
def news(ticker: Annotated[str | None, Query(max_length=20)] = None,
         anzahl: Annotated[int, Query(ge=1, le=200)] = 50, tage: Annotated[int, Query(ge=1, le=365)] = 30) -> dict:
    return _404(lesen.news, ticker, anzahl, tage)


@router.get("/kurse/{ticker}")
def kurs_historie(ticker: str) -> list[dict]:
    return _404(lesen.historie, ticker)


def _dezimal(wert: str, name: str) -> Decimal:
    try:
        zahl = Decimal(wert.replace(",", "."))
    except InvalidOperation as exc:
        raise HTTPException(422, f"{name} ist keine Zahl.") from exc
    if not zahl.is_finite() or zahl <= 0 or zahl > Decimal("1e9"):
        raise HTTPException(422, f"{name} liegt außerhalb des zulässigen Bereichs.")
    return zahl


@router.get("/rechner/ko")
def rechner_ko(richtung: Literal["long", "short"], kurs: Annotated[str, Query(max_length=20)],
               hebel: Annotated[str, Query(max_length=10)]) -> dict:
    hebel_wert = _dezimal(hebel, "Hebel")
    if hebel_wert <= 1 or hebel_wert > 100:
        raise HTTPException(422, "Der Hebel muss zwischen 1 und 100 liegen.")
    return lesen.rechner_ko(richtung, _dezimal(kurs, "Kurs"), hebel_wert)


@router.get("/rechner/faktor")
def rechner_faktor(richtung: Literal["long", "short"], faktor: Annotated[str, Query(max_length=10)],
                   kurse: Annotated[str, Query(max_length=2000)]) -> dict:
    faktor_wert = _dezimal(faktor, "Faktor")
    if faktor_wert < 1 or faktor_wert > 20:
        raise HTTPException(422, "Der Faktor muss zwischen 1 und 20 liegen.")
    reihe = [_dezimal(k, "Kurs") for k in kurse.split(";") if k.strip()]
    if not 2 <= len(reihe) <= 120:
        raise HTTPException(422, "Zwischen 2 und 120 Kurse angeben.")
    return lesen.rechner_faktor(richtung, faktor_wert, reihe)


@router.get("/git")
def git_log(anzahl: Annotated[int, Query(ge=1, le=500)] = 100) -> list[dict]:
    return lesen.git_log(anzahl)


@router.get("/git/{hash_wert}")
def git_commit(hash_wert: str) -> dict:
    return _404(lesen.git_commit, hash_wert)


@router.post("/pruefung")
def pruefung(benutzer: Angemeldet) -> dict:
    begrenzen(f"pruefung:{benutzer.id}", 10, 3600)
    return lesen.pruefung()
