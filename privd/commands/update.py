"""Actualizaciones firmadas con vuelta atrás automática (13.3, 23.5 y 28.3).

`update.apply` corre como trabajo en segundo plano:

1. descarga `SHA256SUMS`, `SHA256SUMS.sig` y el paquete desde `updates_base_url/v<versión>/`
   a `<opt_dir>/.staging/` (directorio root 0700 en la SD: nunca /tmp, que es RAM, ni un
   directorio escribible por `meshbox`);
2. verifica la firma Ed25519 con OpenSSL y la clave pública embebida más abajo, y la suma;
3. descomprime en `<opt_dir>/releases/<v>`, crea el entorno con el Python del sistema e instala
   las ruedas incluidas sin red;
4. respalda la base (`meshbox backup create --suffix pre-<v>`, como usuario meshbox);
5. instala privd, unidades y configuración de Mosquitto del paquete, cambia `current` de forma
   atómica y reinicia meshbox;
6. espera `GET /api/v1/health` 90 s; si falla, vuelve a la versión anterior (y a la base previa si
   hubo migración) y la reinicia;
7. conserva 2 versiones anteriores; al final privd sale para que el socket lo vuelva a levantar
   con el código nuevo.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets
import shutil
import tarfile
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .core import (
    PRIVD_VERSION,
    VERSION_RE,
    Args,
    Command,
    CommandError,
    Context,
    ProcResult,
    Result,
    atomic_write,
    check_keys,
    ensure_dir,
    failed,
    fsync_dir,
    get_str,
    invalid,
    run_checked,
    validate_version,
    version_key,
)
from .jobs import JOB_ID_RE, Job

log = logging.getLogger("privd.update")

# Clave pública Ed25519 de los releases. Para rotarla ver SECURITY.md (sección de claves):
# debe coincidir con MESHBOX_RELEASE_PUBKEY de deploy/install.sh.
RELEASE_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAFcM6F5vQWKziqfj+rf1S0ePm+z6zD5VNb8Pd3fDD9VE=
-----END PUBLIC KEY-----
"""

TARBALL_TEMPLATE = "meshbox-{version}-linux-aarch64.tar.gz"
SUMS_NAME = "SHA256SUMS"
SIG_NAME = "SHA256SUMS.sig"
SIGNATURE_SIZE = 64
MAX_TARBALL = 1 << 30
MAX_SUMS = 1 << 16
HEALTH_TIMEOUT_S = 90.0
HEALTH_INTERVAL_S = 3.0
KEEP_PREVIOUS = 2
INSTALLED_MARKER = ".meshbox-installed"
STATE_FILE = "update-state.json"
MESHBOX_USER = "meshbox"
MESHBOX_UNIT = "meshbox.service"

_SUMS_LINE = re.compile(r"^([0-9a-fA-F]{64}) [ *](.+)$")


# ---------------------------------------------------------------------------
# Disposición en disco
# ---------------------------------------------------------------------------


def releases_dir(ctx: Context) -> Path:
    return ctx.config.opt_dir / "releases"


def current_link(ctx: Context) -> Path:
    return ctx.config.opt_dir / "current"


def release_python(ctx: Context, version: str) -> Path:
    return releases_dir(ctx) / version / ".venv" / "bin" / "python"


def current_version(ctx: Context) -> str | None:
    try:
        target = current_link(ctx).readlink()
    except OSError:
        return None
    name = target.name
    return name if VERSION_RE.fullmatch(name) else None


def is_installed(ctx: Context, version: str) -> bool:
    base = releases_dir(ctx) / version
    return (base / INSTALLED_MARKER).is_file() and release_python(ctx, version).exists()


def release_versions(ctx: Context) -> list[str]:
    """Versiones con directorio en releases/ (instaladas o no), de menor a mayor."""
    base = releases_dir(ctx)
    if not base.is_dir():
        return []
    names = [p.name for p in base.iterdir() if p.is_dir() and VERSION_RE.fullmatch(p.name)]
    return sorted(names, key=version_key)


def installed_versions(ctx: Context) -> list[str]:
    return [v for v in release_versions(ctx) if is_installed(ctx, v)]


