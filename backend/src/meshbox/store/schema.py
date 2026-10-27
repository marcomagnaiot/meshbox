"""Tablas (SQLAlchemy Core, sin ORM). Fiel a la sección 11.2 del plan.

Diferencias registradas en ADR: `receptions.transport` (ADR 0009). El DDL real lo crea
la migración escrita a mano `migrations/versions/0001_inicial.py`; estas definiciones se
usan para armar consultas y deben coincidir con ella (lo verifica una prueba).
"""

from __future__ import annotations

from sqlalchemy import (
    REAL,
    Column,
    ForeignKey,
    Integer,
    LargeBinary,
    MetaData,
    PrimaryKeyConstraint,
    Table,
    Text,
    UniqueConstraint,
)

metadata = MetaData()


def _real(name: str, **kw: object) -> Column[float]:
    return Column(name, REAL, **kw)  # type: ignore[arg-type]


nodes = Table(
    "nodes",
    metadata,
    Column("num", Integer, primary_key=True, autoincrement=False),
    Column("id", Text, nullable=False, unique=True),
    Column("long_name", Text),
    Column("short_name", Text),
    Column("hw_model", Text),
    Column("role", Text, nullable=False, server_default="CLIENT"),
    Column("is_licensed", Integer, nullable=False, server_default="0"),
    Column("public_key", LargeBinary),
    Column("firmware_version", Text),
    Column("region", Text),
    Column("modem_preset", Text),
    _real("lat"),
    _real("lon"),
    Column("alt", Integer),
    Column("precision_bits", Integer),
    _real("position_ts"),
    Column("battery_level", Integer),
    _real("voltage"),
    _real("channel_utilization"),
    _real("air_util_tx"),
    Column("uptime_s", Integer),
    _real("metrics_ts"),
    _real("last_snr"),
    Column("last_rssi", Integer),
    Column("last_hops", Integer),
    Column("last_gateway", Text),
    _real("first_seen", nullable=False),
    _real("last_heard", nullable=False),
    Column("heard_via_mqtt_only", Integer, nullable=False, server_default="0"),
    Column("hidden", Integer, nullable=False, server_default="0"),
    Column("is_fixed", Integer, nullable=False, server_default="0"),
    Column("note", Text),
    _real("updated_at", nullable=False),
)

packets = Table(
    "packets",
    metadata,
    Column("pk", Integer, primary_key=True, autoincrement=False),
    Column("from_num", Integer, nullable=False),
    Column("packet_id", Integer, nullable=False),
    Column("to_num", Integer, nullable=False),
    Column("channel_index", Integer),
    Column("channel_name", Text),
    Column("channel_hash", Integer),
    Column("portnum", Text),
    _real("first_rx", nullable=False),
    Column("hop_start", Integer),
    Column("want_ack", Integer),
    Column("priority", Text),
    Column("encrypted", Integer, nullable=False),
    Column("decoded_ok", Integer, nullable=False),
    Column("is_public", Integer, nullable=False),
    Column("payload_len", Integer),
    Column("raw", LargeBinary),
    UniqueConstraint("from_num", "packet_id"),
)

receptions = Table(
    "receptions",
    metadata,
    Column("packet_pk", Integer, ForeignKey("packets.pk", ondelete="CASCADE"), nullable=False),
    Column("gateway", Text, nullable=False),
    Column("source", Text, nullable=False),
    _real("rx_time", nullable=False),
    _real("rx_snr"),
    Column("rx_rssi", Integer),
    Column("hop_limit", Integer),
    Column("relay_node", Integer),
    Column("via_mqtt", Integer),
    Column("transport", Integer),
    PrimaryKeyConstraint("packet_pk", "gateway"),
)

positions = Table(
    "positions",
    metadata,
    Column("node_num", Integer, nullable=False),
    _real("ts", nullable=False),
    _real("lat", nullable=False),
    _real("lon", nullable=False),
    Column("alt", Integer),
    Column("precision_bits", Integer),
    _real("ground_speed"),
    Column("sats", Integer),
    Column("packet_pk", Integer),
    PrimaryKeyConstraint("node_num", "ts"),
)

