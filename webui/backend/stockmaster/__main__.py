"""Kommandozeile: python -m stockmaster <befehl>.

    vorbereiten                                      Containerstart: Datenbank, Datenverzeichnis, Schlüssel,
                                                     Übernahme alter Umgebungsvariablen
    migrieren                                        nur Datenbankschema aktualisieren
    admin-anlegen --email ... [--anzeigename ...]   einzigen ersten Admin anlegen
    worker                                           Hintergrunddienst (Kurse, News, Zeitplan, Claude-Läufe)
    sicherung-export --datei X [--mit-geheimnissen]  Datenverzeichnis sichern (tar.gz inkl. lokalem Git)
    sicherung-import --datei X [--ohne-einstellungen] [--geheimnisse]
    geheimnisse-pruefen --repo P                     (Git-Hook) Commit ablehnen, wenn ein Secret enthalten ist
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import select

from . import sicherheit as s
from .db import neue_sitzung
from .modelle import AuditEintrag, Benutzer


def konfiguration_pruefen(schluessel_pflicht: bool = True) -> None:
    """Bricht mit klarer Meldung ab, wenn die Konfiguration unbrauchbar ist (statt erst bei der Anmeldung).

    Ohne Schlüssel (frische Installation) ist das vor `vorbereiten` erlaubt; ein vorhandener, aber
    ungültiger Schlüssel bricht immer ab.
    """
    from .config import SchluesselFehler, einstellungen

    e = einstellungen()
    vorhanden = e.master_schluessel_datei.exists() or bool(e.schluessel) or bool(
        e.schluessel_datei and e.schluessel_datei.exists())
    if not vorhanden and not schluessel_pflicht:
        return
    try:
        e.schluessel_bytes()
    except SchluesselFehler as fehler:
        raise SystemExit(f"Konfigurationsfehler: {fehler}") from None


def auf_datenbank_warten(versuche: int = 40, pause: float = 3.0) -> None:
    """Wartet, bis die Datenbank Verbindungen annimmt (Start im Verbund mit der DB, Erstinitialisierung)."""
    import time

    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    from .db import engine

    abgelehnt = 0
    for versuch in range(1, versuche + 1):
        try:
            with engine().connect() as verbindung:
                verbindung.execute(text("select 1"))
            return
        except OperationalError as fehler:
            ursache = str(fehler.orig).strip().splitlines()[0] if fehler.orig else str(fehler)
            print(f"Datenbank noch nicht erreichbar (Versuch {versuch}/{versuche}): {ursache}", file=sys.stderr, flush=True)
            # Der Passwortabgleich des DB-Containers kann beim Start kurz nachlaufen: erst nach
            # mehreren abgelehnten Anmeldungen aufgeben.
            abgelehnt += "password authentication failed" in ursache
            if abgelehnt >= 10:
                raise SystemExit(
                    "Anmeldung an der Datenbank abgelehnt: Das Passwort passt nicht zur Datenbank. "
                    "Der Datenbank-Container gleicht die Passwörter bei jedem Start ab: Container 'db' neu "
                    "starten und dort im Log nach 'db-abgleich' suchen. Das Passwort steht im Volume 'geheim' "
                    "(vom DB-Container erzeugt); ein gesetztes POSTGRES_APP_PASSWORD wird nur beim ersten Start "
                    "übernommen."
                ) from fehler
            time.sleep(pause)
    raise SystemExit("Die Datenbank ist nach dem Warten nicht erreichbar. Logs des Containers 'db' prüfen.")


def migrieren() -> None:
    from alembic.config import Config

    from alembic import command

    konfig = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    konfig.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    print(f"StockMaster API, Version {os.environ.get('SM_VERSION', 'unbekannt')}", flush=True)
    konfiguration_pruefen(schluessel_pflicht=False)
    auf_datenbank_warten()
    command.upgrade(konfig, "head")


def _werkzeuge_laden():
    """tools/ des Frameworks importierbar machen (Datenverzeichnis über die Umgebung)."""
    from .spiel import lesen

    return lesen.werkzeuge()


def hook_installieren(daten: Path) -> None:
    """pre-commit-Hook im Spielstand-Git: Commits mit Secrets werden abgelehnt."""
    haken = daten / ".git" / "hooks" / "pre-commit"
    haken.parent.mkdir(parents=True, exist_ok=True)
    backend = Path(__file__).resolve().parent.parent
    haken.write_text("#!/bin/sh\n# StockMaster: verhindert, dass Secrets aus der App-Konfiguration ins Spielstand-Git "
                     "gelangen.\n"
                     f'PYTHONPATH="{backend}" exec "{sys.executable}" -m stockmaster geheimnisse-pruefen --repo "$(pwd)"\n',
                     encoding="utf-8")
    haken.chmod(0o755)


def einrichten() -> list[str]:
    """Datenverzeichnis, App-Verzeichnis, Master-Schlüssel und Übernahme alter Umgebungsvariablen."""
    from . import appdaten
    from .config import SchluesselFehler, einstellungen

    e = einstellungen()
    meldungen = []
    e.app_pfad.mkdir(parents=True, exist_ok=True)
    for unter in ("laeufe", "zustand", "tmp", "sicherungen"):
        (e.app_pfad / unter).mkdir(exist_ok=True)
    with neue_sitzung() as db:
        totp = db.scalar(select(Benutzer).where(Benutzer.totp_secret_enc.is_not(None)).limit(1)) is not None
    try:
        meldungen += appdaten.schluessel_einrichten(totp)
    except SchluesselFehler as fehler:
        raise SystemExit(f"Konfigurationsfehler: {fehler}") from None
    w = _werkzeuge_laden()
    dv = w["datenverzeichnis"]
    daten = e.daten_pfad
    if dv.ist_eingerichtet(daten):
        meldungen += dv.einrichten(daten)
    elif e.repo_pfad and e.repo_pfad.exists() and dv.ist_leer(daten) and (
            any((e.repo_pfad / "portfolios").glob("*.json")) or any((e.repo_pfad / "journal").glob("*.md"))):
        import migriere  # noqa: PLC0415 - aus tools/

        meldungen += migriere.migrieren(e.repo_pfad, daten)
    else:
        meldungen += dv.einrichten(daten)
    hook_installieren(daten)
    meldungen += appdaten.aus_umgebung_uebernehmen()
    for name in appdaten.ueberfluessige_variablen():
        meldungen.append(f"Hinweis: Umgebungsvariable {name} wird nicht mehr gebraucht und kann aus dem Stack entfernt "
                         "werden.")
    return meldungen


def vorbereiten() -> None:
    migrieren()
    for meldung in einrichten():
        print(meldung, flush=True)


def geheimnisse_pruefen(repo: Path) -> int:
    """Git-Hook: lehnt einen Commit ab, wenn ein Secret im gestagten Inhalt steht (nennt nie den Wert)."""
    import subprocess

    from . import appdaten
    from .claude_lauf import TOKEN_MUSTER
    from .config import einstellungen

    if not einstellungen().master_schluessel_datei.exists():
        return 0
    werte = appdaten.alle_geheimnisse_klartext()
    diff = subprocess.run(["git", "-c", f"safe.directory={repo}", "-C", str(repo), "diff", "--cached", "-U0",
                           "--no-color", "--no-ext-diff"], capture_output=True, text=True, errors="replace").stdout
    datei = None
    for zeile in diff.splitlines():
        if zeile.startswith("+++ "):
            datei = zeile[6:] if zeile.startswith("+++ b/") else zeile[4:]
            continue
        if not zeile.startswith("+"):
            continue
        for name, wert in werte.items():
            if len(wert) >= 8 and wert in zeile:
                print(f"Commit abgelehnt: {appdaten.GEHEIMNISSE[name]} aus der App-Konfiguration steht in {datei}. "
                      "Bitte entfernen.", file=sys.stderr)
                return 1
        if TOKEN_MUSTER.search(zeile):
            print(f"Commit abgelehnt: {datei} enthält etwas, das wie ein Claude-Token aussieht.", file=sys.stderr)
            return 1
    return 0


def sicherung_export(datei: Path, mit_geheimnissen: bool) -> int:
    from getpass import getpass

    from . import sicherung

    passwort = None
    if mit_geheimnissen:
        passwort = os.environ.get("SM_SICHERUNG_PASSWORT") or getpass("Sicherungspasswort (mind. 12 Zeichen): ")
    try:
        manifest = sicherung.exportieren(datei, mit_geheimnissen, passwort)
    except sicherung.SicherungsFehler as fehler:
        print(f"Fehler: {fehler}", file=sys.stderr)
        return 1
    print(f"Sicherung geschrieben: {datei} (Commit {manifest['spielstand_commit']}, "
          f"{'mit' if mit_geheimnissen else 'ohne'} Secrets)")
    return 0


def sicherung_import(datei: Path, einstellungen_uebernehmen: bool, mit_geheimnissen: bool) -> int:
    from getpass import getpass

    from . import sicherung

    passwort = None
    if mit_geheimnissen:
        passwort = os.environ.get("SM_SICHERUNG_PASSWORT") or getpass("Sicherungspasswort: ")
    try:
        ergebnis = sicherung.wiederherstellen(datei, einstellungen_uebernehmen, passwort)
    except sicherung.SicherungsFehler as fehler:
        print(f"Fehler: {fehler}", file=sys.stderr)
        return 1
    print(f"Wiederhergestellt (Commit {ergebnis['manifest'].get('spielstand_commit')}); vorheriger Stand gesichert "
          f"als {ergebnis['vorher_gesichert']}.")
    return 0


def admin_anlegen(email: str, anzeigename: str) -> int:
    konfiguration_pruefen()
    with neue_sitzung() as db:
        if db.scalar(select(Benutzer).where(Benutzer.ist_admin)):
            print("Abgelehnt: Es gibt bereits einen Administrator. Weitere Benutzer legt ein Admin in der UI an.",
                  file=sys.stderr)
            return 1
        if db.scalar(select(Benutzer).where(Benutzer.email == email.lower())):
            print("Abgelehnt: Die E-Mail-Adresse ist bereits vergeben.", file=sys.stderr)
            return 1
        passwort = s.einmalpasswort()
        admin = Benutzer(email=email.lower(), anzeigename=anzeigename, kennung=s.neue_kennung(),
                         passwort_hash=s.passwort_hash(passwort), ist_admin=True, passwortwechsel_noetig=True)
        db.add(admin)
        db.flush()
        db.add(AuditEintrag(akteur=None, aktion="admin_erstanlage", ziel=admin.id))
        db.commit()
    print(f"Administrator angelegt. Einmalpasswort (nur jetzt sichtbar): {passwort}")
    print("Bei der ersten Anmeldung sind Passwortwechsel und Zwei-Faktor Pflicht.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m stockmaster", description="StockMaster-3000-Verwaltung")
    unter = parser.add_subparsers(dest="befehl", required=True)
    p = unter.add_parser("admin-anlegen", help="ersten Administrator anlegen (nur einmal möglich)")
    p.add_argument("--email", required=True)
    p.add_argument("--anzeigename", default="Administrator")
    unter.add_parser("migrieren", help="Datenbankschema aktualisieren")
    unter.add_parser("vorbereiten", help="Start: Datenbank, Datenverzeichnis, Schlüssel, Übernahme aus der Umgebung")
    unter.add_parser("worker", help="Hintergrunddienst starten")
    p = unter.add_parser("geheimnisse-pruefen", help="Git-Hook: Commit mit Secrets ablehnen")
    p.add_argument("--repo", default=".")
    p = unter.add_parser("sicherung-export", help="Datenverzeichnis sichern")
    p.add_argument("--datei", required=True)
    p.add_argument("--mit-geheimnissen", action="store_true",
                   help="Secrets passwortverschlüsselt beilegen (Passwort aus SM_SICHERUNG_PASSWORT oder Abfrage)")
    p = unter.add_parser("sicherung-import", help="Sicherung wiederherstellen (ersetzt das Datenverzeichnis)")
    p.add_argument("--datei", required=True)
    p.add_argument("--ohne-einstellungen", action="store_true")
    p.add_argument("--geheimnisse", action="store_true", help="Secrets aus der Sicherung übernehmen (Passwort nötig)")
    args = parser.parse_args(argv)
    if args.befehl == "migrieren":
        migrieren()
        print("Datenbankschema aktuell.")
        return 0
    if args.befehl == "vorbereiten":
        vorbereiten()
        return 0
    if args.befehl == "worker":
        from . import appdaten
        from .worker import starten

        auf_datenbank_warten()
        with neue_sitzung() as db:
            totp = db.scalar(select(Benutzer).where(Benutzer.totp_secret_enc.is_not(None)).limit(1)) is not None
        appdaten.schluessel_einrichten(totp)
        starten()
        return 0
    if args.befehl == "geheimnisse-pruefen":
        return geheimnisse_pruefen(Path(args.repo).resolve())
    if args.befehl == "sicherung-export":
        return sicherung_export(Path(args.datei), args.mit_geheimnissen)
    if args.befehl == "sicherung-import":
        return sicherung_import(Path(args.datei), not args.ohne_einstellungen, args.geheimnisse)
    return admin_anlegen(args.email, args.anzeigename)


if __name__ == "__main__":
    sys.exit(main())
