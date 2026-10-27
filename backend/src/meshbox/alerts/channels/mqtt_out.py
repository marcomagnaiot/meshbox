"""Salida MQTT de eventos (sección 14.3): JSON en `meshbox/events/<tipo>` (para integraciones)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

import aiomqtt
import orjson

from ...api.stream import public_event
from ...models import (
    AlertFired,
    AlertResolved,
    MessageAdded,
    NodeUpserted,
    PositionAdded,
    TelemetryAdded,
)

if TYPE_CHECKING:
    from ...app import Service

log = logging.getLogger(__name__)
TOPIC_OF = {
    "node": "node",
    "message": "message",
    "telemetry": "telemetry",
    "alert": "alert",
    "position": "position",
}


class MqttOut:
    def __init__(self, service: Service) -> None:
        self.service = service
        self.queue: asyncio.Queue[tuple[str, bytes]] = asyncio.Queue(1000)
        self.published = 0
        self.dropped = 0
        self.connected = False
        self.last_error: str | None = None
        self._tasks: list[asyncio.Task[None]] = []
        self._sub: Any = None

    @property
    def cfg(self) -> Any:
        return self.service.cfg.mqtt_out

    async def start(self) -> None:
        self._sub = self.service.bus.subscribe(
            "mqtt-out",
            maxsize=1000,
            types=(
                NodeUpserted,
                MessageAdded,
                TelemetryAdded,
                AlertFired,
                AlertResolved,
                PositionAdded,
            ),
        )
        self._tasks = [asyncio.create_task(self._collect()), asyncio.create_task(self._run())]

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t
        if self._sub is not None:
            self._sub.close()

    def publish_now(self, kind: str, data: dict[str, Any]) -> None:
        """Publicación pedida por una regla de alerta o un plugin (aunque la salida esté apagada)."""
        try:
            self.queue.put_nowait((f"{self.cfg.prefix}/{kind}", orjson.dumps(data)))
        except asyncio.QueueFull:
            self.dropped += 1

    async def _collect(self) -> None:
        while True:
            ev = await self._sub.get()
            if not self.cfg.enabled:
                continue
            if isinstance(ev, AlertFired | AlertResolved):
                out = ("alert", {"seq": ev.seq, **ev.alert, "is_public": ev.is_public})
            else:
                out = public_event(ev, activity=False)  # type: ignore[assignment]
            if out is None:
                continue
            name, data = out
            topic = TOPIC_OF.get(name)
            if topic:
                self.publish_now(topic, data)

    async def _run(self) -> None:
        delay = 2.0
        while True:
            if not self.cfg.enabled and self.queue.empty():
                await asyncio.sleep(5)
                continue
            try:
                async with aiomqtt.Client(
                    hostname=self.cfg.host,
                    port=self.cfg.port,
                    username=self.cfg.username,
                    password=self.service.secrets.get(self.cfg.password_ref),
                    identifier="meshbox-out",
                ) as client:
                    self.connected, self.last_error, delay = True, None, 2.0
                    while True:
                        topic, payload = await self.queue.get()
                        await client.publish(topic, payload, qos=0, retain=False)
                        self.published += 1
            except aiomqtt.MqttError as e:
                self.connected = False
                self.last_error = str(e)
                await asyncio.sleep(delay)
                delay = min(60.0, delay * 2)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.cfg.enabled,
            "connected": self.connected,
            "published": self.published,
            "dropped": self.dropped,
            "last_error": self.last_error,
            "prefix": self.cfg.prefix,
        }


def make_mqtt_out(service: Service) -> MqttOut:
    return MqttOut(service)
