"""Administración remota de nodos por la malla (ADR 0017) contra un nodo simulado."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest
from meshtastic.protobuf import admin_pb2, localonly_pb2

from meshbox.api.factory import create_app
from meshbox.radio import remote as remote_mod
from meshbox.radio.remote import RemoteLimiter, get_remote

from ..radio_fake import MY_ID, MY_PUBLIC_KEY, REMOTE_ID
from .test_api import ADMIN_PW
from .test_radio import BASE, Client, radio  # noqa: F401

R = f"{BASE}/remote/{REMOTE_ID}"


@pytest.fixture(autouse=True)
def no_limit(radio: Client) -> None:  # noqa: F811
    get_remote(radio.service).limiters["usb-prueba"] = RemoteLimiter(gap_s=0, per_hour=10_000)


def test_every_module_has_a_request_type() -> None:
    names = admin_pb2.AdminMessage.ModuleConfigType.keys()
    for f in localonly_pb2.LocalModuleConfig.DESCRIPTOR.fields:
        if f.name != "version":
            rule = f.name.replace("_", "").upper() + "_CONFIG"
            assert remote_mod.MODULE_TYPES.get(f.name, rule) in names, f.name


async def test_info_without_transmitting(radio: Client) -> None:  # noqa: F811
    r = await radio.lan.get(R)
    assert r.status_code == 200, r.text
    info = r.json()
    assert info["board_public_key"] == base64.b64encode(MY_PUBLIC_KEY).decode()
    assert (
        info["has_pki"] and info["long_name"] == "Repetidor del cerro" and not info["admin_channel"]
    )
    sections = {s["name"]: s for s in info["sections"]}
    assert sections["lora"]["writable"] and not sections["security"]["writable"]
    assert sections["telemetry"]["kind"] == "module"
    assert radio.iface.sent == []
    assert (await radio.lan.get(f"{BASE}/remote/{MY_ID}")).status_code == 409
    assert (await radio.lan.get(f"{BASE}/remote/11112222")).status_code == 422


async def test_probe_and_read(radio: Client) -> None:  # noqa: F811
    r = await radio.lan.post(f"{R}/probe", headers=radio.h)
    assert r.status_code == 200, r.text
    assert r.json()["firmware"] == "2.7.15.test" and r.json()["role"] == "ROUTER"
    assert r.json()["hw_model"] == "TRACKER_T1000_E"
    assert radio.iface.sent[-1] == {"admin": 0x11112222, "pki": True, "ch": 0}

    lora = (await radio.lan.get(f"{R}/config/lora")).json()
    fields = {f["name"]: f for f in lora["fields"]}
    assert fields["tx_power"]["value"] == 27 and not fields["tx_power"]["readonly"]
    assert fields["region"]["value"] == "ANZ" and fields["region"]["readonly"]
    sec = (await radio.lan.get(f"{R}/config/security")).json()
    assert not sec["writable"]
    mqtt = await radio.lan.get(f"{R}/config/mqtt")
    assert mqtt.status_code == 200 and "clave-remota" not in mqtt.text
    assert "AAECAw" not in json.dumps(sec)  # claves enmascaradas
    assert (await radio.lan.get(f"{R}/config/nada")).status_code == 404


async def test_write_verify_and_backup(radio: Client, tmp_path: Path) -> None:  # noqa: F811
    r = await radio.lan.put(f"{R}/config/display", headers=radio.h,
                            json={"values": {"screen_on_secs": 120}})  # fmt: skip
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["changed"] == ["screen_on_secs"] and out["verified"] is True
    fresh = {f["name"]: f["value"] for f in out["section"]["fields"]}
    assert fresh["screen_on_secs"] == 120
    assert radio.iface.remote.config.display.screen_on_secs == 120
    backup = Path(radio.service.cfg.paths.backups) / "radio" / out["backup"]
    saved = json.loads(backup.read_text(encoding="utf-8"))
    assert saved["node"] == REMOTE_ID and saved["config"]["screen_on_secs"] == 600
    # Sin cambios no se transmite: la lectura de verificación quedó como base reciente.
    sent = len(radio.iface.sent)
    r = await radio.lan.put(f"{R}/config/display", headers=radio.h,
                            json={"values": {"screen_on_secs": 120}})  # fmt: skip
    assert r.json()["changed"] == [] and len(radio.iface.sent) == sent


async def test_blocked_and_dangerous(radio: Client) -> None:  # noqa: F811
    r = await radio.lan.put(f"{R}/config/lora", headers=radio.h,
                            json={"values": {"region": "US"}, "confirm_danger": True})  # fmt: skip
    assert r.status_code == 422 and r.json()["fields"] == ["region"]
    r = await radio.lan.put(f"{R}/config/security", headers=radio.h,
                            json={"values": {"serial_enabled": False}})  # fmt: skip
    assert r.status_code == 422
    assert radio.iface.sent == []

    r = await radio.lan.put(f"{R}/config/device", headers=radio.h,
                            json={"values": {"role": "CLIENT_MUTE"}})  # fmt: skip
    assert r.status_code == 409 and r.json()["fields"] == ["role"]
    assert radio.iface.remote.config.device.role != 3
    r = await radio.lan.put(f"{R}/config/device", headers=radio.h,
                            json={"values": {"role": "CLIENT_MUTE"}, "confirm_danger": True})  # fmt: skip
    assert r.status_code == 200 and r.json()["verified"] is True
    assert radio.iface.remote.config.device.role == 1  # CLIENT_MUTE


async def test_node_errors(radio: Client, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    node = radio.iface.remote
    node.authorized = False
    r = await radio.lan.post(f"{R}/probe", headers=radio.h)
    assert r.status_code == 409 and r.json()["code"] == "routing_admin_public_key_unauthorized"
    assert "clave pública" in r.json()["detail"]

    node.authorized, node.answers = True, False
    monkeypatch.setattr(remote_mod, "ADMIN_TIMEOUT_S", 0.2)
    r = await radio.lan.post(f"{R}/probe", headers=radio.h)
    assert r.status_code == 504 and r.json()["code"] == "no_answer"
    assert radio.iface.responseHandlers == {}

    # Clave de sesión vencida: se renueva y se repite una vez.
    node.answers, node.bad_session_once = True, True
    r = await radio.lan.put(f"{R}/config/display", headers=radio.h,
                            json={"values": {"screen_on_secs": 45}})  # fmt: skip
    assert r.status_code == 200, r.text
    assert node.config.display.screen_on_secs == 45

    # El cambio reinicia el nodo: no contesta la verificación y queda sin verificar.
    node.reboot_on_write = True
    monkeypatch.setattr(remote_mod, "VERIFY_TIMEOUT_S", 0.2)
    r = await radio.lan.put(f"{R}/config/display", headers=radio.h,
                            json={"values": {"screen_on_secs": 90}})  # fmt: skip
    assert r.status_code == 200 and r.json()["verified"] is None and r.json()["section"] is None


async def test_owner_position_reboot(radio: Client) -> None:  # noqa: F811
    node = radio.iface.remote
    r = await radio.lan.put(f"{R}/owner", headers=radio.h,
                            json={"long_name": "Torre Norte", "short_name": "TNO"})  # fmt: skip
    assert r.status_code == 200, r.text
    assert (node.owner.long_name, node.owner.short_name) == ("Torre Norte", "TNO")
    assert node.owner.is_unmessagable  # se respeta lo que tenía el nodo
    assert radio.iface.nodesByNum[0x11112222]["user"]["longName"] == "Torre Norte"

    r = await radio.lan.put(f"{R}/position", headers=radio.h,
                            json={"lat": -40.81, "lon": -62.99, "alt": 40})  # fmt: skip
    assert r.status_code == 200
    assert node.position == (-408100000, -629900000, 40) and node.config.position.fixed_position

    assert (await radio.lan.post(f"{R}/reboot", headers=radio.h, json={})).status_code == 400
    r = await radio.lan.post(f"{R}/reboot", headers=radio.h, json={"confirm": True})
    assert r.status_code == 200 and node.reboots == [5]


async def test_rate_limit_and_internet(radio: Client) -> None:  # noqa: F811
    get_remote(radio.service).limiters["usb-prueba"] = RemoteLimiter()
    assert (await radio.lan.post(f"{R}/probe", headers=radio.h)).status_code == 200
    r = await radio.lan.post(f"{R}/probe", headers=radio.h)
    assert r.status_code == 429 and "Retry-After" in r.headers

    get_remote(radio.service).limiters["usb-prueba"] = RemoteLimiter(gap_s=0)
    radio.service.cfg.cloudflare.remote_admin_auth = "password"
    remote = httpx.ASGITransport(app=create_app(radio.service, "remote"))
    async with httpx.AsyncClient(transport=remote, base_url="https://remote") as c:
        r = await c.post(
            "/api/v1/admin/auth/login", json={"username": "admin", "password": ADMIN_PW}
        )
        h = {"X-CSRF-Token": r.json()["csrf_token"]}
        r = await c.put(f"{R}/config/device", headers=h,
                        json={"values": {"role": "CLIENT"}, "confirm_danger": True})  # fmt: skip
        assert r.status_code == 403
        r = await c.put(f"{R}/config/display", headers=h,
                        json={"values": {"screen_on_secs": 30}})  # fmt: skip
        assert r.status_code == 200
        assert (await c.post(f"{R}/reboot", headers=h, json={"confirm": True})).status_code == 200
