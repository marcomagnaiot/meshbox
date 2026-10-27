"""Usuarios del panel y auditoría (secciones 13.2 y 18.2)."""

from __future__ import annotations

import re
import time
from typing import Any

import orjson
from sqlalchemy import Connection, text

from ..config import Config
from ..store.db import BatchWriter, Database
from .passwords import hash_password_async, validate_password

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,31}$")
ROLES = ("admin", "operator")


def valid_username(name: str) -> bool:
    return bool(USERNAME_RE.match(name))


def count_users(conn: Connection) -> int:
    return int(conn.execute(text("SELECT count(*) FROM users")).scalar_one())


def get_user(
    conn: Connection, *, username: str | None = None, user_id: int | None = None
) -> dict[str, Any] | None:
    if username is not None:
        row = (
            conn.execute(text("SELECT * FROM users WHERE username = :u"), {"u": username.lower()})
            .mappings()
            .first()
        )
    else:
        row = (
            conn.execute(text("SELECT * FROM users WHERE id = :i"), {"i": user_id})
            .mappings()
            .first()
        )
    return dict(row) if row else None


def list_users(conn: Connection) -> list[dict[str, Any]]:
    rows = (
        conn.execute(
            text(
                "SELECT id, username, role, disabled, created_at, last_login_at, must_change_password "
                "FROM users ORDER BY username"
            )
        )
        .mappings()
        .all()
    )
    return [
        {
            **dict(r),
            "disabled": bool(r["disabled"]),
            "must_change_password": bool(r["must_change_password"]),
        }
        for r in rows
    ]


async def create_user(
    writer: BatchWriter, username: str, password: str, role: str, must_change: bool = False
) -> int:
    username = username.lower().strip()
    if not valid_username(username):
        raise ValueError("usuario no válido (minúsculas, números, punto, guion; 3 a 32)")
    if role not in ROLES:
        raise ValueError("rol no válido")
    err = validate_password(password, username)
    if err:
        raise ValueError(err)
    pw_hash = await hash_password_async(password)

    def ins(conn: Connection) -> int:
        if get_user(conn, username=username) is not None:
            raise ValueError("el usuario ya existe")
        res = conn.execute(
            text(
                "INSERT INTO users (username, password_hash, role, disabled, created_at, must_change_password) "
                "VALUES (:u, :h, :r, 0, :c, :m)"
            ),
            {"u": username, "h": pw_hash, "r": role, "c": time.time(), "m": int(must_change)},
        )
        return int(res.lastrowid or 0)

    return await writer.run(ins)


async def set_password(
    writer: BatchWriter, user_id: int, username: str, password: str, must_change: bool = False
) -> None:
    err = validate_password(password, username)
    if err:
        raise ValueError(err)
    pw_hash = await hash_password_async(password)
    await writer.run(
        lambda c: c.execute(
            text("UPDATE users SET password_hash = :h, must_change_password = :m WHERE id = :i"),
            {"h": pw_hash, "m": int(must_change), "i": user_id},
        )
    )


def audit_row(
    user_id: int | None, action: str, target: str | None, details: Any, ip: str | None
) -> dict[str, Any]:
    if details is not None and not isinstance(details, str):
        details = orjson.dumps(details).decode()
    return {
        "ts": time.time(),
        "user_id": user_id,
        "action": action,
        "target": target,
        "details": details,
        "ip": ip,
    }


def audit(
    writer: BatchWriter,
    user_id: int | None,
    action: str,
    target: str | None = None,
    details: Any = None,
    ip: str | None = None,
) -> None:
    row = audit_row(user_id, action, target, details, ip)
    writer.enqueue_fn(
        lambda c: c.execute(
            text(
                "INSERT INTO audit_log (ts, user_id, action, target, details, ip) "
                "VALUES (:ts, :user_id, :action, :target, :details, :ip)"
            ),
            row,
        )
    )


def audit_page(
    conn: Connection, before: float | None, limit: int, action: str | None = None
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"limit": limit}
    where = "1=1"
    if before is not None:
        where += " AND a.ts < :b"
        params["b"] = before
    if action:
        where += " AND a.action LIKE :a"
        params["a"] = f"{action}%"
    rows = (
        conn.execute(
            text(
                "SELECT a.id, a.ts, a.user_id, u.username, a.action, a.target, a.details, a.ip FROM audit_log a "
                f"LEFT JOIN users u ON u.id = a.user_id WHERE {where} ORDER BY a.ts DESC LIMIT :limit"
            ),
            params,
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------- CLI


async def cli_user(
    cfg: Config, action: str, username: str | None, role: str, password: str | None
) -> int:
    from ..store.migrate import migrate

    migrate(cfg.paths.db, cfg.paths.backups, "cli", cfg.paths.tmp)
    db = Database(cfg.paths.db)
    writer = BatchWriter(db)
    await writer.start()
    try:
        if action == "list":
            for u in await db.read(list_users):
                flag = " (deshabilitado)" if u["disabled"] else ""
                print(f"{u['id']}\t{u['username']}\t{u['role']}{flag}")
            return 0
        if not username:
            print("falta el nombre de usuario")
            return 2
        if action == "create":
            assert password is not None
            uid = await create_user(writer, username, password, role)
            audit(writer, None, "user.create", username, {"role": role, "via": "cli"})
            print(f"usuario {username} creado (id {uid}, rol {role})")
            return 0
        user = await db.read(lambda c: get_user(c, username=username.lower()))
        if user is None:
            print(f"no existe el usuario {username}")
            return 1
        if action == "passwd":
            assert password is not None
            await set_password(writer, user["id"], user["username"], password)
            await writer.run(
                lambda c: c.execute(
                    text("DELETE FROM sessions WHERE user_id = :u"), {"u": user["id"]}
                )
            )
            audit(writer, None, "user.password", username, {"via": "cli"})
            print("contraseña cambiada; sesiones cerradas")
        elif action in ("disable", "enable"):
            value = 1 if action == "disable" else 0
            await writer.run(
                lambda c: c.execute(
                    text("UPDATE users SET disabled = :d WHERE id = :i"),
                    {"d": value, "i": user["id"]},
                )
            )
            audit(writer, None, f"user.{action}", username, {"via": "cli"})
            print(f"usuario {username}: {'deshabilitado' if value else 'habilitado'}")
        return 0
    except ValueError as e:
        print(f"error: {e}")
        return 1
    finally:
        await writer.stop()
        await db.dispose()
