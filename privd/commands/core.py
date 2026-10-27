"""Piezas comunes de meshbox-privd: contexto, errores, ejecutor de procesos y validaciones.

Solo biblioteca estándar de Python (>= 3.11). Este módulo no ejecuta nada al importarse.
"""

from __future__ import annotations

import contextlib
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

# Lo reemplaza scripts/build-release.py con la versión del release al armar el paquete.
PRIVD_VERSION = "0.0.0-dev"

MODES = ("shared", "appliance")

# Tiempo máximo de un comando sincrónico (13.3).
COMMAND_TIMEOUT_S = 120.0

SAFE_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

ERROR_CODES = (
    "invalid_json",
    "unknown_command",
    "invalid_args",
    "not_allowed_in_shared_mode",
    "command_failed",
    "timeout",
    "busy",
)

Args = Mapping[str, Any]
Result = dict[str, Any]


class CommandError(Exception):
    """Error con código del protocolo (Anexo D). El mensaje nunca lleva secretos."""

    def __init__(self, code: str, message: str) -> None:
        if code not in ERROR_CODES:
            raise ValueError(f"código de error desconocido: {code}")
        super().__init__(message)
        self.code = code
        self.message = message


def invalid(message: str) -> CommandError:
    return CommandError("invalid_args", message)


def failed(message: str) -> CommandError:
    return CommandError("command_failed", message)


# ---------------------------------------------------------------------------
# Configuración y rutas
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Config:
    """Contenido de /etc/meshbox-privd/privd.toml ya validado."""

    mode: str = "shared"
    health_url: str = ""
    updates_base_url: str = ""
    opt_dir: Path = Path("/opt/meshbox")
    python: str = "/usr/bin/python3"
    idle_timeout_s: int = 600

    @property
    def effective_health_url(self) -> str:
        if self.health_url:
            return self.health_url
        port = 8091 if self.mode == "shared" else 8081
        return f"http://127.0.0.1:{port}/api/v1/health"


@dataclass
class Paths:
    """Rutas del sistema que toca privd. Las pruebas las redirigen a un directorio temporal."""

    mosquitto_dir: Path = Path("/etc/mosquitto")
    mosquitto_passwd: Path = Path("/etc/mosquitto/passwd")
    mosquitto_acl: Path = Path("/etc/mosquitto/acl")
    mosquitto_conf_d: Path = Path("/etc/mosquitto/conf.d")
    tunnel_dir: Path = Path("/etc/meshbox-tunnel")
    nm_connections_dir: Path = Path("/etc/NetworkManager/system-connections")
    nm_dnsmasq_shared_dir: Path = Path("/etc/NetworkManager/dnsmasq-shared.d")
    boot_setup_file: Path = Path("/boot/firmware/meshbox-setup.txt")
    sys_class_net: Path = Path("/sys/class/net")
    zoneinfo_dir: Path = Path("/usr/share/zoneinfo")
    etc_hosts: Path = Path("/etc/hosts")
    etc_hostname: Path = Path("/etc/hostname")
    cloud_cfg_d: Path = Path("/etc/cloud/cloud.cfg.d")
    proc_dir: Path = Path("/proc")
    device_tree_model: Path = Path("/proc/device-tree/model")
    os_release: Path = Path("/etc/os-release")
    systemd_system_dir: Path = Path("/etc/systemd/system")
    journald_conf_d: Path = Path("/etc/systemd/journald.conf.d")
    privd_lib_dir: Path = Path("/usr/local/lib/meshbox-privd")
    firstboot_script: Path = Path("/usr/local/sbin/meshbox-firstboot")
    state_dir: Path = Path("/var/lib/meshbox-privd")
    meshbox_config: Path = Path("/etc/meshbox/config.toml")
    meshbox_var_dir: Path = Path("/var/lib/meshbox")


