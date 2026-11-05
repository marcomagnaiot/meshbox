"""Ajustes que guarda el panel en la tabla `settings` (apariencia, umbrales, textos).

`config.toml` guarda lo necesario para arrancar; esto es lo demás (sección 8).
"""

from __future__ import annotations

import time
from typing import Any, Literal

import orjson
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Connection, text

from .store.db import BatchWriter

DEFAULT_NOTICE = """## Privacidad

Este sitio muestra lo que los nodos Meshtastic transmiten **por el canal público** de la red local: nombres, posiciones, telemetría y mensajes. Cada dueño de nodo decide qué transmite; la web solo amplía la audiencia de datos que ya son públicos en la radio.

- Los mensajes directos y los canales privados **nunca** se guardan ni se muestran. Si un nodo contesta por el canal público un pedido de posición de la estación, esa posición y su nombre se muestran como si los hubiera transmitido a todos.
- Las posiciones se guardan 90 días y los mensajes 365 días.
- Sin analítica, sin rastreo y sin cookies para visitantes.
- La capa satelital y el mapa fuera de la zona descargada en el equipo los sirve Esri desde su servidor.

**Baja a pedido:** quien quiera que su nodo no aparezca puede pedirlo; el administrador lo oculta y puede borrar su historial (criterio de la Ley 25.326).
"""

# Avisos de fábrica anteriores: uno guardado sin cambios pasa al actual. Hasta la 0.9.3 Esri solo
# servía la capa satelital (desde la 0.9.4, también el mapa fuera del extracto, ADR 0019), y hasta
# la 0.9.5 no se usaban las respuestas a pedidos de la estación (ADR 0020).
_NOTICE_095 = DEFAULT_NOTICE.replace(
    " Si un nodo contesta por el canal público un pedido de posición de la estación, esa posición y "
    "su nombre se muestran como si los hubiera transmitido a todos.",
    "",
)
OLD_NOTICES = (
    _NOTICE_095.replace(
        "La capa satelital y el mapa fuera de la zona descargada en el equipo los sirve Esri desde "
        "su servidor.",
        "La capa satelital la sirve Esri (Esri World Imagery) desde su servidor.",
    ),
    _NOTICE_095,
)


# Valores de los enumerados de Meshtastic (config.proto) que acepta la ficha de conexión.
REGIONS = (
    "US",
    "EU_433",
    "EU_868",
    "CN",
    "JP",
    "ANZ",
    "KR",
    "TW",
    "RU",
    "IN",
    "NZ_865",
    "TH",
    "LORA_24",
    "UA_433",
    "UA_868",
    "MY_433",
    "MY_919",
    "SG_923",
    "PH_433",
    "PH_868",
    "PH_915",
    "ANZ_433",
    "KZ_433",
    "KZ_863",
    "NP_865",
    "BR_902",
)
PRESETS = (
    "LONG_FAST",
    "LONG_SLOW",
    "VERY_LONG_SLOW",
    "MEDIUM_SLOW",
    "MEDIUM_FAST",
    "SHORT_SLOW",
    "SHORT_FAST",
    "LONG_MODERATE",
    "SHORT_TURBO",
)
ROLES = ("CLIENT", "CLIENT_MUTE", "CLIENT_BASE", "ROUTER", "ROUTER_LATE", "REPEATER", "TRACKER")


