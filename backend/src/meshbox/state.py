"""Estado en memoria: nodos, canales, gateways y métricas en vivo (secciones 5.3 y 12.2.1).

Todo se modifica desde el loop asyncio (sin hilos), así que no hace falta bloqueo.
La base es la persistencia; este estado es la fuente de las respuestas en vivo.
"""

from __future__ import annotations

import time
from collections import Counter, deque
from dataclasses import asdict, dataclass, field, fields
from typing import Any

import orjson
from sqlalchemy import Connection, text

from .models import node_id
from .pipeline.crypto import ChannelKey, decode_psk
from .pipeline.decode import INFRA_ROLES, precision_meters

DEFAULT_THRESHOLDS = {"active_s": 3600, "recent_s": 7200, "late_s": 86400}
NOT_STORED = ("env", "stored_pos", "is_gateway")  # campos de NodeRecord sin columna en `nodes`


@dataclass(slots=True)
class NodeRecord:
    num: int
    id: str
    first_seen: float
    last_heard: float
    long_name: str | None = None
    short_name: str | None = None
    hw_model: str | None = None
    role: str = "CLIENT"
    is_licensed: int = 0
    public_key: bytes | None = None
    firmware_version: str | None = None
    region: str | None = None
    modem_preset: str | None = None
    lat: float | None = None
    lon: float | None = None
    alt: int | None = None
    precision_bits: int | None = None
    position_ts: float | None = None
    battery_level: int | None = None
    voltage: float | None = None
    channel_utilization: float | None = None
    air_util_tx: float | None = None
    uptime_s: int | None = None
    metrics_ts: float | None = None
    last_snr: float | None = None
    last_rssi: int | None = None
    last_hops: int | None = None
    last_gateway: str | None = None
    heard_via_mqtt_only: int = 0
    hidden: int = 0
    is_fixed: int = 0
    note: str | None = None
    updated_at: float = 0.0
    # No persistidos en `nodes`
    env: dict[str, Any] | None = None
    stored_pos: tuple[float, float, float] | None = None  # (ts, lat, lon) última guardada
    is_gateway: bool = False  # pasan paquetes por él (MQTT/USB/TCP); se recalcula al recibir

    @classmethod
    def new(cls, num: int, now: float) -> NodeRecord:
        return cls(num=num, id=node_id(num), first_seen=now, last_heard=now, updated_at=now)

    def db_row(self) -> dict[str, Any]:
        row = {f.name: getattr(self, f.name) for f in fields(self) if f.name not in NOT_STORED}
        return row

    @property
    def is_infra(self) -> bool:
        # Un gateway es infraestructura aunque su rol sea de cliente (p. ej. CLIENT_BASE).
        return self.role in INFRA_ROLES or self.is_gateway

    def public(self) -> dict[str, Any]:
        battery = self.battery_level
        powered = battery is not None and battery > 100
        return {
            "id": self.id,
            "short_name": self.short_name,
            "long_name": self.long_name,
            "role": self.role,
            "hw_model": self.hw_model,
            "lat": self.lat,
            "lon": self.lon,
            "alt": self.alt,
            "precision_m": precision_meters(self.precision_bits),
            "battery": min(battery, 101) if battery is not None else None,
            "powered": powered,
            "voltage": self.voltage,
            "channel_utilization": self.channel_utilization,
            "air_util_tx": self.air_util_tx,
            "uptime_s": self.uptime_s,
            "last_heard": self.last_heard,
            "first_seen": self.first_seen,
            "hops": self.last_hops,
            "snr": self.last_snr,
            "rssi": self.last_rssi,
            "is_infra": self.is_infra,
            "is_fixed": bool(self.is_fixed),
            "is_gateway": self.is_gateway,
            "env": self.env,
        }

    def admin(self) -> dict[str, Any]:
        out = self.public()
        out.update(
            {
                "num": self.num,
                "hidden": bool(self.hidden),
                "note": self.note,
                "firmware_version": self.firmware_version,
                "region": self.region,
                "modem_preset": self.modem_preset,
                "is_licensed": bool(self.is_licensed),
                "has_public_key": self.public_key is not None,
                "last_gateway": self.last_gateway,
                "heard_via_mqtt_only": bool(self.heard_via_mqtt_only),
                "position_ts": self.position_ts,
                "metrics_ts": self.metrics_ts,
                "precision_bits": self.precision_bits,
            }
        )
        return out


@dataclass(slots=True)
class ChannelRow:
    id: int
    name: str
    key_ref: str | None
    is_public: bool
    hash: int | None = None
    key: ChannelKey | None = None

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "is_public": self.is_public,
            "hash": self.hash,
            "has_key": self.key_ref is not None,
        }


