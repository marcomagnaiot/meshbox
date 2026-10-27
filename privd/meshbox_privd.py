"""meshbox-privd: operaciones privilegiadas de meshbox con lista cerrada de comandos (13.3).

Servicio root activado por el socket Unix /run/meshbox/privd.sock (root:meshbox 0660,
`Accept=no`): un único proceso atiende las conexiones de a una y sale tras un rato sin actividad
y sin trabajos en curso; systemd lo vuelve a levantar con la próxima conexión.

Uso:
    meshbox_privd.py serve [--socket RUTA] [--idle-timeout S]   # servicio (o prueba local)
    meshbox_privd.py call  < peticion.json                        # una sola vez (instalador)
    meshbox_privd.py [--config RUTA] ...                          # por defecto privd.toml

Protocolo (Anexo D): una línea JSON por conexión.

    -> {"cmd": "mosquitto.account.set", "args": {...}, "request_id": "6f1c"}
    <- {"request_id": "6f1c", "ok": true, "result": {...}}
    <- {"request_id": "6f1c", "ok": false, "error": {"code": "invalid_args", "message": "..."}}

Códigos de error: invalid_json, unknown_command, invalid_args, not_allowed_in_shared_mode,
command_failed, timeout, busy.

Comandos (args -> result):

    ping                         {} -> {version, mode}
    system.info                  {} -> {hostname, mode, kernel, arch, model, uptime_s, os, python,
                                       privd_version}
    system.hostname*             {name} -> {hostname}
    system.timezone              {tz} -> {timezone}
    system.reboot / .shutdown    {} -> {scheduled, action, delay_s, job}
    time.status                  {} -> {timezone, ntp, ntp_synchronized, can_ntp, local_rtc, time}
    mosquitto.account.set        {username, password} -> {username, created}
    mosquitto.account.delete     {username} -> {username, deleted}
    mosquitto.account.list       {} -> {accounts: [{username}]}
    mosquitto.acl.write          {root, events_prefix?, accounts: [{username, purpose}]}
                                 -> {accounts, bytes, omitted}
    mosquitto.reload             {} -> {reloaded}
    mosquitto.status             {} -> estado de la unidad + {accounts, acl_present}
    cloudflared.set_token        {token} -> {written}
    cloudflared.enable           {} -> {enabled}
    cloudflared.disable          {forget_token?} -> {enabled, token_removed}
    cloudflared.restart          {} -> {queued}
    cloudflared.status           {} -> estado de la unidad + {token_configured}
    wifi.scan                    {} -> {networks: [...], cached, scanned_at}
    wifi.status                  {} -> {device, state, connection, ssid, signal, ip4, hotspot,
                                       saved, job}
    wifi.connect*                {ssid, psk} -> {job, state}   (trabajo: ventana de 2 min)
    wifi.forget*                 {ssid, force?} -> {ssid, deleted}
    hotspot.start*               {} -> {ssid, address, password_source}
    hotspot.stop*                {} -> {stopped, reconnected}
    service.restart              {name} -> {name, unit, queued}
    service.status               {name} -> estado de la unidad + {name}
    logs.read                    {unit, lines?, since?} -> {unit, entries: [...]}
    update.apply                 {version} -> {job, state}
    update.status                {job} -> estado del trabajo (cualquier tipo)
    update.rollback              {version?} -> {job, state}
    update.info                  {} -> {current, installed, previous, last_update, job,
                                       updates_base_url}

    * rechazados en modo shared con not_allowed_in_shared_mode (ADR 0004).

Estado de una unidad: {unit, load, active, sub, enabled, pid, restarts, result, since}.
Estado de un trabajo: {job, kind, state (running|succeeded|failed|rolled_back|interrupted),
step, progress, message, error_code, started_at, finished_at, meta, result}.

Solo biblioteca estándar de Python >= 3.11. Nunca shell=True; binarios con ruta absoluta;
120 s como máximo por comando sincrónico; registro de cada comando sin secretos.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import re
import select
import signal
import socket
import stat
import struct
import sys
import threading
import time
import tomllib
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urlsplit

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:  # con `python3 -I` el directorio del script no está en sys.path
    sys.path.insert(0, str(_HERE))

from commands import REGISTRY  # noqa: E402
from commands.core import (  # noqa: E402
    COMMAND_TIMEOUT_S,
    MODES,
    PRIVD_VERSION,
    CommandError,
    Config,
    Context,
    Paths,
    SubprocessRunner,
    deadline,
    ensure_dir,
)
from commands.jobs import JobManager  # noqa: E402
from commands.update import RELEASE_PUBLIC_KEY_PEM  # noqa: E402

log = logging.getLogger("privd")

DEFAULT_CONFIG = Path("/etc/meshbox-privd/privd.toml")
DEFAULT_SOCKET = Path("/run/meshbox/privd.sock")
SD_LISTEN_FDS_START = 3
MAX_REQUEST_BYTES = 256 * 1024
CONNECTION_TIMEOUT_S = 15.0
REQUEST_KEYS = frozenset({"cmd", "args", "request_id"})
CONFIG_KEYS = frozenset(
    {"mode", "health_url", "updates_base_url", "opt_dir", "python", "idle_timeout_s"}
)
_HEALTH_RE = re.compile(r"^http://(?:127\.0\.0\.1|localhost|\[::1\])(?::\d{1,5})?/[\x21-\x7e]*$")
_REQUEST_ID_RE = re.compile(r"^[\x20-\x7e]{1,128}$")


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------


def _insecure_reason(path: Path, trusted_uids: set[int]) -> str | None:
    """Motivo por el que no se confía en el archivo (o None). Solo aplica en POSIX."""
    if os.name != "posix":
        return None
    for target in (path, path.parent):
        try:
            st = target.stat()
        except OSError as exc:
            return f"no se pudo leer {target}: {exc.strerror}"
        if st.st_uid not in trusted_uids:
            return f"{target} no pertenece a root"
        if st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            return f"{target} es escribible por el grupo u otros usuarios"
    return None


def _trusted_uids() -> set[int]:
    euid = os.geteuid() if hasattr(os, "geteuid") else 0
    return {0} if euid == 0 else {0, euid}


def _valid_url(value: str) -> bool:
    if len(value) > 512 or any(ch.isspace() or ord(ch) < 32 for ch in value):
        return False
    parts = urlsplit(value)
    if parts.scheme in ("https", "http"):
        return bool(parts.netloc)
    return parts.scheme == "file" and parts.path.startswith("/")


def _valid_python(value: str, trusted_uids: set[int]) -> bool:
    if not value.startswith("/") or ".." in value:
        return False
    if os.name != "posix":
        return True
    try:
        st = Path(value).stat()
    except OSError:
        return False
    return (
        stat.S_ISREG(st.st_mode)
        and st.st_uid in trusted_uids
        and not st.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    )


def load_config(path: Path, *, trusted_uids: set[int] | None = None) -> tuple[Config, list[str]]:
    """Lee privd.toml. Ante cualquier duda usa valores seguros (modo shared)."""
    trusted = trusted_uids if trusted_uids is not None else _trusted_uids()
    warnings: list[str] = []
    data: dict[str, Any] = {}
    if not path.exists():
        warnings.append(f"no existe {path}: se usan los valores por defecto (modo shared)")
    else:
        reason = _insecure_reason(path, trusted)
        if reason is not None:
            warnings.append(f"se ignora {path}: {reason}")
        else:
            try:
                data = tomllib.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
                warnings.append(f"no se pudo leer {path}: {exc}")
    defaults = Config()
    for key in sorted(set(data) - CONFIG_KEYS):
        warnings.append(f"clave desconocida en privd.toml: {key}")

    mode = data.get("mode", defaults.mode)
    if mode not in MODES:
        warnings.append("mode no válido: se usa shared")
        mode = "shared"

    health_url = data.get("health_url", "")
    if not isinstance(health_url, str) or (health_url and not _HEALTH_RE.fullmatch(health_url)):
        warnings.append("health_url no válida (debe ser http://127.0.0.1:<puerto>/...)")
        health_url = ""

    updates = data.get("updates_base_url", "")
    if not isinstance(updates, str) or (updates and not _valid_url(updates)):
        warnings.append("updates_base_url no válida")
        updates = ""

    opt_dir = defaults.opt_dir
    if "opt_dir" in data:
        value = data["opt_dir"]
        if isinstance(value, str) and value.startswith("/") and ".." not in value:
            opt_dir = Path(value)
        else:
            warnings.append("opt_dir no válido: se usa /opt/meshbox")

    python = defaults.python
    if "python" in data:
        value = data["python"]
        if isinstance(value, str) and _valid_python(value, trusted):
            python = value
        else:
            warnings.append(f"python no válido (ruta absoluta, de root): se usa {defaults.python}")

    idle = data.get("idle_timeout_s", defaults.idle_timeout_s)
    if isinstance(idle, bool) or not isinstance(idle, int) or not 0 <= idle <= 86400:
        warnings.append("idle_timeout_s no válido")
        idle = defaults.idle_timeout_s

    config = Config(
        mode=mode,
        health_url=health_url,
        updates_base_url=updates,
        opt_dir=opt_dir,
        python=python,
        idle_timeout_s=idle,
    )
    return config, warnings


def build_context(config: Config, *, serving: bool, paths: Paths | None = None) -> Context:
    paths = paths or Paths()
    return Context(
        config=config,
        runner=SubprocessRunner(),
        jobs=JobManager(paths.state_dir),
        paths=paths,
        public_key_pem=RELEASE_PUBLIC_KEY_PEM,
        serving=serving,
    )


# ---------------------------------------------------------------------------
# Despacho
# ---------------------------------------------------------------------------


def _ok(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"request_id": request_id, "ok": True, "result": result}


def _error(request_id: Any, code: str, message: str) -> dict[str, Any]:
    return {"request_id": request_id, "ok": False, "error": {"code": code, "message": message}}


def _request_id(value: Any) -> str | int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise CommandError("invalid_json", "request_id no válido")
    if isinstance(value, int) and abs(value) < 2**53:
        return value
    if isinstance(value, str) and _REQUEST_ID_RE.fullmatch(value):
        return value
    raise CommandError("invalid_json", "request_id no válido")


def _clip(text: str, limit: int = 64) -> str:
    text = re.sub(r"[^\x20-\x7e]", "?", text)
    return text if len(text) <= limit else text[:limit] + "…"


def describe_args(args: dict[str, Any], secret: frozenset[str]) -> str:
    """Resumen de los argumentos para el registro: sin secretos y acotado."""

    def redact(value: Any, depth: int = 0) -> Any:
        if depth > 3:
            return "…"
        if isinstance(value, dict):
            return {
                str(k): ("***" if k in secret else redact(v, depth + 1))
                for k, v in list(value.items())[:20]
            }
        if isinstance(value, list):
            items = [redact(v, depth + 1) for v in value[:10]]
            if len(value) > 10:
                items.append(f"… ({len(value)} en total)")
            return items
        if isinstance(value, str):
            return _clip(value)
        return value

    text = json.dumps(redact(args), ensure_ascii=True, sort_keys=True)
    return text if len(text) <= 400 else text[:400] + "…"


def dispatch(ctx: Context, raw: bytes | str, *, peer: str = "-") -> dict[str, Any]:
    started = time.monotonic()
    request_id: Any = None
    name = "-"
    args_text = "{}"
    try:
        try:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            request = json.loads(text)
        except (UnicodeDecodeError, ValueError) as exc:
            raise CommandError("invalid_json", "la petición no es JSON válido") from exc
        if not isinstance(request, dict):
            raise CommandError("invalid_json", "la petición debe ser un objeto JSON")
        request_id = _request_id(request.get("request_id"))
        unknown = sorted(str(k) for k in request if k not in REQUEST_KEYS)
        if unknown:
            raise CommandError("invalid_json", f"campo desconocido: {_clip(', '.join(unknown))}")
        cmd = request.get("cmd")
        if not isinstance(cmd, str) or not cmd:
            raise CommandError("invalid_json", "falta cmd")
        name = _clip(cmd)
        command = REGISTRY.get(cmd)
        if command is None:
            raise CommandError("unknown_command", f"comando desconocido: {name}")
        args = request.get("args", {})
        if args is None:
            args = {}
        if not isinstance(args, dict):
            raise CommandError("invalid_args", "args debe ser un objeto")
        args_text = describe_args(args, command.secret_args)
        if ctx.mode == "shared" and not command.shared_ok:
            raise CommandError(
                "not_allowed_in_shared_mode", f"{cmd} no se permite en modo compartido"
            )
        if command.exclusive:
            running = ctx.jobs.running("update")
            if running is not None:
                raise CommandError("busy", f"hay una actualización en curso ({running.id})")
        with deadline(COMMAND_TIMEOUT_S):
            result = command.handler(ctx, args)
        response = _ok(request_id, result)
    except CommandError as exc:
        response = _error(request_id, exc.code, exc.message)
    except Exception:
        log.exception("error interno en %s", name)
        response = _error(request_id, "command_failed", "error interno de privd (ver el registro)")
    elapsed_ms = (time.monotonic() - started) * 1000
    if response["ok"]:
        outcome = "ok"
    else:
        outcome = f"error {response['error']['code']}: {response['error']['message']}"
    log.info(
        "cmd=%s request_id=%s peer=%s args=%s -> %s (%.0f ms)",
        name,
        _clip(str(request_id)),
        peer,
        args_text,
        outcome,
        elapsed_ms,
    )
    return response


# ---------------------------------------------------------------------------
# Servidor
# ---------------------------------------------------------------------------


class RequestTooLong(Exception):
    pass


def systemd_listen_socket() -> socket.socket | None:
    """Socket heredado de systemd (LISTEN_FDS/LISTEN_PID), o None si no hay."""
    fds = os.environ.get("LISTEN_FDS")
    pid = os.environ.get("LISTEN_PID")
    if not fds or not pid:
        return None
    try:
        if int(pid) != os.getpid() or int(fds) < 1:
            return None
    except ValueError:
        return None
    for var in ("LISTEN_FDS", "LISTEN_PID", "LISTEN_FDNAMES"):
        os.environ.pop(var, None)
    sock = socket.fromfd(SD_LISTEN_FDS_START, socket.AF_UNIX, socket.SOCK_STREAM)
    os.close(SD_LISTEN_FDS_START)
    return sock


def bind_socket(path: Path) -> socket.socket:
    """Abre el socket sin systemd (pruebas y desarrollo): root:meshbox 0660 si se puede."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(FileNotFoundError):
        if stat.S_ISSOCK(os.lstat(path).st_mode):
            path.unlink()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old = os.umask(0o117)
    try:
        sock.bind(str(path))
    finally:
        os.umask(old)
    if os.geteuid() == 0:
        try:
            import grp

            os.chown(path, 0, grp.getgrnam("meshbox").gr_gid)
        except (KeyError, OSError) as exc:
            log.warning("no se pudo asignar el grupo meshbox al socket: %s", exc)
    sock.listen(16)
    return sock


