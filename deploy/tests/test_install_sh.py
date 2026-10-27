"""Pruebas de deploy/install.sh sin root: opciones, verificación de firma y sumas, paquete,
puertos de config.toml, Mosquitto previo y limpieza de versiones viejas.

Se incluye (`source`) una copia del instalador con rutas temporales y una clave pública de
prueba en lugar de la embebida; nada toca el sistema. Requieren bash y OpenSSL 3 (Linux).
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

INSTALL_SH = Path(__file__).resolve().parents[1] / "install.sh"

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux") or shutil.which("bash") is None,
    reason="requiere Linux con bash",
)


def openssl() -> str:
    path = shutil.which("openssl")
    if path is None:
        pytest.skip("sin OpenSSL")
    return path


def run_installer(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(INSTALL_SH), *args], capture_output=True, text=True, check=False, timeout=60
    )


@pytest.fixture
def keys(tmp_path: Path) -> tuple[Path, Path]:
    private = tmp_path / "privada.pem"
    public = tmp_path / "publica.pem"
    subprocess.run(
        [openssl(), "genpkey", "-algorithm", "ed25519", "-out", str(private)], check=True
    )
    subprocess.run(
        [openssl(), "pkey", "-in", str(private), "-pubout", "-out", str(public)], check=True
    )
    return private, public


@pytest.fixture
def installer(tmp_path: Path, keys: tuple[Path, Path]) -> Path:
    """Copia de install.sh con rutas bajo tmp_path y la clave pública de prueba."""
    root = tmp_path / "raiz"
    root.mkdir()
    text = INSTALL_SH.read_text(encoding="utf-8")
    text = re.sub(
        r"readonly MESHBOX_RELEASE_PUBKEY='-----BEGIN PUBLIC KEY-----\n.*?\n"
        r"-----END PUBLIC KEY-----'",
        "readonly MESHBOX_RELEASE_PUBKEY='" + keys[1].read_text().strip() + "'",
        text,
        flags=re.DOTALL,
    )
    for name, path in {
        "OPT_DIR": "/opt/meshbox",
        "PRIVD_CONF_DIR": "/etc/meshbox-privd",
        "ETC_DIR": "/etc/meshbox",
        "MOSQ_DIR": "/etc/mosquitto",
    }.items():
        text = text.replace(f"readonly {name}={path}\n", f"readonly {name}={root}{path}\n")
    copy = tmp_path / "install.sh"
    copy.write_text(text, encoding="utf-8")
    return copy


def bash(installer: Path, script: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Incluye el instalador y ejecuta `script` (funciones sueltas)."""
    prelude = f'set -Eeuo pipefail\nsource "{installer}"\n'
    return subprocess.run(
        ["bash", "-c", prelude + script],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        cwd=cwd,
    )


def make_package(base: Path, version: str = "0.2.0", *, sign_key: Path | None = None) -> Path:
    """Arma meshbox-<v>-linux-aarch64.tar.gz con SHA256SUMS y (opcional) la firma."""
    tree = base / "arbol" / f"meshbox-{version}"
    files = {
        "VERSION": f"{version}\n",
        f"wheels/meshbox-{version}-py3-none-any.whl": "rueda",
        "privd/meshbox_privd.py": "# privd\n",
        "privd/commands/__init__.py": "",
        "deploy/systemd/meshbox.service": "[Unit]\n",
        "deploy/mosquitto/meshbox.conf": "listener 1883\n",
        "install.sh": "#!/bin/sh\n",
    }
    for rel, content in files.items():
        path = tree / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    out = base / "publicado"
    out.mkdir(parents=True, exist_ok=True)
    tarball = out / f"meshbox-{version}-linux-aarch64.tar.gz"
    with tarfile.open(tarball, "w:gz") as tar:
        tar.add(tree, arcname=f"meshbox-{version}")
    digest = hashlib.sha256(tarball.read_bytes()).hexdigest()
    (out / "SHA256SUMS").write_text(f"{digest}  {tarball.name}\n")
    if sign_key is not None:
        subprocess.run(
            [
                openssl(),
                "pkeyutl",
                "-sign",
                "-inkey",
                str(sign_key),
                "-rawin",
                "-in",
                str(out / "SHA256SUMS"),
                "-out",
                str(out / "SHA256SUMS.sig"),
            ],
            check=True,
        )
    return tarball


# ---------------------------------------------------------------------------
# Opciones
# ---------------------------------------------------------------------------


