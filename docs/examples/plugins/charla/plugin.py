"""Plugin de ejemplo de meshbox (docs/plugins.md).

Escucha los mensajes del canal público, guarda los últimos en memoria y publica una capa
GeoJSON con la posición de los nodos que escribieron en la ventana configurada.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any

from fastapi import APIRouter

from meshbox.models import Event, MessageAdded
from meshbox.plugins.api import PluginBase, PluginContext


class Plugin(PluginBase):
    async def setup(self, ctx: PluginContext) -> None:
        await super().setup(ctx)
        self.mensajes: deque[dict[str, Any]] = deque(maxlen=int(ctx.settings.get("maximo", 50)))
        ctx.log.info("plugin charla listo")

    async def on_event(self, event: Event) -> None:
        if isinstance(event, MessageAdded):
            self.mensajes.append(event.message)

    def router(self) -> APIRouter:
        r = APIRouter()

        @r.get("/mensajes")
        async def mensajes() -> dict[str, Any]:
            return {"mensajes": list(self.mensajes)}

        return r

    async def layer(self, layer_id: str) -> dict[str, Any]:
        desde = time.time() - int(self.ctx.settings.get("ventana_min", 60)) * 60
        quienes = {m["from"] for m in self.mensajes if m["ts"] >= desde}
        features = [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [n["lon"], n["lat"]]},
                "properties": {"id": n["id"], "name": n.get("long_name") or n.get("short_name")},
            }
            for n in self.ctx.nodes()
            if n["id"] in quienes and n.get("lat") is not None
        ]
        return {"type": "FeatureCollection", "features": features}
