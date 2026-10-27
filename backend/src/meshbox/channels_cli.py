"""`meshbox channel list|add|remove`: canales y claves sin pasar por el panel."""

from __future__ import annotations

from sqlalchemy import text

from .config import Config, SecretStore
from .pipeline.crypto import channel_hash, decode_psk
from .store.db import BatchWriter, Database
from .store.migrate import migrate


async def channel_cli(
    cfg: Config, action: str, name: str | None, key: str | None, public: bool
) -> int:
    migrate(cfg.paths.db, cfg.paths.backups, "cli", cfg.paths.tmp)
    db = Database(cfg.paths.db)
    writer = BatchWriter(db)
    await writer.start()
    secrets = SecretStore(cfg.paths.secrets)
    try:
        if action == "list":
            rows = await db.read(
                lambda c: c.execute(
                    text("SELECT id, name, hash, key_ref, is_public FROM channels ORDER BY id")
                ).all()
            )
            for cid, n, h, ref, pub in rows:
                print(
                    f"{cid}\t{n}\thash={h}\tclave={'sí' if ref and secrets.get(ref) else 'no'}\t{'público' if pub else 'privado'}"
                )
            return 0
        if not name:
            print("falta --name")
            return 2
        if action == "add":
            psk = decode_psk(key or "AQ==")
            ref = f"channels.{name}"
            secrets.set(ref, key or "AQ==")
            h = channel_hash(name, psk)
            await writer.run(
                lambda c: c.execute(
                    text(
                        "INSERT INTO channels (name, hash, key_ref, is_public) VALUES (:n, :h, :r, :p)"
                    ),
                    {"n": name, "h": h, "r": ref, "p": int(public)},
                )
            )
            print(f"canal {name} agregado (hash {h}, {'público' if public else 'privado'})")
        elif action == "remove":
            await writer.run(
                lambda c: c.execute(text("DELETE FROM channels WHERE name = :n"), {"n": name})
            )
            secrets.delete(f"channels.{name}")
            print(f"canal {name} eliminado")
        return 0
    finally:
        await writer.stop()
        await db.dispose()