@dataclass
class Bins:
    """Rutas absolutas de los binarios (Debian 12/13 con /usr unificado)."""

    systemctl: str = "/usr/bin/systemctl"
    journalctl: str = "/usr/bin/journalctl"
    nmcli: str = "/usr/bin/nmcli"
    hostnamectl: str = "/usr/bin/hostnamectl"
    timedatectl: str = "/usr/bin/timedatectl"
    mosquitto_passwd: str = "/usr/bin/mosquitto_passwd"  # noqa: S105 - ruta, no una clave
    openssl: str = "/usr/bin/openssl"
    runuser: str = "/usr/sbin/runuser"
    sqlite3: str = "/usr/bin/sqlite3"


# ---------------------------------------------------------------------------
# Ejecución de procesos
# ---------------------------------------------------------------------------


@dataclass
class ProcResult:
    returncode: int
    stdout: bytes = b""
    stderr: bytes = b""

    @property
    def out(self) -> str:
        return self.stdout.decode("utf-8", "replace")

    @property
    def err(self) -> str:
        return self.stderr.decode("utf-8", "replace")


class Runner(Protocol):
    def run(
        self,
        argv: Sequence[str],
        *,
        input: bytes | None = None,
        timeout: float = COMMAND_TIMEOUT_S,
        env: Mapping[str, str] | None = None,
        umask: int | None = None,
        cwd: str | None = None,
    ) -> ProcResult: ...


_deadline = threading.local()


@contextlib.contextmanager
def deadline(seconds: float) -> Iterator[None]:
    """Fija el tiempo máximo del comando en curso (solo para el hilo actual)."""
    previous = getattr(_deadline, "value", None)
    _deadline.value = time.monotonic() + seconds
    try:
        yield
    finally:
        _deadline.value = previous


def remaining_time(default: float) -> float:
    value: float | None = getattr(_deadline, "value", None)
    if value is None:
        return default
    return min(default, value - time.monotonic())


