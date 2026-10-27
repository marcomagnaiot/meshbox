"""Plugins en el panel (secciones 12.4, 18.2 y 21) y transmisión opcional (sección 22)."""

from __future__ import annotations

import time
from collections import deque
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from starlette.responses import Response

from ...auth.sessions import SessionInfo
from ...models import node_num
from ..deps import audit, get_ctx, require_admin
from ..http import JSON, NO_STORE, ProblemError

router = APIRouter(prefix="/api/v1/admin", tags=["administración: plugins y transmisión"])


def plugins_of(request: Request) -> Any:
    pm = get_ctx(request).extensions.get("plugins")
    if pm is None:
        raise ProblemError(503, "El sistema de plugins no está activo")
    return pm


@router.get("/plugins")
async def plugins(request: Request, _: SessionInfo = Depends(require_admin)) -> Response:
    pm = plugins_of(request)
    pm.discover()
    return JSON(
        {
            "plugins": [pm.describe(lp) for lp in pm.plugins.values()],
            "warning": "Un plugin corre dentro del servicio: instalarlo equivale a confiar en su código.",
            "user_dir": str(get_ctx(request).cfg.paths.plugins),
        },
        headers=NO_STORE,
    )


class PluginIn(BaseModel):
    enabled: bool | None = None
    settings: dict[str, Any] | None = None


@router.put("/plugins/{pid}")
async def update_plugin(
    request: Request, pid: str, body: PluginIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    pm = plugins_of(request)
    try:
        out = await pm.update(pid, body.enabled, body.settings)
    except KeyError:
        raise ProblemError(404, "Plugin no encontrado") from None
    except ValueError as e:
        raise ProblemError(422, str(e)) from None
    audit(
        request,
        info,
        "plugin.update",
        pid,
        {"enabled": body.enabled, "settings": body.settings is not None},
    )
    return JSON(out)


@router.get("/plugins/{pid}/logs")
async def plugin_logs(
    request: Request, pid: str, _: SessionInfo = Depends(require_admin)
) -> Response:
    return JSON({"logs": plugins_of(request).logs(pid)}, headers=NO_STORE)


# --------------------------------------------------------------------------- transmisión (22)


class TxLimiter:
    """1 mensaje cada 30 s y 20 por hora (sección 22)."""

    def __init__(self) -> None:
        self.sent: deque[float] = deque()

    def check(self) -> float:
        now = time.time()
        while self.sent and now - self.sent[0] > 3600:
            self.sent.popleft()
        if self.sent and now - self.sent[-1] < 30:
            return 30 - (now - self.sent[-1])
        if len(self.sent) >= 20:
            return 3600 - (now - self.sent[0])
        return 0.0

    def mark(self) -> None:
        self.sent.append(time.time())


def _tx_guard(request: Request) -> tuple[Any, Any, TxLimiter]:
    ctx = get_ctx(request)
    if not ctx.cfg.tx.enabled:
        raise ProblemError(
            403, "La transmisión está desactivada ([tx] enabled = false en config.toml)"
        )
    serial = ctx.connectors.serial()
    if serial is None or serial.status().state != "connected":
        raise ProblemError(409, "Transmitir requiere un nodo conectado por USB o por la red (TCP)")
    limiter: TxLimiter = ctx.extensions.setdefault("tx_limiter", TxLimiter())
    wait = limiter.check()
    if wait > 0:
        raise ProblemError(
            429,
            f"Límite de transmisión: esperar {int(wait)} s",
            headers={"Retry-After": str(int(wait) + 1)},
        )
    return ctx, serial, limiter


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=200)
    channel_index: int = Field(0, ge=0, le=7)
    confirm: bool = False


@router.post("/tx/text")
async def tx_text(
    request: Request, body: TextIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    _ctx, serial, limiter = _tx_guard(request)
    preview = {
        "text": body.text,
        "channel": serial.channel_names.get(body.channel_index),
        "bytes": len(body.text.encode()),
    }
    if not body.confirm:
        return JSON({"preview": preview, "confirm_required": True})
    packet_id = await serial.send_text(body.text, body.channel_index)
    limiter.mark()
    audit(request, info, "tx.text", preview["channel"], {"text": body.text, "packet_id": packet_id})
    return JSON({"ok": True, "packet_id": packet_id})


class TracerouteIn(BaseModel):
    node: str
    hop_limit: int = Field(3, ge=1, le=7)
    channel_index: int = Field(0, ge=0, le=7)
    confirm: bool = False


@router.post("/tx/traceroute")
async def tx_traceroute(
    request: Request, body: TracerouteIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    _ctx, serial, limiter = _tx_guard(request)
    try:
        dest = node_num(body.node)
    except ValueError:
        raise ProblemError(422, "id de nodo no válido") from None
    if not body.confirm:
        return JSON(
            {"preview": {"node": body.node, "hop_limit": body.hop_limit}, "confirm_required": True}
        )
    limiter.mark()
    audit(request, info, "tx.traceroute", body.node, {"hop_limit": body.hop_limit})
    try:
        await serial.send_traceroute(dest, body.hop_limit, body.channel_index)
    except Exception as e:
        return JSON({"ok": False, "error": str(e)[:200]})
    return JSON(
        {
            "ok": True,
            "note": "La respuesta llega como TRACEROUTE_APP y se ve en Paquetes y en el mapa",
        }
    )
