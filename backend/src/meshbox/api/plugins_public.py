"""Capas públicas de plugins (sección 12.2): GeoJSON, sin código de terceros en el sitio."""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import Response

from .deps import get_ctx
from .http import JSON, ProblemError

router = APIRouter(prefix="/api/v1/plugins", tags=["público"])


@router.get("/layers")
async def layers(request: Request) -> Response:
    plugins = get_ctx(request).extensions.get("plugins")
    return JSON(plugins.public_layers() if plugins else [], headers={"Cache-Control": "no-cache"})


@router.get("/{plugin_id}/layers/{layer_id}")
async def layer(request: Request, plugin_id: str, layer_id: str) -> Response:
    plugins = get_ctx(request).extensions.get("plugins")
    data = await plugins.layer(plugin_id, layer_id) if plugins else None
    if data is None:
        raise ProblemError(404, "Capa no encontrada")
    return JSON(data, headers={"Cache-Control": "public, max-age=60"})
