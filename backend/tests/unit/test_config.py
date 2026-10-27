"""Configuración: lo que escribe el panel se vuelve a leer igual y con rutas POSIX."""

from __future__ import annotations

import tomllib
from pathlib import Path

from meshbox.config import Config, save_config


def test_save_config_posix_paths_and_roundtrip(tmp_path: Path) -> None:
    cfg = Config()
    cfg.paths.db = Path("/var/lib/meshbox/meshbox.db")
    target = tmp_path / "config.toml"
    save_config(cfg, target)
    text = target.read_text(encoding="utf-8")
    assert "\\\\" not in text and '"/var/lib/meshbox/meshbox.db"' in text
    data = tomllib.loads(text)
    again = Config(**data)
    assert again.paths.db.as_posix() == "/var/lib/meshbox/meshbox.db"
    assert again.model_dump(mode="json") == cfg.model_dump(mode="json")
