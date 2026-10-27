"""Configuración de la placa como datos para el panel (sección 18.4, ADR 0015).

Cada sección de `LocalConfig` y `LocalModuleConfig` se describe desde los descriptores de
protobuf (campos, tipos, opciones de los enums), así el panel no se desactualiza cuando el
firmware agrega campos. Los cambios se validan y se aplican sobre una copia: los peligrosos
(pueden dejar la placa inalcanzable o fuera de su red) piden confirmación aparte.
"""

from __future__ import annotations

import base64
import os
from typing import Any

from google.protobuf.descriptor import FieldDescriptor as FD
from google.protobuf.message import Message

MASK = "********"

# Secciones que la librería sabe escribir (`Node.writeConfig`); las demás, solo lectura.
WRITABLE = frozenset(
    {
        "device",
        "position",
        "power",
        "network",
        "display",
        "lora",
        "bluetooth",
        "security",
        "mqtt",
        "serial",
        "external_notification",
        "store_forward",
        "range_test",
        "telemetry",
        "canned_message",
        "audio",
        "remote_hardware",
        "neighbor_info",
        "detection_sensor",
        "ambient_lighting",
        "paxcounter",
        "traffic_management",
    }
)

# Secciones enteras peligrosas: red (WiFi), Bluetooth, seguridad (claves de administración) y el
# módulo serie (reusa el puerto USB y corta la conexión con la Pi).
DANGER_SECTIONS = frozenset({"network", "bluetooth", "security", "serial"})
DANGER_FIELDS: dict[str, frozenset[str]] = {
    "device": frozenset({"role", "serial_enabled", "rebroadcast_mode", "is_managed"}),
    "lora": frozenset(
        {
            "region",
            "modem_preset",
            "use_preset",
            "bandwidth",
            "spread_factor",
            "coding_rate",
            "frequency_offset",
            "channel_num",
            "override_frequency",
            "tx_enabled",
            "override_duty_cycle",
            "ignore_incoming",
            "pa_fan_disabled",
        }
    ),
    # Con WiFi encendido, el ahorro de energía lo apaga: la placa queda fuera de la Pi.
    "power": frozenset({"is_power_saving", "on_battery_shutdown_after_secs"}),
    "mqtt": frozenset(
        {
            "enabled",
            "address",
            "username",
            "password",
            "root",
            "encryption_enabled",
            "proxy_to_client_enabled",
            "tls_enabled",
            "json_enabled",
        }
    ),
}
# Secretos: se muestran enmascarados; los de texto se pueden reemplazar (escritura sola).
SECRETS: dict[str, frozenset[str]] = {
    "network": frozenset({"wifi_psk"}),
    "mqtt": frozenset({"password"}),
    "bluetooth": frozenset({"fixed_pin"}),
    "security": frozenset({"private_key", "public_key", "admin_key"}),
}

INT_TYPES = {
    FD.TYPE_INT32: (-(2**31), 2**31 - 1),
    FD.TYPE_SINT32: (-(2**31), 2**31 - 1),
    FD.TYPE_SFIXED32: (-(2**31), 2**31 - 1),
    FD.TYPE_UINT32: (0, 2**32 - 1),
    FD.TYPE_FIXED32: (0, 2**32 - 1),
    FD.TYPE_INT64: (-(2**63), 2**63 - 1),
    FD.TYPE_SINT64: (-(2**63), 2**63 - 1),
    FD.TYPE_SFIXED64: (-(2**63), 2**63 - 1),
    FD.TYPE_UINT64: (0, 2**64 - 1),
    FD.TYPE_FIXED64: (0, 2**64 - 1),
}
MAX_STRING = 256


def is_repeated(f: FD) -> bool:
    flag = getattr(f, "is_repeated", None)
    if isinstance(flag, bool):
        return flag
    return bool(f.label == FD.LABEL_REPEATED)


def is_danger(section: str, name: str) -> bool:
    return section in DANGER_SECTIONS or name in DANGER_FIELDS.get(section, frozenset())


def is_secret(section: str, name: str) -> bool:
    return name in SECRETS.get(section, frozenset())


