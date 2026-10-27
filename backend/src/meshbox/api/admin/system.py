"""Sistema y red (sección 12.4: Sistema, Red; 18.2: Panel, Red, Registros)."""

from __future__ import annotations

import re
import time
from typing import Any, Literal

import orjson
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from starlette.responses import Response

from ... import __version__
from ...auth.sessions import SessionInfo
from ...system.logs import RING
from ...system.privclient import PrivError
from ..deps import audit, get_ctx, require_admin, require_operator
from ..http import JSON, NO_STORE, ProblemError

router = APIRouter(prefix="/api/v1/admin", tags=["administración: sistema"])
UNITS = ("meshbox", "mosquitto", "meshbox-cloudflared", "meshbox-privd")
SINCE_RE = re.compile(
    r"^(-?\d{1,6}\s?(s|min|h|d)|today|yesterday|\d{4}-\d{2}-\d{2}( \d{2}:\d{2}(:\d{2})?)?)$"
)


async def priv(ctx: Any, cmd: str, **args: Any) -> dict[str, Any]:
    try:
        result: dict[str, Any] = await ctx.priv.call(cmd, **args)
        return result
    except PrivError as e:
        status = 409 if e.code == "not_allowed_in_shared_mode" else 502
        raise ProblemError(status, e.message or e.code, extra={"code": e.code}) from None


def shared_guard(ctx: Any) -> None:
    if ctx.cfg.host.mode == "shared":
        raise ProblemError(
            409, "No disponible en un equipo compartido (ADR 0004)", extra={"code": "shared_mode"}
        )


@router.get("/system/status")
async def status(request: Request, _: SessionInfo = Depends(require_operator)) -> Response:
    ctx = get_ctx(request)
    services: dict[str, Any] = {}
    for unit in UNITS:
        try:
            services[unit] = await ctx.priv.call("service.status", name=unit)
        except PrivError as e:
            services[unit] = {"name": unit, "active": None, "state": None, "error": e.message}
    # meshbox responde, así que está activo; de systemd se conservan reinicios y PID.
    meshbox = services["meshbox"]
    meshbox.pop("error", None)
    meshbox.update(
        name="meshbox",
        active=True,
        state="active",
        version=__version__,
        uptime_s=round(time.time() - ctx.started_at),
    )
    alerts = ctx.extensions.get("alerts")
    updates = ctx.extensions.get("updates")
    recent_alerts: list[Any] = []
    if alerts is not None:
        from ...store.queries import alerts_page

        recent_alerts, _n = await ctx.db.read(lambda c: alerts_page(c, None, 5, public_only=False))
    return JSON(
        {
            "version": __version__,
            "mode": ctx.cfg.host.mode,
            "services": services,
            "system": ctx.last_system,
            "connectors": ctx.connectors.statuses(),
            "gateways": [g.as_dict() for g in ctx.state.gateways.values()],
            "summary": ctx.state.summary(),
            "counters": ctx.state.counters(),
            "packets_per_minute": ctx.state.packets_per_minute(60),
            "sse_clients": {"public": ctx.sse_public_clients, "admin": ctx.sse_admin_clients},
            "last_packet_at": ctx.state.last_packet_at,
            "recent_alerts": recent_alerts,
            "update": (await updates.status())
            if updates is not None and ctx.cfg.updates.auto_check
            else None,
            "ntp_synced": ctx.ntp_synced,
            "privd": "simulado" if ctx.priv.fake else "socket",
        },
        headers=NO_STORE,
    )


@router.get("/system/metrics")
async def metrics(
    request: Request,
    minutes: int = Query(60, ge=5, le=1440),
    _: SessionInfo = Depends(require_operator),
) -> Response:
    ctx = get_ctx(request)
    return JSON(
        {
            "system": ctx.last_system,
            "packets_per_minute": ctx.state.packets_per_minute(minutes),
            "counters": ctx.state.counters(),
            "writer": ctx.writer.stats(),
            "bus": ctx.bus.stats(),
            "dedup_entries": len(ctx.processor.dedup),
            "ingest": {"queue": ctx.connectors.queue.qsize(), "dropped": ctx.connectors.dropped},
            "memory_guard": {
                "soft_mb": ctx.memory_guard.soft_mb,
                "hard_mb": ctx.memory_guard.hard_mb,
                "soft_hits": ctx.memory_guard.soft_hits,
            },
        },
        headers=NO_STORE,
    )


@router.get("/system/logs")
async def logs(
    request: Request,
    unit: Literal["meshbox", "mosquitto", "meshbox-cloudflared", "meshbox-privd"] = "meshbox",
    lines: int = Query(200, ge=1, le=2000),
    since: str | None = None,
    level: str | None = None,
    q: str | None = Query(None, max_length=100),
    _: SessionInfo = Depends(require_operator),
) -> Response:
    ctx = get_ctx(request)
    if since and not SINCE_RE.match(since):
        raise ProblemError(
            422, "formato de `since` no válido (ej.: -1h, 30min, today, 2026-10-20 10:00)"
        )
    if ctx.priv.fake and unit == "meshbox":
        return JSON({"unit": unit, "entries": RING.tail(lines, level, q)}, headers=NO_STORE)
    args: dict[str, Any] = {"unit": unit, "lines": lines}
    if since:
        args["since"] = since
    result = await priv(ctx, "logs.read", **args)
    entries = [normalize_journal(e, unit) for e in result.get("entries", [])]
    min_rank = LEVEL_RANK.get((level or "").upper(), 0)
    entries = [
        e
        for e in entries
        if LEVEL_RANK.get(e["level"], 0) >= min_rank and (not q or q.lower() in e["msg"].lower())
    ]
    return JSON({"unit": unit, "entries": entries}, headers=NO_STORE)


