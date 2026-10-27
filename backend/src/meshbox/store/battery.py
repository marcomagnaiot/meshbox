"""Tendencia de carga de la batería de un nodo (placas con panel solar).

Por día local se mira lo que dice si la batería se recupera o se agota: el mínimo antes de
empezar a cargar (al amanecer), las horas con el cargador activo (la placa informa batería
101 = alimentación externa), si llegó a la meseta de carga completa, el voltaje al cerrar el
día y la caída nocturna. La tendencia es la pendiente de los mínimos del amanecer (V por día):
si bajan día tras día, el panel o el cargador no reponen lo que se consume. Si la placa estuvo
apagada más de 6 horas (cambio de batería, mudanza, corte), la tendencia vuelve a contar desde
ahí: lo de antes es otra batería u otro lugar y no se compara.

El voltaje mientras carga es el que fija el cargador (no el de reposo) y el porcentaje que
calcula el firmware sale del voltaje: son indicadores, no una medición de energía.
"""

from __future__ import annotations

import itertools
import statistics
import time
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Connection, text

POWERED = 100  # la placa informa 101 cuando tiene alimentación externa (sol o USB)
FULL_V = 4.2  # meseta del cargador: carga completa
FULL_MIN_H = 1.0  # al menos una hora en la meseta para darla por llena
DAWN_UNTIL_H = 12  # el mínimo del amanecer se busca antes del mediodía (o antes de cargar)
EVENING_FROM_H = 21  # cierre del día: de 21 a 24, ya sin sol
CUTOFF_V = 3.5  # cerca de acá el ESP32 se reinicia por bajo voltaje (visto en un Heltec: 3,4 V)
STABLE_V_DAY = 0.01  # ±10 mV por día en el mínimo del amanecer: estable
MAX_GAP_S = 600  # entre dos muestras más separadas no se suman horas de carga
RESTART_GAP_S = 6 * 3600  # apagada más que esto: la tendencia vuelve a contar desde ahí


def _smooth(values: list[float], k: int = 2) -> list[float]:
    """Mediana móvil (2k+1 muestras): saca los picos de un instante al transmitir."""
    out = []
    for i in range(len(values)):
        out.append(statistics.median(values[max(0, i - k) : i + k + 1]))
    return out


def _slope(points: list[tuple[float, float]]) -> float | None:
    if len(points) < 2:
        return None
    mx = sum(x for x, _ in points) / len(points)
    my = sum(y for _, y in points) / len(points)
    den = sum((x - mx) ** 2 for x, _ in points)
    if den == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in points) / den


