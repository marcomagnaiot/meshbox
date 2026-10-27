"""Funciones puras de scripts/build-release.py (sin red)."""

from __future__ import annotations

import hashlib
import tarfile
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        (
            "pydantic_core-2.50.1-cp313-cp313-manylinux_2_17_aarch64.manylinux2014_aarch64.whl",
            (
                "pydantic_core",
                "2.50.1",
                "cp313",
                "cp313",
                "manylinux_2_17_aarch64.manylinux2014_aarch64",
            ),
        ),
        ("http_ece-1.2.1-py2.py3-none-any.whl", ("http_ece", "1.2.1", "py2.py3", "none", "any")),
        ("pkg-1.0-1-py3-none-any.whl", ("pkg", "1.0", "py3", "none", "any")),
        ("no-es-rueda.tar.gz", None),
        ("mal-formada.whl", None),
    ],
)
def test_wheel_tags(build_release: ModuleType, filename: str, expected: object) -> None:
    assert build_release.wheel_tags(filename) == expected


@pytest.mark.parametrize(
    ("platform", "abi", "usable"),
    [
        ("manylinux_2_28_aarch64", "cp313", True),
        ("manylinux2014_aarch64", "abi3", True),
        ("manylinux_2_26_aarch64.manylinux_2_28_aarch64", "cp313", True),
        ("any", "none", True),
        ("manylinux_2_34_aarch64", "cp313", False),
        ("manylinux_2_28_x86_64", "cp313", False),
        ("musllinux_1_2_aarch64", "cp313", False),
        ("win_amd64", "cp313", False),
        ("manylinux_2_28_aarch64", "cp312", False),
    ],
)
def test_wheel_score(build_release: ModuleType, platform: str, abi: str, usable: bool) -> None:
    assert (build_release.wheel_score(platform, abi) is not None) is usable


def test_find_wheel_prefers_best_tag(build_release: ModuleType, tmp_path: Path) -> None:
    for name in (
        "orjson-3.13.0-cp313-cp313-manylinux_2_17_aarch64.manylinux2014_aarch64.whl",
        "orjson-3.13.0-cp313-cp313-manylinux_2_28_aarch64.whl",
        "orjson-3.13.0-cp313-cp313-win_amd64.whl",
        "orjson-3.12.0-cp313-cp313-manylinux_2_28_aarch64.whl",
    ):
        (tmp_path / name).write_text("")
    best = build_release.find_wheel(tmp_path, "orjson", "3.13.0")
    assert best.name == "orjson-3.13.0-cp313-cp313-manylinux_2_28_aarch64.whl"
    assert build_release.find_wheel(tmp_path, "Orjson", "9.9.9") is None


def test_normalize(build_release: ModuleType) -> None:
    assert build_release.normalize("Argon2-CFFI.bindings") == "argon2_cffi_bindings"


def test_embedded_keys_match(build_release: ModuleType) -> None:
    privd, install = build_release.embedded_keys()
    assert privd == install


def test_copy_privd_stamps_version(build_release: ModuleType, tmp_path: Path) -> None:
    build_release.copy_privd(tmp_path / "privd", "1.2.3")
    core = (tmp_path / "privd/commands/core.py").read_text(encoding="utf-8")
    assert 'PRIVD_VERSION = "1.2.3"' in core
    assert (tmp_path / "privd/meshbox_privd.py").exists()
    assert not list((tmp_path / "privd").rglob("test_*.py"))


def test_copy_deploy_excludes_image_and_tests(build_release: ModuleType, tmp_path: Path) -> None:
    build_release.copy_deploy(tmp_path / "deploy")
    names = {p.name for p in (tmp_path / "deploy").iterdir()}
    assert names == {
        "systemd",
        "mosquitto",
        "journald",
        "nm",
        "firstboot",
        "meshbox-privd.example.toml",
    }


def test_make_tarball_is_reproducible(build_release: ModuleType, tmp_path: Path) -> None:
    root = tmp_path / "meshbox-0.2.0"
    (root / "bin").mkdir(parents=True)
    (root / "bin/pmtiles").write_bytes(b"\x7fELF")
    (root / "install.sh").write_text("#!/bin/bash\n")
    (root / "VERSION").write_text("0.2.0\n")
    first = tmp_path / "a.tar.gz"
    second = tmp_path / "b.tar.gz"
    build_release.make_tarball(root, first, 1_700_000_000)
    (root / "VERSION").touch()  # cambiar el mtime del disco no cambia el paquete
    build_release.make_tarball(root, second, 1_700_000_000)
    assert (
        hashlib.sha256(first.read_bytes()).digest() == hashlib.sha256(second.read_bytes()).digest()
    )
    with tarfile.open(first) as tar:
        members = {m.name: m for m in tar.getmembers()}
    assert list(members) == [
        "meshbox-0.2.0",
        "meshbox-0.2.0/VERSION",
        "meshbox-0.2.0/bin",
        "meshbox-0.2.0/bin/pmtiles",
        "meshbox-0.2.0/install.sh",
    ]
    assert members["meshbox-0.2.0/install.sh"].mode == 0o755
    assert members["meshbox-0.2.0/bin/pmtiles"].mode == 0o755
    assert members["meshbox-0.2.0/VERSION"].mode == 0o644
    assert all(m.uid == 0 and m.uname == "root" for m in members.values())
    assert all(m.mtime == 1_700_000_000 for m in members.values())


def test_project_version(build_release: ModuleType) -> None:
    import tomllib

    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert build_release.project_version() == data["project"]["version"]
