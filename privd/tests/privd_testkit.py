"""Utilidades de prueba de privd: ejecutor falso, reloj falso y contexto con rutas temporales."""

from __future__ import annotations

import base64
import hashlib
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from commands.core import Bins, Config, Context, Paths, ProcResult
from commands.jobs import JobManager

Response = ProcResult | Callable[["Call"], ProcResult]


@dataclass
class Call:
    argv: list[str]
    input: bytes | None = None
    timeout: float = 0.0
    env: dict[str, str] | None = None
    umask: int | None = None


class FakeRunner:
    """Ejecutor de procesos falso: registra llamadas y responde según prefijos de argv."""

    def __init__(self) -> None:
        self.calls: list[Call] = []
        self._handlers: list[tuple[list[str], Response]] = []
        self.default = ProcResult(0, b"", b"")
        self.fallback: Callable[[Call], ProcResult] | None = None

    def on(self, prefix: Sequence[str], response: Response) -> None:
        """Registra una respuesta; ante varias coincidencias gana la última registrada."""
        self._handlers.append(([str(p) for p in prefix], response))

    def run(
        self,
        argv: Sequence[str],
        *,
        input: bytes | None = None,
        timeout: float = 120.0,
        env: Any = None,
        umask: int | None = None,
        cwd: str | None = None,
    ) -> ProcResult:
        call = Call([str(a) for a in argv], input, timeout, dict(env) if env else None, umask)
        self.calls.append(call)
        for prefix, response in reversed(self._handlers):
            if call.argv[: len(prefix)] == prefix:
                return response(call) if callable(response) else response
        if self.fallback is not None:
            return self.fallback(call)
        return self.default

    def argvs(self, prefix: Sequence[str] = ()) -> list[list[str]]:
        prefix = [str(p) for p in prefix]
        return [c.argv for c in self.calls if c.argv[: len(prefix)] == prefix]

    def all_text(self) -> str:
        """Todo lo que pasó por argv, stdin y entorno (para buscar secretos filtrados)."""
        parts = []
        for call in self.calls:
            parts.extend(call.argv)
            if call.input:
                parts.append(call.input.decode("utf-8", "replace"))
            if call.env:
                parts.extend(f"{k}={v}" for k, v in call.env.items())
        return "\n".join(parts)


def ok(stdout: str | bytes = b"", stderr: str | bytes = b"") -> ProcResult:
    out = stdout.encode() if isinstance(stdout, str) else stdout
    err = stderr.encode() if isinstance(stderr, str) else stderr
    return ProcResult(0, out, err)


def fail(code: int = 1, stderr: str = "error", stdout: str = "") -> ProcResult:
    return ProcResult(code, stdout.encode(), stderr.encode())


def fake_mosquitto_passwd(call: Call) -> ProcResult:
    """Simula `mosquitto_passwd -U <archivo>`: reemplaza cada clave por un hash $7$."""
    assert call.argv[1] == "-U"
    path = Path(call.argv[2])
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        user, password = line.split(":", 1)
        salt = base64.b64encode(hashlib.sha256(user.encode()).digest()[:12]).decode()
        digest = base64.b64encode(hashlib.sha512(password.encode()).digest()).decode()
        lines.append(f"{user}:$7$101${salt}${digest}")
    # mosquitto_passwd deja un respaldo junto al archivo y luego lo borra; se imita el respaldo
    # para comprobar que privd limpia el directorio temporal.
    (path.parent / f"{path.name}.backup.ABC123").write_text("respaldo")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ok()


