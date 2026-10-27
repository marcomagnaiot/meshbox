"""Rutas públicas (sección 12.2): en el servidor público y en el de la LAN."""

from __future__ import annotations

import hashlib
import time
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from starlette.responses import Response

from .. import __version__
from ..models import node_num
from ..store import queries
from . import schemas
from .deps import get_ctx, ip_of
from .http import JSON, NO_STORE, ProblemError, json_no_store, parse_cursor
from .markdown import to_blocks


async def public_rate_limit(request: Request) -> None:
    allowed, retry = request.app.state.public_limit.hit(ip_of(request))
    if not allowed:
        raise ProblemError(
            429, "Demasiadas peticiones", headers={"Retry-After": str(int(retry) + 1)}
        )


router = APIRouter(prefix="/api/v1", tags=["público"], dependencies=[Depends(public_rate_limit)])
health_router = APIRouter(prefix="/api/v1", tags=["público"])

ESRI_ATTRIBUTION = {
    "name": "Esri World Imagery",
    "url": "https://www.esri.com",
    "text": "Imágenes © Esri, Maxar, Earthstar Geographics y la comunidad de usuarios de SIG",
}


def _hidden(ctx: Any) -> set[int]:
    return {n for n, r in ctx.state.nodes.items() if r.hidden}


def _node_or_404(ctx: Any, node: str) -> Any:
    try:
        num = node_num(node)
    except ValueError:
        raise ProblemError(404, "id de nodo no válido") from None
    rec = ctx.state.nodes.get(num)
    if rec is None or rec.hidden:
        raise ProblemError(404, "Nodo no encontrado")
    return rec


def site_payload(ctx: Any) -> dict[str, Any]:
    s = ctx.site
    tiles = ctx.extensions.get("tiles")
    has_tiles = bool(tiles and tiles.available)
    attributions = [
        {
            "name": "OpenStreetMap",
            "url": "https://www.openstreetmap.org/copyright",
            "text": "© colaboradores de OpenStreetMap",
        },
        {"name": "Protomaps", "url": "https://protomaps.com", "text": "Mapa base Protomaps (ODbL)"},
        {
            "name": "Meshtastic",
            "url": "https://meshtastic.org",
            "text": "Meshtastic® es una marca de Meshtastic LLC",
        },
    ]
    if s.satellite_enabled:
        attributions.append(ESRI_ATTRIBUTION)
    default_layer = s.default_layer
    if not has_tiles and default_layer != "satellite" and s.satellite_enabled:
        default_layer = "satellite"  # sin extracto se usa la capa satelital (16.5)
    plugins = ctx.extensions.get("plugins")
    alerts = ctx.extensions.get("alerts")
    push = alerts.push if alerts is not None else None
    return {
        "name": s.name,
        "description": s.description,
        "logo_url": "/api/v1/site/logo" if s.logo else None,
        "accent": s.accent,
        "center": s.center,
        "zoom": s.zoom,
        "bounds": s.bounds,
        "layers": {
            "dark": has_tiles,
            "light": has_tiles,
            "satellite": s.satellite_enabled,
            "default": default_layer,
        },
        "has_tiles": has_tiles,
        "thresholds": ctx.state.thresholds,
        "features": {
            "push": bool(push and push.available),
            "activity": s.activity_layer,
            "links": s.links_layer,
            "waypoints": s.waypoints_layer,
            "show_inactive": s.show_inactive,
            "tx": False,
        },
        "notice": to_blocks(s.notice_md),
        "public_channels": ctx.state.public_channel_names(),
        "timezone": ctx.cfg.site.timezone,
        "language": s.default_language,
        "languages": ["es", "en"],
        "version": __version__,
        "attributions": attributions,
        "plugin_layers": plugins.public_layers() if plugins is not None else [],
    }


@router.get("/site", response_model=schemas.Site)
async def get_site(request: Request) -> Response:
    ctx = get_ctx(request)
    from .http import dumps

    body = dumps({**site_payload(ctx), "server": request.app.state.kind})
    etag = '"' + hashlib.sha1(body, usedforsecurity=False).hexdigest()[:20] + '"'
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(body, media_type="application/json", headers=headers)


@router.get("/site/logo", include_in_schema=False)
async def get_logo(request: Request) -> Response:
    ctx = get_ctx(request)
    logo = ctx.site.logo
    if not logo:
        raise ProblemError(404)
    path = ctx.cfg.paths.db.parent / "site" / logo
    if not path.exists():
        raise ProblemError(404)
    media = (
        "image/png"
        if logo.endswith(".png")
        else "image/webp"
        if logo.endswith(".webp")
        else "image/svg+xml"
    )
    return Response(
        path.read_bytes(), media_type=media, headers={"Cache-Control": "public, max-age=3600"}
    )


@router.get("/nodes", response_model=schemas.NodeList)
async def list_nodes(request: Request) -> Response:
    ctx = get_ctx(request)
    # La foto lleva el seq del bus en este instante: el cliente aplica luego los eventos con seq mayor.
    return json_no_store({"seq": ctx.bus.seq, "ts": time.time(), "nodes": ctx.state.public_nodes()})


@router.get("/nodes/{node}", response_model=schemas.NodeDetail)
async def get_node(request: Request, node: str) -> Response:
    rec = _node_or_404(get_ctx(request), node)
    out = rec.public()
    out.update(
        firmware_version=rec.firmware_version,
        region=rec.region,
        modem_preset=rec.modem_preset,
        position_ts=rec.position_ts,
        metrics_ts=rec.metrics_ts,
    )
    return json_no_store(out)


