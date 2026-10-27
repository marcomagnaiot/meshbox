"""Canales y claves (secciones 8, 10.2 y 18.2): la clave es de solo escritura."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text
from starlette.responses import Response

from ...auth.sessions import SessionInfo
from ...pipeline.crypto import channel_hash, decode_psk
from ..deps import audit, get_ctx, require_admin
from ..http import JSON, NO_STORE, ProblemError

router = APIRouter(prefix="/api/v1/admin/channels", tags=["administración: canales"])


class ChannelIn(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=11,
        description="nombre del canal (máximo 11 caracteres en Meshtastic)",
    )
    key: str | None = Field(
        None,
        max_length=64,
        description="base64; vacío/omitido = sin cambios; 'AQ==' = clave por defecto",
    )
    is_public: bool = False


async def _reload(ctx: Any) -> None:
    await ctx.db.read(lambda c: ctx.state.load_channels(c, ctx.secrets.get))


def _rows(conn: Connection) -> list[dict[str, Any]]:
    return [
        dict(r)
        for r in conn.execute(
            text("SELECT id, name, hash, key_ref, is_public FROM channels ORDER BY id")
        )
        .mappings()
        .all()
    ]


@router.get("")
async def list_channels(request: Request, _: SessionInfo = Depends(require_admin)) -> Response:
    ctx = get_ctx(request)
    rows = await ctx.db.read(_rows)
    out = [
        {
            "id": r["id"],
            "name": r["name"],
            "hash": r["hash"],
            "is_public": bool(r["is_public"]),
            "has_key": bool(r["key_ref"] and ctx.secrets.get(r["key_ref"])),
        }
        for r in rows
    ]
    return JSON({"channels": out}, headers=NO_STORE)


def _psk(key: str) -> bytes:
    try:
        return decode_psk(key)
    except ValueError as e:
        raise ProblemError(422, str(e)) from None


@router.post("", status_code=201)
async def create(
    request: Request, body: ChannelIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    key = body.key or "AQ=="
    psk = _psk(key)
    ref = f"channels.{body.name}"
    ctx.secrets.set(ref, key)
    h = channel_hash(body.name, psk)

    def ins(conn: Connection) -> int:
        if conn.execute(text("SELECT 1 FROM channels WHERE name = :n"), {"n": body.name}).first():
            raise ValueError("ya existe un canal con ese nombre")
        res = conn.execute(
            text("INSERT INTO channels (name, hash, key_ref, is_public) VALUES (:n, :h, :r, :p)"),
            {"n": body.name, "h": h, "r": ref, "p": int(body.is_public)},
        )
        return int(res.lastrowid or 0)

    try:
        cid = await ctx.writer.run(ins)
    except ValueError as e:
        raise ProblemError(409, str(e)) from None
    await _reload(ctx)
    audit(request, info, "channel.create", body.name, {"is_public": body.is_public})
    return JSON(
        {"id": cid, "name": body.name, "hash": h, "is_public": body.is_public, "has_key": True},
        status_code=201,
    )


@router.put("/{cid}")
async def update(
    request: Request, cid: int, body: ChannelIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    rows = {r["id"]: r for r in await ctx.db.read(_rows)}
    row = rows.get(cid)
    if row is None:
        raise ProblemError(404, "Canal no encontrado")
    ref = row["key_ref"] or f"channels.{body.name}"
    if body.name != row["name"]:
        old = ctx.secrets.get(ref)
        ctx.secrets.delete(ref, save=False)
        ref = f"channels.{body.name}"
        if old:
            ctx.secrets.set(ref, old, save=False)
        ctx.secrets.save()
    if body.key:
        _psk(body.key)
        ctx.secrets.set(ref, body.key)
    key = ctx.secrets.get(ref) or "AQ=="
    h = channel_hash(body.name, _psk(key))
    await ctx.writer.run(
        lambda c: c.execute(
            text(
                "UPDATE channels SET name = :n, hash = :h, key_ref = :r, is_public = :p WHERE id = :i"
            ),
            {"n": body.name, "h": h, "r": ref, "p": int(body.is_public), "i": cid},
        )
    )
    await _reload(ctx)
    audit(
        request,
        info,
        "channel.update",
        body.name,
        {"is_public": body.is_public, "key_changed": bool(body.key)},
    )
    return JSON(
        {"id": cid, "name": body.name, "hash": h, "is_public": body.is_public, "has_key": True}
    )


@router.delete("/{cid}", status_code=204)
async def delete(
    request: Request, cid: int, info: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    rows = {r["id"]: r for r in await ctx.db.read(_rows)}
    row = rows.get(cid)
    if row is None:
        raise ProblemError(404, "Canal no encontrado")
    await ctx.writer.run(
        lambda c: c.execute(text("DELETE FROM channels WHERE id = :i"), {"i": cid})
    )
    if row["key_ref"]:
        ctx.secrets.delete(row["key_ref"])
    await _reload(ctx)
    audit(request, info, "channel.delete", row["name"])
    return Response(status_code=204)
