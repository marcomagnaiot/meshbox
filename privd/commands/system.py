"""Comandos del sistema: ping, nombre de host, zona horaria, reinicio, apagado e información."""

from __future__ import annotations

import os
import platform
import re
from pathlib import Path

from .core import (
    PRIVD_VERSION,
    Args,
    Command,
    Context,
    Result,
    atomic_write,
    check_keys,
    invalid,
    parse_key_values,
    read_text_limited,
    run_checked,
)

HOSTNAME_RE = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")
TIMEZONE_RE = re.compile(r"^[A-Za-z0-9_+-]{1,32}(?:/[A-Za-z0-9_+-]{1,32}){0,2}$")
POWER_DELAY_S = 2.0
CLOUD_INIT_DROPIN = "99-meshbox-hostname.cfg"


def ping(ctx: Context, args: Args) -> Result:
    check_keys(args)
    return {"version": PRIVD_VERSION, "mode": ctx.mode}


# ---------------------------------------------------------------------------
# Nombre de host (solo modo appliance)
# ---------------------------------------------------------------------------


def validate_hostname(value: object) -> str:
    if not isinstance(value, str) or not HOSTNAME_RE.fullmatch(value):
        raise invalid("name no válido (RFC 1123: letras, números y '-', hasta 63)")
    return value.lower()


def _update_etc_hosts(ctx: Context, name: str) -> None:
    path = ctx.paths.etc_hosts
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = ["127.0.0.1\tlocalhost"]
    entry = f"127.0.1.1\t{name}"
    out: list[str] = []
    found = False
    for line in lines:
        if re.match(r"^\s*127\.0\.1\.1\s", line):
            if not found:
                out.append(entry)
                found = True
            continue
        out.append(line)
    if not found:
        out.append(entry)
    atomic_write(ctx, path, ("\n".join(out) + "\n").encode("utf-8"), mode=0o644)


def _keep_hostname_with_cloud_init(ctx: Context) -> None:
    """En trixie, cloud-init (personalización de Raspberry Pi Imager) maneja el nombre de host.

    Se le pide que conserve el nombre fijado por el panel y que no regenere /etc/hosts.
    """
    directory = ctx.paths.cloud_cfg_d
    if not directory.is_dir():
        return
    text = (
        "# Generado por meshbox-privd: el nombre de host lo administra el panel de meshbox.\n"
        "preserve_hostname: true\n"
        "manage_etc_hosts: false\n"
    )
    atomic_write(ctx, directory / CLOUD_INIT_DROPIN, text.encode("utf-8"), mode=0o644)


def hostname(ctx: Context, args: Args) -> Result:
    check_keys(args, ("name",))
    name = validate_hostname(args["name"])
    run_checked(ctx, [ctx.bins.hostnamectl, "set-hostname", name], what="hostnamectl")
    _update_etc_hosts(ctx, name)
    _keep_hostname_with_cloud_init(ctx)
    return {"hostname": name}


# ---------------------------------------------------------------------------
# Zona horaria
# ---------------------------------------------------------------------------


def validate_timezone(ctx: Context, value: object) -> str:
    if not isinstance(value, str) or not TIMEZONE_RE.fullmatch(value):
        raise invalid("tz no válida")
    if value.startswith(("-", "+")) or ".." in value:
        raise invalid("tz no válida")
    base = ctx.paths.zoneinfo_dir
    candidate = base / value
    try:
        resolved = candidate.resolve(strict=True)
        base_resolved = base.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise invalid("tz desconocida") from exc
    if not resolved.is_file() or not resolved.is_relative_to(base_resolved):
        raise invalid("tz desconocida")
    return value


def timezone(ctx: Context, args: Args) -> Result:
    check_keys(args, ("tz",))
    tz = validate_timezone(ctx, args["tz"])
    run_checked(ctx, [ctx.bins.timedatectl, "set-timezone", tz], what="timedatectl")
    return {"timezone": tz}


def time_status(ctx: Context, args: Args) -> Result:
    check_keys(args)
    out = run_checked(ctx, [ctx.bins.timedatectl, "show"], what="timedatectl show").out
    kv = parse_key_values(out)

    def flag(key: str) -> bool | None:
        value = kv.get(key)
        return None if value is None else value == "yes"

    time_usec = kv.get("TimeUSec")
    return {
        "timezone": kv.get("Timezone"),
        "ntp": flag("NTP"),
        "ntp_synchronized": flag("NTPSynchronized"),
        "can_ntp": flag("CanNTP"),
        "local_rtc": flag("LocalRTC"),
        "time": time_usec,
    }


# ---------------------------------------------------------------------------
# Reinicio y apagado
# ---------------------------------------------------------------------------


def _power(ctx: Context, action: str) -> Result:
    # Se responde primero y se ejecuta unos segundos después, en un trabajo aparte.
    def run(job: object) -> Result:
        ctx.sleep(POWER_DELAY_S)
        run_checked(ctx, [ctx.bins.systemctl, action], what=f"systemctl {action}", timeout=60)
        return {"action": action}

    job = ctx.jobs.start("power", run, group="power", meta={"action": action})
    return {"scheduled": True, "action": action, "delay_s": POWER_DELAY_S, "job": job.id}


def reboot(ctx: Context, args: Args) -> Result:
    check_keys(args)
    return _power(ctx, "reboot")


def shutdown(ctx: Context, args: Args) -> Result:
    check_keys(args)
    return _power(ctx, "poweroff")


# ---------------------------------------------------------------------------
# Información
# ---------------------------------------------------------------------------


def _read_optional(path: Path, limit: int = 4096) -> str | None:
    try:
        return read_text_limited(path, limit)
    except OSError:
        return None


def info(ctx: Context, args: Args) -> Result:
    check_keys(args)
    model_raw = _read_optional(ctx.paths.device_tree_model)
    model = model_raw.replace("\x00", "").strip() if model_raw else None
    uptime_raw = _read_optional(ctx.paths.proc_dir / "uptime")
    uptime: float | None = None
    if uptime_raw:
        try:
            uptime = float(uptime_raw.split()[0])
        except (ValueError, IndexError):
            uptime = None
    os_release = parse_key_values(_read_optional(ctx.paths.os_release) or "")
    host = (_read_optional(ctx.paths.etc_hostname) or "").strip() or platform.node()
    uname = os.uname() if hasattr(os, "uname") else None
    return {
        "hostname": host,
        "mode": ctx.mode,
        "kernel": uname.release if uname else platform.release(),
        "arch": uname.machine if uname else platform.machine(),
        "model": model,
        "uptime_s": uptime,
        "os": os_release.get("PRETTY_NAME", "").strip('"') or None,
        "python": platform.python_version(),
        "privd_version": PRIVD_VERSION,
    }


COMMANDS = {
    "ping": Command(ping),
    "system.hostname": Command(hostname, shared_ok=False, exclusive=True),
    "system.timezone": Command(timezone),
    "system.reboot": Command(reboot, exclusive=True),
    "system.shutdown": Command(shutdown, exclusive=True),
    "system.info": Command(info),
    "time.status": Command(time_status),
}
