"""Sitio y mapa, privacidad y retención (secciones 12.4, 16.5, 18.2)."""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text
from starlette.responses import Response

from ...auth.sessions import SessionInfo
from ...config import PrivacyCfg, RetentionCfg
from ...settings import SITE_KEY, SiteSettings, put_setting
from ...store.retention import run_retention
from ...system.connect_proxy import ConnectProxy
from ..deps import audit, get_ctx, require_admin
from ..http import JSON, NO_STORE, ProblemError

router = APIRouter(prefix="/api/v1/admin", tags=["administración: sitio, mapa y privacidad"])
LOGO_MAX = 512 * 1024
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@router.get("/site")
async def get_site(request: Request, _: SessionInfo = Depends(require_admin)) -> Response:
    ctx = get_ctx(request)
    return JSON(
        {
            "site": ctx.site.model_dump(),
            "timezone": ctx.cfg.site.timezone,
            "slug": ctx.cfg.site.slug,
        },
        headers=NO_STORE,
    )


@router.put("/site")
async def put_site(
    request: Request, body: SiteSettings, info: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    data = body.model_dump()
    data["logo"] = ctx.site.logo  # el logo se cambia solo con POST /site/logo
    await put_setting(ctx.writer, ctx.state.settings, SITE_KEY, data)
    ctx.state.settings["status_thresholds"] = data["status_thresholds"]
    ctx.state.apply_thresholds()
    audit(
        request,
        info,
        "site.update",
        None,
        {k: data[k] for k in ("name", "default_layer", "satellite_enabled")},
    )
    return JSON({"site": data})


async def read_body_limited(request: Request, limit: int) -> bytes:
    """Cuerpo crudo con tope (sin multipart: evita una dependencia más)."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise ProblemError(413, f"El archivo supera {limit // 1024} KB")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise ProblemError(413, f"El archivo supera {limit // 1024} KB")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/site/logo")
async def upload_logo(request: Request, info: SessionInfo = Depends(require_admin)) -> Response:
    """Cuerpo crudo con el archivo. Solo PNG o WebP (nada de SVG: puede llevar scripts), hasta 512 KB."""
    ctx = get_ctx(request)
    data = await read_body_limited(request, LOGO_MAX)
    if data.startswith(PNG_MAGIC):
        ext = "png"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        ext = "webp"
    else:
        raise ProblemError(415, "Formato no admitido: subir PNG o WebP")
    folder = ctx.cfg.paths.db.parent / "site"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"logo-{uuid.uuid4().hex[:8]}.{ext}"
    (folder / name).write_bytes(data)
    site = ctx.site.model_dump()
    old = site.get("logo")
    site["logo"] = name
    await put_setting(ctx.writer, ctx.state.settings, SITE_KEY, site)
    if old and old != name:
        (folder / old).unlink(missing_ok=True)
    audit(request, info, "site.logo", name)
    return JSON({"logo": name})


@router.delete("/site/logo", status_code=204)
async def delete_logo(request: Request, info: SessionInfo = Depends(require_admin)) -> Response:
    ctx = get_ctx(request)
    site = ctx.site.model_dump()
    if site.get("logo"):
        (ctx.cfg.paths.db.parent / "site" / site["logo"]).unlink(missing_ok=True)
    site["logo"] = None
    await put_setting(ctx.writer, ctx.state.settings, SITE_KEY, site)
    audit(request, info, "site.logo.delete")
    return Response(status_code=204)


# --------------------------------------------------------------------------- extracto del mapa (16.5)


class TileJob:
    def __init__(self) -> None:
        self.state = "idle"
        self.progress: list[str] = []
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self.error: str | None = None
        self.bytes = 0
        self.task: asyncio.Task[None] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "progress": self.progress[-20:],
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "bytes": self.bytes,
        }


def _pmtiles_bin(ctx: Any) -> str:
    configured: Path = ctx.cfg.paths.pmtiles_bin
    if configured.exists():
        return str(configured)
    found = shutil.which("pmtiles")
    if found:
        return found
    home = Path.home() / ".meshbox" / "tools"
    if home.exists():
        for exe in sorted(home.glob("pmtiles-*/pmtiles*")):
            return str(exe)
    raise ProblemError(503, "No se encontró el binario pmtiles (/opt/meshbox/bin/pmtiles)")


async def latest_build() -> str:
    """URL del build diario más reciente de Protomaps (no se fija ninguna URL en el código)."""
    import httpx

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get("https://build-metadata.protomaps.dev/builds.json")
        r.raise_for_status()
        builds = r.json()
    if not builds:
        raise ProblemError(502, "Protomaps no listó builds")
    key = sorted(builds, key=lambda b: b["key"])[-1]["key"]
    return f"https://build.protomaps.com/{key}"


class TilesIn(BaseModel):
    bbox: list[float] = Field(min_length=4, max_length=4, description="[oeste, sur, este, norte]")
    maxzoom: int = Field(14, ge=6, le=15)
    source: str | None = Field(None, pattern=r"^https://[A-Za-z0-9./_-]+\.pmtiles$")


@router.get("/tiles/status")
async def tiles_status(request: Request, _: SessionInfo = Depends(require_admin)) -> Response:
    ctx = get_ctx(request)
    store = ctx.extensions.get("tiles")
    job: TileJob = ctx.extensions.setdefault("tiles_job", TileJob())
    return JSON(
        {"store": store.status() if store else None, "job": job.as_dict()}, headers=NO_STORE
    )


@router.post("/tiles/download")
async def tiles_download(
    request: Request, body: TilesIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    w, s, e, n = body.bbox
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90) or (e - w) * (n - s) > 25:
        raise ProblemError(422, "Caja no válida o demasiado grande (máximo ~5°×5°)")
    job: TileJob = ctx.extensions.setdefault("tiles_job", TileJob())
    if job.state == "running":
        raise ProblemError(409, "Ya hay una descarga en curso")
    binary = _pmtiles_bin(ctx)
    source = body.source or await latest_build()
    job.__init__()  # type: ignore[misc]
    job.state, job.started_at = "running", time.time()
    tmp_dir = ctx.cfg.paths.tmp
    tmp_dir.mkdir(parents=True, exist_ok=True)
    target = tmp_dir / f"region-{int(time.time())}.pmtiles"

    async def run() -> None:
        try:
            # pmtiles (Go) resuelve nombres con su propio DNS, que algunos routers rechazan:
            # el túnel pasa por un proxy local que resuelve con el del sistema.
            async with ConnectProxy(urlsplit(source).hostname or "") as proxy:
                proc = await asyncio.create_subprocess_exec(
                    binary,
                    "extract",
                    source,
                    str(target),
                    f"--bbox={w},{s},{e},{n}",
                    f"--maxzoom={body.maxzoom}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env={**os.environ, "HTTPS_PROXY": proxy, "https_proxy": proxy},
                )
                assert proc.stdout is not None
                async for line in proc.stdout:
                    job.progress.append(line.decode(errors="replace").strip()[-200:])
                    if target.exists():
                        job.bytes = target.stat().st_size
                rc = await proc.wait()
            if rc != 0:
                last = next((p for p in reversed(job.progress) if p), "")
                raise RuntimeError(
                    f"pmtiles terminó con código {rc}" + (f": {last}" if last else "")
                )
            # validar antes de reemplazar
            from ...tiles import TileStore

            probe_dir = tmp_dir / f"probe-{uuid.uuid4().hex[:6]}"
            probe_dir.mkdir()
            os.replace(target, probe_dir / "region.pmtiles")
            probe = TileStore(probe_dir)
            ok = probe.available
            probe.close()
            if not ok:
                raise RuntimeError("el extracto descargado no es válido")
            store = ctx.extensions.get("tiles")
            if store is not None:
                store.close()
            ctx.cfg.paths.tiles.mkdir(parents=True, exist_ok=True)
            os.replace(probe_dir / "region.pmtiles", ctx.cfg.paths.tiles / "region.pmtiles")
            shutil.rmtree(probe_dir, ignore_errors=True)
            if store is not None:
                store.open()
            job.bytes = (ctx.cfg.paths.tiles / "region.pmtiles").stat().st_size
            job.state = "done"
        except Exception as ex:
            job.state, job.error = "error", (str(ex) or type(ex).__name__)[:300]
            with contextlib.suppress(OSError):
                target.unlink(missing_ok=True)
        finally:
            job.finished_at = time.time()

    job.task = ctx._spawn(run(), "tiles-download")
    audit(
        request,
        info,
        "tiles.download",
        None,
        {"bbox": body.bbox, "maxzoom": body.maxzoom, "source": source},
    )
    return JSON({"job": job.as_dict(), "source": source}, status_code=202)


@router.delete("/tiles", status_code=204)
async def tiles_delete(request: Request, info: SessionInfo = Depends(require_admin)) -> Response:
    ctx = get_ctx(request)
    store = ctx.extensions.get("tiles")
    if store is not None:
        store.close()
    (ctx.cfg.paths.tiles / "region.pmtiles").unlink(missing_ok=True)
    audit(request, info, "tiles.delete")
    return Response(status_code=204)


# --------------------------------------------------------------------------- privacidad y retención


class PrivacyIn(BaseModel):
    privacy: PrivacyCfg
    retention: RetentionCfg


@router.get("/privacy")
async def get_privacy(request: Request, _: SessionInfo = Depends(require_admin)) -> Response:
    ctx = get_ctx(request)
    return JSON(
        {
            "privacy": ctx.cfg.privacy.model_dump(),
            "retention": ctx.cfg.retention.model_dump(),
            "notice_md": ctx.site.notice_md,
        },
        headers=NO_STORE,
    )


@router.put("/privacy")
async def put_privacy(
    request: Request, body: PrivacyIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    ctx.cfg.privacy = body.privacy
    ctx.cfg.retention = body.retention
    ctx.processor.cfg = ctx.cfg
    ctx.save_config()
    audit(request, info, "privacy.update", None, body.model_dump())
    return JSON(body.model_dump())


class PurgeIn(BaseModel):
    confirm: bool = False


@router.post("/privacy/purge")
async def purge(
    request: Request, body: PurgeIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    """Purga inmediata según la retención configurada (además de la tarea diaria de las 03:30)."""
    if not body.confirm:
        raise ProblemError(400, "Confirmar la purga")
    ctx = get_ctx(request)
    totals = await run_retention(ctx.writer.run, ctx.cfg.retention)

    def hidden_purge(conn: Connection) -> int:
        nums = [r[0] for r in conn.execute(text("SELECT num FROM nodes WHERE hidden = 1")).all()]
        from .packets import purge_node_sql

        return sum(sum(purge_node_sql(conn, n).values()) for n in nums)

    totals["hidden_nodes_rows"] = await ctx.writer.run(hidden_purge)
    audit(request, info, "privacy.purge", None, totals)
    return JSON({"deleted": totals})
