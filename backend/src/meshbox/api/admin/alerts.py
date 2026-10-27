"""Alertas: reglas, eventos y canales de notificación (secciones 12.4, 18.2 y 19)."""

from __future__ import annotations

import secrets as pysecrets
import time
from typing import Any

import orjson
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text
from starlette.responses import Response

from ...alerts.rules import PARAMS, RuleIn
from ...auth.sessions import SessionInfo
from ...config import SECRET_MASK
from ...store.queries import alerts_page
from ..deps import audit, get_ctx, require_admin, require_operator
from ..http import JSON, NO_STORE, ProblemError, parse_cursor

router = APIRouter(prefix="/api/v1/admin/alerts", tags=["administración: alertas"])


def engine_of(request: Request) -> Any:
    engine = get_ctx(request).extensions.get("alerts")
    if engine is None:
        raise ProblemError(503, "El motor de alertas no está activo")
    return engine


def _rule_out(r: dict[str, Any]) -> dict[str, Any]:
    return {
        **r,
        "params": orjson.loads(r["params"]),
        "channels": orjson.loads(r["channels"]),
        "enabled": bool(r["enabled"]),
        "is_public": bool(r["is_public"]),
    }


@router.get("/rules/schema")
async def rules_schema(_: SessionInfo = Depends(require_operator)) -> Response:
    """JSON Schema de la regla y de los parámetros de cada tipo (formularios del panel, 18.3).

    Son los mismos modelos de pydantic que validan en el servidor.
    """
    return JSON(
        {
            "rule": RuleIn.model_json_schema(),
            "params": {kind: model.model_json_schema() for kind, model in PARAMS.items()},
        },
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/rules")
async def rules(request: Request, _: SessionInfo = Depends(require_operator)) -> Response:
    ctx = get_ctx(request)

    def q(conn: Connection) -> list[dict[str, Any]]:
        return [
            _rule_out(dict(r))
            for r in conn.execute(text("SELECT * FROM alert_rules ORDER BY id")).mappings().all()
        ]

    return JSON({"rules": await ctx.db.read(q)}, headers=NO_STORE)


@router.post("/rules", status_code=201)
async def create_rule(
    request: Request, body: RuleIn, info: SessionInfo = Depends(require_operator)
) -> Response:
    ctx = get_ctx(request)
    engine = engine_of(request)
    try:
        row = engine.rule_from_in(body)
    except ValueError as e:
        raise ProblemError(422, str(e)) from None
    now = time.time()
    row.update(created_at=now, updated_at=now)
    rid = await ctx.writer.run(
        lambda c: (
            c.execute(
                text(
                    "INSERT INTO alert_rules (name, kind, params, enabled, cooldown_s, channels, severity, is_public, "
                    "created_at, updated_at) VALUES (:name, :kind, :params, :enabled, :cooldown_s, :channels, :severity, "
                    ":is_public, :created_at, :updated_at)"
                ),
                row,
            ).lastrowid
        )
    )
    await engine.reload()
    audit(request, info, "alert.rule.create", body.name, {"kind": body.kind})
    return JSON({"id": rid, **_rule_out({**row, "id": rid})}, status_code=201)


@router.put("/rules/{rid}")
async def update_rule(
    request: Request, rid: int, body: RuleIn, info: SessionInfo = Depends(require_operator)
) -> Response:
    ctx = get_ctx(request)
    engine = engine_of(request)
    try:
        row = engine.rule_from_in(body)
    except ValueError as e:
        raise ProblemError(422, str(e)) from None
    row.update(id=rid, updated_at=time.time())
    n = await ctx.writer.run(
        lambda c: (
            c.execute(
                text(
                    "UPDATE alert_rules SET name = :name, kind = :kind, params = :params, enabled = :enabled, "
                    "cooldown_s = :cooldown_s, channels = :channels, severity = :severity, is_public = :is_public, "
                    "updated_at = :updated_at WHERE id = :id"
                ),
                row,
            ).rowcount
        )
    )
    if not n:
        raise ProblemError(404, "Regla no encontrada")
    await engine.reload()
    audit(request, info, "alert.rule.update", body.name)
    return JSON(_rule_out(row | {"created_at": None}))


@router.delete("/rules/{rid}", status_code=204)
async def delete_rule(
    request: Request, rid: int, info: SessionInfo = Depends(require_operator)
) -> Response:
    ctx = get_ctx(request)
    engine = engine_of(request)
    n = await ctx.writer.run(
        lambda c: c.execute(text("DELETE FROM alert_rules WHERE id = :i"), {"i": rid}).rowcount
    )
    if not n:
        raise ProblemError(404, "Regla no encontrada")
    await engine.reload()
    audit(request, info, "alert.rule.delete", str(rid))
    return Response(status_code=204)


@router.post("/rules/{rid}/test")
async def test_rule(
    request: Request, rid: int, info: SessionInfo = Depends(require_operator)
) -> Response:
    engine = engine_of(request)
    try:
        result = await engine.test_rule(rid)
    except KeyError:
        raise ProblemError(404, "Regla no encontrada") from None
    audit(request, info, "alert.rule.test", str(rid))
    return JSON(result)


@router.get("/events")
async def events(
    request: Request,
    before: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    _: SessionInfo = Depends(require_operator),
) -> Response:
    ctx = get_ctx(request)
    cur = parse_cursor(before)
    rows, nxt = await ctx.db.read(lambda c: alerts_page(c, cur, limit, public_only=False))
    return JSON({"events": rows, "next": nxt}, headers=NO_STORE)


@router.post("/events/{eid}/ack")
async def ack(
    request: Request, eid: int, info: SessionInfo = Depends(require_operator)
) -> Response:
    ctx = get_ctx(request)
    n = await ctx.writer.run(
        lambda c: (
            c.execute(
                text("UPDATE alert_events SET ack_by = :u, ack_at = :t WHERE id = :i"),
                {"u": info.user_id, "t": time.time(), "i": eid},
            ).rowcount
        )
    )
    if not n:
        raise ProblemError(404, "Evento no encontrado")
    audit(request, info, "alert.ack", str(eid))
    return JSON({"id": eid, "ack_by": info.username})


# --------------------------------------------------------------------------- canales


class WebhookIn(BaseModel):
    id: str | None = Field(None, pattern=r"^[a-z0-9-]{3,24}$")
    url: str = Field(pattern=r"^https?://", max_length=500)
    enabled: bool = True
    secret: str | None = Field(
        None, max_length=200, description="solo escritura; '********' = sin cambios"
    )


class ChannelsIn(BaseModel):
    webpush: dict[str, bool] = Field(default_factory=lambda: {"enabled": True})
    telegram_enabled: bool = False
    telegram_chat_id: str = Field("", max_length=64)
    telegram_bot_token: str | None = Field(None, max_length=200, description="solo escritura")
    webhooks: list[WebhookIn] = Field(default_factory=list, max_length=10)
    mqtt_enabled: bool = True


@router.get("/channels")
async def get_channels(request: Request, _: SessionInfo = Depends(require_admin)) -> Response:
    ctx = get_ctx(request)
    engine = engine_of(request)
    cfg = engine.channels_cfg
    tg = ctx.secrets.data.telegram
    return JSON(
        {
            "webpush": {
                **cfg["webpush"],
                "available": engine.push.available,
                "public_key": engine.push.public_key,
                "subscriptions": await engine.push.count(),
                "subject": ctx.cfg.push.subject,
            },
            "telegram": {
                "enabled": cfg["telegram"].get("enabled", False),
                "chat_id": cfg["telegram"].get("chat_id") or tg.chat_id,
                "bot_token": SECRET_MASK if tg.bot_token else "",
            },
            "webhooks": [
                {
                    **h,
                    "secret": SECRET_MASK if ctx.secrets.data.webhooks.get(h.get("id", "")) else "",
                }
                for h in cfg.get("webhooks") or []
            ],
            "mqtt": cfg["mqtt"],
            "stats": engine.stats.__dict__,
        },
        headers=NO_STORE,
    )


@router.put("/channels")
async def put_channels(
    request: Request, body: ChannelsIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    engine = engine_of(request)
    if body.telegram_bot_token and body.telegram_bot_token != SECRET_MASK:
        ctx.secrets.data.telegram.bot_token = body.telegram_bot_token
    ctx.secrets.data.telegram.chat_id = body.telegram_chat_id
    hooks = []
    for h in body.webhooks:
        hid = h.id or pysecrets.token_hex(4)
        if h.secret and h.secret != SECRET_MASK:
            ctx.secrets.data.webhooks[hid] = h.secret
        elif hid not in ctx.secrets.data.webhooks:
            ctx.secrets.data.webhooks[hid] = pysecrets.token_urlsafe(
                24
            )  # secreto generado si no se dio
        hooks.append({"id": hid, "url": h.url, "enabled": h.enabled})
    ctx.secrets.save()
    cfg = {
        "webpush": {"enabled": bool(body.webpush.get("enabled", True))},
        "telegram": {"enabled": body.telegram_enabled, "chat_id": body.telegram_chat_id},
        "webhooks": hooks,
        "mqtt": {"enabled": body.mqtt_enabled},
    }
    await engine.save_channels(cfg)
    audit(
        request,
        info,
        "alert.channels",
        None,
        {"telegram": body.telegram_enabled, "webhooks": len(hooks)},
    )
    return await get_channels(request, info)


@router.post("/channels/{channel}/test")
async def test_channel(
    request: Request, channel: str, info: SessionInfo = Depends(require_admin)
) -> Response:
    engine = engine_of(request)
    error = await engine.test_channel(channel)
    audit(request, info, "alert.channel.test", channel, {"ok": error is None})
    return JSON({"ok": error is None, "error": error})


@router.get("/webhooks/{hid}/secret")
async def webhook_secret(
    request: Request, hid: str, info: SessionInfo = Depends(require_admin)
) -> Response:
    """Muestra el secreto HMAC de un webhook (para configurarlo en el receptor). Queda en auditoría."""
    ctx = get_ctx(request)
    secret = ctx.secrets.data.webhooks.get(hid)
    if not secret:
        raise ProblemError(404)
    audit(request, info, "alert.webhook.secret_viewed", hid)
    return JSON({"id": hid, "secret": secret}, headers=NO_STORE)


# --------------------------------------------------------------------------- push del panel


class AdminSubIn(BaseModel):
    endpoint: str = Field(pattern=r"^https://", max_length=1000)
    keys: dict[str, str]


@router.post("/push/subscriptions", status_code=201)
async def admin_subscribe(
    request: Request, body: AdminSubIn, info: SessionInfo = Depends(require_operator)
) -> Response:
    """Suscripción de administración: recibe todas las alertas, no solo las públicas."""
    engine = engine_of(request)
    if not engine.push.available:
        raise ProblemError(404, "Push no disponible")
    await engine.push.subscribe(
        body.endpoint, body.keys.get("p256dh", ""), body.keys.get("auth", ""), "admin", info.user_id
    )
    return JSON({"ok": True, "scope": "admin"}, status_code=201)