telemetry_device = Table(
    "telemetry_device",
    metadata,
    Column("node_num", Integer, nullable=False),
    _real("ts", nullable=False),
    Column("battery_level", Integer),
    _real("voltage"),
    _real("channel_utilization"),
    _real("air_util_tx"),
    Column("uptime_s", Integer),
    PrimaryKeyConstraint("node_num", "ts"),
)

telemetry_environment = Table(
    "telemetry_environment",
    metadata,
    Column("node_num", Integer, nullable=False),
    _real("ts", nullable=False),
    _real("temperature"),
    _real("relative_humidity"),
    _real("barometric_pressure"),
    _real("gas_resistance"),
    Column("iaq", Integer),
    _real("lux"),
    _real("wind_speed"),
    _real("wind_gust"),
    Column("wind_direction", Integer),
    _real("rainfall_1h"),
    _real("rainfall_24h"),
    PrimaryKeyConstraint("node_num", "ts"),
)

telemetry_power = Table(
    "telemetry_power",
    metadata,
    Column("node_num", Integer, nullable=False),
    _real("ts", nullable=False),
    _real("ch1_voltage"),
    _real("ch1_current"),
    _real("ch2_voltage"),
    _real("ch2_current"),
    _real("ch3_voltage"),
    _real("ch3_current"),
    PrimaryKeyConstraint("node_num", "ts"),
)

telemetry_rollup = Table(
    "telemetry_rollup",
    metadata,
    Column("node_num", Integer, nullable=False),
    Column("metric", Text, nullable=False),
    Column("bucket_s", Integer, nullable=False),
    _real("bucket_start", nullable=False),
    Column("n", Integer, nullable=False),
    _real("min"),
    _real("max"),
    _real("avg"),
    PrimaryKeyConstraint("node_num", "metric", "bucket_s", "bucket_start"),
)

messages = Table(
    "messages",
    metadata,
    Column("pk", Integer, primary_key=True, autoincrement=False),
    Column("packet_pk", Integer, ForeignKey("packets.pk", ondelete="SET NULL"), unique=True),
    _real("ts", nullable=False),
    Column("from_num", Integer, nullable=False),
    Column("to_num", Integer, nullable=False),
    Column("channel_name", Text),
    Column("text", Text, nullable=False),
    Column("reply_id", Integer),
    Column("emoji", Integer, nullable=False, server_default="0"),
    Column("is_alert", Integer, nullable=False, server_default="0"),
    Column("hidden", Integer, nullable=False, server_default="0"),
)

links = Table(
    "links",
    metadata,
    Column("node_num", Integer, nullable=False),
    Column("neighbor_num", Integer, nullable=False),
    Column("source", Text, nullable=False),
    _real("snr"),
    _real("ts", nullable=False),
    PrimaryKeyConstraint("node_num", "neighbor_num", "source"),
)

traceroutes = Table(
    "traceroutes",
    metadata,
    Column("pk", Integer, primary_key=True),
    Column("packet_pk", Integer),
    _real("ts", nullable=False),
    Column("from_num", Integer, nullable=False),
    Column("to_num", Integer, nullable=False),
    Column("route", Text),
    Column("snr_towards", Text),
    Column("route_back", Text),
    Column("snr_back", Text),
)

waypoints = Table(
    "waypoints",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=False),
    Column("from_num", Integer),
    _real("ts"),
    Column("name", Text),
    Column("description", Text),
    _real("lat"),
    _real("lon"),
    Column("icon", Integer),
    _real("expire"),
)

stats_hourly = Table(
    "stats_hourly",
    metadata,
    _real("hour_start", primary_key=True),
    Column("packets", Integer, nullable=False),
    Column("by_portnum", Text, nullable=False),
    Column("active_nodes", Integer, nullable=False),
    Column("new_nodes", Integer, nullable=False),
    _real("avg_channel_util"),
    Column("by_hops", Text),
    Column("by_relay", Text),  # 0002: retransmisiones por último byte del nodo
)

channels = Table(
    "channels",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", Text, nullable=False),
    Column("hash", Integer),
    Column("key_ref", Text),
    Column("is_public", Integer, nullable=False, server_default="0"),
)

mqtt_accounts = Table(
    "mqtt_accounts",
    metadata,
    Column("username", Text, primary_key=True),
    Column("purpose", Text, nullable=False),
    _real("created_at", nullable=False),
    Column("note", Text),
)

