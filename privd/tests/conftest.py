"""Configuración de las pruebas de privd.

privd no es un paquete instalable: se agrega su carpeta a sys.path para importar
`meshbox_privd` y `commands` igual que lo hace el servicio en la Pi.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PRIVD_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
for directory in (PRIVD_DIR, TESTS_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from privd_testkit import Env, make_env  # noqa: E402


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if sys.platform.startswith("linux"):
        return
    skip = pytest.mark.skip(reason="requiere Linux (AF_UNIX, permisos POSIX o enlaces)")
    for item in items:
        if "linux" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return make_env(tmp_path)


@pytest.fixture
def shared_env(tmp_path: Path) -> Env:
    return make_env(tmp_path, mode="shared")
