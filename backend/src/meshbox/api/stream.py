"""Tiempo real por Server-Sent Events (sección 12.3).

Protocolo sin pérdidas entre la foto inicial y el flujo: el cliente abre el stream, pide
`/api/v1/nodes` (que trae `seq`) y aplica después los eventos con `seq` mayor. Si un cliente
se atrasa y su cola desborda, se cierra el stream: el navegador reconecta solo y el cliente
vuelve a pedir la foto (nunca se pierden eventos en silencio).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

import orjson
from fastapi import APIRouter, Depends, Query, Request
from sse_starlette import EventSourceResponse, ServerSentEvent

from ..auth.sessions import SessionInfo
from ..models import (
    BROADCAST,
    AlertFired,
    AlertResolved,
    ConnectorStatusChanged,
    Diagnostic,
    Event,
    LinkObserved,
    LogEmitted,
    MessageAdded,
    MessageModerated,
    NodeHidden,
    NodeUpserted,
    PacketProcessed,
    PositionAdded,
    StatsUpdated,
    SystemStatus,
    TelemetryAdded,
    TracerouteAdded,
    WaypointChanged,
    node_id,
)
from .deps import get_ctx, ip_of, require_operator
from .http import ProblemError

PUBLIC_TYPES = (
    NodeUpserted,
    NodeHidden,
    PositionAdded,
    TelemetryAdded,
    MessageAdded,
    MessageModerated,
    AlertFired,
    AlertResolved,
    LinkObserved,
    StatsUpdated,
    PacketProcessed,
    WaypointChanged,
)
ADMIN_TYPES = (
    *PUBLIC_TYPES,
    ConnectorStatusChanged,
    SystemStatus,
    Diagnostic,
    LogEmitted,
    TracerouteAdded,
)

router = APIRouter(prefix="/api/v1", tags=["tiempo real"])


def dest(num: int) -> str:
    return "^all" if num == BROADCAST else node_id(num)


def public_event(ev: Event, activity: bool) -> tuple[str, dict[str, Any]] | None:
    seq = ev.seq
    match ev:
        case NodeUpserted():
            return "node", {"seq": seq, **ev.node}
        case NodeHidden():
            return "node_remove", {"seq": seq, "id": ev.node_id}
        case PositionAdded():
            return "position", {
                "seq": seq,
                "id": ev.node_id,
                "lat": ev.lat,
                "lon": ev.lon,
                "alt": ev.alt,
                "precision_m": ev.precision_m,
                "ts": ev.pos_ts,
            }
        case TelemetryAdded():
            return "telemetry", {
                "seq": seq,
                "id": ev.node_id,
                "kind": ev.kind,
                "values": ev.values,
                "ts": ev.tel_ts,
            }
        case MessageAdded():
            return "message", {"seq": seq, **ev.message}
        case MessageModerated():
            return ("message_remove" if ev.hidden else "message_restore"), {"seq": seq, "pk": ev.pk}
        case AlertFired() | AlertResolved():
            return ("alert", {"seq": seq, **ev.alert}) if ev.is_public else None
        case LinkObserved():
            return "link", {
                "seq": seq,
                "a": ev.a,
                "b": ev.b,
                "snr": ev.snr,
                "source": ev.source,
                "ts": ev.link_ts,
            }
        case StatsUpdated():
            return "stats", {"seq": seq, **ev.summary}
        case WaypointChanged():
            return "waypoint", {"seq": seq, "deleted": ev.deleted, **ev.waypoint}
        case PacketProcessed():
            if activity and ev.is_public and not ev.duplicate:
                return "activity", {
                    "portnum": ev.portnum,
                    "from": node_id(ev.from_num),
                    "to": dest(ev.to_num),
                    "hops": ev.hops,
                    "snr": ev.snr,
                    "gateway": ev.gateway,
                    "ts": ev.rx_time,
                }
            return None
    return None


def admin_event(ev: Event, filters: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    match ev:
        case PacketProcessed():
            if not filters.get("packets", True):
                return None
            if filters.get("portnum") and ev.portnum != filters["portnum"]:
                return None
            if filters.get("node") and filters["node"] not in (
                node_id(ev.from_num),
                node_id(ev.to_num),
            ):
                return None
            if filters.get("gateway") and ev.gateway != filters["gateway"]:
                return None
            return "packet", {
                "seq": ev.seq,
                "pk": ev.pk,
                "portnum": ev.portnum,
                "from": node_id(ev.from_num),
                "to": dest(ev.to_num),
                "packet_id": ev.packet_id,
                "channel": ev.channel,
                "hops": ev.hops,
                "snr": ev.snr,
                "rssi": ev.rssi,
                "gateway": ev.gateway,
                "source": ev.source,
                "connector": ev.connector_id,
                "is_public": ev.is_public,
                "encrypted": ev.encrypted,
                "decoded_ok": ev.decoded_ok,
                "duplicate": ev.duplicate,
                "via_mqtt": ev.via_mqtt,
                "ts": ev.rx_time,
            }
        case ConnectorStatusChanged():
            return "connector", {"seq": ev.seq, **ev.status}
        case SystemStatus():
            return "system", {"seq": ev.seq, **ev.metrics}
        case Diagnostic():
            return "diagnostic", {
                "seq": ev.seq,
                "code": ev.code,
                "message": ev.message,
                "details": ev.details,
                "ts": ev.ts,
            }
        case LogEmitted():
            return ("log", {"seq": ev.seq, **ev.record}) if filters.get("logs", True) else None
        case AlertFired() | AlertResolved():
            return "alert", {
                "seq": ev.seq,
                **ev.alert,
                "is_public": ev.is_public,
                "rule_id": ev.rule_id,
            }
        case TracerouteAdded():
            return "traceroute", {"seq": ev.seq, **ev.traceroute}
    return public_event(ev, activity=False)


class SseLimits:
    def __init__(self, max_total: int, max_per_ip: int) -> None:
        self.max_total = max_total
        self.max_per_ip = max_per_ip
        self.total = 0
        self.per_ip: dict[str, int] = defaultdict(int)

    def acquire(self, ip: str) -> bool:
        if self.total >= self.max_total or self.per_ip[ip] >= self.max_per_ip:
            return False
        self.total += 1
        self.per_ip[ip] += 1
        return True

    def release(self, ip: str) -> None:
        self.total = max(0, self.total - 1)
        self.per_ip[ip] -= 1
        if self.per_ip[ip] <= 0:
            self.per_ip.pop(ip, None)


def _ping() -> ServerSentEvent:
    return ServerSentEvent(comment="ping")


async def _pump(
    request: Request,
    sub: Any,
    translate: Any,
    max_per_s: int,
    on_close: Any,
    limited: str = "activity",
) -> AsyncIterator[ServerSentEvent]:
    window_start = time.monotonic()
    activity_count = 0
    try:
        yield ServerSentEvent(comment="conectado")
        while True:
            if sub.dropped:
                # Cliente atrasado: cerrar para que reconecte y vuelva a pedir la foto.
                yield ServerSentEvent(event="resync", data="{}")
                return
            try:
                ev = await asyncio.wait_for(sub.get(), 30)
            except TimeoutError:
                if await request.is_disconnected():
                    return
                continue
            out = translate(ev)
            if out is None:
                continue
            name, data = out
            if name == limited:
                now = time.monotonic()
                if now - window_start >= 1:
                    window_start, activity_count = now, 0
                activity_count += 1
                if activity_count > max_per_s:
                    continue
            yield ServerSentEvent(data=orjson.dumps(data).decode(), event=name, id=str(ev.seq))
    finally:
        sub.close()
        on_close()


@router.get("/stream", tags=["público"])
async def public_stream(request: Request, activity: int = 0) -> EventSourceResponse:
    ctx = get_ctx(request)
    limits: SseLimits = request.app.state.sse_limits
    ip = ip_of(request)
    if not limits.acquire(ip):
        raise ProblemError(429, "Demasiadas conexiones en vivo", headers={"Retry-After": "30"})
    ctx.sse_public_clients += 1
    sub = ctx.bus.subscribe(f"sse:{ip}", maxsize=500, types=PUBLIC_TYPES)
    want_activity = bool(activity)

    def closed() -> None:
        limits.release(ip)
        ctx.sse_public_clients -= 1

    return EventSourceResponse(
        _pump(
            request,
            sub,
            lambda ev: public_event(ev, want_activity),
            ctx.cfg.sse.activity_max_per_s,
            closed,
        ),
        ping=ctx.cfg.sse.heartbeat_s,
        ping_message_factory=_ping,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        send_timeout=30,
    )


@router.get("/admin/stream", tags=["administración"])
async def admin_stream(
    request: Request,
    session: SessionInfo = Depends(require_operator),
    packets: int = 1,
    logs: int = 1,
    portnum: str | None = None,
    node: str | None = None,
    gateway: str | None = None,
    max_packets_per_s: int = Query(20, ge=1, le=100),
) -> EventSourceResponse:
    ctx = get_ctx(request)
    ctx.sse_admin_clients += 1
    filters = {
        "packets": bool(packets),
        "logs": bool(logs),
        "portnum": portnum,
        "node": node,
        "gateway": gateway,
    }
    sub = ctx.bus.subscribe(f"admin-sse:{session.username}", maxsize=2000, types=ADMIN_TYPES)
    log_listener = None
    if logs:
        from ..system.logs import RING

        loop = asyncio.get_running_loop()

        def log_listener(item: dict[str, Any]) -> None:
            # Los registros pueden venir de otros hilos (librería serie): pasar al loop.
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(
                    sub.offer, LogEmitted(record=item, seq=ctx.bus.seq, ts=item["ts"])
                )

        RING.listeners.append(log_listener)

    def closed() -> None:
        ctx.sse_admin_clients -= 1
        if log_listener is not None:
            from ..system.logs import RING

            with contextlib.suppress(ValueError):
                RING.listeners.remove(log_listener)

    return EventSourceResponse(
        _pump(
            request,
            sub,
            lambda ev: admin_event(ev, filters),
            max_packets_per_s,
            closed,
            limited="packet",
        ),
        ping=ctx.cfg.sse.heartbeat_s,
        ping_message_factory=_ping,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        send_timeout=30,
    )
