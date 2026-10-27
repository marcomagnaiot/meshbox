"""Decodificación del contenido según `portnum` (sección 10.3).

Siempre por nombre del enum `PortNum`, nunca por número. Cualquier error queda en
`Decoded.error` y el paquete sigue con `decoded_ok = 0`: el pipeline nunca se detiene.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message
from meshtastic.protobuf import config_pb2, mesh_pb2, mqtt_pb2, portnums_pb2, telemetry_pb2

PortNum = portnums_pb2.PortNum
Role = config_pb2.Config.DeviceConfig.Role

MAX_LONG_NAME = 40
MAX_SHORT_NAME = 5
MAX_TEXT = 250
UNKNOWN_SNR = -128  # valor de SNR desconocido en traceroute (sin multiplicar)


def portnum_name(value: int) -> str:
    try:
        return str(PortNum.Name(value))
    except ValueError:
        return f"PORT_{value}"


def enum_name(enum: Any, value: int, default: str | None = None) -> str | None:
    try:
        return str(enum.Name(value))
    except ValueError:
        return default


def hw_model_name(value: int) -> str | None:
    return enum_name(mesh_pb2.HardwareModel, value, f"HW_{value}")


def role_name(value: int) -> str:
    return enum_name(Role, value, "CLIENT") or "CLIENT"


INFRA_ROLES = frozenset({"ROUTER", "ROUTER_LATE", "REPEATER", "ROUTER_CLIENT"})


@dataclass(slots=True)
class Decoded:
    portnum: str
    kind: str  # text | position | user | telemetry | neighborinfo | traceroute | routing |
    # waypoint | map_report | range_test | raw
    obj: Any = None
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None


def _parse(cls: type[Message], payload: bytes) -> Message:
    msg = cls()
    msg.ParseFromString(payload)
    return msg


def decode_text(payload: bytes) -> str:
    return payload.decode("utf-8", errors="replace")


def decode_data(data: mesh_pb2.Data) -> Decoded:
    name = portnum_name(data.portnum)
    payload = bytes(data.payload)
    try:
        match name:
            case "TEXT_MESSAGE_APP" | "ALERT_APP" | "RANGE_TEST_APP" | "DETECTION_SENSOR_APP":
                kind = "range_test" if name == "RANGE_TEST_APP" else "text"
                if name == "DETECTION_SENSOR_APP":
                    kind = "raw"
                return Decoded(name, kind, decode_text(payload))
            case "POSITION_APP":
                return Decoded(name, "position", _parse(mesh_pb2.Position, payload))
            case "NODEINFO_APP":
                return Decoded(name, "user", _parse(mesh_pb2.User, payload))
            case "TELEMETRY_APP":
                tel = _parse(telemetry_pb2.Telemetry, payload)
                return Decoded(name, "telemetry", tel, extra={"variant": tel.WhichOneof("variant")})
            case "NEIGHBORINFO_APP":
                return Decoded(name, "neighborinfo", _parse(mesh_pb2.NeighborInfo, payload))
            case "TRACEROUTE_APP":
                return Decoded(name, "traceroute", _parse(mesh_pb2.RouteDiscovery, payload))
            case "ROUTING_APP":
                return Decoded(name, "routing", _parse(mesh_pb2.Routing, payload))
            case "WAYPOINT_APP":
                return Decoded(name, "waypoint", _parse(mesh_pb2.Waypoint, payload))
            case "MAP_REPORT_APP":
                return Decoded(name, "map_report", _parse(mqtt_pb2.MapReport, payload))
            case _:
                return Decoded(name, "raw", payload)
    except Exception as e:
        return Decoded(name, "raw", payload, error=f"{type(e).__name__}: {e}")


# --------------------------------------------------------------------------- utilidades


def position_latlon(pos: mesh_pb2.Position) -> tuple[float, float] | None:
    if not pos.HasField("latitude_i") or not pos.HasField("longitude_i"):
        return None
    lat = pos.latitude_i * 1e-7
    lon = pos.longitude_i * 1e-7
    if pos.latitude_i == 0 and pos.longitude_i == 0:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def precision_meters(bits: int | None) -> float | None:
    """Radio aproximado de la posición según `precision_bits` (tabla oficial de la app:
    10 → 23,3 km, 11 → 11,7 km, ..., 19 → 45 m). 0 o 32 = precisión completa (None)."""
    if bits is None or bits <= 0 or bits >= 32:
        return None
    if bits < 10:
        return float(23_300.0 * (2 ** (10 - bits)))
    return float(round(23_300.0 / (2 ** (bits - 10)), 1))


def device_metrics_values(m: telemetry_pb2.DeviceMetrics) -> dict[str, float | int | None]:
    def opt(name: str) -> Any:
        return getattr(m, name) if m.HasField(name) else None

    return {
        "battery_level": opt("battery_level"),
        "voltage": _round(opt("voltage"), 3),
        "channel_utilization": _round(opt("channel_utilization"), 2),
        "air_util_tx": _round(opt("air_util_tx"), 3),
        "uptime_s": opt("uptime_seconds"),
    }


ENV_FIELDS = (
    ("temperature", "temperature"),
    ("relative_humidity", "relative_humidity"),
    ("barometric_pressure", "barometric_pressure"),
    ("gas_resistance", "gas_resistance"),
    ("iaq", "iaq"),
    ("lux", "lux"),
    ("wind_speed", "wind_speed"),
    ("wind_gust", "wind_gust"),
    ("wind_direction", "wind_direction"),
    ("rainfall_1h", "rainfall_1h"),
    ("rainfall_24h", "rainfall_24h"),
)


def environment_values(m: telemetry_pb2.EnvironmentMetrics) -> dict[str, float | int | None]:
    out: dict[str, float | int | None] = {}
    for col, attr in ENV_FIELDS:
        out[col] = _round(getattr(m, attr), 3) if m.HasField(attr) else None
    return out


POWER_FIELDS = tuple(f"ch{i}_{k}" for i in (1, 2, 3) for k in ("voltage", "current"))


def power_values(m: telemetry_pb2.PowerMetrics) -> dict[str, float | int | None]:
    return {f: (_round(getattr(m, f), 3) if m.HasField(f) else None) for f in POWER_FIELDS}


def _round(v: Any, nd: int) -> Any:
    if isinstance(v, float):
        return round(v, nd)
    return v


def traceroute_snrs(values: list[int]) -> list[float | None]:
    """Los SNR de traceroute vienen multiplicados por 4; -128 es desconocido."""
    return [None if v == UNKNOWN_SNR else v / 4 for v in values]


def message_to_dict(msg: Message) -> dict[str, Any]:
    out: dict[str, Any] = MessageToDict(
        msg, preserving_proto_field_name=True, always_print_fields_with_no_presence=False
    )
    return out


def decoded_to_json(dec: Decoded) -> Any:
    """Representación JSON del contenido (detalle de paquetes en el panel)."""
    if dec.obj is None:
        return None
    if isinstance(dec.obj, str):
        return dec.obj
    if isinstance(dec.obj, bytes):
        return {"hex": dec.obj.hex()}
    if isinstance(dec.obj, Message):
        return message_to_dict(dec.obj)
    return str(dec.obj)


def clip(text: str | None, n: int) -> str | None:
    if text is None:
        return None
    text = text.replace("\x00", "")
    return text[:n]