def read_state(ctx: Context) -> dict[str, Any]:
    try:
        data = json.loads((ctx.paths.state_dir / STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_state(ctx: Context, data: dict[str, Any]) -> None:
    ensure_dir(ctx.paths.state_dir, 0o700)
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=1).encode("utf-8")
    atomic_write(ctx, ctx.paths.state_dir / STATE_FILE, payload, mode=0o600)


def previous_version(ctx: Context, current: str | None) -> str | None:
    if current is None:
        return None
    state = read_state(ctx)
    candidate = state.get("previous") if state.get("current") == current else None
    if (
        isinstance(candidate, str)
        and VERSION_RE.fullmatch(candidate)
        and candidate != current
        and is_installed(ctx, candidate)
    ):
        return candidate
    lower = [v for v in installed_versions(ctx) if version_key(v) < version_key(current)]
    return lower[-1] if lower else None


def meshbox_paths(ctx: Context) -> tuple[Path, Path]:
    """Base y carpeta de respaldos según /etc/meshbox/config.toml (con valores por defecto).

    Solo se aceptan rutas dentro de /var/lib/meshbox: el archivo lo escribe el usuario meshbox.
    """
    var = ctx.paths.meshbox_var_dir
    db = var / "meshbox.db"
    backups = var / "backups"
    try:
        with open(ctx.paths.meshbox_config, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return db, backups
    paths = data.get("paths") if isinstance(data, dict) else None
    if isinstance(paths, dict):
        db = _safe_var_path(var, paths.get("db"), db)
        backups = _safe_var_path(var, paths.get("backups"), backups)
    return db, backups


def _safe_var_path(var: Path, value: object, default: Path) -> Path:
    if not isinstance(value, str) or not value.startswith("/") or ".." in value:
        return default
    path = Path(value)
    return path if path.is_relative_to(var) else default


# ---------------------------------------------------------------------------
# Descarga y verificación
# ---------------------------------------------------------------------------


def download(
    url: str,
    dest: Path,
    *,
    max_bytes: int,
    progress: Callable[[int, int | None], None] | None = None,
) -> int:
    name = url.rsplit("/", 1)[-1]
    request = urllib.request.Request(  # noqa: S310 - esquema validado en la configuración
        url, headers={"User-Agent": f"meshbox-privd/{PRIVD_VERSION}"}
    )
    size = 0
    try:
        # URL de privd.toml (root) validada: https, http o file.
        with urllib.request.urlopen(request, timeout=60) as resp:  # noqa: S310  # nosec B310
            length = resp.headers.get("Content-Length")
            total = int(length) if length and length.isdigit() else None
            if total is not None and total > max_bytes:
                raise failed(f"{name} es demasiado grande")
            with open(dest, "wb") as fh:
                while True:
                    chunk = resp.read(1 << 16)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        raise failed(f"{name} es demasiado grande")
                    fh.write(chunk)
                    if progress is not None:
                        progress(size, total)
    except urllib.error.HTTPError as exc:
        raise failed(f"la descarga de {name} devolvió HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise failed(f"no se pudo descargar {name}: {exc.reason}") from exc
    except (OSError, TimeoutError) as exc:
        raise failed(f"no se pudo descargar {name}: {exc}") from exc
    return size


def verify_signature(ctx: Context, sums: Path, signature: Path, workdir: Path) -> None:
    """Ed25519 pura sobre SHA256SUMS con `openssl pkeyutl -rawin` (28.3)."""
    if signature.stat().st_size != SIGNATURE_SIZE:
        raise failed("la firma no tiene 64 bytes (Ed25519)")
    pem = workdir / "release-public.pem"
    pem.write_text(ctx.public_key_pem, encoding="ascii")
    result = ctx.runner.run(
        [
            ctx.bins.openssl,
            "pkeyutl",
            "-verify",
            "-pubin",
            "-inkey",
            str(pem),
            "-rawin",
            "-in",
            str(sums),
            "-sigfile",
            str(signature),
        ],
        timeout=60,
    )
    if result.returncode != 0 or b"Signature Verified Successfully" not in result.stdout:
        raise failed("la firma de SHA256SUMS no es válida")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_sum(sums: Path, name: str) -> str:
    for line in sums.read_text(encoding="utf-8", errors="replace").splitlines():
        match = _SUMS_LINE.match(line.strip())
        if match and match.group(2) == name:
            return match.group(1).lower()
    raise failed(f"{name} no figura en SHA256SUMS")


def verify_checksum(sums: Path, file: Path, name: str) -> str:
    expected = expected_sum(sums, name)
    actual = sha256_file(file)
    if not hmac.compare_digest(actual, expected):
        raise failed(f"la suma SHA-256 de {name} no coincide")
    return actual


def safe_extract(tar_path: Path, dest: Path) -> None:
    try:
        with tarfile.open(tar_path, "r:gz") as tar:
            if hasattr(tarfile, "data_filter"):
                tar.extractall(dest, filter="data")
                return
            _extract_validated(tar, dest)  # pragma: no cover - Python sin PEP 706
    except (tarfile.TarError, EOFError, OSError) as exc:
        raise failed(f"el paquete está dañado o tiene rutas inseguras: {exc}") from exc


def _extract_validated(tar: tarfile.TarFile, dest: Path) -> None:  # pragma: no cover
    """Validación manual para Python 3.11 anterior a 3.11.4 (sin filtros de PEP 706)."""
    members = []
    for member in tar.getmembers():
        parts = Path(member.name).parts
        if member.name.startswith("/") or ".." in parts:
            raise tarfile.TarError(f"ruta insegura: {member.name}")
        if not (member.isfile() or member.isdir()):
            raise tarfile.TarError(f"entrada no permitida: {member.name}")
        member.mode &= 0o755
        members.append(member)
    # Miembros validados arriba: rutas relativas, solo archivos y carpetas, sin setuid.
    tar.extractall(dest, members=members)  # noqa: S202  # nosec B202


def check_layout(root: Path, version: str) -> None:
    version_file = root / "VERSION"
    try:
        found = version_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise failed("el paquete no tiene el archivo VERSION") from exc
    if found != version:
        raise failed(f"el paquete es de la versión {found}, no de {version}")
    for rel in ("wheels", "privd/meshbox_privd.py", "deploy/systemd/meshbox.service"):
        if not (root / rel).exists():
            raise failed(f"al paquete le falta {rel}")


# ---------------------------------------------------------------------------
# Instalación
# ---------------------------------------------------------------------------


def _build_env(tmpdir: Path) -> dict[str, str]:
    return {
        "TMPDIR": str(tmpdir),
        "HOME": str(tmpdir),
        "PIP_NO_CACHE_DIR": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    }


def build_venv(ctx: Context, release_dir: Path, version: str, tmpdir: Path) -> None:
    venv = release_dir / ".venv"
    env = _build_env(tmpdir)
    run_checked(
        ctx,
        [ctx.config.python, "-m", "venv", str(venv)],
        what="python -m venv",
        timeout=300,
        umask=0o022,
        env=env,
    )
    python = venv / "bin" / "python"
    run_checked(
        ctx,
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--find-links",
            str(release_dir / "wheels"),
            "--no-input",
            f"meshbox=={version}",
        ],
        what="pip install",
        timeout=1800,
        umask=0o022,
        env=env,
    )
    run_checked(ctx, [str(python), "-c", "import meshbox"], what="import meshbox", timeout=120)
    atomic_write(ctx, release_dir / INSTALLED_MARKER, f"{version}\n".encode(), mode=0o644)


def run_as_meshbox(ctx: Context, argv: list[str], *, timeout: float, what: str) -> ProcResult:
    var = ctx.paths.meshbox_var_dir
    return run_checked(
        ctx,
        [ctx.bins.runuser, "-u", MESHBOX_USER, "--", *argv],
        what=what,
        timeout=timeout,
        env={"HOME": str(var), "TMPDIR": str(var / "tmp")},
        cwd="/",  # meshbox puede no tener acceso al directorio actual (modo CLI)
    )


def make_backup(ctx: Context, version: str, python: Path, started: float) -> Path | None:
    db, backups = meshbox_paths(ctx)
    if not db.exists():
        return None
    run_as_meshbox(
        ctx,
        [
            str(python),
            "-m",
            "meshbox",
            "backup",
            "create",
            "--suffix",
            f"pre-{version}",
            "--config",
            str(ctx.paths.meshbox_config),
        ],
        timeout=900,
        what="meshbox backup create",
    )
    candidates = [
        p
        for p in backups.glob(f"*pre-{version}*")
        if p.is_file() and p.stat().st_mtime >= started - 5
    ]
    if not candidates:
        raise failed("no se encontró el respaldo previo a la actualización")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def restore_backup(ctx: Context, python: Path, backup: Path) -> None:
    run_as_meshbox(
        ctx,
        [
            str(python),
            "-m",
            "meshbox",
            "backup",
            "restore",
            "--file",
            str(backup),
            "--config",
            str(ctx.paths.meshbox_config),
        ],
        timeout=900,
        what="meshbox backup restore",
    )


def alembic_revision(ctx: Context) -> str | None:
    """Revisión del esquema; se lee como meshbox para no dejar archivos -wal/-shm de root."""
    db, _ = meshbox_paths(ctx)
    if not db.exists():
        return None
    var = ctx.paths.meshbox_var_dir
    result = ctx.runner.run(
        [
            ctx.bins.runuser,
            "-u",
            MESHBOX_USER,
            "--",
            ctx.bins.sqlite3,
            "-readonly",
            str(db),
            "SELECT version_num FROM alembic_version;",
        ],
        timeout=60,
        env={"HOME": str(var)},
        cwd="/",
    )
    if result.returncode != 0:
        return None
    value = result.out.strip()
    return value or None


def switch_current(ctx: Context, version: str) -> None:
    link = current_link(ctx)
    tmp = link.with_name(f".current.{secrets.token_hex(4)}")
    tmp.symlink_to(f"releases/{version}")
    try:
        tmp.replace(link)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    fsync_dir(link.parent)


def install_file(ctx: Context, src: Path, dst: Path, mode: int) -> bool:
    """Copia si cambió (escritura atómica, dueño root). Devuelve si hubo cambio."""
    if not src.is_file():
        return False
    data = src.read_bytes()
    try:
        if dst.read_bytes() == data and (dst.stat().st_mode & 0o7777) == mode:
            return False
    except OSError:
        pass
    atomic_write(ctx, dst, data, mode=mode)
    return True


def sync_privd(ctx: Context, src: Path) -> bool:
    if not (src / "meshbox_privd.py").is_file():
        return False
    dst = ctx.paths.privd_lib_dir
    ensure_dir(dst, 0o755)
    ensure_dir(dst / "commands", 0o755)
    changed = install_file(ctx, src / "meshbox_privd.py", dst / "meshbox_privd.py", 0o644)
    wanted = sorted(p.name for p in (src / "commands").glob("*.py"))
    for name in wanted:
        changed |= install_file(ctx, src / "commands" / name, dst / "commands" / name, 0o644)
    for old in (dst / "commands").glob("*.py"):
        if old.name not in wanted:
            old.unlink()
            changed = True
    for cache in (dst / "__pycache__", dst / "commands" / "__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    return changed


def install_system_files(ctx: Context, release_dir: Path) -> dict[str, bool]:
    """privd, unidades, Mosquitto y (solo appliance) primer arranque, journald y portal."""
    deploy = release_dir / "deploy"
    changed = {"privd": False, "units": False, "mosquitto": False, "other": False}
    changed["privd"] = sync_privd(ctx, release_dir / "privd")
    pmtiles = release_dir / "bin" / "pmtiles"
    if pmtiles.is_file():
        ensure_dir(ctx.config.opt_dir / "bin", 0o755)
        changed["other"] |= install_file(
            ctx, pmtiles, ctx.config.opt_dir / "bin" / "pmtiles", 0o755
        )
    for unit in sorted((deploy / "systemd").glob("*")):
        if unit.suffix not in (".service", ".socket", ".timer"):
            continue
        if unit.name == "meshbox-firstboot.service" and ctx.mode != "appliance":
            continue
        if install_file(ctx, unit, ctx.paths.systemd_system_dir / unit.name, 0o644):
            changed["units"] = True
    mosquitto_conf = deploy / "mosquitto" / "meshbox.conf"
    if ctx.paths.mosquitto_conf_d.is_dir() and install_file(
        ctx, mosquitto_conf, ctx.paths.mosquitto_conf_d / "meshbox.conf", 0o644
    ):
        changed["mosquitto"] = True
    if ctx.mode == "appliance":
        extras = [
            (deploy / "firstboot" / "meshbox-firstboot.sh", ctx.paths.firstboot_script, 0o755),
            (
                deploy / "journald" / "meshbox.conf",
                ctx.paths.journald_conf_d / "meshbox.conf",
                0o644,
            ),
            (
                deploy / "nm" / "dnsmasq-shared.d" / "meshbox-captive.conf",
                ctx.paths.nm_dnsmasq_shared_dir / "meshbox-captive.conf",
                0o644,
            ),
        ]
        for src, dst, mode in extras:
            if src.is_file():
                ensure_dir(dst.parent, 0o755)
                changed["other"] |= install_file(ctx, src, dst, mode)
    if changed["units"]:
        run_checked(ctx, [ctx.bins.systemctl, "daemon-reload"], what="daemon-reload", timeout=60)
    if changed["mosquitto"]:
        run_checked(
            ctx,
            [ctx.bins.systemctl, "--no-block", "restart", "mosquitto.service"],
            what="systemctl restart mosquitto",
        )
    return changed


def wait_health(ctx: Context, version: str, timeout: float = HEALTH_TIMEOUT_S) -> bool:
    url = ctx.config.effective_health_url
    end = ctx.monotonic() + timeout
    while True:
        try:
            code, body = ctx.http_get(url, 3.0)
            data = json.loads(body) if code == 200 else None
        except Exception as exc:  # OSError, ValueError, http.client.HTTPException...
            log.debug("salud todavía no responde: %s", exc)
            data = None
        if isinstance(data, dict) and data.get("status") == "ok" and data.get("version") == version:
            return True
        if ctx.monotonic() >= end:
            return False
        ctx.sleep(HEALTH_INTERVAL_S)


def prune_releases(ctx: Context, protect: set[str]) -> list[str]:
    """Deja la versión actual y las 2 anteriores más recientes; borra el resto."""
    current = current_version(ctx)
    versions = release_versions(ctx)
    keep = set(protect)
    if current is not None:
        keep.add(current)
        older = [v for v in versions if version_key(v) < version_key(current)]
        keep.update(older[-KEEP_PREVIOUS:])
    removed = []
    for version in versions:
        if version in keep:
            continue
        shutil.rmtree(releases_dir(ctx) / version, ignore_errors=True)
        removed.append(version)
    return removed


def rollback_to(ctx: Context, target: str, backup: Path | None) -> bool:
    """Vuelve a `target` (y restaura `backup` si se pasa). Devuelve si `target` respondió."""
    install_system_files(ctx, releases_dir(ctx) / target)
    systemctl = ctx.bins.systemctl
    if backup is not None:
        run_checked(ctx, [systemctl, "stop", MESHBOX_UNIT], what="systemctl stop", timeout=120)
        switch_current(ctx, target)
        try:
            restore_backup(ctx, release_python(ctx, target), backup)
        except CommandError as exc:
            run_checked(
                ctx, [systemctl, "--no-block", "start", MESHBOX_UNIT], what="systemctl start"
            )
            raise failed(f"no se pudo restaurar la base previa: {exc.message}") from exc
        run_checked(ctx, [systemctl, "--no-block", "start", MESHBOX_UNIT], what="systemctl start")
    else:
        switch_current(ctx, target)
        run_checked(
            ctx, [systemctl, "--no-block", "restart", MESHBOX_UNIT], what="systemctl restart"
        )
    return wait_health(ctx, target)


# ---------------------------------------------------------------------------
# Trabajos
# ---------------------------------------------------------------------------


def _progress_reporter(job: Job) -> Callable[[int, int | None], None]:
    last = {"value": -1.0}

    def report(done: int, total: int | None) -> None:
        if not total:
            return
        value = round(done / total, 2)
        if value - last["value"] >= 0.05 or value >= 1.0:
            last["value"] = value
            job.update(progress=value)

    return report


def _apply_job(ctx: Context, job: Job, version: str) -> Result:
    started = time.time()
    previous = current_version(ctx)
    base = ctx.config.updates_base_url.rstrip("/")
    tarball_name = TARBALL_TEMPLATE.format(version=version)
    staging = ctx.config.opt_dir / ".staging"
    ensure_dir(ctx.config.opt_dir, 0o755)
    ensure_dir(staging, 0o700)
    work = Path(tempfile.mkdtemp(prefix=f"update-{version}-", dir=str(staging)))
    release_dir = releases_dir(ctx) / version
    try:
        job.update(step="download", progress=0.0)
        sums = work / SUMS_NAME
        signature = work / SIG_NAME
        tarball = work / tarball_name
        download(f"{base}/v{version}/{SUMS_NAME}", sums, max_bytes=MAX_SUMS)
        download(f"{base}/v{version}/{SIG_NAME}", signature, max_bytes=1024)
        job.update(step="verify_signature")
        verify_signature(ctx, sums, signature, work)
        expected_sum(sums, tarball_name)  # que figure antes de bajar el paquete
        job.update(step="download")
        download(
            f"{base}/v{version}/{tarball_name}",
            tarball,
            max_bytes=MAX_TARBALL,
            progress=_progress_reporter(job),
        )
        job.update(step="verify_checksum", progress=None)
        verify_checksum(sums, tarball, tarball_name)

        job.update(step="extract")
        extract_dir = work / "extract"
        extract_dir.mkdir()
        safe_extract(tarball, extract_dir)
        tarball.unlink()
        root = extract_dir / f"meshbox-{version}"
        check_layout(root, version)

        job.update(step="install")
        ensure_dir(releases_dir(ctx), 0o755)
        if release_dir.is_symlink() or release_dir.is_file():
            release_dir.unlink()
        elif release_dir.exists():
            shutil.rmtree(release_dir)
        root.rename(release_dir)
        release_dir.chmod(0o755)
        build_venv(ctx, release_dir, version, work)

        job.update(step="backup")
        backup_python = (
            release_python(ctx, previous)
            if previous is not None and release_python(ctx, previous).exists()
            else release_python(ctx, version)
        )
        backup = make_backup(ctx, version, backup_python, started)
        rev_before = alembic_revision(ctx)

        job.update(step="switch")
        install_system_files(ctx, release_dir)
        switch_current(ctx, version)
        run_checked(
            ctx,
            [ctx.bins.systemctl, "--no-block", "restart", MESHBOX_UNIT],
            what="systemctl restart",
        )

        job.update(step="health")
        healthy = wait_health(ctx, version)
        rev_after = alembic_revision(ctx)
        migrated = rev_before is not None and rev_after != rev_before
        if healthy:
            write_state(
                ctx,
                {
                    "current": version,
                    "previous": previous,
                    "backup": str(backup) if backup else None,
                    "rev_before": rev_before,
                    "rev_after": rev_after,
                    "migrated": migrated,
                    "updated_at": time.time(),
                },
            )
            job.update(step="cleanup")
            protect = {version} | ({previous} if previous else set())
            removed = prune_releases(ctx, protect)
            ctx.exit_requested = True
            return {
                "version": version,
                "previous": previous,
                "backup": str(backup) if backup else None,
                "migrated": migrated,
                "removed": removed,
            }

        job.update(step="rollback")
        if previous is None:
            raise failed(
                f"la versión {version} no respondió en {HEALTH_TIMEOUT_S:.0f} s y no hay una "
                "versión anterior para volver"
            )
        restore = backup if migrated else None
        back_ok = rollback_to(ctx, previous, restore)
        ctx.exit_requested = True
        message = (
            f"la versión {version} no respondió en {HEALTH_TIMEOUT_S:.0f} s; se volvió a {previous}"
        )
        if restore is not None:
            message += " y se restauró la base previa"
        if not back_ok:
            message += f" (pero {previous} tampoco respondió)"
        job.update(state="rolled_back", message=message)
        return {
            "version": previous,
            "failed_version": version,
            "db_restored": restore is not None,
            "previous_healthy": back_ok,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _rollback_job(ctx: Context, job: Job, current: str, target: str) -> Result:
    state = read_state(ctx)
    backup: Path | None = None
    if (
        state.get("current") == current
        and state.get("previous") == target
        and state.get("migrated")
        and isinstance(state.get("backup"), str)
    ):
        candidate = Path(state["backup"])
        if candidate.is_file():
            backup = candidate
    job.update(step="switch")
    healthy = rollback_to(ctx, target, backup)
    write_state(
        ctx,
        {
            "current": target,
            "previous": current,
            "backup": None,
            "rev_before": None,
            "rev_after": None,
            "migrated": False,
            "updated_at": time.time(),
            "rolled_back_from": current,
        },
    )
    ctx.exit_requested = True
    if not healthy:
        raise failed(f"se volvió a {target}, pero no respondió en {HEALTH_TIMEOUT_S:.0f} s")
    return {"version": target, "previous": current, "db_restored": backup is not None}


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------


def _ensure_quiet(ctx: Context) -> None:
    for group in ("network", "power"):
        job = ctx.jobs.running(group)
        if job is not None:
            raise CommandError("busy", f"hay otro trabajo en curso ({job.kind} {job.id})")


def apply(ctx: Context, args: Args) -> Result:
    check_keys(args, ("version",))
    version = validate_version(args["version"])
    if not ctx.config.updates_base_url:
        raise failed("updates_base_url no está configurado en privd.toml")
    if not ctx.public_key_pem.strip():
        raise failed("privd no tiene clave pública de releases")
    current = current_version(ctx)
    if current == version:
        raise failed(f"la versión {version} ya está instalada")
    _ensure_quiet(ctx)
    job = ctx.jobs.start(
        "update",
        lambda job: _apply_job(ctx, job, version),
        group="update",
        meta={"action": "apply", "version": version, "from": current},
    )
    return {"job": job.id, "state": job.state}


def rollback(ctx: Context, args: Args) -> Result:
    check_keys(args, (), ("version",))
    current = current_version(ctx)
    if current is None:
        raise failed("no hay una versión instalada")
    if "version" in args:
        target = validate_version(args["version"])
        if target == current:
            raise invalid("esa es la versión actual")
    else:
        found = previous_version(ctx, current)
        if found is None:
            raise failed("no hay una versión anterior instalada")
        target = found
    if not is_installed(ctx, target):
        raise failed(f"la versión {target} no está instalada")
    _ensure_quiet(ctx)
    job = ctx.jobs.start(
        "update",
        lambda job: _rollback_job(ctx, job, current, target),
        group="update",
        meta={"action": "rollback", "version": target, "from": current},
    )
    return {"job": job.id, "state": job.state}


def status(ctx: Context, args: Args) -> Result:
    check_keys(args, ("job",))
    job_id = get_str(args, "job")
    if not JOB_ID_RE.fullmatch(job_id):
        raise invalid("job no válido")
    data: dict[str, Any] | None = ctx.jobs.get(job_id)
    if data is None:
        raise invalid("trabajo desconocido")
    return data


def info(ctx: Context, args: Args) -> Result:
    check_keys(args)
    current = current_version(ctx)
    state = read_state(ctx)
    return {
        "current": current,
        "installed": installed_versions(ctx),
        "previous": previous_version(ctx, current),
        "last_update": state or None,
        "job": ctx.jobs.latest("update"),
        "updates_base_url": ctx.config.updates_base_url or None,
    }


COMMANDS = {
    "update.apply": Command(apply),
    "update.status": Command(status),
    "update.rollback": Command(rollback),
    "update.info": Command(info),
}