def test_help() -> None:
    proc = run_installer("--help")
    assert proc.returncode == 0
    assert "--shared" in proc.stdout
    assert "--insecure-skip-signature" in proc.stdout


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--version", "1.0"], "X.Y.Z"),
        (["--updates-url", "ftp://x"], "URL"),
        (["--updates-url", "https://x/a b"], "URL"),
        (["--site-slug", "Viedma"], "--site-slug"),
        (["--mqtt-root", "msh/#"], "--mqtt-root"),
        (["--mqtt-root", "/msh/AR"], "--mqtt-root"),
        (["--hostname", "-malo"], "--hostname"),
        (["--shared", "--appliance"], "excluyentes"),
        (["--desconocida"], "desconocida"),
        (["--from"], "--from"),
    ],
)
def test_invalid_options(args: list[str], message: str) -> None:
    proc = run_installer(*args)
    assert proc.returncode == 1
    assert message in proc.stderr


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="corre como root")
def test_requires_root() -> None:
    proc = run_installer("--shared", "--from", "/no/existe.tar.gz")
    assert proc.returncode == 1
    assert "root" in proc.stderr


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="corre como root")
def test_get_sh_requires_root() -> None:
    get_sh = INSTALL_SH.parent / "get.sh"
    proc = subprocess.run(
        ["bash", str(get_sh), "--shared"], capture_output=True, text=True, check=False, timeout=60
    )
    assert proc.returncode == 1
    assert "sudo" in proc.stderr


def test_site_slug_sets_default_mqtt_root(installer: Path) -> None:
    proc = bash(installer, 'parse_args --site-slug viedma; echo "$MQTT_ROOT"')
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "msh/AR/viedma"


# ---------------------------------------------------------------------------
# Firma y sumas
# ---------------------------------------------------------------------------


def verify(installer: Path, tmp_path: Path, tarball: Path, insecure: int = 0):  # type: ignore[no-untyped-def]
    stage = tmp_path / "stage"
    stage.mkdir(exist_ok=True)
    return bash(installer, f'STAGE="{stage}"; INSECURE={insecure}; verify_tarball "{tarball}"')


def test_verify_tarball_ok(installer: Path, tmp_path: Path, keys: tuple[Path, Path]) -> None:
    tarball = make_package(tmp_path, sign_key=keys[0])
    proc = verify(installer, tmp_path, tarball)
    assert proc.returncode == 0, proc.stderr
    assert "Firma Ed25519 de SHA256SUMS verificada" in proc.stdout
    assert "Suma SHA-256" in proc.stdout


def test_verify_rejects_other_key(installer: Path, tmp_path: Path) -> None:
    other = tmp_path / "otra.pem"
    subprocess.run([openssl(), "genpkey", "-algorithm", "ed25519", "-out", str(other)], check=True)
    tarball = make_package(tmp_path, sign_key=other)
    proc = verify(installer, tmp_path, tarball)
    assert proc.returncode == 1
    assert "no es válida" in proc.stderr


def test_verify_rejects_tampered_sums(
    installer: Path, tmp_path: Path, keys: tuple[Path, Path]
) -> None:
    tarball = make_package(tmp_path, sign_key=keys[0])
    sums = tarball.parent / "SHA256SUMS"
    text = sums.read_text()
    sums.write_text(("0" if text[0] != "0" else "1") + text[1:])
    proc = verify(installer, tmp_path, tarball)
    assert proc.returncode == 1
    assert "no es válida" in proc.stderr


def test_verify_rejects_tampered_package(
    installer: Path, tmp_path: Path, keys: tuple[Path, Path]
) -> None:
    tarball = make_package(tmp_path, sign_key=keys[0])
    with open(tarball, "ab") as fh:
        fh.write(b"basura")
    proc = verify(installer, tmp_path, tarball)
    assert proc.returncode == 1
    assert "no coincide" in proc.stderr


def test_verify_rejects_short_signature(
    installer: Path, tmp_path: Path, keys: tuple[Path, Path]
) -> None:
    tarball = make_package(tmp_path, sign_key=keys[0])
    sig = tarball.parent / "SHA256SUMS.sig"
    sig.write_bytes(sig.read_bytes()[:32])
    proc = verify(installer, tmp_path, tarball)
    assert proc.returncode == 1
    assert "64 bytes" in proc.stderr


