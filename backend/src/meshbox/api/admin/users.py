"""Usuarios, sesiones y auditoría (secciones 12.4, 13.2 y 18.2)."""

from __future__ import annotations

import time
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from starlette.responses import Response

from ...auth.passwords import MIN_LENGTH
from ...auth.sessions import SessionInfo
from ...auth.users import audit_page, create_user, get_user, list_users, set_password
from ..deps import audit, get_ctx, require_admin
from ..http import JSON, NO_STORE, ProblemError

router = APIRouter(prefix="/api/v1/admin", tags=["administración: usuarios"])


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=MIN_LENGTH, max_length=256)
    role: Literal["admin", "operator"] = "operator"
    must_change_password: bool = True


class UserPatch(BaseModel):
    role: Literal["admin", "operator"] | None = None
    disabled: bool | None = None
    password: str | None = Field(None, min_length=MIN_LENGTH, max_length=256)
    must_change_password: bool | None = None


@router.get("/users")
async def users(request: Request, _: SessionInfo = Depends(require_admin)) -> Response:
    return JSON({"users": await get_ctx(request).db.read(list_users)}, headers=NO_STORE)


@router.post("/users", status_code=201)
async def create(
    request: Request, body: UserIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    try:
        uid = await create_user(
            ctx.writer, body.username, body.password, body.role, body.must_change_password
        )
    except ValueError as e:
        raise ProblemError(422, str(e)) from None
    audit(request, info, "user.create", body.username.lower(), {"role": body.role})
    return JSON({"id": uid, "username": body.username.lower(), "role": body.role}, status_code=201)


async def _admins_left(ctx: object, excluding: int) -> int:
    def q(conn):  # type: ignore[no-untyped-def]
        return conn.execute(
            text("SELECT count(*) FROM users WHERE role = 'admin' AND disabled = 0 AND id != :i"),
            {"i": excluding},
        ).scalar_one()

    return int(await ctx.db.read(q))  # type: ignore[attr-defined]


@router.put("/users/{uid}")
async def update(
    request: Request, uid: int, body: UserPatch, info: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    user = await ctx.db.read(lambda c: get_user(c, user_id=uid))
    if user is None:
        raise ProblemError(404, "Usuario no encontrado")
    demoting = (body.role == "operator" and user["role"] == "admin") or (
        body.disabled and user["role"] == "admin"
    )
    if demoting and await _admins_left(ctx, uid) == 0:
        raise ProblemError(409, "Tiene que quedar al menos un administrador activo")
    if body.password:
        try:
            await set_password(
                ctx.writer, uid, user["username"], body.password, bool(body.must_change_password)
            )
        except ValueError as e:
            raise ProblemError(422, str(e)) from None
        await ctx.extensions["auth"].sessions.delete_user_sessions(uid)
    sets: list[str] = []
    params: dict[str, Any] = {"i": uid}
    if body.role is not None:
        sets.append("role = :r")
        params["r"] = body.role
    if body.disabled is not None:
        sets.append("disabled = :d")
        params["d"] = int(body.disabled)
    if body.must_change_password is not None and not body.password:
        sets.append("must_change_password = :m")
        params["m"] = int(body.must_change_password)
    if sets:
        await ctx.writer.run(
            lambda c: c.execute(text(f"UPDATE users SET {', '.join(sets)} WHERE id = :i"), params)
        )
    if body.disabled or body.role is not None:
        ctx.extensions["auth"].sessions.invalidate_user(uid)
        if body.disabled:
            await ctx.extensions["auth"].sessions.delete_user_sessions(uid)
    audit(
        request,
        info,
        "user.update",
        user["username"],
        body.model_dump(exclude={"password"}, exclude_none=True)
        | ({"password_changed": True} if body.password else {}),
    )
    updated = await ctx.db.read(lambda c: get_user(c, user_id=uid)) or {}
    return JSON({**updated, "password_hash": None})


@router.delete("/users/{uid}", status_code=204)
async def delete(
    request: Request, uid: int, info: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    if uid == info.user_id:
        raise ProblemError(409, "No se puede borrar el propio usuario")
    user = await ctx.db.read(lambda c: get_user(c, user_id=uid))
    if user is None:
        raise ProblemError(404, "Usuario no encontrado")
    if user["role"] == "admin" and await _admins_left(ctx, uid) == 0:
        raise ProblemError(409, "Tiene que quedar al menos un administrador activo")
    ctx.extensions["auth"].sessions.invalidate_user(uid)
    await ctx.writer.run(lambda c: c.execute(text("DELETE FROM users WHERE id = :i"), {"i": uid}))
    audit(request, info, "user.delete", user["username"])
    return Response(status_code=204)


@router.get("/sessions")
async def sessions(request: Request, info: SessionInfo = Depends(require_admin)) -> Response:
    items = await get_ctx(request).extensions["auth"].sessions.list_all()
    for s in items:
        s["current"] = info.token_hash.startswith(s["id"])
    return JSON({"sessions": items}, headers=NO_STORE)


@router.delete("/sessions/{sid}", status_code=204)
async def close_session(
    request: Request, sid: str, info: SessionInfo = Depends(require_admin)
) -> Response:
    ok = await get_ctx(request).extensions["auth"].sessions.delete_by_prefix(sid)
    if not ok:
        raise ProblemError(404, "Sesión no encontrada")
    audit(request, info, "session.close", sid)
    return Response(status_code=204)


@router.get("/audit")
async def audit_log(
    request: Request,
    before: float | None = None,
    action: str | None = Query(None, max_length=40),
    limit: int = Query(100, ge=1, le=500),
    _: SessionInfo = Depends(require_admin),
) -> Response:
    rows = await get_ctx(request).db.read(lambda c: audit_page(c, before, limit, action))
    nxt = rows[-1]["ts"] if len(rows) == limit else None
    return JSON({"entries": rows, "next": nxt, "now": time.time()}, headers=NO_STORE)
