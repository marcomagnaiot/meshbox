"""Respaldos, exportación e importación de configuración y actualizaciones (11.6, 18.2, 23.5)."""

from __future__ import annotations

import asyncio
import base64
import os
import time
from typing import Any

import orjson
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from starlette.responses import FileResponse, Response

from ... import __version__
from ...auth.sessions import SessionInfo
from ...config import Config, config_to_dict
from ...store import backup as bk
from ..deps import audit, get_ctx, require_admin
from ..http import JSON, NO_STORE, ProblemError
from .site import read_body_limited

router = APIRouter(prefix="/api/v1/admin", tags=["administración: respaldos y actualizaciones"])
RESTORE_MAX = 512 * 1024 * 1024


@router.get("/backups")
async def backups(request: Request, _: SessionInfo = Depends(require_admin)) -> Response:
    ctx = get_ctx(request)
    items = [b.as_dict() for b in bk.list_backups(ctx.cfg.paths.backups)]
    return JSON({"backups": items, "db": ctx.db.size_bytes()}, headers=NO_STORE)


@router.post("/backups", status_code=201)
async def create_backup(request: Request, info: SessionInfo = Depends(require_admin)) -> Response:
    ctx = get_ctx(request)
    await ctx.writer.flush()
    b = await asyncio.to_thread(
        bk.create_backup, ctx.cfg.paths.db, ctx.cfg.paths.backups, "manual", ctx.cfg.paths.tmp
    )
    audit(request, info, "backup.create", b.name)
    return JSON(b.as_dict(), status_code=201)


