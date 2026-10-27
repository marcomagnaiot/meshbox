"""Paquetes, nodos y mensajes (secciones 12.4 y 18.2): captura, moderación y bajas."""

from __future__ import annotations

import csv
import io
import time
from collections.abc import AsyncIterator, Iterator
from typing import Annotated, Any, Literal

import orjson
from fastapi import APIRouter, Depends, Query, Request
from google.protobuf.json_format import MessageToDict
from meshtastic.protobuf import mesh_pb2
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text
from starlette.responses import Response, StreamingResponse

from ...auth.sessions import SessionInfo
from ...models import BROADCAST, MessageModerated, NodeHidden, NodeUpserted, node_id, node_num
from ...pipeline.decode import decode_data, decoded_to_json
from ..deps import audit, get_ctx, require_operator
from ..http import JSON, NO_STORE, ProblemError, make_cursor, parse_cursor

router = APIRouter(prefix="/api/v1/admin", tags=["administración: paquetes, nodos y mensajes"])

PACKET_COLS = (
    "p.pk, p.from_num, p.packet_id, p.to_num, p.channel_index, p.channel_name, p.channel_hash, p.portnum, "
    "p.first_rx, p.hop_start, p.want_ack, p.priority, p.encrypted, p.decoded_ok, p.is_public, p.payload_len, "
    "(p.raw IS NOT NULL) AS has_raw, r.gateway, r.source, r.rx_snr, r.rx_rssi, r.hop_limit, r.relay_node, r.via_mqtt, "
    "(SELECT count(*) FROM receptions r2 WHERE r2.packet_pk = p.pk) AS receptions"
)
FIRST_RX_JOIN = (
    "LEFT JOIN receptions r ON r.packet_pk = p.pk AND r.rx_time = "
    "(SELECT min(r3.rx_time) FROM receptions r3 WHERE r3.packet_pk = p.pk)"
)


def _nid(value: str | None, field: str) -> int | None:
    if not value:
        return None
    if value == "^all":
        return BROADCAST
    try:
        return node_num(value)
    except ValueError:
        raise ProblemError(422, f"{field}: id de nodo no válido") from None


def _filters(
    portnum: str | None,
    from_: str | None,
    to: str | None,
    channel: str | None,
    gateway: str | None,
    min_snr: float | None,
    max_hops: int | None,
    q: str | None,
    since: float | None,
    names: dict[int, str],
) -> tuple[str, dict[str, Any]]:
    where = ["1=1"]
    params: dict[str, Any] = {}
    if portnum:
        if portnum == "ENCRYPTED":
            where.append("p.portnum IS NULL")
        else:
            where.append("p.portnum = :portnum")
            params["portnum"] = portnum
    if (f := _nid(from_, "from")) is not None:
        where.append("p.from_num = :from_num")
        params["from_num"] = f
    if (t := _nid(to, "to")) is not None:
        where.append("p.to_num = :to_num")
        params["to_num"] = t
    if channel:
        where.append("p.channel_name = :channel")
        params["channel"] = channel
    if gateway:
        where.append(
            "EXISTS (SELECT 1 FROM receptions g WHERE g.packet_pk = p.pk AND g.gateway = :gateway)"
        )
        params["gateway"] = gateway
    if min_snr is not None:
        where.append("r.rx_snr >= :min_snr")
        params["min_snr"] = min_snr
    if max_hops is not None:
        where.append("p.hop_start > 0 AND (p.hop_start - r.hop_limit) <= :max_hops")
        params["max_hops"] = max_hops
    if since is not None:
        where.append("p.first_rx >= :since")
        params["since"] = since
    if q:
        ql = q.lower()
        matches = [n for n, name in names.items() if name and ql in name.lower()]
        try:
            matches.append(node_num(q))
        except ValueError:
            pass
        if q.isdigit():
            where.append(
                "(p.packet_id = :qid OR p.from_num IN (%s))" % (",".join(map(str, matches)) or "-1")
            )
            params["qid"] = int(q)
        else:
            where.append("p.from_num IN (%s)" % (",".join(map(str, matches)) or "-1"))
    return " AND ".join(where), params


