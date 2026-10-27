"""Capa de datos: respaldos, migraciones, escritor, retención, agregados y consultas (11)."""

from __future__ import annotations

import gzip
import os
import sqlite3
import time
from pathlib import Path

import orjson
import pytest
from sqlalchemy import text

from meshbox.config import RetentionCfg
from meshbox.store import backup, migrate, queries, rollups
from meshbox.store.db import BatchWriter, Database
from meshbox.store.retention import maintenance, run_retention

from ..conftest import Pipe

SIM = Path(__file__).parent.parent / "fixtures" / "sim-24h.jsonl"


# --------------------------------------------------------------------------- respaldos


def test_backup_create_list_prune_restore(tmp_path: Path, migrated_db: Path) -> None:
    con = sqlite3.connect(migrated_db)
    con.execute("INSERT INTO settings (key, value, updated_at) VALUES ('x', '1', 0)")
    con.commit()
    con.close()
    bdir = tmp_path / "bk"
    info = backup.create_backup(migrated_db, bdir)
    assert info.daily and (bdir / info.name).exists()
    with gzip.open(bdir / info.name) as f:
        assert f.read(16).startswith(b"SQLite format 3")
    tagged = backup.create_backup(migrated_db, bdir, suffix="pre-1.2.3")
    assert not tagged.daily and "pre-1.2.3" in tagged.name
    for i in range(10):  # más de los que se conservan, todos más viejos que los reales
        for name in (f"meshbox-2026010{i}.db.gz", f"meshbox-20260101-00000{i}-tag.db.gz"):
            (bdir / name).write_bytes(b"x")
            os.utime(bdir / name, (1_700_000_000 + i, 1_700_000_000 + i))
    removed = backup.prune(bdir)
    left = backup.list_backups(bdir)
    assert sum(b.daily for b in left) == backup.KEEP_DAILY
    assert sum(not b.daily for b in left) == backup.KEEP_TAGGED
    assert removed
    # restauración con validación
    con = sqlite3.connect(migrated_db)
    con.execute("DELETE FROM settings")
    con.commit()
    con.close()
    assert (bdir / info.name).exists() and (bdir / tagged.name).exists()
    backup.restore_backup(bdir / info.name, migrated_db)
    con = sqlite3.connect(migrated_db)
    assert con.execute("SELECT value FROM settings WHERE key='x'").fetchone() == ("1",)
    con.close()


def test_restore_rejects_invalid_file(tmp_path: Path, migrated_db: Path) -> None:
    bad = tmp_path / "meshbox-20260101.db.gz"
    with gzip.open(bad, "wb") as f:
        f.write(b"esto no es una base")
    with pytest.raises(ValueError):
        backup.restore_backup(bad, migrated_db)
    other = tmp_path / "otra.db"
    sqlite3.connect(other).execute("CREATE TABLE t (x)").connection.commit()
    gz = tmp_path / "meshbox-20260102.db.gz"
    with other.open("rb") as fi, gzip.open(gz, "wb") as fo:
        fo.write(fi.read())
    with pytest.raises(ValueError, match="no es una base de meshbox"):
        backup.restore_backup(gz, migrated_db)


def test_backup_name_validation() -> None:
    assert backup.valid_backup_name("meshbox-20261020.db.gz")
    assert backup.valid_backup_name("meshbox-20261020-101010-pre-1.0.0.db.gz")
    assert not backup.valid_backup_name("../secrets.toml")
    assert not backup.valid_backup_name("meshbox-../../x.db.gz")
    assert "x_y" in backup.backup_name("x/y")


# --------------------------------------------------------------------------- migraciones


def test_migrate_new_existing_and_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "m.db"
    assert migrate.pending(db)
    assert migrate.migrate(db, tmp_path / "bk", "1.0.0") == "created"
    assert migrate.current_revision(db) == migrate.HEAD
    con = sqlite3.connect(db)
    assert con.execute("PRAGMA auto_vacuum").fetchone()[0] == 2  # INCREMENTAL
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    con.close()
    assert migrate.migrate(db, tmp_path / "bk", "1.0.0") == "up-to-date"
    # simular una migración pendiente que falla: se restaura el respaldo
    con = sqlite3.connect(db)
    con.execute("UPDATE alembic_version SET version_num = '0000'")
    con.execute("INSERT INTO settings (key, value, updated_at) VALUES ('antes', '1', 0)")
    con.commit()
    con.close()

    def boom(_db: Path) -> None:
        c = sqlite3.connect(_db)
        c.execute("DELETE FROM settings")
        c.commit()
        c.close()
        raise RuntimeError("migración rota")

    monkeypatch.setattr(migrate, "upgrade", boom)
    with pytest.raises(RuntimeError):
        migrate.migrate(db, tmp_path / "bk", "2.0.0")
    con = sqlite3.connect(db)
    assert con.execute("SELECT value FROM settings WHERE key='antes'").fetchone() == ("1",)
    con.close()
    assert any("pre-2.0.0" in b.name for b in backup.list_backups(tmp_path / "bk"))


