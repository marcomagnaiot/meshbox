"""Comandos del túnel de Cloudflare (modo token, 15.1) sobre meshbox-cloudflared.service."""

from __future__ import annotations

import contextlib
import re
from pathlib import Path

from .core import (
    Args,
    Command,
    Context,
    Result,
    atomic_write,
    check_keys,
    ensure_dir,
    failed,
    get_bool,
    invalid,
    run_checked,
    unit_status,
)

UNIT = "meshbox-cloudflared.service"
ENV_FILE_NAME = "cloudflared.env"

# El token del túnel es base64 (estándar o url) de un JSON; se admite también la forma de JWT.
# Sin espacios, comillas, '$', '\\' ni saltos de línea: es seguro como valor de EnvironmentFile.
TOKEN_RE = re.compile(r"^[A-Za-z0-9+/_.-]{48,4096}={0,2}$")
TOKEN_MIN = 50
TOKEN_MAX = 4096


def validate_token(value: object) -> str:
    if not isinstance(value, str):
        raise invalid("token debe ser texto")
    if not TOKEN_MIN <= len(value) <= TOKEN_MAX or not TOKEN_RE.fullmatch(value):
        raise invalid("token no válido")
    return value


def _env_file(ctx: Context) -> Path:
    return ctx.paths.tunnel_dir / ENV_FILE_NAME


def set_token(ctx: Context, args: Args) -> Result:
    check_keys(args, ("token",))
    token = validate_token(args["token"])
    ensure_dir(ctx.paths.tunnel_dir, 0o700)
    data = f"TUNNEL_TOKEN={token}\n".encode("ascii")
    atomic_write(ctx, _env_file(ctx), data, mode=0o600)
    return {"written": True}


def enable(ctx: Context, args: Args) -> Result:
    check_keys(args)
    if not _env_file(ctx).is_file():
        raise failed("no hay token configurado (cloudflared.set_token)")
    run_checked(ctx, [ctx.bins.systemctl, "enable", UNIT], what="systemctl enable")
    # --no-block: el arranque de cloudflared puede tardar; el estado se consulta con .status.
    run_checked(ctx, [ctx.bins.systemctl, "--no-block", "restart", UNIT], what="systemctl restart")
    return {"enabled": True}


def disable(ctx: Context, args: Args) -> Result:
    check_keys(args, (), ("forget_token",))
    forget = get_bool(args, "forget_token")
    run_checked(ctx, [ctx.bins.systemctl, "disable", "--now", UNIT], what="systemctl disable")
    removed = False
    if forget:
        with contextlib.suppress(FileNotFoundError):
            _env_file(ctx).unlink()
            removed = True
    return {"enabled": False, "token_removed": removed}


def restart(ctx: Context, args: Args) -> Result:
    check_keys(args)
    if not _env_file(ctx).is_file():
        raise failed("no hay token configurado (cloudflared.set_token)")
    run_checked(ctx, [ctx.bins.systemctl, "--no-block", "restart", UNIT], what="systemctl restart")
    return {"queued": True}


def status(ctx: Context, args: Args) -> Result:
    check_keys(args)
    result = unit_status(ctx, UNIT)
    result["token_configured"] = _env_file(ctx).is_file()
    return result


COMMANDS = {
    "cloudflared.set_token": Command(set_token, secret_args=frozenset({"token"})),
    "cloudflared.enable": Command(enable),
    "cloudflared.disable": Command(disable),
    "cloudflared.restart": Command(restart),
    "cloudflared.status": Command(status),
}
