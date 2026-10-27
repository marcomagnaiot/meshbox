"""Lectura de /etc/meshbox-privd/privd.toml con valores seguros por defecto."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import meshbox_privd
from commands.core import Config


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "privd.toml"
    path.write_text(text, encoding="utf-8")
    if os.name == "posix":
        path.chmod(0o644)
        tmp_path.chmod(0o755)
    return path


def load(path: Path) -> tuple[Config, list[str]]:
    uid = os.geteuid() if hasattr(os, "geteuid") else 0
    return meshbox_privd.load_config(path, trusted_uids={0, uid})


def test_missing_file_uses_safe_defaults(tmp_path: Path) -> None:
    config, warnings = load(tmp_path / "no-existe.toml")
    assert config.mode == "shared"
    assert config.updates_base_url == ""
    assert config.effective_health_url == "http://127.0.0.1:8091/api/v1/health"
    assert any("no existe" in w for w in warnings)


def test_full_appliance_config(tmp_path: Path) -> None:
    # Un ejecutable propio con permisos conocidos: el de la máquina puede ser escribible por el
    # grupo (en GitHub Actions lo es) y privd lo rechaza a propósito.
    python = "/usr/bin/python3"
    if os.name == "posix":
        fake_python = tmp_path / "python3"
        fake_python.write_text("#!/bin/sh\n")
        fake_python.chmod(0o755)
        python = str(fake_python)
    path = write(
        tmp_path,
        f"""
mode = "appliance"
health_url = "http://127.0.0.1:8081/api/v1/health"
updates_base_url = "https://github.com/ejemplo/meshbox/releases/download"
opt_dir = "/opt/meshbox"
python = "{python}"
idle_timeout_s = 300
""",
    )
    config, warnings = load(path)
    assert warnings == []
    assert config.mode == "appliance"
    assert config.health_url == "http://127.0.0.1:8081/api/v1/health"
    assert config.updates_base_url.startswith("https://github.com/")
    assert config.opt_dir == Path("/opt/meshbox")
    assert config.idle_timeout_s == 300


def test_effective_health_url_by_mode() -> None:
    assert Config(mode="appliance").effective_health_url.endswith(":8081/api/v1/health")
    assert Config(mode="shared").effective_health_url.endswith(":8091/api/v1/health")


@pytest.mark.parametrize(
    ("text", "field"),
    [
        ('mode = "root"', "mode"),
        ("mode = 1", "mode"),
        ('health_url = "http://192.168.0.40:8091/api/v1/health"', "health_url"),
        ('health_url = "https://ejemplo.com/health"', "health_url"),
        ('updates_base_url = "ftp://ejemplo.com/x"', "updates_base_url"),
        ('updates_base_url = "https://ejemplo.com/a b"', "updates_base_url"),
        ('updates_base_url = "https://"', "updates_base_url"),
        ('opt_dir = "relativo/meshbox"', "opt_dir"),
        ('opt_dir = "/opt/../etc"', "opt_dir"),
        ('python = "python3"', "python"),
        pytest.param('python = "/no/existe/python3"', "python", marks=pytest.mark.linux),
        ("idle_timeout_s = -1", "idle_timeout_s"),
        ("idle_timeout_s = true", "idle_timeout_s"),
        ('desconocida = "x"', "desconocida"),
    ],
)
def test_invalid_values_fall_back(tmp_path: Path, text: str, field: str) -> None:
    config, warnings = load(write(tmp_path, text))
    assert any(field in w for w in warnings), warnings
    assert config.mode in ("shared", "appliance")
    defaults = Config()
    if field == "mode":
        assert config.mode == "shared"
    if field == "opt_dir":
        assert config.opt_dir == defaults.opt_dir
    if field == "python":
        assert config.python == defaults.python


def test_file_url_allowed_for_tests(tmp_path: Path) -> None:
    config, warnings = load(write(tmp_path, 'updates_base_url = "file:///srv/releases"'))
    assert warnings == []
    assert config.updates_base_url == "file:///srv/releases"


def test_invalid_toml(tmp_path: Path) -> None:
    config, warnings = load(write(tmp_path, "mode = [sin cerrar"))
    assert config.mode == "shared"
    assert any("no se pudo leer" in w for w in warnings)


@pytest.mark.linux
def test_group_writable_file_is_ignored(tmp_path: Path) -> None:
    path = write(tmp_path, 'mode = "appliance"')
    path.chmod(0o664)
    config, warnings = load(path)
    assert config.mode == "shared"
    assert any("escribible" in w for w in warnings)


@pytest.mark.linux
def test_writable_directory_is_ignored(tmp_path: Path) -> None:
    path = write(tmp_path, 'mode = "appliance"')
    tmp_path.chmod(0o777)
    try:
        config, _ = load(path)
    finally:
        tmp_path.chmod(0o755)
    assert config.mode == "shared"


@pytest.mark.linux
def test_untrusted_owner_is_ignored(tmp_path: Path) -> None:
    path = write(tmp_path, 'mode = "appliance"')
    if os.geteuid() == 0:
        pytest.skip("como root el archivo es de un dueño confiable")
    config, warnings = meshbox_privd.load_config(path, trusted_uids={0})
    assert config.mode == "shared"
    assert any("root" in w for w in warnings)


@pytest.mark.linux
def test_python_must_not_be_group_writable(tmp_path: Path) -> None:
    fake_python = tmp_path / "python3"
    fake_python.write_text("#!/bin/sh\n")
    fake_python.chmod(0o775)
    config, warnings = load(write(tmp_path, f'python = "{fake_python}"'))
    assert config.python == "/usr/bin/python3"
    assert any("python" in w for w in warnings)
    fake_python.chmod(0o755)
    config, warnings = load(write(tmp_path, f'python = "{fake_python}"'))
    assert config.python == str(fake_python)
