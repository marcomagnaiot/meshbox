"""Retención (sección 11.4): borra por lotes de 5.000 filas para no bloquear al escritor."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import Connection, text

from ..config import RetentionCfg

log = logging.getLogger(__name__)
BATCH = 5000
DAY = 86400.0

# (tabla, columna de tiempo, campo de RetentionCfg, columna de rowid o pk para el lote)
RULES: list[tuple[str, str, str, str]] = [
    ("packets", "first_rx", "packets", "pk"),
    ("positions", "ts", "positions", "rowid"),
    ("telemetry_device", "ts", "telemetry_raw", "rowid"),
    ("telemetry_environment", "ts", "telemetry_raw", "rowid"),
    ("telemetry_power", "ts", "telemetry_raw", "rowid"),
    ("messages", "ts", "messages", "pk"),
    ("radio_messages", "ts", "radio_messages", "id"),
    ("traceroutes", "ts", "traceroutes", "pk"),
    ("links", "ts", "links", "rowid"),
    ("alert_events", "ts", "alerts", "id"),
    ("notification_log", "ts", "alerts", "id"),
    ("audit_log", "ts", "audit", "id"),
]


def _delete_batch(conn: Connection, table: str, ts_col: str, cutoff: float, key: str) -> int:
    if key == "rowid":
        # Tablas WITHOUT ROWID: se borra por la clave primaria compuesta con LIMIT vía subconsulta.
        pk_cols = {
            "positions": "node_num, ts",
            "telemetry_device": "node_num, ts",
            "telemetry_environment": "node_num, ts",
            "telemetry_power": "node_num, ts",
            "links": "node_num, neighbor_num, source",
        }[table]
        res = conn.execute(
            text(
                f"DELETE FROM {table} WHERE ({pk_cols}) IN ("
                f"SELECT {pk_cols} FROM {table} WHERE {ts_col} < :cut LIMIT {BATCH})"
            ),
            {"cut": cutoff},
        )
    else:
        res = conn.execute(
            text(
                f"DELETE FROM {table} WHERE {key} IN ("
                f"SELECT {key} FROM {table} WHERE {ts_col} < :cut LIMIT {BATCH})"
            ),
            {"cut": cutoff},
        )
    return res.rowcount or 0


async def run_retention(
    run: Callable[[Callable[[Connection], Any]], Awaitable[Any]],
    cfg: RetentionCfg,
    now: float | None = None,
) -> dict[str, int]:
    """Aplica la retención. `run` es `BatchWriter.run` (cada lote en su transacción)."""
    now = now or time.time()
    totals: dict[str, int] = {}
    for table, ts_col, field, key in RULES:
        days = getattr(cfg, field)
        cutoff = now - days * DAY
        total = 0
        while True:

            def batch(
                c: Connection, t: str = table, col: str = ts_col, k: str = key, cut: float = cutoff
            ) -> int:
                return _delete_batch(c, t, col, cut, k)

            n = await run(batch)
            total += int(n)
            if n < BATCH:
                break
        totals[table] = total
    # agregados horarios: rollup_hourly días; diarios sin límite
    cutoff = now - cfg.rollup_hourly * DAY
    totals["telemetry_rollup"] = int(
        await run(
            lambda c: (
                c.execute(
                    text(
                        "DELETE FROM telemetry_rollup WHERE bucket_s = 3600 AND bucket_start < :c"
                    ),
                    {"c": cutoff},
                ).rowcount
                or 0
            )
        )
    )
    # sesiones vencidas (a diario, no configurable)
    totals["sessions"] = int(
        await run(
            lambda c: (
                c.execute(text("DELETE FROM sessions WHERE expires_at < :n"), {"n": now}).rowcount
                or 0
            )
        )
    )
    log.info("retención aplicada: %s", {k: v for k, v in totals.items() if v})
    return totals


def maintenance(conn: Connection) -> None:
    """Tarea diaria: PRAGMA optimize e incremental_vacuum(2000) (11.1)."""
    conn.exec_driver_sql("PRAGMA optimize")
    conn.exec_driver_sql("PRAGMA incremental_vacuum(2000)")
