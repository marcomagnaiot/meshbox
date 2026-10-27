"""Agregados (sección 11.4): `telemetry_rollup` horario y diario, y `stats_hourly`.

Funciones síncronas que corren en la conexión del escritor (`BatchWriter.run`).
"""

from __future__ import annotations

import time
from typing import Any

import orjson
from sqlalchemy import Connection, text

from ..pipeline.decode import POWER_FIELDS
from .queries import DEVICE_METRICS, ENV_METRICS, KIND_TABLE, RELAY_SQL

METRICS = {"device": DEVICE_METRICS, "environment": ENV_METRICS, "power": POWER_FIELDS}


def hour_floor(ts: float) -> float:
    return float(int(ts // 3600) * 3600)


def rollup_hour(conn: Connection, hour_start: float) -> int:
    """Agrega una hora de telemetría cruda en `telemetry_rollup` (bucket 3600)."""
    end = hour_start + 3600
    n = 0
    for kind, metrics in METRICS.items():
        table = KIND_TABLE[kind]
        for m in metrics:
            res = conn.execute(
                text(
                    "INSERT OR REPLACE INTO telemetry_rollup (node_num, metric, bucket_s, bucket_start, n, min, max, avg) "
                    f"SELECT node_num, :metric, 3600, :start, count({m}), min({m}), max({m}), avg({m}) "
                    f"FROM {table} WHERE ts >= :start AND ts < :end AND {m} IS NOT NULL GROUP BY node_num"
                ),
                {"metric": f"{kind}.{m}", "start": hour_start, "end": end},
            )
            n += res.rowcount or 0
    return n


def rollup_day(conn: Connection, day_start: float) -> int:
    """Agregado diario a partir de los horarios (promedio ponderado por cantidad)."""
    res = conn.execute(
        text(
            "INSERT OR REPLACE INTO telemetry_rollup (node_num, metric, bucket_s, bucket_start, n, min, max, avg) "
            "SELECT node_num, metric, 86400, :start, sum(n), min(min), max(max), sum(avg * n) / sum(n) "
            "FROM telemetry_rollup WHERE bucket_s = 3600 AND bucket_start >= :start "
            "AND bucket_start < :end GROUP BY node_num, metric"
        ),
        {"start": day_start, "end": day_start + 86400},
    )
    return res.rowcount or 0


def stats_hour(conn: Connection, hour_start: float) -> dict[str, Any]:
    end = hour_start + 3600
    p = {"s": hour_start, "e": end}
    packets = conn.execute(
        text("SELECT count(*) FROM packets WHERE first_rx >= :s AND first_rx < :e"), p
    ).scalar_one()
    by_port: dict[str, int] = dict(
        conn.execute(
            text(
                "SELECT COALESCE(portnum, 'ENCRYPTED'), count(*) FROM packets "
                "WHERE first_rx >= :s AND first_rx < :e GROUP BY 1"
            ),
            p,
        ).all()
    )
    active = conn.execute(
        text("SELECT count(DISTINCT from_num) FROM packets WHERE first_rx >= :s AND first_rx < :e"),
        p,
    ).scalar_one()
    new = conn.execute(
        text(
            "SELECT count(*) FROM nodes WHERE first_seen >= :s AND first_seen < :e AND hidden = 0"
        ),
        p,
    ).scalar_one()
    util = conn.execute(
        text(
            "SELECT avg(channel_utilization) FROM telemetry_device WHERE ts >= :s AND ts < :e "
            "AND channel_utilization IS NOT NULL"
        ),
        p,
    ).scalar()
    by_hops: dict[str, int] = dict(
        conn.execute(
            text(
                "SELECT CAST(p.hop_start - r.hop_limit AS TEXT), count(*) FROM packets p "
                "JOIN receptions r ON r.packet_pk = p.pk WHERE p.first_rx >= :s AND p.first_rx < :e "
                "AND p.hop_start > 0 AND r.hop_limit IS NOT NULL GROUP BY 1"
            ),
            p,
        ).all()
    )
    by_relay = {str(k): v for k, v in conn.execute(text(RELAY_SQL), p).all()}
    row = {
        "hour_start": hour_start,
        "packets": packets,
        "by_portnum": orjson.dumps(by_port).decode(),
        "active_nodes": active,
        "new_nodes": new,
        "avg_channel_util": round(util, 2) if util is not None else None,
        "by_hops": orjson.dumps(by_hops).decode(),
        "by_relay": orjson.dumps(by_relay).decode(),
    }
    conn.execute(
        text(
            "INSERT OR REPLACE INTO stats_hourly (hour_start, packets, by_portnum, active_nodes, "
            "new_nodes, avg_channel_util, by_hops, by_relay) VALUES (:hour_start, :packets, "
            ":by_portnum, :active_nodes, :new_nodes, :avg_channel_util, :by_hops, :by_relay)"
        ),
        row,
    )
    return row


def run_hourly(conn: Connection, now: float | None = None, backfill_hours: int = 6) -> int:
    """Calcula las últimas horas cerradas que falten (o las recalcula si son recientes)."""
    now = now or time.time()
    last_closed = hour_floor(now) - 3600
    done = 0
    for i in range(backfill_hours):
        h = last_closed - i * 3600
        rollup_hour(conn, h)
        stats_hour(conn, h)
        done += 1
    return done


def backfill(conn: Connection, since: float, until: float | None = None) -> int:
    """Recalcula agregados de un rango (tras importar o reproducir grabaciones)."""
    until = until or time.time()
    h = hour_floor(since)
    n = 0
    while h < hour_floor(until):
        rollup_hour(conn, h)
        stats_hour(conn, h)
        h += 3600
        n += 1
    d = float(int(since // 86400) * 86400)
    while d < until:
        rollup_day(conn, d)
        d += 86400
    return n


def run_daily(conn: Connection, now: float | None = None) -> int:
    now = now or time.time()
    day = float(int(now // 86400) * 86400) - 86400
    return rollup_day(conn, day)
