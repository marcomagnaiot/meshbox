"""Deduplicación por (from, id) y límite de paquetes por nodo (sección 10.4)."""

from __future__ import annotations

from collections import OrderedDict


class Deduplicator:
    """Caché LRU con vencimiento. Guarda el `pk` asignado a la primera copia."""

    def __init__(self, max_entries: int = 20_000, ttl_s: float = 1800) -> None:
        self.max_entries = max_entries
        self.ttl_s = ttl_s
        self._seen: OrderedDict[tuple[int, int], tuple[float, int]] = OrderedDict()

    def __len__(self) -> int:
        return len(self._seen)

    def lookup(self, from_num: int, packet_id: int, now: float) -> int | None:
        key = (from_num, packet_id)
        hit = self._seen.get(key)
        if hit is None:
            return None
        first_seen, pk = hit
        if now - first_seen > self.ttl_s:
            del self._seen[key]
            return None
        return pk

    def add(self, from_num: int, packet_id: int, pk: int, now: float) -> None:
        key = (from_num, packet_id)
        self._seen[key] = (now, pk)
        self._seen.move_to_end(key)
        while len(self._seen) > self.max_entries:
            self._seen.popitem(last=False)

    def expire(self, now: float) -> int:
        """Elimina entradas vencidas (las más viejas están al principio)."""
        removed = 0
        while self._seen:
            key, (first_seen, _pk) = next(iter(self._seen.items()))
            if now - first_seen <= self.ttl_s:
                break
            del self._seen[key]
            removed += 1
        return removed

    def remap(self, old_pk: int, new_pk: int) -> None:
        """El escritor encontró que el paquete ya estaba en la base con otro pk."""
        for key, (ts, pk) in self._seen.items():
            if pk == old_pk:
                self._seen[key] = (ts, new_pk)
                return


class NodeRateLimiter:
    """Ventana fija de 60 s por nodo; protege ante inundaciones."""

    def __init__(self, max_per_min: int = 120) -> None:
        self.max_per_min = max_per_min
        self._windows: dict[int, list[float]] = {}  # from -> [inicio, cuenta, excedidos]
        self.dropped_total = 0

    def allow(self, from_num: int, now: float) -> bool:
        w = self._windows.get(from_num)
        if w is None or now - w[0] >= 60:
            self._windows[from_num] = [now, 1.0, 0.0]
            return True
        if w[1] >= self.max_per_min:
            w[2] += 1
            self.dropped_total += 1
            return False
        w[1] += 1
        return True

    def first_drop_in_window(self, from_num: int) -> bool:
        w = self._windows.get(from_num)
        return w is not None and w[2] == 1

    def cleanup(self, now: float) -> None:
        stale = [k for k, w in self._windows.items() if now - w[0] >= 120]
        for k in stale:
            del self._windows[k]
