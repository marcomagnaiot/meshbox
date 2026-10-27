"""Migraciones (sección 11.5).

`pending()` no importa Alembic (solo sqlite3): el servicio lo consulta al arrancar y, si
hay migraciones pendientes, las aplica en un proceso aparte (`meshbox migrate`), así
Alembic y Mako no quedan en la memoria del servicio (ADR 0010).
"""

from __future__ import annotations

import logging
import sqlite3
import subprocess
import sys
from pathlib import Path

from .backup import create_backup, restore_backup

log = logging.getLogger(__name__)

HEAD = "0003"  # última revisión; una prueba verifica que coincida con Alembic
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def current_revision(db_path: Path) -> str | None:
    if not db_path.exists():
        return None
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        has = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        ).fetchone()[0]
        if not has:
            return None
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        return str(row[0]) if row else None
    finally:
        conn.close()


def pending(db_path: Path) -> bool:
    return current_revision(db_path) != HEAD


def _init_new_db(db_path: Path) -> None:
    """Antes de la primera migración: auto_vacuum incremental y WAL."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("VACUUM")
    finally:
        conn.close()


def upgrade(db_path: Path) -> None:
    from alembic import command
    from alembic.config import Config as AlembicConfig

    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    command.upgrade(cfg, "head")


def migrate(db_path: Path, backups_dir: Path, version: str, tmp_dir: Path | None = None) -> str:
    """Aplica las migraciones pendientes. Devuelve 'up-to-date', 'created' o 'migrated'.

    Con una base existente hace un respaldo `-pre-<versión>` y, si la migración falla,
    lo restaura y vuelve a lanzar la excepción (el servicio no arranca).
    """
    rev = current_revision(db_path)
    if rev == HEAD:
        return "up-to-date"
    if not db_path.exists():
        _init_new_db(db_path)
        upgrade(db_path)
        log.info("base creada en %s (revisión %s)", db_path, HEAD)
        return "created"
    info = create_backup(db_path, backups_dir, suffix=f"pre-{version}", tmp_dir=tmp_dir)
    try:
        upgrade(db_path)
    except Exception:
        log.exception("la migración falló; se restaura %s", info.name)
        restore_backup(backups_dir / info.name, db_path, tmp_dir)
        raise
    log.info("base migrada de %s a %s", rev, HEAD)
    return "migrated"


def migrate_in_subprocess(config_path: Path | None) -> None:
    cmd = [sys.executable, "-m", "meshbox", "migrate"]
    if config_path is not None:
        cmd += ["--config", str(config_path)]
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"las migraciones fallaron (código {result.returncode})")