def peer_credentials(conn: socket.socket) -> tuple[int, int, int] | None:
    option = getattr(socket, "SO_PEERCRED", None)
    if option is None:
        return None
    try:
        raw = conn.getsockopt(socket.SOL_SOCKET, option, struct.calcsize("3i"))
    except OSError:
        return None
    pid, uid, gid = struct.unpack("3i", raw)
    return pid, uid, gid


def peer_allowed(ctx: Context, peer: tuple[int, int, int] | None) -> bool:
    if peer is None:
        return True  # sin SO_PEERCRED decide el permiso del socket (0660 root:meshbox)
    _pid, uid, gid = peer
    if uid in (0, os.geteuid()):
        return True
    ids = ctx.owner.user_ids("meshbox")
    return ids is not None and (uid == ids[0] or gid == ids[1])


def read_request(conn: socket.socket, limit: int = MAX_REQUEST_BYTES) -> bytes:
    buffer = bytearray()
    while b"\n" not in buffer:
        chunk = conn.recv(65536)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > limit:
            raise RequestTooLong
    line = bytes(buffer).split(b"\n", 1)[0]
    return line.rstrip(b"\r")


def handle_connection(ctx: Context, conn: socket.socket) -> None:
    with conn:
        conn.settimeout(CONNECTION_TIMEOUT_S)
        peer = peer_credentials(conn)
        peer_text = f"pid={peer[0]},uid={peer[1]}" if peer else "-"
        if not peer_allowed(ctx, peer):
            log.warning("conexión rechazada de %s", peer_text)
            return
        try:
            raw = read_request(conn)
        except RequestTooLong:
            response = _error(None, "invalid_json", "petición demasiado larga")
        except OSError as exc:
            log.warning("conexión sin petición completa (%s): %s", peer_text, exc)
            return
        else:
            response = dispatch(ctx, raw, peer=peer_text)
        try:
            conn.sendall(json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\n")
        except OSError as exc:
            log.warning("no se pudo enviar la respuesta (%s): %s", peer_text, exc)


def serve(ctx: Context, sock: socket.socket, idle_timeout: float) -> int:
    stopping = {"flag": False}

    def on_signal(signum: int, _frame: object) -> None:
        stopping["flag"] = True

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, on_signal)
        signal.signal(signal.SIGINT, on_signal)
    sock.setblocking(False)
    last_activity = time.monotonic()
    log.info(
        "meshbox-privd %s escuchando (modo %s, inactividad %ss)",
        PRIVD_VERSION,
        ctx.mode,
        idle_timeout,
    )
    while not stopping["flag"]:
        try:
            ready, _, _ = select.select([sock], [], [], 1.0)
        except InterruptedError:
            continue
        if ready:
            try:
                conn, _ = sock.accept()
            except (BlockingIOError, InterruptedError):
                continue
            handle_connection(ctx, conn)
            last_activity = time.monotonic()
        if ctx.jobs.active():
            last_activity = time.monotonic()
            continue
        if ctx.exit_requested:
            log.info("saliendo para cargar el código nuevo (el socket sigue activo)")
            break
        if idle_timeout > 0 and time.monotonic() - last_activity >= idle_timeout:
            log.info("sin actividad ni trabajos: saliendo")
            break
    return 0


