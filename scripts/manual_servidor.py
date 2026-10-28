"""Servidor de prueba para las capturas del manual (docs/manual.md).

Arranca como una instalación nueva (sin usuarios, código de configuración ABCD2345), con la red
simulada de las pruebas reproduciéndose en vivo y una placa simulada conectada por USB para el
Cliente Meshtastic. Los servicios del sistema (privd) también son simulados: no toca la red, el
WiFi ni Mosquitto de la PC.

    uv run python scripts/manual_servidor.py <carpeta de datos> [puerto]

Con una carpeta nueva empieza de cero; con la misma carpeta sigue donde quedó.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from tests.radio_fake import MY_ID, attach_fake_board  # noqa: E402

from meshbox.api.factory import create_app  # noqa: E402
from meshbox.app import Service, _make_server  # noqa: E402
from meshbox.config import SecretStore, load_config  # noqa: E402

CONFIG = """\
[site]
slug = "mired"
timezone = "America/Argentina/Buenos_Aires"
language = "es"

[host]
mode = "appliance"

[system]
privd = "fake"

[server]
lan_bind = "127.0.0.1:{port}"
public_bind = "127.0.0.1:{public}"
admin_remote_bind = ""

[paths]
db = "{data}/meshbox.db"
tiles = "{data}/tiles"
backups = "{data}/backups"
plugins = "{data}/plugins"
recordings = "{data}/rec"
tmp = "{data}/tmp"
secrets = "{data}/secrets.toml"
web = "{web}"

[[connectors]]
id = "replay"
kind = "replay"
enabled = true
file = "{fixture}"
speed = 10
loop = true
rebase_time = true

[privacy]
ignore_via_mqtt = true

[logging]
level = "WARNING"
json_output = false
"""


def prepare(data: Path, port: int) -> tuple[Path, bool]:
    """Escribe la configuración de una carpeta nueva y el código de configuración."""
    data.mkdir(parents=True, exist_ok=True)
    config = data / "config.toml"
    fresh = not config.exists()
    if fresh:
        config.write_text(
            CONFIG.format(
                port=port,
                public=port + 1,
                data=data.as_posix(),
                web=(ROOT / "frontend" / "build").as_posix(),
                fixture=(ROOT / "backend" / "tests" / "fixtures" / "sim-24h.jsonl").as_posix(),
            ),
            encoding="utf-8",
        )
    secrets = SecretStore(load_config(config).paths.secrets)
    if not secrets.data.setup_code:
        secrets.data.setup_code = "ABCD2345"
    secrets.save()
    return config, fresh


async def main(data: Path, port: int) -> None:
    config, fresh = prepare(data, port)
    service = Service(load_config(config), config, dev=True)
    await service.start()
    service.ready = True
    board, iface = attach_fake_board(service)
    iface.remote.delay_s = 2.4  # el nodo remoto contesta como con un par de saltos
    if fresh:
        now = time.time()
        for i, (to, ch, text) in enumerate(
            [
                ("^all", 0, "Hola malla, prueba desde el centro"),
                ("^all", 1, "¿Alguien en el canal Familia?"),
                (MY_ID, 0, "Te escribo directo, ¿me leés?"),
            ]
        ):
            board._track_message(
                {"id": 100 + i, "fromId": "!11112222", "toId": to, "channel": ch, "rxSnr": 7.5,
                 "rxRssi": -71, "hopStart": 3, "hopLimit": 2, "rxTime": now - 600 + i * 60,
                 "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": text}}
            )  # fmt: skip
    server = _make_server(create_app(service, "lan"), f"127.0.0.1:{port}")
    print(f"listo: http://127.0.0.1:{port} (datos en {data}, código ABCD2345)", flush=True)
    try:
        await server.serve()
    finally:
        await service.stop()


asyncio.run(main(Path(sys.argv[1]).resolve(), int(sys.argv[2]) if len(sys.argv) > 2 else 8120))
