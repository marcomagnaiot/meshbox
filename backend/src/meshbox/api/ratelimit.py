"""Límites de uso (sección 12.5). Cubeta de fichas en memoria por clave."""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated: float


class RateLimiter:
    """`rate` fichas por `per` segundos, con ráfaga igual a `rate`."""

    def __init__(self, rate: int, per: float, max_keys: int = 50_000) -> None:
        self.rate = rate
        self.per = per
        self.max_keys = max_keys
        self._buckets: dict[str, _Bucket] = {}
        self._last_cleanup = time.monotonic()

    def hit(self, key: str, cost: float = 1.0) -> tuple[bool, float]:
        """Devuelve (permitido, segundos hasta la próxima ficha)."""
        now = time.monotonic()
        b = self._buckets.get(key)
        refill = self.rate / self.per
        if b is None:
            b = _Bucket(tokens=float(self.rate), updated=now)
            self._buckets[key] = b
        else:
            b.tokens = min(float(self.rate), b.tokens + (now - b.updated) * refill)
            b.updated = now
        if b.tokens >= cost:
            b.tokens -= cost
            allowed, retry = True, 0.0
        else:
            allowed, retry = False, (cost - b.tokens) / refill
        if now - self._last_cleanup > 60 or len(self._buckets) > self.max_keys:
            self._cleanup(now)
        return allowed, retry

    def peek(self, key: str, cost: float = 1.0) -> tuple[bool, float]:
        """Como `hit`, pero sin gastar fichas."""
        b = self._buckets.get(key)
        if b is None:
            return True, 0.0
        refill = self.rate / self.per
        tokens = min(float(self.rate), b.tokens + (time.monotonic() - b.updated) * refill)
        return (True, 0.0) if tokens >= cost else (False, (cost - tokens) / refill)

    def _cleanup(self, now: float) -> None:
        full_after = self.per * 2
        stale = [k for k, b in self._buckets.items() if now - b.updated > full_after]
        for k in stale:
            del self._buckets[k]
        self._last_cleanup = now


class LoginGuard:
    """5 fallos por minuto por IP; tras 10 fallos seguidos de un usuario, espera creciente.

    Los inicios de sesión correctos no gastan el cupo: varios administradores detrás de la
    misma IP (NAT) no se traban entre sí.
    """

    def __init__(self) -> None:
        self.per_ip = RateLimiter(5, 60)
        self._fails: dict[
            str, tuple[int, float]
        ] = {}  # usuario -> (fallos seguidos, bloqueado hasta)

    def check(self, ip: str, username: str) -> float:
        """0 si se permite; si no, segundos de espera."""
        ok, retry = self.per_ip.peek(ip)
        if not ok:
            return max(retry, 1.0)
        _fails, until = self._fails.get(username.lower(), (0, 0.0))
        now = time.time()
        if until > now:
            return until - now
        return 0.0

    def failure(self, username: str, ip: str | None = None) -> None:
        if ip is not None:
            self.per_ip.hit(ip)
        key = username.lower()
        fails, _ = self._fails.get(key, (0, 0.0))
        fails += 1
        until = 0.0
        if fails >= 10:
            # 10 fallos: 30 s; cada fallo más duplica, hasta 1 h
            until = time.time() + min(3600.0, 30.0 * 2 ** (fails - 10))
        self._fails[key] = (fails, until)

    def success(self, username: str) -> None:
        self._fails.pop(username.lower(), None)