def _value(f: FD, value: Any, section: str) -> Any:
    if is_secret(section, f.name):
        if is_repeated(f):  # security.admin_key: hasta tres claves
            return [MASK if v else "" for v in value]
        if isinstance(value, bytes):
            return MASK if value else ""
        return MASK if value else value
    if f.type == FD.TYPE_ENUM:
        if is_repeated(f):
            return [_enum_name(f, v) for v in value]
        return _enum_name(f, value)
    if f.type == FD.TYPE_BYTES:
        if is_repeated(f):
            return [MASK if v else "" for v in value]
        return MASK if value else ""
    if is_repeated(f):
        return list(value)
    return value


def _enum_name(f: FD, number: int) -> str | int:
    v = f.enum_type.values_by_number.get(number)
    return v.name if v is not None else number


def describe_message(msg: Message, section: str, depth: int = 0) -> list[dict[str, Any]]:
    """Campos de una sección: tipo, valor actual, opciones, si es peligroso o secreto."""
    out: list[dict[str, Any]] = []
    for f in msg.DESCRIPTOR.fields:
        item: dict[str, Any] = {
            "name": f.name,
            "danger": is_danger(section, f.name),
            "secret": is_secret(section, f.name),
            "readonly": False,
        }
        value = getattr(msg, f.name)
        if f.type == FD.TYPE_MESSAGE and not is_repeated(f):
            item["type"] = "object"
            if depth >= 1:
                item.update(readonly=True, value=None, fields=[])
            else:
                item["fields"] = describe_message(value, section, depth + 1)
            out.append(item)
            continue
        if is_repeated(f):
            item.update(type="list", readonly=True)
        elif f.type == FD.TYPE_BOOL:
            item["type"] = "bool"
        elif f.type == FD.TYPE_ENUM:
            item.update(type="enum", options=[v.name for v in f.enum_type.values])
        elif f.type == FD.TYPE_STRING:
            item.update(type="string", max_length=MAX_STRING)
        elif f.type in (FD.TYPE_FLOAT, FD.TYPE_DOUBLE):
            item["type"] = "float"
        elif f.type in INT_TYPES:
            lo, hi = INT_TYPES[f.type]
            item.update(type="int", min=lo, max=hi)
        else:  # bytes y otros
            item.update(type="bytes", readonly=True)
        if item["secret"] and item["type"] == "bytes":
            item["readonly"] = True
        item["value"] = _value(f, value, section)
        out.append(item)
    return out


def _convert(f: FD, value: Any, path: str) -> Any:
    if f.type == FD.TYPE_BOOL:
        if not isinstance(value, bool):
            raise ValueError(f"{path}: se espera verdadero o falso")
        return value
    if f.type == FD.TYPE_ENUM:
        if isinstance(value, str):
            v = f.enum_type.values_by_name.get(value)
            if v is None:
                raise ValueError(f"{path}: opción no válida ({value})")
            return v.number
        if isinstance(value, int) and not isinstance(value, bool):
            if value not in f.enum_type.values_by_number:
                raise ValueError(f"{path}: opción no válida ({value})")
            return value
        raise ValueError(f"{path}: opción no válida")
    if f.type == FD.TYPE_STRING:
        if not isinstance(value, str) or len(value) > MAX_STRING:
            raise ValueError(f"{path}: texto no válido")
        return value
    if f.type in (FD.TYPE_FLOAT, FD.TYPE_DOUBLE):
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError(f"{path}: se espera un número")
        return float(value)
    if f.type in INT_TYPES:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{path}: se espera un número entero")
        lo, hi = INT_TYPES[f.type]
        if not lo <= value <= hi:
            raise ValueError(f"{path}: fuera de rango ({lo} a {hi})")
        return value
    raise ValueError(f"{path}: no se puede editar desde el panel")


def apply_values(
    msg: Message, section: str, values: dict[str, Any], prefix: str = ""
) -> tuple[list[str], list[str]]:
    """Aplica `values` sobre `msg` (usar una copia). Devuelve (cambiados, peligrosos)."""
    changed: list[str] = []
    danger: list[str] = []
    fields = msg.DESCRIPTOR.fields_by_name
    for name, value in values.items():
        f = fields.get(name)
        path = f"{prefix}{name}"
        if f is None:
            raise ValueError(f"campo desconocido: {path}")
        if is_repeated(f):
            raise ValueError(f"{path}: no se puede editar desde el panel")
        if f.type == FD.TYPE_MESSAGE:
            if not isinstance(value, dict):
                raise ValueError(f"{path}: se espera un objeto")
            if prefix:
                raise ValueError(f"{path}: no se puede editar desde el panel")
            c, d = apply_values(getattr(msg, name), section, value, f"{path}.")
            changed += c
            danger += d if not is_danger(section, name) else c
            continue
        if is_secret(section, name):
            if f.type == FD.TYPE_BYTES:
                raise ValueError(f"{path}: no se puede editar desde el panel")
            if value == MASK:
                continue  # sin cambios
        if f.type == FD.TYPE_BYTES:
            raise ValueError(f"{path}: no se puede editar desde el panel")
        new = _convert(f, value, path)
        if new != getattr(msg, name):
            setattr(msg, name, new)
            changed.append(path)
            if is_danger(section, name):
                danger.append(path)
    return changed, danger