def base_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Entorno mínimo y predecible para los procesos hijos (salida sin traducir)."""
    env = {"PATH": SAFE_PATH, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    if extra:
        env.update(extra)
    return env


class SubprocessRunner:
    """Ejecutor real: listas de argumentos, rutas absolutas, nunca shell."""

    def run(
        self,
        argv: Sequence[str],
        *,
        input: bytes | None = None,
        timeout: float = COMMAND_TIMEOUT_S,
        env: Mapping[str, str] | None = None,
        umask: int | None = None,
        cwd: str | None = None,
    ) -> ProcResult:
        args = [str(a) for a in argv]
        if not args or not args[0].startswith("/"):
            raise failed("el binario debe ir con ruta absoluta")
        limit = remaining_time(timeout)
        name = args[0].rsplit("/", 1)[-1]
        if limit <= 0:
            raise CommandError("timeout", f"sin tiempo para ejecutar {name}")
        kwargs: dict[str, Any] = {}
        if umask is not None and os.name == "posix":
            kwargs["umask"] = umask
        try:
            proc = subprocess.run(
                args,
                input=input,
                stdin=None if input is not None else subprocess.DEVNULL,
                capture_output=True,
                timeout=limit,
                env=base_env(env),
                cwd=cwd,
                close_fds=True,
                check=False,
                **kwargs,
            )
        except subprocess.TimeoutExpired as exc:
            raise CommandError("timeout", f"{name} no terminó en {limit:.0f} s") from exc
        except FileNotFoundError as exc:
            raise failed(f"no se encontró {args[0]}") from exc
        except OSError as exc:
            raise failed(f"no se pudo ejecutar {name}: {exc.strerror}") from exc
        return ProcResult(proc.returncode, proc.stdout, proc.stderr)


_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def clean_text(text: str, limit: int = 400) -> str:
    """Recorta y quita caracteres de control (para mensajes de error y registros)."""
    text = _CONTROL.sub("?", text.strip())
    if len(text) > limit:
        text = "…" + text[-limit:]
    return text


def run_checked(
    ctx: Context,
    argv: Sequence[str],
    *,
    what: str | None = None,
    **kwargs: Any,
) -> ProcResult:
    """Ejecuta y falla con `command_failed` si el código de salida no es 0."""
    result = ctx.runner.run(argv, **kwargs)
    if result.returncode != 0:
        label = what or str(argv[0]).rsplit("/", 1)[-1]
        detail = clean_text(result.err or result.out)
        message = f"{label} falló (código {result.returncode})"
        if detail:
            message += f": {detail}"
        raise failed(message)
    return result


# ---------------------------------------------------------------------------
# Dueños de archivos
# ---------------------------------------------------------------------------


class OwnerOps:
    """Cambia dueño por nombre. En las pruebas se reemplaza por una versión que registra."""

    def ids(self, user: str, group: str) -> tuple[int, int]:
        import grp
        import pwd

        try:
            uid = pwd.getpwnam(user).pw_uid
        except KeyError as exc:
            raise failed(f"no existe el usuario {user}") from exc
        try:
            gid = grp.getgrnam(group).gr_gid
        except KeyError as exc:
            raise failed(f"no existe el grupo {group}") from exc
        return uid, gid

    def chown(self, path: Path, user: str, group: str) -> None:
        uid, gid = self.ids(user, group)
        os.chown(path, uid, gid, follow_symlinks=False)

    def user_ids(self, user: str) -> tuple[int, int] | None:
        """(uid, gid principal) del usuario o None si no existe."""
        try:
            import pwd
        except ImportError:
            return None
        try:
            entry = pwd.getpwnam(user)
        except KeyError:
            return None
        return entry.pw_uid, entry.pw_gid


# ---------------------------------------------------------------------------
# Contexto
# ---------------------------------------------------------------------------


def _default_http_get(url: str, timeout: float) -> tuple[int, bytes]:
    import urllib.error
    import urllib.request

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    headers = {"User-Agent": f"meshbox-privd/{PRIVD_VERSION}"}
    request = urllib.request.Request(url, headers=headers)  # noqa: S310 - URL local validada
    try:
        with opener.open(request, timeout=timeout) as resp:
            return resp.status, resp.read(65536)
    except urllib.error.HTTPError as exc:
        return exc.code, b""


@dataclass
class Context:
    config: Config
    runner: Runner
    jobs: Any  # JobManager (evita importación circular)
    paths: Paths = field(default_factory=Paths)
    bins: Bins = field(default_factory=Bins)
    owner: OwnerOps = field(default_factory=OwnerOps)
    public_key_pem: str = ""
    http_get: Callable[[str, float], tuple[int, bytes]] = _default_http_get
    sleep: Callable[[float], None] = time.sleep
    monotonic: Callable[[], float] = time.monotonic
    wifi_iface: str = "wlan0"
    serving: bool = False
    exit_requested: bool = False

    @property
    def mode(self) -> str:
        return self.config.mode


Handler = Callable[[Context, Args], Result]


@dataclass(frozen=True)
class Command:
    """Entrada del registro de comandos.

    - `shared_ok`: se permite en modo `shared` (ADR 0004).
    - `secret_args`: argumentos que nunca se registran.
    - `exclusive`: no se ejecuta mientras haya una actualización en curso.
    """

    handler: Handler
    shared_ok: bool = True
    secret_args: frozenset[str] = frozenset()
    exclusive: bool = False


# ---------------------------------------------------------------------------
# Validaciones
# ---------------------------------------------------------------------------


def check_keys(args: Args, required: Sequence[str] = (), optional: Sequence[str] = ()) -> None:
    """Exige exactamente las claves esperadas: ni faltantes ni desconocidas."""
    if not isinstance(args, Mapping):
        raise invalid("args debe ser un objeto")
    missing = [k for k in required if k not in args]
    if missing:
        raise invalid(f"falta {', '.join(missing)}")
    allowed = set(required) | set(optional)
    unknown = sorted(k for k in args if k not in allowed)
    if unknown:
        raise invalid(f"argumento desconocido: {', '.join(str(k) for k in unknown)}")


def get_str(args: Args, key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str):
        raise invalid(f"{key} debe ser texto")
    return value


def get_bool(args: Args, key: str, default: bool = False) -> bool:
    if key not in args:
        return default
    value = args[key]
    if not isinstance(value, bool):
        raise invalid(f"{key} debe ser verdadero o falso")
    return value


def get_int(args: Args, key: str, *, minimum: int, maximum: int, default: int | None = None) -> int:
    if key not in args:
        if default is None:
            raise invalid(f"falta {key}")
        return default
    value = args[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise invalid(f"{key} debe ser un número entero")
    if not minimum <= value <= maximum:
        raise invalid(f"{key} debe estar entre {minimum} y {maximum}")
    return value


USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,31}$")
VERSION_RE = re.compile(r"^\d{1,6}\.\d{1,6}\.\d{1,6}$")


def validate_username(value: Any) -> str:
    if not isinstance(value, str) or not USERNAME_RE.fullmatch(value):
        raise invalid("username no válido")
    return value


def validate_version(value: Any) -> str:
    if not isinstance(value, str) or not VERSION_RE.fullmatch(value):
        raise invalid("version no válida (se espera X.Y.Z)")
    return value


def version_key(version: str) -> tuple[int, int, int]:
    major, minor, patch = (int(p) for p in version.split("."))
    return major, minor, patch


# ---------------------------------------------------------------------------
# Archivos
# ---------------------------------------------------------------------------


def fsync_dir(path: Path) -> None:
    if os.name != "posix":
        return
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write(
    ctx: Context,
    path: Path,
    data: bytes,
    *,
    mode: int,
    owner: tuple[str, str] | None = None,
) -> None:
    """Escribe en un temporal del mismo directorio y lo reemplaza con os.replace.

    El temporal nace 0600 (mkstemp), así que el contenido nunca queda expuesto con permisos
    más amplios que los finales.
    """
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        tmp.chmod(mode)
        if owner is not None:
            ctx.owner.chown(tmp, owner[0], owner[1])
        tmp.replace(path)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
    fsync_dir(path.parent)


def ensure_dir(path: Path, mode: int) -> None:
    """Crea el directorio si falta y le fija los permisos (sin seguir enlaces)."""
    if path.is_symlink():
        raise failed(f"{path} es un enlace simbólico")
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(mode)


def read_text_limited(path: Path, limit: int = 1 << 20) -> str:
    with open(path, "rb") as fh:
        return fh.read(limit).decode("utf-8", "replace")


def parse_key_values(text: str, sep: str = "=") -> dict[str, str]:
    """Parsea líneas `Clave=valor` (systemctl show, timedatectl show, os-release)."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        if sep not in line:
            continue
        key, value = line.split(sep, 1)
        result[key.strip()] = value.strip()
    return result


