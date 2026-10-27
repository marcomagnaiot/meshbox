"""Historial de mensajes del cliente Meshtastic y lo leído por cada usuario (ADR 0016).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-26
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

DDL = """
CREATE TABLE radio_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  board TEXT NOT NULL,
  connector_id TEXT NOT NULL,
  conv TEXT NOT NULL,
  ts REAL NOT NULL,
  direction TEXT NOT NULL,
  packet_id INTEGER NOT NULL DEFAULT 0,
  from_id TEXT, to_id TEXT,
  dm INTEGER NOT NULL DEFAULT 0,
  channel_index INTEGER NOT NULL DEFAULT 0,
  channel TEXT,
  text TEXT NOT NULL,
  snr REAL, rssi INTEGER, hops INTEGER,
  reply_id INTEGER,
  emoji INTEGER NOT NULL DEFAULT 0,
  status TEXT
);
CREATE INDEX ix_radio_messages_board ON radio_messages(board, id);
CREATE INDEX ix_radio_messages_conv ON radio_messages(board, conv, id);
CREATE INDEX ix_radio_messages_ts ON radio_messages(ts);
CREATE UNIQUE INDEX ux_radio_messages_packet ON radio_messages(board, from_id, packet_id)
  WHERE packet_id != 0;

CREATE TABLE radio_reads (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  board TEXT NOT NULL,
  conv TEXT NOT NULL,
  seq INTEGER NOT NULL,
  PRIMARY KEY (user_id, board, conv)
) WITHOUT ROWID
"""


def upgrade() -> None:
    for statement in DDL.split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS radio_reads")
    op.execute("DROP TABLE IF EXISTS radio_messages")
