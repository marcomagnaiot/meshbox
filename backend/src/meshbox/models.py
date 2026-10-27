"""Paquetes crudos, estado de conectores y eventos del bus (sección 5.4)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from meshtastic.protobuf import mesh_pb2

BROADCAST = 0xFFFFFFFF
Source = Literal["mqtt", "serial", "tcp", "replay"]
ConnectorState = Literal["stopped", "connecting", "connected", "degraded", "error"]


def node_id(num: int) -> str:
    return f"!{num & 0xFFFFFFFF:08x}"


def node_num(node: str) -> int:
    """`!xxxxxxxx` (o hexadecimal suelto) → número. ValueError si no es válido."""
    s = node[1:] if node.startswith("!") else node
    if not (1 <= len(s) <= 8) or any(c not in "0123456789abcdefABCDEF" for c in s):
        raise ValueError(f"id de nodo no válido: {node!r}")
    return int(s, 16)


@dataclass(frozen=True, slots=True)
class RawPacket:
    source: Source
    connector_id: str
    gateway_id: str | None  # "!xxxxxxxx" del nodo que lo recibió por radio
    channel_id: str | None  # nombre del canal (MQTT: ServiceEnvelope.channel_id)
    rx_time: float  # hora del servidor al recibir
    packet: mesh_pb2.MeshPacket


@dataclass(slots=True)
class ConnectorStatus:
    id: str
    kind: str
    state: ConnectorState = "stopped"
    since: float = field(default_factory=time.time)
    last_packet_at: float | None = None
    packets: int = 0
    invalid: int = 0
    errors: int = 0
    last_error: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "state": self.state,
            "since": self.since,
            "last_packet_at": self.last_packet_at,
            "packets": self.packets,
            "invalid": self.invalid,
            "errors": self.errors,
            "last_error": self.last_error,
            "detail": self.detail,
        }


# --------------------------------------------------------------------------- eventos


@dataclass(frozen=True, slots=True, kw_only=True)
class Event:
    """Evento inmutable. `seq` y `ts` los asigna el bus al publicar."""

    type: ClassVar[str] = "event"
    seq: int = 0
    ts: float = 0.0


@dataclass(frozen=True, slots=True, kw_only=True)
class RawPacketReceived(Event):
    type: ClassVar[str] = "raw_packet"
    raw: RawPacket


@dataclass(frozen=True, slots=True, kw_only=True)
class PacketProcessed(Event):
    type: ClassVar[str] = "packet"
    pk: int
    portnum: str | None
    from_num: int
    to_num: int
    packet_id: int
    channel: str | None
    hops: int | None
    snr: float | None
    rssi: int | None
    gateway: str | None
    source: str
    connector_id: str
    is_public: bool
    encrypted: bool
    decoded_ok: bool
    duplicate: bool
    via_mqtt: bool
    rx_time: float


@dataclass(frozen=True, slots=True, kw_only=True)
class NodeUpserted(Event):
    type: ClassVar[str] = "node"
    node: dict[str, Any]  # nodo público completo
    changed: tuple[str, ...] = ()
    is_new: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class NodeHidden(Event):
    type: ClassVar[str] = "node_remove"
    node_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PositionAdded(Event):
    type: ClassVar[str] = "position"
    node_id: str
    lat: float
    lon: float
    alt: int | None
    precision_m: float | None
    pos_ts: float


@dataclass(frozen=True, slots=True, kw_only=True)
class TelemetryAdded(Event):
    type: ClassVar[str] = "telemetry"
    node_id: str
    kind: Literal["device", "environment", "power"]
    values: dict[str, float | int | None]
    tel_ts: float


@dataclass(frozen=True, slots=True, kw_only=True)
class MessageAdded(Event):
    type: ClassVar[str] = "message"
    message: dict[str, Any]  # mensaje público
    is_alert: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class MessageModerated(Event):
    type: ClassVar[str] = "message_moderated"
    pk: int
    hidden: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class LinkObserved(Event):
    type: ClassVar[str] = "link"
    a: str
    b: str
    snr: float | None
    source: Literal["neighborinfo", "direct", "traceroute"]
    link_ts: float


@dataclass(frozen=True, slots=True, kw_only=True)
class TracerouteAdded(Event):
    type: ClassVar[str] = "traceroute"
    traceroute: dict[str, Any]


@dataclass(frozen=True, slots=True, kw_only=True)
class WaypointChanged(Event):
    type: ClassVar[str] = "waypoint"
    waypoint: dict[str, Any]
    deleted: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class AlertFired(Event):
    type: ClassVar[str] = "alert"
    alert: dict[str, Any]  # público: id, state, severity, kind, node, title, body, ts
    is_public: bool
    rule_id: int | None
    channels: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class AlertResolved(Event):
    type: ClassVar[str] = "alert"
    alert: dict[str, Any]
    is_public: bool
    rule_id: int | None
    channels: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class ConnectorStatusChanged(Event):
    type: ClassVar[str] = "connector"
    status: dict[str, Any]


@dataclass(frozen=True, slots=True, kw_only=True)
class SystemStatus(Event):
    type: ClassVar[str] = "system"
    metrics: dict[str, Any]


@dataclass(frozen=True, slots=True, kw_only=True)
class StatsUpdated(Event):
    type: ClassVar[str] = "stats"
    summary: dict[str, Any]


@dataclass(frozen=True, slots=True, kw_only=True)
class Diagnostic(Event):
    """Avisos internos para el panel: inundación de un nodo, cola llena, etc."""

    type: ClassVar[str] = "diagnostic"
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True, kw_only=True)
class LogEmitted(Event):
    type: ClassVar[str] = "log"
    record: dict[str, Any]