class JoinSettings(BaseModel):
    """Ficha «Cómo conectarse»: los parámetros de radio de la red para quien llega.

    Vacía por defecto: se publica solo cuando quien administra la activa.
    """

    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    region: str = Field("", max_length=16)
    preset: str = Field("", max_length=20)
    slot: int = Field(0, ge=0, le=255)  # 0: el que elige el equipo según el nombre del canal
    frequency_mhz: float | None = Field(None, gt=0, le=3000)
    channel_name: str = Field("", max_length=11)  # vacío: el canal de fábrica del preset
    default_key: bool = True
    role: str = Field("CLIENT", max_length=20)
    hop_limit: int = Field(3, ge=1, le=7)
    contact: str = Field("", max_length=200)
    notes_md: str = Field("", max_length=4000)

    @field_validator("region")
    @classmethod
    def _region(cls, v: str) -> str:
        if v and v not in REGIONS:
            raise ValueError("región no válida")
        return v

    @field_validator("preset")
    @classmethod
    def _preset(cls, v: str) -> str:
        if v and v not in PRESETS:
            raise ValueError("preset no válido")
        return v

    @field_validator("role")
    @classmethod
    def _role(cls, v: str) -> str:
        if v and v not in ROLES:
            raise ValueError("rol no válido")
        return v


class SiteSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field("Red Meshtastic", min_length=1, max_length=60)
    description: str = Field("Mapa en vivo de la red Meshtastic local", max_length=300)
    accent: str = Field("#22b8cf", pattern=r"^#[0-9a-fA-F]{6}$")
    logo: str | None = Field(None, max_length=200)
    center: list[float] = Field(default_factory=lambda: [-34.6037, -58.3816])
    zoom: float = Field(11.0, ge=1, le=18)
    bounds: list[float] | None = None  # [oeste, sur, este, norte]
    default_layer: Literal["dark", "light", "satellite"] = "dark"
    satellite_enabled: bool = True
    default_language: Literal["es", "en"] = "es"
    notice_md: str = Field(DEFAULT_NOTICE, max_length=20_000)
    status_thresholds: dict[str, int] = Field(
        default_factory=lambda: {"active_s": 3600, "recent_s": 7200, "late_s": 86400}
    )
    show_inactive: bool = False
    activity_layer: bool = True
    links_layer: bool = True
    waypoints_layer: bool = True
    join: JoinSettings = Field(default_factory=JoinSettings)

    @field_validator("center")
    @classmethod
    def _center(cls, v: list[float]) -> list[float]:
        if len(v) != 2 or not (-90 <= v[0] <= 90 and -180 <= v[1] <= 180):
            raise ValueError("centro no válido: [lat, lon]")
        return [round(v[0], 6), round(v[1], 6)]

    @field_validator("bounds")
    @classmethod
    def _bounds(cls, v: list[float] | None) -> list[float] | None:
        if v is None:
            return v
        if len(v) != 4:
            raise ValueError("límites no válidos: [oeste, sur, este, norte]")
        w, s, e, n = v
        if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
            raise ValueError("límites fuera de rango o invertidos")
        return [round(x, 6) for x in v]

    @field_validator("status_thresholds")
    @classmethod
    def _thresholds(cls, v: dict[str, int]) -> dict[str, int]:
        a, r, late = v.get("active_s", 3600), v.get("recent_s", 7200), v.get("late_s", 86400)
        if not (0 < a < r < late <= 30 * 86400):
            raise ValueError("los umbrales deben crecer: activo < reciente < tardío")
        return {"active_s": a, "recent_s": r, "late_s": late}


SITE_KEY = "site"


def load_site(settings: dict[str, Any]) -> SiteSettings:
    raw = settings.get(SITE_KEY)
    if isinstance(raw, dict):
        try:
            site = SiteSettings(**raw)
        except ValueError:
            return SiteSettings()
        if site.notice_md.strip() in {n.strip() for n in OLD_NOTICES}:
            site.notice_md = DEFAULT_NOTICE
        return site
    return SiteSettings()


def put_setting_sql(conn: Connection, key: str, value: Any) -> None:
    conn.execute(
        text(
            "INSERT INTO settings (key, value, updated_at) VALUES (:k, :v, :t) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at"
        ),
        {"k": key, "v": orjson.dumps(value).decode(), "t": time.time()},
    )


async def put_setting(writer: BatchWriter, settings: dict[str, Any], key: str, value: Any) -> None:
    await writer.run(lambda c: put_setting_sql(c, key, value))
    settings[key] = value
