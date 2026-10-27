"""Conector MQTT (sección 9.2): `ServiceEnvelope` protobuf en `<root>/2/e/<canal>/<!gateway>`."""

from __future__ import annotations

import logging
import secrets
import ssl
import time
from collections.abc import Callable

import aiomqtt
from google.protobuf.message import DecodeError
from meshtastic.protobuf import mqtt_pb2

from ..config import MqttConnectorCfg
from ..models import RawPacket
from .base import BaseConnector, StatusCallback

log = logging.getLogger(__name__)


def parse_topic(topic: str) -> tuple[str, str | None, str | None]:
    """Devuelve (tipo, canal, gateway). tipo: "e" (paquetes), "map" o "other"."""
    if "/2/e/" in topic:
        rest = topic.split("/2/e/", 1)[1].split("/")
        channel = rest[0] or None if rest else None
        gateway = rest[1] if len(rest) > 1 and rest[1].startswith("!") else None
        return "e", channel, gateway
    if "/2/map" in topic:
        rest = topic.split("/2/map", 1)[1].strip("/").split("/")
        gateway = rest[-1] if rest and rest[-1].startswith("!") else None
        return "map", None, gateway
    return "other", None, None


def parse_envelope(payload: bytes) -> mqtt_pb2.ServiceEnvelope | None:
    env = mqtt_pb2.ServiceEnvelope()
    try:
        env.ParseFromString(payload)
    except (DecodeError, ValueError):
        return None
    if not env.HasField("packet"):
        return None
    return env


class MqttConnector(BaseConnector):
    kind = "mqtt"

    def __init__(
        self,
        cfg: MqttConnectorCfg,
        password_resolver: Callable[[str | None], str | None],
        on_status: StatusCallback | None = None,
    ) -> None:
        super().__init__(cfg.id, on_status)
        self.cfg = cfg
        self._password = password_resolver
        self._set_detail(
            host=cfg.host, port=cfg.port, topics=list(cfg.topics), username=cfg.username
        )

    async def _run_once(self) -> None:
        cfg = self.cfg
        tls_context = ssl.create_default_context() if cfg.tls else None
        identifier = cfg.client_id or f"meshbox-{cfg.id}-{secrets.token_hex(3)}"
        async with aiomqtt.Client(
            hostname=cfg.host,
            port=cfg.port,
            username=cfg.username,
            password=self._password(cfg.password_ref),
            identifier=identifier,
            keepalive=cfg.keepalive,
            tls_context=tls_context,
            clean_session=True,
        ) as client:
            for topic in cfg.topics:
                await client.subscribe(topic, qos=0)
            self._set_state("connected")
            self._set_detail(connected_at=time.time())
            log.info("conector %s conectado a %s:%d", cfg.id, cfg.host, cfg.port)
            async for message in client.messages:
                await self._on_message(message.topic.value, message.payload)

    async def _on_message(self, topic: str, payload: object) -> None:
        if not isinstance(payload, bytes | bytearray):
            self._status.invalid += 1
            return
        kind, topic_channel, topic_gateway = parse_topic(topic)
        if kind == "other":
            return
        env = parse_envelope(bytes(payload))
        if env is None:
            self._status.invalid += 1
            return
        raw = RawPacket(
            source="mqtt",
            connector_id=self.id,
            gateway_id=env.gateway_id or topic_gateway,
            channel_id=env.channel_id or topic_channel,
            rx_time=time.time(),
            packet=env.packet,
        )
        await self._deliver(raw)