# ---------------------------------------------------------------------------
# Línea de comandos
# ---------------------------------------------------------------------------


class JournalFormatter(logging.Formatter):
    """Prefijos <N> de prioridad que journald interpreta (SyslogLevelPrefix)."""

    LEVELS: ClassVar[dict[int, int]] = {
        logging.DEBUG: 7,
        logging.INFO: 6,
        logging.WARNING: 4,
        logging.ERROR: 3,
        logging.CRITICAL: 2,
    }

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        prefix = f"<{self.LEVELS.get(record.levelno, 6)}>"
        return "\n".join(prefix + line for line in text.splitlines())


def setup_logging(*, journal: bool) -> None:
    handler = logging.StreamHandler(sys.stdout if journal else sys.stderr)
    if journal:
        handler.setFormatter(JournalFormatter("%(name)s: %(message)s"))
    else:
        handler.setFormatter(logging.Formatter("privd %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)


def run_call(ctx: Context, data: bytes) -> tuple[dict[str, Any], int]:
    """Modo de una sola vez: misma validación y despacho que el socket."""
    if len(data) > MAX_REQUEST_BYTES:
        return _error(None, "invalid_json", "petición demasiado larga"), 1
    response = dispatch(ctx, data.strip(), peer="cli")
    code = 0 if response["ok"] else 1
    result = response.get("result")
    if response["ok"] and isinstance(result, dict) and isinstance(result.get("job"), str):
        job_id = result["job"]
        ctx.jobs.wait(job_id)
        final = ctx.jobs.get(job_id)
        if final is not None:
            response["result"] = final
            if final.get("state") != "succeeded":
                code = 1
    return response, code


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="meshbox_privd", description="meshbox-privd")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    sub = parser.add_subparsers(dest="action", required=True)
    serve_p = sub.add_parser("serve", help="atiende el socket (lo usa systemd)")
    serve_p.add_argument("--socket", type=Path, default=DEFAULT_SOCKET)
    serve_p.add_argument("--idle-timeout", type=float, default=None)
    sub.add_parser("call", help="ejecuta una petición JSON leída de stdin")
    sub.add_parser("version", help="muestra la versión")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.action == "version":
        print(PRIVD_VERSION)
        return 0
    serving = args.action == "serve"
    setup_logging(journal=serving)
    config, warnings = load_config(args.config)
    for warning in warnings:
        log.warning("%s", warning)
    ctx = build_context(config, serving=serving)
    if serving:
        if os.geteuid() == 0:
            with contextlib.suppress(OSError, CommandError):
                ensure_dir(ctx.paths.state_dir, 0o700)
        ctx.jobs.load_persisted()
        sock = systemd_listen_socket()
        own_socket = sock is None
        if sock is None:
            sock = bind_socket(args.socket)
        idle = args.idle_timeout if args.idle_timeout is not None else config.idle_timeout_s
        try:
            return serve(ctx, sock, idle)
        finally:
            sock.close()
            if own_socket:
                with contextlib.suppress(OSError):
                    args.socket.unlink()
    response, code = run_call(ctx, sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1))
    sys.stdout.buffer.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
    sys.stdout.flush()
    return code


if __name__ == "__main__":
    sys.exit(main())
