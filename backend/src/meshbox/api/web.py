"""Teselas (`/tiles`) y estáticos del frontend como SPA (secciones 12.1, 12.2 y 16.5)."""

from __future__ import annotations

import mimetypes
from pathlib import Path

import orjson
from fastapi import APIRouter, Request
from starlette.responses import FileResponse, HTMLResponse, Response

from .deps import get_ctx
from .http import JSON, ProblemError

tiles_router = APIRouter(prefix="/tiles", tags=["mapa"])
TILE_CACHE = "public, max-age=2592000"  # 30 días; la URL lleva la versión del extracto
ASSET_CACHE = "public, max-age=604800"


def web_dir(ctx: object) -> Path | None:
    cfg = getattr(ctx, "cfg")  # noqa: B009
    if cfg.paths.web is not None:
        return Path(cfg.paths.web)
    pkg = Path(__file__).resolve().parent.parent / "web"
    return pkg if (pkg / "index.html").exists() or (pkg / "200.html").exists() else None


@tiles_router.get("/v.json")
async def tilejson(request: Request) -> Response:
    ctx = get_ctx(request)
    store = ctx.extensions.get("tiles")
    if store is None or not store.available:
        raise ProblemError(404, "No hay extracto del mapa base descargado")
    tj = store.tilejson("")
    version = int(store.path.stat().st_mtime)
    tj["tiles"] = [f"/tiles/v/{{z}}/{{x}}/{{y}}.mvt?v={version}"]
    return JSON(tj, headers={"Cache-Control": "no-cache"})


@tiles_router.get("/v/{z}/{x}/{y}.mvt")
async def tile(request: Request, z: int, x: int, y: int) -> Response:
    ctx = get_ctx(request)
    store = ctx.extensions.get("tiles")
    if store is None or not store.available:
        return Response(status_code=204)
    data = store.get(z, x, y)
    if data is None:
        return Response(status_code=204, headers={"Cache-Control": TILE_CACHE})
    headers = {"Cache-Control": TILE_CACHE}
    if store.gzipped:
        headers["Content-Encoding"] = "gzip"
    return Response(data, media_type="application/vnd.mapbox-vector-tile", headers=headers)


def _asset(ctx: object, sub: str, rel: str) -> Response:
    base = web_dir(ctx)
    if base is None:
        raise ProblemError(404)
    root = (base / "tiles-assets" / sub).resolve()
    target = (root / rel).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise ProblemError(404)
    media = (
        "application/x-protobuf"
        if target.suffix == ".pbf"
        else mimetypes.guess_type(target.name)[0]
    )
    return FileResponse(
        target,
        media_type=media or "application/octet-stream",
        headers={"Cache-Control": ASSET_CACHE},
    )


@tiles_router.get("/fonts/{fontstack}/{rng}.pbf")
async def glyphs(request: Request, fontstack: str, rng: str) -> Response:
    # MapLibre pide "Fuente A,Fuente B": se usa la primera disponible.
    ctx = get_ctx(request)
    for font in fontstack.split(","):
        try:
            return _asset(ctx, "fonts", f"{font.strip()}/{rng}.pbf")
        except ProblemError:
            continue
    raise ProblemError(404)


@tiles_router.get("/sprites/{path:path}")
async def sprites(request: Request, path: str) -> Response:
    return _asset(get_ctx(request), "sprites", path)


# --------------------------------------------------------------------------- SPA

NOT_BUILT = """<!doctype html><html lang="es"><meta charset="utf-8"><title>meshbox</title>
<body style="font-family:system-ui;background:#111;color:#eee;padding:2rem">
<h1>meshbox</h1><p>El frontend no está compilado. Ejecutar <code>pnpm --dir frontend build</code>
o usar <code>./scripts/dev.ps1</code> en desarrollo.</p></body></html>"""


