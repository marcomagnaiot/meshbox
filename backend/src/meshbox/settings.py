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

- Los mensajes directos y los canales privados **nunca** se guardan ni se muestran.
- Las posiciones se guardan 90 días y los mensajes 365 días.
- Sin analítica, sin rastreo y sin cookies para visitantes.
- La capa satelital la sirve Esri (Esri World Imagery) desde su servidor.

**Baja a pedido:** quien quiera que su nodo no aparezca puede pedirlo; el administrador lo oculta y puede borrar su historial (criterio de la Ley 25.326).
"""


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
            return SiteSettings(**raw)
        except ValueError:
            pass
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