def test_verify_requires_signature_files(installer: Path, tmp_path: Path) -> None:
    tarball = make_package(tmp_path)
    proc = verify(installer, tmp_path, tarball)
    assert proc.returncode == 1
    assert "insecure-skip-signature" in proc.stderr


def test_verify_package_not_listed(
    installer: Path, tmp_path: Path, keys: tuple[Path, Path]
) -> None:
    tarball = make_package(tmp_path, sign_key=keys[0])
    renamed = tarball.with_name("meshbox-0.3.0-linux-aarch64.tar.gz")
    tarball.rename(renamed)
    proc = verify(installer, tmp_path, renamed)
    assert proc.returncode == 1
    assert "no figura" in proc.stderr


def test_insecure_still_checks_sums(installer: Path, tmp_path: Path) -> None:
    tarball = make_package(tmp_path)
    proc = verify(installer, tmp_path, tarball, insecure=1)
    assert proc.returncode == 0, proc.stderr
    assert "NO se verifica la firma" in proc.stderr
    with open(tarball, "ab") as fh:
        fh.write(b"x")
    proc = verify(installer, tmp_path, tarball, insecure=1)
    assert proc.returncode == 1


# ---------------------------------------------------------------------------
# Paquete
# ---------------------------------------------------------------------------


def test_acquire_package_from_tarball(
    installer: Path, tmp_path: Path, keys: tuple[Path, Path]
) -> None:
    tarball = make_package(tmp_path, sign_key=keys[0])
    stage = tmp_path / "stage"
    stage.mkdir()
    proc = bash(
        installer,
        f'STAGE="{stage}"; FROM="{tarball}"; acquire_package; echo "V=$VERSION"; echo "P=$PKG_DIR"',
    )
    assert proc.returncode == 0, proc.stderr
    assert "V=0.2.0" in proc.stdout
    assert f"P={stage}/extract/meshbox-0.2.0" in proc.stdout


def test_acquire_package_directory_needs_insecure(installer: Path, tmp_path: Path) -> None:
    make_package(tmp_path)
    tree = tmp_path / "arbol" / "meshbox-0.2.0"
    proc = bash(installer, f'STAGE="{tmp_path}"; FROM="{tree}"; acquire_package')
    assert proc.returncode == 1
    assert "carpeta no se puede verificar" in proc.stderr
    proc = bash(installer, f'STAGE="{tmp_path}"; FROM="{tree}"; INSECURE=1; acquire_package')
    assert proc.returncode == 0, proc.stderr


def test_acquire_package_version_mismatch(
    installer: Path, tmp_path: Path, keys: tuple[Path, Path]
) -> None:
    tarball = make_package(tmp_path, sign_key=keys[0])
    stage = tmp_path / "stage"
    stage.mkdir()
    proc = bash(installer, f'STAGE="{stage}"; FROM="{tarball}"; VERSION_ARG=0.9.9; acquire_package')
    assert proc.returncode == 1
    assert "no de 0.9.9" in proc.stderr


def test_extract_rejects_unexpected_name(installer: Path, tmp_path: Path) -> None:
    other = tmp_path / "otro.tar.gz"
    other.write_bytes(b"")
    proc = bash(installer, f'STAGE="{tmp_path}"; extract_tarball "{other}"')
    assert proc.returncode == 1
    assert "inesperado" in proc.stderr


# ---------------------------------------------------------------------------
# Modo, puertos y Mosquitto
# ---------------------------------------------------------------------------


def test_config_port(installer: Path, tmp_path: Path) -> None:
    proc = bash(installer, "config_port public_bind 8091")
    assert proc.stdout.strip() == "8091"
    config = tmp_path / "raiz/etc/meshbox/config.toml"
    config.parent.mkdir(parents=True)
    config.write_text('[server]\npublic_bind = "127.0.0.1:9191"\nlan_bind = "roto"\n')
    proc = bash(installer, "config_port public_bind 8091; config_port lan_bind 8090")
    assert proc.stdout.split() == ["9191", "8090"]