def _row(r: Any) -> dict[str, Any]:
    hops = (
        (r["hop_start"] - r["hop_limit"]) if r["hop_start"] and r["hop_limit"] is not None else None
    )
    return {
        "pk": r["pk"],
        "from": node_id(r["from_num"]),
        "to": "^all" if r["to_num"] == BROADCAST else node_id(r["to_num"]),
        "packet_id": r["packet_id"],
        "channel": r["channel_name"],
        "channel_index": r["channel_index"],
        "channel_hash": r["channel_hash"],
        "portnum": r["portnum"],
        "ts": r["first_rx"],
        "hop_start": r["hop_start"],
        "hops": hops,
        "want_ack": bool(r["want_ack"]),
        "priority": r["priority"],
        "encrypted": bool(r["encrypted"]),
        "decoded_ok": bool(r["decoded_ok"]),
        "is_public": bool(r["is_public"]),
        "payload_len": r["payload_len"],
        "has_raw": bool(r["has_raw"]),
        "gateway": r["gateway"],
        "source": r["source"],
        "snr": r["rx_snr"],
        "rssi": r["rx_rssi"],
        "relay_node": r["relay_node"],
        "via_mqtt": bool(r["via_mqtt"]),
        "receptions": r["receptions"],
    }


def _names(ctx: Any) -> dict[int, str]:
    return {n: (r.long_name or r.short_name or "") for n, r in ctx.state.nodes.items()}


@router.get("/packets")
async def packets(
    request: Request,
    portnum: str | None = None,
    from_: Annotated[str | None, Query(alias="from")] = None,
    to: str | None = None,
    channel: str | None = None,
    gateway: str | None = None,
    min_snr: float | None = None,
    max_hops: int | None = None,
    q: str | None = Query(None, max_length=64),
    before: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    _: SessionInfo = Depends(require_operator),
) -> Response:
    ctx = get_ctx(request)
    where, params = _filters(
        portnum, from_, to, channel, gateway, min_snr, max_hops, q, None, _names(ctx)
    )
    cur = parse_cursor(before)
    if cur is not None:
        where += " AND (p.first_rx < :bts OR (p.first_rx = :bts AND p.pk < :bpk))"
        params.update(bts=cur[0], bpk=cur[1])
    params["limit"] = limit + 1

    def q_(conn: Connection) -> list[Any]:
        return list(
            conn.execute(
                text(
                    f"SELECT {PACKET_COLS} FROM packets p {FIRST_RX_JOIN} WHERE {where} "
                    "ORDER BY p.first_rx DESC, p.pk DESC LIMIT :limit"
                ),
                params,
            )
            .mappings()
            .all()
        )

    rows = await ctx.db.read(q_)
    items = [_row(r) for r in rows[:limit]]
    nxt = (
        make_cursor(rows[limit - 1]["first_rx"], rows[limit - 1]["pk"])
        if len(rows) > limit
        else None
    )
    return JSON({"packets": items, "next": nxt}, headers=NO_STORE)


@router.get("/packets/export")
async def export(
    request: Request,
    format: Literal["csv", "jsonl"] = "csv",
    portnum: str | None = None,
    from_: Annotated[str | None, Query(alias="from")] = None,
    to: str | None = None,
    channel: str | None = None,
    gateway: str | None = None,
    since: float | None = None,
    _: SessionInfo = Depends(require_operator),
) -> Response:
    ctx = get_ctx(request)
    where, params = _filters(
        portnum, from_, to, channel, gateway, None, None, None, since, _names(ctx)
    )

    def q_(conn: Connection) -> list[dict[str, Any]]:
        rows = (
            conn.execute(
                text(
                    f"SELECT {PACKET_COLS} FROM packets p {FIRST_RX_JOIN} WHERE {where} "
                    "ORDER BY p.first_rx DESC LIMIT 100000"
                ),
                params,
            )
            .mappings()
            .all()
        )
        return [_row(r) for r in rows]

    rows = await ctx.db.read(q_)
    stamp = time.strftime("%Y%m%d-%H%M")

    def gen() -> Iterator[bytes]:
        if format == "jsonl":
            for r in rows:
                yield orjson.dumps(r) + b"\n"
            return
        buf = io.StringIO()
        if rows:
            w = csv.DictWriter(buf, fieldnames=list(rows[0]))
            w.writeheader()
            for r in rows:
                w.writerow(r)
                if buf.tell() > 64_000:
                    yield buf.getvalue().encode()
                    buf.seek(0)
                    buf.truncate()
        yield buf.getvalue().encode()

    media = "application/x-ndjson" if format == "jsonl" else "text/csv; charset=utf-8"
    return StreamingResponse(
        gen(),
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="meshbox-paquetes-{stamp}.{format}"'
        },
    )


