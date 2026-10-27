"""Lecturas para la API (secciones 12.2 y 17). Funciones síncronas sobre una conexión;
se ejecutan con `Database.read(...)` en el pool de lectura."""

from __future__ import annotations

import math
import time
from collections import Counter, defaultdict
from typing import Any

import orjson
from sqlalchemy import Connection, text

from ..models import BROADCAST, node_id
from ..pipeline.decode import ENV_FIELDS, POWER_FIELDS, precision_meters
from ..pipeline.privacy import haversine_m

DEVICE_METRICS = ("battery_level", "voltage", "channel_utilization", "air_util_tx", "uptime_s")
ENV_METRICS = tuple(col for col, _ in ENV_FIELDS)
KIND_METRICS = {"device": DEVICE_METRICS, "environment": ENV_METRICS, "power": POWER_FIELDS}
KIND_TABLE = {
    "device": "telemetry_device",
    "environment": "telemetry_environment",
    "power": "telemetry_power",
}
RAW_MAX_S = 48 * 3600
BUCKET_POINTS = 2100  # puntos por serie al agrupar crudos (más de 48 h): 7 días en 5 min
BUCKET_MIN_S = 300
HOURLY_MAX_S = 90 * 86400


# --------------------------------------------------------------------------- mensajes y alertas


def messages_page(
    conn: Connection, before: tuple[float, int] | None, limit: int, names: dict[int, str | None]
) -> tuple[list[dict[str, Any]], str | None]:
    params: dict[str, Any] = {"limit": limit + 1}
    where = "hidden = 0"
    if before is not None:
        where += " AND (ts < :bts OR (ts = :bts AND pk < :bpk))"
        params.update(bts=before[0], bpk=before[1])
    rows = conn.execute(
        text(
            f"SELECT pk, ts, from_num, channel_name, text, reply_id, emoji, packet_pk "
            f"FROM messages WHERE {where} ORDER BY ts DESC, pk DESC LIMIT :limit"
        ),
        params,
    ).all()
    out = []
    for pk, ts, from_num, channel, txt, reply_id, emoji, _ppk in rows[:limit]:
        out.append(
            {
                "pk": pk,
                "ts": ts,
                "from": node_id(from_num),
                "from_name": names.get(from_num),
                "channel": channel,
                "text": txt,
                "reply_id": reply_id,
                "emoji": bool(emoji),
            }
        )
    nxt = f"{rows[limit - 1][1]:.3f}:{rows[limit - 1][0]}" if len(rows) > limit else None
    return out, nxt


def message_packet_ids(conn: Connection, pks: list[int]) -> dict[int, int]:
    """pk de mensaje → id del paquete (para enlazar respuestas `reply_id`)."""
    if not pks:
        return {}
    rows = conn.execute(
        text(
            "SELECT m.pk, p.packet_id FROM messages m JOIN packets p ON p.pk = m.packet_pk "
            f"WHERE m.pk IN ({','.join(str(int(p)) for p in pks)})"
        )
    ).all()
    return dict(rows)


def alerts_page(
    conn: Connection, before: tuple[float, int] | None, limit: int, public_only: bool = True
) -> tuple[list[dict[str, Any]], str | None]:
    params: dict[str, Any] = {"limit": limit + 1}
    where = "1=1"
    if public_only:
        where += " AND e.is_public = 1"
    if before is not None:
        where += " AND (e.ts < :bts OR (e.ts = :bts AND e.id < :bid))"
        params.update(bts=before[0], bid=before[1])
    rows = conn.execute(
        text(
            "SELECT e.id, e.ts, e.state, e.severity, e.node_num, e.title, e.body, r.kind, "
            "e.rule_id, e.is_public, e.ack_by, e.ack_at "
            "FROM alert_events e LEFT JOIN alert_rules r ON r.id = e.rule_id "
            f"WHERE {where} ORDER BY e.ts DESC, e.id DESC LIMIT :limit"
        ),
        params,
    ).all()
    out = []
    for row in rows[:limit]:
        (aid, ts, state, severity, node_num, title, body, kind, rule_id, is_pub, ack_by, ack_at) = (
            row
        )
        item: dict[str, Any] = {
            "id": aid,
            "state": state,
            "severity": severity,
            "kind": kind or "system",
            "node": node_id(node_num) if node_num is not None else None,
            "title": title,
            "body": body,
            "ts": ts,
        }
        if not public_only:
            item.update(rule_id=rule_id, is_public=bool(is_pub), ack_by=ack_by, ack_at=ack_at)
        out.append(item)
    nxt = f"{rows[limit - 1][1]:.3f}:{rows[limit - 1][0]}" if len(rows) > limit else None
    return out, nxt


