"""Avisos push en los equipos del panel (ADR 0023).

Cada equipo (navegador o panel instalado en el celular) se suscribe por su cuenta y elige qué
recibe: las alertas y los mensajes que llegan a las placas del Cliente Meshtastic (solo los
directos o también los de canales). Los permisos son los de leer los mensajes: operadores y
administradores.
"""

from __future__ import annotations

from typing import Any, Literal

import orjson
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from starlette.responses import Response

from ...alerts.channels.webpush import WebPush
from ...auth.sessions import SessionInfo
from ..deps import audit, get_ctx, require_operator
from ..http import JSON, NO_STORE, ProblemError

router = APIRouter(
    prefix="/api/v1/admin/notifications", tags=["administración: avisos en este equipo"]
)


class Keys(BaseModel):
    p256dh: str = Field(min_length=20, max_length=200)
    auth: str = Field(min_length=8, max_length=100)


class EndpointIn(BaseModel):
    endpoint: str = Field(pattern=r"^https://", max_length=1000)


class DeviceIn(EndpointIn):
    keys: Keys
    alerts: bool = True
    messages: Literal["off", "dm", "all"] = "dm"


def _push(request: Request) -> WebPush:
    ctx = get_ctx(request)
    notifier: Any = ctx.extensions.get("message_push")
    push: WebPush = notifier.push if notifier is not None else WebPush(ctx)
    return push


def _available(request: Request) -> WebPush:
    push = _push(request)
    if not push.available:
        raise ProblemError(404, "Las notificaciones push no están disponibles")
    return push


@router.get("")
async def info(request: Request, _: SessionInfo = Depends(require_operator)) -> Response:
    """Si el equipo puede mandar push y la clave pública para suscribirse."""
    push = _push(request)
    return JSON(
        {"available": push.available, "public_key": push.public_key if push.available else None},
        headers=NO_STORE,
    )


@router.post("/device/state")
async def device_state(
    request: Request, body: EndpointIn, _: SessionInfo = Depends(require_operator)
) -> Response:
    """Lo que recibe este equipo (POST: la dirección de la suscripción es larga)."""
    state = await _push(request).device(body.endpoint)
    return JSON({"subscribed": state is not None, **(state or {})}, headers=NO_STORE)


@router.put("/device")
async def put_device(
    request: Request, body: DeviceIn, info: SessionInfo = Depends(require_operator)
) -> Response:
    push = _available(request)
    await push.set_device(
        body.endpoint, body.keys.p256dh, body.keys.auth, info.user_id, body.alerts, body.messages
    )
    audit(
        request,
        info,
        "notifications.device",
        None,
        {"alerts": body.alerts, "messages": body.messages},
    )
    return JSON({"subscribed": True, "alerts": body.alerts, "messages": body.messages})


@router.delete("/device", status_code=204)
async def delete_device(
    request: Request, body: EndpointIn, info: SessionInfo = Depends(require_operator)
) -> Response:
    if await _push(request).unsubscribe(body.endpoint):
        audit(request, info, "notifications.device.delete")
    return Response(status_code=204)


@router.post("/device/test")
async def test_device(
    request: Request, body: EndpointIn, _: SessionInfo = Depends(require_operator)
) -> Response:
    """Manda un aviso de prueba solo a este equipo."""
    push = _available(request)

    def q(conn: Any) -> list[dict[str, Any]]:
        from sqlalchemy import text

        rows = conn.execute(
            text(
                "SELECT id, endpoint, p256dh, auth, failures FROM push_subscriptions "
                "WHERE endpoint = :e AND scope = 'admin'"
            ),
            {"e": body.endpoint},
        ).mappings()
        return [dict(r) for r in rows]

    subs = await get_ctx(request).db.read(q)
    if not subs:
        raise ProblemError(404, "Este equipo no está suscripto")
    spanish = get_ctx(request).site.default_language == "es"
    payload = {
        "kind": "message",
        "title": "meshbox",
        "body": "Prueba: los avisos llegan a este equipo."
        if spanish
        else "Test: notifications reach this device.",
        "url": "/admin",
        "tag": "test",
    }
    ok, _fail = await push.deliver(subs, orjson.dumps(payload), urgency="high", ttl=600)
    if not ok:
        raise ProblemError(502, "El servicio de notificaciones del navegador no aceptó el aviso")
    return JSON({"ok": True})
