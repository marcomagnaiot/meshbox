"""Tendencia de carga de la batería (placas con panel solar)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Connection, create_engine, text

from meshbox.store.battery import battery_trend

TZ = "America/Argentina/Buenos_Aires"


@pytest.fixture
def conn() -> Iterator[Connection]:
    eng = create_engine("sqlite://")
    with eng.begin() as c:
        c.execute(
            text(
                "CREATE TABLE telemetry_device (node_num INTEGER, ts REAL, battery_level INTEGER,"
                " voltage REAL)"
            )
        )
        yield c


def _days(c: Connection, start: datetime, dawn: list[float], full: bool) -> float:
    """Una muestra por minuto: de noche baja, de 9 a 18 carga (101), a la noche cierra."""
    t = start
    rows = []
    prev_evening = dawn[0] + 0.05
    for d, v_dawn in enumerate(dawn):
        day = start + timedelta(days=d)
        evening = v_dawn + (0.08 if full else 0.03)
        for minute in range(24 * 60):
            t = day + timedelta(minutes=minute)
            h = minute / 60
            if h < 9:  # baja en línea recta hasta el mínimo, justo antes de que salga el sol
                v, level = prev_evening - (prev_evening - v_dawn) * h / 9, 85
            elif h < 18:
                v, level = (4.31 if full else 4.12), 101
            else:
                v, level = evening, 85
            rows.append({"t": t.timestamp(), "b": level, "v": round(v, 3)})
        prev_evening = evening
    c.execute(text("INSERT INTO telemetry_device VALUES (1, :t, :b, :v)"), rows)
    return t.timestamp()


def test_recovers_when_full_every_day(conn: Connection) -> None:
    start = datetime(2026, 10, 24, tzinfo=ZoneInfo(TZ))
    now = _days(conn, start, [4.02, 4.03, 4.03], full=True)
    r = battery_trend(conn, 1, 2, TZ, now=now)
    assert [d["date"] for d in r["per_day"]] == ["2026-10-25", "2026-10-26"]
    day = r["per_day"][0]
    assert day["full"] and day["charge_h"] == pytest.approx(9.0, abs=0.05)
    assert day["dawn_v"] == pytest.approx(4.03, abs=0.005)
    assert day["night_drain_mv_h"] is not None and day["night_drain_mv_h"] > 0
    assert r["trend"]["verdict"] == "recupera"


def test_deficit_projects_days_to_cutoff(conn: Connection) -> None:
    start = datetime(2026, 10, 20, tzinfo=ZoneInfo(TZ))
    now = _days(conn, start, [4.00, 3.95, 3.90, 3.85, 3.80], full=False)
    r = battery_trend(conn, 1, 7, TZ, now=now)
    t = r["trend"]
    assert t["verdict"] == "deficit" and t["full_days"] == 0
    assert t["dawn_slope_v_day"] == pytest.approx(-0.05, abs=0.002)
    # Del último amanecer (3,80 V) a 3,5 V a 50 mV por día: 6 días.
    assert t["days_to_cutoff"] == pytest.approx(6.0, abs=0.3)


def test_restarts_after_long_outage(conn: Connection) -> None:
    """Otra batería después de un día apagada: los días viejos no cuentan para la tendencia."""
    _days(conn, datetime(2026, 10, 18, tzinfo=ZoneInfo(TZ)), [3.60, 3.55, 3.50], full=False)
    start = datetime(2026, 10, 22, tzinfo=ZoneInfo(TZ))
    now = _days(conn, start, [4.10, 4.05, 4.00], full=False)
    r = battery_trend(conn, 1, 7, TZ, now=now)
    assert [d["in_trend"] for d in r["per_day"]] == [False] * 4 + [True] * 3
    t = r["trend"]
    assert t["since"] == pytest.approx(start.timestamp(), abs=1)
    assert t["verdict"] == "deficit" and t["complete_days"] == 2
    assert t["dawn_slope_v_day"] == pytest.approx(-0.05, abs=0.002)


def test_without_data(conn: Connection) -> None:
    r = battery_trend(conn, 1, 2, TZ, now=datetime(2026, 10, 26, tzinfo=ZoneInfo(TZ)).timestamp())
    assert r["samples"] == 0 and r["trend"]["verdict"] == "sin_datos"
