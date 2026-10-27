from __future__ import annotations

import shutil
from pathlib import Path

from pmtiles.reader import MmapSource, all_tiles

from meshbox.tiles import TileStore

FIXTURE = Path(__file__).parent.parent / "fixtures" / "viedma-centro.pmtiles"


def _store(tmp_path: Path) -> TileStore:
    shutil.copy(FIXTURE, tmp_path / "region.pmtiles")
    return TileStore(tmp_path)


def test_every_tile_matches_reference_reader(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.available and store.gzipped
    n = 0
    with FIXTURE.open("rb") as f:
        for (z, x, y), data in all_tiles(MmapSource(f)):
            assert store.get(z, x, y) == data, (z, x, y)
            n += 1
    assert n >= 15  # el extracto del centro tiene 21 teselas
    store.close()


def test_missing_and_out_of_range(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.get(14, 0, 0) is None
    assert store.get(20, 1, 1) is None
    assert store.get(3, 99, 99) is None
    tj = store.tilejson("")
    assert tj["maxzoom"] == 14 and tj["vector_layers"]
    store.close()


def test_absent_file(tmp_path: Path) -> None:
    store = TileStore(tmp_path)
    assert not store.available
    assert store.get(0, 0, 0) is None
    assert store.status()["available"] is False