# --------------------------------------------------------------------------- posiciones


def node_positions(
    conn: Connection, num: int, t_from: float, t_to: float, max_points: int
) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT ts, lat, lon, alt, precision_bits FROM positions "
            "WHERE node_num = :n AND ts >= :f AND ts <= :t ORDER BY ts"
        ),
        {"n": num, "f": t_from, "t": t_to},
    ).all()
    if len(rows) > max_points > 0:
        span = (rows[-1][0] - rows[0][0]) or 1.0
        bucket = span / max_points
        reduced: dict[int, Any] = {}
        for r in rows:
            reduced[int((r[0] - rows[0][0]) // bucket)] = r  # el último de cada tramo
        rows = [reduced[k] for k in sorted(reduced)]
    out: list[dict[str, Any]] = []
    prev = None
    for ts, lat, lon, alt, bits in rows:
        speed = None
        if prev is not None:
            dt = ts - prev[0]
            dist = haversine_m(prev[1], prev[2], lat, lon)
            if dt > 0 and dist >= 5:  # ignorar saltos menores a 5 m (17.2)
                kmh = dist / dt * 3.6
                speed = round(kmh, 1) if kmh >= 2 else None  # ignorar menos de 2 km/h
        out.append(
            {
                "ts": ts,
                "lat": lat,
                "lon": lon,
                "alt": alt,
                "precision_m": precision_meters(bits),
                "speed_kmh": speed,
            }
        )
        prev = (ts, lat, lon)
    return out


# --------------------------------------------------------------------------- telemetría


def telemetry_series(
    conn: Connection,
    num: int,
    kind: str,
    t_from: float,
    t_to: float,
    raw_keep_s: float = 30 * 86400,
) -> dict[str, Any]:
    """Crudos hasta 48 h; mientras queden crudos (`raw_keep_s`, la retención), grupos de
    minutos con promedio, mínimo y máximo (hasta 2100 puntos: 7 días se ven con detalle de 5
    min); más atrás, agregados horarios hasta 90 d y diarios (12.2)."""
    metrics = KIND_METRICS[kind]
    span = t_to - t_from
    if span > RAW_MAX_S + 120 and t_from >= time.time() - raw_keep_s - 3600:
        return _telemetry_buckets(conn, num, kind, t_from, t_to)
    if span <= RAW_MAX_S + 120:  # margen: el navegador redondea el rango a segundos
        cols = ", ".join(metrics)
        rows = conn.execute(
            text(
                f"SELECT ts, {cols} FROM {KIND_TABLE[kind]} "
                "WHERE node_num = :n AND ts >= :f AND ts <= :t ORDER BY ts"
            ),
            {"n": num, "f": t_from, "t": t_to},
        ).all()
        ts = [r[0] for r in rows]
        series = {m: [r[i + 1] for r in rows] for i, m in enumerate(metrics)}
        series = {m: v for m, v in series.items() if any(x is not None for x in v)}
        return {"kind": kind, "resolution": "raw", "ts": ts, "series": series}
    bucket_s = 3600 if span <= HOURLY_MAX_S else 86400
    rows = conn.execute(
        text(
            "SELECT bucket_start, metric, avg, min, max FROM telemetry_rollup "
            "WHERE node_num = :n AND bucket_s = :b AND bucket_start >= :f AND bucket_start <= :t "
            "AND metric LIKE :prefix ORDER BY bucket_start"
        ),
        {"n": num, "b": bucket_s, "f": t_from, "t": t_to, "prefix": f"{kind}.%"},
    ).all()
    starts = sorted({r[0] for r in rows})
    index = {s: i for i, s in enumerate(starts)}
    avg: dict[str, list[float | None]] = defaultdict(lambda: [None] * len(starts))
    mn: dict[str, list[float | None]] = defaultdict(lambda: [None] * len(starts))
    mx: dict[str, list[float | None]] = defaultdict(lambda: [None] * len(starts))
    for start, metric, a, lo, hi in rows:
        name = metric.split(".", 1)[1]
        i = index[start]
        avg[name][i], mn[name][i], mx[name][i] = a, lo, hi
    return {
        "kind": kind,
        "resolution": "hour" if bucket_s == 3600 else "day",
        "ts": starts,
        "series": dict(avg),
        "min": dict(mn),
        "max": dict(mx),
    }


def _telemetry_buckets(
    conn: Connection, num: int, kind: str, t_from: float, t_to: float
) -> dict[str, Any]:
    """Crudos agrupados en intervalos de minutos enteros (5 min como mínimo)."""
    metrics = KIND_METRICS[kind]
    bucket_s = max(BUCKET_MIN_S, math.ceil((t_to - t_from) / BUCKET_POINTS / 60) * 60)
    cols = ", ".join(f"AVG({m}), MIN({m}), MAX({m})" for m in metrics)
    rows = conn.execute(
        text(
            f"SELECT CAST((ts - :f) / :b AS INTEGER) AS k, {cols} FROM {KIND_TABLE[kind]} "
            "WHERE node_num = :n AND ts >= :f AND ts <= :t GROUP BY k ORDER BY k"
        ),
        {"n": num, "f": t_from, "t": t_to, "b": bucket_s},
    ).all()
    ts = [t_from + r[0] * bucket_s for r in rows]
    avg = {m: [r[1 + 3 * i] for r in rows] for i, m in enumerate(metrics)}
    keep = [m for m, v in avg.items() if any(x is not None for x in v)]
    return {
        "kind": kind,
        "resolution": "bucket",
        "bucket_s": bucket_s,
        "ts": ts,
        "series": {m: avg[m] for m in keep},
        "min": {m: [r[2 + 3 * metrics.index(m)] for r in rows] for m in keep},
        "max": {m: [r[3 + 3 * metrics.index(m)] for r in rows] for m in keep},
    }


# --------------------------------------------------------------------------- enlaces y rutas


def links(
    conn: Connection, max_age_s: float, hidden: set[int], node: int | None = None
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"since": time.time() - max_age_s}
    where = "ts >= :since"
    if node is not None:
        where += " AND (node_num = :n OR neighbor_num = :n)"
        params["n"] = node
    rows = conn.execute(
        text(
            f"SELECT node_num, neighbor_num, source, snr, ts FROM links WHERE {where} ORDER BY ts DESC"
        ),
        params,
    ).all()
    return [
        {"a": node_id(a), "b": node_id(b), "snr": snr, "source": src, "ts": ts}
        for a, b, src, snr, ts in rows
        if a not in hidden and b not in hidden
    ]


def traceroutes(
    conn: Connection, node: int | None, limit: int, hidden: set[int]
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"limit": limit}
    where = "1=1"
    if node is not None:
        where = "(from_num = :n OR to_num = :n)"
        params["n"] = node
    rows = conn.execute(
        text(
            "SELECT ts, from_num, to_num, route, snr_towards, route_back, snr_back FROM traceroutes "
            f"WHERE {where} ORDER BY ts DESC LIMIT :limit"
        ),
        params,
    ).all()
    out = []
    for ts, f, t, route, st, rb, sb in rows:
        if f in hidden or t in hidden:
            continue
        out.append(
            {
                "ts": ts,
                "from": node_id(f),
                "to": node_id(t),
                "route": orjson.loads(route or "[]"),
                "snr_towards": orjson.loads(st or "[]"),
                "route_back": orjson.loads(rb or "[]"),
                "snr_back": orjson.loads(sb or "[]"),
            }
        )
    return out


def waypoints(conn: Connection, now: float) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            "SELECT id, from_num, ts, name, description, lat, lon, icon, expire FROM waypoints "
            "WHERE expire IS NULL OR expire > :now ORDER BY ts DESC LIMIT 500"
        ),
        {"now": now},
    ).all()
    return [
        {
            "id": r[0],
            "from": node_id(r[1]) if r[1] is not None else None,
            "ts": r[2],
            "name": r[3],
            "description": r[4],
            "lat": r[5],
            "lon": r[6],
            "icon": r[7],
            "expire": r[8],
        }
        for r in rows
    ]


