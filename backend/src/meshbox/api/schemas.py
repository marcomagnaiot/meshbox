"""Esquemas públicos (sección 12.2.1).

Un solo modelo por recurso, usado por la API, el SSE, la salida MQTT y los webhooks; el
frontend genera sus tipos desde el OpenAPI. Los campos sin dato van en `null`. Destino
broadcast: "^all".
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Out(BaseModel):
    model_config = ConfigDict(extra="ignore")


class EnvValues(_Out):
    temperature: float | None = None
    humidity: float | None = None
    pressure: float | None = None
    lux: float | None = None
    ts: float


class Node(_Out):
    id: str
    short_name: str | None
    long_name: str | None
    role: str
    hw_model: str | None
    lat: float | None
    lon: float | None
    alt: int | None
    precision_m: float | None
    battery: int | None = Field(description="0-100; 101 = alimentación externa")
    powered: bool
    voltage: float | None
    channel_utilization: float | None
    air_util_tx: float | None
    uptime_s: int | None
    last_heard: float
    first_seen: float
    hops: int | None
    snr: float | None
    rssi: int | None
    is_infra: bool
    is_fixed: bool
    is_gateway: bool = False
    env: EnvValues | None


class NodeDetail(Node):
    firmware_version: str | None = None
    region: str | None = None
    modem_preset: str | None = None
    position_ts: float | None = None
    metrics_ts: float | None = None


class NodeList(_Out):
    seq: int
    ts: float
    nodes: list[Node]


class Message(_Out):
    pk: int
    ts: float
    from_: str = Field(alias="from", serialization_alias="from")
    from_name: str | None
    channel: str | None
    text: str
    reply_id: int | None
    emoji: bool
    packet_id: int | None = None

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class Page(_Out):
    next: str | None = Field(None, description="cursor `ts:pk` para pedir la página siguiente")


class MessagePage(Page):
    messages: list[Message]


class Alert(_Out):
    id: int
    state: Literal["firing", "resolved"]
    severity: Literal["info", "warning", "critical"]
    kind: str
    node: str | None
    title: str
    body: str | None
    ts: float


class AlertPage(Page):
    alerts: list[Alert]


class Activity(_Out):
    portnum: str | None
    from_: str = Field(alias="from", serialization_alias="from")
    to: str
    hops: int | None
    snr: float | None
    gateway: str | None
    ts: float

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class Link(_Out):
    a: str
    b: str
    snr: float | None
    source: Literal["neighborinfo", "direct", "traceroute"]
    ts: float


class Traceroute(_Out):
    ts: float
    from_: str = Field(alias="from", serialization_alias="from")
    to: str
    route: list[str]
    snr_towards: list[float | None]
    route_back: list[str]
    snr_back: list[float | None]

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class Waypoint(_Out):
    id: int
    from_: str | None = Field(None, alias="from", serialization_alias="from")
    ts: float | None
    name: str | None
    description: str | None
    lat: float | None
    lon: float | None
    icon: int | None
    expire: float | None

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class Position(_Out):
    ts: float
    lat: float
    lon: float
    alt: int | None
    precision_m: float | None
    speed_kmh: float | None = None


class TelemetrySeries(_Out):
    kind: Literal["device", "environment", "power"]
    # raw: cada muestra; bucket: crudos agrupados de a `bucket_s`; hour y day: agregados
    resolution: Literal["raw", "bucket", "hour", "day"]
    bucket_s: int | None = None
    ts: list[float]
    series: dict[str, list[float | None]]
    min: dict[str, list[float | None]] | None = None
    max: dict[str, list[float | None]] | None = None


class StatsSummary(_Out):
    nodes: dict[str, int]
    packets_last_hour: int
    channel_utilization_avg: float | None
    new_nodes_24h: int
    last_packet_at: float | None
    ts: float


class TimeSeries(_Out):
    metric: str
    range: str
    ts: list[float]
    values: list[Any]


class Health(_Out):
    status: Literal["ok"]
    version: str


class MapLayers(_Out):
    dark: bool
    light: bool
    satellite: bool
    default: Literal["dark", "light", "satellite"]


class Thresholds(_Out):
    active_s: int
    recent_s: int
    late_s: int


class Site(_Out):
    name: str
    description: str
    logo_url: str | None
    accent: str
    center: list[float] = Field(description="[lat, lon]")
    zoom: float
    bounds: list[float] | None = Field(None, description="[oeste, sur, este, norte]")
    layers: MapLayers
    has_tiles: bool
    thresholds: Thresholds
    features: dict[str, bool]
    notice: list[dict[str, Any]] = Field(
        default_factory=list, description="aviso de privacidad como bloques (sin HTML)"
    )
    public_channels: list[str]
    timezone: str
    language: str
    languages: list[str]
    version: str
    attributions: list[dict[str, str]]
    plugin_layers: list[dict[str, Any]] = Field(default_factory=list)
    server: Literal["public", "lan", "remote"] = Field(
        "public", description="servidor que respondió: el remoto es el hostname de administración"
    )


class PushSubscriptionIn(BaseModel):
    endpoint: str = Field(max_length=1000, pattern=r"^https://")
    keys: dict[str, str]


class Problem(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
