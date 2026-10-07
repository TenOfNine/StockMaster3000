"""Freigaben: Anfragen der Claude-CLI an einen Menschen (Befehl erlauben oder ablehnen)

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "freigaben",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("auftrag_id", sa.String(36), sa.ForeignKey("auftraege.id", ondelete="CASCADE"), nullable=False),
        sa.Column("werkzeug", sa.String(60), nullable=False),
        sa.Column("befehl", sa.Text, nullable=False),
        sa.Column("beschreibung", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="offen"),
        sa.Column("grund", sa.Text, nullable=True),
        sa.Column("erstellt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("laeuft_ab", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entschieden", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entschieden_von", sa.String(36), nullable=True),
    )
    op.create_index("ix_freigaben_auftrag_id", "freigaben", ["auftrag_id"])
    op.create_index("ix_freigaben_status", "freigaben", ["status"])
    op.create_index("ix_freigaben_erstellt", "freigaben", ["erstellt"])


def downgrade() -> None:
    op.drop_table("freigaben")
