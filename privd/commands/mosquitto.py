"""Comandos de Mosquitto: cuentas (passwd), ACL desde plantilla (14.2), recarga y estado."""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from pathlib import Path

from .core import (
    Args,
    Command,
    Context,
    Result,
    atomic_write,
    check_keys,
    failed,
    invalid,
    run_checked,
    unit_status,
    validate_username,
)

log = logging.getLogger("privd.mosquitto")

MOSQUITTO_OWNER = ("mosquitto", "mosquitto")
MOSQUITTO_UNIT = "mosquitto.service"

PASSWORD_MIN = 12
PASSWORD_MAX = 128
_PASSWORD_CHARS = re.compile(r"^[\x20-\x39\x3b-\x7e]+$")  # ASCII imprimible sin ':'
_HASHED_LINE = re.compile(r"^(?P<user>[a-z0-9][a-z0-9_-]{2,31}):\$[67]\$\S+$")

TOPIC_ROOT_RE = re.compile(r"^[A-Za-z0-9_/-]{1,64}$")
PURPOSES = ("gateway", "ingest", "integration", "debug")
MAX_ACCOUNTS = 256


def validate_password(value: object) -> str:
    """12-128 caracteres ASCII imprimibles, sin ':' ni saltos de línea.

    `mosquitto_passwd` corta en ':' y recorta espacios en los extremos: por eso tampoco se
    aceptan espacios al principio ni al final (la clave guardada no coincidiría).
    """
    if not isinstance(value, str):
        raise invalid("password debe ser texto")
    if not PASSWORD_MIN <= len(value) <= PASSWORD_MAX:
        raise invalid(f"password debe tener entre {PASSWORD_MIN} y {PASSWORD_MAX} caracteres")
    if not _PASSWORD_CHARS.fullmatch(value):
        raise invalid("password solo admite caracteres ASCII imprimibles, sin ':'")
    if value != value.strip():
        raise invalid("password no puede empezar ni terminar con espacios")
    return value


def validate_topic_root(value: object, name: str) -> str:
    if not isinstance(value, str) or not TOPIC_ROOT_RE.fullmatch(value):
        raise invalid(f"{name} no válido")
    if "+" in value or "#" in value or ".." in value:
        raise invalid(f"{name} no puede tener comodines ni '..'")
    if value.startswith("/") or value.endswith("/") or "//" in value:
        raise invalid(f"{name} no puede empezar ni terminar con '/' ni tener niveles vacíos")
    return value


# ---------------------------------------------------------------------------
# passwd
# ---------------------------------------------------------------------------


