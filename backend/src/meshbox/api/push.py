"""Suscripción pública a notificaciones push (secciones 12.2 y 19.2)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from starlette.responses import Response

from .deps import get_ctx, ip_of
from .http import JSON, NO_STORE, ProblemError

router = APIRouter(prefix="/api/v1/push", tags=["público"])


class Keys(BaseModel):
    p256dh: str = Field(min_length=20, max_length=200)
    auth: str = Field(min_length=8, max_length=100)


class SubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1000, pattern=r"^https://")
    keys: Keys


class SubscriptionDel(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1000)


def _push(request: Request):  # type: ignore[no-untyped-def]
    alerts = get_ctx(request).extensions.get("alerts")
    push = alerts.push if alerts is not None else None
    if push is None or not push.available:
        raise ProblemError(404, "Las notificaciones push no están disponibles")
    return push


@router.get("/vapid-public-key")
async def vapid_public_key(request: Request) -> Response:
    return JSON({"key": _push(request).public_key}, headers={"Cache-Control": "no-cache"})


@router.post("/subscriptions", status_code=201)
async def subscribe(request: Request, body: SubscriptionIn) -> Response:
    push = _push(request)
    allowed, retry = request.app.state.push_limit.hit(ip_of(request))
    if not allowed:
        raise ProblemError(
            429,
            "Demasiadas suscripciones desde esta conexión",
            headers={"Retry-After": str(int(retry) + 1)},
        )
    # Las suscripciones públicas solo reciben alertas públicas (19.2).
    await push.subscribe(body.endpoint, body.keys.p256dh, body.keys.auth, "public", None)
    return JSON({"ok": True, "scope": "public"}, status_code=201, headers=NO_STORE)


@router.delete("/subscriptions", status_code=204)
async def unsubscribe(request: Request, body: SubscriptionDel) -> Response:
    push = _push(request)
    await push.unsubscribe(body.endpoint)
    return Response(status_code=204)
