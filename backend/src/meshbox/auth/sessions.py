"""Sesiones del panel (sección 13.2).

Token aleatorio de 32 bytes solo en la cookie; en la base se guarda su SHA-256. Vence a
los 7 días o a las 12 h sin uso. Token CSRF por sesión, enviado en `X-CSRF-Token`.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, text

from ..store.db import BatchWriter, Database

COOKIE = "meshbox_session"
LIFETIME_S = 7 * 86400
IDLE_S = 12 * 3600
TOUCH_EVERY_S = 60


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(slots=True)
class SessionInfo:
    token_hash: str
    user_id: int
    username: str
    role: str
    csrf_token: str
    created_at: float
    expires_at: float
    last_seen_at: float
    must_change_password: bool = False
    ip: str | None = None
    user_agent: str | None = None
    via: str = "lan"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def public(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role,
            "csrf_token": self.csrf_token,
            "expires_at": self.expires_at,
            "must_change_password": self.must_change_password,
        }


class SessionStore:
    def __init__(self, db: Database, writer: BatchWriter) -> None:
        self.db = db
        self.writer = writer
        self._cache: dict[str, SessionInfo] = {}

    async def create(
        self,
        user_id: int,
        username: str,
        role: str,
        must_change: bool,
        ip: str | None,
        user_agent: str | None,
    ) -> tuple[str, SessionInfo]:
        token = secrets.token_urlsafe(32)
        now = time.time()
        info = SessionInfo(
            token_hash=token_hash(token),
            user_id=user_id,
            username=username,
            role=role,
            csrf_token=secrets.token_urlsafe(24),
            created_at=now,
            expires_at=now + LIFETIME_S,
            last_seen_at=now,
            must_change_password=must_change,
            ip=ip,
            user_agent=(user_agent or "")[:200] or None,
        )

        def ins(conn: Connection) -> None:
            conn.execute(
                text(
                    "INSERT INTO sessions (token_hash, user_id, csrf_token, created_at, expires_at, "
                    "last_seen_at, ip, user_agent) VALUES (:th, :uid, :csrf, :c, :e, :l, :ip, :ua)"
                ),
                {
                    "th": info.token_hash,
                    "uid": user_id,
                    "csrf": info.csrf_token,
                    "c": now,
                    "e": info.expires_at,
                    "l": now,
                    "ip": ip,
                    "ua": info.user_agent,
                },
            )
            conn.execute(
                text("UPDATE users SET last_login_at = :n WHERE id = :u"), {"n": now, "u": user_id}
            )

        await self.writer.run(ins)
        self._cache[info.token_hash] = info
        return token, info

    async def get(self, token: str | None) -> SessionInfo | None:
        if not token or len(token) > 200:
            return None
        th = token_hash(token)
        info = self._cache.get(th)
        if info is None:
            info = await self.db.read(lambda c: self._load(c, th))
            if info is None:
                return None
            self._cache[th] = info
        now = time.time()
        if now > info.expires_at or now - info.last_seen_at > IDLE_S:
            await self.delete_hash(th)
            return None
        if now - info.last_seen_at > TOUCH_EVERY_S:
            info.last_seen_at = now

            def touch(c: Connection, h: str = th, t: float = now) -> None:
                c.execute(
                    text("UPDATE sessions SET last_seen_at = :t WHERE token_hash = :h"),
                    {"t": t, "h": h},
                )

            self.writer.enqueue_fn(touch)
        return info

    @staticmethod
    def _load(conn: Connection, th: str) -> SessionInfo | None:
        row = conn.execute(
            text(
                "SELECT s.token_hash, s.user_id, u.username, u.role, s.csrf_token, s.created_at, "
                "s.expires_at, s.last_seen_at, u.must_change_password, s.ip, s.user_agent, u.disabled "
                "FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = :h"
            ),
            {"h": th},
        ).first()
        if row is None or row[11]:
            return None
        return SessionInfo(
            token_hash=row[0],
            user_id=row[1],
            username=row[2],
            role=row[3],
            csrf_token=row[4],
            created_at=row[5],
            expires_at=row[6],
            last_seen_at=row[7],
            must_change_password=bool(row[8]),
            ip=row[9],
            user_agent=row[10],
        )

    async def delete_hash(self, th: str) -> None:
        self._cache.pop(th, None)
        await self.writer.run(
            lambda c: c.execute(text("DELETE FROM sessions WHERE token_hash = :h"), {"h": th})
        )

    async def delete_user_sessions(self, user_id: int, except_hash: str | None = None) -> None:
        for h, info in list(self._cache.items()):
            if info.user_id == user_id and h != except_hash:
                del self._cache[h]
        await self.writer.run(
            lambda c: c.execute(
                text("DELETE FROM sessions WHERE user_id = :u AND token_hash != :keep"),
                {"u": user_id, "keep": except_hash or ""},
            )
        )

    def invalidate_user(self, user_id: int) -> None:
        for h, info in list(self._cache.items()):
            if info.user_id == user_id:
                del self._cache[h]

    async def list_all(self) -> list[dict[str, Any]]:
        def q(conn: Connection) -> list[dict[str, Any]]:
            rows = conn.execute(
                text(
                    "SELECT s.token_hash, s.user_id, u.username, s.created_at, s.expires_at, s.last_seen_at, "
                    "s.ip, s.user_agent FROM sessions s JOIN users u ON u.id = s.user_id "
                    "WHERE s.expires_at > :n ORDER BY s.last_seen_at DESC"
                ),
                {"n": time.time()},
            ).all()
            return [
                {
                    "id": r[0][:16],
                    "user_id": r[1],
                    "username": r[2],
                    "created_at": r[3],
                    "expires_at": r[4],
                    "last_seen_at": r[5],
                    "ip": r[6],
                    "user_agent": r[7],
                }
                for r in rows
            ]

        return await self.db.read(q)

    async def delete_by_prefix(self, prefix: str) -> bool:
        if len(prefix) < 16:
            return False

        def q(conn: Connection) -> str | None:
            row = conn.execute(
                text("SELECT token_hash FROM sessions WHERE substr(token_hash, 1, 16) = :p"),
                {"p": prefix[:16]},
            ).first()
            return row[0] if row else None

        th = await self.db.read(q)
        if th is None:
            return False
        await self.delete_hash(th)
        return True


def csrf_ok(info: SessionInfo, header: str | None) -> bool:
    return bool(header) and hmac.compare_digest(info.csrf_token, header or "")
