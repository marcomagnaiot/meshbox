"""Carga de los scripts (tienen guiones en el nombre, no se importan como módulos comunes)."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent


def load_script(name: str) -> ModuleType:
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def sign_release() -> ModuleType:
    return load_script("sign-release")


@pytest.fixture(scope="session")
def build_release() -> ModuleType:
    return load_script("build-release")


def find_openssl3() -> str | None:
    """OpenSSL 3 (con `pkeyutl -rawin`); en Windows, el que trae Git."""
    candidates = [shutil.which("openssl")]
    candidates += [
        r"C:\Program Files\Git\mingw64\bin\openssl.exe",
        r"C:\Program Files\Git\usr\bin\openssl.exe",
    ]
    for candidate in candidates:
        if not candidate or not Path(candidate).exists():
            continue
        try:
            out = subprocess.run(
                [candidate, "version"], capture_output=True, text=True, check=False
            ).stdout
        except OSError:
            continue
        if out.startswith("OpenSSL 3"):
            return candidate
    return None


@pytest.fixture(scope="session")
def openssl() -> str:
    path = find_openssl3()
    if path is None:
        pytest.skip("sin OpenSSL 3")
    return path
