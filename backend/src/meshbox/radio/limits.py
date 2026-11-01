"""Límites propios de meshbox para lo que sale por la malla (sección 22, ADR 0018).

Los valores están en `[tx]` de config.toml y se cambian desde el panel (Transmisión), así que se
leen en cada consulta. 0 deja ese límite sin efecto; el firmware de la placa tiene los suyos aparte.
"""

from __future__ import annotations

import time
from collections import deque


class SendLimiter:
    """Envíos de la última hora, para una pausa mínima entre envíos y un tope por hora."""

    def __init__(self) -> None:
        self.sent: deque[float] = deque()

    def check(self, gap_s: float, per_hour: int) -> float:
        """Segundos hasta el próximo envío permitido (0: se puede ya)."""
        now = time.monotonic()  # el reloj de la Pi salta al sincronizar la hora
        while self.sent and now - self.sent[0] > 3600:
            self.sent.popleft()
        wait = 0.0
        if gap_s and self.sent:
            wait = gap_s - (now - self.sent[-1])
        if per_hour and len(self.sent) >= per_hour:
            wait = max(wait, 3600 - (now - self.sent[-per_hour]))
        return max(wait, 0.0)

    def mark(self) -> None:
        self.sent.append(time.monotonic())
