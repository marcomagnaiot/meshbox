"""Bus de eventos interno (sección 5.4).

Un `seq` global creciente por evento y una cola acotada por suscriptor: un suscriptor
lento pierde eventos (con contador) y no frena a los demás. Todo corre en el loop
asyncio; `publish` no bloquea nunca.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import time
from collections.abc import AsyncIterator, Callable, Iterable
from typing import TypeVar

from .models import Event

log = logging.getLogger(__name__)
E = TypeVar("E", bound=Event)


class Subscription:
    def __init__(
        self,
        bus: EventBus,
        name: str,
        maxsize: int,
        types: frozenset[type[Event]] | None,
        predicate: Callable[[Event], bool] | None,
    ) -> None:
        self.bus = bus
        self.name = name
        self.types = types
        self.predicate = predicate
        self.queue: asyncio.Queue[Event] = asyncio.Queue(maxsize)
        self.dropped = 0
        self.closed = False

    def accepts(self, ev: Event) -> bool:
        if self.types is not None and type(ev) not in self.types:
            return False
        return self.predicate is None or self.predicate(ev)

    def offer(self, ev: Event) -> None:
        try:
            self.queue.put_nowait(ev)
        except asyncio.QueueFull:
            self.dropped += 1
            self.bus.dropped_total += 1
            if self.dropped in (1, 100) or self.dropped % 1000 == 0:
                log.warning("suscriptor %s lento: %d eventos descartados", self.name, self.dropped)

    async def get(self) -> Event:
        return await self.queue.get()

    def get_nowait(self) -> Event | None:
        try:
            return self.queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    def close(self) -> None:
        self.closed = True
        self.bus.unsubscribe(self)

    def __aiter__(self) -> AsyncIterator[Event]:
        return self._iter()

    async def _iter(self) -> AsyncIterator[Event]:
        while not self.closed:
            yield await self.queue.get()


class EventBus:
    def __init__(self) -> None:
        self._seq = 0
        self._subs: list[Subscription] = []
        self.dropped_total = 0
        self.published_total = 0

    @property
    def seq(self) -> int:
        return self._seq

    def publish(self, ev: E) -> E:
        self._seq += 1
        stamped = dataclasses.replace(ev, seq=self._seq, ts=ev.ts or time.time())
        self.published_total += 1
        for sub in self._subs:
            if sub.accepts(stamped):
                sub.offer(stamped)
        return stamped

    def subscribe(
        self,
        name: str,
        *,
        maxsize: int = 1000,
        types: Iterable[type[Event]] | None = None,
        predicate: Callable[[Event], bool] | None = None,
    ) -> Subscription:
        sub = Subscription(
            self, name, maxsize, frozenset(types) if types is not None else None, predicate
        )
        self._subs.append(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        if sub in self._subs:
            self._subs.remove(sub)

    def stats(self) -> dict[str, object]:
        return {
            "seq": self._seq,
            "published": self.published_total,
            "dropped": self.dropped_total,
            "subscribers": [
                {"name": s.name, "queued": s.queue.qsize(), "dropped": s.dropped}
                for s in self._subs
            ],
        }