# --------------------------------------------------------------------------- estadísticas

RANGES = {"24h": 86400, "7d": 7 * 86400, "30d": 30 * 86400}
STAT_METRICS = ("packets", "active_nodes", "new_nodes", "avg_channel_util", "by_portnum", "by_hops")


def stats_timeseries(conn: Connection, metric: str, rng: str, now: float) -> dict[str, Any]:
    since = now - RANGES[rng]
    rows = conn.execute(
        text(
            f"SELECT hour_start, {metric} FROM stats_hourly WHERE hour_start >= :s ORDER BY hour_start"
        ),
        {"s": since},
    ).all()
    values: list[Any] = []
    for _, v in rows:
        if metric in ("by_portnum", "by_hops"):
            values.append(orjson.loads(v) if v else {})
        else:
            values.append(v)
    return {"metric": metric, "range": rng, "ts": [r[0] for r in rows], "values": values}


def stats_totals(conn: Connection, rng: str, now: float) -> dict[str, Any]:
    """Totales del rango para la página de estadísticas: paquetes por tipo y saltos."""
    since = now - RANGES[rng]
    by_port: Counter[str] = Counter()
    by_hops: Counter[str] = Counter()
    rows = conn.execute(
        text("SELECT by_portnum, by_hops FROM stats_hourly WHERE hour_start >= :s"), {"s": since}
    ).all()
    for bp, bh in rows:
        by_port.update(orjson.loads(bp or "{}"))
        by_hops.update(orjson.loads(bh or "{}"))
    return {"by_portnum": dict(by_port), "by_hops": dict(by_hops)}


