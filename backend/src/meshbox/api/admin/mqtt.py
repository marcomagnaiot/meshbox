"""Broker MQTT: cuentas, ACL y comandos para el gateway (secciones 14 y 18.2)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from starlette.responses import Response

from ...auth.sessions import SessionInfo
from ...integrations.mosquitto import MosquittoAdmin, heltec_commands, lan_ip
from ...system.privclient import PrivError
from ..deps import audit, get_ctx, require_admin
from ..http import JSON, NO_STORE, ProblemError

router = APIRouter(prefix="/api/v1/admin/mqtt", tags=["administración: broker MQTT"])


def admin_of(request: Request) -> MosquittoAdmin:
    return MosquittoAdmin(get_ctx(request))


class AccountIn(BaseModel):
    name: str = Field(min_length=2, max_length=28, pattern=r"^[a-z0-9][a-z0-9_-]+$")
    purpose: Literal["gateway", "integration", "debug"]
    note: str | None = Field(None, max_length=200)
    serial_port: str = Field(
        "COM5", max_length=40, description="puerto para los comandos de ejemplo"
    )


def _commands(
    request: Request, mq: MosquittoAdmin, username: str, password: str, port: str
) -> dict[str, Any]:
    host = lan_ip()
    if host.startswith("127."):
        host = request.url.hostname or host
    return heltec_commands(host=host, username=username, password=password, root=mq.root, port=port)


@router.get("/accounts")
async def accounts(request: Request, _: SessionInfo = Depends(require_admin)) -> Response:
    mq = admin_of(request)
    await mq.adopt_existing()
    return JSON(
        {"accounts": await mq.accounts(), "root": mq.root, "events_prefix": mq.events_prefix},
        headers=NO_STORE,
    )


@router.post("/accounts", status_code=201)
async def create(
    request: Request, body: AccountIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    mq = admin_of(request)
    try:
        username, password = await mq.create(body.name, body.purpose, body.note)
    except ValueError as e:
        raise ProblemError(422, str(e)) from None
    except PrivError as e:
        raise ProblemError(502, f"privd: {e.message}") from None
    audit(request, info, "mqtt.account.create", username, {"purpose": body.purpose})
    out: dict[str, Any] = {
        "username": username,
        "password": password,
        "purpose": body.purpose,
        "warning": "La contraseña se muestra una sola vez; para volver a verla hay que rotarla.",
    }
    if body.purpose == "gateway":
        out["heltec"] = _commands(request, mq, username, password, body.serial_port)
    return JSON(out, status_code=201, headers=NO_STORE)


class RotateIn(BaseModel):
    serial_port: str = Field("COM5", max_length=40)


@router.post("/accounts/{username}/rotate")
async def rotate(
    request: Request, username: str, body: RotateIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    mq = admin_of(request)
    try:
        password = await mq.rotate(username)
    except KeyError:
        raise ProblemError(404, "Cuenta no encontrada") from None
    except PrivError as e:
        raise ProblemError(502, f"privd: {e.message}") from None
    audit(request, info, "mqtt.account.rotate", username)
    out: dict[str, Any] = {"username": username, "password": password}
    if username.startswith("gw-"):
        out["heltec"] = _commands(request, mq, username, password, body.serial_port)
    return JSON(out, headers=NO_STORE)


@router.delete("/accounts/{username}", status_code=204)
async def delete(
    request: Request, username: str, info: SessionInfo = Depends(require_admin)
) -> Response:
    mq = admin_of(request)
    try:
        await mq.delete(username)
    except ValueError as e:
        raise ProblemError(409, str(e)) from None
    except PrivError as e:
        raise ProblemError(502, f"privd: {e.message}") from None
    audit(request, info, "mqtt.account.delete", username)
    return Response(status_code=204)


@router.get("/acl")
async def acl(request: Request, _: SessionInfo = Depends(require_admin)) -> Response:
    mq = admin_of(request)
    accounts = await mq.accounts()
    return JSON(
        {"acl": mq.acl_preview(accounts), "payload": mq.acl_payload(accounts)}, headers=NO_STORE
    )


@router.get("/status")
async def broker_status(request: Request, _: SessionInfo = Depends(require_admin)) -> Response:
    ctx = get_ctx(request)
    try:
        st = await ctx.priv.call("mosquitto.status")
    except PrivError as e:
        st = {"active": None, "error": e.message}
    out = ctx.extensions.get("mqtt_out")
    return JSON(
        {"broker": st, "mqtt_out": out.status() if out else None, "lan_ip": lan_ip(), "port": 1883},
        headers=NO_STORE,
    )


class MqttOutIn(BaseModel):
    enabled: bool
    prefix: str = Field("meshbox/events", pattern=r"^[A-Za-z0-9_/-]{1,64}$")


@router.put("/out")
async def mqtt_out(
    request: Request, body: MqttOutIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    """Salida MQTT de eventos para otros sistemas (14.3)."""
    ctx = get_ctx(request)
    ctx.cfg.mqtt_out.enabled = body.enabled
    ctx.cfg.mqtt_out.prefix = body.prefix
    ctx.save_config()
    audit(request, info, "mqtt.out", None, body.model_dump())
    out = ctx.extensions.get("mqtt_out")
    return JSON(out.status() if out else {"enabled": body.enabled})
