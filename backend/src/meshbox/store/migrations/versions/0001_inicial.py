"""Esquema inicial (sección 11.2 del plan, escrito a mano).

Revision ID: 0001
Revises:
Create Date: 2026-10-20
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

DDL = """
CREATE TABLE nodes (
  num INTEGER PRIMARY KEY,
  id TEXT NOT NULL UNIQUE,
  long_name TEXT, short_name TEXT,
  hw_model TEXT, role TEXT NOT NULL DEFAULT 'CLIENT',
  is_licensed INTEGER NOT NULL DEFAULT 0,
  public_key BLOB,
  firmware_version TEXT, region TEXT, modem_preset TEXT,
  lat REAL, lon REAL, alt INTEGER, precision_bits INTEGER, position_ts REAL,
  battery_level INTEGER, voltage REAL, channel_utilization REAL, air_util_tx REAL,
  uptime_s INTEGER, metrics_ts REAL,
  last_snr REAL, last_rssi INTEGER, last_hops INTEGER, last_gateway TEXT,
  first_seen REAL NOT NULL, last_heard REAL NOT NULL,
  heard_via_mqtt_only INTEGER NOT NULL DEFAULT 0,
  hidden INTEGER NOT NULL DEFAULT 0,
  is_fixed INTEGER NOT NULL DEFAULT 0,
  note TEXT,
  updated_at REAL NOT NULL
);
CREATE INDEX ix_nodes_last_heard ON nodes(last_heard);

CREATE TABLE packets (
  pk INTEGER PRIMARY KEY,
  from_num INTEGER NOT NULL,
  packet_id INTEGER NOT NULL,
  to_num INTEGER NOT NULL,
  channel_index INTEGER, channel_name TEXT, channel_hash INTEGER,
  portnum TEXT,
  first_rx REAL NOT NULL,
  hop_start INTEGER, want_ack INTEGER, priority TEXT,
  encrypted INTEGER NOT NULL, decoded_ok INTEGER NOT NULL,
  is_public INTEGER NOT NULL,
  payload_len INTEGER,
  raw BLOB,
  UNIQUE (from_num, packet_id)
);
CREATE INDEX ix_packets_rx ON packets(first_rx);
CREATE INDEX ix_packets_port_rx ON packets(portnum, first_rx);
CREATE INDEX ix_packets_from_rx ON packets(from_num, first_rx);

CREATE TABLE receptions (
  packet_pk INTEGER NOT NULL REFERENCES packets(pk) ON DELETE CASCADE,
  gateway TEXT NOT NULL,
  source TEXT NOT NULL,
  rx_time REAL NOT NULL,
  rx_snr REAL, rx_rssi INTEGER, hop_limit INTEGER, relay_node INTEGER, via_mqtt INTEGER,
  transport INTEGER,
  PRIMARY KEY (packet_pk, gateway)
) WITHOUT ROWID;

CREATE TABLE positions (
  node_num INTEGER NOT NULL, ts REAL NOT NULL,
  lat REAL NOT NULL, lon REAL NOT NULL, alt INTEGER, precision_bits INTEGER,
  ground_speed REAL, sats INTEGER, packet_pk INTEGER,
  PRIMARY KEY (node_num, ts)
) WITHOUT ROWID;

CREATE TABLE telemetry_device (
  node_num INTEGER NOT NULL, ts REAL NOT NULL,
  battery_level INTEGER, voltage REAL, channel_utilization REAL, air_util_tx REAL, uptime_s INTEGER,
  PRIMARY KEY (node_num, ts)
) WITHOUT ROWID;

CREATE TABLE telemetry_environment (
  node_num INTEGER NOT NULL, ts REAL NOT NULL,
  temperature REAL, relative_humidity REAL, barometric_pressure REAL,
  gas_resistance REAL, iaq INTEGER, lux REAL,
  wind_speed REAL, wind_gust REAL, wind_direction INTEGER,
  rainfall_1h REAL, rainfall_24h REAL,
  PRIMARY KEY (node_num, ts)
) WITHOUT ROWID;

CREATE TABLE telemetry_power (
  node_num INTEGER NOT NULL, ts REAL NOT NULL,
  ch1_voltage REAL, ch1_current REAL, ch2_voltage REAL, ch2_current REAL,
  ch3_voltage REAL, ch3_current REAL,
  PRIMARY KEY (node_num, ts)
) WITHOUT ROWID;

CREATE TABLE telemetry_rollup (
  node_num INTEGER NOT NULL, metric TEXT NOT NULL,
  bucket_s INTEGER NOT NULL, bucket_start REAL NOT NULL,
  n INTEGER NOT NULL, min REAL, max REAL, avg REAL,
  PRIMARY KEY (node_num, metric, bucket_s, bucket_start)
) WITHOUT ROWID;