@router.get("/packets/{pk}")
async def packet(request: Request, pk: int, _: SessionInfo = Depends(require_operator)) -> Response:
    ctx = get_ctx(request)

    def q_(conn: Connection) -> tuple[Any, list[Any], bytes | None]:
        row = (
            conn.execute(
                text(f"SELECT {PACKET_COLS} FROM packets p {FIRST_RX_JOIN} WHERE p.pk = :pk"),
                {"pk": pk},
            )
            .mappings()
            .first()
        )
        recs = (
            conn.execute(
                text("SELECT * FROM receptions WHERE packet_pk = :pk ORDER BY rx_time"), {"pk": pk}
            )
            .mappings()
            .all()
        )
        raw = conn.execute(text("SELECT raw FROM packets WHERE pk = :pk"), {"pk": pk}).scalar()
        return row, [dict(r) for r in recs], raw

    row, receptions, raw = await ctx.db.read(q_)
    if row is None:
        raise ProblemError(404, "Paquete no encontrado")
    out = _row(row)
    out["receptions_detail"] = receptions
    if raw:
        pkt = mesh_pb2.MeshPacket.FromString(raw)
        fields = MessageToDict(pkt, preserving_proto_field_name=True)
        fields.pop("decoded", None)
        fields.pop("encrypted", None)
        out["fields"] = fields
        out["hex"] = raw.hex()
        if pkt.HasField("decoded"):
            dec = decode_data(pkt.decoded)
            out["decoded"] = {
                "portnum": dec.portnum,
                "kind": dec.kind,
                "content": decoded_to_json(dec),
                "error": dec.error,
                "request_id": pkt.decoded.request_id or None,
                "reply_id": pkt.decoded.reply_id or None,
            }
        elif pkt.HasField("encrypted"):
            from ...pipeline.crypto import try_decrypt

            res = try_decrypt(pkt, ctx.state.channel_keys())
            if res is not None:
                dec = decode_data(res[0])
                out["decoded"] = {
                    "portnum": dec.portnum,
                    "kind": dec.kind,
                    "content": decoded_to_json(dec),
                    "channel": res[1].name,
                    "error": dec.error,
                }
    else:
        out["privacy_note"] = (
            "Solo se guardó el encabezado (privacidad: canal no público, dirigido o sin descifrar)"
        )
    return JSON(out, headers=NO_STORE)


# --------------------------------------------------------------------------- nodos


@router.get("/nodes")
async def nodes(request: Request, _: SessionInfo = Depends(require_operator)) -> Response:
    ctx = get_ctx(request)
    now = time.time()
    items = []
    for rec in ctx.state.nodes.values():
        d = rec.admin()
        d["status"] = ctx.state.status_of(rec, now)
        items.append(d)
    items.sort(key=lambda n: n["last_heard"], reverse=True)
    return JSON({"nodes": items, "seq": ctx.bus.seq}, headers=NO_STORE)


@router.get("/nodes/{nid}/battery")
async def node_battery(
    request: Request,
    nid: str,
    days: int = Query(2, ge=1, le=30),
    _: SessionInfo = Depends(require_operator),
) -> Response:
    """Tendencia de carga de la batería por día (placas con panel solar): ¿se recupera?"""
    from ...store.battery import battery_trend

    ctx = get_ctx(request)
    try:
        num = node_num(nid)
    except ValueError:
        raise ProblemError(404, "id de nodo no válido") from None
    if num not in ctx.state.nodes:
        raise ProblemError(404, "Nodo no encontrado")
    tz = ctx.cfg.site.timezone
    data = await ctx.db.read(lambda c: battery_trend(c, num, days, tz))
    data["node"] = node_id(num)
    return JSON(data, headers=NO_STORE)


class NodePatch(BaseModel):
    hidden: bool | None = None
    is_fixed: bool | None = None
    note: str | None = Field(None, max_length=500)


@router.patch("/nodes/{nid}")
async def patch_node(
    request: Request, nid: str, body: NodePatch, info: SessionInfo = Depends(require_operator)
) -> Response:
    ctx = get_ctx(request)
    try:
        num = node_num(nid)
    except ValueError:
        raise ProblemError(404, "id de nodo no válido") from None
    rec = ctx.state.nodes.get(num)
    if rec is None:
        raise ProblemError(404, "Nodo no encontrado")
    changes = body.model_dump(exclude_unset=True)
    if "hidden" in changes and changes["hidden"] is not None:
        rec.hidden = int(changes["hidden"])
        if rec.hidden:
            ctx.bus.publish(NodeHidden(node_id=rec.id))
    if "is_fixed" in changes and changes["is_fixed"] is not None:
        rec.is_fixed = int(changes["is_fixed"])
    if "note" in changes:
        rec.note = changes["note"] or None
    rec.updated_at = time.time()
    ctx.processor.mark_dirty(num)
    ctx.processor.flush_dirty_nodes()
    await ctx.writer.flush()
    if not rec.hidden:
        ctx.bus.publish(NodeUpserted(node=rec.public(), changed=tuple(changes)))
    audit(request, info, "node.update", rec.id, changes)
    return JSON(rec.admin())


