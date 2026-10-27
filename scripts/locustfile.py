"""Carga con Locust (sección 27: 50 clientes SSE y 20 peticiones/s durante 10 min).

    uv run locust -f scripts/locustfile.py --host http://192.168.0.10:8090 \
        --users 70 --spawn-rate 10 --run-time 10m --headless

Los usuarios `SseUser` (50) mantienen el stream abierto; `ApiUser` (20) piden la API pública.
"""

from __future__ import annotations

import random

from locust import HttpUser, between, constant, task

PATHS = [
    "/api/v1/site",
    "/api/v1/nodes",
    "/api/v1/messages",
    "/api/v1/stats/summary",
    "/api/v1/links",
]


class ApiUser(HttpUser):
    weight = 2
    wait_time = between(0.5, 1.5)

    @task
    def public_api(self) -> None:
        self.client.get(random.choice(PATHS), name="api")


class SseUser(HttpUser):
    weight = 5
    wait_time = constant(1)

    @task
    def stream(self) -> None:
        with self.client.get("/api/v1/stream?activity=1", stream=True, name="sse", timeout=120,
                             catch_response=True) as r:  # fmt: skip
            events = 0
            for line in r.iter_lines():
                if line.startswith(b"event:"):
                    events += 1
                if events >= 50:
                    break
            r.success()