def _read_passwd_lines(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    return [line for line in text.splitlines() if line.strip()]


def _line_user(line: str) -> str | None:
    if ":" not in line or line.lstrip().startswith("#"):
        return None
    return line.split(":", 1)[0].strip()


def _write_passwd(ctx: Context, lines: list[str]) -> None:
    data = ("\n".join(lines) + "\n") if lines else ""
    atomic_write(
        ctx, ctx.paths.mosquitto_passwd, data.encode("utf-8"), mode=0o640, owner=MOSQUITTO_OWNER
    )


def _hash_entry(ctx: Context, username: str, password: str) -> str:
    """Convierte `usuario:clave` con `mosquitto_passwd -U` sin pasar la clave por argumentos.

    El temporal va en un directorio 0700 dentro de /etc/mosquitto (mismo sistema de archivos,
    no /tmp); el respaldo que crea mosquitto_passwd (`<archivo>.backup.XXXXXX`) queda en ese
    mismo directorio y se borra junto con él.
    """
    workdir = Path(tempfile.mkdtemp(prefix=".meshbox-passwd-", dir=str(ctx.paths.mosquitto_dir)))
    try:
        entry = workdir / "entry"
        fd = os.open(entry, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(f"{username}:{password}\n".encode())
        run_checked(
            ctx,
            [ctx.bins.mosquitto_passwd, "-U", str(entry)],
            what="mosquitto_passwd",
            umask=0o077,
        )
        lines = [ln for ln in entry.read_text(encoding="utf-8").splitlines() if ln.strip()]
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    if len(lines) != 1:
        raise failed("mosquitto_passwd devolvió un resultado inesperado")
    match = _HASHED_LINE.fullmatch(lines[0].strip())
    if not match or match.group("user") != username:
        raise failed("mosquitto_passwd devolvió un resultado inesperado")
    return lines[0].strip()


def account_set(ctx: Context, args: Args) -> Result:
    check_keys(args, ("username", "password"))
    username = validate_username(args["username"])
    password = validate_password(args["password"])
    hashed = _hash_entry(ctx, username, password)
    lines = _read_passwd_lines(ctx.paths.mosquitto_passwd)
    new_lines: list[str] = []
    replaced = False
    for line in lines:
        if _line_user(line) == username:
            if not replaced:
                new_lines.append(hashed)
                replaced = True
            continue
        new_lines.append(line)
    if not replaced:
        new_lines.append(hashed)
    _write_passwd(ctx, new_lines)
    return {"username": username, "created": not replaced}


def account_delete(ctx: Context, args: Args) -> Result:
    check_keys(args, ("username",))
    username = validate_username(args["username"])
    lines = _read_passwd_lines(ctx.paths.mosquitto_passwd)
    kept = [line for line in lines if _line_user(line) != username]
    deleted = len(kept) != len(lines)
    if deleted or not ctx.paths.mosquitto_passwd.exists():
        _write_passwd(ctx, kept)
    return {"username": username, "deleted": deleted}


def passwd_usernames(ctx: Context) -> list[str]:
    """Usuarios presentes en /etc/mosquitto/passwd (solo nombres, nunca hashes)."""
    names = (_line_user(line) for line in _read_passwd_lines(ctx.paths.mosquitto_passwd))
    return sorted({name for name in names if name})


def account_list(ctx: Context, args: Args) -> Result:
    check_keys(args)
    return {"accounts": [{"username": name} for name in passwd_usernames(ctx)]}


# ---------------------------------------------------------------------------
# ACL
# ---------------------------------------------------------------------------


def render_acl(root: str, events_prefix: str, accounts: list[tuple[str, str]]) -> str:
    """Plantilla de 14.2. `accounts` es una lista de (usuario, propósito) ya validada."""
    lines = [
        "# Generado por meshbox-privd. No editar a mano: el panel de meshbox lo reescribe.",
        f"# root={root} events_prefix={events_prefix}",
    ]
    for username, purpose in sorted(accounts):
        lines.append("")
        lines.append(f"user {username}")
        if purpose == "gateway":
            lines.append(f"topic readwrite {root}/#")
        elif purpose == "ingest":
            lines.append(f"topic read {root}/#")
            lines.append(f"topic write {events_prefix}/#")
        elif purpose == "integration":
            lines.append(f"topic read {events_prefix}/events/#")
        elif purpose == "debug":
            lines.append(f"topic read {root}/#")
        else:  # pragma: no cover - validado antes
            raise invalid("purpose no válido")
    return "\n".join(lines) + "\n"


def acl_write(ctx: Context, args: Args) -> Result:
    check_keys(args, ("root", "accounts"), ("events_prefix",))
    root = validate_topic_root(args["root"], "root")
    events_prefix = validate_topic_root(args.get("events_prefix", "meshbox"), "events_prefix")
    raw_accounts = args["accounts"]
    if not isinstance(raw_accounts, list):
        raise invalid("accounts debe ser una lista")
    if len(raw_accounts) > MAX_ACCOUNTS:
        raise invalid(f"accounts admite como máximo {MAX_ACCOUNTS} cuentas")
    accounts: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in raw_accounts:
        if not isinstance(item, dict):
            raise invalid("cada cuenta debe ser un objeto {username, purpose}")
        check_keys(item, ("username", "purpose"))
        username = validate_username(item["username"])
        purpose = item["purpose"]
        if purpose not in PURPOSES:
            raise invalid("purpose no válido")
        if username in seen:
            raise invalid("username repetido en accounts")
        seen.add(username)
        accounts.append((username, purpose))
    # La lista completa la decide el backend; privd la renderiza tal cual, pero avisa si deja
    # sin permisos a una cuenta que existe en passwd (por ejemplo, una creada a mano).
    omitted = [name for name in passwd_usernames(ctx) if name not in seen]
    if omitted:
        log.warning(
            "mosquitto.acl.write: la ACL no incluye cuentas presentes en passwd: %s",
            ", ".join(omitted),
        )
    text = render_acl(root, events_prefix, accounts)
    atomic_write(
        ctx, ctx.paths.mosquitto_acl, text.encode("utf-8"), mode=0o640, owner=MOSQUITTO_OWNER
    )
    return {"accounts": len(accounts), "bytes": len(text.encode("utf-8")), "omitted": omitted}


# ---------------------------------------------------------------------------
# Servicio
# ---------------------------------------------------------------------------


def reload(ctx: Context, args: Args) -> Result:
    check_keys(args)
    run_checked(ctx, [ctx.bins.systemctl, "reload", MOSQUITTO_UNIT], what="systemctl reload")
    return {"reloaded": True}


def status(ctx: Context, args: Args) -> Result:
    check_keys(args)
    result = unit_status(ctx, MOSQUITTO_UNIT)
    result["accounts"] = passwd_usernames(ctx)
    result["acl_present"] = ctx.paths.mosquitto_acl.is_file()
    return result


COMMANDS = {
    "mosquitto.account.set": Command(account_set, secret_args=frozenset({"password"})),
    "mosquitto.account.delete": Command(account_delete),
    "mosquitto.account.list": Command(account_list),
    "mosquitto.acl.write": Command(acl_write),
    "mosquitto.reload": Command(reload),
    "mosquitto.status": Command(status),
}
