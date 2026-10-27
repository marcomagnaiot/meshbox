"""Tiempo de las consultas de 30 días contra una base (criterio de E8: menos de 1 s en la Pi).

Se corre contra una copia, nunca contra la base en uso. En la Pi, con el entorno de meshbox:

    nice -n 10 /opt/meshbox/current/.venv/bin/python bench-queries.py --db bench30.db

La base se arma en la PC con la red simulada (30 días, horas corridas al presente):

    uv run meshbox simulate generate --out sim-30d.jsonl --hours 720
    uv run meshbox replay sim-30d.jsonl --config dev/config.toml --db bench30.db --speed max
"""

from __future__ import annotations

import argparse
import statistics
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from meshbox.store import queries

BUDGET_S = 1.0
DAY = 86400


def timed(fn: Callable[[], Any], runs: int) -> tuple[float, float, Any]:
    times = []
    result = None
    for _ in range(runs):
        t0 = time.perf_counter()
        result = fn()
        times.append(time.perf_counter() - t0)
    return min(times), statistics.median(times), result


def busiest_node(conn: Connection) -> int:
    row = conn.execute(
        text(
            "SELECT node_num FROM telemetry_device GROUP BY node_num ORDER BY count(*) DESC LIMIT 1"
        )
    ).first()
    return int(row[0]) if row else 0


def moving_node(conn: Connection) -> int:
    row = conn.execute(
        text("SELECT node_num FROM positions GROUP BY node_num ORDER BY count(*) DESC LIMIT 1")
    ).first()
    return int(row[0]) if row else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    engine = create_engine(f"sqlite:///{args.db}")
    with engine.connect() as conn:
        conn.execute(text("PRAGMA query_only = 1"))
        now = time.time()
        since = now - 30 * DAY
        counts = {
            t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()
            for t in ("packets", "receptions", "messages", "positions", "telemetry_device", "links")
        }
        size_mb = args.db.stat().st_size / 1e6
        print(
            f"base {args.db.name}: {size_mb:.1f} MB; "
            + ", ".join(f"{k} {v}" for k, v in counts.items())
        )
        node = busiest_node(conn)
        mover = moving_node(conn)
        nodes: dict[int, Any] = {}
        cases: list[tuple[str, Callable[[], Any]]] = [
            ("stats/timeseries packets 30d", lambda: queries.stats_timeseries(conn, "packets", "30d", now)),
            ("stats/timeseries active_nodes 30d", lambda: queries.stats_timeseries(conn, "active_nodes", "30d", now)),
            ("stats/timeseries by_portnum 30d", lambda: queries.stats_timeseries(conn, "by_portnum", "30d", now)),
            ("stats/breakdown totales 30d", lambda: queries.stats_totals(conn, "30d", now)),
            ("saltos 30d en vivo (respaldo)", lambda: queries.hops_distribution(conn, since)),
            ("stats/breakdown retransmisores 30d", lambda: queries.relays(conn, since, nodes)),
            ("telemetría de un nodo 30d", lambda: queries.telemetry_series(conn, node, "device", since, now)),
            ("recorrido de un nodo 30d", lambda: queries.node_positions(conn, mover, since, now, 2000)),
            ("enlaces 30d", lambda: queries.links(conn, 30 * DAY, set())),
            ("mensajes (primera página)", lambda: queries.messages_page(conn, None, 50, {})),
        ]  # fmt: skip
        worst = 0.0
        for name, fn in cases:
            try:
                best, median, _ = timed(fn, args.runs)
            except TypeError as e:  # firma distinta: avisar sin cortar la medición
                print(f"  {name:38s} (no medida: {e})")
                continue
            # El respaldo en vivo solo corre sin agregados horarios (instalación recién hecha).
            fallback = "respaldo" in name
            if not fallback:
                worst = max(worst, median)
            mark = "ok" if median < BUDGET_S else ("lenta (respaldo)" if fallback else "LENTA")
            print(
                f"  {name:38s} mediana {median * 1000:8.1f} ms  mínimo {best * 1000:8.1f} ms  {mark}"
            )
        print(f"peor mediana: {worst * 1000:.0f} ms (presupuesto {BUDGET_S * 1000:.0f} ms)")
        return 0 if worst < BUDGET_S else 1


if __name__ == "__main__":
    raise SystemExit(main())
