"""Servicios y registros: service.restart, service.status y logs.read (listas cerradas)."""

from __future__ import annotations

import json
import re
from typing import Any

from .core import (
    Args,
    Command,
    Context,
    Result,
    check_keys,
    get_int,
    get_str,
    invalid,
    run_checked,
    unit_status,
)

SERVICES = {
    "meshbox": "meshbox.service",
    "mosquitto": "mosquitto.service",
    "meshbox-cloudflared": "meshbox-cloudflared.service",
    "meshbox-privd": "meshbox-privd.service",
}

LOG_UNITS = {
    **SERVICES,
    "meshbox-backup": "meshbox-backup.service",
    "meshbox-firstboot": "meshbox-firstboot.service",
    "NetworkManager": "NetworkManager.service",
}

# Formatos aceptados por `journalctl --since` que se permiten desde el panel.
SINCE_RE = re.compile(
    r"^(?:today|yesterday|now"
    r"|-\d{1,6}(?:s|sec|m|min|h|d|w)"
    r"|@\d{1,12}"
    r"|\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?)$"
)
MAX_MESSAGE = 4096


def _service_name(args: Args) -> tuple[str, str]:
    name = get_str(args, "name")
    unit = SERVICES.get(name)
    if unit is None:
        raise invalid("name no permitido")
    return name, unit


def restart(ctx: Context, args: Args) -> Result:
    check_keys(args, ("name",))
    name, unit = _service_name(args)
    if name == "meshbox-privd" and ctx.serving:
        # privd se reinicia a sí mismo saliendo después de responder: el socket queda escuchando
        # y la próxima petición arranca el código nuevo.
        ctx.exit_requested = True
        return {"name": name, "unit": unit, "queued": True}
    # --no-block: reiniciar meshbox puede tardar (migraciones) y quien llama suele ser meshbox.
    run_checked(ctx, [ctx.bins.systemctl, "--no-block", "restart", unit], what="systemctl restart")
    return {"name": name, "unit": unit, "queued": True}


def status(ctx: Context, args: Args) -> Result:
    check_keys(args, ("name",))
    name, unit = _service_name(args)
    result = unit_status(ctx, unit)
    result["name"] = name
    return result


def _message_text(value: Any) -> str:
    if isinstance(value, str):
        text = value
    elif isinstance(value, list) and all(isinstance(b, int) and 0 <= b < 256 for b in value):
        text = bytes(value).decode("utf-8", "replace")
    else:
        text = ""
    return text[:MAX_MESSAGE]


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_journal(out: str) -> list[dict[str, Any]]:
    entries = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if not isinstance(item, dict):
            continue
        ts_us = _as_int(item.get("__REALTIME_TIMESTAMP"))
        entries.append(
            {
                "ts": ts_us / 1_000_000 if ts_us is not None else None,
                "priority": _as_int(item.get("PRIORITY")),
                "message": _message_text(item.get("MESSAGE")),
                "pid": _as_int(item.get("_PID")),
                "identifier": item.get("SYSLOG_IDENTIFIER")
                if isinstance(item.get("SYSLOG_IDENTIFIER"), str)
                else None,
            }
        )
    return entries


def logs_read(ctx: Context, args: Args) -> Result:
    check_keys(args, ("unit",), ("lines", "since"))
    unit_name = get_str(args, "unit")
    unit = LOG_UNITS.get(unit_name)
    if unit is None and unit_name in LOG_UNITS.values():
        unit = unit_name
    if unit is None:
        raise invalid("unit no permitida")
    lines = get_int(args, "lines", minimum=1, maximum=2000, default=200)
    argv = [
        ctx.bins.journalctl,
        f"--unit={unit}",
        f"--lines={lines}",
        "--output=json",
        "--no-pager",
        "--quiet",
    ]
    if "since" in args:
        since = get_str(args, "since")
        if not SINCE_RE.fullmatch(since):
            raise invalid("since no válido")
        argv.append(f"--since={since}")
    out = run_checked(ctx, argv, what="journalctl").out
    return {"unit": unit, "entries": parse_journal(out)}


COMMANDS = {
    "service.restart": Command(restart, exclusive=True),
    "service.status": Command(status),
    "logs.read": Command(logs_read),
}
