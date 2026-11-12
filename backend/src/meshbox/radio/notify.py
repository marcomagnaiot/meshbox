"""Avisos push de los mensajes que llegan a las placas del Cliente Meshtastic (ADR 0023).

Cada equipo del panel suscripto a push elige si quiere aviso de los directos (`dm`) o de todo
(`all`); el aviso abre la conversación en el Cliente. Un mensaje que oyen dos placas avisa una
vez, y lo que manda una placa propia y oye otra no avisa.
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import orjson

from ..alerts.channels.webpush import WebPush

if TYPE_CHECKING:
    from ..app import Service

log = logging.getLogger(__name__)
SEEN_MAX = 500  # paquetes recordados para no avisar dos veces el que oyen dos placas
TTL_S = 86400  # si el teléfono está sin conexión, el aviso le llega igual dentro del día


def conv_url(cid: str, conv: str) -> str:
    return f"/admin/cliente?placa={quote(cid, safe='')}&conv={quote(conv, safe='')}"


class MessageNotifier:
    def __init__(self, service: Service) -> None:
        self.service = service
        self.push = WebPush(service)
        self.sent = 0
        self.failed = 0
        self._seen: OrderedDict[tuple[str | None, int], None] = OrderedDict()
        self._tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        self.service.radio_messages.listeners.append(self.on_message)

    async def stop(self) -> None:
        listeners = self.service.radio_messages.listeners
        if self.on_message in listeners:
            listeners.remove(self.on_message)
        if self._tasks:
            await asyncio.wait(self._tasks, timeout=5)

    def _own_boards(self) -> set[str]:
        from .service import get_radio

        return {b["gateway_id"] for b in get_radio(self.service).boards() if b["gateway_id"]}

    def on_message(self, item: dict[str, Any]) -> None:
        """Lo llama el historial en el loop por cada mensaje recibido."""
        if item.get("direction") != "in" or not self.push.available:
            return
        sender = item.get("from_id")
        if sender and sender in self._own_boards():
            return
        packet = int(item.get("packet_id") or 0)
        if packet:
            key = (sender, packet)
            if key in self._seen:
                return
            self._seen[key] = None
            while len(self._seen) > SEEN_MAX:
                self._seen.popitem(last=False)
        task = asyncio.get_running_loop().create_task(self._send(item))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def payload(self, item: dict[str, Any]) -> dict[str, Any]:
        from ..api.admin.inbox import Names

        names = Names(self.service)
        long_name, short_name = names.node(item.get("from_id"))
        sender = long_name or short_name or item.get("from_id") or "?"
        if long_name and short_name and short_name != long_name:
            sender = f"{long_name} ({short_name})"
        if item.get("dm"):
            title = sender
            if names.count > 1:
                title += f" → {names.board(item['board'])}"
        else:
            channel = names.conv(item["connector_id"], item["conv"], item.get("channel"))["name"]
            title = f"# {channel or item.get('channel_index', 0)} · {sender}"
        return {
            "kind": "message",
            "title": title,
            "body": item.get("text") or "",
            "url": conv_url(item["connector_id"], item["conv"]),
            "tag": f"msg-{item['connector_id']}-{item['conv']}",
            "ts": item.get("ts"),
        }

    async def _send(self, item: dict[str, Any]) -> None:
        try:
            subs = await self.push.message_subscriptions(bool(item.get("dm")))
            if not subs:
                return
            body = orjson.dumps(self.payload(item))
            ok, fail = await self.push.deliver(subs, body, urgency="high", ttl=TTL_S)
            self.sent += ok
            self.failed += fail
        except Exception:
            log.exception("no se pudo avisar un mensaje nuevo")


def make_notifier(service: Service) -> MessageNotifier:
    return MessageNotifier(service)
