from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import text

from meshbox.bus import EventBus
from meshbox.config import Config, SecretStore
from meshbox.connectors.replay import read_recording, record_to_packet
from meshbox.models import RawPacket
from meshbox.pipeline.process import Processor
from meshbox.state import MeshState
from meshbox.store.db import BatchWriter, Database
from meshbox.store.migrate import migrate

FIXTURES = Path(__file__).parent / "fixtures"
FAMILIA_KEY = "q0Kn3Ys7mQ5rUjXp2bF9tA=="

if sys.platform == "win32":

    def pytest_asyncio_loop_factories(config: object, item: object) -> dict[str, object]:
        # aiomqtt necesita SelectorEventLoop en Windows (el Proactor no tiene add_writer)
        return {"selector": asyncio.SelectorEventLoop}


def make_cfg(tmp_path: Path) -> Config:
    cfg = Config()
    cfg.paths.db = tmp_path / "meshbox.db"
    cfg.paths.backups = tmp_path / "backups"
    cfg.paths.tmp = tmp_path / "tmp"
    cfg.paths.secrets = tmp_path / "secrets.toml"
    cfg.paths.recordings = tmp_path / "rec"
    cfg.paths.tiles = tmp_path / "tiles"
    cfg.paths.plugins = tmp_path / "plugins"
    cfg.system.privd = "fake"
    cfg.writer.flush_interval_s = 0.05
    return cfg


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    return make_cfg(tmp_path)


@pytest.fixture
def migrated_db(cfg: Config) -> Path:
    migrate(cfg.paths.db, cfg.paths.backups, "test", cfg.paths.tmp)
    return cfg.paths.db


@dataclass
class Pipe:
    cfg: Config
    db: Database
    writer: BatchWriter
    state: MeshState
    bus: EventBus
    proc: Processor
    secrets: SecretStore

    async def feed_file(self, path: Path, limit: int | None = None) -> int:
        n = 0
        for rec in read_recording(path):
            pkt = record_to_packet(rec)
            if pkt is None:
                self.state.invalid_total += 1
                continue
            self.proc.process(
                RawPacket(
                    source="replay",
                    connector_id=str(rec.get("connector_id") or "replay"),
                    gateway_id=rec.get("gateway_id"),
                    channel_id=rec.get("channel_id"),
                    rx_time=float(rec["rx_time"]),
                    packet=pkt,
                )
            )
            n += 1
            if limit and n >= limit:
                break
        await self.flush()
        return n

    async def flush(self) -> None:
        self.proc.flush_dirty_nodes()
        await self.writer.flush()

    async def scalar(self, sql: str, **params: object) -> object:
        def q(conn):  # type: ignore[no-untyped-def]
            return conn.execute(text(sql), params).scalar()

        return await self.db.read(q)

    async def rows(self, sql: str, **params: object) -> list[dict[str, object]]:
        def q(conn):  # type: ignore[no-untyped-def]
            return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]

        return await self.db.read(q)


async def seed_channels(db: Database, writer: BatchWriter, secrets: SecretStore) -> None:
    secrets.set("channels.MediumFast", "AQ==", save=False)
    secrets.set("channels.Familia", FAMILIA_KEY, save=False)
    secrets.save()

    def ins(conn):  # type: ignore[no-untyped-def]
        conn.execute(
            text(
                "INSERT INTO channels (name, hash, key_ref, is_public) VALUES "
                "('MediumFast', 31, 'channels.MediumFast', 1), "
                "('Familia', NULL, 'channels.Familia', 0)"
            )
        )

    await writer.run(ins)


@pytest.fixture
async def pipe(cfg: Config, migrated_db: Path) -> AsyncIterator[Pipe]:
    db = Database(cfg.paths.db)
    bus = EventBus()
    writer = BatchWriter(db, flush_interval_s=0.05, flush_max_ops=200, max_queue=100_000)
    await writer.start()
    secrets = SecretStore(cfg.paths.secrets)
    await seed_channels(db, writer, secrets)
    state = MeshState()
    await db.read(lambda c: state.load_from_db(c, secrets.get))
    proc = Processor(cfg, state, writer, bus)
    p = Pipe(cfg, db, writer, state, bus, proc, secrets)
    try:
        yield p
    finally:
        await writer.stop()
        await db.dispose()