# --------------------------------------------------------------------------- canales

CHANNEL_NAME_MAX = 11  # bytes (límite del firmware)


def psk_kind(psk: bytes) -> str:
    if not psk:
        return "none"
    if len(psk) == 1:
        return "default" if psk == b"\x01" else "simple"
    return "secret"


def describe_channels(channels: list[Any], default_name: str) -> list[dict[str, Any]]:
    out = []
    for ch in channels:
        role = ch.DESCRIPTOR.fields_by_name["role"].enum_type.values_by_number[ch.role].name
        s = ch.settings
        out.append(
            {
                "index": ch.index,
                "role": role,
                "name": s.name or (default_name if role == "PRIMARY" else ""),
                "custom_name": bool(s.name),
                "psk": psk_kind(bytes(s.psk)),
                "uplink": s.uplink_enabled,
                "downlink": s.downlink_enabled,
                "position_precision": s.module_settings.position_precision,
                "muted": s.module_settings.is_muted,
            }
        )
    return out


def new_psk(spec: str) -> bytes:
    """`default` (clave pública conocida), `none`, `random` (32 bytes) o base64 propio."""
    if spec == "default":
        return b"\x01"
    if spec == "none":
        return b""
    if spec == "random":
        return os.urandom(32)
    try:
        raw = base64.b64decode(spec, validate=True)
    except ValueError:
        raise ValueError("clave no válida: usar default, none, random o base64") from None
    if len(raw) not in (1, 16, 32):
        raise ValueError("la clave tiene que tener 1, 16 o 32 bytes")
    return raw


def apply_channel(ch: Any, values: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Cambios de un canal (sobre una copia). Devuelve (cambiados, peligrosos)."""
    changed: list[str] = []
    danger: list[str] = []
    s = ch.settings
    is_primary = ch.role == 1  # PRIMARY
    if "name" in values:
        name = values["name"]
        if not isinstance(name, str) or len(name.encode()) > CHANNEL_NAME_MAX:
            raise ValueError(f"nombre del canal: hasta {CHANNEL_NAME_MAX} caracteres")
        if name != s.name:
            s.name = name
            changed.append("name")
            danger.append("name")  # los demás nodos del canal dejan de entenderse con este
    if "psk" in values and values["psk"] not in (None, "", "keep"):
        psk = new_psk(str(values["psk"]))
        if psk != bytes(s.psk):
            s.psk = psk
            changed.append("psk")
            danger.append("psk")
    for key, attr in (("uplink", "uplink_enabled"), ("downlink", "downlink_enabled")):
        if key in values:
            if not isinstance(values[key], bool):
                raise ValueError(f"{key}: se espera verdadero o falso")
            if values[key] != getattr(s, attr):
                setattr(s, attr, values[key])
                changed.append(key)
                if key == "downlink":
                    danger.append(key)  # bajada por MQTT: vía de inyección (sección 22)
    if "position_precision" in values:
        p = values["position_precision"]
        if isinstance(p, bool) or not isinstance(p, int) or not 0 <= p <= 32:
            raise ValueError("precisión de posición: de 0 (no compartir) a 32 (exacta)")
        if p != s.module_settings.position_precision:
            s.module_settings.position_precision = p
            changed.append("position_precision")
    if "muted" in values:
        if not isinstance(values["muted"], bool):
            raise ValueError("muted: se espera verdadero o falso")
        if values["muted"] != s.module_settings.is_muted:
            s.module_settings.is_muted = values["muted"]
            changed.append("muted")
    if is_primary and "uplink" in changed:
        danger.append("uplink")  # el primario es el canal público que llega al sitio
    return changed, danger