# Retransmisiones por último byte del nodo en un tramo de `packets.first_rx` (usa su índice).
RELAY_SQL = (
    "SELECT r.relay_node & 255, count(*) FROM packets p JOIN receptions r ON r.packet_pk = p.pk "
    "WHERE p.first_rx >= :s AND p.first_rx < :e AND r.relay_node IS NOT NULL "
    "AND r.relay_node != 0 GROUP BY 1"
)


def relay_counts(conn: Connection, since: float, now: float) -> Counter[int]:
    """Horas cerradas desde `stats_hourly.by_relay`; los bordes sin agregado, en vivo.

    En 30 días evita recorrer todas las recepciones (0,6 s en la Pi con la red simulada).
    """
    first_full = since if since % 3600 == 0 else (since // 3600 + 1) * 3600
    counts: Counter[int] = Counter()
    rows = conn.execute(
        text(
            "SELECT hour_start, by_relay FROM stats_hourly WHERE hour_start >= :s "
            "AND hour_start + 3600 <= :n AND by_relay IS NOT NULL ORDER BY hour_start"
        ),
        {"s": first_full, "n": now},
    ).all()
    live = [(since, now)]
    if rows:
        for _, data in rows:
            counts.update({int(k): v for k, v in orjson.loads(data).items()})
        live = [(since, first_full), (rows[-1][0] + 3600, now)]
    for start, end in live:
        if end > start:
            counts.update(dict(conn.execute(text(RELAY_SQL), {"s": start, "e": end}).all()))
    return counts


def relays(conn: Connection, since: float, nodes: dict[int, Any]) -> list[dict[str, Any]]:
    """Nodos que más retransmiten: el firmware 2.6+ informa solo el último byte (`relay_node`)."""
    out = []
    for relay, count in relay_counts(conn, since, time.time()).most_common(20):
        byte = int(relay) & 0xFF
        candidates = [
            {"id": rec.id, "name": rec.long_name or rec.short_name, "is_infra": rec.is_infra}
            for num, rec in nodes.items()
            if (num & 0xFF) == byte and not rec.hidden
        ]
        candidates.sort(key=lambda c: (not c["is_infra"], c["name"] or ""))
        out.append({"relay": f"0x{byte:02x}", "count": count, "candidates": candidates[:5]})
    return out


def hops_distribution(conn: Connection, since: float) -> dict[str, int]:
    rows = conn.execute(
        text(
            "SELECT p.hop_start - r.hop_limit AS hops, count(*) FROM packets p "
            "JOIN receptions r ON r.packet_pk = p.pk WHERE p.first_rx >= :s AND p.hop_start > 0 "
            "GROUP BY hops"
        ),
        {"s": since},
    ).all()
    return {str(h): c for h, c in rows if h is not None and 0 <= h <= 7}


def nan_to_none(v: float | None) -> float | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return v


BROADCAST_ID = "^all"


def dest_id(num: int) -> str:
    return BROADCAST_ID if num == BROADCAST else node_id(num)
