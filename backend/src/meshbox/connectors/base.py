"""Interfaz común de conectores (sección 9.1)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time
from collections.abc import Awaitable, Callable, Iterator
from typing import Any, ClassVar, Protocol

from ..models import ConnectorState, ConnectorStatus, RawPacket

log = logging.getLogger(__name__)

Emit = Callable[[RawPacket], Awaitable[None]]
StatusCallback = Callable[[ConnectorStatus], None]

DEGRADED_AFTER_S = 15 * 60
BACKOFF_STEPS = (2, 4, 8, 16, 30, 60)


def backoff_delays(jitter: float = 0.2) -> Iterator[float]:
    """2, 4, 8, 16, 30, 60, 60, ... segundos con ±20 % de variación aleatoria."""
    i = 0
    while True:
        base = BACKOFF_STEPS[min(i, len(BACKOFF_STEPS) - 1)]
        yield base * random.uniform(1 - jitter, 1 + jitter)  # noqa: S311 - no es criptográfico
        i += 1


class Connector(Protocol):
    id: str
    kind: str

    async def start(self, emit: Emit) -> None: ...
    async def stop(self) -> None: ...
    def status(self) -> ConnectorStatus: ...


class BaseConnector:
    kind: ClassVar[str] = "base"

    def __init__(self, connector_id: str, on_status: StatusCallback | None = None) -> None:
        self.id = connector_id
        self._status = ConnectorStatus(id=connector_id, kind=self.kind)
        self._on_status = on_status
        self._emit: Emit | None = None
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    # ---------------------------------------------------------------- ciclo de vida

    async def start(self, emit: Emit) -> None:
        self._emit = emit
        self._stopping.clear()
        self._task = asyncio.create_task(self._supervise(), name=f"connector-{self.id}")

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None
        await self._cleanup()
        self._set_state("stopped")

    def status(self) -> ConnectorStatus:
        st = self._status
        if (
            st.state == "connected"
            and st.last_packet_at is not None
            and time.time() - st.last_packet_at > DEGRADED_AFTER_S
        ):
            self._set_state("degraded")
        return self._status

    # ---------------------------------------------------------------- para subclases

    async def _run_once(self) -> None:
        """Conecta y atiende hasta que se corta (lanza excepción) o se detiene."""
        raise NotImplementedError

    async def _cleanup(self) -> None:
        """Libera recursos al detener (cerrar puertos, hilos)."""

    async def _supervise(self) -> None:
        delays = backoff_delays()
        while not self._stopping.is_set():
            self._set_state("connecting")
            try:
                await self._run_once()
                delays = backoff_delays()  # terminó bien (p. ej. fin de la grabación)
                if self._stopping.is_set():
                    break
                if self.finished:
                    self._set_state("stopped")
                    return
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._status.errors += 1
                self._set_state("error", f"{type(e).__name__}: {e}")
                log.warning("conector %s: %s", self.id, e)
            delay = next(delays)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), delay)

    @property
    def finished(self) -> bool:
        return False

    def _set_state(self, state: ConnectorState, error: str | None = None) -> None:
        st = self._status
        changed = st.state != state or (error is not None and error != st.last_error)
        if st.state != state:
            st.since = time.time()
        st.state = state
        if error is not None:
            st.last_error = error
        if changed and self._on_status is not None:
            self._on_status(st)

    def _set_detail(self, **kw: Any) -> None:
        self._status.detail.update(kw)

    async def _deliver(self, raw: RawPacket) -> None:
        st = self._status
        st.packets += 1
        st.last_packet_at = time.time()
        if st.state in ("degraded", "connecting"):
            self._set_state("connected")
        if self._emit is not None:
            await self._emit(raw)
