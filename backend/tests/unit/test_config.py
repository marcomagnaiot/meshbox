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


def test_factory_notice_follows_the_new_default() -> None:
    """Un aviso de privacidad de fábrica guardado sin cambios pasa al actual (ADR 0019)."""
    from meshbox.settings import DEFAULT_NOTICE, OLD_NOTICES, SITE_KEY, load_site

    old = OLD_NOTICES[0]
    assert old != DEFAULT_NOTICE and "Esri World Imagery" in old
    assert load_site({SITE_KEY: {"name": "Red", "notice_md": old}}).notice_md == DEFAULT_NOTICE
    assert "mapa fuera de la zona descargada" in DEFAULT_NOTICE
    custom = old + "\nContacto: admin@example.com"
    assert load_site({SITE_KEY: {"notice_md": custom}}).notice_md == custom
    # El de la 0.9.4 y 0.9.5, sin la línea de las respuestas a pedidos de la estación (ADR 0020).
    previous = OLD_NOTICES[1]
    assert "pedido de posición" not in previous and "pedido de posición" in DEFAULT_NOTICE
    assert load_site({SITE_KEY: {"notice_md": previous}}).notice_md == DEFAULT_NOTICE
