"""Hintergrunddienst (Dienst 'worker'): Kurse, News, Zeitplan, Claude-Läufe, Verbindungstests.

Er ist der einzige Dienst mit Internetzugang. Er ruft die Werkzeuge in tools/ als eigene Prozesse
auf (Rechnen macht Code), bucht nichts und committet Abrufe höchstens stündlich lokal im
Spielstand-Git, nie während einer Session. Die API legt Aufträge in der Datenbank an.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import tempfile
import threading
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select

from . import appdaten, auftraege, claude_anmeldung, claude_lauf, claude_optionen, freigaben
from .config import einstellungen
from .db import jetzt_utc, neue_sitzung, utc
from .modelle import AuditEintrag, Auftrag

log = logging.getLogger("stockmaster.worker")
TZ = ZoneInfo("Europe/Berlin")
TESTARTEN = ("test_claude", "test_kurse", "test_feed", "kurse_jetzt", "news_jetzt")
# Nachbuchung (Entscheidung 38): bewertung.py verarbeitet Tage bis gestern; deshalb nachts, wenn der Handelstag
# (auch NYSE, Gold und Brent bis 22:00) zu Ende ist und die Tageskerzen vorliegen. Bei Fehlern stündlich erneut.
NACHBUCHUNG_AB = (0, 30)
NACHBUCHUNG_WIEDERHOLUNG_MINUTEN = 60
# Beobachtungsliste (Entscheidung 38): Tageskerzen von rund 600 Werten, einmal je Handelstag nach dem Schluss von
# Xetra und NYSE (22:00 Berlin), vor der Nachbuchung; bei Fehlern stündlich erneut.
BEOBACHTUNG_AB = (23, 15)
BEOBACHTUNG_WIEDERHOLUNG_MINUTEN = 60
# Zeitplan (Umbau v2): verpasste Termine werden so lange nachgeholt, wartende so lange wiederholt.
OVERNIGHT_AB = (23, 30)
OVERNIGHT_TAGE = 7
NACHHOLEN_MINUTEN = 120
WARTEN_STUNDEN = 24


def _werkzeuge():
    from .spiel import lesen

    return lesen.werkzeuge()


def werkzeug(name: str, *argumente: str, zusatz: dict | None = None, timeout: int = 600) -> subprocess.CompletedProcess:
    """Werkzeug aus tools/ als eigener Prozess mit Datenverzeichnis und (falls konfiguriert) Kursanbieter."""
    e = einstellungen()
    import os

    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": tempfile.gettempdir(), "LANG": "C.UTF-8",
           "STOCKMASTER_DATA_DIR": str(e.daten_pfad), "STOCKMASTER_FRAMEWORK_DIR": str(e.framework_pfad),
           "PYTHONDONTWRITEBYTECODE": "1", **claude_lauf.kurs_umgebung(), **(zusatz or {})}
    for name_ in claude_lauf.DURCHREICHEN:
        if os.environ.get(name_):
            env[name_] = os.environ[name_]
    return subprocess.run([sys.executable, str(e.framework_pfad / "tools" / f"{name}.py"), *argumente],
                          capture_output=True, text=True, env=env, cwd=e.daten_pfad, timeout=timeout)


def _letzte_zeile(lauf: subprocess.CompletedProcess) -> str:
    text = (lauf.stdout.strip() or lauf.stderr.strip()).splitlines()
    return text[-1][:300] if text else ""


class Worker:
    def __init__(self):
        self.lauf_thread: threading.Thread | None = None
        self.anmeldung_thread: threading.Thread | None = None
        self.zustand = appdaten.zustand_lesen("planer")

    # ------------------------------------------------------------------ Zustand

    def _merken(self, **werte) -> None:
        self.zustand.update(werte)
        appdaten.zustand_schreiben("planer", self.zustand)

    def herzschlag(self, meldung: str = "") -> None:
        appdaten.zustand_schreiben("worker", {"zeit": datetime.now(UTC).isoformat(timespec="seconds"),
                                              "meldung": meldung, "lauf_aktiv": self.lauf_aktiv()})

    def lauf_aktiv(self) -> bool:
        return bool(self.lauf_thread and self.lauf_thread.is_alive())

    @staticmethod
    def _faellig(letzte: str | None, minuten: float, jetzt: datetime) -> bool:
        if not letzte:
            return True
        return jetzt - datetime.fromisoformat(letzte) >= timedelta(minutes=minuten)

    # ------------------------------------------------------------------ Abrufe

    def markt_offen(self, jetzt: datetime) -> bool:
        kurse = _werkzeuge()["kurse"]
        return any(kurse.markt_offen(t, jetzt.astimezone(TZ)) for t in ("^GDAXI", "^GSPC"))

    def kurse_abrufen(self, historie: bool) -> str:
        argumente = ["markt", "--historie"] if historie else ["markt"]
        lauf = werkzeug("kurse", *argumente, timeout=900)
        return _letzte_zeile(lauf) if lauf.returncode else lauf.stdout.splitlines()[0] if lauf.stdout else "ok"

    def news_abrufen(self) -> str:
        from .einrichtung import news_konfig_wirksam

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as datei:
            json.dump(news_konfig_wirksam(), datei)
        try:
            lauf = werkzeug("news", "abrufen", "--konfig", datei.name, timeout=900)
        finally:
            Path(datei.name).unlink(missing_ok=True)
        return _letzte_zeile(lauf) if lauf.returncode else lauf.stdout.splitlines()[0] if lauf.stdout else "ok"

    def planen(self, jetzt: datetime) -> list[str]:
        """Fällige Abrufe ausführen (Kurse: 5 Min. bei offenem Markt, sonst stündlich; einmal nach Schluss)."""
        meldungen = []
        app = appdaten.laden()
        kurs = app["kursdaten"]
        offen = self.markt_offen(jetzt)
        schluss_danach = self.zustand.get("kurse_offen") and not offen
        intervall = kurs["intervall_offen_minuten"] if offen else kurs["intervall_geschlossen_minuten"]
        # Tagesdaten: beim ersten Abruf (Diagramme füllen) und einmal täglich nach US-Börsenschluss.
        lokal = jetzt.astimezone(TZ)
        abends = lokal.replace(hour=22, minute=0, second=0, microsecond=0)
        letzte_historie = self.zustand.get("historie_zeit")
        historie = not letzte_historie or (lokal >= abends and datetime.fromisoformat(letzte_historie) < abends)
        if schluss_danach or historie or self._faellig(self.zustand.get("kurse_zeit"), intervall, jetzt):
            meldungen.append("Kurse: " + self.kurse_abrufen(historie))
            self._merken(kurse_zeit=jetzt.isoformat(), kurse_offen=offen,
                         **({"historie_zeit": jetzt.isoformat()} if historie else {}))
        news = app["news"]
        if news["aktiv"] and self._faellig(self.zustand.get("news_zeit"), news["intervall_minuten"], jetzt):
            ergebnis = self.news_abrufen()
            meldungen.append(ergebnis if ergebnis.startswith("News:") else "News: " + ergebnis)
            self._merken(news_zeit=jetzt.isoformat())
        return meldungen

    @staticmethod
    def beobachtung_soll_tag(jetzt: datetime) -> date:
        """Letzter Handelstag (Mo–Fr), dessen Tageskerzen nach `BEOBACHTUNG_AB` vorliegen sollten."""
        lokal = jetzt.astimezone(TZ)
        tag = lokal.date() if (lokal.hour, lokal.minute) >= BEOBACHTUNG_AB else lokal.date() - timedelta(days=1)
        while tag.weekday() >= 5:
            tag -= timedelta(days=1)
        return tag

    def beobachtung_aktualisieren(self, jetzt: datetime) -> str | None:
        """Beobachtungsliste nach Handelsschluss auffrischen (tools/beobachtung.py, Quelle yfinance).

        Läuft einmal je Handelstag ab 23:15 Uhr, nach einem Ausfall oder bei fehlendem Stand sofort. Der Stand liegt im
        Zwischenspeicher (.cache), nicht im Spielstand; ein Fehlschlag lässt den alten Stand stehen.
        """
        soll = self.beobachtung_soll_tag(jetzt)
        stand_da = (einstellungen().daten_pfad / ".cache" / "beobachtung.json").exists()
        if stand_da and (self.zustand.get("beobachtung_tag") or "") >= soll.isoformat():
            return None
        if not self._faellig(self.zustand.get("beobachtung_versuch"), BEOBACHTUNG_WIEDERHOLUNG_MINUTEN, jetzt):
            return None
        self._merken(beobachtung_versuch=jetzt.isoformat())
        try:
            lauf = werkzeug("beobachtung", "aktualisieren", timeout=1800)
            ok = lauf.returncode == 0
            meldung = (lauf.stdout.splitlines() or ["ok"])[0] if ok else (_letzte_zeile(lauf) or "fehlgeschlagen")
        except subprocess.TimeoutExpired:
            ok, meldung = False, "Zeitüberschreitung beim Abruf."
        self._merken(beobachtung_ergebnis={"zeit": jetzt.isoformat(timespec="seconds"), "ok": ok, "meldung": meldung[:300]},
                     **({"beobachtung_tag": soll.isoformat()} if ok else {}))
        return meldung if meldung.startswith("Beobachtungsliste") else f"Beobachtungsliste: {meldung}"

    def richtlinien_standard(self, jetzt: datetime) -> str | None:
        """Nach dem Spielstart gelten die Standard-Anlagerichtlinien, solange keine eigene vorliegt.

        Fehlt eine Richtlinie oder ist sie noch die Vorlage, wird die Standard-Richtlinie übernommen; eine unveränderte
        ältere Standardfassung wird aktualisiert (Umbau v2: Handeln ist der Normalfall), die bisherige Historie bleibt.
        Eine angepasste Richtlinie bleibt unberührt.
        """
        if self.lauf_aktiv() or auftraege.session_sperre_aktiv() is not None:
            return None
        g = _werkzeuge()["gemeinsam"]
        if not g.spiel_lesen().get("startdatum") or not (g.richtlinien_offen() or g.richtlinien_veraltet()):
            return None
        lauf = werkzeug("richtlinien", "standard", timeout=60)
        if lauf.returncode != 0:
            return "Standard-Anlagerichtlinien: " + _letzte_zeile(lauf)
        werkzeug("datenverzeichnis", "commit", "-m", "aufbau: Standard-Anlagerichtlinien übernommen bzw. aktualisiert",
                 timeout=60)
        return "Standard-Anlagerichtlinien übernommen bzw. aktualisiert."

    def _nachbuchung_rueckstand(self, gestern: date) -> list[str]:
        """Aktive Portfolios, die noch nicht bis gestern verarbeitet sind (Kennungen)."""
        g = _werkzeuge()["gemeinsam"]
        offen = []
        for profil in g.vorhandene_profile():
            portfolio = g.portfolio_laden(profil)
            if portfolio["status"] == "aktiv" and date.fromisoformat(portfolio["verarbeitet_bis"]) < gestern:
                offen.append(profil)
        return offen

    def nachbuchen(self, jetzt: datetime) -> str | None:
        """Nach Handelsschluss alle Tage bis gestern nachbuchen, ohne auf die nächste Session zu warten.

        Der Ablauf ist derselbe wie beim Session-Start (regeln.md 6: vorgemerkte Market-Orders zur Eröffnung,
        Limits, Barrieren, Stops, Tagesabschluss); der Code rechnet, Claude ist nicht beteiligt. bewertung.py
        verlangt dafür eine Sperre: Der Dienst setzt sie als Art "nachbuchung" und gibt sie danach frei.
        """
        lokal = jetzt.astimezone(TZ)
        if (lokal.hour, lokal.minute) < NACHBUCHUNG_AB or self.zustand.get("nachbuchung_tag") == lokal.date().isoformat():
            return None
        if not self._faellig(self.zustand.get("nachbuchung_versuch"), NACHBUCHUNG_WIEDERHOLUNG_MINUTEN, jetzt):
            return None
        if self.lauf_aktiv() or auftraege.session_sperre_aktiv() is not None:
            return None  # eine Session bucht beim Start selbst nach; später erneut versuchen
        g = _werkzeuge()["gemeinsam"]
        if not g.spiel_lesen().get("startdatum"):
            return None
        gestern = lokal.date() - timedelta(days=1)
        if not self._nachbuchung_rueckstand(gestern):
            self._merken(nachbuchung_tag=lokal.date().isoformat())
            return None
        auftraggeber = g.projekt()["auftraggeber"]
        person = appdaten.laden()["zeitplan"].get("auftraggeber")
        person = person if person in auftraggeber else auftraggeber[0]
        self._merken(nachbuchung_versuch=jetzt.isoformat())

        def ergebnis(ok: bool, meldung: str, pruefung_ok: bool | None = None) -> str:
            self._merken(nachbuchung_ergebnis={"zeit": jetzt.isoformat(timespec="seconds"), "ok": ok,
                                               "meldung": meldung[:300], "pruefung_ok": pruefung_ok,
                                               "bis": gestern.isoformat()})
            if ok:
                self._merken(nachbuchung_tag=lokal.date().isoformat())
            return f"Nachbuchung: {meldung}"

        start = werkzeug("session", "start", "--person", person, "--art", "nachbuchung", timeout=120)
        if start.returncode != 0:
            return ergebnis(False, "Sperre nicht möglich: " + _letzte_zeile(start))
        try:
            buchung = werkzeug("bewertung", "nachbuchen", timeout=900)
            if buchung.returncode != 0:
                return ergebnis(False, _letzte_zeile(buchung) or "Nachbuchung fehlgeschlagen.")
            bericht = werkzeug("bewertung", "bericht", timeout=600)
            pruefung = werkzeug("pruefe", timeout=300)
            werkzeug("datenverzeichnis", "commit", "-m", f"session: Nachbuchung bis {gestern} (automatisch)", timeout=120)
        finally:
            werkzeug("session", "ende", timeout=120)
        meldung = f"bis {gestern:%d.%m.%Y} gebucht"
        if bericht.returncode != 0:
            meldung += f"; Bericht: {_letzte_zeile(bericht)}"
        meldung += "; Prüfung bestanden" if pruefung.returncode == 0 else f"; Prüfung mit Fehlern: {_letzte_zeile(pruefung)}"
        return ergebnis(True, meldung, pruefung.returncode == 0)

    def profile_ergaenzen(self, jetzt: datetime) -> str | None:
        """Migration (regeln.md 7, Entscheidung 44): fehlende Profile im laufenden Spiel ergänzen.

        Ein neues Profil (Overnight) startet mit 1.000 EUR am heutigen Tag, nie rückwirkend; die vorhandenen
        Portfolios, Trades, Journal und Historie bleiben unberührt. Vorher entsteht eine Sicherung im App-Verzeichnis
        und ein lokaler Commit des Ist-Zustands; danach committet der Dienst die Ergänzung. Idempotent und ohne
        manuellen Eingriff: Läuft gerade eine Session, versucht es der Dienst später erneut.
        """
        g = _werkzeuge()["gemeinsam"]
        if not g.spiel_lesen().get("startdatum"):
            return None
        fehlend = [p for p in g.profile() if not g.portfolio_pfad(p).exists()]
        if not fehlend or self.lauf_aktiv() or auftraege.session_sperre_aktiv() is not None:
            return None
        if not self._faellig(self.zustand.get("profile_versuch"), 30, jetzt):
            return None
        self._merken(profile_versuch=jetzt.isoformat())
        from . import sicherung

        ziel = einstellungen().app_pfad / "sicherungen" / f"vor-migration-{jetzt:%Y%m%d-%H%M}.tar.gz"
        try:
            sicherung.exportieren(ziel)
        except Exception as exc:  # noqa: BLE001 - ohne Sicherung wird nicht migriert
            self._merken(profile_ergebnis={"zeit": jetzt.isoformat(timespec="seconds"), "ok": False,
                                           "meldung": f"Sicherung fehlgeschlagen: {exc}"[:300]})
            return f"Migration abgebrochen: Sicherung fehlgeschlagen ({exc})"
        for alt in sorted(ziel.parent.glob("vor-migration-*.tar.gz"))[:-3]:
            alt.unlink(missing_ok=True)  # die letzten drei bleiben
        werkzeug("datenverzeichnis", "commit", "-m", "daten: Stand vor der Migration neuer Profile", timeout=120)
        lauf = werkzeug("init", "--profile-ergaenzen", "--ausloeser", "migration", timeout=120)
        ok = lauf.returncode == 0
        meldung = (_letzte_zeile(lauf) if not ok else f"Profil {', '.join(fehlend)} ergänzt (Start heute, 1.000 EUR)")
        if ok:
            werkzeug("datenverzeichnis", "commit", "-m",
                     f"aufbau: Profil {', '.join(fehlend)} ergänzt (Migration, Start heute, automatisch)", timeout=120)
        self._merken(profile_ergebnis={"zeit": jetzt.isoformat(timespec="seconds"), "ok": ok, "meldung": meldung[:300],
                                       "sicherung": ziel.name})
        return f"Migration: {meldung}"

    def overnight_analysieren(self, jetzt: datetime) -> str | None:
        """Wöchentlicher Rückblick auf Schluss → Eröffnung (tools/overnight.py analyse, Kosten des Spiels, Train/Test)."""
        g = _werkzeuge()["gemeinsam"]
        if "overnight" not in g.vorhandene_profile():
            return None
        lokal = jetzt.astimezone(TZ)
        if (lokal.hour, lokal.minute) < OVERNIGHT_AB:
            return None
        letzte = self.zustand.get("overnight_zeit")
        if letzte and jetzt - datetime.fromisoformat(letzte) < timedelta(days=OVERNIGHT_TAGE):
            return None
        if not self._faellig(self.zustand.get("overnight_versuch"), 60, jetzt):
            return None
        self._merken(overnight_versuch=jetzt.isoformat())
        lauf = werkzeug("overnight", "analyse", timeout=1800)
        ok = lauf.returncode == 0
        self._merken(overnight_ergebnis={"zeit": jetzt.isoformat(timespec="seconds"), "ok": ok,
                                         "meldung": (_letzte_zeile(lauf) or "")[:300]},
                     **({"overnight_zeit": jetzt.isoformat()} if ok else {}))
        return f"Overnight-Analyse: {_letzte_zeile(lauf)}"

    def ausfuehren(self, jetzt: datetime) -> str | None:
        """Automatische Ausführung ohne Claude-Lauf (regeln.md 6, Entscheidung 43).

        Im Takt bei offenem Markt sowie zu Öffnung und Schluss jeder Börse: vorgemerkte Orders, Limits, Stops,
        Kursziele und Knock-outs zu protokollierten Kursen. Der Code rechnet und bucht (tools/ausfuehrung.py, unter
        der Buchungssperre, unabhängig von der Session-Sperre); ein Fehler oder fehlender Kurs wird nach kurzer Pause
        erneut versucht. Weder Claude noch ein Token sind beteiligt.
        """
        werkzeuge = _werkzeuge()
        if not werkzeuge["gemeinsam"].spiel_lesen().get("startdatum"):
            return None
        stand = self.zustand.get("ausfuehrung") or {}
        zuletzt = datetime.fromisoformat(stand["versuch"]) if stand.get("versuch") else None
        ausloeser = werkzeuge["ausfuehrung"].faellig(zuletzt, jetzt.astimezone(TZ), wiederholen=bool(stand.get("wiederholen")))
        if not ausloeser:
            return None
        lauf = werkzeug("ausfuehrung", "tick", "--ausloeser", ausloeser, "--json", timeout=300)
        ergebnis: dict = {"versuch": jetzt.isoformat(timespec="seconds"), "ausloeser": ausloeser,
                          "letzte_buchung": stand.get("letzte_buchung")}
        try:
            bericht = json.loads((lauf.stdout.strip().splitlines() or [""])[-1])
        except ValueError:
            bericht = None
        if bericht is None or lauf.returncode != 0:
            ergebnis.update(ok=False, wiederholen=True, meldung=_letzte_zeile(lauf) or "Ausführung ohne Ergebnis.",
                            fehler=[], offen=stand.get("offen", 0), rueckstand=stand.get("rueckstand", 0))
            self._merken(ausfuehrung=ergebnis)
            return f"Ausführung: {ergebnis['meldung']}"
        fehler = [f"{f.get('ticker') or f.get('profil')}: {f['text']}" for f in bericht["fehler"]][:5]
        probleme = [f"{p['profil']}: {p['text']}" for p in bericht.get("probleme", [])][:5]
        ergebnis.update(ok=not fehler, wiederholen=bool(bericht["wiederholen"]), fehler=fehler, probleme=probleme,
                        offen=bericht["offen"], rueckstand=bericht["rueckstand"],
                        rueckstand_nachbuchung=bool(bericht.get("rueckstand_nachbuchung")),
                        buchungen=len(bericht["ausgefuehrt"]), hinweis=bericht.get("hinweis", ""),
                        meldung=bericht["meldungen"][-1] if bericht["meldungen"] else "")
        meldung = None
        if bericht["ausgefuehrt"]:
            ergebnis["letzte_buchung"] = {"zeit": bericht["zeit"], "anzahl": len(bericht["ausgefuehrt"]),
                                          "text": "; ".join(bericht["meldungen"])[:300]}
            anzahl = len(bericht["ausgefuehrt"])
            meldung = f"Ausführung ({ausloeser}): {anzahl} Buchung(en): " + ergebnis["letzte_buchung"]["text"]
            if not auftraege.session_sperre_aktiv() and not self.lauf_aktiv():
                werkzeug("datenverzeichnis", "commit", "-m",
                         f"session: automatische Ausführung ({len(bericht['ausgefuehrt'])} Buchungen, automatisch)",
                         timeout=120)
        elif fehler:
            meldung = f"Ausführung: {fehler[0]}"
        self._merken(ausfuehrung=ergebnis)
        return meldung

    def committen(self, jetzt: datetime) -> str | None:
        """Abrufe höchstens stündlich lokal committen; nie während einer Session oder eines Laufs."""
        if not self._faellig(self.zustand.get("commit_zeit"), 60, jetzt) or self.lauf_aktiv():
            return None
        if auftraege.session_sperre_aktiv():
            return None
        lauf = werkzeug("datenverzeichnis", "commit", "-m", "daten: Kurs- und News-Abruf", timeout=120)
        self._merken(commit_zeit=jetzt.isoformat())
        return _letzte_zeile(lauf)

    # ------------------------------------------------------------------ Zeitplan

    def zeitplan(self, jetzt: datetime) -> str | None:
        """Geplante Läufe starten (Umbau v2, Entscheidung 41).

        Der Zeitplan (Wochentage, Uhrzeiten, Zeitzone) ist der einzige feste Termin. Ein fälliger Termin läuft immer:
        unabhängig von Handelstag, Feiertag, Startdatum und Spielzustand. Ist gerade eine Session oder ein anderer
        Lauf aktiv (oder fehlt das Token), bleibt der Termin sichtbar „wartend“ (GET /api/laeufe/plan) und wird
        bei jedem Takt wiederholt; nach `WARTEN_STUNDEN` ohne Erfolg gilt er sichtbar als nicht gestartet.
        Ein Termin, den der Dienst wegen eines Ausfalls verpasst hat, wird bis `NACHHOLEN_MINUTEN` danach nachgeholt.
        """
        plan = appdaten.laden()["zeitplan"]
        if not plan["automatik"]:
            return None
        zone = ZoneInfo(plan["zeitzone"])
        lokal = jetzt.astimezone(zone)
        erledigt = dict(self.zustand.get("zeitplan_erledigt", {}))
        offen = {k: dict(v) for k, v in self.zustand.get("zeitplan_offen", {}).items()}
        vorher = (dict(erledigt), json.dumps(offen, sort_keys=True))
        meldungen = []
        for termin in plan["termine"]:
            stunde, minute = map(int, termin["uhrzeit"].split(":"))
            beginn = lokal.replace(hour=stunde, minute=minute, second=0, microsecond=0)
            schluessel = f"{beginn:%Y-%m-%dT%H:%M}-{termin['art']}"
            nachholfenster = beginn + timedelta(minutes=NACHHOLEN_MINUTEN)
            if lokal.weekday() not in termin["wochentage"] or not (beginn <= lokal < nachholfenster):
                continue
            if schluessel in erledigt or schluessel in offen:
                continue
            offen[schluessel] = {"art": termin["art"], "auftraggeber": plan["auftraggeber"], "seit": jetzt.isoformat(),
                                 "grund": "fällig"}
        for schluessel, eintrag in sorted(offen.items(), key=lambda kv: kv[1]["seit"]):
            status, text = self.geplanten_lauf_anlegen(eintrag["art"], eintrag["auftraggeber"])
            if status == "angelegt":
                erledigt[schluessel] = text
                del offen[schluessel]
                meldungen.append(f"Zeitplan {schluessel}: {text}")
            elif status == "fehler":
                erledigt[schluessel] = f"nicht gestartet: {text}"
                del offen[schluessel]
                meldungen.append(f"Zeitplan {schluessel}: nicht gestartet: {text}")
            elif jetzt - datetime.fromisoformat(eintrag["seit"]) >= timedelta(hours=WARTEN_STUNDEN):
                erledigt[schluessel] = f"nicht gestartet: {text} (nach {WARTEN_STUNDEN} Stunden aufgegeben)"
                del offen[schluessel]
                meldungen.append(f"Zeitplan {schluessel}: aufgegeben: {text}")
            else:
                eintrag["grund"] = text
        grenze = f"{lokal - timedelta(days=7):%Y-%m-%d}"
        erledigt = {k: v for k, v in erledigt.items() if k >= grenze}
        if (erledigt, json.dumps(offen, sort_keys=True)) != vorher:
            self._merken(zeitplan_erledigt=erledigt, zeitplan_offen=offen)
        return "; ".join(meldungen) or None

    def geplanten_lauf_anlegen(self, art: str, auftraggeber: str) -> tuple[str, str]:
        """Legt den geplanten Lauf an. Ergebnis: ("angelegt" | "wartet" | "fehler", Klartext).

        „wartet“ (HTTP 409: Session aktiv, Lauf aktiv, Token fehlt) wird wiederholt, „fehler“ (422: Eingaben der
        Konfiguration ungültig) nicht.
        """
        from fastapi import HTTPException

        zweck = claude_optionen.optionen()["laufarten"][art]["zweck"]
        vorgabe = appdaten.laden()["claude"]["voreinstellungen"][zweck]
        with neue_sitzung() as db:
            try:
                auftraege.lauf_pruefen(db, art, vorgabe["modell"], vorgabe["aufwand"], auftraggeber)
            except HTTPException as exc:
                return ("wartet" if exc.status_code == 409 else "fehler"), f"{exc.detail}"
            auftrag = auftraege.anlegen(db, art, {}, modell=vorgabe["modell"], aufwand=vorgabe["aufwand"],
                                        auftraggeber=auftraggeber, ausloeser="zeitplan")
            db.add(AuditEintrag(akteur=None, aktion="lauf_geplant", ziel=auftrag.id,
                                meta=json.dumps({"art": art, "modell": vorgabe["modell"],
                                                 "aufwand": vorgabe["aufwand"] or "standard",
                                                 "auftraggeber": auftraggeber})))
            db.commit()
            return "angelegt", f"Lauf {auftrag.id} angelegt"

    def spiel_vorbereiten(self, auftrag, log_datei: Path, schwaerzen) -> list[str]:
        """Trading-Lauf: Ist das Spiel noch nicht initialisiert, initialisiert der Lauf es selbst (Entscheidung 41).

        Startdatum ist heute, die Standard-Anlagerichtlinien legt init.py an, die Freigabe nach AP12 trägt die Kennung
        des Auftraggebers dieses Laufs; dazu ein Audit-Eintrag und ein lokaler Commit. Liegt ein älteres Startdatum
        in der Zukunft (frühere Version), wird es auf heute vorgezogen, soweit noch nichts gebucht wurde.
        """
        g = _werkzeuge()["gemeinsam"]
        meldungen: list[str] = []
        spiel = g.spiel_lesen()
        if not spiel.get("startdatum") or not g.vorhandene_profile():
            lauf = werkzeug("init", "--freigabe", auftrag.auftraggeber, "--ausloeser", "lauf", timeout=120)
            if lauf.returncode != 0:
                meldungen.append("Spielstart durch den Lauf fehlgeschlagen: " + _letzte_zeile(lauf))
            else:
                werkzeug("datenverzeichnis", "commit", "-m",
                         f"aufbau: Spielstart durch Trading-Lauf (Freigabe AP12: {auftrag.auftraggeber})", timeout=120)
                with neue_sitzung() as db:
                    db.add(AuditEintrag(akteur=None, aktion="spielstart_automatisch", ziel=auftrag.id,
                                        meta=json.dumps({"freigabe": auftrag.auftraggeber,
                                                         "startdatum": g.spiel_lesen().get("startdatum")})))
                    db.commit()
                meldungen.append(f"Spiel noch nicht gestartet: Der Lauf hat es gestartet (Startdatum "
                                 f"{g.spiel_lesen().get('startdatum')}, Standard-Anlagerichtlinien, Freigabe "
                                 f"{auftrag.auftraggeber}).")
        elif spiel["startdatum"] > g.heute().isoformat():
            lauf = werkzeug("init", "--vorziehen", timeout=120)
            if lauf.returncode == 0:
                werkzeug("datenverzeichnis", "commit", "-m", "aufbau: Startdatum durch Trading-Lauf vorgezogen",
                         timeout=120)
                meldungen.append(f"Startdatum {spiel['startdatum']} lag in der Zukunft: auf heute vorgezogen.")
            else:
                meldungen.append("Startdatum liegt in der Zukunft und ließ sich nicht vorziehen: " + _letzte_zeile(lauf))
        if meldungen:
            with open(log_datei, "a", encoding="utf-8") as datei:
                for zeile in meldungen:
                    datei.write(schwaerzen(zeile) + "\n")
        return meldungen

    # ------------------------------------------------------------------ Aufträge

    def auftraege_bearbeiten(self) -> None:
        with neue_sitzung() as db:
            wartend = db.scalars(select(Auftrag).where(Auftrag.status == "wartet").order_by(Auftrag.erstellt)).all()
            ids = [(a.id, a.art) for a in wartend]
        for auftrag_id, art in ids:
            if art in TESTARTEN:
                self.test_ausfuehren(auftrag_id)
            elif art in auftraege.LAUFARTEN and not self.lauf_aktiv():
                self.lauf_thread = threading.Thread(target=self.lauf_ausfuehren, args=(auftrag_id,), daemon=True)
                self.lauf_thread.start()
            elif art == "claude_anmeldung" and not (self.anmeldung_thread and self.anmeldung_thread.is_alive()):
                self.anmeldung_thread = threading.Thread(target=self.anmeldung_ausfuehren, args=(auftrag_id,),
                                                         daemon=True)
                self.anmeldung_thread.start()

    def _status(self, auftrag_id: str, **werte) -> None:
        with neue_sitzung() as db:
            auftrag = db.get(Auftrag, auftrag_id)
            for schluessel, wert in werte.items():
                setattr(auftrag, schluessel, wert)
            db.commit()

    def test_ausfuehren(self, auftrag_id: str) -> None:
        with neue_sitzung() as db:
            auftrag = db.get(Auftrag, auftrag_id)
            art, parameter = auftrag.art, json.loads(auftrag.parameter or "{}")
        self._status(auftrag_id, status="laeuft", begonnen=jetzt_utc())
        try:
            ergebnis = self._test(art, parameter)
        except Exception as exc:  # noqa: BLE001 - Ergebnis im Klartext an die UI
            log.exception("Auftrag %s fehlgeschlagen", auftrag_id)
            ergebnis = {"ok": False, "meldung": f"{type(exc).__name__}: {str(exc)[:200]}"}
        self._status(auftrag_id, status="ok" if ergebnis.get("ok") else "fehler", beendet=jetzt_utc(),
                     meldung=ergebnis.get("meldung"), ergebnis=json.dumps(ergebnis, ensure_ascii=False))

    def _test(self, art: str, parameter: dict) -> dict:
        jetzt = datetime.now(UTC).isoformat(timespec="seconds")
        if art == "test_claude":
            token = appdaten.geheimnis("claude_token")
            if not token:
                return {"ok": False, "meldung": "Kein Claude-Token hinterlegt."}
            vorgaben = appdaten.laden()["claude"]["voreinstellungen"]
            kombinationen = {(v["modell"], v["aufwand"]) for v in vorgaben.values()}
            ergebnisse = [claude_lauf.verbindung_testen(token, m, a) for m, a in sorted(kombinationen)]
            ergebnis = {"ok": all(r["ok"] for r in ergebnisse), "meldung": " ".join(r["meldung"] for r in ergebnisse),
                        "zeit": jetzt}
            appdaten.bereich_speichern("claude", {"letzter_test": ergebnis})
            return ergebnis
        if art == "test_kurse":
            anbieter = parameter["anbieter"]
            zusatz = {}
            if anbieter != "yfinance":
                zusatz["STOCKMASTER_KURSANBIETER_KEY"] = appdaten.geheimnis(f"kurs_key_{anbieter}") or ""
            lauf = werkzeug("kurse", "test", "--anbieter", anbieter, zusatz=zusatz, timeout=60)
            try:
                ergebnis = json.loads(lauf.stdout.strip().splitlines()[-1])
            except (ValueError, IndexError):
                ergebnis = {"ok": False, "meldung": _letzte_zeile(lauf) or "keine Antwort"}
            ergebnis = {**ergebnis, "anbieter": anbieter, "zeit": jetzt}
            appdaten.bereich_speichern("kursdaten", {"letzter_test": ergebnis})
            return ergebnis
        if art == "test_feed":
            lauf = werkzeug("news", "test", "--url", parameter["url"], timeout=60)
            zeilen = lauf.stdout.strip().splitlines()
            if lauf.returncode == 0:
                return {"ok": True, "meldung": zeilen[0] if zeilen else "Feed gültig.",
                        "beispiele": [z.removeprefix("- ") for z in zeilen[1:4]]}
            return {"ok": False, "meldung": _letzte_zeile(lauf).removeprefix("Fehler: ")}
        if art == "kurse_jetzt":
            meldung = self.kurse_abrufen(historie=bool(parameter.get("historie")))
            self._merken(kurse_zeit=datetime.now(UTC).isoformat())
            return {"ok": not meldung.startswith("Fehler"), "meldung": meldung}
        if art == "news_jetzt":
            from .einrichtung import news_status

            meldung = self.news_abrufen()
            self._merken(news_zeit=datetime.now(UTC).isoformat())
            ergebnis = {"ok": not meldung.startswith("Fehler"), "meldung": meldung}
            if ergebnis["ok"]:  # einzelne ausgefallene Feeds: die Oberfläche zeigt eine Warnung statt eines Erfolgs
                ergebnis["fehlerhaft"] = news_status()["fehlerhaft"]
            return ergebnis
        return {"ok": False, "meldung": f"Unbekannter Auftrag {art}."}

    # ------------------------------------------------------------------ Claude-Anmeldung (setup-token)

    def anmeldung_ausfuehren(self, auftrag_id: str) -> None:
        """`claude setup-token` interaktiv: Link an die UI, Code aus der UI, Token verschlüsselt speichern.

        Ausgaben des Befehls werden weder geloggt noch gespeichert (sie enthalten das Token).
        """
        self._status(auftrag_id, status="laeuft", begonnen=jetzt_utc(),
                     ergebnis=json.dumps({"phase": "starte"}))
        code_datei = auftraege.anmeldecode_pfad(auftrag_id)

        def link_melden(link: str) -> None:
            self._status(auftrag_id, ergebnis=json.dumps({"phase": "warte_auf_code", "link": link}))

        def code_holen() -> str | None:
            if not code_datei.exists():
                return None
            code = code_datei.read_text(encoding="utf-8").strip()
            code_datei.unlink(missing_ok=True)
            self._status(auftrag_id, ergebnis=json.dumps({"phase": "pruefe_code"}))
            return code or None

        def abbrechen() -> bool:
            with neue_sitzung() as db:
                return bool(db.get(Auftrag, auftrag_id).abbrechen)

        try:
            with claude_lauf.TempVerzeichnis() as temp:
                ergebnis = claude_anmeldung.ausfuehren(link_melden, code_holen, abbrechen,
                                                       claude_anmeldung.umgebung(temp), temp)
        except claude_anmeldung.AnmeldeFehler as exc:
            status = "abgebrochen" if abbrechen() else "fehler"
            self._status(auftrag_id, status=status, beendet=jetzt_utc(), meldung=str(exc),
                         ergebnis=json.dumps({"phase": "fehler"}))
            return
        except FileNotFoundError:
            self._status(auftrag_id, status="fehler", beendet=jetzt_utc(), ergebnis=json.dumps({"phase": "fehler"}),
                         meldung="Claude Code CLI ist im Container nicht installiert.")
            return
        except Exception as exc:  # noqa: BLE001 - nur Typ und eigene Meldung, nie Ausgaben des Befehls
            log.error("Claude-Anmeldung %s fehlgeschlagen: %s", auftrag_id, type(exc).__name__)
            self._status(auftrag_id, status="fehler", beendet=jetzt_utc(), ergebnis=json.dumps({"phase": "fehler"}),
                         meldung=f"Anmeldung fehlgeschlagen ({type(exc).__name__}).")
            return
        finally:
            code_datei.unlink(missing_ok=True)
        appdaten.geheimnis_setzen("claude_token", ergebnis.token, quelle="anmeldung")
        appdaten.bereich_speichern("claude", {"letzter_test": None})
        test = self._test("test_claude", {})
        with neue_sitzung() as db:
            db.add(AuditEintrag(akteur=None, aktion="claude_anmeldung_abgeschlossen", ziel=auftrag_id,
                                meta=json.dumps({"text": "Claude-Token über die App-Anmeldung gespeichert"})))
            db.commit()
        self._status(auftrag_id, status="ok", beendet=jetzt_utc(),
                     meldung="Claude-Konto verbunden, Token verschlüsselt gespeichert. " + test.get("meldung", ""),
                     ergebnis=json.dumps({"phase": "fertig", "test_ok": bool(test.get("ok"))}))

    # ------------------------------------------------------------------ Claude-Lauf

    def lauf_ausfuehren(self, auftrag_id: str) -> None:
        with neue_sitzung() as db:
            auftrag = db.get(Auftrag, auftrag_id)
            if auftrag.status != "wartet":
                return
            auftrag.status, auftrag.begonnen = "laeuft", jetzt_utc()
            db.commit()
            db.refresh(auftrag)
            db.expunge(auftrag)
        log_datei = auftraege.log_pfad(auftrag_id)
        token = appdaten.geheimnis("claude_token")
        schwaerzen = claude_lauf.Schwaerzer(list(appdaten.alle_geheimnisse_klartext().values()))
        if not token:
            self._status(auftrag_id, status="fehler", beendet=jetzt_utc(), meldung="Kein Claude-Token hinterlegt.")
            return
        log_datei.parent.mkdir(parents=True, exist_ok=True)
        with open(log_datei, "a", encoding="utf-8") as datei:
            datei.write(f"Lauf {auftrag_id}: {auftrag.art}, Modell {auftrag.modell}, Aufwand "
                        f"{auftrag.aufwand or 'Standard'}, Auftraggeber {auftrag.auftraggeber}"
                        + (f", Vorgaben: {claude_lauf.vorgaben_versionen()}" if auftrag.art == "trading" else "") + "\n")
        if auftrag.art == "trading":
            try:
                self.spiel_vorbereiten(auftrag, log_datei, schwaerzen)
            except Exception as exc:  # noqa: BLE001 - der Lauf selbst meldet, was fehlt
                log.exception("Spielstart durch den Lauf %s fehlgeschlagen", auftrag_id)
                with open(log_datei, "a", encoding="utf-8") as datei:
                    datei.write(f"Spielstart durch den Lauf fehlgeschlagen: {type(exc).__name__}: {exc}\n")

        def abbrechen() -> bool:
            with neue_sitzung() as db:
                return bool(db.get(Auftrag, auftrag_id).abbrechen)

        zeitlimit = int(claude_optionen.optionen().get("zeitlimit_minuten", 90)) * 60
        e = einstellungen()
        try:
            with claude_lauf.TempVerzeichnis() as temp:
                ergebnis = claude_lauf.ausfuehren(
                    claude_lauf.lauf_befehl(auftrag.modell, auftrag.aufwand or ""),
                    claude_lauf.umgebung(token, temp), e.framework_pfad, log_datei, schwaerzen, abbrechen, zeitlimit,
                    auftrag=claude_lauf.prompt(auftrag.art, auftrag),
                    entscheider=freigaben.entscheider_fuer(auftrag_id, schwaerzen, abbrechen))
        except FileNotFoundError:
            ergebnis = {"rueckgabe": 127, "ausgabe": "Claude Code CLI ist im Container nicht installiert.",
                        "abgebrochen": None, "is_error": True}
        finally:
            freigaben.schliessen(auftrag_id)
        status, meldung = self._lauf_ergebnis(ergebnis)
        nachlauf = self._nachlauf(auftrag)
        with open(log_datei, "a", encoding="utf-8") as datei:
            for zeile in nachlauf["meldungen"]:
                datei.write(schwaerzen(zeile) + "\n")
        self._status(auftrag_id, status=status, meldung=meldung, beendet=jetzt_utc(), pruefung_ok=nachlauf["pruefung_ok"],
                     ergebnis=json.dumps({k: ergebnis.get(k) for k in ("result", "num_turns", "duration_ms", "subtype",
                                                                       "rueckgabe")}, ensure_ascii=False))

    @staticmethod
    def _lauf_ergebnis(ergebnis: dict) -> tuple[str, str]:
        if ergebnis.get("abgebrochen") == "abgebrochen":
            return "abgebrochen", "Vom Admin abgebrochen."
        if ergebnis.get("abgebrochen") == "zeitlimit":
            return "fehler", "Zeitlimit überschritten; Lauf abgebrochen."
        if ergebnis.get("rueckgabe") == 0 and not ergebnis.get("is_error"):
            return "ok", (ergebnis.get("result") or "Lauf beendet.")[:20000]
        return claude_lauf.fehler_einordnen(str(ergebnis.get("result") or ergebnis.get("ausgabe") or ""))

    def _nachlauf(self, auftrag) -> dict:
        """Nach dem Lauf: liegengebliebene Sperre freigeben, Rest committen, pruefe.py ausführen."""
        meldungen = []
        g = _werkzeuge()["gemeinsam"]
        sperre = g.sperre_lesen()
        if sperre and utc(auftrag.begonnen) and sperre["start_dt"] >= utc(auftrag.begonnen).astimezone(TZ) \
                - timedelta(minutes=1):
            lauf = werkzeug("session", "ende", timeout=120)
            meldungen.append("Nachlauf: Session-Sperre freigegeben. " + _letzte_zeile(lauf))
        lauf = werkzeug("datenverzeichnis", "commit", "-m", f"session: Nachtrag Lauf {auftrag.id[:8]} "
                        "(nicht committete Änderungen)", timeout=120)
        if "Lokal committet" in lauf.stdout:
            meldungen.append("Nachlauf: " + _letzte_zeile(lauf))
        pruefung = werkzeug("pruefe", timeout=300)
        meldungen.append("Prüfung: " + _letzte_zeile(pruefung))
        return {"meldungen": meldungen, "pruefung_ok": pruefung.returncode == 0}

    # ------------------------------------------------------------------ Schleife

    def einmal(self, jetzt: datetime | None = None) -> list[str]:
        jetzt = jetzt or datetime.now(UTC)
        meldungen = []
        if appdaten.zustand_lesen("wartung").get("seit"):
            self.herzschlag("Wartung (Wiederherstellung)")
            return ["Wartung"]
        self.auftraege_bearbeiten()
        for schritt in (self.zeitplan, self.richtlinien_standard, self.profile_ergaenzen, self.planen, self.ausfuehren,
                        self.beobachtung_aktualisieren, self.overnight_analysieren, self.nachbuchen, self.committen):
            try:
                ergebnis = schritt(jetzt)
            except Exception as exc:  # noqa: BLE001 - ein Fehler stoppt den Dienst nicht
                log.exception("Schritt %s fehlgeschlagen", schritt.__name__)
                ergebnis = f"{schritt.__name__}: {type(exc).__name__}: {exc}"
            if isinstance(ergebnis, list):
                meldungen += ergebnis
            elif ergebnis:
                meldungen.append(ergebnis)
        self.herzschlag("; ".join(meldungen)[-300:] or self.zustand.get("letzte_meldung", ""))
        if meldungen:
            self._merken(letzte_meldung="; ".join(meldungen)[-300:])
            for meldung in meldungen:
                log.info(meldung)
        return meldungen


def starten(pause: float = 5.0) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log.info("StockMaster-Hintergrunddienst startet (Daten: %s)", einstellungen().daten_pfad)
    with neue_sitzung() as db:
        anzahl = auftraege.verwaiste_aufraeumen(db, stunden=0)
        if anzahl:
            log.warning("%s Lauf/Läufe aus einem früheren Start als abgebrochen markiert.", anzahl)
    freigaben.schliessen()  # Anfragen eines früheren Starts: die CLI, die wartete, gibt es nicht mehr
    worker = Worker()
    while True:
        try:
            worker.einmal()
        except Exception:  # noqa: BLE001
            log.exception("Fehler in der Worker-Schleife")
        time.sleep(pause)
