"""Integración con Mosquitto real (sección 27): envelopes grabados → broker → conector → base.

Usa `MESHBOX_TEST_MQTT_HOST`/`MESHBOX_TEST_MQTT_PORT` (CI) o levanta un Mosquitto local en un
puerto libre si el binario está instalado. Si no hay ninguno, se saltea.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from meshbox.config import MqttConnectorCfg
from meshbox.connectors.mqtt import MqttConnector
from meshbox.devtools import sim

from ..conftest import FIXTURES, Pipe

pytestmark = pytest.mark.integration
ROOT = "msh/AR/prueba"


def _mosquitto_binary() -> str | None:
    found = shutil.which("mosquitto")
    if found:
        return found
    for candidate in (
        Path(r"C:\Program Files\mosquitto\mosquitto.exe"),
        Path("/usr/sbin/mosquitto"),
    ):
        if candidate.exists():
            return str(candidate)
    return None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def broker(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[str, int]]:
    host = os.environ.get("MESHBOX_TEST_MQTT_HOST")
    if host:
        yield host, int(os.environ.get("MESHBOX_TEST_MQTT_PORT", "1883"))
        return
    binary = _mosquitto_binary()
    if binary is None:
        pytest.skip("no hay Mosquitto disponible")
    port = _free_port()
    conf = tmp_path_factory.mktemp("mosq") / "test.conf"
    conf.write_text(
        f"listener {port} 127.0.0.1\nallow_anonymous true\npersistence false\n", encoding="utf-8"
    )
    proc = subprocess.Popen(
        [binary, "-c", str(conf)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    deadline = time.time() + 10
    while time.time() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
        time.sleep(0.1)
    else:
        proc.kill()
        pytest.skip("Mosquitto no arrancó")
    yield "127.0.0.1", port
    proc.terminate()
    proc.wait(timeout=10)


async def test_envelopes_through_real_broker(pipe: Pipe, broker: tuple[str, int]) -> None:
    host, port = broker
    statuses: list[str] = []
    conn = MqttConnector(
        MqttConnectorCfg(
            id="mqtt-test", host=host, port=port, topics=[f"{ROOT}/2/e/#", f"{ROOT}/2/map/#"]
        ),
        password_resolver=lambda _ref: None,
        on_status=lambda st: statuses.append(st.state),
    )

    async def emit(raw):  # type: ignore[no-untyped-def]
        pipe.proc.process(raw)

    await conn.start(emit)
    for _ in range(100):
        if conn.status().state == "connected":
            break
        await asyncio.sleep(0.05)
    assert conn.status().state == "connected", statuses
    sent = await sim.publish(
        FIXTURES / "sim-6h.jsonl",
        host=host,
        port=port,
        root=ROOT,
        username=None,
        password=None,
        speed=0,
        limit=400,
    )
    assert sent == 400
    for _ in range(100):
        if conn.status().packets >= sent:
            break
        await asyncio.sleep(0.05)
    await conn.stop()
    await pipe.flush()
    st = conn.status()
    assert st.packets == sent and st.invalid == 0
    receptions = int(await pipe.scalar("SELECT count(*) FROM receptions"))  # type: ignore[call-overload]
    packets = int(await pipe.scalar("SELECT count(*) FROM packets"))  # type: ignore[call-overload]
    assert receptions == sent and 0 < packets < receptions  # hubo duplicados entre gateways
    gateways = {r["gateway"] for r in await pipe.rows("SELECT DISTINCT gateway FROM receptions")}
    assert gateways == {"!a1b2c3d4", "!a1b2c3d5"}  # gateway tomado del envelope
    assert await pipe.scalar("SELECT count(*) FROM nodes") > 0  # type: ignore[operator]
    if sys.platform == "win32":
        assert "connecting" in statuses
