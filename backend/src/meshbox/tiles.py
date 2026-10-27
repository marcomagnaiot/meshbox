"""Teselas vectoriales desde el extracto PMTiles local (secciones 12.2 y 16.5).

El lector de la librería `pmtiles` vuelve a leer y descomprimir el directorio raíz en cada
tesela; acá se guardan el encabezado y el directorio raíz, y los directorios hoja más usados
en una caché chica (la Pi tiene poca CPU).
"""

from __future__ import annotations

import gzip
import json
import logging
import mmap
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

from pmtiles.tile import (
    Compression,
    Entry,
    deserialize_directory,
    deserialize_header,
    find_tile,
    zxy_to_tileid,
)

log = logging.getLogger(__name__)
REGION_FILE = "region.pmtiles"
OSM_ATTRIBUTION = (
    '<a href="https://protomaps.com">Protomaps</a> © '
    '<a href="https://openstreetmap.org/copyright">OpenStreetMap</a>'
)


class TileStore:
    def __init__(self, tiles_dir: Path, leaf_cache: int = 64) -> None:
        self.dir = tiles_dir
        self.path = tiles_dir / REGION_FILE
        self._lock = threading.Lock()
        self._file: Any = None
        self._mm: mmap.mmap | None = None
        self.header: dict[str, Any] | None = None
        self.metadata: dict[str, Any] = {}
        self._root: list[Entry] = []
        self._leaves: OrderedDict[tuple[int, int], list[Entry]] = OrderedDict()
        self._leaf_cache = leaf_cache
        self.served = 0
        self.open()

    @property
    def available(self) -> bool:
        return self._mm is not None and self.header is not None

    def open(self) -> None:
        self.close()
        if not self.path.exists() or self.path.stat().st_size < 127:
            return
        try:
            f = self.path.open("rb")
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            header: dict[str, Any] = dict(deserialize_header(mm[0:127]))
            root = deserialize_directory(
                mm[header["root_offset"] : header["root_offset"] + header["root_length"]]
            )
            raw_meta = mm[
                header["metadata_offset"] : header["metadata_offset"] + header["metadata_length"]
            ]
            if header["internal_compression"] == Compression.GZIP:
                raw_meta = gzip.decompress(raw_meta)
            self.metadata = json.loads(raw_meta) if raw_meta else {}
        except Exception:
            log.exception("el extracto %s no es válido", self.path)
            return
        self._file, self._mm, self.header, self._root = f, mm, header, root
        log.info("extracto de mapa abierto: z%d-%d", header["min_zoom"], header["max_zoom"])

    def close(self) -> None:
        with self._lock:
            if self._mm is not None:
                self._mm.close()
            if self._file is not None:
                self._file.close()
            self._mm = self._file = self.header = None
            self._root = []
            self._leaves.clear()

    def _leaf(self, offset: int, length: int) -> list[Entry]:
        key = (offset, length)
        hit = self._leaves.get(key)
        if hit is not None:
            self._leaves.move_to_end(key)
            return hit
        assert self._mm is not None and self.header is not None
        base = self.header["leaf_directory_offset"] + offset
        entries = deserialize_directory(self._mm[base : base + length])
        self._leaves[key] = entries
        while len(self._leaves) > self._leaf_cache:
            self._leaves.popitem(last=False)
        return entries

    def get(self, z: int, x: int, y: int) -> bytes | None:
        with self._lock:
            if self._mm is None or self.header is None:
                return None
            h = self.header
            if not (h["min_zoom"] <= z <= h["max_zoom"]) or not (0 <= x < 2**z and 0 <= y < 2**z):
                return None
            tile_id = zxy_to_tileid(z, x, y)
            directory = self._root
            for _ in range(4):
                entry = find_tile(directory, tile_id)
                if entry is None:
                    return None
                if entry.run_length == 0:
                    directory = self._leaf(entry.offset, entry.length)
                    continue
                start = h["tile_data_offset"] + entry.offset
                self.served += 1
                return bytes(self._mm[start : start + entry.length])
        return None

    @property
    def gzipped(self) -> bool:
        return bool(self.header and self.header["tile_compression"] == Compression.GZIP)

    def tilejson(self, base_url: str) -> dict[str, Any]:
        h = self.header or {}
        bounds = [
            h.get("min_lon_e7", 0) / 1e7,
            h.get("min_lat_e7", 0) / 1e7,
            h.get("max_lon_e7", 0) / 1e7,
            h.get("max_lat_e7", 0) / 1e7,
        ]
        return {
            "tilejson": "3.0.0",
            "name": self.metadata.get("name", "meshbox"),
            "tiles": [f"{base_url}/tiles/v/{{z}}/{{x}}/{{y}}.mvt"],
            "minzoom": h.get("min_zoom", 0),
            "maxzoom": h.get("max_zoom", 14),
            "bounds": bounds,
            "center": [
                h.get("center_lon_e7", 0) / 1e7,
                h.get("center_lat_e7", 0) / 1e7,
                h.get("center_zoom", 0),
            ],
            "vector_layers": self.metadata.get("vector_layers", []),
            "attribution": self.metadata.get("attribution") or OSM_ATTRIBUTION,
        }

    def status(self) -> dict[str, Any]:
        h = self.header or {}
        return {
            "available": self.available,
            "path": str(self.path),
            "size": self.path.stat().st_size if self.path.exists() else 0,
            "min_zoom": h.get("min_zoom"),
            "max_zoom": h.get("max_zoom"),
            "bounds": self.tilejson("")["bounds"] if self.available else None,
            "served": self.served,
        }
