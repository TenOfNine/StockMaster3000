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
        """Nach dem Spielstart gelten die Standard-Anlagerichtlinien, solange keine eigene vorliegt."""
        if self.lauf_aktiv() or auftraege.session_sperre_aktiv() is not None:
            return None
        g = _werkzeuge()["gemeinsam"]
        if not g.spiel_lesen().get("startdatum") or not g.richtlinien_offen():
            return None
        lauf = werkzeug("richtlinien", "standard", timeout=60)
        if lauf.returncode != 0:
            return "Standard-Anlagerichtlinien: " + _letzte_zeile(lauf)
        werkzeug("datenverzeichnis", "commit", "-m", "aufbau: Standard-Anlagerichtlinien übernommen", timeout=60)
        return "Standard-Anlagerichtlinien übernommen."

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
        plan = appdaten.laden()["zeitplan"]
        if not plan["automatik"]:
            return None
        zone = ZoneInfo(plan["zeitzone"])
        lokal = jetzt.astimezone(zone)
        kurse = _werkzeuge()["kurse"]
        handelstag = any(kurse.ist_handelstag(t, lokal.date()) for t in ("EUNL.DE", "^GSPC"))
        erledigt = self.zustand.get("zeitplan_erledigt", {})
        for termin in plan["termine"]:
            stunde, minute = map(int, termin["uhrzeit"].split(":"))
            beginn = lokal.replace(hour=stunde, minute=minute, second=0, microsecond=0)
            schluessel = f"{beginn:%Y-%m-%dT%H:%M}-{termin['art']}"
            if lokal.weekday() not in termin["wochentage"] or not (beginn <= lokal < beginn + timedelta(minutes=30)):
                continue
            if schluessel in erledigt:
                continue
            erledigt = {k: v for k, v in erledigt.items() if k >= f"{lokal - timedelta(days=7):%Y-%m-%d}"}
            if not handelstag:
                erledigt[schluessel] = "kein Handelstag"
                self._merken(zeitplan_erledigt=erledigt)
                continue
            erledigt[schluessel] = self.geplanten_lauf_anlegen(termin["art"], plan["auftraggeber"])
            self._merken(zeitplan_erledigt=erledigt)
            return f"Zeitplan {schluessel}: {erledigt[schluessel]}"
        return None

    def geplanten_lauf_anlegen(self, art: str, auftraggeber: str) -> str:
        from fastapi import HTTPException

        zweck = claude_optionen.optionen()["laufarten"][art]["zweck"]
        vorgabe = appdaten.laden()["claude"]["voreinstellungen"][zweck]
        with neue_sitzung() as db:
            try:
                auftraege.lauf_pruefen(db, art, vorgabe["modell"], vorgabe["aufwand"], auftraggeber, geplant=True)
            except HTTPException as exc:
                return f"übersprungen: {exc.detail}"
            auftrag = auftraege.anlegen(db, art, {}, modell=vorgabe["modell"], aufwand=vorgabe["aufwand"],
                                        auftraggeber=auftraggeber, ausloeser="zeitplan")
            db.add(AuditEintrag(akteur=None, aktion="lauf_geplant", ziel=auftrag.id,
                                meta=json.dumps({"art": art, "modell": vorgabe["modell"],
                                                 "aufwand": vorgabe["aufwand"] or "standard",
                                                 "auftraggeber": auftraggeber})))
            db.commit()
            return f"Lauf {auftrag.id} angelegt"

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
        for schritt in (self.zeitplan, self.richtlinien_standard, self.planen, self.beobachtung_aktualisieren,
                        self.nachbuchen, self.committen):
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