LEVEL_RANK = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
SYSLOG_LEVEL = {
    0: "CRITICAL",
    1: "CRITICAL",
    2: "CRITICAL",
    3: "ERROR",
    4: "WARNING",
    5: "INFO",
    6: "INFO",
    7: "DEBUG",
}


def normalize_journal(entry: dict[str, Any], unit: str) -> dict[str, Any]:
    """Entrada de journalctl (vía privd) → {ts, level, msg, logger, unit}.

    meshbox escribe una línea JSON por registro; si el mensaje lo es, se usan sus campos.
    """
    msg = str(entry.get("message") or entry.get("msg") or "")
    priority = entry.get("priority")
    level = SYSLOG_LEVEL.get(priority if isinstance(priority, int) else 6, "INFO")
    logger = entry.get("identifier")
    if msg.startswith("{") and '"msg"' in msg:
        try:
            data = orjson.loads(msg)
            msg = str(data.get("msg", msg))
            level = str(data.get("level", level))
            logger = data.get("logger", logger)
            if data.get("exc"):
                msg += "\n" + str(data["exc"])
        except orjson.JSONDecodeError:
            pass
    return {"ts": entry.get("ts"), "level": level, "msg": msg, "logger": logger, "unit": unit}


class HostnameIn(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


class TimezoneIn(BaseModel):
    tz: str = Field(pattern=r"^[A-Za-z_]+(/[A-Za-z0-9_+-]+){0,2}$", max_length=64)


class ConfirmIn(BaseModel):
    confirm: bool = False


@router.put("/system/hostname")
async def hostname(
    request: Request, body: HostnameIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    shared_guard(ctx)
    result = await priv(ctx, "system.hostname", name=body.name)
    audit(request, info, "system.hostname", body.name)
    return JSON(result)


@router.put("/system/timezone")
async def timezone(
    request: Request, body: TimezoneIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    if ctx.cfg.host.mode != "shared":
        await priv(ctx, "system.timezone", tz=body.tz)
    ctx.cfg.site.timezone = body.tz  # zona del sitio (formatos y tareas diarias)
    ctx.save_config()
    audit(request, info, "system.timezone", body.tz)
    return JSON({"timezone": body.tz, "system_changed": ctx.cfg.host.mode != "shared"})


@router.post("/system/reboot")
async def reboot(
    request: Request, body: ConfirmIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    if not body.confirm:
        raise ProblemError(
            400, "Confirmar el reinicio (también corta los demás servicios del equipo)"
        )
    ctx = get_ctx(request)
    audit(request, info, "system.reboot")
    await ctx.writer.flush()
    return JSON(await priv(ctx, "system.reboot"))


@router.post("/system/shutdown")
async def shutdown(
    request: Request, body: ConfirmIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    if not body.confirm:
        raise ProblemError(400, "Confirmar el apagado")
    ctx = get_ctx(request)
    audit(request, info, "system.shutdown")
    await ctx.writer.flush()
    return JSON(await priv(ctx, "system.shutdown"))


@router.post("/system/services/{name}/restart")
async def restart_service(
    request: Request,
    name: Literal["meshbox", "mosquitto", "meshbox-cloudflared"],
    info: SessionInfo = Depends(require_admin),
) -> Response:
    ctx = get_ctx(request)
    audit(request, info, "service.restart", name)
    return JSON(await priv(ctx, "service.restart", name=name))


# --------------------------------------------------------------------------- red


@router.get("/network/status")
async def network_status(request: Request, _: SessionInfo = Depends(require_admin)) -> Response:
    ctx = get_ctx(request)
    wifi = await priv(ctx, "wifi.status")
    timeinfo = await priv(ctx, "time.status")
    sysinfo = await priv(ctx, "system.info")
    from ...integrations.mosquitto import lan_ip

    return JSON(
        {
            "wifi": wifi,
            "time": timeinfo,
            "system": sysinfo,
            "lan_ip": lan_ip(),
            "managed": ctx.cfg.host.mode == "appliance",
        },
        headers=NO_STORE,
    )


@router.get("/network/wifi/scan")
async def wifi_scan(request: Request, _: SessionInfo = Depends(require_admin)) -> Response:
    return JSON(await priv(get_ctx(request), "wifi.scan"), headers=NO_STORE)


class WifiIn(BaseModel):
    ssid: str = Field(min_length=1, max_length=32)
    psk: str = Field(min_length=8, max_length=63)
    confirm: bool = False


@router.post("/network/wifi/connect")
async def wifi_connect(
    request: Request, body: WifiIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    shared_guard(ctx)
    if not body.confirm:
        raise ProblemError(
            400,
            "Confirmar: se puede perder la conexión con el panel (vuelve a la red anterior en 2 min si falla)",
        )
    audit(request, info, "wifi.connect", body.ssid)
    return JSON(await priv(ctx, "wifi.connect", ssid=body.ssid, psk=body.psk))


@router.delete("/network/wifi/{ssid}")
async def wifi_forget(
    request: Request, ssid: str, info: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    shared_guard(ctx)
    audit(request, info, "wifi.forget", ssid)
    return JSON(await priv(ctx, "wifi.forget", ssid=ssid))


class HotspotIn(BaseModel):
    enabled: bool


@router.post("/network/hotspot")
async def hotspot(
    request: Request, body: HotspotIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    shared_guard(ctx)
    audit(request, info, "hotspot.start" if body.enabled else "hotspot.stop")
    return JSON(await priv(ctx, "hotspot.start" if body.enabled else "hotspot.stop"))