@router.get("/nodes/{node}/positions", response_model=list[schemas.Position])
async def node_positions(
    request: Request,
    node: str,
    from_: Annotated[float | None, Query(alias="from")] = None,
    to: float | None = None,
    max_points: Annotated[int, Query(ge=10, le=5000)] = 500,
) -> Response:
    ctx = get_ctx(request)
    rec = _node_or_404(ctx, node)
    t_to = to or time.time()
    t_from = from_ if from_ is not None else t_to - 86400
    if t_to - t_from > 90 * 86400:
        raise ProblemError(400, "rango máximo de 90 días")
    rows = await ctx.db.read(lambda c: queries.node_positions(c, rec.num, t_from, t_to, max_points))
    return json_no_store(rows)


@router.get("/nodes/{node}/telemetry", response_model=schemas.TelemetrySeries)
async def node_telemetry(
    request: Request,
    node: str,
    kind: Literal["device", "environment", "power"] = "device",
    from_: Annotated[float | None, Query(alias="from")] = None,
    to: float | None = None,
) -> Response:
    ctx = get_ctx(request)
    rec = _node_or_404(ctx, node)
    t_to = to or time.time()
    t_from = from_ if from_ is not None else t_to - 86400
    if t_from >= t_to:
        raise ProblemError(400, "rango vacío")
    keep_s = ctx.cfg.retention.telemetry_raw * 86400
    data = await ctx.db.read(
        lambda c: queries.telemetry_series(c, rec.num, kind, t_from, t_to, keep_s)
    )
    return json_no_store(data)


@router.get("/nodes/{node}/links", response_model=list[schemas.Link])
async def node_links(request: Request, node: str, max_age: int = 7 * 86400) -> Response:
    ctx = get_ctx(request)
    rec = _node_or_404(ctx, node)
    rows = await ctx.db.read(lambda c: queries.links(c, max_age, _hidden(ctx), node=rec.num))
    return json_no_store(rows)


@router.get("/messages", response_model=schemas.MessagePage)
async def messages(
    request: Request, before: str | None = None, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> Response:
    ctx = get_ctx(request)
    cursor = parse_cursor(before)
    names = {n: (r.long_name or r.short_name) for n, r in ctx.state.nodes.items()}
    hidden = _hidden(ctx)
    rows, nxt = await ctx.db.read(lambda c: queries.messages_page(c, cursor, limit, names))
    rows = [m for m in rows if node_num(m["from"]) not in hidden]
    ids = await ctx.db.read(lambda c: queries.message_packet_ids(c, [m["pk"] for m in rows]))
    for m in rows:
        m["packet_id"] = ids.get(m["pk"])
    return json_no_store({"messages": rows, "next": nxt})


@router.get("/alerts", response_model=schemas.AlertPage)
async def alerts(
    request: Request, before: str | None = None, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> Response:
    ctx = get_ctx(request)
    cursor = parse_cursor(before)
    rows, nxt = await ctx.db.read(lambda c: queries.alerts_page(c, cursor, limit, public_only=True))
    return json_no_store({"alerts": rows, "next": nxt})


@router.get("/links", response_model=list[schemas.Link])
async def links(
    request: Request, max_age: Annotated[int, Query(ge=60, le=30 * 86400)] = 86400
) -> Response:
    ctx = get_ctx(request)
    return json_no_store(await ctx.db.read(lambda c: queries.links(c, max_age, _hidden(ctx))))


@router.get("/traceroutes", response_model=list[schemas.Traceroute])
async def traceroutes(
    request: Request, node: str | None = None, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> Response:
    ctx = get_ctx(request)
    num = _node_or_404(ctx, node).num if node else None
    return json_no_store(
        await ctx.db.read(lambda c: queries.traceroutes(c, num, limit, _hidden(ctx)))
    )


@router.get("/waypoints", response_model=list[schemas.Waypoint])
async def waypoints(request: Request) -> Response:
    ctx = get_ctx(request)
    return json_no_store(await ctx.db.read(lambda c: queries.waypoints(c, time.time())))


@router.get("/stats/summary", response_model=schemas.StatsSummary)
async def stats_summary(request: Request) -> Response:
    return json_no_store(get_ctx(request).state.summary())


@router.get("/stats/timeseries", response_model=schemas.TimeSeries)
async def stats_timeseries(
    request: Request,
    metric: Literal[
        "packets", "active_nodes", "new_nodes", "avg_channel_util", "by_portnum", "by_hops"
    ] = "active_nodes",
    range: Literal["24h", "7d", "30d"] = "24h",
) -> Response:
    ctx = get_ctx(request)
    return json_no_store(
        await ctx.db.read(lambda c: queries.stats_timeseries(c, metric, range, time.time()))
    )


@router.get("/stats/breakdown")
async def stats_breakdown(request: Request, range: Literal["24h", "7d", "30d"] = "24h") -> Response:
    """Totales del rango: paquetes por tipo, distribución de saltos y nodos que más retransmiten."""
    ctx = get_ctx(request)
    now = time.time()
    since = now - queries.RANGES[range]
    totals = await ctx.db.read(lambda c: queries.stats_totals(c, range, now))
    if not totals["by_portnum"]:  # aún sin agregados horarios: calcular en vivo
        totals["by_hops"] = await ctx.db.read(lambda c: queries.hops_distribution(c, since))
    totals["relays"] = await ctx.db.read(lambda c: queries.relays(c, since, ctx.state.nodes))
    totals["range"] = range
    return json_no_store(totals)


@health_router.get("/health", response_model=schemas.Health)
async def health(request: Request) -> Response:
    ctx = get_ctx(request)
    if not ctx.ready:
        return JSON(
            {"status": "starting", "version": __version__}, status_code=503, headers=NO_STORE
        )
    return JSON({"status": "ok", "version": __version__}, headers=NO_STORE)