def test_head_matches_alembic_script() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option("script_location", str(migrate.MIGRATIONS_DIR))
    assert ScriptDirectory.from_config(cfg).get_current_head() == migrate.HEAD


def test_schema_matches_migration(migrated_db: Path) -> None:
    """Las tablas de schema.py coinciden con el DDL de la migración escrita a mano."""
    from meshbox.store.schema import metadata

    con = sqlite3.connect(migrated_db)
    for table in metadata.sorted_tables:
        cols = {r[1] for r in con.execute(f"PRAGMA table_info({table.name})")}
        assert cols == {c.name for c in table.columns}, table.name
    con.close()


# --------------------------------------------------------------------------- escritor


async def test_writer_overflow_and_isolation(migrated_db: Path) -> None:
    db = Database(migrated_db)
    w = BatchWriter(db, flush_interval_s=60, flush_max_ops=10_000, max_queue=5)
    overflows: list[int] = []
    w.on_overflow = overflows.append
    await w.start()
    try:
        pk = w.ids.next("packets")
        base = {"from_num": 1, "to_num": 2, "channel_index": 0, "channel_name": "c", "channel_hash": None,
                "portnum": "X", "first_rx": 1.0, "hop_start": 3, "want_ack": 0, "priority": None, "encrypted": 0,
                "decoded_ok": 1, "is_public": 1, "payload_len": 1}  # fmt: skip
        for i in range(6):
            w.enqueue("packet", {**base, "pk": pk + i, "packet_id": 100 + i, "raw": b"crudo"})
        w.enqueue("reception", {"packet_pk": pk, "gateway": "g", "source": "mqtt", "rx_time": 1.0, "rx_snr": None,
                                "rx_rssi": None, "hop_limit": 3, "relay_node": None, "via_mqtt": 0, "transport": None})  # fmt: skip
        assert w.dropped_ops == 2 and overflows  # crudo del 6.º paquete y la recepción
        # una operación inválida no tira el lote completo
        w.enqueue("position", {"node_num": 1, "ts": 1.0, "lat": None, "lon": 2.0, "alt": None, "precision_bits": None,
                               "ground_speed": None, "sats": None, "packet_pk": None})  # fmt: skip
        await w.flush()
        assert w.failed_ops == 1

        def count(conn) -> tuple[int, int]:  # type: ignore[no-untyped-def]
            return (
                conn.execute(text("SELECT count(*) FROM packets")).scalar_one(),
                conn.execute(text("SELECT count(*) FROM packets WHERE raw IS NULL")).scalar_one(),
            )

        assert await db.read(count) == (6, 1)
        stats = w.stats()
        assert stats["written_ops"] >= 6 and stats["batches"] >= 1
    finally:
        await w.stop()
        await db.dispose()


async def test_writer_run_returns_and_propagates(migrated_db: Path) -> None:
    db = Database(migrated_db)
    w = BatchWriter(db)
    await w.start()
    try:
        assert await w.run(lambda c: c.execute(text("SELECT 41 + 1")).scalar_one()) == 42
        with pytest.raises(Exception, match="no such table"):
            await w.run(lambda c: c.execute(text("SELECT * FROM inexistente")))
        await w.wait_below(0)
    finally:
        await w.stop()
        await db.dispose()


# --------------------------------------------------------------------------- consultas, agregados, retención


