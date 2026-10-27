"""Notificaciones a systemd (`Type=notify`, sección 29) con la biblioteca estándar."""

from __future__ import annotations

import os
import socket


def notify(state: str) -> bool:
    """Envía `READY=1`, `WATCHDOG=1`, `STOPPING=1`, `STATUS=...` si hay NOTIFY_SOCKET."""
    path = os.environ.get("NOTIFY_SOCKET")
    if not path or not hasattr(socket, "AF_UNIX"):
        return False
    if path.startswith("@"):
        path = "\0" + path[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.connect(path)
            s.sendall(state.encode())
        return True
    except OSError:
        return False


def watchdog_interval_s() -> float | None:
    """Mitad del intervalo de vigilancia de systemd (WATCHDOG_USEC), si está activo."""
    usec = os.environ.get("WATCHDOG_USEC")
    if not usec or not usec.isdigit():
        return None
    return int(usec) / 1_000_000 / 3
