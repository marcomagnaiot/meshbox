"""Reglas de privacidad (sección 10.5).

Antes de decodificar: nodo oculto, canal no público, paquete dirigido.
Después: paquetes que entraron a la red por MQTT, precisión de posición, moderación
(la moderación se aplica al consultar: los mensajes ocultos no se publican).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from meshtastic.protobuf import mesh_pb2

from ..models import BROADCAST

TRANSPORT_MQTT = mesh_pb2.MeshPacket.TransportMechanism.TRANSPORT_MQTT

# Dirigidos que igual se procesan para enlaces (10.5)
DIRECTED_PROCESSED = frozenset({"TRACEROUTE_APP", "ROUTING_APP"})
# Siempre metadatos del propio gateway, sin contenido de usuarios
ALWAYS_PROCESSED = frozenset({"MAP_REPORT_APP"})


@dataclass(frozen=True, slots=True)
class PreDecision:
    header_only: bool  # se guarda solo el encabezado (sin `raw` ni contenido)
    process: bool  # se decodifica el contenido (para tablas, enlaces o estado)
    public: bool  # se publica (API pública, SSE, salida MQTT)
    reason: str


def pre_filter(
    *, to_num: int, portnum: str | None, channel_public: bool, decoded: bool
) -> PreDecision:
    if not decoded or portnum is None:
        return PreDecision(True, False, False, "undecoded")
    if portnum in ALWAYS_PROCESSED:
        return PreDecision(False, True, False, "map_report")
    if not channel_public:
        return PreDecision(True, False, False, "channel_not_public")
    if to_num != BROADCAST:
        if portnum in DIRECTED_PROCESSED:
            return PreDecision(True, True, False, "directed_links")
        return PreDecision(True, False, False, "directed")
    return PreDecision(False, True, True, "public")


def entered_via_mqtt(packet: mesh_pb2.MeshPacket) -> bool:
    """El paquete entró a la red de radio desde MQTT (otro gateway lo inyectó). ADR 0009."""
    return bool(packet.via_mqtt) or packet.transport_mechanism == TRANSPORT_MQTT


METERS_PER_DEG_LAT = 111_320.0


def degrade_position(lat: float, lon: float, meters: float) -> tuple[float, float]:
    """Ajusta la posición al centro de una grilla de `meters` (precisión degradada)."""
    step_lat = meters / METERS_PER_DEG_LAT
    glat = (math.floor(lat / step_lat) + 0.5) * step_lat
    # El paso en longitud usa la latitud del centro de la franja: así la grilla es la misma
    # para todos los puntos de esa franja y el ajuste es idempotente.
    cos_lat = max(math.cos(math.radians(glat)), 0.01)
    step_lon = meters / (METERS_PER_DEG_LAT * cos_lat)
    glon = (math.floor(lon / step_lon) + 0.5) * step_lon
    return round(glat, 6), round(glon, 6)


def bits_for_meters(meters: float) -> int:
    """`precision_bits` aproximado para un radio en metros (inversa de precision_meters)."""
    if meters <= 0:
        return 32
    bits = 10 + math.log2(23_300.0 / meters)
    return max(10, min(31, math.floor(bits + 1e-3)))  # tolera el redondeo de precision_meters


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))
