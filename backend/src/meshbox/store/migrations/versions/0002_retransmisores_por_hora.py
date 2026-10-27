"""Retransmisiones por hora en stats_hourly (consultas de 30 días en la Pi, E8).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-20
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

RELAY_SQL = (
    "SELECT r.relay_node & 255, count(*) FROM packets p JOIN receptions r ON r.packet_pk = p.pk "
    "WHERE p.first_rx >= :s AND p.first_rx < :e AND r.relay_node IS NOT NULL "
    "AND r.relay_node != 0 GROUP BY 1"
)


def upgrade() -> None:
    op.execute("ALTER TABLE stats_hourly ADD COLUMN by_relay TEXT")
    conn = op.get_bind()
    hours = conn.execute(sa.text("SELECT hour_start FROM stats_hourly")).scalars().all()
    for hour in hours:
        rows = conn.execute(sa.text(RELAY_SQL), {"s": hour, "e": hour + 3600}).all()
        conn.execute(
            sa.text("UPDATE stats_hourly SET by_relay = :r WHERE hour_start = :h"),
            {"r": json.dumps({str(k): v for k, v in rows}), "h": hour},
        )


def downgrade() -> None:
    op.execute("ALTER TABLE stats_hourly DROP COLUMN by_relay")
