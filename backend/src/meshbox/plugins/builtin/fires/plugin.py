"""Focos de incendio desde NASA FIRMS (sección 21.2).

API de área: `/api/area/csv/{MAP_KEY}/{fuente}/{oeste,sur,este,norte}/{días}`.
"""

from __future__ import annotations

import asyncio
import contextlib
import csv
import io
import math
import time
from typing import Any

from ...api import PluginBase, PluginContext

FIRMS = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371 * math.asin(min(1.0, math.sqrt(a)))


def parse_csv(text: str, source: str) -> list[dict[str, Any]]:
    features = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
        except (KeyError, ValueError):
            continue
        frp = float(row.get("frp") or 0)
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "frp": frp,
                    "confidence": row.get("confidence"),
                    "acq_date": row.get("acq_date"),
                    "acq_time": row.get("acq_time"),
                    "satellite": row.get("satellite"),
                    "source": source,
                    "daynight": row.get("daynight"),
                    "weight": min(1.0, max(0.1, frp / 50)),  # tamaño según FRP
                },
            }
        )
    return features


class Plugin(PluginBase):
    async def setup(self, ctx: PluginContext) -> None:
        await super().setup(ctx)
        self.features: list[dict[str, Any]] = []
        self.updated_at: float | None = None
        self.alerted: set[str] = set()
        self._task = asyncio.create_task(self._loop())

    async def teardown(self) -> None:
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task

    def bbox(self) -> list[float]:
        b = self.ctx.settings.get("bbox") or []
        if len(b) == 4:
            return [float(x) for x in b]
        site = self.ctx.site
        if site.bounds:
            return list(site.bounds)
        lat, lon = site.center
        return [lon - 1.0, lat - 1.0, lon + 1.0, lat + 1.0]

    async def fetch(self) -> list[dict[str, Any]]:
        key = self.ctx.secrets.get("map_key", "")
        if not key:
            self.ctx.log.warning("falta MAP_KEY de FIRMS")
            return []
        area = ",".join(f"{x:.4f}" for x in self.bbox())
        days = int(self.ctx.settings.get("days", 1))
        out: list[dict[str, Any]] = []
        for source in self.ctx.settings.get("sources") or ["VIIRS_NOAA20_NRT"]:
            r = await self.ctx.http.get(f"{FIRMS}/{key}/{source}/{area}/{days}")
            if r.status_code != 200 or r.text.lstrip().lower().startswith("invalid"):
                self.ctx.log.warning(
                    "FIRMS %s respondió %s: %s", source, r.status_code, r.text[:120]
                )
                continue
            out.extend(parse_csv(r.text, source))
        return out

    async def _loop(self) -> None:
        while True:
            try:
                self.features = await self.fetch()
                self.updated_at = time.time()
                self.ctx.log.info("FIRMS: %d focos", len(self.features))
                await self._check_alerts()
            except Exception as e:
                self.ctx.log.warning("consulta a FIRMS falló: %s", e)
            await asyncio.sleep(int(self.ctx.settings.get("refresh_min", 30)) * 60)

    async def _check_alerts(self) -> None:
        limit = float(self.ctx.settings.get("alert_km") or 0)
        if limit <= 0:
            return
        for node in self.ctx.fixed_nodes():
            for f in self.features:
                lon, lat = f["geometry"]["coordinates"]
                d = haversine_km(node["lat"], node["lon"], lat, lon)
                key = f"{lat:.3f},{lon:.3f},{f['properties'].get('acq_date')}"
                if d <= limit and key not in self.alerted:
                    self.alerted.add(key)
                    name = node.get("long_name") or node.get("short_name") or node["id"]
                    await self.ctx.raise_alert(
                        f"Foco de calor a {d:.1f} km de {name}",
                        f"Detectado {f['properties'].get('acq_date')} {f['properties'].get('acq_time')} "
                        f"({f['properties'].get('source')}), FRP {f['properties'].get('frp')}",
                        severity="warning",
                        node=node["id"],
                        is_public=bool(self.ctx.settings.get("alert_public")),
                        key=key,
                    )

    async def layer(self, layer_id: str) -> dict[str, Any]:
        return {
            "type": "FeatureCollection",
            "features": self.features,
            "updated_at": self.updated_at,
        }
