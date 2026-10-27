"""Comandos de meshbox-privd: un módulo por grupo y un registro con la lista cerrada."""

from __future__ import annotations

from . import cloudflared, mosquitto, services, system, update, wifi
from .core import Command

_MODULES = (system, mosquitto, cloudflared, wifi, services, update)


def build_registry() -> dict[str, Command]:
    registry: dict[str, Command] = {}
    for module in _MODULES:
        for name, command in module.COMMANDS.items():
            if name in registry:
                raise RuntimeError(f"comando duplicado: {name}")
            registry[name] = command
    return registry


REGISTRY = build_registry()

# Comandos que el modo compartido rechaza (ADR 0004).
SHARED_FORBIDDEN = frozenset(name for name, cmd in REGISTRY.items() if not cmd.shared_ok)
