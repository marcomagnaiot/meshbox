"""Estación meteorológica externa (sección 21.2): JSON por URL → punto fijo con valores."""

from __future__ import annotations

import time
from typing import Any

from ...api import PluginBase, PluginContext


def dig(data: Any, path: str) -> Any:
    """Valor por ruta con puntos (`current.temp`, `data.0.value`)."""
    cur = data
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return None
    return cur


class Plugin(PluginBase):
    async def setup(self, ctx: PluginContext) -> None:
        await super().setup(ctx)
        self.last: dict[str, Any] | None = None

    async def layer(self, layer_id: str) -> dict[str, Any]:
        s = self.ctx.settings
        r = await self.ctx.http.get(s["url"])
        r.raise_for_status()
        data = r.json()
        values = []
        for f in s.get("fields") or []:
            v = dig(data, str(f.get("path", "")))
            if isinstance(v, int | float | str) and not isinstance(v, bool):
                values.append(
                    {
                        "label": f.get("label") or f.get("path"),
                        "value": v,
                        "unit": f.get("unit") or "",
                    }
                )
        feature = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(s["lon"]), float(s["lat"])]},
            "properties": {
                "name": s.get("name") or "Estación",
                "values": values,
                "ts": time.time(),
            },
        }
        self.last = feature
        return {"type": "FeatureCollection", "features": [feature]}
