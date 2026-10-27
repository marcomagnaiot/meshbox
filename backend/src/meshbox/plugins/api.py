"""API de plugins (sección 21.1).

Un plugin corre dentro del proceso: instalarlo equivale a confiar en su código (el panel lo
advierte). Sus datos públicos se exponen solo como capas GeoJSON declaradas en el manifiesto;
sus rutas propias son de administración.
"""

from __future__ import annotations

import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx
import orjson

from ..models import Event

if TYPE_CHECKING:
    from fastapi import APIRouter

    from ..app import Service

API_VERSION = 1
PERMISSIONS = frozenset(
    {"events.read", "http.outbound", "alerts.raise", "map.layers", "mqtt.publish", "nodes.read"}
)
LAYER_STYLES = frozenset({"point", "heat", "line", "polygon"})


@dataclass
class LayerDecl:
    id: str
    name: str
    geometry: str = "point"
    style: str = "point"
    refresh_s: int = 900


@dataclass
class Manifest:
    id: str
    name: str
    version: str
    api_version: int
    entrypoint: str
    permissions: list[str]
    settings_schema: dict[str, Any] = field(default_factory=dict)
    map_layers: list[LayerDecl] = field(default_factory=list)
    description: str = ""
    builtin: bool = False
    path: str = ""


class PluginLogHandler(logging.Handler):
    def __init__(self, capacity: int = 300) -> None:
        super().__init__()
        self.records: deque[dict[str, Any]] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(
            {"ts": record.created, "level": record.levelname, "msg": record.getMessage()}
        )


class PluginContext:
    """Lo que un plugin puede usar. Cada método verifica el permiso declarado."""

    def __init__(
        self,
        service: Service,
        manifest: Manifest,
        settings: dict[str, Any],
        secrets: dict[str, str],
    ) -> None:
        self._service = service
        self.manifest = manifest
        self.settings = settings
        self.secrets = secrets
        self.log = logging.getLogger(f"meshbox.plugin.{manifest.id}")
        self.log_handler = PluginLogHandler()
        self.log.addHandler(self.log_handler)
        self._http: httpx.AsyncClient | None = None

    def _need(self, perm: str) -> None:
        if perm not in self.manifest.permissions:
            raise PermissionError(f"el plugin {self.manifest.id} no declaró el permiso {perm}")

    @property
    def http(self) -> httpx.AsyncClient:
        self._need("http.outbound")
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=20,
                follow_redirects=True,
                headers={"User-Agent": f"meshbox-plugin/{self.manifest.id}"},
            )
        return self._http

    async def raise_alert(
        self,
        title: str,
        body: str | None = None,
        *,
        severity: str = "warning",
        node: str | None = None,
        is_public: bool = False,
        key: str | None = None,
    ) -> None:
        self._need("alerts.raise")
        engine = self._service.extensions.get("alerts")
        if engine is None:
            return
        from ..alerts.engine import Rule

        rule = Rule(
            id=0,
            name=f"plugin:{self.manifest.id}",
            kind=f"plugin:{self.manifest.id}",
            params=None,
            enabled=True,
            cooldown_s=3600,
            channels=["webpush", "telegram", "webhook", "mqtt"],
            severity=severity,
            is_public=is_public,
        )
        await engine.fire(rule, key=key or title, node=node, title=title, body=body, one_shot=True)

    def publish_mqtt(self, subtopic: str, data: dict[str, Any]) -> None:
        self._need("mqtt.publish")
        out = self._service.extensions.get("mqtt_out")
        if out is not None:
            out.publish_now(f"plugins/{self.manifest.id}/{subtopic}".strip("/"), data)

    def nodes(self) -> list[dict[str, Any]]:
        self._need("nodes.read")
        return self._service.state.public_nodes()

    def fixed_nodes(self) -> list[dict[str, Any]]:
        return [n for n in self.nodes() if n.get("is_fixed") and n.get("lat") is not None]

    @property
    def site(self) -> Any:
        return self._service.site

    async def kv_get(self, key: str, default: Any = None) -> Any:
        return self._service.state.settings.get(f"plugin.{self.manifest.id}.{key}", default)

    async def kv_set(self, key: str, value: Any) -> None:
        from ..settings import put_setting

        await put_setting(
            self._service.writer,
            self._service.state.settings,
            f"plugin.{self.manifest.id}.{key}",
            value,
        )

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None
        self.log.removeHandler(self.log_handler)