class RecordingOwner:
    def __init__(self, meshbox_ids: tuple[int, int] | None = None) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.meshbox_ids = meshbox_ids

    def ids(self, user: str, group: str) -> tuple[int, int]:
        return 0, 0

    def chown(self, path: Path, user: str, group: str) -> None:
        self.calls.append((Path(path).name, user, group))

    def user_ids(self, user: str) -> tuple[int, int] | None:
        return self.meshbox_ids if user == "meshbox" else None


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make_paths(root: Path) -> Paths:
    paths = Paths(
        mosquitto_dir=root / "etc/mosquitto",
        mosquitto_passwd=root / "etc/mosquitto/passwd",
        mosquitto_acl=root / "etc/mosquitto/acl",
        mosquitto_conf_d=root / "etc/mosquitto/conf.d",
        tunnel_dir=root / "etc/meshbox-tunnel",
        nm_connections_dir=root / "etc/NetworkManager/system-connections",
        nm_dnsmasq_shared_dir=root / "etc/NetworkManager/dnsmasq-shared.d",
        boot_setup_file=root / "boot/firmware/meshbox-setup.txt",
        sys_class_net=root / "sys/class/net",
        zoneinfo_dir=root / "usr/share/zoneinfo",
        etc_hosts=root / "etc/hosts",
        etc_hostname=root / "etc/hostname",
        cloud_cfg_d=root / "etc/cloud/cloud.cfg.d",
        proc_dir=root / "proc",
        device_tree_model=root / "proc/device-tree/model",
        os_release=root / "etc/os-release",
        systemd_system_dir=root / "etc/systemd/system",
        journald_conf_d=root / "etc/systemd/journald.conf.d",
        privd_lib_dir=root / "usr/local/lib/meshbox-privd",
        firstboot_script=root / "usr/local/sbin/meshbox-firstboot",
        state_dir=root / "var/lib/meshbox-privd",
        meshbox_config=root / "etc/meshbox/config.toml",
        meshbox_var_dir=root / "var/lib/meshbox",
    )
    for directory in (
        paths.mosquitto_dir,
        paths.mosquitto_conf_d,
        paths.nm_connections_dir,
        paths.systemd_system_dir,
        paths.firstboot_script.parent,
        paths.meshbox_var_dir / "backups",
        paths.meshbox_config.parent,
        paths.etc_hosts.parent,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    return paths


@dataclass
class Env:
    root: Path
    ctx: Context
    runner: FakeRunner
    clock: FakeClock
    owner: RecordingOwner
    http_responses: list[tuple[int, bytes]] = field(default_factory=list)


def make_env(
    root: Path,
    *,
    mode: str = "appliance",
    updates_base_url: str = "",
    serving: bool = False,
    public_key_pem: str = "",
) -> Env:
    paths = make_paths(root)
    runner = FakeRunner()
    clock = FakeClock()
    owner = RecordingOwner()
    config = Config(
        mode=mode,
        health_url="http://127.0.0.1:8091/api/v1/health",
        updates_base_url=updates_base_url,
        opt_dir=root / "opt/meshbox",
        python="/usr/bin/python3",
    )
    ctx = Context(
        config=config,
        runner=runner,
        jobs=JobManager(paths.state_dir),
        paths=paths,
        bins=Bins(),
        owner=owner,  # type: ignore[arg-type]
        public_key_pem=public_key_pem,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        serving=serving,
    )
    env = Env(root=root, ctx=ctx, runner=runner, clock=clock, owner=owner)

    def http_get(url: str, timeout: float) -> tuple[int, bytes]:
        if env.http_responses:
            return env.http_responses.pop(0)
        raise ConnectionRefusedError("sin respuesta")

    ctx.http_get = http_get
    return env


def find_openssl() -> str | None:
    """OpenSSL 3 para las pruebas de firma (en Windows, el de Git)."""
    found = shutil.which("openssl")
    candidates = [found] if found else []
    candidates += [
        r"C:\Program Files\Git\mingw64\bin\openssl.exe",
        r"C:\Program Files\Git\usr\bin\openssl.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            try:
                out = subprocess.run(
                    [candidate, "version"], capture_output=True, text=True, check=False
                ).stdout
            except OSError:
                continue
            if out.startswith("OpenSSL 3"):
                return candidate
    return None
