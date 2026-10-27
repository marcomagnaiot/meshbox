"""Carga y ejecución de plugins (sección 21).

Incluidos: `meshbox/plugins/builtin/<id>/`. Del usuario: `/var/lib/meshbox/plugins/<id>/`
(se instalan copiando la carpeta). Estado y ajustes en la tabla `plugins`; los campos
secretos (`writeOnly`) van a `secrets.toml` y nunca se devuelven.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import importlib.util
import logging
import sys
import time
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import orjson
from sqlalchemy import Connection, text

from ..config import SECRET_MASK
from ..models import Event
from .api import (
    API_VERSION,
    LAYER_STYLES,
    PERMISSIONS,
    LayerDecl,
    Manifest,
    PluginBase,
    PluginContext,
    SettingsError,
    secret_fields,
    validate_settings,
)

if TYPE_CHECKING:
    from ..app import Service

log = logging.getLogger(__name__)
BUILTIN_DIR = Path(__file__).parent / "builtin"
SETUP_TIMEOUT_S = 20


def read_manifest(folder: Path, builtin: bool) -> Manifest:
    data = tomllib.loads((folder / "plugin.toml").read_text(encoding="utf-8"))
    schema: dict[str, Any] = {}
    if data.get("settings_schema"):
        schema = orjson.loads((folder / data["settings_schema"]).read_bytes())
    perms = list(data.get("permissions", []))
    bad = set(perms) - PERMISSIONS
    if bad:
        raise ValueError(f"permisos desconocidos: {', '.join(sorted(bad))}")
    layers = []
    for layer in data.get("map_layers", []):
        decl = LayerDecl(
            id=layer["id"],
            name=layer.get("name", layer["id"]),
            geometry=layer.get("geometry", "point"),
            style=layer.get("style", "point"),
            refresh_s=int(layer.get("refresh_s", 900)),
        )
        if decl.style not in LAYER_STYLES:
            raise ValueError(f"estilo de capa desconocido: {decl.style}")
        layers.append(decl)
    manifest = Manifest(
        id=str(data["id"]),
        name=str(data.get("name", data["id"])),
        version=str(data.get("version", "0.0.0")),
        api_version=int(data.get("api_version", 1)),
        entrypoint=str(data["entrypoint"]),
        permissions=perms,
        settings_schema=schema,
        map_layers=layers,
        description=str(data.get("description", "")),
        builtin=builtin,
        path=str(folder),
    )
    if manifest.id != folder.name:
        raise ValueError(f"el id {manifest.id} no coincide con la carpeta {folder.name}")
    if manifest.api_version != API_VERSION:
        raise ValueError(
            f"api_version {manifest.api_version} no soportada (se espera {API_VERSION})"
        )
    return manifest


class LoadedPlugin:
    def __init__(self, manifest: Manifest) -> None:
        self.manifest = manifest
        self.instance: PluginBase | None = None
        self.ctx: PluginContext | None = None
        self.error: str | None = None
        self.enabled = False
        self.settings: dict[str, Any] = {}
        self.queue: asyncio.Queue[Event] | None = None
        self.task: asyncio.Task[None] | None = None
        self.layer_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self.sub_app: Any = None


class PluginManager:
    def __init__(self, service: Service) -> None:
        self.service = service
        self.plugins: dict[str, LoadedPlugin] = {}
        self._sub: Any = None
        self._dispatch_task: asyncio.Task[None] | None = None

    # ---------------------------------------------------------------- descubrimiento

    def discover(self) -> None:
        found: dict[str, LoadedPlugin] = {}
        for base, builtin in ((BUILTIN_DIR, True), (self.service.cfg.paths.plugins, False)):
            if not base.exists():
                continue
            for folder in sorted(p for p in base.iterdir() if (p / "plugin.toml").exists()):
                try:
                    m = read_manifest(folder, builtin)
                except Exception as e:
                    log.warning("plugin en %s no válido: %s", folder, e)
                    continue
                if m.id in found:
                    log.warning("plugin %s duplicado: se usa el incluido", m.id)
                    continue
                found[m.id] = self.plugins.get(m.id) or LoadedPlugin(m)
                found[m.id].manifest = m
        self.plugins = found

    async def _db_rows(self) -> dict[str, dict[str, Any]]:
        def q(conn: Connection) -> dict[str, dict[str, Any]]:
            return {
                r["id"]: dict(r)
                for r in conn.execute(text("SELECT * FROM plugins")).mappings().all()
            }

        return await self.service.db.read(q)

    # ---------------------------------------------------------------- ciclo de vida

    async def start(self) -> None:
        self.discover()
        rows = await self._db_rows()
        for pid, lp in self.plugins.items():
            row = rows.get(pid)
            lp.settings = orjson.loads(row["settings"]) if row else {}
            lp.enabled = bool(row and row["enabled"])
            if lp.enabled:
                await self._start_plugin(lp)
        if any("events.read" in lp.manifest.permissions for lp in self.plugins.values()):
            self._sub = self.service.bus.subscribe("plugins", maxsize=2000)
            self._dispatch_task = asyncio.create_task(self._dispatch())

    async def stop(self) -> None:
        if self._dispatch_task is not None:
            self._dispatch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._dispatch_task
        if self._sub is not None:
            self._sub.close()
        for lp in self.plugins.values():
            await self._stop_plugin(lp)

    def _secrets_for(self, pid: str) -> dict[str, str]:
        return dict(self.service.secrets.data.plugins.get(pid, {}))

    def _validated(self, m: Manifest, plain: dict[str, Any]) -> dict[str, Any]:
        """Valida los ajustes contando los secretos guardados aparte (no viajan en `plain`)."""
        stored = self._secrets_for(m.id)
        with_secrets = {
            **plain,
            **{k: stored[k] for k in secret_fields(m.settings_schema) if stored.get(k)},
        }
        settings = validate_settings(m.settings_schema, with_secrets)
        return {k: v for k, v in settings.items() if k not in secret_fields(m.settings_schema)}

    def _import(self, manifest: Manifest) -> type[PluginBase]:
        module_name, _, cls_name = manifest.entrypoint.partition(":")
        if manifest.builtin:
            module = importlib.import_module(f"meshbox.plugins.builtin.{module_name}")
        else:
            base = str(Path(manifest.path).parent)
            if base not in sys.path:
                sys.path.insert(0, base)
            module = importlib.import_module(module_name)
        cls = getattr(module, cls_name)
        if not (isinstance(cls, type) and issubclass(cls, PluginBase)):
            raise TypeError("el punto de entrada no es una subclase de PluginBase")
        return cls

    async def _start_plugin(self, lp: LoadedPlugin) -> None:
        m = lp.manifest
        try:
            settings = self._validated(m, lp.settings)
            cls = self._import(m)
            instance = cls()
            ctx = PluginContext(self.service, m, settings, self._secrets_for(m.id))
            await asyncio.wait_for(instance.setup(ctx), SETUP_TIMEOUT_S)
        except Exception as e:
            lp.error = f"{type(e).__name__}: {e}"
            lp.instance = None
            log.warning("plugin %s no arrancó: %s", m.id, lp.error)
            return
        lp.instance, lp.ctx, lp.error = instance, ctx, None
        lp.layer_cache.clear()
        if "events.read" in m.permissions:
            lp.queue = asyncio.Queue(500)
            lp.task = asyncio.create_task(self._plugin_events(lp))
        log.info("plugin %s %s activo", m.id, m.version)

    async def _stop_plugin(self, lp: LoadedPlugin) -> None:
        if lp.task is not None:
            lp.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await lp.task
            lp.task = None
        if lp.instance is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(lp.instance.teardown(), 10)
        if lp.ctx is not None:
            await lp.ctx.close()
        lp.instance = lp.ctx = lp.queue = lp.sub_app = None

    async def _dispatch(self) -> None:
        while True:
            ev = await self._sub.get()
            for lp in self.plugins.values():
                if lp.queue is not None:
                    with contextlib.suppress(asyncio.QueueFull):
                        lp.queue.put_nowait(ev)

    async def _plugin_events(self, lp: LoadedPlugin) -> None:
        assert lp.queue is not None
        while True:
            ev = await lp.queue.get()
            if lp.instance is None:
                continue
            try:
                await asyncio.wait_for(lp.instance.on_event(ev), 10)
            except Exception as e:
                if lp.ctx:
                    lp.ctx.log.warning("on_event falló: %s", e)

    # ---------------------------------------------------------------- panel

    def describe(self, lp: LoadedPlugin) -> dict[str, Any]:
        m = lp.manifest
        secrets = secret_fields(m.settings_schema)
        stored = self._secrets_for(m.id)
        settings = {k: v for k, v in lp.settings.items() if k not in secrets}
        for k in secrets:
            settings[k] = SECRET_MASK if stored.get(k) else ""
        return {
            "id": m.id,
            "name": m.name,
            "version": m.version,
            "description": m.description,
            "builtin": m.builtin,
            "permissions": m.permissions,
            "enabled": lp.enabled,
            "running": lp.instance is not None,
            "error": lp.error,
            "settings": settings,
            "settings_schema": m.settings_schema,
            "layers": [
                {"id": la.id, "name": la.name, "geometry": la.geometry, "style": la.style}
                for la in m.map_layers
            ],
        }

    async def update(
        self, pid: str, enabled: bool | None, settings: dict[str, Any] | None
    ) -> dict[str, Any]:
        lp = self.plugins.get(pid)
        if lp is None:
            raise KeyError(pid)
        m = lp.manifest
        if settings is not None:
            secrets = secret_fields(m.settings_schema)
            plain = {k: v for k, v in settings.items() if k not in secrets}
            for k in secrets:
                v = settings.get(k)
                if isinstance(v, str) and v and v != SECRET_MASK:
                    self.service.secrets.data.plugins.setdefault(pid, {})[k] = v
            self.service.secrets.save()
            merged_for_check = {
                **plain,
                **{k: "x" for k in secrets if self._secrets_for(pid).get(k)},
            }
            try:
                validate_settings(m.settings_schema, merged_for_check)
            except SettingsError as e:
                raise ValueError(str(e)) from e
            lp.settings = plain
        if enabled is not None:
            lp.enabled = enabled
        row = {
            "id": pid,
            "e": int(lp.enabled),
            "v": m.version,
            "s": orjson.dumps(lp.settings).decode(),
            "t": time.time(),
        }
        await self.service.writer.run(
            lambda c: c.execute(
                text(
                    "INSERT INTO plugins (id, enabled, version, settings, installed_at) VALUES (:id, :e, :v, :s, :t) "
                    "ON CONFLICT(id) DO UPDATE SET enabled = excluded.enabled, version = excluded.version, "
                    "settings = excluded.settings"
                ),
                row,
            )
        )
        await self._stop_plugin(lp)
        if lp.enabled:
            await self._start_plugin(lp)
        if lp.enabled and lp.queue is not None and self._sub is None:
            self._sub = self.service.bus.subscribe("plugins", maxsize=2000)
            self._dispatch_task = asyncio.create_task(self._dispatch())
        return self.describe(lp)

    def logs(self, pid: str) -> list[dict[str, Any]]:
        lp = self.plugins.get(pid)
        if lp is None or lp.ctx is None:
            return []
        return list(lp.ctx.log_handler.records)

    # ---------------------------------------------------------------- capas públicas

    def public_layers(self) -> list[dict[str, Any]]:
        out = []
        for pid, lp in self.plugins.items():
            if lp.instance is None or "map.layers" not in lp.manifest.permissions:
                continue
            for la in lp.manifest.map_layers:
                out.append(
                    {
                        "plugin": pid,
                        "id": la.id,
                        "name": la.name,
                        "geometry": la.geometry,
                        "style": la.style,
                        "refresh_s": la.refresh_s,
                        "url": f"/api/v1/plugins/{pid}/layers/{la.id}",
                    }
                )
        return out

    async def layer(self, pid: str, layer_id: str) -> dict[str, Any] | None:
        lp = self.plugins.get(pid)
        if lp is None or lp.instance is None or "map.layers" not in lp.manifest.permissions:
            return None
        decl = next((la for la in lp.manifest.map_layers if la.id == layer_id), None)
        if decl is None:
            return None
        cached = lp.layer_cache.get(layer_id)
        if cached and time.time() - cached[0] < decl.refresh_s:
            return cached[1]
        try:
            data = await asyncio.wait_for(lp.instance.layer(layer_id), 30)
        except Exception as e:
            if lp.ctx:
                lp.ctx.log.warning("capa %s falló: %s", layer_id, e)
            return cached[1] if cached else {"type": "FeatureCollection", "features": []}
        if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
            data = {"type": "FeatureCollection", "features": []}
        lp.layer_cache[layer_id] = (time.time(), data)
        return data

    # ---------------------------------------------------------------- rutas propias

    def sub_app(self, pid: str) -> Any:
        lp = self.plugins.get(pid)
        if lp is None or lp.instance is None:
            return None
        if lp.sub_app is None:
            router = lp.instance.router()
            if router is None:
                return None
            from fastapi import FastAPI

            app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
            app.include_router(router)
            lp.sub_app = app
        return lp.sub_app


def make_plugins(service: Service) -> PluginManager:
    return PluginManager(service)