alert_rules = Table(
    "alert_rules",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("params", Text, nullable=False),
    Column("enabled", Integer, nullable=False, server_default="1"),
    Column("cooldown_s", Integer, nullable=False, server_default="900"),
    Column("channels", Text, nullable=False),
    Column("severity", Text, nullable=False, server_default="warning"),
    Column("is_public", Integer, nullable=False, server_default="0"),
    _real("created_at", nullable=False),
    _real("updated_at", nullable=False),
)

alert_events = Table(
    "alert_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=False),
    Column("rule_id", Integer, ForeignKey("alert_rules.id", ondelete="SET NULL")),
    _real("ts", nullable=False),
    Column("state", Text, nullable=False),
    Column("node_num", Integer),
    Column("title", Text, nullable=False),
    Column("body", Text),
    Column("severity", Text, nullable=False),
    Column("is_public", Integer, nullable=False),
    Column("ack_by", Integer),
    _real("ack_at"),
)

notification_log = Table(
    "notification_log",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("alert_event_id", Integer),
    Column("channel", Text, nullable=False),
    _real("ts", nullable=False),
    Column("ok", Integer, nullable=False),
    Column("error", Text),
)

push_subscriptions = Table(
    "push_subscriptions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("endpoint", Text, nullable=False, unique=True),
    Column("p256dh", Text, nullable=False),
    Column("auth", Text, nullable=False),
    Column("scope", Text, nullable=False),
    Column("user_id", Integer),
    _real("created_at", nullable=False),
    _real("last_ok_at"),
    Column("failures", Integer, nullable=False, server_default="0"),
)

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("username", Text, nullable=False, unique=True),
    Column("password_hash", Text, nullable=False),
    Column("role", Text, nullable=False),
    Column("disabled", Integer, nullable=False, server_default="0"),
    _real("created_at", nullable=False),
    _real("last_login_at"),
    Column("must_change_password", Integer, nullable=False, server_default="0"),
)

sessions = Table(
    "sessions",
    metadata,
    Column("token_hash", Text, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("csrf_token", Text, nullable=False),
    _real("created_at", nullable=False),
    _real("expires_at", nullable=False),
    _real("last_seen_at", nullable=False),
    Column("ip", Text),
    Column("user_agent", Text),
)

audit_log = Table(
    "audit_log",
    metadata,
    Column("id", Integer, primary_key=True),
    _real("ts", nullable=False),
    Column("user_id", Integer),
    Column("action", Text, nullable=False),
    Column("target", Text),
    Column("details", Text),
    Column("ip", Text),
)

settings = Table(
    "settings",
    metadata,
    Column("key", Text, primary_key=True),
    Column("value", Text, nullable=False),
    _real("updated_at", nullable=False),
)

plugins = Table(
    "plugins",
    metadata,
    Column("id", Text, primary_key=True),
    Column("enabled", Integer, nullable=False, server_default="0"),
    Column("version", Text),
    Column("settings", Text, nullable=False, server_default="{}"),
    _real("installed_at", nullable=False),
)

# Cliente Meshtastic del panel (ADR 0016): mensajes de cada placa USB/TCP y lo leído por usuario.
radio_messages = Table(
    "radio_messages",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("board", Text, nullable=False),
    Column("connector_id", Text, nullable=False),
    Column("conv", Text, nullable=False),
    _real("ts", nullable=False),
    Column("direction", Text, nullable=False),
    Column("packet_id", Integer, nullable=False, server_default="0"),
    Column("from_id", Text),
    Column("to_id", Text),
    Column("dm", Integer, nullable=False, server_default="0"),
    Column("channel_index", Integer, nullable=False, server_default="0"),
    Column("channel", Text),
    Column("text", Text, nullable=False),
    _real("snr"),
    Column("rssi", Integer),
    Column("hops", Integer),
    Column("reply_id", Integer),
    Column("emoji", Integer, nullable=False, server_default="0"),
    Column("status", Text),
)

radio_reads = Table(
    "radio_reads",
    metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("board", Text, nullable=False),
    Column("conv", Text, nullable=False),
    Column("seq", Integer, nullable=False),
    PrimaryKeyConstraint("user_id", "board", "conv"),
)
