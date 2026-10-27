"""Conexiones SQLite y escritor por lotes (secciones 11.1 y 11.3).

Una sola conexión escribe (el escritor). Las lecturas usan otra conexión del pool de
lectura (WAL permite leer mientras se escribe).

Los `pk` de `packets`, `messages` y `alert_events` los asigna la aplicación al recibir el
paquete (contadores iniciados con el máximo de la base). Así las recepciones, posiciones
y mensajes pueden referenciar el paquete antes de que el lote se escriba, y los eventos
SSE salen con su `pk` sin esperar a la base.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from sqlalchemy import Connection, event, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool

log = logging.getLogger(__name__)
T = TypeVar("T")

BASE_PRAGMAS = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA foreign_keys=ON",
    "PRAGMA busy_timeout=5000",
    "PRAGMA temp_store=MEMORY",
)


def _make_engine(path: Path, *, cache_kib: int, pool_size: int, overflow: int) -> AsyncEngine:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path.as_posix()}",
        poolclass=AsyncAdaptedQueuePool,
        pool_size=pool_size,
        max_overflow=overflow,
        pool_pre_ping=False,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_conn: Any, _record: Any) -> None:
        cur = dbapi_conn.cursor()
        for pragma in BASE_PRAGMAS:
            cur.execute(pragma)
        cur.execute(f"PRAGMA cache_size=-{int(cache_kib)}")
        cur.close()

    return engine


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        # Escritor: caché de 8 MB (11.1). Lectores: 2 MB cada uno, para cuidar la RAM.
        self.write_engine = _make_engine(path, cache_kib=8000, pool_size=1, overflow=0)
        self.read_engine = _make_engine(path, cache_kib=2000, pool_size=2, overflow=2)

    async def read(self, fn: Callable[[Connection], T]) -> T:
        async with self.read_engine.connect() as conn:
            return await conn.run_sync(fn)

    async def dispose(self) -> None:
        await self.write_engine.dispose()
        await self.read_engine.dispose()

    def size_bytes(self) -> dict[str, int]:
        out = {}
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(self.path) + suffix)
            out["db" + suffix.replace("-", "_")] = p.stat().st_size if p.exists() else 0
        return out


# --------------------------------------------------------------------------- escritor

SQL: dict[str, str] = {
    "node": """
        INSERT INTO nodes (num, id, long_name, short_name, hw_model, role, is_licensed, public_key,
          firmware_version, region, modem_preset, lat, lon, alt, precision_bits, position_ts,
          battery_level, voltage, channel_utilization, air_util_tx, uptime_s, metrics_ts,
          last_snr, last_rssi, last_hops, last_gateway, first_seen, last_heard,
          heard_via_mqtt_only, hidden, is_fixed, note, updated_at)
        VALUES (:num, :id, :long_name, :short_name, :hw_model, :role, :is_licensed, :public_key,
          :firmware_version, :region, :modem_preset, :lat, :lon, :alt, :precision_bits,
          :position_ts, :battery_level, :voltage, :channel_utilization, :air_util_tx, :uptime_s,
          :metrics_ts, :last_snr, :last_rssi, :last_hops, :last_gateway, :first_seen,
          :last_heard, :heard_via_mqtt_only, :hidden, :is_fixed, :note, :updated_at)
        ON CONFLICT(num) DO UPDATE SET long_name=excluded.long_name,
          short_name=excluded.short_name, hw_model=excluded.hw_model, role=excluded.role,
          is_licensed=excluded.is_licensed, public_key=excluded.public_key,
          firmware_version=excluded.firmware_version, region=excluded.region,
          modem_preset=excluded.modem_preset, lat=excluded.lat, lon=excluded.lon,
          alt=excluded.alt, precision_bits=excluded.precision_bits,
          position_ts=excluded.position_ts, battery_level=excluded.battery_level,
          voltage=excluded.voltage, channel_utilization=excluded.channel_utilization,
          air_util_tx=excluded.air_util_tx, uptime_s=excluded.uptime_s,
          metrics_ts=excluded.metrics_ts, last_snr=excluded.last_snr,
          last_rssi=excluded.last_rssi, last_hops=excluded.last_hops,
          last_gateway=excluded.last_gateway, last_heard=excluded.last_heard,
          heard_via_mqtt_only=excluded.heard_via_mqtt_only, hidden=excluded.hidden,
          is_fixed=excluded.is_fixed, note=excluded.note, updated_at=excluded.updated_at
    """,
    "packet": """
        INSERT OR IGNORE INTO packets (pk, from_num, packet_id, to_num, channel_index,
          channel_name, channel_hash, portnum, first_rx, hop_start, want_ack, priority,
          encrypted, decoded_ok, is_public, payload_len, raw)
        VALUES (:pk, :from_num, :packet_id, :to_num, :channel_index, :channel_name,
          :channel_hash, :portnum, :first_rx, :hop_start, :want_ack, :priority, :encrypted,
          :decoded_ok, :is_public, :payload_len, :raw)
    """,
    "reception": """
        INSERT OR IGNORE INTO receptions (packet_pk, gateway, source, rx_time, rx_snr, rx_rssi,
          hop_limit, relay_node, via_mqtt, transport)
        VALUES (:packet_pk, :gateway, :source, :rx_time, :rx_snr, :rx_rssi, :hop_limit,
          :relay_node, :via_mqtt, :transport)
    """,
    "position": """
        INSERT OR REPLACE INTO positions (node_num, ts, lat, lon, alt, precision_bits,
          ground_speed, sats, packet_pk)
        VALUES (:node_num, :ts, :lat, :lon, :alt, :precision_bits, :ground_speed, :sats,
          :packet_pk)
    """,
    "tel_device": """
        INSERT OR REPLACE INTO telemetry_device (node_num, ts, battery_level, voltage,
          channel_utilization, air_util_tx, uptime_s)
        VALUES (:node_num, :ts, :battery_level, :voltage, :channel_utilization, :air_util_tx,
          :uptime_s)
    """,
    "tel_environment": """
        INSERT OR REPLACE INTO telemetry_environment (node_num, ts, temperature,
          relative_humidity, barometric_pressure, gas_resistance, iaq, lux, wind_speed,
          wind_gust, wind_direction, rainfall_1h, rainfall_24h)
        VALUES (:node_num, :ts, :temperature, :relative_humidity, :barometric_pressure,
          :gas_resistance, :iaq, :lux, :wind_speed, :wind_gust, :wind_direction,
          :rainfall_1h, :rainfall_24h)
    """,
    "tel_power": """
        INSERT OR REPLACE INTO telemetry_power (node_num, ts, ch1_voltage, ch1_current,
          ch2_voltage, ch2_current, ch3_voltage, ch3_current)
        VALUES (:node_num, :ts, :ch1_voltage, :ch1_current, :ch2_voltage, :ch2_current,
          :ch3_voltage, :ch3_current)
    """,
    "message": """
        INSERT OR IGNORE INTO messages (pk, packet_pk, ts, from_num, to_num, channel_name, text,
          reply_id, emoji, is_alert, hidden)
        VALUES (:pk, :packet_pk, :ts, :from_num, :to_num, :channel_name, :text, :reply_id,
          :emoji, :is_alert, 0)
    """,
    "link": """
        INSERT INTO links (node_num, neighbor_num, source, snr, ts)
        VALUES (:node_num, :neighbor_num, :source, :snr, :ts)
        ON CONFLICT(node_num, neighbor_num, source) DO UPDATE SET snr=excluded.snr, ts=excluded.ts
    """,
    "traceroute": """
        INSERT INTO traceroutes (packet_pk, ts, from_num, to_num, route, snr_towards, route_back,
          snr_back)
        VALUES (:packet_pk, :ts, :from_num, :to_num, :route, :snr_towards, :route_back,
          :snr_back)
    """,
    "waypoint": """
        INSERT OR REPLACE INTO waypoints (id, from_num, ts, name, description, lat, lon, icon,
          expire)
        VALUES (:id, :from_num, :ts, :name, :description, :lat, :lon, :icon, :expire)
    """,
    "waypoint_delete": "DELETE FROM waypoints WHERE id = :id",
}
_COMPILED = {k: text(v) for k, v in SQL.items()}

# Al desbordar la cola se descartan primero estas operaciones (11.3): nunca nodos ni mensajes.
DROPPABLE = frozenset({"reception"})
WITH_PACKET_PK = frozenset({"reception", "position", "message", "traceroute"})


@dataclass(slots=True)
class Op:
    kind: str
    params: dict[str, Any] | None = None
    fn: Callable[[Connection], Any] | None = None
    future: asyncio.Future[Any] | None = None


class IdAllocator:
    def __init__(self) -> None:
        self._next: dict[str, int] = {}

    def init(self, name: str, current_max: int) -> None:
        self._next[name] = max(current_max, 0) + 1

    def next(self, name: str) -> int:
        value = self._next[name]
        self._next[name] = value + 1
        return value


class BatchWriter:
    def __init__(
        self,
        db: Database,
        *,
        flush_interval_s: float = 2.0,
        flush_max_ops: int = 200,
        max_queue: int = 10_000,
        on_overflow: Callable[[int], None] | None = None,
        on_remap: Callable[[int, int], None] | None = None,
    ) -> None:
        self.db = db
        self.flush_interval_s = flush_interval_s
        self.flush_max_ops = flush_max_ops
        self.max_queue = max_queue
        self.on_overflow = on_overflow
        self.on_remap = on_remap
        self.ids = IdAllocator()
        self._queue: deque[Op] = deque()
        self._wakeup = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._remap: OrderedDict[int, int] = OrderedDict()
        # métricas
        self.written_ops = 0
        self.dropped_ops = 0
        self.failed_ops = 0
        self.batches = 0
        self.last_batch_ms = 0.0
        self.last_batch_size = 0
        self._overflow_notified_at = 0.0

    # ---------------------------------------------------------------- ciclo de vida

    async def start(self) -> None:
        def init_ids(conn: Connection) -> dict[str, int]:
            return {
                "packets": conn.execute(
                    text("SELECT COALESCE(MAX(pk), 0) FROM packets")
                ).scalar_one(),
                "messages": conn.execute(
                    text("SELECT COALESCE(MAX(pk), 0) FROM messages")
                ).scalar_one(),
                "alert_events": conn.execute(
                    text("SELECT COALESCE(MAX(id), 0) FROM alert_events")
                ).scalar_one(),
            }

        maxes = await self.db.read(init_ids)
        for name, value in maxes.items():
            self.ids.init(name, int(value))
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="db-writer")

    async def stop(self, max_wait_s: float = 10.0) -> None:
        """Vacía la cola antes de salir (como máximo `max_wait_s` segundos)."""
        self._running = False
        self._wakeup.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, max_wait_s)
            except TimeoutError:
                log.error(
                    "el escritor no terminó en %.0f s; quedan %d operaciones",
                    max_wait_s,
                    len(self._queue),
                )
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._task
        for op in self._queue:
            if op.future is not None and not op.future.done():
                op.future.set_exception(RuntimeError("escritor detenido"))
        self._queue.clear()

    # ---------------------------------------------------------------- API

    @property
    def queue_len(self) -> int:
        return len(self._queue)

    def enqueue(self, kind: str, params: dict[str, Any]) -> None:
        if len(self._queue) >= self.max_queue:
            if kind in DROPPABLE:
                self.dropped_ops += 1
                self._notify_overflow()
                return
            if kind == "packet" and params.get("raw") is not None:
                params = {**params, "raw": None}
                self.dropped_ops += 1
                self._notify_overflow()
        self._queue.append(Op(kind, params))
        if len(self._queue) >= self.flush_max_ops:
            self._wakeup.set()

    async def wait_below(self, n: int) -> None:
        """Espera a que la cola baje de `n` operaciones (contrapresión para reproducciones)."""
        while len(self._queue) > n and self._running:
            self._wakeup.set()
            await asyncio.sleep(0.01)

    def enqueue_fn(self, fn: Callable[[Connection], Any], *, now: bool = False) -> None:
        """Encola una escritura sin esperar el resultado (va en el próximo lote; con `now`, ya)."""
        self._queue.append(Op("fn", fn=fn))
        if now:
            self._wakeup.set()

    async def run(self, fn: Callable[[Connection], T]) -> T:
        """Ejecuta `fn` en la conexión de escritura, en orden con el resto, y espera el resultado."""
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[T] = loop.create_future()
        self._queue.append(Op("fn", fn=fn, future=fut))
        self._wakeup.set()
        if not self._running:
            await self._flush()
        return await fut

    async def flush(self) -> None:
        """Escribe ya lo pendiente (pruebas y antes de respaldos)."""
        done: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._queue.append(Op("fn", fn=lambda _c: None, future=done))
        self._wakeup.set()
        if not self._running:
            await self._flush()
        await done

    def stats(self) -> dict[str, Any]:
        return {
            "queue": len(self._queue),
            "written_ops": self.written_ops,
            "dropped_ops": self.dropped_ops,
            "failed_ops": self.failed_ops,
            "batches": self.batches,
            "last_batch_ms": round(self.last_batch_ms, 1),
            "last_batch_size": self.last_batch_size,
        }

    # ---------------------------------------------------------------- interno

    def _notify_overflow(self) -> None:
        now = time.monotonic()
        if now - self._overflow_notified_at > 60:
            self._overflow_notified_at = now
            log.error(
                "cola del escritor llena (%d): se descartan recepciones y crudos", len(self._queue)
            )
            if self.on_overflow:
                self.on_overflow(len(self._queue))

    async def _loop(self) -> None:
        while self._running or self._queue:
            if self._running:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._wakeup.wait(), self.flush_interval_s)
            self._wakeup.clear()
            try:
                await self._flush()
            except Exception:
                log.exception("error inesperado del escritor")
                await asyncio.sleep(1)

    async def _flush(self) -> None:
        while self._queue:
            batch: list[Op] = []
            while self._queue and len(batch) < 1000:
                batch.append(self._queue.popleft())
            t0 = time.perf_counter()
            try:
                async with self.db.write_engine.begin() as conn:
                    results = await conn.run_sync(self._apply, batch)
            except Exception as e:
                log.warning(
                    "lote de %d operaciones falló (%s); se reintenta de a una", len(batch), e
                )
                results = await self._apply_one_by_one(batch)
            else:
                self._resolve(batch, results)
            self.batches += 1
            self.last_batch_size = len(batch)
            self.last_batch_ms = (time.perf_counter() - t0) * 1000

    async def _apply_one_by_one(self, batch: list[Op]) -> list[Any]:
        results: list[Any] = []
        for op in batch:
            try:
                async with self.db.write_engine.begin() as conn:
                    res = await conn.run_sync(self._apply, [op])
                results.append(res[0])
                self._resolve([op], res)
            except Exception as e:
                self.failed_ops += 1
                log.error("operación %s descartada: %s", op.kind, e)
                if op.future is not None and not op.future.done():
                    op.future.set_exception(e)
                results.append(None)
        return results

    def _resolve(self, batch: list[Op], results: list[Any]) -> None:
        for op, res in zip(batch, results, strict=True):
            if op.future is not None and not op.future.done():
                op.future.set_result(res)

    def _map_pk(self, pk: int | None) -> int | None:
        if pk is None:
            return None
        return self._remap.get(pk, pk)

    def _apply(self, conn: Connection, batch: list[Op]) -> list[Any]:
        results: list[Any] = []
        for op in batch:
            if op.kind == "fn":
                assert op.fn is not None
                results.append(op.fn(conn))
                continue
            params = op.params or {}
            if op.kind in WITH_PACKET_PK and params.get("packet_pk") is not None:
                params = {**params, "packet_pk": self._map_pk(params["packet_pk"])}
            res = conn.execute(_COMPILED[op.kind], params)
            if op.kind == "packet" and res.rowcount == 0:
                # Ya estaba en la base (p. ej. tras un reinicio): usar el pk existente.
                existing = conn.execute(
                    text("SELECT pk FROM packets WHERE from_num = :f AND packet_id = :i"),
                    {"f": params["from_num"], "i": params["packet_id"]},
                ).scalar()
                if existing is not None and existing != params["pk"]:
                    self._remap[params["pk"]] = int(existing)
                    while len(self._remap) > 5000:
                        self._remap.popitem(last=False)
                    if self.on_remap:
                        self.on_remap(params["pk"], int(existing))
            self.written_ops += 1
            results.append(None)
        return results


async def run_periodic(
    interval_s: float, fn: Callable[[], Awaitable[Any]], name: str, first_delay: float | None = None
) -> None:
    """Corre `fn` cada `interval_s`; los errores se registran y el ciclo sigue."""
    await asyncio.sleep(interval_s if first_delay is None else first_delay)
    while True:
        try:
            await fn()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("tarea periódica %s falló", name)
        await asyncio.sleep(interval_s)