# El hostname de administración no instala la PWA: su service worker respondería "/" desde la
# caché (el mapa) en vez de pasar por el servidor, que manda al panel. Un 404 no alcanza
# (Chrome conserva el registro si la actualización falla): se sirve un service worker que se da
# de baja, borra la caché y recarga las pestañas.
SERVICE_WORKERS = ("service-worker.js", "sw.js")
KILL_SWITCH_SW = """// meshbox: el hostname de administración no usa PWA (ADR 0014).
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    await self.registration.unregister();
    const keys = await caches.keys();
    await Promise.all(keys.map((key) => caches.delete(key)));
    const windows = await self.clients.matchAll({ type: 'window' });
    for (const client of windows) client.navigate(client.url);
  })());
});
"""


def spa_response(
    request: Request, path: str, *, public_only: bool, admin_host: bool = False
) -> Response:
    ctx = get_ctx(request)
    clean = path.lstrip("/")
    if clean.startswith("api/") or clean == "api":
        raise ProblemError(404)
    first = clean.split("/", 1)[0]
    if public_only and first in ("admin", "setup"):
        raise ProblemError(404)
    if admin_host and clean in SERVICE_WORKERS:
        return Response(
            KILL_SWITCH_SW,
            media_type="application/javascript",
            headers={"Cache-Control": "no-cache"},
        )
    base = web_dir(ctx)
    if base is None:
        return HTMLResponse(NOT_BUILT, headers={"Cache-Control": "no-store"})
    if clean == "manifest.webmanifest":
        return manifest_response(ctx, base)
    root = base.resolve()
    if clean:
        target = (root / clean).resolve()
        if target.is_relative_to(root) and target.is_file():
            return static_file(request, target, clean)
        if "." in clean.rsplit("/", 1)[-1] and not clean.endswith(".html"):
            raise ProblemError(404)  # archivo inexistente (no es ruta de la app)
    for fallback in ("index.html", "200.html"):
        page = root / fallback
        if page.exists():
            return static_file(request, page, fallback)
    return HTMLResponse(NOT_BUILT, headers={"Cache-Control": "no-store"})


# Precomprimidos del build (adapter-static con precompress): se sirven sin gastar CPU de la Pi.
ENCODINGS = (("br", ".br"), ("gzip", ".gz"))


def accepted_encodings(header: str) -> set[str]:
    """Codificaciones aceptadas en `Accept-Encoding` (sin las que tienen q=0)."""
    out: set[str] = set()
    for part in header.split(","):
        token, _, params = part.strip().partition(";")
        q = params.strip()
        if q.startswith("q=") and q[2:].strip() in ("0", "0.0", "0.00", "0.000"):
            continue
        if token:
            out.add(token.strip().lower())
    return out


def static_file(request: Request, target: Path, rel: str) -> Response:
    media = "text/html" if target.suffix == ".html" else mimetypes.guess_type(target.name)[0]
    headers = {"Cache-Control": cache_for(rel), "Vary": "Accept-Encoding"}
    accepted = accepted_encodings(request.headers.get("accept-encoding", ""))
    for encoding, suffix in ENCODINGS:
        compressed = target.with_name(target.name + suffix)
        if encoding in accepted and compressed.is_file():
            headers["Content-Encoding"] = encoding
            return FileResponse(
                compressed, media_type=media or "application/octet-stream", headers=headers
            )
    return FileResponse(target, media_type=media, headers=headers)


def manifest_response(ctx: object, base: Path) -> Response:
    """Manifiesto de la PWA con el nombre y la descripción del sitio (el del build es genérico)."""
    try:
        data: dict[str, object] = orjson.loads((base / "manifest.webmanifest").read_bytes())
    except (OSError, orjson.JSONDecodeError):
        data = {}
    site = getattr(ctx, "site")  # noqa: B009
    data["name"] = site.name
    if len(site.name) <= 12:
        data["short_name"] = site.name
    data["description"] = site.description
    data["lang"] = site.default_language
    return Response(
        orjson.dumps(data),
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-cache"},
    )


def cache_for(rel: str) -> str:
    if rel.startswith("_app/immutable/"):
        return "public, max-age=31536000, immutable"
    if rel.endswith(".html"):
        # no-transform: que un proxy (Cloudflare) no inyecte scripts que la CSP bloquearía.
        return "no-cache, no-transform"
    if rel.endswith(("sw.js", "service-worker.js", "manifest.webmanifest", "version.json")):
        return "no-cache"
    return "public, max-age=3600"
