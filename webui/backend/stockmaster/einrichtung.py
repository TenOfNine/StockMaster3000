"""Einrichtung: Einstellungen und Secrets in der App, Verbindungstests, Systemstatus, Spielstart.

Lesen und Schreiben nur für Administratoren; jede Änderung mit CSRF-Prüfung (über die
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
from .auftraege import AdminPflicht, admin_pflicht
from .auth import DB, Streng, audit, begrenzen
from .config import einstellungen
from .db import jetzt_utc

router = APIRouter(prefix="/api/einrichtung", tags=["einrichtung"], dependencies=[Depends(admin_pflicht)])

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
    # Spielstart und Anlagerichtlinien sind keine Pflichtschritte mehr: Der erste Trading-Lauf startet das Spiel
    # selbst (Startdatum heute, Standard-Anlagerichtlinien); die Einrichtung bietet den manuellen Start weiter an.
    return offen


def _ampel(kennung: str, titel: str, stufe: str, text: str, details: list[dict] | None = None,
           link: str | None = None) -> dict:
    """Eine Zeile des Systemstatus. details nennt die Ursache im Einzelnen (z. B. die fehlerhaften Feeds),
    link führt zum Bereich der Einrichtung, in dem sich das beheben lässt."""
    return {"id": kennung, "titel": titel, "stufe": stufe, "text": text, "details": details or [], "link": link}


NEWS_DETAILS_IM_STATUS = 5


def news_status() -> dict:
    """Ergebnis des letzten News-Abrufs je Feed (Fehlerhafte zuerst) aus .cache/news_stand.json."""
    stand = _cache("news_stand.json")
    feeds = []
    for kennung, s in (stand.get("feeds") or {}).items():
        feeds.append({"id": kennung, "name": s.get("anzeige") or s.get("name") or kennung, "url": s.get("url"),
                      "ok": bool(s.get("ok")), "fehler": s.get("fehler"), "art": s.get("art"),
                      "hinweis": s.get("hinweis"), "seit": s.get("seit"), "in_folge": int(s.get("in_folge") or 0),
                      "letzter_erfolg": s.get("letzter_erfolg"), "anzahl": int(s.get("anzahl") or 0),
                      "neu": int(s.get("neu") or 0)})
    feeds.sort(key=lambda f: (f["ok"], f["name"].casefold()))
    return {"zeit": stand.get("zeit"), "neu": int(stand.get("neu") or 0), "anzahl_feeds": len(feeds),
            "fehlerhaft": sum(1 for f in feeds if not f["ok"]), "feeds": feeds}


def _feed_detail(feed: dict) -> dict:
    return {"titel": feed["name"], "text": feed["fehler"] or "Fehler ohne Angabe.", "hinweis": feed["hinweis"],
            "seit": feed["seit"], "anzahl": feed["in_folge"], "url": feed["url"]}


NACHBUCHUNG_UHR = "00:30"  # lokale Zeit, wie worker.NACHBUCHUNG_AB


def _nachbuchung_ampel() -> dict:
    """Wie weit die Portfolios verbucht sind. Die Nachbuchung läuft nachts um 00:30 Uhr (Entscheidung 38)."""
    titel = "Nachbuchung"
    g = _werkzeuge()["gemeinsam"]
    try:
        if not g.spiel_lesen().get("startdatum"):
            return _ampel("nachbuchung", titel, "gruen", "Das Spiel ist noch nicht gestartet, es gibt nichts zu buchen.")
        stand = [g.portfolio_laden(p) for p in g.vorhandene_profile()]
    except Exception as exc:  # noqa: BLE001 - der Status darf nie an einer unlesbaren Datei scheitern
        return _ampel("nachbuchung", titel, "gelb", f"Stand der Portfolios nicht lesbar ({type(exc).__name__}).")
    aktiv = [p for p in stand if p["status"] == "aktiv"]
    if not aktiv:
        return _ampel("nachbuchung", titel, "gruen", "Keine aktiven Portfolios.")
    jetzt = datetime.now(TZ)
    bis = min(date.fromisoformat(p["verarbeitet_bis"]) for p in aktiv)
    rueckstand = ((jetzt.date() - timedelta(days=1)) - bis).days
    letzte = appdaten.zustand_lesen("planer").get("nachbuchung_ergebnis") or {}
    text = f"Verbucht bis {bis:%d.%m.%Y}"
    stufe = "gruen"
    if rueckstand <= 0:
        text += " (gestern)."
    elif jetzt.hour < 3:
        text += f"; die automatische Nachbuchung läuft um {NACHBUCHUNG_UHR} Uhr."
    else:
        stufe = "rot" if rueckstand >= 3 else "gelb"
        text += f": {rueckstand} {'Tag' if rueckstand == 1 else 'Tage'} im Rückstand."
        text += " Der Hintergrunddienst versucht es stündlich, spätestens bucht die nächste Session nach."
    details = []
    if letzte:
        text += f" Letzte automatische Nachbuchung {_alter_text(_zeit(letzte.get('zeit')))}: {letzte.get('meldung', '')}"
        if not letzte.get("ok"):
            stufe = "rot" if stufe == "rot" else "gelb"
        elif letzte.get("pruefung_ok") is False:
            stufe = "rot" if stufe == "rot" else "gelb"
            details.append({"titel": "Prüfung nach der Nachbuchung", "text": letzte.get("meldung", ""),
                            "hinweis": "pruefe.py meldet Fehler im Spielstand: Prüfung und Audit ansehen, bevor die "
                                       "nächste Session startet.", "seit": None, "anzahl": 0, "url": None})
    return _ampel("nachbuchung", titel, stufe, text, details, link="#zeitplan")


AUSFUEHRUNG_UEBERFAELLIG_MINUTEN = 15


def _ausfuehrung_ampel() -> dict:
    """Automatische Ausführung ohne Claude-Lauf (Entscheidung 43): letzter Lauf, Warteschlange, Fehler, Rückstand."""
    titel = "Ausführung"
    werkzeuge = _werkzeuge()
    try:
        if not werkzeuge["gemeinsam"].spiel_lesen().get("startdatum"):
            return _ampel("ausfuehrung", titel, "gruen", "Das Spiel ist noch nicht gestartet, es gibt nichts auszuführen.")
        offen_boerse = werkzeuge["ausfuehrung"].irgendeine_boerse_offen(datetime.now(TZ))
    except Exception as exc:  # noqa: BLE001 - der Status darf nie an einer unlesbaren Datei scheitern
        return _ampel("ausfuehrung", titel, "gelb", f"Stand nicht lesbar ({type(exc).__name__}).")
    stand = appdaten.zustand_lesen("planer").get("ausfuehrung") or {}
    versuch = _zeit(stand.get("versuch"))
    if not versuch:
        return _ampel("ausfuehrung", titel, "gruen" if not offen_boerse else "gelb",
                      "Noch kein Durchlauf; der Hintergrunddienst führt bei offenem Markt im 5-Minuten-Takt aus.")
    text = (f"Letzter Durchlauf {_alter_text(versuch)} ({stand.get('ausloeser', 'takt')}): "
            f"{stand.get('buchungen', 0)} Buchung(en); {stand.get('offen', 0)} Orders in der Warteschlange")
    if stand.get("rueckstand"):
        text += f", davon {stand['rueckstand']} Market-Order(s) bei offenem Markt noch nicht ausgeführt"
    text += "."
    letzte = stand.get("letzte_buchung")
    if letzte:
        text += f" Zuletzt gebucht {_alter_text(_zeit(letzte.get('zeit')))}: {letzte.get('text', '')[:120]}"
    stufe, details = "gruen", []
    for fehler in stand.get("fehler", []):
        details.append({"titel": "Fehler", "text": fehler, "hinweis": "Kein verlässlicher Kurs oder Fehler im Werkzeug; "
                        "der Hintergrunddienst versucht es im Minutentakt erneut.", "seit": None, "anzahl": 0, "url": None})
    for problem in stand.get("probleme", []):
        details.append({"titel": "Hinweis", "text": problem, "hinweis": "Die Nachbuchung führt vorgemerkte Orders sonst "
                        "zum Eröffnungskurs aus.", "seit": None, "anzahl": 0, "url": None})
    if stand.get("rueckstand_nachbuchung"):
        details.append({"titel": "Nachbuchung steht aus", "text": "Die Ausführung wartet auf die Nachbuchung der Vortage.",
                        "hinweis": "Zeile Nachbuchung ansehen.", "seit": None, "anzahl": 0, "url": None})
    if stand.get("fehler") or not stand.get("ok", True) or stand.get("rueckstand") or stand.get("rueckstand_nachbuchung"):
        stufe = "gelb"
    if offen_boerse and datetime.now(UTC) - versuch > timedelta(minutes=AUSFUEHRUNG_UEBERFAELLIG_MINUTEN):
        stufe = "rot"
        text += " Überfällig: bei offenem Markt wird alle 5 Minuten ausgeführt (Hintergrunddienst prüfen)."
    return _ampel("ausfuehrung", titel, stufe, text, details)


BEOBACHTUNG_UHR = "23:15"  # lokale Zeit, wie worker.BEOBACHTUNG_AB
BEOBACHTUNG_ALT_TAGE = 4  # Wochenende plus ein Feiertag
BEOBACHTUNG_DETAILS_IM_STATUS = 10


def _beobachtung_ampel() -> dict:
    """Stand der Beobachtungsliste (Screener). Der Abruf läuft einmal je Handelstag nach 23:15 Uhr (Entscheidung 38)."""
    titel = "Beobachtungsliste"
    stand = _cache("beobachtung.json")
    letzte = appdaten.zustand_lesen("planer").get("beobachtung_ergebnis") or {}
    zeit = _zeit(stand.get("zeit"))
    fehler = bool(letzte) and not letzte.get("ok")
    if not stand.get("eintraege") or not zeit:
        if fehler:
            return _ampel("beobachtung", titel, "rot",
                           f"Noch keine Daten; der letzte Abruf ist fehlgeschlagen: {letzte.get('meldung', '')} "
                           "Der Hintergrunddienst versucht es stündlich.")
        return _ampel("beobachtung", titel, "gelb", "Noch kein Abruf; der Hintergrunddienst holt die Tageskerzen "
                                                    "beim nächsten Durchlauf und danach nach jedem Handelsschluss.")
    anzahl, mit_daten = int(stand.get("anzahl", 0)), int(stand.get("mit_daten", 0))
    veraltet, ohne = stand.get("veraltet", []), stand.get("ohne_daten", [])
    alt = datetime.now(UTC) - zeit > timedelta(days=BEOBACHTUNG_ALT_TAGE)
    luecke = anzahl > 0 and mit_daten < 0.8 * anzahl
    stufe = "gelb" if alt or luecke or fehler or veraltet else "gruen"
    text = f"{_alter_text(zeit)}: {mit_daten} von {anzahl} Werten mit Tagesdaten ({stand.get('quelle', 'yfinance')})."
    if veraltet:
        text += f" {len(veraltet)} davon mit altem Stand (Abruf lückenhaft)."
    if alt:
        text += (f" Überfällig: erwartet wird ein Abruf je Handelstag nach {BEOBACHTUNG_UHR} Uhr "
                 "(Hintergrunddienst prüfen).")
    if fehler:
        text += f" Letzter Abruf {_alter_text(_zeit(letzte.get('zeit')))} fehlgeschlagen: {letzte.get('meldung', '')}"
    details = []
    if ohne:
        zeigen = ohne[:BEOBACHTUNG_DETAILS_IM_STATUS]
        details.append({"titel": f"{len(ohne)} Werte ohne Kursdaten",
                        "text": ", ".join(zeigen) + (" …" if len(ohne) > len(zeigen) else ""),
                        "hinweis": "Kürzel in config/beobachtung.json prüfen (Indexwechsel, Umbenennung, Delisting) "
                                   "oder aus der Liste nehmen: python tools/beobachtung.py pruefen.",
                        "seit": None, "anzahl": len(ohne), "url": None})
    return _ampel("beobachtung", titel, stufe, text, details)


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
        status.append(_ampel("kurse", "Letzter Kursabruf", "rot", "Noch kein Kursabruf.", link="#kursdaten"))
    else:
        alt = datetime.now(UTC) - markt_zeit > timedelta(minutes=2 * int(kurs["intervall_geschlossen_minuten"]) + 10)
        teilweise = markt.get("erfolgreich", 0) < markt.get("anzahl", 0)
        stufe = "rot" if not markt.get("erfolgreich") else ("gelb" if alt or teilweise else "gruen")
        text = (f"{_alter_text(markt_zeit)}: {markt.get('erfolgreich', 0)} von {markt.get('anzahl', 0)} Kursen aktuell"
                f" (zuerst gefragt: {markt.get('quelle_konfiguriert', '–')}).")
        if teilweise:
            text += " Fehlende Werte zeigen den letzten bekannten Kurs mit Kennzeichnung „veraltet“."
        if alt:
            text += (f" Überfällig: außerhalb der Handelszeiten wird alle {kurs['intervall_geschlossen_minuten']} Minuten "
                     "abgerufen (Hintergrunddienst prüfen).")
        status.append(_ampel("kurse", "Letzter Kursabruf", stufe, text, link="#kursdaten"))

    news = _cache("news_stand.json")
    news_zeit = _zeit(news.get("zeit"))
    news_einstellung = appdaten.laden()["news"]
    intervall = int(news_einstellung["intervall_minuten"])
    if not news_einstellung["aktiv"]:
        status.append(_ampel("news", "Letzter News-Abruf", "gelb", "News-Abruf ist ausgeschaltet.", link="#news"))
    elif not news_zeit:
        status.append(_ampel("news", "Letzter News-Abruf", "rot", "Noch kein News-Abruf.", link="#news"))
    else:
        alt = datetime.now(UTC) - news_zeit > timedelta(minutes=3 * intervall + 5)
        abruf = news_status()
        kaputt = [f for f in abruf["feeds"] if not f["ok"]]
        stufe = "rot" if kaputt and len(kaputt) == abruf["anzahl_feeds"] else ("gelb" if alt or kaputt else "gruen")
        text = f"{_alter_text(news_zeit)}: {abruf['neu']} neue Meldungen"
        if kaputt:
            text += f", {len(kaputt)} von {abruf['anzahl_feeds']} Feeds mit Fehler."
        else:
            text += f" aus {abruf['anzahl_feeds']} Feeds."
        if alt:
            text += f" Überfällig: erwartet wird ein Abruf alle {intervall} Minuten (Hintergrunddienst prüfen)."
        details = [_feed_detail(f) for f in kaputt[:NEWS_DETAILS_IM_STATUS]]
        if len(kaputt) > NEWS_DETAILS_IM_STATUS:
            details.append({"titel": f"… und {len(kaputt) - NEWS_DETAILS_IM_STATUS} weitere", "text":
                            "Alle Feeds mit Fehler stehen unter Einrichtung → News.", "hinweis": None, "seit": None,
                            "anzahl": 0, "url": None})
        status.append(_ampel("news", "Letzter News-Abruf", stufe, text, details, link="#news"))

    status.append(_beobachtung_ampel())
    status.append(_nachbuchung_ampel())
    status.append(_ausfuehrung_ampel())

    info =appdaten.geheimnis_info("claude_token")
    test = appdaten.laden()["claude"].get("letzter_test") or {}
    if not info["gesetzt"]:
        status.append(_ampel("claude", "Claude-Verbindung", "rot", "Kein Claude-Token hinterlegt.", link="#claude"))
    elif not test:
        status.append(_ampel("claude", "Claude-Verbindung", "gelb", "Token hinterlegt, Verbindung noch nicht getestet.",
                             link="#claude"))
    else:
        status.append(_ampel("claude", "Claude-Verbindung", "gruen" if test.get("ok") else "rot",
                             f"Test {_alter_text(_zeit(test.get('zeit')))}: {test.get('meldung', '')}", link="#claude"))

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
    punkte.append({"id": "richtlinien", "pflicht": False, "ok": True,
                   "text": "Anlagerichtlinien aller Profile ausformuliert (AP12 Punkt 2)." if not offen_richtlinien
                   else "Die Standard-Anlagerichtlinien (config/richtlinien) gelten automatisch ab Spielstart; "
                        "wer sie vorher individuell anpassen will, startet den Lauf „Anlagerichtlinien“."})
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
    heute = datetime.now(TZ).date()
    return {"punkte": punkte, "bereit": all(p["ok"] for p in punkte if p["pflicht"]),
            "gestartet": bool(spiel.get("startdatum")), "spiel": spiel,
            "vorschlag_startdatum": heute.isoformat(),
            "vorziehen": _vorziehen_stand(heute, spiel),
            "auftraggeber": g.projekt()["auftraggeber"]}


def _vorziehen_stand(heute: date, spiel: dict) -> dict:
    """Ob und worauf das noch unberührte Startdatum vorgezogen werden kann (tools/init.py prüft verbindlich)."""
    if not spiel.get("startdatum"):
        return {"moeglich": False, "grund": "Das Spiel ist noch nicht gestartet.", "ziel": None}
    ziel = heute
    if ziel.isoformat() >= spiel["startdatum"]:
        return {"moeglich": False, "grund": "Das Startdatum liegt nicht in der Zukunft.", "ziel": None}
    import init as init_werkzeug  # noqa: PLC0415

    try:
        init_werkzeug.vorziehen_pruefen(ziel)
    except Exception as exc:  # noqa: BLE001
        return {"moeglich": False, "grund": str(exc), "ziel": ziel.isoformat()}
    return {"moeglich": True, "grund": None, "ziel": ziel.isoformat()}



# --------------------------------------------------------------------------
# Lesen


@router.get("")
def ueberblick(db: DB) -> dict:
    app = appdaten.laden()
    quellen = kursquellen()
    news = news_konfig_wirksam()
    return {
        "einstellungen": {k: v for k, v in app.items() if k not in ("migration", "vorgaben")},
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
        "news_status": news_status(),
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
def claude_speichern(daten: ClaudeDaten, request: Request, db: DB, admin: AdminPflicht) -> dict:
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
                     request: Request, db: DB, admin: AdminPflicht) -> dict:
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
                       db: DB, admin: AdminPflicht) -> dict:
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
def claude_anmeldung_starten(request: Request, db: DB, admin: AdminPflicht) -> dict:
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
def claude_anmeldung_code(auftrag_id: str, daten: AnmeldeCode, request: Request, db: DB, admin: AdminPflicht) -> dict:
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
def claude_anmeldung_abbrechen(auftrag_id: str, request: Request, db: DB, admin: AdminPflicht) -> dict:
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
def claude_test(request: Request, db: DB, admin: AdminPflicht) -> dict:
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
def kursdaten_speichern(daten: KursDaten, request: Request, db: DB, admin: AdminPflicht) -> dict:
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
def kursdaten_test(daten: KursTest, request: Request, db: DB, admin: AdminPflicht) -> dict:
    if daten.anbieter != "yfinance" and not appdaten.geheimnis_info(f"kurs_key_{daten.anbieter}")["gesetzt"]:
        raise HTTPException(409, "Zuerst den API-Key eintragen.")
    return _test_ausfuehren(db, admin, request, "test_kurse", {"anbieter": daten.anbieter}, "einrichtung_kurse_test")


@router.post("/kursdaten/abrufen")
def kursdaten_abrufen(request: Request, db: DB, admin: AdminPflicht) -> dict:
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
def news_speichern(daten: NewsDaten, request: Request, db: DB, admin: AdminPflicht) -> dict:
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
def news_test(daten: FeedTest, request: Request, db: DB, admin: AdminPflicht) -> dict:
    return _test_ausfuehren(db, admin, request, "test_feed", {"url": daten.url}, "einrichtung_feed_test")


@router.post("/news/abrufen")
def news_abrufen(request: Request, db: DB, admin: AdminPflicht) -> dict:
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
def zeitplan_speichern(daten: ZeitplanDaten, request: Request, db: DB, admin: AdminPflicht) -> dict:
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


class AutomatikDaten(Streng):
    an: bool


@router.post("/zeitplan/automatik")
def automatik_schalten(daten: AutomatikDaten, request: Request, db: DB, admin: AdminPflicht) -> dict:
    """Automatik ein- oder ausschalten, ohne den Zeitplan neu zu speichern (Start/Stopp per Klick)."""
    plan = appdaten.laden()["zeitplan"]
    if daten.an:
        if not plan["termine"]:
            raise HTTPException(422, "Für die Automatik mindestens einen Termin angeben (Einrichtung → Zeitplan).")
        if not appdaten.geheimnis_info("claude_token")["gesetzt"]:
            raise HTTPException(422, "Die Automatik braucht ein Claude-Token (Einrichtung → Claude).")
    appdaten.bereich_speichern("zeitplan", {**plan, "automatik": daten.an})
    audit(db, admin.id, "einrichtung_automatik", request, meta={"automatik": daten.an})
    db.commit()
    return {"ok": True, "automatik": daten.an}


# --------------------------------------------------------------------------
# Vorgaben der Auftraggeber je Portfolio (Entscheidung 39)

VORGABEN_HISTORIE_ANZEIGE = 100
STEUERZEICHEN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u202a-\u202e\u2066-\u2069]")


class VorgabeDaten(Streng):
    text: str = Field(max_length=appdaten.VORGABEN_MAX_ZEICHEN * 2)

    @field_validator("text")
    @classmethod
    def _text(cls, wert: str) -> str:
        wert = wert.replace("\r\n", "\n").replace("\r", "\n").strip()
        if STEUERZEICHEN.search(wert):
            raise ValueError("Der Text enthält Steuerzeichen.")
        if len(wert) > appdaten.VORGABEN_MAX_ZEICHEN:
            raise ValueError(f"Höchstens {appdaten.VORGABEN_MAX_ZEICHEN} Zeichen.")
        return wert


def vorgaben_ueberblick() -> dict:
    vorgaben = appdaten.laden()["vorgaben"]
    return {"profile": vorgaben["profile"], "max_zeichen": appdaten.VORGABEN_MAX_ZEICHEN,
            "historie": list(reversed(vorgaben["historie"]))[:VORGABEN_HISTORIE_ANZEIGE]}


@router.get("/vorgaben")
def vorgaben_lesen() -> dict:
    return vorgaben_ueberblick()


@router.put("/vorgaben/{profil}")
def vorgabe_speichern(profil: Literal["defensiv", "ausgewogen", "aggressiv"], daten: VorgabeDaten, request: Request,
                      db: DB, admin: AdminPflicht) -> dict:
    """Neue Version der Vorgabe; gilt ab dem nächsten Lauf. Unveränderter Text legt keine Version an."""
    begrenzen(f"vorgaben:{admin.id}", 30, 60)
    eintrag = appdaten.vorgaben_aendern(profil, daten.text, admin.kennung)
    if eintrag:
        audit(db, admin.id, "einrichtung_vorgabe", request, ziel=profil,
              meta={"version": eintrag["version"], "zeichen": len(daten.text)})
        db.commit()
    return {"ok": True, "geaendert": eintrag is not None, **vorgaben_ueberblick()}


# --------------------------------------------------------------------------
# Spielstart (tools/init.py)


class SpielstartDaten(Streng):
    # Ohne Angabe beginnt das Spiel heute: kein vorab festgelegter Starttermin (regeln.md Abschnitt 2).
    startdatum: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    freigabe_durch: str = Field(max_length=40)
    freigabe_ap12_bestaetigt: bool
    passwort: str = Field(min_length=1, max_length=200)


@router.post("/spielstart")
def spielstart(daten: SpielstartDaten, request: Request, db: DB, admin: AdminPflicht) -> dict:
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
    datum = ["--startdatum", daten.startdatum] if daten.startdatum else []
    ergebnis = subprocess.run([sys.executable, str(werkzeug / "init.py"), *datum, "--freigabe", daten.freigabe_durch],
                              capture_output=True, text=True, env=umgebung, timeout=120, cwd=e.daten_pfad)
    if ergebnis.returncode != 0:
        raise HTTPException(422, (ergebnis.stderr or ergebnis.stdout).strip().removeprefix("Fehler: ")[:500])
    commit = subprocess.run([sys.executable, str(werkzeug / "datenverzeichnis.py"), "commit", "-m",
                             f"aufbau: Spielstart (Freigabe AP12: {daten.freigabe_durch})"],
                            capture_output=True, text=True, env=umgebung, timeout=60, cwd=e.daten_pfad)
    audit(db, admin.id, "spielstart", request, ziel=daten.startdatum or "heute", meta={"freigabe": daten.freigabe_durch})
    db.commit()
    return {"ok": True, "meldungen": ergebnis.stdout.strip().splitlines(), "commit": commit.stdout.strip()}


class VorziehenDaten(Streng):
    startdatum: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    passwort: str = Field(min_length=1, max_length=200)


@router.post("/spielstart/vorziehen")
def spielstart_vorziehen(daten: VorziehenDaten, request: Request, db: DB, admin: AdminPflicht) -> dict:
    """Noch unberührtes Startdatum auf heute/den nächsten Handelstag vorziehen (tools/init.py --vorziehen)."""
    from .admin import bestaetigen

    bestaetigen(admin, daten.passwort)
    if auftraege.session_sperre_aktiv() is not None or auftraege.offener_lauf(db) is not None:
        raise HTTPException(409, "Es läuft gerade eine Session oder ein Lauf.")
    e = einstellungen()
    umgebung = {**os.environ, "STOCKMASTER_DATA_DIR": str(e.daten_pfad),
                "STOCKMASTER_FRAMEWORK_DIR": str(e.framework_pfad), "PYTHONDONTWRITEBYTECODE": "1"}
    werkzeug = e.framework_pfad / "tools"
    datum = ["--startdatum", daten.startdatum] if daten.startdatum else []
    ergebnis = subprocess.run([sys.executable, str(werkzeug / "init.py"), *datum, "--vorziehen"],
                              capture_output=True, text=True, env=umgebung, timeout=120, cwd=e.daten_pfad)
    if ergebnis.returncode != 0:
        raise HTTPException(422, (ergebnis.stderr or ergebnis.stdout).strip().removeprefix("Fehler: ")[:500])
    commit = subprocess.run([sys.executable, str(werkzeug / "datenverzeichnis.py"), "commit", "-m",
                             "aufbau: Startdatum vorgezogen"],
                            capture_output=True, text=True, env=umgebung, timeout=60, cwd=e.daten_pfad)
    audit(db, admin.id, "spielstart_vorgezogen", request, ziel=daten.startdatum or "heute")
    db.commit()
    return {"ok": True, "meldungen": ergebnis.stdout.strip().splitlines(), "commit": commit.stdout.strip()}