@router.get("/backups/{name}")
async def download(
    request: Request, name: str, info: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    if not bk.valid_backup_name(name):
        raise ProblemError(404)
    path = ctx.cfg.paths.backups / name
    if not path.is_file():
        raise ProblemError(404, "Respaldo no encontrado")
    audit(request, info, "backup.download", name)
    return FileResponse(path, media_type="application/gzip", filename=name)


class RestoreIn(BaseModel):
    name: str
    confirm: bool = False


async def _restore(ctx: Any, gz_path: Any) -> None:
    """Detiene conectores, valida (integrity_check), reemplaza la base y recarga el estado."""
    await ctx.connectors.stop()
    ctx.processor.flush_dirty_nodes()
    await ctx.writer.stop()
    await ctx.db.dispose()
    try:
        await asyncio.to_thread(bk.restore_backup, gz_path, ctx.cfg.paths.db, ctx.cfg.paths.tmp)
    finally:
        from ...store.db import BatchWriter, Database
        from ...store.migrate import migrate

        await asyncio.to_thread(
            migrate, ctx.cfg.paths.db, ctx.cfg.paths.backups, __version__, ctx.cfg.paths.tmp
        )
        ctx.db = Database(ctx.cfg.paths.db)
        writer = BatchWriter(
            ctx.db,
            flush_interval_s=ctx.cfg.writer.flush_interval_s,
            flush_max_ops=ctx.cfg.writer.flush_max_ops,
            max_queue=ctx.cfg.writer.max_queue,
        )
        ctx.writer = writer
        ctx.processor.writer = writer
        writer.on_remap = ctx.processor.dedup.remap
        await writer.start()
        auth = ctx.extensions.get("auth")
        if auth is not None:
            auth.sessions.db, auth.sessions.writer = ctx.db, writer
            auth.sessions._cache.clear()
        await ctx.db.read(lambda c: ctx.state.load_from_db(c, ctx.secrets.get))
        await ctx.connectors.start()


@router.post("/backups/restore")
async def restore(
    request: Request, body: RestoreIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    if not body.confirm:
        raise ProblemError(400, "Confirmar la restauración (reemplaza todos los datos actuales)")
    if not bk.valid_backup_name(body.name) or not (ctx.cfg.paths.backups / body.name).is_file():
        raise ProblemError(404, "Respaldo no encontrado")
    audit(request, info, "backup.restore", body.name)
    await ctx.writer.flush()
    safety = await asyncio.to_thread(
        bk.create_backup, ctx.cfg.paths.db, ctx.cfg.paths.backups, "pre-restore", ctx.cfg.paths.tmp
    )
    try:
        await _restore(ctx, ctx.cfg.paths.backups / body.name)
    except ValueError as e:
        raise ProblemError(422, str(e)) from None
    return JSON({"ok": True, "restored": body.name, "safety_backup": safety.name})


@router.post("/backups/upload")
async def upload_and_restore(
    request: Request, info: SessionInfo = Depends(require_admin)
) -> Response:
    """Sube un `.db.gz` (cuerpo crudo) y lo restaura. `?confirm=1` obligatorio."""
    ctx = get_ctx(request)
    if request.query_params.get("confirm") != "1":
        raise ProblemError(400, "Confirmar la restauración con ?confirm=1")
    data = await read_body_limited(request, RESTORE_MAX)
    if data[:2] != b"\x1f\x8b":
        raise ProblemError(415, "Se espera un respaldo comprimido (.db.gz)")
    name = time.strftime("meshbox-%Y%m%d-%H%M%S-subido.db.gz")
    path = ctx.cfg.paths.backups / name
    path.write_bytes(data)
    audit(request, info, "backup.upload_restore", name)
    try:
        await _restore(ctx, path)
    except ValueError as e:
        path.unlink(missing_ok=True)
        raise ProblemError(422, str(e)) from None
    return JSON({"ok": True, "restored": name})


# --------------------------------------------------------------------------- configuración


def _encrypt(data: bytes, password: str) -> dict[str, str]:
    salt, nonce = os.urandom(16), os.urandom(12)
    key = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(password.encode())
    ct = AESGCM(key).encrypt(nonce, data, b"meshbox-secrets")

    def b64(b: bytes) -> str:
        return base64.b64encode(b).decode()

    return {
        "kdf": "scrypt-n15-r8-p1",
        "cipher": "aes-256-gcm",
        "salt": b64(salt),
        "nonce": b64(nonce),
        "data": b64(ct),
    }


def _decrypt(blob: dict[str, str], password: str) -> bytes:

    def d(k: str) -> bytes:
        return base64.b64decode(blob[k])

    key = Scrypt(salt=d("salt"), length=32, n=2**15, r=8, p=1).derive(password.encode())
    return AESGCM(key).decrypt(d("nonce"), d("data"), b"meshbox-secrets")


class ExportIn(BaseModel):
    include_secrets: bool = False
    password: str | None = Field(None, min_length=10, max_length=256)


@router.post("/config/export")
async def export_config(
    request: Request, body: ExportIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    """Exporta config.toml, ajustes, canales, reglas y cuentas MQTT. Los secretos solo cifrados."""
    ctx = get_ctx(request)

    def q(conn: Any) -> dict[str, Any]:
        def rows(sql: str) -> list[dict[str, Any]]:
            return [dict(r) for r in conn.execute(text(sql)).mappings().all()]

        return {
            "settings": rows("SELECT key, value FROM settings"),
            "channels": rows("SELECT name, key_ref, is_public FROM channels"),
            "alert_rules": rows(
                "SELECT name, kind, params, enabled, cooldown_s, channels, severity, is_public FROM alert_rules"
            ),
            "mqtt_accounts": rows("SELECT username, purpose, note FROM mqtt_accounts"),
            "plugins": rows("SELECT id, enabled, version, settings FROM plugins"),
        }

    data = {
        "format": "meshbox-config",
        "version": 1,
        "meshbox": __version__,
        "exported_at": time.time(),
        "config": config_to_dict(ctx.cfg),
        **(await ctx.db.read(q)),
    }
    if body.include_secrets:
        if not body.password:
            raise ProblemError(
                422, "Para incluir los secretos hace falta una contraseña (se cifran con ella)"
            )
        data["secrets_encrypted"] = _encrypt(
            orjson.dumps(ctx.secrets.data.model_dump()), body.password
        )
    audit(request, info, "config.export", None, {"include_secrets": body.include_secrets})
    name = time.strftime("meshbox-config-%Y%m%d-%H%M.json")
    return Response(
        orjson.dumps(data, option=orjson.OPT_INDENT_2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "no-store",
        },
    )


class ImportIn(BaseModel):
    data: dict[str, Any]
    password: str | None = None
    confirm: bool = False


@router.post("/config/import")
async def import_config(
    request: Request, body: ImportIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    if not body.confirm:
        raise ProblemError(400, "Confirmar la importación (reemplaza ajustes, canales y reglas)")
    d = body.data
    if d.get("format") != "meshbox-config":
        raise ProblemError(422, "El archivo no es una exportación de meshbox")
    try:
        new_cfg = Config(**d["config"])
    except Exception as e:
        raise ProblemError(422, f"config no válida: {e}") from None
    # se conservan rutas y puertos del equipo actual (la exportación puede venir de otro)
    new_cfg.paths, new_cfg.server, new_cfg.host, new_cfg.system = (
        ctx.cfg.paths,
        ctx.cfg.server,
        ctx.cfg.host,
        ctx.cfg.system,
    )
    if "secrets_encrypted" in d:
        if not body.password:
            raise ProblemError(422, "La exportación trae secretos cifrados: indicar la contraseña")
        try:
            plain = orjson.loads(_decrypt(d["secrets_encrypted"], body.password))
        except Exception:
            raise ProblemError(422, "Contraseña incorrecta o archivo dañado") from None
        from ...config import Secrets

        ctx.secrets.data = Secrets(**plain)
        ctx.secrets.save()
    now = time.time()

    def apply(conn: Any) -> None:
        conn.execute(text("DELETE FROM settings WHERE key NOT LIKE 'setup.%'"))
        for s in d.get("settings", []):
            conn.execute(
                text(
                    "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (:k, :v, :t)"
                ),
                {"k": s["key"], "v": s["value"], "t": now},
            )
        conn.execute(text("DELETE FROM channels"))
        for c in d.get("channels", []):
            conn.execute(
                text("INSERT INTO channels (name, key_ref, is_public) VALUES (:n, :r, :p)"),
                {"n": c["name"], "r": c.get("key_ref"), "p": int(c.get("is_public", 0))},
            )
        if d.get("alert_rules"):
            conn.execute(text("DELETE FROM alert_rules"))
            for r in d["alert_rules"]:
                conn.execute(
                    text(
                        "INSERT INTO alert_rules (name, kind, params, enabled, cooldown_s, channels, severity, is_public, "
                        "created_at, updated_at) VALUES (:name, :kind, :params, :enabled, :cooldown_s, :channels, "
                        ":severity, :is_public, :t, :t)"
                    ),
                    {**r, "t": now},
                )

    await ctx.writer.run(apply)
    ctx.cfg = new_cfg
    ctx.save_config()
    await ctx.db.read(lambda c: ctx.state.load_from_db(c, ctx.secrets.get))
    engine = ctx.extensions.get("alerts")
    if engine is not None:
        await engine.reload()
    audit(request, info, "config.import", None, {"secrets": "secrets_encrypted" in d})
    return JSON({"ok": True, "restart_recommended": True})


# --------------------------------------------------------------------------- actualizaciones


def _updates(ctx: Any) -> Any:
    from ...integrations.updates import Updates

    upd = ctx.extensions.get("updates")
    if upd is None:
        upd = Updates(ctx)
        ctx.extensions["updates"] = upd
    return upd


@router.get("/updates")
async def updates(
    request: Request, force: bool = False, _: SessionInfo = Depends(require_admin)
) -> Response:
    upd = _updates(get_ctx(request))
    if force:
        await upd.releases(force=True)
    return JSON(await upd.status(), headers=NO_STORE)


class InstallIn(BaseModel):
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    confirm: bool = False


@router.post("/updates/install", status_code=202)
async def install(
    request: Request, body: InstallIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    if not body.confirm:
        raise ProblemError(400, "Confirmar la actualización (el servicio se reinicia)")
    ctx = get_ctx(request)
    await ctx.writer.flush()
    audit(request, info, "update.install", body.version)
    result = await _updates(ctx).install(body.version)
    return JSON(result, status_code=202)


@router.get("/updates/jobs/{job}")
async def job(request: Request, job: str, _: SessionInfo = Depends(require_admin)) -> Response:
    return JSON(await _updates(get_ctx(request)).job_status(job), headers=NO_STORE)


class ConfirmIn(BaseModel):
    confirm: bool = False


@router.post("/updates/rollback")
async def rollback(
    request: Request, body: ConfirmIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    if not body.confirm:
        raise ProblemError(400, "Confirmar la vuelta a la versión anterior")
    ctx = get_ctx(request)
    audit(request, info, "update.rollback")
    return JSON(await _updates(ctx).rollback())


class UpdateSettingsIn(BaseModel):
    auto_check: bool
    source: str | None = Field(None, pattern=r"^https://", max_length=300)


@router.put("/updates/settings")
async def update_settings(
    request: Request, body: UpdateSettingsIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    ctx.cfg.updates.auto_check = body.auto_check
    if body.source:
        ctx.cfg.updates.source = body.source
    ctx.save_config()
    audit(request, info, "update.settings", None, body.model_dump())
    return JSON(ctx.cfg.updates.model_dump())
