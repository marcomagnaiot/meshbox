"""API de administración (sección 12.4): una ruta por área."""

from __future__ import annotations

import importlib
import logging
from typing import Any

log = logging.getLogger(__name__)

AREAS = (
    "auth",
    "setup",
    "system",
    "network",
    "connectors",
    "mqtt",
    "channels",
    "packets",
    "nodes",
    "messages",
    "alerts",
    "site",
    "privacy",
    "cloudflare",
    "plugins",
    "users",
    "backups",
    "updates",
    "tx",
    "radio",
)


def routers() -> list[Any]:
    out = []
    for area in AREAS:
        try:
            module = importlib.import_module(f"{__name__}.{area}")
        except ModuleNotFoundError as e:
            if e.name and e.name.endswith(f".{area}"):
                continue  # área todavía no implementada
            raise
        out.append(module.router)
        extra = getattr(module, "portal", None)  # portal cautivo del asistente (24.3)
        if extra is not None:
            out.append(extra)
    return out
