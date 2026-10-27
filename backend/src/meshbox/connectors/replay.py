"""Reproducción de grabaciones JSONL (sección 9.4).

Formato de cada línea: {"source","connector_id","gateway_id","channel_id","rx_time","packet_b64"}.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import random
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import orjson
from meshtastic.protobuf import mesh_pb2

from ..config import ReplayConnectorCfg
from ..models import RawPacket
from .base import BaseConnector, StatusCallback

log = logging.getLogger(__name__)
LOOP_ID_STEP = 0x9E3779B1  # cambia los id en cada vuelta para que no parezcan duplicados


def read_recording(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("rb") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(b"#"):
                continue
            try:
                yield orjson.loads(line)
            except orjson.JSONDecodeError:
                continue


def record_to_packet(rec: dict[str, Any]) -> mesh_pb2.MeshPacket | None:
    try:
        pkt = mesh_pb2.MeshPacket()
        pkt.ParseFromString(base64.b64decode(rec["packet_b64"]))
        return pkt
    except Exception:
        return None


def packet_to_record(raw: RawPacket) -> dict[str, Any]:
    return {
        "source": raw.source,
        "connector_id": raw.connector_id,
        "gateway_id": raw.gateway_id,
        "channel_id": raw.channel_id,
        "rx_time": round(raw.rx_time, 3),
        "packet_b64": base64.b64encode(raw.packet.SerializeToString()).decode(),
    }


def shift_ids(pkt: mesh_pb2.MeshPacket, shift: int) -> None:
    """Corre el id del paquete y, si viene decodificado, los ids a los que responde.

    Sin esto, en la reproducción las respuestas y reacciones apuntan a ids viejos.
    """

    def moved(value: int) -> int:
        return (value + shift) & 0xFFFFFFFF or 1

    pkt.id = moved(pkt.id)
    if pkt.HasField("decoded"):
        if pkt.decoded.reply_id:
            pkt.decoded.reply_id = moved(pkt.decoded.reply_id)
        if pkt.decoded.request_id:
            pkt.decoded.request_id = moved(pkt.decoded.request_id)


class ReplayConnector(BaseConnector):
    kind = "replay"

    def __init__(self, cfg: ReplayConnectorCfg, on_status: StatusCallback | None = None) -> None:
        super().__init__(cfg.id, on_status)
        self.cfg = cfg
        self._done = False
        self._set_detail(file=str(cfg.file), speed=cfg.speed, loop=cfg.loop)

    @property
    def finished(self) -> bool:
        return self._done

    async def _run_once(self) -> None:
        path = self.cfg.file
        if not path.exists():
            raise FileNotFoundError(f"no existe la grabación {path}")
        self._set_state("connected")
        speed = self.cfg.speed
        loop_n = 0
        offset = 0.0
        # Con horas corridas al presente es una demostración: id distintos en cada corrida
        # para no chocar con paquetes de corridas anteriores guardados en la misma base.
        salt = (
            self.cfg.id_salt
            if self.cfg.id_salt is not None
            else (
                random.randint(1, 0xFFFFFFFE) if self.cfg.rebase_time else 0  # noqa: S311
            )
        )
        if self.cfg.rebase_time and speed <= 0:
            # A máxima velocidad la grabación se corre para que termine "ahora" (relleno).
            last = max((float(r.get("rx_time") or 0) for r in read_recording(path)), default=0.0)
            offset = time.time() - last
        while True:
            first_rx: float | None = None
            last_rx: float | None = None
            wall_start = time.monotonic()
            count = 0
            for rec in read_recording(path):
                pkt = record_to_packet(rec)
                if pkt is None:
                    self._status.invalid += 1
                    continue
                rx = float(rec.get("rx_time") or 0)
                if first_rx is None:
                    first_rx = rx
                last_rx = rx
                if speed > 0:
                    due = (rx - first_rx) / speed
                    delay = due - (time.monotonic() - wall_start)
                    if delay > 0:
                        await asyncio.sleep(delay)
                elif count % 200 == 0:
                    await asyncio.sleep(0)
                if loop_n or salt:
                    shift_ids(pkt, salt + loop_n * LOOP_ID_STEP)
                rx_time = rx + offset if self.cfg.rebase_time else rx
                if speed > 0 and self.cfg.rebase_time:
                    rx_time = time.time()
                raw = RawPacket(
                    source="replay",
                    connector_id=self.id,
                    gateway_id=rec.get("gateway_id"),
                    channel_id=rec.get("channel_id"),
                    rx_time=rx_time,
                    packet=pkt,
                )
                await self._deliver(raw)
                count += 1
            log.info("reproducción %s: %d paquetes (vuelta %d)", path.name, count, loop_n + 1)
            if not self.cfg.loop:
                self._done = True
                return
            loop_n += 1
            if self.cfg.rebase_time and last_rx is not None and first_rx is not None:
                offset += (last_rx - first_rx) + 60


class Recorder:
    """Graba cada RawPacket en `AAAAMMDD-HHMM.jsonl` (9.4)."""

    def __init__(self, out_dir: Path, connector_ids: set[str] | None = None) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        self.path = out_dir / time.strftime("%Y%m%d-%H%M.jsonl")
        self.connector_ids = connector_ids
        self._f = self.path.open("ab")
        self.count = 0

    def __call__(self, raw: RawPacket) -> None:
        if self.connector_ids is not None and raw.connector_id not in self.connector_ids:
            return
        self._f.write(orjson.dumps(packet_to_record(raw)) + b"\n")
        self.count += 1
        if self.count % 20 == 0:
            self._f.flush()

    def close(self) -> None:
        self._f.flush()
        self._f.close()
