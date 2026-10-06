"""Kommandozeile: python -m stockmaster <befehl>.

    admin-anlegen --email ... [--anzeigename ...]   einzigen ersten Admin anlegen
    migrieren                                        Datenbankschema aktualisieren
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import select

from . import sicherheit as s
from .db import neue_sitzung
from .modelle import AuditEintrag, Benutzer


def migrieren() -> None:
    from alembic.config import Config

    from alembic import command

    konfig = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    konfig.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
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
