"""Einrichtung: Einstellungen und Secrets in der App, Verbindungstests, Systemstatus, Spielstart.

Lesen und Schreiben nur für Admins mit Zwei-Faktor; jede Änderung mit CSRF-Prüfung (über die
Anmeldung) und Audit-Eintrag ohne Werte. Secrets werden nie zurückgegeben, nur "gesetzt" und die
letzten vier Zeichen.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, field_validator

from . import appdaten, auftraege, claude_optionen
from .auftraege import Admin2FA, admin_2fa
from .auth import DB, Streng, audit, begrenzen
from .config import einstellungen
from .db import jetzt_utc

router = APIRouter(prefix="/api/einrichtung", tags=["einrichtung"], dependencies=[Depends(admin_2fa)])

TZ = ZoneInfo("Europe/Berlin")
FEED_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
TICKER = re.compile(r"^[A-Z0-9^=.\-]{1,20}$")
UHRZEIT = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


# --------------------------------------------------------------------------
# Hilfen


def _werkzeuge():
    from .spiel import lesen

    return lesen.werkzeuge()


def _lesen():
    from .spiel import lesen

    return lesen


def _zeit(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        wert = datetime.fromisoformat(text)
    except ValueError:
        return None
    return wert if wert.tzinfo else wert.replace(tzinfo=TZ)


def _alter_text(zeit: datetime | None) -> str:
    if zeit is None:
        return "nie"
    minuten = int((datetime.now(UTC) - zeit).total_seconds() // 60)
    if minuten < 1:
        return "gerade eben"
    if minuten < 120:
        return f"vor {minuten} Min."
    if minuten < 48 * 60:
        return f"vor {minuten // 60} Std."
    return f"vor {minuten // 1440} Tagen"


def _cache(name: str) -> dict:
    datei = einstellungen().daten_pfad / ".cache" / name
    try:
        return json.loads(datei.read_text(encoding="utf-8")) if datei.exists() else {}
    except (OSError, ValueError):
        return {}


def news_konfig_wirksam() -> dict:
    """config/news.json plus Änderungen aus der App (aus/an, eigene Feeds, Intervall, User-Agent)."""
    basis = json.loads((einstellungen().framework_pfad / "config" / "news.json").read_text(encoding="utf-8"))
    app = appdaten.laden()["news"]
    feeds = [{**f, "aktiv": f.get("aktiv", True) and f["id"] not in app["deaktiviert"]} for f in basis["feeds"]]
    feeds += [{**f, "aktiv": f.get("aktiv", True), "eigen": True} for f in app["eigene"]]
    return {**basis, "feeds": feeds, "intervall_minuten": app["intervall_minuten"],
            "user_agent": app.get("user_agent") or basis["user_agent"]}


def kursquellen() -> dict:
    return json.loads((einstellungen().framework_pfad / "config" / "kursquellen.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Pflichtschritte und Systemstatus


def pflichtschritte() -> list[dict]:
    """Offene Pflichtschritte in Reihenfolge (für den Cockpit-Hinweis); leer = alles erledigt."""
    offen = []
    markt = _cache("markt.json")
    markt_zeit = _zeit(markt.get("zeit"))
    if not markt.get("erfolgreich") or not markt_zeit or datetime.now(UTC) - markt_zeit > timedelta(days=1):
        offen.append({"schritt": "kursdaten", "titel": "Kursdaten einrichten",
                      "text": "Noch keine Kursquelle erreichbar. Kursanbieter wählen oder Verbindung testen.",
                      "link": "/einrichtung#kursdaten"})
    if not appdaten.geheimnis_info("claude_token")["gesetzt"]:
        offen.append({"schritt": "claude", "titel": "Claude verbinden",
                      "text": "Kein Claude-Token hinterlegt; Sessions können nicht starten.",
                      "link": "/einrichtung#claude"})
    try:
        gestartet = bool(_werkzeuge()["gemeinsam"].spiel_lesen().get("startdatum"))
    except Exception:  # noqa: BLE001 - Datenverzeichnis fehlt: ebenfalls offen
        gestartet = False
    if not gestartet:
        offen.append({"schritt": "spielstart", "titel": "Spiel starten",
                      "text": "Das Spiel ist noch nicht gestartet (Startdatum fehlt).", "link": "/einrichtung#spielstart"})
    else:
        try:
            ohne = _werkzeuge()["gemeinsam"].richtlinien_offen()
        except Exception:  # noqa: BLE001
            ohne = []
        if ohne:
            offen.append({"schritt": "richtlinien", "titel": "Anlagerichtlinien ausformulieren",
                          "text": f"Für {', '.join(ohne)} gibt es nur die Vorlage; vor der ersten Trading-Session "
                                  "den Lauf „Anlagerichtlinien ausformulieren“ starten.",
                          "link": "/laeufe"})
    return offen


def _ampel(kennung: str, titel: str, stufe: str, text: str) -> dict:
    return {"id": kennung, "titel": titel, "stufe": stufe, "text": text}


def systemstatus() -> list[dict]:
    e = einstellungen()
    status = []
    try:
        dv = _werkzeuge()["datenverzeichnis"].status(e.daten_pfad)
    except Exception as exc:  # noqa: BLE001
        dv = {"vorhanden": False, "git": False, "fehler": str(exc)}
    if not dv.get("vorhanden"):
        status.append(_ampel("daten", "Datenverzeichnis", "rot", f"{e.daten_pfad} fehlt."))
    elif not dv.get("beschreibbar"):
        status.append(_ampel("daten", "Datenverzeichnis", "rot", f"{e.daten_pfad} ist nicht beschreibbar."))
    else:
        status.append(_ampel("daten", "Datenverzeichnis", "gruen", f"{e.daten_pfad} vorhanden und beschreibbar."))
    if not dv.get("git"):
        status.append(_ampel("git", "Lokales Git", "rot", "Das Datenverzeichnis ist kein Git-Repository."))
    elif dv.get("remotes"):
        status.append(_ampel("git", "Lokales Git", "gelb",
                             f"Remote vorhanden ({', '.join(dv['remotes'])}); Spielstand bleibt trotzdem lokal."))
    else:
        letzter = dv.get("letzter_commit") or {}
        offen = dv.get("offene_aenderungen", 0)
        text = (f"{dv['commits']} Commits, letzter {_alter_text(_zeit(letzter.get('zeit')))}"
                f" ({letzter.get('text', '')[:60]}). Ohne Remote.")
        if offen:
            text += f" {offen} Änderungen noch nicht committet (werden mit dem nächsten Abruf bzw. der Session committet)."
        status.append(_ampel("git", "Lokales Git", "gruen", text))

    kurs = appdaten.laden()["kursdaten"]
    markt = _cache("markt.json")
    markt_zeit = _zeit(markt.get("zeit"))
    if not markt_zeit:
        status.append(_ampel("kurse", "Letzter Kursabruf", "rot", "Noch kein Kursabruf."))
    else:
        alt = datetime.now(UTC) - markt_zeit > timedelta(minutes=2 * int(kurs["intervall_geschlossen_minuten"]) + 10)
        teilweise = markt.get("erfolgreich", 0) < markt.get("anzahl", 0)
        stufe = "rot" if not markt.get("erfolgreich") else ("gelb" if alt or teilweise else "gruen")
        text = (f"{_alter_text(markt_zeit)}: {markt.get('erfolgreich', 0)} von {markt.get('anzahl', 0)} Kursen aktuell"
                f" (zuerst gefragt: {markt.get('quelle_konfiguriert', '–')}).")
        if teilweise:
            text += " Fehlende Werte zeigen den letzten bekannten Kurs mit Kennzeichnung „veraltet“."
        status.append(_ampel("kurse", "Letzter Kursabruf", stufe, text))

    news = _cache("news_stand.json")
    news_zeit = _zeit(news.get("zeit"))
    intervall = int(appdaten.laden()["news"]["intervall_minuten"])
    if not appdaten.laden()["news"]["aktiv"]:
        status.append(_ampel("news", "Letzter News-Abruf", "gelb", "News-Abruf ist ausgeschaltet."))
    elif not news_zeit:
        status.append(_ampel("news", "Letzter News-Abruf", "rot", "Noch kein News-Abruf."))
    else:
        alt = datetime.now(UTC) - news_zeit > timedelta(minutes=3 * intervall + 5)
        fehler = news.get("fehlerhaft", 0)
        stufe = "rot" if fehler and fehler == news.get("anzahl_feeds") else ("gelb" if alt or fehler else "gruen")
        status.append(_ampel("news", "Letzter News-Abruf", stufe,
                             f"{_alter_text(news_zeit)}: {news.get('neu', 0)} neue Meldungen, {fehler} von "
                             f"{news.get('anzahl_feeds', 0)} Feeds mit Fehler."))

    info = appdaten.geheimnis_info("claude_token")
    test = appdaten.laden()["claude"].get("letzter_test") or {}
    if not info["gesetzt"]:
        status.append(_ampel("claude", "Claude-Verbindung", "rot", "Kein Claude-Token hinterlegt."))
    elif not test:
        status.append(_ampel("claude", "Claude-Verbindung", "gelb", "Token hinterlegt, Verbindung noch nicht getestet."))
    else:
        status.append(_ampel("claude", "Claude-Verbindung", "gruen" if test.get("ok") else "rot",
                             f"Test {_alter_text(_zeit(test.get('zeit')))}: {test.get('meldung', '')}"))

    herz = appdaten.zustand_lesen("worker")
    herz_zeit = _zeit(herz.get("zeit"))
    if herz_zeit and datetime.now(UTC) - herz_zeit < timedelta(minutes=3):
        status.append(_ampel("worker", "Hintergrunddienst", "gruen",
                             f"Aktiv ({_alter_text(herz_zeit)}); {herz.get('meldung', '')}".strip()))
    else:
        status.append(_ampel("worker", "Hintergrunddienst", "rot",
                             "Der Dienst 'worker' meldet sich nicht. Kurse, News, Tests und Sessions laufen nur dort."))
    return status


# --------------------------------------------------------------------------
# Spielstart


def naechster_handelstag(ab: date) -> date:
    kurse = _werkzeuge()["kurse"]
    tag = ab
    for _ in range(14):
        if kurse.ist_handelstag("EUNL.DE", tag):
            return tag
        tag += timedelta(days=1)
    return ab


def spielstart_checkliste(db) -> dict:
    w = _werkzeuge()
    g = w["gemeinsam"]
    spiel = g.spiel_lesen()
    punkte = []
    try:
        import init as init_werkzeug  # noqa: PLC0415 - aus tools/, nach werkzeuge() importierbar

        init_werkzeug.status_pruefen()
        punkte.append({"id": "aufbau", "pflicht": True, "ok": True, "text": "Aufbau AP1 bis AP10 abgeschlossen."})
    except Exception as exc:  # noqa: BLE001
        punkte.append({"id": "aufbau", "pflicht": True, "ok": False, "text": str(exc)})
    punkte.append({"id": "nicht_gestartet", "pflicht": True, "ok": not spiel.get("startdatum"),
                   "text": "Noch nicht gestartet." if not spiel.get("startdatum")
                   else f"Bereits gestartet am {spiel['startdatum']} (nur einmal möglich)."})
    markt = _cache("markt.json")
    benchmark = next((x for x in markt.get("eintraege", []) if x.get("ticker") == "EUNL.DE"), None)
    punkte.append({"id": "kurse", "pflicht": True, "ok": bool(benchmark and benchmark.get("kurs") is not None),
                   "text": "Benchmark EUNL.DE hat einen Kurs (Kursabruf funktioniert)." if benchmark and
                   benchmark.get("kurs") is not None else "Kein Kurs für den Benchmark EUNL.DE: Kursdaten zuerst einrichten."})
    sperre = auftraege.session_sperre_aktiv()
    punkte.append({"id": "keine_session", "pflicht": True, "ok": sperre is None and auftraege.offener_lauf(db) is None,
                   "text": "Keine Session aktiv." if sperre is None else f"Session von {sperre['person']} läuft."})
    offen_richtlinien = g.richtlinien_offen()
    punkte.append({"id": "richtlinien", "pflicht": False, "ok": not offen_richtlinien,
                   "text": "Anlagerichtlinien aller Profile ausformuliert (AP12 Punkt 2)." if not offen_richtlinien
                   else f"Empfohlen vor der Freigabe: Anlagerichtlinien ausformulieren ({', '.join(offen_richtlinien)}); "
                        "Trading-Sessions starten erst, wenn sie vorliegen."})
    test = appdaten.laden()["claude"].get("letzter_test") or {}
    punkte.append({"id": "claude", "pflicht": False, "ok": bool(test.get("ok")),
                   "text": "Claude-Verbindung erfolgreich getestet." if test.get("ok")
                   else "Empfohlen: Claude-Verbindung testen (für Sessions nötig)."})
    from sqlalchemy import select

    from .modelle import Auftrag

    testsession = db.scalar(select(Auftrag).where(Auftrag.art == "testsession", Auftrag.status == "ok").limit(1))
    punkte.append({"id": "testsession", "pflicht": False, "ok": testsession is not None,
                   "text": "Testsession ohne Trades (AP12) durchgeführt." if testsession
                   else "Empfohlen: Testsession ohne Trades (AP12) durchführen, bevor die Freigabe erteilt wird."})
    morgen = date.today() if datetime.now(TZ).hour < 9 else date.today() + timedelta(days=1)
    return {"punkte": punkte, "bereit": all(p["ok"] for p in punkte if p["pflicht"]),
            "gestartet": bool(spiel.get("startdatum")), "spiel": spiel,
            "vorschlag_startdatum": naechster_handelstag(morgen).isoformat(),
            "auftraggeber": g.projekt()["auftraggeber"]}


# --------------------------------------------------------------------------
# Lesen


@router.get("")
def ueberblick(db: DB) -> dict:
    app = appdaten.laden()
    quellen = kursquellen()
    news = news_konfig_wirksam()
    return {
        "einstellungen": {k: v for k, v in app.items() if k != "migration"},
        "geheimnisse": {name: appdaten.geheimnis_info(name) for name in appdaten.GEHEIMNISSE},
        "optionen": {
            "claude": claude_optionen.optionen(),
            "kursanbieter": [{"id": k, "name": v["name"], "hinweis": v.get("hinweis"), "doku": v.get("doku")}
                             for k, v in quellen["anbieter"].items()],
            "news_feeds": [{"id": f["id"], "name": f.get("name", f["id"]), "url": f["url"],
                            "je_ticker": bool(f.get("je_ticker")), "aktiv": f["aktiv"], "eigen": bool(f.get("eigen")),
                            "ticker": f.get("ticker", [])} for f in news["feeds"]],
            "auftraggeber": _lesen().konfiguration()["projekt"]["auftraggeber"],
        },
        "migration": {"aus_umgebung": app["migration"]["aus_umgebung"],
                      "ueberfluessige_variablen": appdaten.ueberfluessige_variablen()},
        "pflichtschritte": pflichtschritte(),
        "systemstatus": systemstatus(),
        "spielstart": spielstart_checkliste(db),
        "pfade": {"daten": str(einstellungen().daten_pfad), "app": str(einstellungen().app_pfad)},
    }


# --------------------------------------------------------------------------
# Claude


class Voreinstellung(Streng):
    modell: str = Field(max_length=100)
    aufwand: str = Field(default="", max_length=20)


class ClaudeDaten(Streng):
    trading: Voreinstellung
    review: Voreinstellung


@router.put("/claude")
def claude_speichern(daten: ClaudeDaten, request: Request, db: DB, admin: Admin2FA) -> dict:
    for zweck, v in (("Trading-Session", daten.trading), ("Review/Bericht", daten.review)):
        fehler = claude_optionen.pruefen(v.modell.strip(), v.aufwand)
        if fehler:
            raise HTTPException(422, f"{zweck}: {fehler}")
    werte = {"trading": {"modell": daten.trading.modell.strip(), "aufwand": daten.trading.aufwand},
             "review": {"modell": daten.review.modell.strip(), "aufwand": daten.review.aufwand}}
    appdaten.bereich_speichern("claude", {"voreinstellungen": werte})
    audit(db, admin.id, "einrichtung_claude", request, meta={"trading": werte["trading"], "review": werte["review"]})
    db.commit()
    return {"ok": True, "voreinstellungen": werte}


class GeheimnisDaten(Streng):
    wert: str = Field(min_length=8, max_length=4000)

    @field_validator("wert")
    @classmethod
    def _ohne_leerraum(cls, wert: str) -> str:
        wert = wert.strip()
        if any(z.isspace() for z in wert) or not wert.isprintable():
            raise ValueError("Der Wert darf keine Leerzeichen oder Steuerzeichen enthalten.")
        return wert


@router.put("/geheimnis/{name}")
def geheimnis_setzen(name: Literal["claude_token", "kurs_key_finnhub", "kurs_key_twelvedata"], daten: GeheimnisDaten,
                     request: Request, db: DB, admin: Admin2FA) -> dict:
    begrenzen(f"geheimnis:{admin.id}", 20, 3600)
    if name == "claude_token" and not daten.wert.startswith("sk-ant-"):
        raise HTTPException(422, "Das sieht nicht nach einem Claude-Token aus (beginnt mit 'sk-ant-'). "
                                 "Erzeugen mit: claude setup-token")
    appdaten.geheimnis_setzen(name, daten.wert)
    if name == "claude_token":
        appdaten.bereich_speichern("claude", {"letzter_test": None})
    audit(db, admin.id, "einrichtung_geheimnis_geaendert", request, ziel=name,
          meta={"text": f"{appdaten.GEHEIMNISSE[name]} geändert"})
    db.commit()
    return appdaten.geheimnis_info(name)


@router.delete("/geheimnis/{name}")
def geheimnis_loeschen(name: Literal["claude_token", "kurs_key_finnhub", "kurs_key_twelvedata"], request: Request,
                       db: DB, admin: Admin2FA) -> dict:
    appdaten.geheimnis_loeschen(name)
    audit(db, admin.id, "einrichtung_geheimnis_geloescht", request, ziel=name,
          meta={"text": f"{appdaten.GEHEIMNISSE[name]} gelöscht"})
    db.commit()
    return appdaten.geheimnis_info(name)


def _test_ausfuehren(db, admin, request, art: str, parameter: dict, aktion: str) -> dict:
    begrenzen(f"test:{admin.id}", 20, 600)
    auftrag = auftraege.anlegen(db, art, parameter, erstellt_von=admin.id)
    audit(db, admin.id, aktion, request, ziel=auftrag.id)
    db.commit()
    ergebnis = auftraege.warten(auftrag.id, einstellungen().auftrag_warten_sekunden)
    daten = auftraege.als_dict(ergebnis) if ergebnis else {"status": "wartet"}
    if daten["status"] in auftraege.OFFEN:
        daten["meldung"] = ("Der Hintergrunddienst hat den Test noch nicht abgeschlossen. Das Ergebnis erscheint "
                            "im Systemstatus; läuft der Dienst 'worker'?")
    return daten


def _anmeldung(auftrag) -> dict:
    """Stand einer Anmeldung für die UI: nie das Token, nur Phase, Link und Meldung."""
    ergebnis = json.loads(auftrag.ergebnis) if auftrag and auftrag.ergebnis else {}
    return {"id": auftrag.id if auftrag else None, "status": auftrag.status if auftrag else "wartet",
            "phase": ergebnis.get("phase", "starte"), "link": ergebnis.get("link"),
            "test_ok": ergebnis.get("test_ok"), "meldung": auftrag.meldung if auftrag else None,
            "token": appdaten.geheimnis_info("claude_token")}


def _anmeldung_laden(db, auftrag_id: str):
    from .modelle import Auftrag

    auftrag = db.get(Auftrag, auftrag_id)
    if auftrag is None or auftrag.art != "claude_anmeldung":
        raise HTTPException(404, "Anmeldung nicht gefunden.")
    return auftrag


@router.post("/claude/anmeldung")
def claude_anmeldung_starten(request: Request, db: DB, admin: Admin2FA) -> dict:
    """Startet `claude setup-token` im Worker und liefert den Anmeldelink."""
    from sqlalchemy import select

    from .modelle import Auftrag

    begrenzen(f"anmeldung:{admin.id}", 10, 3600)
    for offen in db.scalars(select(Auftrag).where(Auftrag.art == "claude_anmeldung",
                                                  Auftrag.status.in_(auftraege.OFFEN))).all():
        offen.abbrechen = True  # es gibt immer nur eine laufende Anmeldung
    auftrag = auftraege.anlegen(db, "claude_anmeldung", {}, erstellt_von=admin.id)
    audit(db, admin.id, "einrichtung_claude_anmeldung_gestartet", request, ziel=auftrag.id)
    db.commit()
    stand = auftraege.warten_bis(auftrag.id, min(30.0, einstellungen().auftrag_warten_sekunden),
                                 lambda a: bool(a.ergebnis and '"link"' in a.ergebnis))
    daten = _anmeldung(stand)
    if daten["status"] in auftraege.OFFEN and not daten["link"]:
        daten["meldung"] = "Der Hintergrunddienst bereitet die Anmeldung vor …"
    return daten


@router.get("/claude/anmeldung/{auftrag_id}")
def claude_anmeldung_stand(auftrag_id: str, db: DB) -> dict:
    return _anmeldung(_anmeldung_laden(db, auftrag_id))


class AnmeldeCode(Streng):
    code: str = Field(min_length=8, max_length=512)


@router.post("/claude/anmeldung/{auftrag_id}/code")
def claude_anmeldung_code(auftrag_id: str, daten: AnmeldeCode, request: Request, db: DB, admin: Admin2FA) -> dict:
    from . import claude_anmeldung

    begrenzen(f"anmeldecode:{admin.id}", 10, 600)
    try:
        code = claude_anmeldung.code_pruefen(daten.code)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    auftrag = _anmeldung_laden(db, auftrag_id)
    if auftrag.status not in auftraege.OFFEN or _anmeldung(auftrag)["phase"] != "warte_auf_code":
        raise HTTPException(409, "Diese Anmeldung wartet nicht auf einen Code. Bitte neu starten.")
    datei = auftraege.anmeldecode_pfad(auftrag_id)
    datei.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(datei, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(code)
    audit(db, admin.id, "einrichtung_claude_anmeldung_code", request, ziel=auftrag_id,
          meta={"text": "Anmeldecode übergeben"})
    db.commit()
    stand = auftraege.warten_bis(auftrag_id, einstellungen().auftrag_warten_sekunden, lambda a: False)
    daten = _anmeldung(stand)
    if daten["status"] in auftraege.OFFEN:
        daten["meldung"] = "Der Code wird geprüft …"
    return daten


@router.post("/claude/anmeldung/{auftrag_id}/abbrechen")
def claude_anmeldung_abbrechen(auftrag_id: str, request: Request, db: DB, admin: Admin2FA) -> dict:
    auftrag = _anmeldung_laden(db, auftrag_id)
    if auftrag.status in auftraege.OFFEN:
        auftrag.abbrechen = True
        if auftrag.status == "wartet":
            auftrag.status, auftrag.beendet, auftrag.meldung = "abgebrochen", jetzt_utc(), "Abgebrochen."
    auftraege.anmeldecode_pfad(auftrag_id).unlink(missing_ok=True)
    audit(db, admin.id, "einrichtung_claude_anmeldung_abgebrochen", request, ziel=auftrag_id)
    db.commit()
    return _anmeldung(auftrag)


@router.post("/claude/test")
def claude_test(request: Request, db: DB, admin: Admin2FA) -> dict:
    if not appdaten.geheimnis_info("claude_token")["gesetzt"]:
        raise HTTPException(409, "Zuerst ein Claude-Token hinterlegen.")
    return _test_ausfuehren(db, admin, request, "test_claude", {}, "einrichtung_claude_test")


# --------------------------------------------------------------------------
# Kursdaten


class KursDaten(Streng):
    anbieter: Literal["keiner", "finnhub", "twelvedata"]
    intervall_offen_minuten: int = Field(ge=1, le=60)
    intervall_geschlossen_minuten: int = Field(ge=5, le=1440)


@router.put("/kursdaten")
def kursdaten_speichern(daten: KursDaten, request: Request, db: DB, admin: Admin2FA) -> dict:
    if daten.anbieter != "keiner" and not appdaten.geheimnis_info(f"kurs_key_{daten.anbieter}")["gesetzt"]:
        raise HTTPException(422, f"Für {kursquellen()['anbieter'][daten.anbieter]['name']} zuerst den API-Key eintragen.")
    werte = daten.model_dump()
    appdaten.bereich_speichern("kursdaten", werte)
    audit(db, admin.id, "einrichtung_kursdaten", request, meta=werte)
    db.commit()
    return {"ok": True, "kursdaten": appdaten.laden()["kursdaten"]}


class KursTest(Streng):
    anbieter: Literal["finnhub", "twelvedata", "yfinance"]


@router.post("/kursdaten/test")
def kursdaten_test(daten: KursTest, request: Request, db: DB, admin: Admin2FA) -> dict:
    if daten.anbieter != "yfinance" and not appdaten.geheimnis_info(f"kurs_key_{daten.anbieter}")["gesetzt"]:
        raise HTTPException(409, "Zuerst den API-Key eintragen.")
    return _test_ausfuehren(db, admin, request, "test_kurse", {"anbieter": daten.anbieter}, "einrichtung_kurse_test")


@router.post("/kursdaten/abrufen")
def kursdaten_abrufen(request: Request, db: DB, admin: Admin2FA) -> dict:
    return _test_ausfuehren(db, admin, request, "kurse_jetzt", {"historie": True}, "einrichtung_kurse_abruf")


# --------------------------------------------------------------------------
# News


class EigenerFeed(Streng):
    id: str = Field(max_length=41)
    name: str = Field(min_length=2, max_length=80)
    url: str = Field(max_length=500)
    aktiv: bool = True
    ticker: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("id")
    @classmethod
    def _id(cls, wert: str) -> str:
        if not FEED_ID.match(wert):
            raise ValueError("Kennung: Kleinbuchstaben, Ziffern und Bindestrich.")
        return wert

    @field_validator("url")
    @classmethod
    def _url(cls, wert: str) -> str:
        if not re.match(r"^https?://[^\s/$.?#][^\s]*$", wert):
            raise ValueError("Nur http(s)-Adressen.")
        return wert

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, wert: list[str]) -> list[str]:
        for t in wert:
            if not TICKER.match(t):
                raise ValueError(f"Ungültiger Ticker {t[:20]}.")
        return wert


class NewsDaten(Streng):
    aktiv: bool
    intervall_minuten: int = Field(ge=5, le=1440)
    deaktiviert: list[str] = Field(default_factory=list, max_length=100)
    eigene: list[EigenerFeed] = Field(default_factory=list, max_length=50)
    user_agent: str = Field(default="", max_length=200)


@router.put("/news")
def news_speichern(daten: NewsDaten, request: Request, db: DB, admin: Admin2FA) -> dict:
    standard = {f["id"] for f in json.loads((einstellungen().framework_pfad / "config" / "news.json")
                                           .read_text(encoding="utf-8"))["feeds"]}
    unbekannt = [d for d in daten.deaktiviert if d not in standard]
    if unbekannt:
        raise HTTPException(422, f"Unbekannte Standard-Feeds: {', '.join(unbekannt)[:200]}.")
    ids = [f.id for f in daten.eigene]
    if len(set(ids)) != len(ids) or set(ids) & standard:
        raise HTTPException(422, "Feed-Kennungen müssen eindeutig sein und dürfen keinem Standard-Feed entsprechen.")
    if daten.user_agent and not daten.user_agent.isprintable():
        raise HTTPException(422, "User-Agent enthält Steuerzeichen.")
    werte = daten.model_dump()
    appdaten.bereich_speichern("news", werte)
    audit(db, admin.id, "einrichtung_news", request,
          meta={"aktiv": daten.aktiv, "intervall": daten.intervall_minuten, "deaktiviert": len(daten.deaktiviert),
                "eigene": len(daten.eigene)})
    db.commit()
    return {"ok": True, "news": appdaten.laden()["news"]}


class FeedTest(Streng):
    url: str = Field(max_length=500)

    @field_validator("url")
    @classmethod
    def _url(cls, wert: str) -> str:
        if not re.match(r"^https?://[^\s/$.?#][^\s]*$", wert):
            raise ValueError("Nur http(s)-Adressen.")
        return wert


@router.post("/news/test")
def news_test(daten: FeedTest, request: Request, db: DB, admin: Admin2FA) -> dict:
    return _test_ausfuehren(db, admin, request, "test_feed", {"url": daten.url}, "einrichtung_feed_test")


@router.post("/news/abrufen")
def news_abrufen(request: Request, db: DB, admin: Admin2FA) -> dict:
    return _test_ausfuehren(db, admin, request, "news_jetzt", {}, "einrichtung_news_abruf")


# --------------------------------------------------------------------------
# Zeitplan


class Termin(Streng):
    wochentage: list[int] = Field(min_length=1, max_length=7)
    uhrzeit: str
    art: Literal["trading", "review"]

    @field_validator("wochentage")
    @classmethod
    def _tage(cls, wert: list[int]) -> list[int]:
        if any(t < 0 or t > 6 for t in wert):
            raise ValueError("Wochentage 0 (Montag) bis 6 (Sonntag).")
        return sorted(set(wert))

    @field_validator("uhrzeit")
    @classmethod
    def _uhrzeit(cls, wert: str) -> str:
        if not UHRZEIT.match(wert):
            raise ValueError("Uhrzeit als HH:MM.")
        return wert


class ZeitplanDaten(Streng):
    automatik: bool
    zeitzone: str = Field(max_length=60)
    auftraggeber: str = Field(max_length=40)
    termine: list[Termin] = Field(max_length=12)


@router.put("/zeitplan")
def zeitplan_speichern(daten: ZeitplanDaten, request: Request, db: DB, admin: Admin2FA) -> dict:
    try:
        ZoneInfo(daten.zeitzone)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(422, f"Unbekannte Zeitzone '{daten.zeitzone[:60]}'.") from None
    if daten.auftraggeber not in _lesen().konfiguration()["projekt"]["auftraggeber"]:
        raise HTTPException(422, "Auftraggeber muss eine Kennung aus config/projekt.json sein.")
    if daten.automatik:
        if not daten.termine:
            raise HTTPException(422, "Für die Automatik mindestens einen Termin angeben.")
        if not appdaten.geheimnis_info("claude_token")["gesetzt"]:
            raise HTTPException(422, "Die Automatik braucht ein Claude-Token (Bereich Claude).")
    werte = daten.model_dump()
    appdaten.bereich_speichern("zeitplan", werte)
    audit(db, admin.id, "einrichtung_zeitplan", request,
          meta={"automatik": daten.automatik, "termine": len(daten.termine), "zeitzone": daten.zeitzone})
    db.commit()
    return {"ok": True, "zeitplan": appdaten.laden()["zeitplan"]}


# --------------------------------------------------------------------------
# Spielstart (tools/init.py), nur einmal


class SpielstartDaten(Streng):
    startdatum: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    freigabe_durch: str = Field(max_length=40)
    freigabe_ap12_bestaetigt: bool
    passwort: str = Field(min_length=1, max_length=200)


@router.post("/spielstart")
def spielstart(daten: SpielstartDaten, request: Request, db: DB, admin: Admin2FA) -> dict:
    from .admin import bestaetigen

    bestaetigen(admin, daten.passwort)
    if not daten.freigabe_ap12_bestaetigt:
        raise HTTPException(422, "Die Freigabe nach AP12 durch einen Auftraggeber muss bestätigt werden.")
    liste = spielstart_checkliste(db)
    offen = [p["text"] for p in liste["punkte"] if p["pflicht"] and not p["ok"]]
    if offen:
        raise HTTPException(409, "Voraussetzungen fehlen: " + " ".join(offen))
    e = einstellungen()
    umgebung = {**os.environ, "STOCKMASTER_DATA_DIR": str(e.daten_pfad),
                "STOCKMASTER_FRAMEWORK_DIR": str(e.framework_pfad), "PYTHONDONTWRITEBYTECODE": "1"}
    werkzeug = e.framework_pfad / "tools"
    ergebnis = subprocess.run([sys.executable, str(werkzeug / "init.py"), "--startdatum", daten.startdatum,
                               "--freigabe", daten.freigabe_durch], capture_output=True, text=True, env=umgebung,
                              timeout=120, cwd=e.daten_pfad)
    if ergebnis.returncode != 0:
        raise HTTPException(422, (ergebnis.stderr or ergebnis.stdout).strip().removeprefix("Fehler: ")[:500])
    commit = subprocess.run([sys.executable, str(werkzeug / "datenverzeichnis.py"), "commit", "-m",
                             f"aufbau: Spielstart {daten.startdatum} (Freigabe AP12: {daten.freigabe_durch})"],
                            capture_output=True, text=True, env=umgebung, timeout=60, cwd=e.daten_pfad)
    audit(db, admin.id, "spielstart", request, ziel=daten.startdatum, meta={"freigabe": daten.freigabe_durch})
    db.commit()
    return {"ok": True, "meldungen": ergebnis.stdout.strip().splitlines(), "commit": commit.stdout.strip()}