def battery_trend(
    conn: Connection, num: int, days: int, tz_name: str, now: float | None = None
) -> dict[str, Any]:
    now = now or time.time()
    tz = ZoneInfo(tz_name)
    today = datetime.fromtimestamp(now, tz).replace(hour=0, minute=0, second=0, microsecond=0)
    first_day = today - timedelta(days=days - 1)
    # Un día más atrás para la caída nocturna de la primera noche.
    t_from = (first_day - timedelta(days=1)).timestamp()
    rows = conn.execute(
        text(
            "SELECT ts, battery_level, voltage FROM telemetry_device "
            "WHERE node_num = :n AND ts >= :f AND ts <= :t AND voltage IS NOT NULL ORDER BY ts"
        ),
        {"n": num, "f": t_from, "t": now},
    ).all()
    ts = [float(r[0]) for r in rows]
    level = [r[1] for r in rows]
    volts = _smooth([float(r[2]) for r in rows])

    base = first_day.date()
    day_of = [(datetime.fromtimestamp(t, tz).date() - base).days for t in ts]
    since = next(
        (b for a, b in reversed(list(itertools.pairwise(ts))) if b - a > RESTART_GAP_S), None
    )
    since_day = datetime.fromtimestamp(since, tz).date().isoformat() if since else None

    per_day: list[dict[str, Any]] = []
    prev: dict[str, Any] | None = None
    for d in range(-1, days):
        idx = [i for i, x in enumerate(day_of) if x == d]
        start = first_day + timedelta(days=d)
        item: dict[str, Any] = {
            "date": start.date().isoformat(),
            "samples": len(idx),
            "complete": (start + timedelta(days=1)).timestamp() <= now,
        }
        charging = [i for i in idx if (level[i] or 0) > POWERED]
        charge_s = 0.0
        full_s = 0.0
        for a, b in itertools.pairwise(idx):
            dt = ts[b] - ts[a]
            if dt > MAX_GAP_S or (level[a] or 0) <= POWERED or (level[b] or 0) <= POWERED:
                continue
            charge_s += dt
            if volts[a] >= FULL_V and volts[b] >= FULL_V:
                full_s += dt
        item["charge_h"] = round(charge_s / 3600, 2)
        item["full"] = full_s / 3600 >= FULL_MIN_H
        item["charge_start"] = ts[charging[0]] if charging else None
        item["charge_end"] = ts[charging[-1]] if charging else None
        # Mínimo del amanecer: antes de empezar a cargar y antes del mediodía.
        limit = (start + timedelta(hours=DAWN_UNTIL_H)).timestamp()
        if charging:
            limit = min(limit, ts[charging[0]])
        dawn = [i for i in idx if ts[i] <= limit]
        if dawn:
            i = min(dawn, key=lambda j: volts[j])
            item.update(dawn_v=round(volts[i], 3), dawn_at=ts[i], dawn_pct=level[i])
        else:
            item.update(dawn_v=None, dawn_at=None, dawn_pct=None)
        item["max_v"] = round(max(volts[i] for i in idx), 3) if idx else None
        evening_from = (start + timedelta(hours=EVENING_FROM_H)).timestamp()
        evening = [volts[i] for i in idx if ts[i] >= evening_from and (level[i] or 0) <= POWERED]
        item["evening_v"] = round(statistics.median(evening), 3) if evening else None
        # Caída nocturna: desde una hora después del último sol de ayer hasta el mínimo de hoy.
        item["night_drain_mv_h"] = None
        if prev is not None and item["dawn_at"] is not None:
            after = (prev["charge_end"] or prev["_start"] + EVENING_FROM_H * 3600) + 3600
            night = [i for i, t in enumerate(ts) if after <= t <= item["dawn_at"]]
            if night and item["dawn_at"] - ts[night[0]] >= 3 * 3600:
                drop = volts[night[0]] - item["dawn_v"]
                hours = (item["dawn_at"] - ts[night[0]]) / 3600
                item["night_drain_mv_h"] = round(drop / hours * 1000, 1)
        item["in_trend"] = since_day is None or item["date"] >= since_day
        item["_start"] = start.timestamp()
        if d >= 0:
            per_day.append(item)
        prev = item
    for item in per_day:
        item.pop("_start", None)

    used = [(i, it) for i, it in enumerate(per_day) if it["in_trend"]]
    dawns: list[tuple[float, float]] = [
        (float(i), float(it["dawn_v"])) for i, it in used if it["dawn_v"] is not None
    ]
    slope = _slope(dawns)
    evenings = [it["evening_v"] for _, it in used if it["evening_v"] is not None]
    evening_delta = round(evenings[-1] - evenings[-2], 3) if len(evenings) >= 2 else None
    complete = [it for _, it in used if it["complete"] and it["samples"]]
    full_days = sum(1 for it in complete if it["full"])
    rate = slope if slope is not None else evening_delta
    days_to_cutoff = None
    if rate is None:
        verdict = "sin_datos"
    elif (complete and full_days == len(complete) and rate > -STABLE_V_DAY) or rate >= STABLE_V_DAY:
        verdict = "recupera"
    elif rate > -STABLE_V_DAY:
        verdict = "estable"
    else:
        verdict = "deficit"
        last = dawns[-1][1] if dawns else evenings[-1]
        days_to_cutoff = round(max(0.0, (last - CUTOFF_V) / -rate), 1)
    return {
        "days": days,
        "timezone": tz_name,
        "samples": len(ts),
        "from": ts[0] if ts else None,
        "to": ts[-1] if ts else None,
        "per_day": per_day,
        "trend": {
            "dawn_slope_v_day": round(slope, 4) if slope is not None else None,
            "evening_delta_v": evening_delta,
            "full_days": full_days,
            "complete_days": len(complete),
            "verdict": verdict,
            "days_to_cutoff": days_to_cutoff,
            "cutoff_v": CUTOFF_V,
            "since": since,
        },
    }
