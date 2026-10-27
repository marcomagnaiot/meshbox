"""Respaldos de la base (sección 11.6): API de respaldo en caliente de SQLite + gzip."""

from __future__ import annotations

import contextlib
import gzip
import logging
import os
import re
import shutil
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

DAILY_RE = re.compile(r"^meshbox-(\d{8})\.db\.gz$")
ANY_RE = re.compile(r"^meshbox-[0-9A-Za-z._-]+\.db\.gz$")
KEEP_DAILY = 7
KEEP_TAGGED = 5


@dataclass(frozen=True, slots=True)
class BackupInfo:
    name: str
    size: int
    mtime: float
    daily: bool

    def as_dict(self) -> dict[str, object]:
        return {"name": self.name, "size": self.size, "mtime": self.mtime, "daily": self.daily}


def valid_backup_name(name: str) -> bool:
    return bool(ANY_RE.match(name)) and "/" not in name and "\\" not in name and ".." not in name


def _gzip_file(src: Path, dest: Path) -> None:
    tmp = dest.with_name(dest.name + ".part")
    with src.open("rb") as fin, gzip.open(tmp, "wb", compresslevel=6) as fout:
        shutil.copyfileobj(fin, fout, 1024 * 1024)
    os.replace(tmp, dest)


def hot_backup(db_path: Path, dest_gz: Path, tmp_dir: Path | None = None) -> Path:
    """Copia consistente con la base en uso (WAL) y la comprime."""
    dest_gz.parent.mkdir(parents=True, exist_ok=True)
    work_dir = tmp_dir or dest_gz.parent
    work_dir.mkdir(parents=True, exist_ok=True)
    tmp_db = work_dir / f".backup-{os.getpid()}-{int(time.time() * 1000)}.db"
    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(tmp_db)
        try:
            src.backup(dst, pages=4096)
        finally:
            dst.close()
    finally:
        src.close()
    try:
        _gzip_file(tmp_db, dest_gz)
    finally:
        tmp_db.unlink(missing_ok=True)
    return dest_gz


def backup_name(suffix: str | None = None, now: float | None = None) -> str:
    t = time.localtime(now or time.time())
    if not suffix:
        return time.strftime("meshbox-%Y%m%d.db.gz", t)
    clean = re.sub(r"[^0-9A-Za-z._-]", "_", suffix)[:40]
    return time.strftime(f"meshbox-%Y%m%d-%H%M%S-{clean}.db.gz", t)


def create_backup(
    db_path: Path, backups_dir: Path, suffix: str | None = None, tmp_dir: Path | None = None
) -> BackupInfo:
    if not db_path.exists():
        raise FileNotFoundError(f"no existe la base {db_path}")
    dest = backups_dir / backup_name(suffix)
    hot_backup(db_path, dest, tmp_dir)
    prune(backups_dir)
    st = dest.stat()
    log.info("respaldo creado: %s (%d bytes)", dest.name, st.st_size)
    return BackupInfo(dest.name, st.st_size, st.st_mtime, suffix is None)


def list_backups(backups_dir: Path) -> list[BackupInfo]:
    if not backups_dir.exists():
        return []
    out = []
    for p in backups_dir.iterdir():
        if p.is_file() and ANY_RE.match(p.name):
            st = p.stat()
            out.append(BackupInfo(p.name, st.st_size, st.st_mtime, bool(DAILY_RE.match(p.name))))
    out.sort(key=lambda b: b.mtime, reverse=True)
    return out


def prune(backups_dir: Path) -> list[str]:
    removed: list[str] = []
    backups = list_backups(backups_dir)
    daily = [b for b in backups if b.daily]
    tagged = [b for b in backups if not b.daily]
    for b in daily[KEEP_DAILY:] + tagged[KEEP_TAGGED:]:
        (backups_dir / b.name).unlink(missing_ok=True)
        removed.append(b.name)
    return removed


def integrity_ok(db_file: Path) -> tuple[bool, str]:
    conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        result = str(row[0]) if row else "sin resultado"
        has_nodes = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='nodes'"
        ).fetchone()[0]
    except sqlite3.DatabaseError as e:
        return False, str(e)
    finally:
        conn.close()
    if result != "ok":
        return False, result
    if not has_nodes:
        return False, "el archivo no es una base de meshbox"
    return True, "ok"


def decompress_to(gz_path: Path, dest: Path) -> None:
    tmp = dest.with_name(dest.name + ".part")
    with gzip.open(gz_path, "rb") as fin, tmp.open("wb") as fout:
        shutil.copyfileobj(fin, fout, 1024 * 1024)
    os.replace(tmp, dest)


def restore_backup(gz_path: Path, db_path: Path, tmp_dir: Path | None = None) -> None:
    """Valida el respaldo y reemplaza la base. Con el servicio detenido o la base cerrada."""
    work = tmp_dir or db_path.parent
    work.mkdir(parents=True, exist_ok=True)
    candidate = work / f".restore-{os.getpid()}.db"
    decompress_to(gz_path, candidate)
    ok, msg = integrity_ok(candidate)
    if not ok:
        candidate.unlink(missing_ok=True)
        raise ValueError(f"respaldo no válido: {msg}")
    for suffix in ("-wal", "-shm"):
        with contextlib.suppress(FileNotFoundError):
            Path(str(db_path) + suffix).unlink()
    os.replace(candidate, db_path)
    log.warning("base restaurada desde %s", gz_path.name)