CREATE TABLE messages (
  pk INTEGER PRIMARY KEY,
  packet_pk INTEGER UNIQUE REFERENCES packets(pk) ON DELETE SET NULL,
  ts REAL NOT NULL, from_num INTEGER NOT NULL, to_num INTEGER NOT NULL,
  channel_name TEXT, text TEXT NOT NULL,
  reply_id INTEGER, emoji INTEGER NOT NULL DEFAULT 0,
  is_alert INTEGER NOT NULL DEFAULT 0, hidden INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX ix_messages_ts ON messages(ts);

CREATE TABLE links (
  node_num INTEGER NOT NULL, neighbor_num INTEGER NOT NULL,
  source TEXT NOT NULL,
  snr REAL, ts REAL NOT NULL,
  PRIMARY KEY (node_num, neighbor_num, source)
) WITHOUT ROWID;

CREATE TABLE traceroutes (
  pk INTEGER PRIMARY KEY, packet_pk INTEGER, ts REAL NOT NULL,
  from_num INTEGER NOT NULL, to_num INTEGER NOT NULL,
  route TEXT, snr_towards TEXT, route_back TEXT, snr_back TEXT
);
CREATE INDEX ix_traceroutes_ts ON traceroutes(ts);

CREATE TABLE waypoints (
  id INTEGER PRIMARY KEY, from_num INTEGER, ts REAL, name TEXT, description TEXT,
  lat REAL, lon REAL, icon INTEGER, expire REAL
);

CREATE TABLE stats_hourly (
  hour_start REAL PRIMARY KEY,
  packets INTEGER NOT NULL, by_portnum TEXT NOT NULL,
  active_nodes INTEGER NOT NULL, new_nodes INTEGER NOT NULL,
  avg_channel_util REAL, by_hops TEXT
);

CREATE TABLE channels (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, hash INTEGER,
  key_ref TEXT,
  is_public INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE mqtt_accounts (
  username TEXT PRIMARY KEY, purpose TEXT NOT NULL,
  created_at REAL NOT NULL, note TEXT
);

CREATE TABLE alert_rules (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL,
  params TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
  cooldown_s INTEGER NOT NULL DEFAULT 900, channels TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'warning',
  is_public INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL, updated_at REAL NOT NULL
);

CREATE TABLE alert_events (
  id INTEGER PRIMARY KEY, rule_id INTEGER REFERENCES alert_rules(id) ON DELETE SET NULL,
  ts REAL NOT NULL, state TEXT NOT NULL,
  node_num INTEGER, title TEXT NOT NULL, body TEXT, severity TEXT NOT NULL,
  is_public INTEGER NOT NULL, ack_by INTEGER, ack_at REAL
);
CREATE INDEX ix_alert_events_ts ON alert_events(ts);

CREATE TABLE notification_log (
  id INTEGER PRIMARY KEY, alert_event_id INTEGER, channel TEXT NOT NULL,
  ts REAL NOT NULL, ok INTEGER NOT NULL, error TEXT
);

CREATE TABLE push_subscriptions (
  id INTEGER PRIMARY KEY, endpoint TEXT NOT NULL UNIQUE, p256dh TEXT NOT NULL, auth TEXT NOT NULL,
  scope TEXT NOT NULL,
  user_id INTEGER, created_at REAL NOT NULL, last_ok_at REAL, failures INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE users (
  id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
  role TEXT NOT NULL,
  disabled INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL, last_login_at REAL,
  must_change_password INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE sessions (
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  csrf_token TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL,
  last_seen_at REAL NOT NULL, ip TEXT, user_agent TEXT
);

CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY, ts REAL NOT NULL, user_id INTEGER, action TEXT NOT NULL,
  target TEXT, details TEXT, ip TEXT
);
CREATE INDEX ix_audit_log_ts ON audit_log(ts);

CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL NOT NULL);

CREATE TABLE plugins (
  id TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0, version TEXT,
  settings TEXT NOT NULL DEFAULT '{}', installed_at REAL NOT NULL
);
"""

TABLES = [
    "plugins",
    "settings",
    "audit_log",
    "sessions",
    "users",
    "push_subscriptions",
    "notification_log",
    "alert_events",
    "alert_rules",
    "mqtt_accounts",
    "channels",
    "stats_hourly",
    "waypoints",
    "traceroutes",
    "links",
    "messages",
    "telemetry_rollup",
    "telemetry_power",
    "telemetry_environment",
    "telemetry_device",
    "positions",
    "receptions",
    "packets",
    "nodes",
]


def upgrade() -> None:
    for statement in DDL.split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table}")