async def test_queries_rollups_retention(pipe: Pipe) -> None:
    await pipe.feed_file(SIM)
    rows = await pipe.rows("SELECT min(first_rx) AS a, max(first_rx) AS b FROM packets")
    t0, t1 = float(rows[0]["a"]), float(rows[0]["b"])
    n = await pipe.writer.run(lambda c: rollups.backfill(c, t0, t1 + 3600))
    assert n >= 24
    assert int(await pipe.scalar("SELECT count(*) FROM stats_hourly")) >= 24  # type: ignore[call-overload]
    assert (
        int(await pipe.scalar("SELECT count(*) FROM telemetry_rollup WHERE bucket_s = 86400")) > 0
    )  # type: ignore[call-overload]
    db = pipe.db
    techo = 0x0B03CBF0
    raw = await db.read(lambda c: queries.telemetry_series(c, techo, "device", t1 - 6 * 3600, t1))
    assert raw["resolution"] == "raw" and raw["ts"] and "voltage" in raw["series"]
    # Sin crudos guardados (retención 0): agregados horarios.
    hourly = await db.read(
        lambda c: queries.telemetry_series(c, techo, "device", t0, t0 + 3 * 86400, 0)
    )
    assert hourly["resolution"] == "hour" and hourly["ts"]
    # Con crudos: grupos de minutos con mínimo y máximo (7 días → grupos de 5 min).
    week = await db.read(
        lambda c: queries.telemetry_series(c, techo, "device", t1 - 7 * 86400, t1, 10**10)
    )
    assert week["resolution"] == "bucket" and week["bucket_s"] == 300 and week["ts"]
    assert len(week["ts"]) <= 2100 and set(week["min"]) == set(week["series"])
    v, lo, hi = week["series"]["voltage"], week["min"]["voltage"], week["max"]["voltage"]
    assert all(a <= b <= c for a, b, c in zip(lo, v, hi, strict=True) if b is not None)
    daily = await db.read(
        lambda c: queries.telemetry_series(c, techo, "power", t0 - 100 * 86400, t1)
    )
    assert daily["resolution"] == "day"
    cam = 0x0B03CBF5
    pos = await db.read(lambda c: queries.node_positions(c, cam, t0, t1, 20))
    assert 0 < len(pos) <= 21 and any(p["speed_kmh"] for p in pos)
    hidden = {next(iter(pipe.state.nodes))}
    links_all = await db.read(lambda c: queries.links(c, 10**9, set()))
    links_vis = await db.read(lambda c: queries.links(c, 10**9, hidden))
    assert len(links_vis) <= len(links_all)
    trs = await db.read(lambda c: queries.traceroutes(c, None, 10, set()))
    assert len(trs) == 4 and trs[0]["route"]
    wps = await db.read(lambda c: queries.waypoints(c, t0))
    assert wps and wps[0]["name"] == "Punto de encuentro"
    names = {n: r.long_name for n, r in pipe.state.nodes.items()}
    page1, nxt = await db.read(lambda c: queries.messages_page(c, None, 10, names))
    assert len(page1) == 10 and nxt
    page2, _ = await db.read(
        lambda c: queries.messages_page(
            c, (float(nxt.split(":")[0]), int(nxt.split(":")[1])), 10, names
        )
    )
    assert {m["pk"] for m in page1}.isdisjoint({m["pk"] for m in page2})
    ts = await db.read(lambda c: queries.stats_timeseries(c, "by_portnum", "30d", t1 + 3600))
    assert ts["values"] and isinstance(ts["values"][0], dict)
    totals = await db.read(lambda c: queries.stats_totals(c, "30d", t1 + 3600))
    assert totals["by_portnum"]["POSITION_APP"] > 0
    relays = await db.read(lambda c: queries.relays(c, t0, pipe.state.nodes))
    assert relays and relays[0]["candidates"]
    # Retransmisiones: agregados horarios (by_relay) + bordes en vivo == todo en vivo.
    end = t1 + 3600
    live = await db.read(
        lambda c: dict(c.execute(text(queries.RELAY_SQL), {"s": t0, "e": end}).all())
    )
    via_rollups = await db.read(lambda c: queries.relay_counts(c, t0, end))
    assert dict(via_rollups) == live and sum(live.values()) > 0
    hops = await db.read(lambda c: queries.hops_distribution(c, t0))
    assert set(hops) <= {"0", "1", "2", "3"}
    # retención: todo lo de la grabación es "viejo" si el ahora está 400 días después
    totals_del = await run_retention(pipe.writer.run, RetentionCfg(), now=t1 + 400 * 86400)
    assert totals_del["packets"] > 0 and totals_del["positions"] > 0
    assert await pipe.scalar("SELECT count(*) FROM packets") == 0
    assert await pipe.scalar("SELECT count(*) FROM receptions") == 0  # ON DELETE CASCADE
    await pipe.writer.run(maintenance)


async def test_alerts_page_and_dest(pipe: Pipe) -> None:
    now = time.time()

    def ins(conn) -> None:  # type: ignore[no-untyped-def]
        for i in range(5):
            conn.execute(
                text(
                    "INSERT INTO alert_events (id, ts, state, title, severity, is_public) VALUES (:i, :t, 'firing', 'x', 'info', :p)"
                ),
                {"i": i + 1, "t": now + i, "p": i % 2},
            )

    await pipe.writer.run(ins)
    pub, _ = await pipe.db.read(lambda c: queries.alerts_page(c, None, 10))
    allr, nxt = await pipe.db.read(lambda c: queries.alerts_page(c, None, 2, public_only=False))
    assert len(pub) == 2 and len(allr) == 2 and nxt
    assert queries.dest_id(0xFFFFFFFF) == "^all" and queries.dest_id(1) == "!00000001"
    assert queries.nan_to_none(float("nan")) is None
    assert orjson.loads(orjson.dumps({"a": 1}))["a"] == 1