def test_resolve_mode_and_ports(installer: Path, tmp_path: Path) -> None:
    proc = bash(installer, 'resolve_mode; resolve_ports; echo "$MODE $LAN_PORT $PUBLIC_PORT"')
    assert proc.stdout.strip() == "appliance 80 8081"
    conf = tmp_path / "raiz/etc/meshbox-privd/privd.toml"
    conf.parent.mkdir(parents=True)
    conf.write_text('mode = "shared"\n')
    proc = bash(installer, 'resolve_mode; resolve_ports; echo "$MODE $LAN_PORT $ADMIN_PORT"')
    assert proc.stdout.strip() == "shared 8090 8092"
    proc = bash(installer, "MODE=appliance; resolve_mode")
    assert proc.returncode == 1
    assert "--change-mode" in proc.stderr
    proc = bash(installer, "MODE=appliance; CHANGE_MODE=1; resolve_mode; echo $MODE")
    assert proc.stdout.strip() == "appliance"
    proc = bash(installer, "MODE=shared; HOSTNAME_ARG=x; resolve_mode")
    assert proc.returncode == 1


def test_check_mosquitto_config(installer: Path, tmp_path: Path) -> None:
    mosq = tmp_path / "raiz/etc/mosquitto"
    (mosq / "conf.d").mkdir(parents=True)
    (mosq / "mosquitto.conf").write_text(
        "pid_file /run/mosquitto/mosquitto.pid\npersistence true\n"
        "include_dir /etc/mosquitto/conf.d\n# listener 1883 comentado\n"
    )
    (mosq / "conf.d/meshbox.conf").write_text("listener 1883\n")
    assert bash(installer, "check_mosquitto_config").returncode == 0
    (mosq / "conf.d/otro.conf").write_text("listener 1884\n")
    proc = bash(installer, "check_mosquitto_config")
    assert proc.returncode == 1
    assert "otro.conf" in proc.stderr
    (mosq / "conf.d/otro.conf").unlink()
    (mosq / "mosquitto.conf").write_text("listener 1883\nallow_anonymous true\n")
    assert bash(installer, "check_mosquitto_config").returncode == 1


@pytest.mark.skipif(shutil.which("ss") is None, reason="sin ss (iproute2)")
def test_check_port_uses_effective_uid(installer: Path) -> None:
    import getpass
    import socket

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        me = getpass.getuser()
        proc = bash(installer, f'check_port {port} "prueba" "{me}"; echo libre')
        assert proc.returncode == 0, proc.stderr
        assert "libre" in proc.stdout
        proc = bash(installer, f'check_port {port} "prueba" mosquitto')
        assert proc.returncode == 1
        assert f"El puerto {port} (prueba) está ocupado" in proc.stderr
        assert f"usuario {me}" in proc.stderr
    proc = bash(installer, f'check_port {port} "prueba" mosquitto; echo libre')
    assert proc.returncode == 0
    assert "libre" in proc.stdout


# ---------------------------------------------------------------------------
# Versiones viejas
# ---------------------------------------------------------------------------


def test_prune_releases(installer: Path, tmp_path: Path) -> None:
    releases = tmp_path / "raiz/opt/meshbox/releases"
    for version in ("0.0.1", "0.0.2", "0.0.10", "0.1.0", "0.2.0", "0.3.0", "dev"):
        (releases / version).mkdir(parents=True)
    proc = bash(installer, "prune_releases 0.2.0")
    assert proc.returncode == 0, proc.stderr
    assert sorted(p.name for p in releases.iterdir()) == [
        "0.0.10",
        "0.1.0",
        "0.2.0",
        "0.3.0",
        "dev",
    ]


def test_package_digest_changes_with_wheels(installer: Path, tmp_path: Path) -> None:
    make_package(tmp_path)
    tree = tmp_path / "arbol" / "meshbox-0.2.0"
    first = bash(installer, f'PKG_DIR="{tree}"; package_digest').stdout.strip()
    (tree / "wheels/otra-1.0-py3-none-any.whl").write_text("x")
    second = bash(installer, f'PKG_DIR="{tree}"; package_digest').stdout.strip()
    assert re.fullmatch(r"[0-9a-f]{64}", first)
    assert first != second


def test_embedded_key_matches_privd() -> None:
    install_key = re.search(
        r"-----BEGIN PUBLIC KEY-----\n(.+?)\n-----END PUBLIC KEY-----",
        INSTALL_SH.read_text(encoding="utf-8"),
        re.DOTALL,
    )
    update_py = INSTALL_SH.parents[1] / "privd" / "commands" / "update.py"
    privd_key = re.search(
        r"-----BEGIN PUBLIC KEY-----\n(.+?)\n-----END PUBLIC KEY-----",
        update_py.read_text(encoding="utf-8"),
        re.DOTALL,
    )
    assert install_key and privd_key
    assert install_key.group(1).strip() == privd_key.group(1).strip()