class PluginBase:
    """Clase base de un plugin. Todo es opcional salvo lo que declare el manifiesto."""

    ctx: PluginContext

    async def setup(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    async def on_event(self, event: Event) -> None:  # requiere events.read
        return None

    def router(self) -> APIRouter | None:  # rutas de administración propias
        return None

    async def layer(self, layer_id: str) -> dict[str, Any]:  # GeoJSON de cada capa declarada
        return {"type": "FeatureCollection", "features": []}

    async def teardown(self) -> None:
        return None


# --------------------------------------------------------------------------- validación de ajustes


class SettingsError(ValueError):
    pass


def validate_settings(schema: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """Subconjunto de JSON Schema: object/properties/required, type, enum, minimum, maximum,
    minLength, maxLength, pattern, items (de tipo simple) y default. Suficiente para formularios."""
    if not schema:
        return dict(data)
    props: dict[str, Any] = schema.get("properties", {})
    out: dict[str, Any] = {}
    for name, spec in props.items():
        if name in data and data[name] is not None:
            out[name] = _check(name, spec, data[name])
        elif "default" in spec:
            out[name] = spec["default"]
    for name in schema.get("required", []):
        if name not in out or out[name] in ("", None):
            raise SettingsError(f"falta el campo obligatorio {name}")
    unknown = set(data) - set(props)
    if unknown and schema.get("additionalProperties", True) is False:
        raise SettingsError(f"campos desconocidos: {', '.join(sorted(unknown))}")
    return out


def _check(name: str, spec: dict[str, Any], value: Any) -> Any:
    t = spec.get("type")
    match t:
        case "string":
            if not isinstance(value, str):
                raise SettingsError(f"{name}: se espera texto")
            if len(value) < spec.get("minLength", 0) or len(value) > spec.get("maxLength", 10_000):
                raise SettingsError(f"{name}: largo fuera de rango")
            if "pattern" in spec and not re.fullmatch(spec["pattern"], value):
                raise SettingsError(f"{name}: formato no válido")
        case "integer" | "number":
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise SettingsError(f"{name}: se espera un número")
            if t == "integer" and int(value) != value:
                raise SettingsError(f"{name}: se espera un entero")
            if "minimum" in spec and value < spec["minimum"]:
                raise SettingsError(f"{name}: mínimo {spec['minimum']}")
            if "maximum" in spec and value > spec["maximum"]:
                raise SettingsError(f"{name}: máximo {spec['maximum']}")
        case "boolean":
            if not isinstance(value, bool):
                raise SettingsError(f"{name}: se espera verdadero o falso")
        case "array":
            if not isinstance(value, list):
                raise SettingsError(f"{name}: se espera una lista")
            item = spec.get("items", {})
            value = [_check(f"{name}[]", item, v) for v in value] if item else value
            if len(value) > spec.get("maxItems", 1000):
                raise SettingsError(f"{name}: demasiados elementos")
        case "object":
            if not isinstance(value, dict):
                raise SettingsError(f"{name}: se espera un objeto")
            return validate_settings(spec, value) if spec.get("properties") else value
    if "enum" in spec and value not in spec["enum"]:
        raise SettingsError(f"{name}: valor no permitido")
    return value


def secret_fields(schema: dict[str, Any]) -> set[str]:
    return {
        k
        for k, v in schema.get("properties", {}).items()
        if v.get("writeOnly") or v.get("format") == "password"
    }


def now() -> float:
    return time.time()


def dumps(data: Any) -> str:
    return orjson.dumps(data).decode()
