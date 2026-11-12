"""Preferencias de aviso por equipo suscripto a push (ADR 0023).

`alerts`: recibe las alertas (como hasta ahora). `messages`: avisos de mensajes que llegan a las
placas del Cliente Meshtastic: `off`, `dm` (solo directos) o `all` (directos y canales).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-12
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE push_subscriptions ADD COLUMN alerts INTEGER NOT NULL DEFAULT 1")
    op.execute("ALTER TABLE push_subscriptions ADD COLUMN messages TEXT NOT NULL DEFAULT 'off'")


def downgrade() -> None:
    with op.batch_alter_table("push_subscriptions") as batch:
        batch.drop_column("messages")
        batch.drop_column("alerts")