@dataclass(slots=True)
class GatewayInfo:
    id: str
    last_seen: float
    connectors: set[str] = field(default_factory=set)
    firmware_version: str | None = None
    region: str | None = None
    modem_preset: str | None = None
    num_online_local_nodes: int | None = None
    has_default_channel: bool | None = None
    local_stats: dict[str, Any] | None = None
    local_stats_ts: float | None = None
    packets: int = 0

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["connectors"] = sorted(self.connectors)
        return d


class MeshState:
    def __init__(self) -> None:
        self.nodes: dict[int, NodeRecord] = {}
        self.channels: list[ChannelRow] = []
        self.gateways: dict[str, GatewayInfo] = {}
        self.settings: dict[str, Any] = {}
        self.thresholds = dict(DEFAULT_THRESHOLDS)
        # métricas
        self.started_at = time.time()
        self.last_packet_at: float | None = None
        self.packets_total = 0
        self.duplicates_total = 0
        self.invalid_total = 0
        self.hidden_dropped = 0
        self.local_packets = 0  # generados por la placa solo para su cliente USB/TCP
        self.flood_dropped = 0
        self.undecryptable = 0
        self.decode_errors = 0
        self.routing_errors: Counter[str] = Counter()
        self._minute_counts: deque[tuple[int, int]] = deque(maxlen=60 * 24)  # (minuto, paquetes)
        self._portnum_hour: deque[tuple[float, str]] = deque(maxlen=20_000)
        self.by_connector: Counter[str] = Counter()

    # ---------------------------------------------------------------- carga inicial

    def load_from_db(self, conn: Connection, secrets_get: Any) -> None:
        cols = [f.name for f in fields(NodeRecord) if f.name not in NOT_STORED]
        query = text(f"SELECT {', '.join(cols)} FROM nodes")  # noqa: S608 - columnas propias
        rows = conn.execute(query).mappings().all()
        self.nodes = {}
        for r in rows:
            rec = NodeRecord(**{k: r[k] for k in cols})
            self.nodes[rec.num] = rec
        # Tras un reinicio, el último paquete es el último que se oyó (no "sin paquetes todavía").
        heard = [rec.last_heard for rec in self.nodes.values() if rec.last_heard]
        self.last_packet_at = max(heard) if heard else None
        # Gateways conocidos: los que figuran como último gateway de algún nodo (se completa
        # con el tráfico que llegue después).
        gateway_ids = {rec.last_gateway for rec in self.nodes.values() if rec.last_gateway}
        for rec in self.nodes.values():
            rec.is_gateway = rec.id in gateway_ids
        # última telemetría ambiental por nodo (para `env`)
        env_rows = (
            conn.execute(
                text(
                    "SELECT e.* FROM telemetry_environment e JOIN ("
                    " SELECT node_num, MAX(ts) AS ts FROM telemetry_environment GROUP BY node_num"
                    ") m ON e.node_num = m.node_num AND e.ts = m.ts"
                )
            )
            .mappings()
            .all()
        )
        for r in env_rows:
            env_rec = self.nodes.get(r["node_num"])
            if env_rec is not None:
                env_rec.env = env_public(dict(r), r["ts"])
        pos_rows = conn.execute(
            text(
                "SELECT p.node_num, p.ts, p.lat, p.lon FROM positions p JOIN ("
                " SELECT node_num, MAX(ts) AS ts FROM positions GROUP BY node_num"
                ") m ON p.node_num = m.node_num AND p.ts = m.ts"
            )
        ).all()
        for node_num, ts, lat, lon in pos_rows:
            pos_rec = self.nodes.get(node_num)
            if pos_rec is not None:
                pos_rec.stored_pos = (ts, lat, lon)
        self.load_channels(conn, secrets_get)
        settings_rows = conn.execute(text("SELECT key, value FROM settings")).all()
        self.settings = {}
        for key, value in settings_rows:
            try:
                self.settings[key] = orjson.loads(value)
            except orjson.JSONDecodeError:
                self.settings[key] = value
        self.apply_thresholds()

    def load_channels(self, conn: Connection, secrets_get: Any) -> None:
        rows = conn.execute(
            text("SELECT id, name, key_ref, is_public FROM channels ORDER BY id")
        ).all()
        self.channels = []
        for cid, name, key_ref, is_public in rows:
            row = ChannelRow(id=cid, name=name, key_ref=key_ref, is_public=bool(is_public))
            psk_text = secrets_get(key_ref) if key_ref else None
            if psk_text is not None:
                try:
                    row.key = ChannelKey.from_psk(name, decode_psk(psk_text), bool(is_public))
                    row.hash = row.key.hash
                except ValueError:
                    row.key = None
            self.channels.append(row)

    def apply_thresholds(self) -> None:
        t = self.settings.get("status_thresholds")
        if isinstance(t, dict):
            for k in DEFAULT_THRESHOLDS:
                if isinstance(t.get(k), int | float) and t[k] > 0:
                    self.thresholds[k] = int(t[k])

    # ---------------------------------------------------------------- canales

    def channel_keys(self) -> list[ChannelKey]:
        return [c.key for c in self.channels if c.key is not None]

    def channel_is_public(self, name: str | None) -> bool:
        if not name:
            return False
        return any(c.is_public and c.name == name for c in self.channels)

    def public_channel_names(self) -> list[str]:
        return [c.name for c in self.channels if c.is_public]

    # ---------------------------------------------------------------- nodos

    def public_nodes(self) -> list[dict[str, Any]]:
        return [n.public() for n in self.nodes.values() if not n.hidden]

    def is_hidden(self, num: int) -> bool:
        rec = self.nodes.get(num)
        return rec is not None and bool(rec.hidden)

    def display_name(self, num: int) -> str | None:
        rec = self.nodes.get(num)
        if rec is None:
            return None
        return rec.long_name or rec.short_name

    def status_of(self, rec: NodeRecord, now: float) -> str:
        age = now - rec.last_heard
        if age < self.thresholds["active_s"]:
            return "active"
        if age < self.thresholds["recent_s"]:
            return "recent"
        if age < self.thresholds["late_s"]:
            return "late"
        return "inactive"

    # ---------------------------------------------------------------- métricas

    def count_packet(self, portnum: str | None, connector_id: str, now: float) -> None:
        self.packets_total += 1
        self.last_packet_at = now
        self.by_connector[connector_id] += 1
        minute = int(now // 60)
        if self._minute_counts and self._minute_counts[-1][0] == minute:
            m, c = self._minute_counts[-1]
            self._minute_counts[-1] = (m, c + 1)
        else:
            self._minute_counts.append((minute, 1))
        self._portnum_hour.append((now, portnum or "ENCRYPTED"))

    def packets_per_minute(
        self, minutes: int = 60, now: float | None = None
    ) -> list[dict[str, int]]:
        now_min = int((now or time.time()) // 60)
        counts = dict(self._minute_counts)
        return [
            {"t": (now_min - i) * 60, "n": counts.get(now_min - i, 0)}
            for i in range(minutes - 1, -1, -1)
        ]

    def packets_last_hour(self, now: float | None = None) -> int:
        cutoff = (now or time.time()) - 3600
        return sum(1 for ts, _ in self._portnum_hour if ts >= cutoff)

    def portnums_last_hour(self, now: float | None = None) -> dict[str, int]:
        cutoff = (now or time.time()) - 3600
        return dict(Counter(p for ts, p in self._portnum_hour if ts >= cutoff))

    def summary(self, now: float | None = None) -> dict[str, Any]:
        now = now or time.time()
        counts = Counter(self.status_of(n, now) for n in self.nodes.values() if not n.hidden)
        utils = [
            n.channel_utilization
            for n in self.nodes.values()
            if not n.hidden
            and n.channel_utilization is not None
            and n.metrics_ts
            and now - n.metrics_ts < 7200
        ]
        new_24h = sum(1 for n in self.nodes.values() if not n.hidden and now - n.first_seen < 86400)
        return {
            "nodes": {
                "total": sum(counts.values()),
                "active": counts.get("active", 0),
                "recent": counts.get("recent", 0),
                "late": counts.get("late", 0),
                "inactive": counts.get("inactive", 0),
                "with_position": sum(
                    1 for n in self.nodes.values() if not n.hidden and n.lat is not None
                ),
            },
            "packets_last_hour": self.packets_last_hour(now),
            "channel_utilization_avg": round(sum(utils) / len(utils), 2) if utils else None,
            "new_nodes_24h": new_24h,
            "last_packet_at": self.last_packet_at,
            "ts": now,
        }

    def counters(self) -> dict[str, Any]:
        return {
            "packets_total": self.packets_total,
            "duplicates_total": self.duplicates_total,
            "invalid_total": self.invalid_total,
            "hidden_dropped": self.hidden_dropped,
            "local_packets": self.local_packets,
            "flood_dropped": self.flood_dropped,
            "undecryptable": self.undecryptable,
            "decode_errors": self.decode_errors,
            "routing_errors": dict(self.routing_errors),
            "by_connector": dict(self.by_connector),
            "portnums_last_hour": self.portnums_last_hour(),
        }


def env_public(values: dict[str, Any], ts: float) -> dict[str, Any] | None:
    env = {
        "temperature": values.get("temperature"),
        "humidity": values.get("relative_humidity"),
        "pressure": values.get("barometric_pressure"),
        "lux": values.get("lux"),
        "ts": ts,
    }
    if all(env[k] is None for k in ("temperature", "humidity", "pressure", "lux")):
        return None
    return env
