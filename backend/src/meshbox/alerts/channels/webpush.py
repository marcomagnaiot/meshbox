"""Web Push con VAPID (sección 19.2).

Suscripciones públicas (solo alertas públicas) y de administración (todas). Se borran al
primer 404 o 410; otros errores se reintentan y la suscripción se borra tras 3 fallos
seguidos. `pywebpush` se importa recién al enviar (memoria).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

import orjson
from sqlalchemy import Connection, text

if TYPE_CHECKING:
    from ...app import Service

log = logging.getLogger(__name__)
MAX_FAILURES = 3


class WebPush:
    def __init__(self, service: Service) -> None:
        self.service = service
        self.sent = 0
        self.failed = 0

    @property
    def public_key(self) -> str:
        return self.service.secrets.data.vapid.public_key

    @property
    def available(self) -> bool:
        v = self.service.secrets.data.vapid
        return bool(v.public_key and v.private_key)

    async def subscribe(
        self, endpoint: str, p256dh: str, auth: str, scope: str, user_id: int | None
    ) -> None:
        def q(conn: Connection) -> None:
            conn.execute(
                text(
                    "INSERT INTO push_subscriptions (endpoint, p256dh, auth, scope, user_id, created_at, failures) "
                    "VALUES (:e, :p, :a, :s, :u, :t, 0) ON CONFLICT(endpoint) DO UPDATE SET p256dh = excluded.p256dh, "
                    "auth = excluded.auth, scope = excluded.scope, user_id = excluded.user_id, failures = 0"
                ),
                {"e": endpoint, "p": p256dh, "a": auth, "s": scope, "u": user_id, "t": time.time()},
            )

        await self.service.writer.run(q)

    async def unsubscribe(self, endpoint: str) -> bool:
        def q(conn: Connection) -> int:
            return (
                conn.execute(
                    text("DELETE FROM push_subscriptions WHERE endpoint = :e"), {"e": endpoint}
                ).rowcount
                or 0
            )

        return bool(await self.service.writer.run(q))

    async def count(self) -> dict[str, int]:
        def q(conn: Connection) -> dict[str, int]:
            return dict(
                conn.execute(
                    text("SELECT scope, count(*) FROM push_subscriptions GROUP BY scope")
                ).all()
            )

        return await self.service.db.read(q)

    def _send_one(self, sub: dict[str, Any], payload: bytes) -> tuple[bool, int | None, str | None]:
        from pywebpush import WebPushException, webpush

        v = self.service.secrets.data.vapid
        try:
            webpush(
                subscription_info={
                    "endpoint": sub["endpoint"],
                    "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
                },
                data=payload,
                vapid_private_key=v.private_key,
                vapid_claims={"sub": self.service.cfg.push.subject},
                ttl=3600,
                timeout=10,
            )
            return True, None, None
        except WebPushException as e:
            status = e.response.status_code if e.response is not None else None
            return False, status, str(e)[:300]
        except Exception as e:
            return False, None, f"{type(e).__name__}: {e}"[:300]

    async def send(self, alert: dict[str, Any], is_public: bool) -> tuple[int, int]:
        if not self.available:
            return 0, 0
        # Avisos públicos: suscripciones públicas y del panel; los internos, solo del panel.
        query = "SELECT id, endpoint, p256dh, auth, failures FROM push_subscriptions WHERE scope = 'admin'"
        if is_public:
            query += " OR scope = 'public'"

        def q(conn: Connection) -> list[dict[str, Any]]:
            rows = conn.execute(text(query)).mappings().all()
            return [dict(r) for r in rows]

        subs = await self.service.db.read(q)
        if not subs:
            return 0, 0
        node = alert.get("node")
        payload = orjson.dumps(
            {
                "title": alert.get("title"),
                "body": alert.get("body") or "",
                "severity": alert.get("severity"),
                "url": f"/n/{node}" if node else "/alertas",
                "tag": f"alert-{alert.get('id')}",
                "ts": alert.get("ts"),
            }
        )
        sem = asyncio.Semaphore(4)
        ok = fail = 0

        async def one(sub: dict[str, Any]) -> None:
            nonlocal ok, fail
            async with sem:
                success, status, error = await asyncio.to_thread(self._send_one, sub, payload)
            if success:
                ok += 1
                await self.service.writer.run(
                    lambda c: c.execute(
                        text(
                            "UPDATE push_subscriptions SET last_ok_at = :t, failures = 0 WHERE id = :i"
                        ),
                        {"t": time.time(), "i": sub["id"]},
                    )
                )
                return
            fail += 1
            if status in (404, 410) or sub["failures"] + 1 >= MAX_FAILURES:
                await self.service.writer.run(
                    lambda c: c.execute(
                        text("DELETE FROM push_subscriptions WHERE id = :i"), {"i": sub["id"]}
                    )
                )
            else:
                await self.service.writer.run(
                    lambda c: c.execute(
                        text("UPDATE push_subscriptions SET failures = failures + 1 WHERE id = :i"),
                        {"i": sub["id"]},
                    )
                )
            log.info("push falló (%s): %s", status, error)

        await asyncio.gather(*(one(s) for s in subs))
        self.sent += ok
        self.failed += fail
        return ok, fail
