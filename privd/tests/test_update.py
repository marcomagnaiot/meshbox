"""Actualizaciones firmadas: descarga, firma, sumas, instalación, salud y vuelta atrás (23.5)."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from privd_testkit import Call, Env, fail, find_openssl, make_env, ok

from commands import update
from commands.core import CommandError, Config, ProcResult

OLD = "0.1.0"
NEW = "0.2.0"


# ---------------------------------------------------------------------------
# Piezas puras
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("version", ["0.1.0", "10.20.30", "1.0.0"])
def test_valid_versions(version: str) -> None:
    assert update.validate_version(version) == version


@pytest.mark.parametrize(
    "version", ["1.0", "v1.0.0", "1.0.0-rc1", "1.0.0;rm", "../1.0.0", "1.0.0\n", "", 1, None]
)
def test_invalid_versions(version: object) -> None:
    with pytest.raises(CommandError) as exc:
        update.validate_version(version)
    assert exc.value.code == "invalid_args"


def test_expected_sum_and_checksum(tmp_path: Path) -> None:
    data = tmp_path / "paquete.tar.gz"
    data.write_bytes(b"contenido")
    digest = hashlib.sha256(b"contenido").hexdigest()
    sums = tmp_path / "SHA256SUMS"
    sums.write_text(f"{'0' * 64}  otro.img.xz\n{digest} *paquete.tar.gz\n")
    assert update.expected_sum(sums, "paquete.tar.gz") == digest
    assert update.verify_checksum(sums, data, "paquete.tar.gz") == digest
    with pytest.raises(CommandError, match="no figura"):
        update.expected_sum(sums, "falta.tar.gz")
    data.write_bytes(b"adulterado")
    with pytest.raises(CommandError, match="no coincide"):
        update.verify_checksum(sums, data, "paquete.tar.gz")


def _tar_with(tmp_path: Path, name: str, member: tarfile.TarInfo, data: bytes = b"x") -> Path:
    path = tmp_path / name
    with tarfile.open(path, "w:gz") as tar:
        member.size = len(data)
        tar.addfile(member, io.BytesIO(data))
    return path


def test_safe_extract_rejects_traversal(tmp_path: Path) -> None:
    bad = _tar_with(tmp_path, "malo.tar.gz", tarfile.TarInfo("../fuera.txt"))
    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(CommandError, match="inseguras"):
        update.safe_extract(bad, dest)
    assert not (tmp_path / "fuera.txt").exists()


def test_safe_extract_rejects_absolute_and_devices(tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    dest.mkdir()
    absolute = _tar_with(tmp_path, "abs.tar.gz", tarfile.TarInfo("/etc/cron.d/meshbox-prueba"))
    # El filtro "data" quita la barra inicial (queda dentro de dest) o rechaza la entrada.
    try:
        update.safe_extract(absolute, dest)
    except CommandError:
        pass
    else:
        assert (dest / "etc/cron.d/meshbox-prueba").exists()
    device = tarfile.TarInfo("dispositivo")
    device.type = tarfile.CHRTYPE
    dev_tar = _tar_with(tmp_path, "dev.tar.gz", device, b"")
    with pytest.raises(CommandError):
        update.safe_extract(dev_tar, dest)


def test_safe_extract_corrupt(tmp_path: Path) -> None:
    broken = tmp_path / "roto.tar.gz"
    broken.write_bytes(b"no es gzip")
    with pytest.raises(CommandError, match="dañado"):
        update.safe_extract(broken, tmp_path)


def test_check_layout(tmp_path: Path) -> None:
    root = tmp_path / "meshbox-0.2.0"
    with pytest.raises(CommandError, match="VERSION"):
        update.check_layout(root, NEW)
    root.mkdir()
    (root / "VERSION").write_text("0.3.0\n")
    with pytest.raises(CommandError, match=r"0\.3\.0"):
        update.check_layout(root, NEW)
    (root / "VERSION").write_text(f"{NEW}\n")
    with pytest.raises(CommandError, match="wheels"):
        update.check_layout(root, NEW)


def test_download_limits_and_errors(tmp_path: Path) -> None:
    source = tmp_path / "grande.bin"
    source.write_bytes(b"x" * 5000)
    dest = tmp_path / "copia.bin"
    seen: list[tuple[int, int | None]] = []
    size = update.download(
        source.as_uri(), dest, max_bytes=10000, progress=lambda d, t: seen.append((d, t))
    )
    assert size == 5000
    assert dest.read_bytes() == b"x" * 5000
    assert seen[-1] == (5000, 5000)
    with pytest.raises(CommandError, match="demasiado grande"):
        update.download(source.as_uri(), dest, max_bytes=100)
    with pytest.raises(CommandError, match="no se pudo descargar"):
        update.download((tmp_path / "no-existe.bin").as_uri(), dest, max_bytes=100)


def test_meshbox_paths_defaults(env: Env) -> None:
    var = env.ctx.paths.meshbox_var_dir
    assert update.meshbox_paths(env.ctx) == (var / "meshbox.db", var / "backups")
    env.ctx.paths.meshbox_config.write_text("[paths\nroto")
    assert update.meshbox_paths(env.ctx) == (var / "meshbox.db", var / "backups")
    env.ctx.paths.meshbox_config.write_text('[paths]\ndb = "/etc/shadow"\nbackups = "relativo"\n')
    assert update.meshbox_paths(env.ctx) == (var / "meshbox.db", var / "backups")


@pytest.mark.linux
def test_meshbox_paths_custom_inside_var(env: Env) -> None:
    var = env.ctx.paths.meshbox_var_dir
    env.ctx.paths.meshbox_config.write_text(
        f'[paths]\ndb = "{var}/datos/m.db"\nbackups = "{var}/resp"\n'
    )
    assert update.meshbox_paths(env.ctx) == (var / "datos/m.db", var / "resp")


def test_wait_health(env: Env) -> None:
    env.http_responses[:] = [
        (503, b""),
        (200, b"no-json"),
        (200, json.dumps({"status": "ok", "version": OLD}).encode()),
        (200, json.dumps({"status": "ok", "version": NEW}).encode()),
    ]
    assert update.wait_health(env.ctx, NEW) is True
    assert env.clock.sleeps == [3.0, 3.0, 3.0]


def test_wait_health_timeout(env: Env) -> None:
    assert update.wait_health(env.ctx, NEW) is False
    assert env.clock.now >= 1000.0 + update.HEALTH_TIMEOUT_S


def test_apply_requires_base_url(env: Env) -> None:
    with pytest.raises(CommandError, match="updates_base_url"):
        update.apply(env.ctx, {"version": NEW})


def test_apply_requires_public_key(tmp_path: Path) -> None:
    env = make_env(tmp_path, updates_base_url="https://ejemplo.com/releases")
    with pytest.raises(CommandError, match="clave pública"):
        update.apply(env.ctx, {"version": NEW})


def test_apply_rejects_bad_args(tmp_path: Path) -> None:
    env = make_env(tmp_path, updates_base_url="https://x.com/r", public_key_pem="PEM")
    for args in ({}, {"version": "latest"}, {"version": NEW, "force": True}):
        with pytest.raises(CommandError) as exc:
            update.apply(env.ctx, args)
        assert exc.value.code == "invalid_args"


def test_status_validation(env: Env) -> None:
    with pytest.raises(CommandError, match="no válido"):
        update.status(env.ctx, {"job": "../../etc"})
    with pytest.raises(CommandError, match="desconocido"):
        update.status(env.ctx, {"job": "0123456789ab"})
    job = env.ctx.jobs.start("update", lambda job: {"ok": 1}, group="update")
    env.ctx.jobs.wait_all(5)
    assert update.status(env.ctx, {"job": job.id})["state"] == "succeeded"


def test_status_survives_restart(env: Env) -> None:
    from commands.jobs import JobManager

    job = env.ctx.jobs.start("update", lambda job: {"version": NEW}, group="update")
    env.ctx.jobs.wait_all(5)
    env.ctx.jobs = JobManager(env.ctx.paths.state_dir)
    data = update.status(env.ctx, {"job": job.id})
    assert data["state"] == "succeeded"
    assert data["result"] == {"version": NEW}


# ---------------------------------------------------------------------------
# Flujo completo (Linux: enlaces simbólicos y OpenSSL real)
# ---------------------------------------------------------------------------


@dataclass
class Harness:
    env: Env
    openssl: str
    key: Path
    server: Path
    revisions: list[str] = field(default_factory=lambda: ["rev-a", "rev-b"])
    healthy: set[str] = field(default_factory=lambda: {NEW})
    fail_on: set[str] = field(default_factory=set)
    restored: list[list[str]] = field(default_factory=list)

    @property
    def ctx(self):  # type: ignore[no-untyped-def]
        return self.env.ctx

    def releases(self) -> Path:
        return self.ctx.config.opt_dir / "releases"

    def current(self) -> str | None:
        return update.current_version(self.ctx)


def _openssl(openssl: str, *args: str) -> None:
    subprocess.run([openssl, *args], check=True, capture_output=True)


def _write_release_tree(root: Path, version: str, version_file: str | None = None) -> None:
    files = {
        "VERSION": f"{version_file or version}\n",
        f"wheels/meshbox-{version}-py3-none-any.whl": "rueda",
        "privd/meshbox_privd.py": f"# privd {version}\n",
        "privd/commands/__init__.py": f"# comandos {version}\n",
        "deploy/systemd/meshbox.service": f"# unidad {version}\n",
        "deploy/systemd/meshbox-firstboot.service": f"# firstboot {version}\n",
        "deploy/systemd/README.txt": "no es una unidad\n",
        "deploy/mosquitto/meshbox.conf": f"# mosquitto {version}\n",
        "deploy/firstboot/meshbox-firstboot.sh": f"#!/bin/sh\n# {version}\n",
        "deploy/journald/meshbox.conf": "[Journal]\nSystemMaxUse=50M\n",
        "deploy/nm/dnsmasq-shared.d/meshbox-captive.conf": "address=/#/10.42.0.1\n",
        "bin/pmtiles": f"pmtiles {version}\n",
    }
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def publish(
    h: Harness,
    version: str,
    *,
    key: Path | None = None,
    version_file: str | None = None,
    corrupt_sum: bool = False,
    omit_from_sums: bool = False,
) -> None:
    """Arma `server/v<versión>/` como lo publica release.yml."""
    build = h.env.root / "build" / version
    tree = build / f"meshbox-{version}"
    _write_release_tree(tree, version, version_file)
    out = h.server / f"v{version}"
    out.mkdir(parents=True, exist_ok=True)
    name = update.TARBALL_TEMPLATE.format(version=version)
    with tarfile.open(out / name, "w:gz") as tar:
        tar.add(tree, arcname=f"meshbox-{version}")
    digest = hashlib.sha256((out / name).read_bytes()).hexdigest()
    if corrupt_sum:
        digest = "f" * 64
    listed = "otro-archivo.img.xz" if omit_from_sums else name
    (out / "SHA256SUMS").write_text(f"{digest}  {listed}\n")
    _openssl(
        h.openssl,
        "pkeyutl",
        "-sign",
        "-inkey",
        str(key or h.key),
        "-rawin",
        "-in",
        str(out / "SHA256SUMS"),
        "-out",
        str(out / "SHA256SUMS.sig"),
    )


def install_fake_release(h: Harness, version: str) -> None:
    base = h.releases() / version
    _write_release_tree(base, version)
    python = base / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("")
    (base / update.INSTALLED_MARKER).write_text(version)


def point_current(h: Harness, version: str) -> None:
    link = h.ctx.config.opt_dir / "current"
    if link.is_symlink():
        link.unlink()
    link.symlink_to(f"releases/{version}")


def runner_fallback(h: Harness):  # type: ignore[no-untyped-def]
    ctx = h.ctx

    def handle(call: Call) -> ProcResult:
        argv = call.argv
        joined = " ".join(argv)
        for marker in h.fail_on:
            if marker in joined:
                return fail(1, f"falló {marker}")
        if argv[0] == ctx.bins.openssl:
            real = subprocess.run([h.openssl, *argv[1:]], capture_output=True, check=False)
            return ProcResult(real.returncode, real.stdout, real.stderr)
        if argv[:3] == [ctx.config.python, "-m", "venv"]:
            python = Path(argv[3]) / "bin/python"
            python.parent.mkdir(parents=True, exist_ok=True)
            python.write_text("")
            return ok()
        if argv[0] == ctx.bins.runuser and "sqlite3" in joined:
            return ok(h.revisions[0] + "\n") if h.revisions else ok()
        if argv[0] == ctx.bins.runuser and "backup create" in joined:
            suffix = argv[argv.index("--suffix") + 1]
            backups = ctx.paths.meshbox_var_dir / "backups"
            (backups / f"meshbox-20261020-{suffix}.db.gz").write_bytes(b"respaldo")
            return ok()
        if argv[0] == ctx.bins.runuser and "backup restore" in joined:
            h.restored.append(argv)
            return ok()
        return ok()

    return handle


def health_by_link(h: Harness):  # type: ignore[no-untyped-def]
    def http_get(url: str, timeout: float) -> tuple[int, bytes]:
        version = update.current_version(h.ctx)
        if version in h.healthy:
            return 200, json.dumps({"status": "ok", "version": version}).encode()
        raise ConnectionRefusedError("no responde")

    return http_get


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    openssl = find_openssl()
    if openssl is None:
        pytest.skip("sin OpenSSL 3")
    keys = tmp_path / "claves"
    keys.mkdir()
    key = keys / "privada.pem"
    _openssl(openssl, "genpkey", "-algorithm", "ed25519", "-out", str(key))
    _openssl(openssl, "pkey", "-in", str(key), "-pubout", "-out", str(keys / "publica.pem"))
    server = tmp_path / "servidor"
    server.mkdir()
    env = make_env(
        tmp_path / "raiz",
        updates_base_url=server.as_uri(),
        public_key_pem=(keys / "publica.pem").read_text(),
    )
    env.ctx.bins.openssl = openssl
    h = Harness(env=env, openssl=openssl, key=key, server=server)
    env.runner.fallback = runner_fallback(h)
    env.ctx.http_get = health_by_link(h)
    for version in ("0.0.1", "0.0.2", "0.0.3", OLD):
        install_fake_release(h, version)
    point_current(h, OLD)
    (env.ctx.paths.meshbox_var_dir / "meshbox.db").write_bytes(b"base")
    return h


def run_apply(h: Harness, version: str = NEW) -> dict:
    result = update.apply(h.ctx, {"version": version})
    assert result["state"] == "running"
    h.ctx.jobs.wait_all(30)
    job = h.ctx.jobs.get(result["job"])
    assert job is not None
    return job


def advance_revision_after_switch(h: Harness, before: str, after: str) -> None:
    """La revisión cambia cuando `current` ya apunta a la versión nueva (migración)."""

    def sqlite(call: Call) -> ProcResult:
        return ok((after if update.current_version(h.ctx) == NEW else before) + "\n")

    h.env.runner.on([h.ctx.bins.runuser, "-u", "meshbox", "--", h.ctx.bins.sqlite3], sqlite)


@pytest.mark.linux
def test_apply_success(harness: Harness) -> None:
    h = harness
    advance_revision_after_switch(h, "rev-a", "rev-b")
    publish(h, NEW)
    job = run_apply(h)
    assert job["state"] == "succeeded", job
    assert job["meta"] == {"action": "apply", "version": NEW, "from": OLD}
    result = job["result"]
    assert result["version"] == NEW
    assert result["previous"] == OLD
    assert result["migrated"] is True
    assert sorted(result["removed"]) == ["0.0.1", "0.0.2"]
    assert h.current() == NEW
    assert sorted(p.name for p in h.releases().iterdir()) == ["0.0.3", OLD, NEW]
    assert (h.releases() / NEW / update.INSTALLED_MARKER).read_text().strip() == NEW
    paths = h.ctx.paths
    assert (paths.privd_lib_dir / "meshbox_privd.py").read_text() == f"# privd {NEW}\n"
    assert (paths.systemd_system_dir / "meshbox.service").read_text() == f"# unidad {NEW}\n"
    assert (paths.systemd_system_dir / "meshbox-firstboot.service").exists()
    assert not (paths.systemd_system_dir / "README.txt").exists()
    assert (paths.mosquitto_conf_d / "meshbox.conf").read_text() == f"# mosquitto {NEW}\n"
    assert paths.firstboot_script.exists()
    assert (paths.journald_conf_d / "meshbox.conf").exists()
    pmtiles = h.ctx.config.opt_dir / "bin/pmtiles"
    assert pmtiles.read_text() == f"pmtiles {NEW}\n"
    assert pmtiles.stat().st_mode & 0o777 == 0o755
    argvs = h.env.runner.argvs()
    assert ["/usr/bin/systemctl", "daemon-reload"] in argvs
    assert ["/usr/bin/systemctl", "--no-block", "restart", "meshbox.service"] in argvs
    assert ["/usr/bin/systemctl", "--no-block", "restart", "mosquitto.service"] in argvs
    venv = [a for a in argvs if a[:3] == ["/usr/bin/python3", "-m", "venv"]]
    assert venv == [["/usr/bin/python3", "-m", "venv", str(h.releases() / NEW / ".venv")]]
    pip = [a for a in argvs if "pip" in a]
    assert pip[0][-1] == f"meshbox=={NEW}"
    assert "--no-index" in pip[0]
    backup = next(a for a in argvs if "backup" in a and "create" in a)
    assert backup[:4] == ["/usr/sbin/runuser", "-u", "meshbox", "--"]
    assert backup[4] == str(h.releases() / OLD / ".venv/bin/python")
    state = update.read_state(h.ctx)
    assert state["current"] == NEW
    assert state["previous"] == OLD
    assert state["migrated"] is True
    assert state["backup"].endswith(f"pre-{NEW}.db.gz")
    assert h.ctx.exit_requested is True
    assert list((h.ctx.config.opt_dir / ".staging").iterdir()) == []
    pip_call = next(c for c in h.env.runner.calls if "pip" in c.argv)
    assert pip_call.umask == 0o022
    # Temporales grandes en el área root de la SD, nunca en /tmp (RAM).
    staging = str(h.ctx.config.opt_dir / ".staging")
    assert pip_call.env is not None
    assert pip_call.env["TMPDIR"].startswith(staging)


@pytest.mark.linux
def test_apply_rolls_back_and_restores_db(harness: Harness) -> None:
    h = harness
    h.healthy = {OLD}
    advance_revision_after_switch(h, "rev-a", "rev-b")
    publish(h, NEW)
    job = run_apply(h)
    assert job["state"] == "rolled_back", job
    assert "se volvió a 0.1.0" in job["message"]
    assert "se restauró la base previa" in job["message"]
    assert job["result"] == {
        "version": OLD,
        "failed_version": NEW,
        "db_restored": True,
        "previous_healthy": True,
    }
    assert h.current() == OLD
    (restore,) = h.restored
    assert restore[4] == str(h.releases() / OLD / ".venv/bin/python")
    assert restore[restore.index("--file") + 1].endswith(f"pre-{NEW}.db.gz")
    argvs = h.env.runner.argvs()
    assert ["/usr/bin/systemctl", "stop", "meshbox.service"] in argvs
    assert ["/usr/bin/systemctl", "--no-block", "start", "meshbox.service"] in argvs
    # privd y las unidades vuelven a las de la versión anterior.
    assert (h.ctx.paths.privd_lib_dir / "meshbox_privd.py").read_text() == f"# privd {OLD}\n"
    assert update.read_state(h.ctx) == {}


@pytest.mark.linux
def test_apply_rolls_back_without_migration(harness: Harness) -> None:
    h = harness
    h.healthy = set()
    advance_revision_after_switch(h, "rev-a", "rev-a")
    publish(h, NEW)
    job = run_apply(h)
    assert job["state"] == "rolled_back"
    assert job["result"]["db_restored"] is False
    assert job["result"]["previous_healthy"] is False
    assert "tampoco respondió" in job["message"]
    assert h.restored == []
    assert h.current() == OLD


@pytest.mark.linux
def test_apply_bad_signature(harness: Harness, tmp_path: Path) -> None:
    h = harness
    other = tmp_path / "otra.pem"
    _openssl(h.openssl, "genpkey", "-algorithm", "ed25519", "-out", str(other))
    publish(h, NEW, key=other)
    job = run_apply(h)
    assert job["state"] == "failed"
    assert "firma" in job["message"]
    assert h.current() == OLD
    assert not (h.releases() / NEW).exists()


@pytest.mark.linux
def test_apply_truncated_signature(harness: Harness) -> None:
    h = harness
    publish(h, NEW)
    sig = h.server / f"v{NEW}" / "SHA256SUMS.sig"
    sig.write_bytes(sig.read_bytes()[:10])
    job = run_apply(h)
    assert job["state"] == "failed"
    assert "64 bytes" in job["message"]


@pytest.mark.linux
@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"corrupt_sum": True}, "no coincide"),
        ({"omit_from_sums": True}, "no figura"),
        ({"version_file": "9.9.9"}, "9.9.9"),
    ],
)
def test_apply_rejects_bad_packages(harness: Harness, kwargs: dict, message: str) -> None:
    h = harness
    publish(h, NEW, **kwargs)
    job = run_apply(h)
    assert job["state"] == "failed"
    assert message in job["message"]
    assert h.current() == OLD


@pytest.mark.linux
def test_apply_missing_release(harness: Harness) -> None:
    job = run_apply(harness, "0.9.0")
    assert job["state"] == "failed"
    assert "no se pudo descargar" in job["message"]


@pytest.mark.linux
@pytest.mark.parametrize(
    ("marker", "message"), [("pip", "pip install"), ("backup create", "backup")]
)
def test_apply_install_failures_keep_current(harness: Harness, marker: str, message: str) -> None:
    h = harness
    h.fail_on = {marker}
    publish(h, NEW)
    job = run_apply(h)
    assert job["state"] == "failed"
    assert message in job["message"]
    assert h.current() == OLD


@pytest.mark.linux
def test_apply_same_version_and_busy(harness: Harness) -> None:
    h = harness
    with pytest.raises(CommandError, match="ya está instalada"):
        update.apply(h.ctx, {"version": OLD})
    import threading

    gate = threading.Event()
    h.ctx.jobs.start("wifi", lambda job: gate.wait(5) and {}, group="network")
    try:
        with pytest.raises(CommandError) as exc:
            update.apply(h.ctx, {"version": NEW})
        assert exc.value.code == "busy"
    finally:
        gate.set()
        h.ctx.jobs.wait_all(5)


@pytest.mark.linux
def test_apply_shared_mode_skips_appliance_files(tmp_path: Path, harness: Harness) -> None:
    h = harness
    h.env.ctx.config = Config(
        mode="shared",
        health_url=h.ctx.config.health_url,
        updates_base_url=h.ctx.config.updates_base_url,
        opt_dir=h.ctx.config.opt_dir,
    )
    publish(h, NEW)
    job = run_apply(h)
    assert job["state"] == "succeeded", job
    paths = h.ctx.paths
    assert not (paths.systemd_system_dir / "meshbox-firstboot.service").exists()
    assert not paths.firstboot_script.exists()
    assert not (paths.journald_conf_d / "meshbox.conf").exists()


@pytest.mark.linux
def test_apply_without_database_skips_backup(harness: Harness) -> None:
    h = harness
    (h.ctx.paths.meshbox_var_dir / "meshbox.db").unlink()
    publish(h, NEW)
    job = run_apply(h)
    assert job["state"] == "succeeded"
    assert job["result"]["backup"] is None
    assert job["result"]["migrated"] is False


@pytest.mark.linux
def test_rollback_command_restores_after_migration(harness: Harness) -> None:
    h = harness
    install_fake_release(h, NEW)
    point_current(h, NEW)
    backup = h.ctx.paths.meshbox_var_dir / "backups" / f"meshbox-20261020-pre-{NEW}.db.gz"
    backup.write_bytes(b"respaldo")
    update.write_state(
        h.ctx,
        {"current": NEW, "previous": OLD, "migrated": True, "backup": str(backup)},
    )
    h.healthy = {OLD}
    result = update.rollback(h.ctx, {})
    h.ctx.jobs.wait_all(30)
    job = h.ctx.jobs.get(result["job"])
    assert job["state"] == "succeeded", job
    assert job["result"] == {"version": OLD, "previous": NEW, "db_restored": True}
    assert h.current() == OLD
    assert len(h.restored) == 1
    state = update.read_state(h.ctx)
    assert state["current"] == OLD
    assert state["rolled_back_from"] == NEW


@pytest.mark.linux
def test_rollback_command_errors(harness: Harness) -> None:
    h = harness
    with pytest.raises(CommandError, match="versión actual"):
        update.rollback(h.ctx, {"version": OLD})
    with pytest.raises(CommandError, match="no está instalada"):
        update.rollback(h.ctx, {"version": "0.0.9"})
    h.healthy = set()
    result = update.rollback(h.ctx, {"version": "0.0.3"})
    h.ctx.jobs.wait_all(30)
    job = h.ctx.jobs.get(result["job"])
    assert job["state"] == "failed"
    assert "no respondió" in job["message"]


@pytest.mark.linux
def test_rollback_without_previous(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    with pytest.raises(CommandError, match="no hay una versión instalada"):
        update.rollback(env.ctx, {})
    releases = env.ctx.config.opt_dir / "releases" / OLD
    (releases / ".venv/bin").mkdir(parents=True)
    (releases / ".venv/bin/python").write_text("")
    (releases / update.INSTALLED_MARKER).write_text(OLD)
    (env.ctx.config.opt_dir / "current").symlink_to(f"releases/{OLD}")
    with pytest.raises(CommandError, match="no hay una versión anterior"):
        update.rollback(env.ctx, {})


@pytest.mark.linux
def test_info_and_previous(harness: Harness) -> None:
    h = harness
    info = update.info(h.ctx, {})
    assert info["current"] == OLD
    assert info["installed"] == ["0.0.1", "0.0.2", "0.0.3", OLD]
    assert info["previous"] == "0.0.3"
    assert info["last_update"] is None
    assert info["updates_base_url"] == h.ctx.config.updates_base_url
    update.write_state(h.ctx, {"current": OLD, "previous": "0.0.1"})
    assert update.previous_version(h.ctx, OLD) == "0.0.1"


@pytest.mark.linux
def test_prune_keeps_current_and_two_previous(harness: Harness) -> None:
    h = harness
    install_fake_release(h, "0.3.0")  # una versión nueva que falló: se borra
    removed = update.prune_releases(h.ctx, protect=set())
    assert sorted(removed) == ["0.0.1", "0.3.0"]
    assert sorted(p.name for p in h.releases().iterdir()) == ["0.0.2", "0.0.3", OLD]


@pytest.mark.linux
def test_install_system_files_is_idempotent(harness: Harness) -> None:
    h = harness
    release = h.releases() / OLD
    first = update.install_system_files(h.ctx, release)
    assert first == {"privd": True, "units": True, "mosquitto": True, "other": True}
    second = update.install_system_files(h.ctx, release)
    assert second == {"privd": False, "units": False, "mosquitto": False, "other": False}
    stale = h.ctx.paths.privd_lib_dir / "commands" / "viejo.py"
    stale.write_text("")
    assert update.install_system_files(h.ctx, release)["privd"] is True
    assert not stale.exists()
