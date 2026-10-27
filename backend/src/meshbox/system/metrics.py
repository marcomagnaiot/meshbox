"""Métricas del sistema (sección 29) y guardia de memoria (ADR 0006)."""

from __future__ import annotations

import gc
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any

import psutil

log = logging.getLogger(__name__)
THERMAL = Path("/sys/class/thermal/thermal_zone0/temp")


def cpu_temperature() -> float | None:
    try:
        return round(int(THERMAL.read_text().strip()) / 1000, 1)
    except (OSError, ValueError):
        pass
    try:
        temps = psutil.sensors_temperatures()
    except (AttributeError, OSError):
        return None
    for entries in temps.values():
        for e in entries:
            if e.current:
                return round(float(e.current), 1)
    return None


class Metrics:
    def __init__(self, data_dir: Path) -> None:
        self.proc = psutil.Process(os.getpid())
        self.data_dir = data_dir
        self.proc.cpu_percent(None)
        psutil.cpu_percent(None)
        self.started = time.time()
        self.rss_peak_mb = 0.0

    def rss_mb(self) -> float:
        rss = self.proc.memory_info().rss / 1_048_576
        self.rss_peak_mb = max(self.rss_peak_mb, rss)
        return float(round(rss, 1))

    def snapshot(self) -> dict[str, Any]:
        vm = psutil.virtual_memory()
        try:
            disk = shutil.disk_usage(self.data_dir if self.data_dir.exists() else Path.cwd())
            disk_info = {
                "total": disk.total,
                "used": disk.used,
                "free": disk.free,
                "percent": round(disk.used / disk.total * 100, 1),
            }
        except OSError:
            disk_info = {}
        try:
            load = getattr(os, "getloadavg")()  # noqa: B009 - no existe en Windows
        except (AttributeError, OSError):
            load = (0.0, 0.0, 0.0)
        swap = psutil.swap_memory()
        return {
            "ts": time.time(),
            "rss_mb": self.rss_mb(),
            "rss_peak_mb": round(self.rss_peak_mb, 1),
            "cpu_process": round(self.proc.cpu_percent(None), 1),
            "cpu_system": round(psutil.cpu_percent(None), 1),
            "threads": self.proc.num_threads(),
            "mem_total": vm.total,
            "mem_available": vm.available,
            "mem_percent": vm.percent,
            "swap_used": swap.used,
            "swap_percent": swap.percent,
            "temperature": cpu_temperature(),
            "disk": disk_info,
            "load": [round(x, 2) for x in load],
            "uptime_s": round(time.time() - self.started),
            "boot_time": psutil.boot_time(),
        }


class MemoryGuard:
    """Suave: alerta y libera cachés. Dura: termina el proceso (systemd lo reinicia)."""

    def __init__(self, soft_mb: int, hard_mb: int) -> None:
        self.soft_mb = soft_mb
        self.hard_mb = hard_mb
        self.soft_hits = 0
        self._last_soft = 0.0

    def check(self, rss_mb: float, on_soft: Any = None) -> str:
        if rss_mb >= self.hard_mb:
            log.critical(
                "memoria residente %.0f MB supera el límite duro %d MB: se reinicia",
                rss_mb,
                self.hard_mb,
            )
            return "hard"
        if rss_mb >= self.soft_mb:
            now = time.monotonic()
            if now - self._last_soft > 300:
                self._last_soft = now
                self.soft_hits += 1
                gc.collect()
                log.warning("memoria residente %.0f MB supera %d MB", rss_mb, self.soft_mb)
                if on_soft is not None:
                    on_soft(rss_mb)
            return "soft"
        return "ok"