def unit_status(ctx: Context, unit: str) -> Result:
    """Estado resumido de una unidad systemd (para *.status)."""
    props = (
        "Id,LoadState,ActiveState,SubState,UnitFileState,MainPID,NRestarts,Result,"
        "ActiveEnterTimestamp"
    )
    res = run_checked(
        ctx,
        [ctx.bins.systemctl, "show", unit, "--timestamp=unix", f"--property={props}"],
        what="systemctl show",
    )
    kv = parse_key_values(res.out)

    def as_int(value: str | None) -> int | None:
        try:
            return int(value) if value not in (None, "") else None
        except ValueError:
            return None

    since_raw = kv.get("ActiveEnterTimestamp", "")
    since = as_int(since_raw[1:]) if since_raw.startswith("@") else None
    pid = as_int(kv.get("MainPID"))
    return {
        "unit": unit,
        "load": kv.get("LoadState") or None,
        "active": kv.get("ActiveState") or None,
        "sub": kv.get("SubState") or None,
        "enabled": kv.get("UnitFileState") or None,
        "pid": pid if pid else None,
        "restarts": as_int(kv.get("NRestarts")),
        "result": kv.get("Result") or None,
        "since": since,
    }


def is_linux() -> bool:
    return sys.platform.startswith("linux")
