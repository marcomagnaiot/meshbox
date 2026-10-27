"""Tipos de regla y sus parámetros (sección 19.1)."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Severity = Literal["info", "warning", "critical"]
CHANNELS = ("webpush", "telegram", "webhook", "mqtt")
KINDS = (
    "keyword",
    "telemetry_threshold",
    "node_offline",
    "node_online",
    "new_node",
    "gateway_down",
    "system",
)


class _P(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Scope(_P):
    """Alcance: lista de nodos, todos los fijos, la infraestructura o todos."""

    mode: Literal["nodes", "fixed", "infra", "all"] = "fixed"
    nodes: list[str] = Field(default_factory=list)

    @field_validator("nodes")
    @classmethod
    def _ids(cls, v: list[str]) -> list[str]:
        for n in v:
            if not re.fullmatch(r"![0-9a-f]{8}", n):
                raise ValueError(f"id de nodo no válido: {n}")
        return v


class KeywordParams(_P):
    patterns: list[str] = Field(default_factory=lambda: [r"\bSOS\b"], max_length=20)
    regex: bool = True
    case_sensitive: bool = False
    include_bell: bool = True  # carácter campana \x07
    channels: list[str] = Field(
        default_factory=list, description="canales de radio; vacío = los públicos"
    )

    @field_validator("patterns")
    @classmethod
    def _compile(cls, v: list[str]) -> list[str]:
        for p in v:
            if len(p) > 200:
                raise ValueError("patrón demasiado largo")
            try:
                re.compile(p)
            except re.error as e:
                raise ValueError(f"expresión regular no válida: {p} ({e})") from e
        return v

    def matcher(self) -> re.Pattern[str]:
        parts = self.patterns if self.regex else [re.escape(p) for p in self.patterns]
        if self.include_bell:
            parts = [*parts, "\x07"]
        flags = 0 if self.case_sensitive else re.IGNORECASE
        return re.compile("|".join(f"(?:{p})" for p in parts) or "(?!x)x", flags)


class TelemetryThresholdParams(_P):
    scope: Scope = Field(default_factory=Scope)
    kind: Literal["device", "environment", "power"] = "device"
    metric: str = "battery_level"
    op: Literal["<", "<=", ">", ">="] = "<"
    value: float = 30
    duration_s: int = Field(1800, ge=0, le=7 * 86400)

    def test(self, v: float) -> bool:
        match self.op:
            case "<":
                return v < self.value
            case "<=":
                return v <= self.value
            case ">":
                return v > self.value
            case _:
                return v >= self.value


class NodeOfflineParams(_P):
    scope: Scope = Field(default_factory=Scope)
    hours: float = Field(6, gt=0, le=24 * 30)


class NodeOnlineParams(_P):
    scope: Scope = Field(default_factory=Scope)


class NewNodeParams(_P):
    pass


class GatewayDownParams(_P):
    connector: str | None = None  # None = cualquiera
    minutes: int = Field(30, ge=1, le=7 * 24 * 60)


class SystemParams(_P):
    cpu_pct: float | None = 90
    ram_pct: float | None = 92
    temp_c: float | None = 75
    disk_pct: float | None = 90
    writer_queue: int | None = 5000
    rss_mb: float | None = 220


PARAMS: dict[str, type[_P]] = {
    "keyword": KeywordParams,
    "telemetry_threshold": TelemetryThresholdParams,
    "node_offline": NodeOfflineParams,
    "node_online": NodeOnlineParams,
    "new_node": NewNodeParams,
    "gateway_down": GatewayDownParams,
    "system": SystemParams,
}


class RuleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    kind: Literal[
        "keyword",
        "telemetry_threshold",
        "node_offline",
        "node_online",
        "new_node",
        "gateway_down",
        "system",
    ]
    params: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    cooldown_s: int = Field(900, ge=0, le=7 * 86400)
    channels: list[Literal["webpush", "telegram", "webhook", "mqtt"]] = Field(default_factory=list)
    severity: Severity = "warning"
    is_public: bool = False

    def parsed_params(self) -> _P:
        return PARAMS[self.kind](**self.params)


DEFAULT_RULES: list[dict[str, Any]] = [
    {
        "name": "SOS en el canal público",
        "kind": "keyword",
        "params": {"patterns": [r"\bSOS\b"], "regex": True, "include_bell": True},
        "severity": "critical",
        "is_public": True,
        "cooldown_s": 300,
        "channels": ["webpush", "telegram", "webhook", "mqtt"],
    },
    {
        "name": "Gateway sin paquetes",
        "kind": "gateway_down",
        "params": {"minutes": 30},
        "severity": "warning",
        "is_public": False,
        "cooldown_s": 3600,
        "channels": ["webpush", "telegram"],
    },
    {
        "name": "Sistema",
        "kind": "system",
        "params": {},
        "severity": "warning",
        "is_public": False,
        "cooldown_s": 3600,
        "channels": ["webpush", "telegram"],
    },
]
