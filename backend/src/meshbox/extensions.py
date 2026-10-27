"""Registro de módulos opcionales del servicio: teselas, alertas, push, salida MQTT, plugins.

Cada módulo queda en `service.extensions[<nombre>]` con `start()`/`stop()` si los necesita.
Un módulo que falla al iniciar se registra en el log y no impide que el resto arranque.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .app import Service

log = logging.getLogger(__name__)


async def start_extensions(service: Service) -> None:
    from .tiles import TileStore

    service.extensions["tiles"] = TileStore(service.cfg.paths.tiles)
    for name, factory in _optional_factories():
        try:
            ext = factory(service)
            if ext is None:
                continue
            start = getattr(ext, "start", None)
            if start is not None:
                await start()
            service.extensions[name] = ext
        except Exception:
            log.exception("el módulo %s no pudo iniciar", name)


def _optional_factories() -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    try:
        from .auth.service import make_auth

        out.append(("auth", make_auth))
    except ImportError:
        pass
    try:
        from .alerts.engine import make_engine

        out.append(("alerts", make_engine))
    except ImportError:
        pass
    try:
        from .alerts.channels.mqtt_out import make_mqtt_out

        out.append(("mqtt_out", make_mqtt_out))
    except ImportError:
        pass
    try:
        from .plugins.loader import make_plugins

        out.append(("plugins", make_plugins))
    except ImportError:
        pass
    return out


def get(service: Service, name: str) -> Any:
    return service.extensions.get(name)
