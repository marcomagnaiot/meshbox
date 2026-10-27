"""Servicio completo: ciclo de vida, tareas periódicas y servidores HTTP (secciones 5, 13.1, 23.4, 29).

Los servidores son instancias de `uvicorn.Server` en el mismo loop, sin manejadores de
señales propios: un único manejador de SIGTERM/SIGINT marca `should_exit` en todos, detiene
los conectores y vacía el escritor antes de salir.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import logging
import signal
import sys
import time
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import uvicorn
from sqlalchemy import text

from . import __version__
from .bus import EventBus
from .config import Config, SecretStore, parse_bind, save_config
from .connectors.manager import ConnectorManager
from .models import Diagnostic, StatsUpdated, SystemStatus
from .pipeline.process import Processor
from .radio.messages import MessageStore
from .settings import SiteSettings, load_site
from .state import MeshState
from .store import rollups
from .store.db import BatchWriter, Database
from .store.migrate import migrate, migrate_in_subprocess, pending
from .store.retention import maintenance, run_retention
from .system.metrics import MemoryGuard, Metrics
from .system.privclient import FakePrivClient, PrivClient, make_privclient
from .system.sdnotify import notify, watchdog_interval_s

log = logging.getLogger(__name__)


class Service:
    """Contenedor de todos los módulos. La API lo recibe en `app.state.ctx`."""

    def __init__(self, cfg: Config, config_path: Path | None, *, dev: bool = False) -> None:
        self.cfg = cfg
        self.config_path = config_path
        self.dev = dev
        self.version = __version__
        self.started_at = time.time()
        self.ready = False
        self.secrets = SecretStore(cfg.paths.secrets)
        self.bus = EventBus()
        self.state = MeshState()
        self.db = Database(cfg.paths.db)
        self.writer = BatchWriter(
            self.db,
            flush_interval_s=cfg.writer.flush_interval_s,
            flush_max_ops=cfg.writer.flush_max_ops,
            max_queue=cfg.writer.max_queue,
            on_overflow=self._writer_overflow,
        )
        self.processor = Processor(cfg, self.state, self.writer, self.bus)
        self.radio_messages = MessageStore(self.db, self.writer)
        self.connectors = ConnectorManager(
            cfg,
            self.secrets,
            self.bus,
            self.processor.process,
            self.processor.seed_nodes,
            cfg.ingest.queue_size,
            pressure=lambda: self.writer.wait_below(
                max(cfg.writer.flush_max_ops, cfg.writer.max_queue // 4)
            ),
            messages=self.radio_messages.on_event,
        )
        self.priv: PrivClient | FakePrivClient = make_privclient(
            cfg.system.privd, cfg.system.privd_socket, cfg.host.mode
        )
        self.metrics = Metrics(cfg.paths.db.parent)
        self.memory_guard = MemoryGuard(cfg.limits.rss_soft_mb, cfg.limits.rss_hard_mb)
        self.last_system: dict[str, Any] | None = None  # hasta la primera medición
        self.ntp_synced: bool | None = None
        self.exit_code = 0
        self.stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task[Any]] = []
        self.extensions: dict[
            str, Any
        ] = {}  # alertas, plugins, push, etc. (se registran al iniciar)
        self.sse_public_clients = 0
        self.sse_admin_clients = 0
        self.last_lan_request = time.time()  # para apagar el punto de acceso sin uso (24.3)

    # ---------------------------------------------------------------- ajustes

    @property
    def site(self) -> SiteSettings:
        return load_site(self.state.settings)

    def save_config(self) -> None:
        if self.config_path is None:
            log.warning("sin ruta de config.toml: el cambio no se guarda en disco")
            return
        save_config(self.cfg, self.config_path)

    def setup_window_open(self) -> bool:
        """El asistente sin usuario se cierra a los 60 min del arranque (13.2)."""
        return time.time() - self.started_at < 3600

    # ---------------------------------------------------------------- ciclo de vida

    def _ensure_dirs(self) -> None:
        p = self.cfg.paths
        for d in (p.db.parent, p.backups, p.tmp, p.tiles, p.recordings, p.plugins):
            d.mkdir(parents=True, exist_ok=True)

    async def start(self) -> None:
        self._ensure_dirs()
        from .bootstrap import ensure_secrets

        created = ensure_secrets(self.secrets)  # en la Pi ya los creó `bootstrap`
        if created:
            log.info("secretos generados: %s", ", ".join(created))
        if pending(self.cfg.paths.db):
            log.info("hay migraciones pendientes; se aplican en un proceso aparte")
            if self.config_path is not None and not self.dev:
                await asyncio.to_thread(migrate_in_subprocess, self.config_path)
            else:
                await asyncio.to_thread(
                    migrate,
                    self.cfg.paths.db,
                    self.cfg.paths.backups,
                    __version__,
                    self.cfg.paths.tmp,
                )
        await self.writer.start()
        await self.db.read(lambda c: self.state.load_from_db(c, self.secrets.get))
        await self._warm_dedup()
        log.info(
            "estado cargado: %d nodos, %d canales (%s públicos)",
            len(self.state.nodes),
            len(self.state.channels),
            ", ".join(self.state.public_channel_names()) or "ninguno",
        )
        await self._start_extensions()
        self._spawn(
            self.processor.run_dirty_flusher(self.cfg.writer.flush_interval_s), "nodes-flush"
        )
        self._spawn(self._every(self.cfg.sse.stats_interval_s, self._publish_stats), "stats")
        self._spawn(self._every(10, self._system_tick), "system")
        self._spawn(self._every(300, self._housekeeping), "housekeeping")
        self._spawn(self._hourly_loop(), "hourly")
        self._spawn(self._daily_loop(), "daily")
        self._spawn(self._start_connectors_after_ntp(), "connectors-start")
        if self.cfg.host.mode == "appliance":
            self._spawn(self._every(60, self._hotspot_watch), "hotspot-watch")

    async def _start_extensions(self) -> None:
        """Módulos opcionales (alertas, salida MQTT, plugins, push). Cada uno se registra solo."""
        from .extensions import start_extensions

        await start_extensions(self)

    async def _warm_dedup(self) -> None:
        ttl = self.cfg.ingest.dedup_ttl_s
        since = time.time() - ttl

        def q(conn: Any) -> list[tuple[int, int, int, float]]:
            return list(
                conn.execute(
                    text(
                        "SELECT from_num, packet_id, pk, first_rx FROM packets WHERE first_rx >= :s ORDER BY first_rx"
                    ),
                    {"s": since},
                ).all()
            )

        for from_num, packet_id, pk, first_rx in await self.db.read(q):
            self.processor.dedup.add(from_num, packet_id, pk, first_rx)

    async def stop(self) -> None:
        notify("STOPPING=1")
        await self.connectors.stop()
        for name, ext in list(self.extensions.items()):
            stop = getattr(ext, "stop", None)
            if stop is not None:
                try:
                    await stop()
                except Exception:
                    log.exception("error deteniendo %s", name)
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        self.processor.flush_dirty_nodes()
        await self.writer.stop(max_wait_s=10)
        await self.db.dispose()
        log.info("servicio detenido")

    def _spawn(self, coro: Awaitable[Any], name: str) -> asyncio.Task[Any]:
        task = asyncio.ensure_future(coro)
        task.set_name(name)
        self._tasks.append(task)
        return task

    async def _every(self, interval: float, fn: Callable[[], Awaitable[Any]]) -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                await fn()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("tarea periódica falló")

    # ---------------------------------------------------------------- tareas

    async def _start_connectors_after_ntp(self) -> None:
        """Sin reloj con batería: espera la hora (NTP) hasta `wait_ntp_s` (23.4)."""
        if sys.platform.startswith("linux") and not self.dev:
            deadline = time.time() + self.cfg.ingest.wait_ntp_s
            while time.time() < deadline:
                self.ntp_synced = await self._ntp_synced()
                if self.ntp_synced:
                    break
                await asyncio.sleep(5)
            if not self.ntp_synced:
                log.warning(
                    "la hora no se sincronizó en %d s; los conectores arrancan igual",
                    self.cfg.ingest.wait_ntp_s,
                )
        await self.connectors.start()

    async def _ntp_synced(self) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "/usr/bin/timedatectl",
                "show",
                "-p",
                "NTPSynchronized",
                "--value",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), 5)
            return out.strip() == b"yes"
        except (OSError, TimeoutError):
            return True  # sin timedatectl no se puede saber: no bloquear

    async def _publish_stats(self) -> None:
        self.bus.publish(StatsUpdated(summary=self.state.summary()))

    async def _system_tick(self) -> None:
        snap = await asyncio.to_thread(self.metrics.snapshot)
        snap["db"] = self.db.size_bytes()
        snap["writer"] = self.writer.stats()
        snap["bus"] = {"seq": self.bus.seq, "dropped": self.bus.dropped_total}
        snap["ingest_queue"] = self.connectors.queue.qsize()
        snap["ingest_dropped"] = self.connectors.dropped
        snap["sse_clients"] = {"public": self.sse_public_clients, "admin": self.sse_admin_clients}
        snap["connectors"] = self.connectors.statuses()
        snap["ntp_synced"] = self.ntp_synced
        self.last_system = snap
        self.bus.publish(SystemStatus(metrics=snap))
        verdict = self.memory_guard.check(
            snap["rss_mb"],
            lambda mb: self.bus.publish(
                Diagnostic(
                    code="memory_soft",
                    message=f"memoria residente {mb:.0f} MB",
                    details={"rss_mb": mb},
                )
            ),
        )
        if verdict == "hard":
            self.exit_code = 3
            self.stop_event.set()

    async def _housekeeping(self) -> None:
        now = time.time()
        self.processor.dedup.expire(now)
        self.processor.rate.cleanup(now)
        for conn in list(self.connectors.connectors.values()):
            conn.status()  # pasa a "degraded" si corresponde

    async def _hourly_loop(self) -> None:
        await asyncio.sleep(20)
        await self.writer.run(lambda c: rollups.run_hourly(c, backfill_hours=3))
        while True:
            now = time.time()
            next_run = rollups.hour_floor(now) + 3600 + 120  # 2 min después de cada hora
            await asyncio.sleep(max(1.0, next_run - now))
            try:
                await self.writer.run(lambda c: rollups.run_hourly(c, backfill_hours=2))
            except Exception:
                log.exception("agregados horarios fallaron")

    async def _daily_loop(self) -> None:
        tz = ZoneInfo(self.cfg.site.timezone)
        while True:
            now = dt.datetime.now(tz)
            target = now.replace(hour=3, minute=30, second=0, microsecond=0)
            if target <= now:
                target += dt.timedelta(days=1)
            await asyncio.sleep((target - now).total_seconds())
            try:
                await self.writer.run(rollups.run_daily)
                await run_retention(self.writer.run, self.cfg.retention)
                await self.writer.run(maintenance)
            except Exception:
                log.exception("tarea diaria falló")

    async def _hotspot_watch(self) -> None:
        """El punto de acceso se apaga solo tras 30 min sin uso y se reintenta la red conocida (24.3)."""
        if time.time() - self.last_lan_request < 1800:
            return
        try:
            status = await self.priv.call("wifi.status")
            if status.get("hotspot"):
                log.info("punto de acceso sin uso hace 30 min: se apaga")
                await self.priv.call("hotspot.stop")
        except Exception as e:
            log.warning("no se pudo revisar el punto de acceso: %s", e)

    def _writer_overflow(self, queued: int) -> None:
        self.bus.publish(
            Diagnostic(
                code="writer_overflow",
                message=f"la cola de escritura superó {self.cfg.writer.max_queue} operaciones",
                details={"queued": queued},
            )
        )


# --------------------------------------------------------------------------- servidores


class _Server(uvicorn.Server):
    """Sin manejadores de señales propios: los maneja `serve()` para todos los servidores."""

    @contextlib.contextmanager
    def capture_signals(self) -> Iterator[None]:
        yield


def _make_server(app: Any, bind: str) -> _Server:
    host, port = parse_bind(bind)
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
        lifespan="off",
        proxy_headers=False,
        server_header=False,
        ws="none",
        timeout_graceful_shutdown=5,
        timeout_keep_alive=30,
    )
    return _Server(config)


def _install_signals(service: Service) -> None:
    loop = asyncio.get_running_loop()
    if sys.platform != "win32":
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, service.stop_event.set)
    else:

        def handler(_sig: int, _frame: object) -> None:
            loop.call_soon_threadsafe(service.stop_event.set)

        signal.signal(signal.SIGINT, handler)


async def serve(cfg: Config, config_path: Path | None, *, dev: bool = False) -> int:
    from .api.factory import create_apps

    service = Service(cfg, config_path, dev=dev)
    _install_signals(service)
    await service.start()
    apps = create_apps(service)
    servers = [_make_server(app, bind) for bind, app in apps]
    tasks = [asyncio.create_task(s.serve(), name=f"http-{i}") for i, s in enumerate(servers)]
    # esperar a que todos escuchen
    for _ in range(200):
        if all(s.started for s in servers) or any(t.done() for t in tasks):
            break
        await asyncio.sleep(0.05)
    failed = [t for t in tasks if t.done()]
    if failed:
        log.error("un servidor HTTP no pudo arrancar (¿puerto ocupado?)")
        service.exit_code = 2
        service.stop_event.set()
    else:
        service.ready = True
        notify("READY=1")
        for bind, _ in apps:
            log.info("escuchando en http://%s", bind)
        if dev and service.secrets.data.setup_code:
            from .auth.users import count_users

            if await service.db.read(count_users) == 0:
                # Solo en desarrollo: en la Pi el código lo muestra el instalador (13.2).
                print(
                    f"\n  Asistente: http://{cfg.server.lan_bind}/setup  código: {service.secrets.data.setup_code}\n"
                )
    watchdog = watchdog_interval_s()
    if watchdog:

        async def ping() -> None:
            while True:
                await asyncio.sleep(watchdog)
                writer_alive = service.writer._task is not None and not service.writer._task.done()
                if writer_alive:
                    notify("WATCHDOG=1")

        service._spawn(ping(), "watchdog")
    await service.stop_event.wait()
    log.info("deteniendo…")
    for s in servers:
        s.should_exit = True
    with contextlib.suppress(Exception):
        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 10)
    await service.stop()
    return service.exit_code


async def replay_only(cfg: Config, config_path: Path | None) -> int:
    """`meshbox replay` sin servidores: carga la grabación en la base y recalcula agregados."""
    service = Service(cfg, config_path, dev=True)
    service._ensure_dirs()
    migrate(cfg.paths.db, cfg.paths.backups, __version__, cfg.paths.tmp)
    await service.writer.start()
    await service.db.read(lambda c: service.state.load_from_db(c, service.secrets.get))
    t0 = time.time()
    await service.connectors.start()
    conn = next(iter(service.connectors.connectors.values()))
    while not conn.finished and conn.status().state != "error":  # noqa: ASYNC110 - sondeo simple
        await asyncio.sleep(0.2)
    while not service.connectors.queue.empty():  # noqa: ASYNC110
        await asyncio.sleep(0.05)
    await service.connectors.stop()
    service.processor.flush_dirty_nodes()
    await service.writer.flush()
    first = await service.db.read(
        lambda c: c.execute(text("SELECT min(first_rx) FROM packets")).scalar()
    )
    if first:
        await service.writer.run(lambda c: rollups.backfill(c, float(first)))
    await service.writer.stop()
    await service.db.dispose()
    st = service.state
    print(
        f"reproducción terminada en {time.time() - t0:.1f} s: {st.packets_total} paquetes, "
        f"{st.duplicates_total} duplicados, {len(st.nodes)} nodos, RSS {service.metrics.rss_mb()} MB"
    )
    return 0


def save_and_reload_config(service: Service) -> None:
    service.save_config()
