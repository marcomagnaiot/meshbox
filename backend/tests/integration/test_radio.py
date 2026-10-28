"""Cliente Meshtastic del panel (ADR 0015) contra una placa simulada."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from meshbox.api.factory import create_app
from meshbox.store.retention import run_retention

from ..radio_fake import MY_ID, attach_fake_board
from .test_api import ADMIN_PW, _make

BASE = "/api/v1/admin/radio/usb-prueba"


async def _settle(radio: Client) -> None:
    """Corre lo que el hilo de la librería dejó en el loop y espera que llegue a la base."""
    await asyncio.sleep(0)
    await radio.service.radio_messages.sync()


class Client:
    def __init__(self, service: Any, lan: httpx.AsyncClient, board: Any, iface: Any) -> None:
        self.service, self.lan, self.board, self.iface = service, lan, board, iface
        self.h: dict[str, str] = {}

    @property
    def calls(self) -> list[tuple[str, Any]]:
        return self.iface.localNode.calls  # type: ignore[no-any-return]


@pytest.fixture
async def radio(tmp_path: Path) -> AsyncIterator[Client]:
    service, lan_app, _ = await _make(tmp_path)
    board, iface = attach_fake_board(service)
    transport = httpx.ASGITransport(app=lan_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://lan") as lan:
        r = await lan.post("/api/v1/setup/admin", json={"username": "admin", "password": ADMIN_PW},
                           headers={"X-Setup-Code": "ABCD2345"})  # fmt: skip
        c = Client(service, lan, board, iface)
        c.h = {"X-CSRF-Token": r.json()["csrf_token"]}
        yield c
    await service.stop()


async def test_status_nodes_and_config(radio: Client) -> None:
    boards = (await radio.lan.get("/api/v1/admin/radio")).json()["boards"]
    assert boards[0]["id"] == "usb-prueba" and boards[0]["long_name"] == "Placa de prueba"
    st = (await radio.lan.get(BASE)).json()
    assert st["node"]["role"] == "CLIENT_BASE" and st["node"]["region"] == "ANZ"
    assert st["node"]["firmware"] == "2.7.26.test" and st["metrics"]["batteryLevel"] == 80
    assert [c["name"] for c in st["channels"][:2]] == ["MediumFast", "Familia"]
    assert st["channels"][1]["psk"] == "secret" and st["channels"][0]["psk"] == "default"
    nodes = (await radio.lan.get(f"{BASE}/nodes")).json()["nodes"]
    assert {n["id"] for n in nodes} == {MY_ID, "!11112222"}
    cfg = (await radio.lan.get(f"{BASE}/config")).json()
    sections = {s["name"]: s for s in cfg["sections"]}
    lora = {f["name"]: f for f in sections["lora"]["fields"]}
    assert lora["region"]["type"] == "enum" and "ANZ" in lora["region"]["options"]
    assert lora["region"]["danger"] and not lora["hop_limit"]["danger"]
    net = {f["name"]: f for f in sections["network"]["fields"]}
    assert net["wifi_psk"]["value"] == "********" and sections["network"]["danger"]
    mqtt = {f["name"]: f for f in sections["mqtt"]["fields"]}
    assert mqtt["password"]["value"] == "********"
    assert "clave-wifi" not in json.dumps(cfg) and "secreta" not in json.dumps(cfg)


async def test_write_section_backup_and_danger(radio: Client, tmp_path: Path) -> None:
    r = await radio.lan.put(f"{BASE}/config/display", headers=radio.h,
                            json={"values": {"screen_on_secs": 30}})  # fmt: skip
    assert r.status_code == 200, r.text
    assert r.json()["changed"] == ["screen_on_secs"] and r.json()["backup"]
    # Sin transacción: cerrarla reinicia la placa aunque el cambio no lo necesite.
    assert ("writeConfig", "display") in radio.calls and ("commit", None) not in radio.calls
    assert radio.iface.localNode.localConfig.display.screen_on_secs == 30
    backup = (await radio.lan.get(f"{BASE}/backups")).json()["backups"][0]["name"]
    data = (await radio.lan.get(f"{BASE}/backups/{backup}")).json()
    assert data["local_config"]["display"]["screen_on_secs"] == 60  # la copia es de antes
    # Peligroso sin confirmar: no toca nada.
    r = await radio.lan.put(f"{BASE}/config/lora", headers=radio.h,
                            json={"values": {"region": "US"}})  # fmt: skip
    assert r.status_code == 409 and r.json()["code"] == "danger_confirmation_required"
    assert r.json()["fields"] == ["region"]
    assert radio.iface.localNode.localConfig.lora.region != 1  # sigue en ANZ
    r = await radio.lan.put(f"{BASE}/config/lora", headers=radio.h,
                            json={"values": {"region": "US"}, "confirm_danger": True})  # fmt: skip
    assert r.status_code == 200 and ("writeConfig", "lora") in radio.calls
    # Errores de validación y secretos sin cambios.
    r = await radio.lan.put(f"{BASE}/config/lora", headers=radio.h,
                            json={"values": {"hop_limit": "siete"}})  # fmt: skip
    assert r.status_code == 422
    r = await radio.lan.put(f"{BASE}/config/mqtt", headers=radio.h,
                            json={"values": {"password": "********"}})  # fmt: skip
    assert r.status_code == 200 and r.json()["changed"] == []
    r = await radio.lan.put(f"{BASE}/config/statusmessage", headers=radio.h, json={"values": {}})
    assert r.status_code == 422
    # Restaurar la primera copia: dos secciones en una transacción (un solo reinicio).
    r = await radio.lan.post(f"{BASE}/backups/{backup}/restore", headers=radio.h,
                             json={"confirm_danger": True})  # fmt: skip
    assert r.status_code == 200 and sorted(r.json()["sections"]) == ["display", "lora"]
    assert radio.calls[-4:] == [
        ("begin", None), ("writeConfig", "display"), ("writeConfig", "lora"), ("commit", None)
    ]  # fmt: skip
    assert radio.iface.localNode.localConfig.display.screen_on_secs == 60


async def test_remote_cannot_make_dangerous_changes(radio: Client) -> None:
    radio.service.cfg.cloudflare.remote_admin_auth = "password"
    remote = httpx.ASGITransport(app=create_app(radio.service, "remote"))
    async with httpx.AsyncClient(transport=remote, base_url="https://remote") as c:
        r = await c.post(
            "/api/v1/admin/auth/login", json={"username": "admin", "password": ADMIN_PW}
        )
        h = {"X-CSRF-Token": r.json()["csrf_token"]}
        r = await c.put(f"{BASE}/config/lora", headers=h,
                        json={"values": {"region": "US"}, "confirm_danger": True})  # fmt: skip
        assert r.status_code == 403
        r = await c.put(
            f"{BASE}/config/display", headers=h, json={"values": {"screen_on_secs": 15}}
        )
        assert r.status_code == 200
        assert (
            await c.post(f"{BASE}/shutdown", headers=h, json={"confirm_danger": True})
        ).status_code == 403


async def test_channels(radio: Client) -> None:
    r = await radio.lan.put(f"{BASE}/channels/1", headers=radio.h, json={"uplink": True})
    assert r.status_code == 200 and r.json()["changed"] == ["uplink"]
    r = await radio.lan.put(f"{BASE}/channels/1", headers=radio.h, json={"psk": "random"})
    assert r.status_code == 409
    r = await radio.lan.put(f"{BASE}/channels/1", headers=radio.h,
                            json={"psk": "random", "confirm_danger": True})  # fmt: skip
    assert r.status_code == 200 and ("writeChannel", 1) in radio.calls
    r = await radio.lan.post(f"{BASE}/channels", headers=radio.h, json={"name": "Nuevo"})
    assert r.status_code == 201 and r.json()["index"] == 2
    assert radio.iface.localNode.channels[2].settings.name == "Nuevo"
    assert len(radio.iface.localNode.channels[2].settings.psk) == 32
    r = await radio.lan.put(
        f"{BASE}/channels/2", headers=radio.h, json={"name": "nombre-demasiado-largo"}
    )
    assert r.status_code == 422
    r = await radio.lan.request("DELETE", f"{BASE}/channels/0", headers=radio.h,
                                json={"confirm_danger": True})  # fmt: skip
    assert r.status_code == 409
    r = await radio.lan.request("DELETE", f"{BASE}/channels/2", headers=radio.h,
                                json={"confirm_danger": True})  # fmt: skip
    assert r.status_code == 200 and ("deleteChannel", 2) in radio.calls
    assert radio.board.channel_names[1] == "Familia"


async def test_messages_tx_and_acks(radio: Client) -> None:
    body = {"text": "hola familia", "channel_index": 1}
    r = await radio.lan.post(f"{BASE}/messages", headers=radio.h, json=body)
    assert r.json()["preview"]["channel"] == "Familia"
    r = await radio.lan.post(f"{BASE}/messages", headers=radio.h, json={**body, "confirm": True})
    assert r.status_code == 403  # [tx] apagado por defecto
    radio.service.cfg.tx.enabled = True
    r = await radio.lan.post(f"{BASE}/messages", headers=radio.h, json={**body, "confirm": True})
    assert r.status_code == 200, r.text
    pid = r.json()["packet_id"]
    assert radio.iface.sent[-1] == {"text": "hola familia", "to": "^all", "ack": True, "ch": 1}
    # El enviado ya está en la base al responder.
    d = (await radio.lan.get(f"{BASE}/messages")).json()
    assert [(m["text"], m["status"]) for m in d["messages"]] == [("hola familia", "enviado")]
    # El vecino lo repite (acuse implícito) y después llega un mensaje directo.
    radio.board._track_message({"fromId": "!11112222", "decoded": {
        "portnum": "ROUTING_APP", "requestId": pid, "routing": {"errorReason": "NONE"}}})  # fmt: skip
    radio.board._track_message({"id": 77, "fromId": "!11112222", "toId": MY_ID, "channel": 0,
        "rxSnr": 6.0, "hopStart": 3, "hopLimit": 3,
        "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "hola!"}})  # fmt: skip
    await _settle(radio)
    d = (await radio.lan.get(f"{BASE}/messages")).json()
    msgs = d["messages"]
    assert msgs[0]["status"] == "entregado" and msgs[0]["direction"] == "out"
    assert msgs[0]["conv"] == "ch:1" and msgs[1]["conv"] == "dm:!11112222"
    assert msgs[1]["dm"] and msgs[1]["text"] == "hola!" and msgs[1]["hops"] == 0
    assert d["board"] == MY_ID and d["more"] is False and d["reads"] == {}
    assert d["retention_days"] == 365
    after = (await radio.lan.get(f"{BASE}/messages", params={"after": msgs[0]["seq"]})).json()
    assert [m["text"] for m in after["messages"]] == ["hola!"]
    # Directo con límite de 30 s entre envíos.
    r = await radio.lan.post(f"{BASE}/messages", headers=radio.h,
                             json={"text": "x", "to": "!11112222", "confirm": True})  # fmt: skip
    assert r.status_code == 429


def _text(pid: int, text: str, ts: float, frm: str = "!11112222") -> dict[str, Any]:
    return {"id": pid, "fromId": frm, "toId": "^all", "channel": 1, "rxTime": ts,
            "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": text}}  # fmt: skip


async def test_history_survives_restarts_reads_and_clear(radio: Client) -> None:
    """ADR 0016: el historial queda en la base, se pagina, guarda lo leído y se puede borrar."""
    for i in range(3):
        radio.board._track_message(_text(500 + i, f"m{i}", 1792900000 + i))
    radio.board._track_message(_text(500, "m0", 1792900000))  # repetido al reconectar
    await _settle(radio)
    # Conector nuevo para la misma placa (reinicio del conector o de meshbox): sigue todo.
    attach_fake_board(radio.service)
    d = (await radio.lan.get(f"{BASE}/messages")).json()
    assert [m["text"] for m in d["messages"]] == ["m0", "m1", "m2"]
    assert d["messages"][0]["ts"] == 1792900000 and d["messages"][0]["channel"] == "Familia"
    # Los últimos 2 y después los anteriores.
    d = (await radio.lan.get(f"{BASE}/messages", params={"limit": 2})).json()
    assert [m["text"] for m in d["messages"]] == ["m1", "m2"] and d["more"] is True
    older = await radio.lan.get(f"{BASE}/messages", params={"before": d["messages"][0]["seq"]})
    assert [m["text"] for m in older.json()["messages"]] == ["m0"] and not older.json()["more"]
    # Lo leído es por usuario (igual en todos sus dispositivos) y solo avanza.
    last = d["messages"][-1]["seq"]
    r = await radio.lan.put(f"{BASE}/reads", headers=radio.h, json={"conv": "ch:1", "seq": last})
    assert r.status_code == 200
    await radio.lan.put(f"{BASE}/reads", headers=radio.h, json={"conv": "ch:1", "seq": 1})
    assert (await radio.lan.get(f"{BASE}/messages")).json()["reads"] == {"ch:1": last}
    r = await radio.lan.put(f"{BASE}/reads", headers=radio.h, json={"conv": "otra", "seq": 1})
    assert r.status_code == 422
    # Un acuse que llega antes de guardar el enviado se aplica al guardarlo.
    store = radio.service.radio_messages
    store.on_event("ack", {"board": MY_ID, "packet_id": 4242, "from_id": MY_ID,
                           "reason": "NO_CHANNEL"})  # fmt: skip
    radio.board._emit_message("text", radio.board._message(
        packet_id=4242, ts=time.time(), direction="out", from_id=MY_ID, to_id="^all", dm=False,
        channel_index=1, channel="Familia", text="rápido", status="enviado"))  # fmt: skip
    # Lo más viejo que la retención (365 días) se borra en la tarea diaria.
    radio.board._track_message(_text(900, "viejo", time.time() - 400 * 86400))
    await _settle(radio)
    msgs = (await radio.lan.get(f"{BASE}/messages")).json()["messages"]
    assert msgs[-2]["text"] == "rápido" and msgs[-2]["status"] == "error: NO_CHANNEL"
    totals = await run_retention(radio.service.writer.run, radio.service.cfg.retention)
    assert totals["radio_messages"] == 1
    # Borrar el historial: administrador y con confirmación.
    r = await radio.lan.request("DELETE", f"{BASE}/messages", headers=radio.h, json={})
    assert r.status_code == 400
    r = await radio.lan.request("DELETE", f"{BASE}/messages", headers=radio.h,
                                json={"confirm": True})  # fmt: skip
    assert r.json()["deleted"] == 4
    d = (await radio.lan.get(f"{BASE}/messages")).json()
    assert d["messages"] == [] and d["reads"] == {}


async def test_owner_position_restore_and_auto_refresh(radio: Client) -> None:
    r = await radio.lan.put(f"{BASE}/owner", headers=radio.h,
                            json={"long_name": "Nodo Pi", "short_name": "NPI"})  # fmt: skip
    assert r.status_code == 200 and ("setOwner", ("Nodo Pi", "NPI")) in radio.calls
    backups = (await radio.lan.get(f"{BASE}/backups")).json()["backups"]
    r = await radio.lan.post(f"{BASE}/backups/{backups[0]['name']}/restore", headers=radio.h,
                             json={"confirm_danger": True})  # fmt: skip
    assert r.status_code == 200 and r.json()["owner"] is True
    assert radio.calls[-1] == ("setOwner", ("Placa de prueba", "PRB"))
    assert ("begin", None) not in radio.calls  # sin secciones distintas no hay transacción
    r = await radio.lan.post(f"{BASE}/position/refresh", headers=radio.h)
    assert r.status_code == 200 and ("setFixedPosition", (-40.8, -63.0, 8)) in radio.calls
    # Al conectar se repone una sola vez por arranque de la placa.
    from meshbox.connectors import serial as serial_mod

    serial_mod._POSITION_REFRESHED.clear()
    assert radio.board._refresh_fixed_position(radio.iface) is True
    assert radio.board._refresh_fixed_position(radio.iface) is False


async def test_set_and_remove_fixed_position(radio: Client) -> None:
    """Fijar o quitar la posición también actualiza la copia local de la configuración: si no,
    guardar después la sección Posición apagaría la posición fija de la placa."""
    radio.iface.localNode.localConfig.position.fixed_position = False
    r = await radio.lan.put(f"{BASE}/position", headers=radio.h,
                            json={"lat": -40.8135, "lon": -62.9967, "alt": 8})  # fmt: skip
    assert r.status_code == 200 and ("setFixedPosition", (-40.8135, -62.9967, 8)) in radio.calls
    assert (await radio.lan.get(BASE)).json()["node"]["fixed_position"] is True
    r = await radio.lan.put(f"{BASE}/position", headers=radio.h, json={"lat": 0, "lon": 0})
    assert r.status_code == 422
    r = await radio.lan.request("DELETE", f"{BASE}/position", headers=radio.h)
    assert r.status_code == 200 and ("removeFixedPosition", None) in radio.calls
    assert (await radio.lan.get(BASE)).json()["node"]["fixed_position"] is False


async def test_mesh_queries_do_not_block_the_board(
    radio: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Traceroute y pedido de posición no dejan tomada la placa (antes: hasta 300 s por salto)."""
    from meshbox.radio import service as radio_service

    radio.service.cfg.tx.enabled = True
    r = await radio.lan.post(f"{BASE}/traceroute", headers=radio.h,
                             json={"node": "!11112222", "hop_limit": 5})  # fmt: skip
    assert r.status_code == 200, r.text
    assert radio.iface.sent[-1]["port"] == "TRACEROUTE_APP" and radio.iface.sent[-1]["hops"] == 5

    radio.service.extensions.pop("tx_limiter", None)
    r = await radio.lan.post(f"{BASE}/request-position", headers=radio.h,
                             json={"node": "!11112222"})  # fmt: skip
    assert r.json() == {"answered": True}

    # Un nodo que no contesta: mientras se espera, el estado de la placa sigue respondiendo.
    radio.service.extensions.pop("tx_limiter", None)
    radio.iface.position_reply = False
    monkeypatch.setattr(radio_service, "MESH_TIMEOUT_S", 1.0)
    waiting = asyncio.create_task(
        radio.lan.post(f"{BASE}/request-position", headers=radio.h, json={"node": "!11112222"})
    )
    await asyncio.sleep(0.2)
    started = time.monotonic()
    assert (await radio.lan.get(BASE)).status_code == 200
    assert time.monotonic() - started < 0.8
    out = (await waiting).json()
    assert out["answered"] is False and radio.iface.responseHandlers == {}


async def test_busy_board_answers_instead_of_hanging(
    radio: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    from meshbox.radio import service as radio_service
    from meshbox.radio.service import get_radio

    monkeypatch.setattr(radio_service, "LOCK_WAIT_S", 0.2)
    lock = get_radio(radio.service)._locks.setdefault("usb-prueba", asyncio.Lock())
    await lock.acquire()
    try:
        r = await radio.lan.get(BASE)
        assert r.status_code == 409 and r.json()["code"] == "board_busy"
    finally:
        lock.release()
    assert (await radio.lan.get(BASE)).status_code == 200
