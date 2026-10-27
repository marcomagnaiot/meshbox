"""Contrato privd ↔ backend.

El backend usa `FakePrivClient` en Windows y en sus pruebas; si sus respuestas no tienen la
misma forma que las de privd, el panel funciona en la PC y falla en la Pi. Cada prueba ejecuta
el comando real de privd (con systemctl/timedatectl simulados por su kit de pruebas) y lo
compara con el simulado, los dos pasados por `normalize` como hace el cliente del socket.

Vive en las pruebas del backend porque necesita los dos lados instalados (el job `privd` del CI
corre sin meshbox).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

from meshbox.system.privclient import FakePrivClient, PrivError, normalize

PRIVD = Path(__file__).resolve().parents[3] / "privd"
for directory in (PRIVD, PRIVD / "tests"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from privd_testkit import Env, make_env, ok  # noqa: E402

from commands import cloudflared, mosquitto, services, system, update  # noqa: E402


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return make_env(tmp_path)


SHOW = (
    "Id={unit}\nLoadState=loaded\nActiveState={state}\nSubState=running\n"
    "UnitFileState={enabled}\nMainPID=812\nNRestarts=0\nResult=success\n"
    "ActiveEnterTimestamp=@1792465562\n"
)


def simulated(cmd: str, **args: Any) -> dict[str, Any]:
    return asyncio.run(FakePrivClient("appliance").call(cmd, **args))


def show(env: Env, unit: str, state: str = "active", enabled: str = "enabled") -> None:
    env.runner.on(
        ["/usr/bin/systemctl", "show"], ok(SHOW.format(unit=unit, state=state, enabled=enabled))
    )


def test_service_status(env: Env) -> None:
    show(env, "meshbox.service")
    real = normalize("service.status", services.status(env.ctx, {"name": "meshbox"}))
    assert set(real) == set(simulated("service.status", name="meshbox"))
    assert real["active"] is True and real["state"] == "active"
    assert real["enabled"] is True and real["unit_file_state"] == "enabled"
    assert real["since"] == 1792465562 and real["pid"] == 812


def test_service_status_failed(env: Env) -> None:
    show(env, "mosquitto.service", state="failed", enabled="disabled")
    real = normalize("service.status", services.status(env.ctx, {"name": "mosquitto"}))
    assert real["active"] is False and real["state"] == "failed" and real["enabled"] is False


def test_mosquitto_status(env: Env) -> None:
    show(env, "mosquitto.service")
    real = normalize("mosquitto.status", mosquitto.status(env.ctx, {}))
    assert set(real) == set(simulated("mosquitto.status"))
    assert real["accounts"] == [] and real["acl_present"] is False


def test_cloudflared_status(env: Env) -> None:
    show(env, "meshbox-cloudflared.service", state="inactive", enabled="disabled")
    real = normalize("cloudflared.status", cloudflared.status(env.ctx, {}))
    assert set(real) == set(simulated("cloudflared.status"))
    assert real["active"] is False and real["token_configured"] is False


def test_cloudflared_enable_needs_token() -> None:
    with pytest.raises(PrivError) as e:
        simulated("cloudflared.enable")
    assert e.value.code == "command_failed"


def test_time_status(env: Env) -> None:
    env.runner.on(
        ["/usr/bin/timedatectl", "show"],
        ok(
            "Timezone=America/Argentina/Buenos_Aires\nLocalRTC=no\nCanNTP=yes\nNTP=yes\n"
            "NTPSynchronized=yes\nTimeUSec=Tue 2026-10-20 10:00:00 -03\n"
        ),
    )
    real = system.time_status(env.ctx, {})
    assert set(real) == set(simulated("time.status"))
    assert real["ntp_synchronized"] is True


def test_system_info(env: Env) -> None:
    real = system.info(env.ctx, {})
    assert set(real) == set(simulated("system.info"))


def test_update_info(env: Env) -> None:
    real = update.info(env.ctx, {})
    assert set(real) == set(simulated("update.info"))


def test_restart_shape(env: Env) -> None:
    real = services.restart(env.ctx, {"name": "mosquitto"})
    assert set(real) == set(simulated("service.restart", name="mosquitto"))
