"""Dependencias comunes de la API: contexto, IP del cliente, sesión, roles y CSRF."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import Depends, Request

from ..auth.sessions import COOKIE, SessionInfo, csrf_ok
from .http import ProblemError
from .security import client_ip

if TYPE_CHECKING:
    from ..app import Service

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def get_ctx(request: Request) -> Service:
    return request.app.state.ctx  # type: ignore[no-any-return]


def ip_of(request: Request) -> str:
    cached = getattr(request.state, "client_ip", None)
    if cached:
        return str(cached)
    ctx: Any = request.app.state.ctx
    ip = client_ip(
        request.scope.get("client"),
        {"cf-connecting-ip": request.headers.get("cf-connecting-ip", "")},
        ctx.cfg.server.trust_cf_headers_from,
    )
    request.state.client_ip = ip
    return ip


async def optional_session(request: Request) -> SessionInfo | None:
    if hasattr(request.state, "session"):
        return request.state.session  # type: ignore[no-any-return]
    ctx = get_ctx(request)
    auth = ctx.extensions.get("auth")
    info = await auth.sessions.get(request.cookies.get(COOKIE)) if auth is not None else None
    request.state.session = info
    return info


async def require_session(
    request: Request, info: SessionInfo | None = Depends(optional_session)
) -> SessionInfo:
    if info is None:
        raise ProblemError(401, "Iniciar sesión para continuar")
    if request.method in UNSAFE_METHODS and not csrf_ok(info, request.headers.get("x-csrf-token")):
        raise ProblemError(403, "Falta o no coincide el token CSRF (cabecera X-CSRF-Token)")
    ctx = get_ctx(request)
    auth = ctx.extensions.get("auth")
    if auth is not None:
        allowed, retry = auth.admin_limit.hit(info.token_hash)
        if not allowed:
            raise ProblemError(429, headers={"Retry-After": str(int(retry) + 1)})
    return info


async def require_operator(info: SessionInfo = Depends(require_session)) -> SessionInfo:
    if info.role not in ("admin", "operator"):
        raise ProblemError(403, "Rol sin permiso")
    return info


async def require_admin(info: SessionInfo = Depends(require_session)) -> SessionInfo:
    if info.role != "admin":
        raise ProblemError(403, "Solo administradores")
    return info


def audit(
    request: Request,
    info: SessionInfo | None,
    action: str,
    target: str | None = None,
    details: Any = None,
) -> None:
    from ..auth.users import audit as _audit

    ctx = get_ctx(request)
    _audit(ctx.writer, info.user_id if info else None, action, target, details, ip_of(request))