class PurgeIn(BaseModel):
    confirm: bool = False


def purge_node_sql(conn: Connection, num: int) -> dict[str, int]:
    counts = {}
    for table, col in (
        ("positions", "node_num"),
        ("telemetry_device", "node_num"),
        ("telemetry_environment", "node_num"),
        ("telemetry_power", "node_num"),
        ("telemetry_rollup", "node_num"),
        ("messages", "from_num"),
        ("traceroutes", "from_num"),
        ("traceroutes", "to_num"),
        ("links", "node_num"),
        ("links", "neighbor_num"),
        ("packets", "from_num"),
        ("waypoints", "from_num"),
    ):
        counts[f"{table}.{col}"] = (
            conn.execute(text(f"DELETE FROM {table} WHERE {col} = :n"), {"n": num}).rowcount or 0
        )
    return counts


@router.delete("/nodes/{nid}/history")
async def purge_node(
    request: Request, nid: str, body: PurgeIn, info: SessionInfo = Depends(require_operator)
) -> Response:
    """Baja a pedido (sección 30): borra el historial del nodo (posiciones, telemetría, mensajes, enlaces, paquetes)."""
    ctx = get_ctx(request)
    if not body.confirm:
        raise ProblemError(400, "Confirmar el borrado del historial (no se puede deshacer)")
    try:
        num = node_num(nid)
    except ValueError:
        raise ProblemError(404, "id de nodo no válido") from None
    counts = await ctx.writer.run(lambda c: purge_node_sql(c, num))
    rec = ctx.state.nodes.get(num)
    if rec is not None:
        rec.lat = rec.lon = rec.alt = rec.position_ts = None
        rec.env = None
        rec.stored_pos = None
        ctx.processor.mark_dirty(num)
    audit(request, info, "node.purge", nid, counts)
    return JSON({"deleted": counts})


# --------------------------------------------------------------------------- mensajes


@router.get("/messages")
async def messages(
    request: Request,
    before: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    _: SessionInfo = Depends(require_operator),
) -> Response:
    ctx = get_ctx(request)
    cur = parse_cursor(before)
    params: dict[str, Any] = {"limit": limit + 1}
    where = "1=1"
    if cur is not None:
        where = "(ts < :bts OR (ts = :bts AND pk < :bpk))"
        params.update(bts=cur[0], bpk=cur[1])

    def q_(conn: Connection) -> list[Any]:
        return list(
            conn.execute(
                text(
                    f"SELECT * FROM messages WHERE {where} ORDER BY ts DESC, pk DESC LIMIT :limit"
                ),
                params,
            )
            .mappings()
            .all()
        )

    rows = await ctx.db.read(q_)
    names = _names(ctx)
    items = [
        {
            "pk": r["pk"],
            "ts": r["ts"],
            "from": node_id(r["from_num"]),
            "from_name": names.get(r["from_num"]) or None,
            "channel": r["channel_name"],
            "text": r["text"],
            "reply_id": r["reply_id"],
            "emoji": bool(r["emoji"]),
            "is_alert": bool(r["is_alert"]),
            "hidden": bool(r["hidden"]),
        }
        for r in rows[:limit]
    ]
    nxt = make_cursor(rows[limit - 1]["ts"], rows[limit - 1]["pk"]) if len(rows) > limit else None
    return JSON({"messages": items, "next": nxt}, headers=NO_STORE)


class MessagePatch(BaseModel):
    hidden: bool


@router.patch("/messages/{pk}")
async def moderate(
    request: Request, pk: int, body: MessagePatch, info: SessionInfo = Depends(require_operator)
) -> Response:
    ctx = get_ctx(request)
    n = await ctx.writer.run(
        lambda c: (
            c.execute(
                text("UPDATE messages SET hidden = :h WHERE pk = :pk"),
                {"h": int(body.hidden), "pk": pk},
            ).rowcount
        )
    )
    if not n:
        raise ProblemError(404, "Mensaje no encontrado")
    ctx.bus.publish(MessageModerated(pk=pk, hidden=body.hidden))
    audit(request, info, "message.hide" if body.hidden else "message.show", str(pk))
    return JSON({"pk": pk, "hidden": body.hidden})


async def _iter(rows: list[dict[str, Any]]) -> AsyncIterator[bytes]:  # pragma: no cover - reservado
    for r in rows:
        yield orjson.dumps(r) + b"\n"
