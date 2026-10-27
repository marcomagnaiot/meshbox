"""Arma las aplicaciones ASGI de los servidores (sección 13.1).

- Público (`public_bind`): solo rutas públicas, estáticos y teselas. Destino del túnel.
- LAN (`lan_bind`): público + administración + asistente.
- Administración remota (`admin_remote_bind`, opcional): como la LAN, pero toda ruta de
  administración y del asistente exige un JWT válido de Cloudflare Access.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Literal

from fastapi import FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import RedirectResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .. import __version__
from .http import JSON, ProblemError, install_error_handlers, problem
from .ratelimit import RateLimiter
from .security import ScriptHashes, SecurityHeaders, build_csp
from .stream import SseLimits

if TYPE_CHECKING:
    from ..app import Service

Kind = Literal["public", "lan", "remote"]
ADMIN_PREFIXES = (
    "/api/v1/admin",
    "/api/v1/setup",
    "/admin",
    "/setup",
    "/api/docs",
    "/api/openapi.json",
)


class AccessGuard:
    """Servidor remoto: rutas de administración solo con JWT de Cloudflare Access válido."""

    def __init__(self, app: ASGIApp, service: Service) -> None:
        self.app = app
        self.service = service

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"].startswith(ADMIN_PREFIXES):
            headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
            auth = self.service.extensions.get("auth")
            validator = auth.access if auth is not None else None
            claims = (
                await validator.validate(headers.get("cf-access-jwt-assertion"))
                if validator
                else None
            )
            if claims is None:
                resp = problem(403, "Se requiere Cloudflare Access para administrar desde internet")
                await resp(scope, receive, send)
                return
            scope.setdefault("state", {})["access_email"] = claims.get("email")
        await self.app(scope, receive, send)


class RemotePasswordGuard:
    """Servidor remoto sin Cloudflare Access (ADR 0014): el panel con usuario y clave.

    Alternativa a Access, que pide cargar una tarjeta. Para achicar lo expuesto: el asistente `/setup`
    no existe por acá, y reiniciar o apagar el equipo (corta otros servicios del equipo) solo se
    puede desde la red local.
    """

    BLOCKED = ("/setup", "/api/v1/setup")
    LAN_ONLY = ("/api/v1/admin/system/reboot", "/api/v1/admin/system/shutdown")

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope["path"]
        if path.startswith(self.BLOCKED):
            await problem(404)(scope, receive, send)
            return
        if path.rstrip("/") in self.LAN_ONLY:
            resp = problem(
                403, "Por seguridad, reiniciar o apagar el equipo solo se puede desde la red local"
            )
            await resp(scope, receive, send)
            return

        async def send_noindex(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append((b"x-robots-tag", b"noindex, nofollow"))
            await send(message)

        await self.app(scope, receive, send_noindex)


class _TouchLan:
    """Registra la hora de la última petición en la LAN (apagado del punto de acceso sin uso)."""

    def __init__(self, app: ASGIApp, service: Service) -> None:
        self.app = app
        self.service = service

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            self.service.last_lan_request = time.time()
        await self.app(scope, receive, send)


def create_app(service: Service, kind: Kind) -> FastAPI:
    from . import public, stream, web

    app = FastAPI(
        title="meshbox",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        default_response_class=JSON,
    )
    app.state.ctx = service
    app.state.kind = kind
    app.state.public_limit = RateLimiter(300, 60)  # 300 peticiones/min por IP (12.5)
    app.state.push_limit = RateLimiter(5, 3600)  # 5 suscripciones por hora por IP
    app.state.sse_limits = SseLimits(
        service.cfg.sse.public_max_clients, service.cfg.sse.public_max_per_ip
    )
    install_error_handlers(app)
    # gzip para la API y lo que no venga precomprimido. Starlette no comprime SSE, imágenes,
    # fuentes ni respuestas que ya traen Content-Encoding (teselas, .br/.gz del build).
    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)

    app.include_router(public.health_router)
    app.include_router(public.router)
    app.include_router(stream.router if kind != "public" else _public_stream_only(stream))
    app.include_router(web.tiles_router)
    for router in _extension_routers(service, kind):
        app.include_router(router)
    if kind != "public":
        from .admin import routers as admin_routers

        for router in admin_routers():
            app.include_router(router)
        _openapi_routes(app, service)

    if kind == "remote":

        @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
        async def remote_root() -> Response:
            # El hostname de administración abre directo el panel (ADR 0014).
            return RedirectResponse("/admin", status_code=302)

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def spa(request: Request, path: str) -> Response:
        return web.spa_response(
            request, path, public_only=kind == "public", admin_host=kind == "remote"
        )

    @app.api_route(
        "/api/{path:path}", methods=["POST", "PUT", "PATCH", "DELETE"], include_in_schema=False
    )
    async def api_404(path: str) -> Response:
        raise ProblemError(404)

    hashes = ScriptHashes(lambda: web.web_dir(service))

    def csp() -> str:
        return build_csp(hashes.get(), satellite=service.site.satellite_enabled)

    asgi: Any = SecurityHeaders(app, csp)
    if kind == "lan":
        asgi = _TouchLan(asgi, service)
    if kind == "remote":
        if service.cfg.cloudflare.remote_admin_auth == "password":
            asgi = RemotePasswordGuard(asgi)
        else:
            asgi = AccessGuard(asgi, service)
    asgi.state_app = app  # para pruebas
    return asgi  # type: ignore[no-any-return]


def _public_stream_only(stream_module: Any) -> Any:
    from fastapi import APIRouter

    r = APIRouter(prefix="/api/v1")
    r.add_api_route("/stream", stream_module.public_stream, methods=["GET"], tags=["público"])
    return r


def _extension_routers(service: Service, kind: Kind) -> list[Any]:
    out: list[Any] = []
    try:
        from .push import router as push_router

        out.append(push_router)
    except ImportError:
        pass
    try:
        from .plugins_public import router as plugins_router

        out.append(plugins_router)
    except ImportError:
        pass
    if kind != "public":
        # Rutas de administración propias de cada plugin activo al arrancar (21.1).
        from fastapi import APIRouter, Depends

        from .deps import require_admin

        pm = service.extensions.get("plugins")
        for pid, lp in pm.plugins.items() if pm is not None else []:
            if lp.instance is None:
                continue
            try:
                prouter = lp.instance.router()
            except Exception:
                prouter = None
            if prouter is not None:
                wrapper = APIRouter(
                    prefix=f"/api/v1/admin/plugins/{pid}/api",
                    dependencies=[Depends(require_admin)],
                    tags=[f"plugin {pid}"],
                )
                wrapper.include_router(prouter)
                out.append(wrapper)
    return out


def _openapi_routes(app: FastAPI, service: Service) -> None:
    from fastapi import Depends

    from .deps import optional_session

    async def guard(request: Request) -> None:
        if service.dev:
            return
        info = await optional_session(request)
        if info is None or info.role != "admin":
            raise ProblemError(404)

    @app.get("/api/openapi.json", include_in_schema=False, dependencies=[Depends(guard)])
    async def openapi() -> Response:
        return JSON(app.openapi())

    @app.get("/api/docs", include_in_schema=False, dependencies=[Depends(guard)])
    async def docs() -> Response:
        html = get_swagger_ui_html(openapi_url="/api/openapi.json", title="meshbox API")
        html.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com"
        )
        return html


def create_apps(service: Service) -> list[tuple[str, Any]]:
    cfg = service.cfg
    apps: list[tuple[str, Any]] = []
    if cfg.server.public_bind:
        apps.append((cfg.server.public_bind, create_app(service, "public")))
    if cfg.server.lan_bind:
        apps.append((cfg.server.lan_bind, create_app(service, "lan")))
    if cfg.server.admin_remote_bind and cfg.cloudflare.admin_hostname:
        apps.append((cfg.server.admin_remote_bind, create_app(service, "remote")))
    return apps
