"""Índice de rutas desde el OpenAPI de la aplicación (para el final de docs/api.md).

$env:PYTHONIOENCODING="utf-8"; uv run python scripts/gen-api-index.py > rutas.md
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "backend")

from meshbox.api.factory import create_app
from meshbox.app import Service
from tests.conftest import make_cfg


async def main() -> None:
    cfg = make_cfg(Path(tempfile.mkdtemp()))
    cfg.connectors = []
    service = Service(cfg, None, dev=True)
    await service.start()
    app = create_app(service, "lan").state_app
    rows = sorted(
        ((op.get("tags") or ["-"])[0], path, method.upper())
        for path, ops in app.openapi()["paths"].items()
        for method, op in ops.items()
    )
    current = None
    for tag, path, method in rows:
        if tag != current:
            print(f"\n### {tag}\n\n| Método | Ruta |\n|---|---|")
            current = tag
        print(f"| `{method}` | `{path}` |")
    await service.stop()


if __name__ == "__main__":
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    asyncio.run(main(), loop_factory=loop_factory)
