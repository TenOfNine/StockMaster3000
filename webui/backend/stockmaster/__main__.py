"""Kommandozeile: python -m stockmaster <befehl>.

    admin-anlegen --email ... [--anzeigename ...]   einzigen ersten Admin anlegen
    migrieren                                        Datenbankschema aktualisieren
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
                    "starten und dort im Log nach 'db-abgleich' suchen. Prüfen, dass POSTGRES_APP_PASSWORD "
                    "in beiden Diensten gleich ist und nur Buchstaben und Ziffern enthält."
                ) from fehler
            time.sleep(pause)
    raise SystemExit("Die Datenbank ist nach dem Warten nicht erreichbar. Logs des Containers 'db' prüfen.")


def migrieren() -> None:
    from alembic.config import Config

    from alembic import command

    konfig = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    konfig.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    print(f"StockMaster API, Version {os.environ.get('SM_VERSION', 'unbekannt')}", flush=True)
    auf_datenbank_warten()
    command.upgrade(konfig, "head")


def admin_anlegen(email: str, anzeigename: str) -> int:
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
    args = parser.parse_args(argv)
    if args.befehl == "migrieren":
        migrieren()
        print("Datenbankschema aktuell.")
        return 0
    return admin_anlegen(args.email, args.anzeigename)


if __name__ == "__main__":
    sys.exit(main())
