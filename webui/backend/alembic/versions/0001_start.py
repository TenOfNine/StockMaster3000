"""Benutzer, Sitzungen, Audit-Log

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("anzeigename", sa.String(80), nullable=False),
        sa.Column("kennung", sa.String(20), nullable=False, unique=True),
        sa.Column("passwort_hash", sa.String(255), nullable=False),
        sa.Column("ist_admin", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("aktiv", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("totp_secret_enc", sa.Text, nullable=True),
        sa.Column("totp_aktiv", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("passwortwechsel_noetig", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("fehlversuche", sa.Integer, nullable=False, server_default="0"),
        sa.Column("gesperrt_bis", sa.DateTime(timezone=True), nullable=True),
        sa.Column("erstellt", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table(
        "auth_sessions",
        sa.Column("id_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("csrf", sa.String(64), nullable=False),
        sa.Column("totp_offen", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("erstellt", sa.DateTime(timezone=True), nullable=False),
        sa.Column("zuletzt_aktiv", sa.DateTime(timezone=True), nullable=False),
        sa.Column("laeuft_ab", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_hash", sa.String(64), nullable=False),
        sa.Column("user_agent", sa.String(200), nullable=False),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("akteur", sa.String(36), nullable=True),
        sa.Column("aktion", sa.String(60), nullable=False),
        sa.Column("ziel", sa.String(120), nullable=True),
        sa.Column("zeit", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_hash", sa.String(64), nullable=True),
        sa.Column("meta", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
