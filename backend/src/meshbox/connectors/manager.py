"""Alta, baja y reinicio de conectores; cola de ingreso hacia el procesador."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from ..bus import EventBus
from ..config import (
    Config,
    ConnectorCfg,
    MqttConnectorCfg,
    ReplayConnectorCfg,
    SecretStore,
    SerialConnectorCfg,
    TcpConnectorCfg,
)
from ..models import ConnectorStatus, ConnectorStatusChanged, RawPacket
from .base import BaseConnector

log = logging.getLogger(__name__)


class ConnectorManager:
    def __init__(
        self,
        cfg: Config,
        secrets: SecretStore,
        bus: EventBus,
        process: Callable[[RawPacket], None],
        seed: Callable[[str, list[dict[str, Any]], float], int] | None = None,
        queue_size: int = 2000,
        pressure: Callable[[], Awaitable[None]] | None = None,
        messages: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.cfg = cfg
        self.secrets = secrets
        self.bus = bus
        self._process = process
        self._seed = seed
        self._messages = messages  # historial del cliente Meshtastic (ADR 0016)
        self._pressure = pressure  # contrapresión del escritor (solo reproducciones)
        self.connectors: dict[str, BaseConnector] = {}
        self.queue: asyncio.Queue[RawPacket] = asyncio.Queue(queue_size)
        self.dropped = 0
        self._consumer: asyncio.Task[None] | None = None
        self.hold = asyncio.Event()  # liberado = los conectores pueden arrancar
        self.hold.set()

    # ---------------------------------------------------------------- creación

    def build(self, ccfg: ConnectorCfg) -> BaseConnector:
        if isinstance(ccfg, MqttConnectorCfg):
            from .mqtt import MqttConnector

            return MqttConnector(ccfg, self.secrets.get, self._on_status)
        if isinstance(ccfg, SerialConnectorCfg | TcpConnectorCfg):
            from .serial import SerialConnector, TcpConnector

            def seed(gw: str, nodes: list[dict[str, Any]], now: float) -> None:
                if self._seed is not None:
                    self._seed(gw, nodes, now)

            cls = TcpConnector if isinstance(ccfg, TcpConnectorCfg) else SerialConnector
            return cls(ccfg, self._on_status, seed, self._messages)
        if isinstance(ccfg, ReplayConnectorCfg):
            from .replay import ReplayConnector

            return ReplayConnector(ccfg, self._on_status)
        raise ValueError(f"tipo de conector desconocido: {ccfg!r}")

    def _on_status(self, st: ConnectorStatus) -> None:
        self.bus.publish(ConnectorStatusChanged(status=st.as_dict()))

    async def _emit(self, raw: RawPacket) -> None:
        """Conectores en vivo: si la cola está llena se descarta (protege la memoria)."""
        try:
            self.queue.put_nowait(raw)
        except asyncio.QueueFull:
            self.dropped += 1
            if self.dropped in (1, 100) or self.dropped % 1000 == 0:
                log.warning("cola de ingreso llena: %d paquetes descartados", self.dropped)

    async def _emit_wait(self, raw: RawPacket) -> None:
        """Reproducción: espera lugar en la cola (contrapresión), nunca descarta."""
        await self.queue.put(raw)

    # ---------------------------------------------------------------- ciclo de vida

    async def start(self, *, wait_for: asyncio.Event | None = None) -> None:
        self._consumer = asyncio.create_task(self._consume(), name="ingest")
        if wait_for is not None:
            await wait_for.wait()
        for ccfg in self.cfg.connectors:
            if ccfg.enabled:
                await self.start_one(ccfg)

    async def start_one(self, ccfg: ConnectorCfg) -> BaseConnector:
        await self.stop_one(ccfg.id)
        conn = self.build(ccfg)
        self.connectors[ccfg.id] = conn
        await conn.start(self._emit_wait if isinstance(ccfg, ReplayConnectorCfg) else self._emit)
        log.info("conector %s (%s) iniciado", ccfg.id, ccfg.kind)
        return conn

    async def stop_one(self, connector_id: str) -> None:
        conn = self.connectors.pop(connector_id, None)
        if conn is not None:
            await conn.stop()
            log.info("conector %s detenido", connector_id)

    async def restart(self, connector_id: str) -> BaseConnector | None:
        ccfg = self.cfg.connector(connector_id)
        if ccfg is None:
            return None
        if not ccfg.enabled:
            await self.stop_one(connector_id)
            return None
        return await self.start_one(ccfg)

    async def stop(self) -> None:
        for cid in list(self.connectors):
            await self.stop_one(cid)
        # procesar lo que quedó en la cola
        while not self.queue.empty():
            self._process(self.queue.get_nowait())
        if self._consumer is not None:
            self._consumer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._consumer

    async def _consume(self) -> None:
        n = 0
        while True:
            raw = await self.queue.get()
            if raw.source == "replay" and self._pressure is not None:
                await self._pressure()
            self._process(raw)
            n += 1
            if n % 50 == 0:
                await asyncio.sleep(0)  # deja respirar al resto del loop

    # ---------------------------------------------------------------- consultas

    def statuses(self) -> list[dict[str, Any]]:
        out = []
        for ccfg in self.cfg.connectors:
            conn = self.connectors.get(ccfg.id)
            if conn is not None:
                d = conn.status().as_dict()
            else:
                d = ConnectorStatus(id=ccfg.id, kind=ccfg.kind).as_dict()
            d["enabled"] = ccfg.enabled
            out.append(d)
        return out

    def get(self, connector_id: str) -> BaseConnector | None:
        return self.connectors.get(connector_id)

    def serial(self, connector_id: str | None = None) -> Any:
        """Primer conector USB conectado (o el indicado)."""
        from .serial import SerialConnector

        for cid, conn in self.connectors.items():
            if isinstance(conn, SerialConnector) and (connector_id is None or cid == connector_id):
                return conn
        return None
