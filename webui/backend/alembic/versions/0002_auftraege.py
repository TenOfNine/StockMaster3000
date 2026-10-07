"""Aufträge an den Hintergrunddienst (Claude-Läufe, Verbindungstests)

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auftraege",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("art", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="wartet"),
        sa.Column("parameter", sa.Text, nullable=True),
        sa.Column("ergebnis", sa.Text, nullable=True),
        sa.Column("meldung", sa.Text, nullable=True),
        sa.Column("modell", sa.String(100), nullable=True),
        sa.Column("aufwand", sa.String(20), nullable=True),
        sa.Column("auftraggeber", sa.String(40), nullable=True),
        sa.Column("ausloeser", sa.String(20), nullable=False, server_default="manuell"),
        sa.Column("erstellt_von", sa.String(36), nullable=True),
        sa.Column("erstellt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("begonnen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("beendet", sa.DateTime(timezone=True), nullable=True),
        sa.Column("abbrechen", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("pruefung_ok", sa.Boolean, nullable=True),
    )
    op.create_index("ix_auftraege_art", "auftraege", ["art"])
    op.create_index("ix_auftraege_status", "auftraege", ["status"])
    op.create_index("ix_auftraege_erstellt", "auftraege", ["erstellt"])


def downgrade() -> None:
    op.drop_table("auftraege")
