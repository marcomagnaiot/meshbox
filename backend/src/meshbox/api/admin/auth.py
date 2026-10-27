"""Autenticación del panel (secciones 12.4 y 13.2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from starlette.responses import Response

from ...auth.passwords import DUMMY_HASH, MIN_LENGTH, needs_rehash, verify_password_async
from ...auth.sessions import COOKIE, IDLE_S, SessionInfo
from ...auth.users import get_user, set_password
from ..deps import audit, get_ctx, ip_of, require_session
from ..http import JSON, NO_STORE, ProblemError

router = APIRouter(prefix="/api/v1/admin/auth", tags=["administración: sesión"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class PasswordIn(BaseModel):
    current: str = Field(min_length=1, max_length=256)
    new: str = Field(min_length=MIN_LENGTH, max_length=256)


def set_session_cookie(request: Request, response: Response, token: str) -> None:
    secure = request.url.scheme == "https" or request.app.state.kind == "remote"
    response.set_cookie(
        COOKIE, token, max_age=7 * 86400, httponly=True, samesite="strict", secure=secure, path="/"
    )


@router.post("/login")
async def login(request: Request, body: LoginIn) -> Response:
    ctx = get_ctx(request)
    auth = ctx.extensions["auth"]
    ip = ip_of(request)
    username = body.username.strip().lower()
    wait = auth.login_guard.check(ip, username)
    if wait > 0:
        raise ProblemError(
            429,
            "Demasiados intentos; esperar antes de reintentar",
            headers={"Retry-After": str(int(wait) + 1)},
        )
    user = await ctx.db.read(lambda c: get_user(c, username=username))
    stored = user["password_hash"] if user else DUMMY_HASH
    ok = await verify_password_async(stored, body.password)
    if not user or not ok or user["disabled"]:
        auth.login_guard.failure(username, ip)
        audit(request, None, "auth.login_failed", username)
        raise ProblemError(401, "Usuario o contraseña incorrectos")
    auth.login_guard.success(username)
    if needs_rehash(stored):
        await set_password(ctx.writer, user["id"], username, body.password)
    token, info = await auth.sessions.create(
        user["id"],
        user["username"],
        user["role"],
        bool(user["must_change_password"]),
        ip,
        request.headers.get("user-agent"),
    )
    audit(request, info, "auth.login", username)
    response = JSON({**info.public(), "idle_timeout_s": IDLE_S}, headers=NO_STORE)
    set_session_cookie(request, response, token)
    return response


@router.post("/logout")
async def logout(request: Request, info: SessionInfo = Depends(require_session)) -> Response:
    ctx = get_ctx(request)
    await ctx.extensions["auth"].sessions.delete_hash(info.token_hash)
    audit(request, info, "auth.logout", info.username)
    response = JSON({"ok": True}, headers=NO_STORE)
    response.delete_cookie(COOKIE, path="/")
    return response


@router.get("/me")
async def me(request: Request, info: SessionInfo = Depends(require_session)) -> Response:
    ctx = get_ctx(request)
    return JSON(
        {
            **info.public(),
            "mode": ctx.cfg.host.mode,
            "server": request.app.state.kind,
            "insecure_transport": request.url.scheme != "https"
            and request.app.state.kind != "remote",
            "tx_enabled": ctx.cfg.tx.enabled,
        },
        headers=NO_STORE,
    )


@router.post("/password")
async def change_password(
    request: Request, body: PasswordIn, info: SessionInfo = Depends(require_session)
) -> Response:
    ctx = get_ctx(request)
    user = await ctx.db.read(lambda c: get_user(c, user_id=info.user_id))
    if user is None or not await verify_password_async(user["password_hash"], body.current):
        raise ProblemError(400, "La contraseña actual no es correcta")
    try:
        await set_password(ctx.writer, info.user_id, info.username, body.new)
    except ValueError as e:
        raise ProblemError(422, str(e)) from None
    info.must_change_password = False
    await ctx.extensions["auth"].sessions.delete_user_sessions(
        info.user_id, except_hash=info.token_hash
    )
    audit(request, info, "auth.password", info.username)
    return JSON({"ok": True}, headers=NO_STORE)
