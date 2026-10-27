"""API completa sobre una base temporal, con privd simulado (criterios de E4, E6, E7, E9)."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from meshtastic.protobuf import mesh_pb2, portnums_pb2

from meshbox.api.factory import create_app
from meshbox.app import Service
from meshbox.config import Config, SecretStore
from meshbox.models import BROADCAST, RawPacket
from meshbox.system.logs import RING
from meshbox.system.privclient import PrivError

from ..conftest import FIXTURES, make_cfg

ADMIN_PW = "clave-segura-123"


class Api:
    def __init__(self, service: Service, lan: httpx.AsyncClient, pub: httpx.AsyncClient) -> None:
        self.service = service
        self.lan = lan
        self.pub = pub
        self.csrf = ""

    async def login(self, username: str = "admin", password: str = ADMIN_PW) -> httpx.Response:
        r = await self.lan.post(
            "/api/v1/admin/auth/login", json={"username": username, "password": password}
        )
        if r.status_code == 200:
            self.csrf = r.json()["csrf_token"]
        return r

    def h(self) -> dict[str, str]:
        return {"X-CSRF-Token": self.csrf}

    def feed(
        self, text: str, from_num: int = 0x11112222, to: int = BROADCAST, pid: int = 7
    ) -> None:
        pkt = mesh_pb2.MeshPacket()
        setattr(pkt, "from", from_num)
        pkt.to = to
        pkt.id = pid
        pkt.hop_start, pkt.hop_limit = 3, 2
        pkt.decoded.portnum = portnums_pb2.PortNum.TEXT_MESSAGE_APP
        pkt.decoded.payload = text.encode()
        self.service.processor.process(
            RawPacket("replay", "t", "!a1b2c3d4", "MediumFast", 1792500000.0, pkt)
        )


async def _make(tmp_path: Path, mode: str = "appliance") -> tuple[Service, Any, Any]:
    cfg: Config = make_cfg(tmp_path)
    cfg.host.mode = mode  # type: ignore[assignment]
    cfg.connectors = []
    cfg.server.admin_remote_bind = ""
    secrets = SecretStore(cfg.paths.secrets)
    secrets.data.setup_code = "ABCD2345"
    secrets.data.vapid.public_key, secrets.data.vapid.private_key = "BPublicKeyDePrueba", "privada"
    secrets.save()
    service = Service(cfg, tmp_path / "config.toml", dev=True)
    await service.start()
    service.ready = True
    return service, create_app(service, "lan"), create_app(service, "public")


@pytest.fixture
async def api(tmp_path: Path) -> AsyncIterator[Api]:
    service, lan_app, pub_app = await _make(tmp_path)
    async with (
        httpx.AsyncClient(transport=httpx.ASGITransport(app=lan_app), base_url="http://lan") as lan,
        httpx.AsyncClient(transport=httpx.ASGITransport(app=pub_app), base_url="http://pub") as pub,
    ):
        a = Api(service, lan, pub)
        r = await lan.post("/api/v1/setup/admin", json={"username": "admin", "password": ADMIN_PW},
                           headers={"X-Setup-Code": "ABCD2345"})  # fmt: skip
        assert r.status_code == 200, r.text
        lan.cookies.clear()
        yield a
    await service.stop()


# --------------------------------------------------------------------------- asistente


async def test_setup_requires_code(tmp_path: Path) -> None:
    service, lan_app, _ = await _make(tmp_path)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=lan_app), base_url="http://lan"
        ) as c:
            st = (await c.get("/api/v1/setup/state")).json()
            assert st["needs_setup"] and st["code_required"] and not st["users_exist"]
            r = await c.post(
                "/api/v1/setup/admin", json={"username": "admin", "password": ADMIN_PW}
            )
            assert r.status_code == 401
            r = await c.post("/api/v1/setup/admin", json={"username": "admin", "password": ADMIN_PW},
                             headers={"X-Setup-Code": "XXXXXXXX"})  # fmt: skip
            assert r.status_code == 401
            r = await c.post("/api/v1/setup/code", json={"code": "abcd2345"})
            assert r.status_code == 200
            r = await c.post("/api/v1/setup/admin", json={"username": "admin", "password": ADMIN_PW},
                             headers={"X-Setup-Code": "ABCD2345"})  # fmt: skip
            assert r.status_code == 200 and "meshbox_session" in r.cookies
            csrf = r.json()["csrf_token"]
            # el código era de un solo uso y ya hay usuario
            assert service.secrets.data.setup_code == ""
            r = await c.post("/api/v1/setup/site", headers={"X-CSRF-Token": csrf},
                             json={"name": "Mesh Viedma", "center": [-40.81, -62.99], "zoom": 12})  # fmt: skip
            assert r.status_code == 200, r.text
            r = await c.post(
                "/api/v1/setup/channel", headers={"X-CSRF-Token": csrf}, json={"name": "MediumFast"}
            )
            assert r.status_code == 200 and r.json()["hash"] == 31
            r = await c.post(
                "/api/v1/setup/radio",
                headers={"X-CSRF-Token": csrf},
                json={"mqtt": True, "gateway_name": "interior"},
            )
            assert r.status_code == 200, r.text
            body = r.json()["mqtt"]
            assert body["username"] == "gw-interior" and len(body["password"]) == 24
            assert "mqtt.address" in body["heltec"]["commands"][0]
            assert service.priv.accounts.get("meshbox-ingest")  # type: ignore[union-attr]
            r = await c.post("/api/v1/setup/finish", headers={"X-CSRF-Token": csrf})
            assert r.json()["state"]["done"] is True
            c.cookies.clear()
            r = await c.post("/api/v1/setup/admin", json={"username": "otro", "password": ADMIN_PW},
                             headers={"X-Setup-Code": "ABCD2345"})  # fmt: skip
            assert r.status_code == 401
            site = (await c.get("/api/v1/site")).json()
            assert site["name"] == "Mesh Viedma" and site["public_channels"] == ["MediumFast"]
    finally:
        await service.stop()


async def test_setup_window_closes(tmp_path: Path) -> None:
    service, lan_app, _ = await _make(tmp_path)
    service.started_at -= 3700
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=lan_app), base_url="http://lan"
        ) as c:
            r = await c.post("/api/v1/setup/admin", json={"username": "admin", "password": ADMIN_PW},
                             headers={"X-Setup-Code": "ABCD2345"})  # fmt: skip
            assert r.status_code == 403
    finally:
        await service.stop()


# --------------------------------------------------------------------------- autenticación y exposición


async def test_public_server_hides_admin(api: Api) -> None:
    for path in (
        "/admin",
        "/setup",
        "/admin/radio",
        "/api/v1/admin/auth/me",
        "/api/v1/setup/state",
        "/api/docs",
    ):
        assert (await api.pub.get(path)).status_code == 404, path
    r = await api.pub.post(
        "/api/v1/admin/auth/login", json={"username": "admin", "password": ADMIN_PW}
    )
    assert r.status_code == 404
    assert (await api.pub.get("/api/v1/health")).json()["status"] == "ok"
    assert "content-security-policy" in (await api.pub.get("/api/v1/site")).headers


async def test_login_csrf_and_roles(api: Api) -> None:
    assert (await api.login(password="incorrecta")).status_code == 401
    r = await api.login()
    assert r.status_code == 200 and r.json()["role"] == "admin"
    assert (await api.lan.get("/api/v1/admin/auth/me")).status_code == 200
    # sin CSRF no se modifica nada
    r = await api.lan.post(
        "/api/v1/admin/users",
        json={"username": "oper", "password": "turno-noche-42", "role": "operator"},
    )
    assert r.status_code == 403
    r = await api.lan.post("/api/v1/admin/users", headers=api.h(),
                           json={"username": "oper", "password": "turno-noche-42", "role": "operator", "must_change_password": False})  # fmt: skip
    assert r.status_code == 201
    # operador: ve paquetes, no ve usuarios ni red
    api.lan.cookies.clear()
    assert (await api.login("oper", "turno-noche-42")).status_code == 200
    assert (await api.lan.get("/api/v1/admin/packets")).status_code == 200
    assert (await api.lan.get("/api/v1/admin/users")).status_code == 403
    assert (await api.lan.get("/api/v1/admin/network/status")).status_code == 403
    r = await api.lan.post("/api/v1/admin/auth/logout", headers=api.h())
    assert r.status_code == 200
    assert (await api.lan.get("/api/v1/admin/auth/me")).status_code == 401


async def test_login_rate_limit(api: Api) -> None:
    codes = [(await api.login(password=f"mala-{i}")).status_code for i in range(7)]
    assert codes[:5] == [401] * 5
    assert 429 in codes[5:]


async def test_successful_logins_do_not_use_ip_quota(api: Api) -> None:
    """Varios administradores detrás de la misma IP no se traban: solo cuentan los fallos."""
    codes = [(await api.login()).status_code for _ in range(7)]
    assert codes == [200] * 7
    fails = [(await api.login(password=f"mala-{i}")).status_code for i in range(6)]
    assert fails[:5] == [401] * 5 and fails[5] == 429


async def test_audit_records_actions(api: Api) -> None:
    await api.login()
    await api.lan.post(
        "/api/v1/admin/channels",
        headers=api.h(),
        json={"name": "MediumFast", "key": "AQ==", "is_public": True},
    )
    await api.service.writer.flush()
    entries = (await api.lan.get("/api/v1/admin/audit")).json()["entries"]
    actions = {e["action"] for e in entries}
    assert {"setup.admin", "auth.login", "channel.create"} <= actions


# --------------------------------------------------------------------------- datos


async def test_channels_nodes_messages_moderation(api: Api) -> None:
    await api.login()
    r = await api.lan.post(
        "/api/v1/admin/channels",
        headers=api.h(),
        json={"name": "MediumFast", "key": "AQ==", "is_public": True},
    )
    assert r.status_code == 201 and r.json()["hash"] == 31
    assert (await api.lan.get("/api/v1/admin/channels")).json()["channels"][0]["has_key"] is True
    api.feed("hola a todos")
    await api.service.writer.flush()
    nodes = {n["id"]: n for n in (await api.pub.get("/api/v1/nodes")).json()["nodes"]}
    # El gateway aparece por el tráfico que pasa por él, aunque todavía no mandó su NodeInfo.
    assert set(nodes) == {"!11112222", "!a1b2c3d4"}
    assert nodes["!a1b2c3d4"]["is_gateway"] and not nodes["!11112222"]["is_gateway"]
    msgs = (await api.pub.get("/api/v1/messages")).json()["messages"]
    assert msgs[0]["text"] == "hola a todos"
    pk = msgs[0]["pk"]
    r = await api.lan.patch(f"/api/v1/admin/messages/{pk}", headers=api.h(), json={"hidden": True})
    assert r.status_code == 200
    assert (await api.pub.get("/api/v1/messages")).json()["messages"] == []
    r = await api.lan.patch(
        "/api/v1/admin/nodes/!11112222", headers=api.h(), json={"hidden": True, "note": "baja"}
    )
    assert r.status_code == 200
    visible = (await api.pub.get("/api/v1/nodes")).json()["nodes"]
    assert [n["id"] for n in visible] == ["!a1b2c3d4"]
    assert (await api.pub.get("/api/v1/nodes/!11112222")).status_code == 404
    admin_nodes = {n["id"]: n for n in (await api.lan.get("/api/v1/admin/nodes")).json()["nodes"]}
    assert admin_nodes["!11112222"]["hidden"] is True and admin_nodes["!11112222"]["note"] == "baja"
    r = await api.lan.request(
        "DELETE", "/api/v1/admin/nodes/!11112222/history", headers=api.h(), json={"confirm": True}
    )
    assert r.status_code == 200 and r.json()["deleted"]["messages.from_num"] == 1
    packets = (await api.lan.get("/api/v1/admin/packets")).json()["packets"]
    assert packets == []


async def test_packets_capture_and_detail(api: Api) -> None:
    await api.login()
    await api.lan.post(
        "/api/v1/admin/channels", headers=api.h(), json={"name": "MediumFast", "is_public": True}
    )
    from meshbox.connectors.replay import read_recording, record_to_packet

    for n, rec in enumerate(read_recording(FIXTURES / "sim-6h.jsonl")):
        pkt = record_to_packet(rec)
        if pkt is not None:
            api.service.processor.process(
                RawPacket(
                    "replay",
                    "r",
                    rec.get("gateway_id"),
                    rec.get("channel_id"),
                    float(rec["rx_time"]),
                    pkt,
                )
            )
        if n > 400:
            break
    api.service.processor.flush_dirty_nodes()
    await api.service.writer.flush()
    page = (await api.lan.get("/api/v1/admin/packets?limit=50")).json()
    assert len(page["packets"]) == 50 and page["next"]
    page2 = (await api.lan.get(f"/api/v1/admin/packets?limit=50&before={page['next']}")).json()
    assert page2["packets"][0]["pk"] != page["packets"][0]["pk"]
    pos = (await api.lan.get("/api/v1/admin/packets?portnum=POSITION_APP&limit=5")).json()[
        "packets"
    ]
    assert pos and all(p["portnum"] == "POSITION_APP" for p in pos)
    detail = (await api.lan.get(f"/api/v1/admin/packets/{pos[0]['pk']}")).json()
    assert detail["decoded"]["kind"] == "position" and detail["hex"] and detail["receptions_detail"]
    csv_text = (await api.lan.get("/api/v1/admin/packets/export?format=csv")).text
    assert csv_text.startswith("pk,from,to")
    status = (await api.lan.get("/api/v1/admin/system/status")).json()
    assert status["counters"]["packets_total"] > 0 and status["mode"] == "appliance"


async def test_mqtt_accounts(api: Api) -> None:
    await api.login()
    r = await api.lan.post(
        "/api/v1/admin/mqtt/accounts", headers=api.h(), json={"name": "techo", "purpose": "gateway"}
    )
    assert r.status_code == 201
    body = r.json()
    assert (
        body["username"] == "gw-techo"
        and len(body["password"]) == 24
        and body["heltec"]["commands"]
    )
    accounts = (await api.lan.get("/api/v1/admin/mqtt/accounts")).json()
    assert {a["username"] for a in accounts["accounts"]} >= {"gw-techo"}
    acl = (await api.lan.get("/api/v1/admin/mqtt/acl")).json()["acl"]
    assert "user gw-techo" in acl and "topic readwrite" in acl
    r = await api.lan.post("/api/v1/admin/mqtt/accounts/gw-techo/rotate", headers=api.h(), json={})
    assert r.status_code == 200 and r.json()["password"] != body["password"]
    assert (
        await api.lan.delete("/api/v1/admin/mqtt/accounts/gw-techo", headers=api.h())
    ).status_code == 204
    assert (
        await api.lan.delete("/api/v1/admin/mqtt/accounts/meshbox-ingest", headers=api.h())
    ).status_code == 409


async def test_users_last_admin_protected(api: Api) -> None:
    await api.login()
    users = (await api.lan.get("/api/v1/admin/users")).json()["users"]
    me = users[0]["id"]
    assert (await api.lan.delete(f"/api/v1/admin/users/{me}", headers=api.h())).status_code == 409
    r = await api.lan.put(f"/api/v1/admin/users/{me}", headers=api.h(), json={"role": "operator"})
    assert r.status_code == 409
    weak = await api.lan.post(
        "/api/v1/admin/users", headers=api.h(), json={"username": "x1y", "password": "aaaaaaaaaa"}
    )
    assert weak.status_code == 422


async def test_site_privacy_backups(api: Api) -> None:
    await api.login()
    cur = (await api.lan.get("/api/v1/admin/site")).json()["site"]
    cur.update(
        name="Red de prueba",
        accent="#ff8800",
        notice_md="## Aviso\n\nTexto **importante** [más](https://example.com)",
    )
    assert (await api.lan.put("/api/v1/admin/site", headers=api.h(), json=cur)).status_code == 200
    site = (await api.pub.get("/api/v1/site")).json()
    assert site["name"] == "Red de prueba" and site["accent"] == "#ff8800"
    assert site["notice"][1]["c"][1] == {"t": "strong", "v": "importante"}
    etag = (await api.pub.get("/api/v1/site")).headers["etag"]
    assert (await api.pub.get("/api/v1/site", headers={"If-None-Match": etag})).status_code == 304
    bad = {**cur, "center": [123, 0]}
    assert (await api.lan.put("/api/v1/admin/site", headers=api.h(), json=bad)).status_code == 422
    priv = (await api.lan.get("/api/v1/admin/privacy")).json()
    priv["privacy"]["position_policy"] = "degrade"
    r = await api.lan.put(
        "/api/v1/admin/privacy",
        headers=api.h(),
        json={"privacy": priv["privacy"], "retention": priv["retention"]},
    )
    assert r.status_code == 200 and api.service.cfg.privacy.position_policy == "degrade"
    r = await api.lan.post("/api/v1/admin/backups", headers=api.h())
    assert r.status_code == 201
    names = [b["name"] for b in (await api.lan.get("/api/v1/admin/backups")).json()["backups"]]
    assert names and (await api.lan.get(f"/api/v1/admin/backups/{names[0]}")).status_code == 200
    assert (await api.lan.get("/api/v1/admin/backups/..%2Fsecrets.toml")).status_code == 404
    logo = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    r = await api.lan.post(
        "/api/v1/admin/site/logo", headers={**api.h(), "Content-Type": "image/png"}, content=logo
    )
    assert r.status_code == 200
    svg = b"<svg onload='alert(1)'/>"
    r = await api.lan.post(
        "/api/v1/admin/site/logo", headers={**api.h(), "Content-Type": "image/svg+xml"}, content=svg
    )
    assert r.status_code == 415


async def test_config_export_import_roundtrip(api: Api) -> None:
    await api.login()
    await api.lan.post(
        "/api/v1/admin/channels", headers=api.h(), json={"name": "MediumFast", "is_public": True}
    )
    exported = await api.lan.post("/api/v1/admin/config/export", headers=api.h(),
                                  json={"include_secrets": True, "password": "exportacion-123"})  # fmt: skip
    data = exported.json()
    assert "secrets_encrypted" in data and "session_key" not in exported.text
    r = await api.lan.post("/api/v1/admin/config/import", headers=api.h(),
                           json={"data": data, "password": "otra-clave-xx", "confirm": True})  # fmt: skip
    assert r.status_code == 422
    r = await api.lan.post("/api/v1/admin/config/import", headers=api.h(),
                           json={"data": data, "password": "exportacion-123", "confirm": True})  # fmt: skip
    assert r.status_code == 200, r.text


# --------------------------------------------------------------------------- alertas


async def test_sos_fires_public_alert(api: Api) -> None:
    await api.login()
    await api.lan.post(
        "/api/v1/admin/channels", headers=api.h(), json={"name": "MediumFast", "is_public": True}
    )
    rules = (await api.lan.get("/api/v1/admin/alerts/rules")).json()["rules"]
    assert any(r["kind"] == "keyword" for r in rules)
    sub = api.service.bus.subscribe("t", maxsize=1000)
    api.feed("SOS me quedé sin nafta en la ruta 3", pid=99)
    for _ in range(50):
        await asyncio.sleep(0.05)
        alerts = (await api.pub.get("/api/v1/alerts")).json()["alerts"]
        if alerts:
            break
    assert alerts and alerts[0]["severity"] == "critical" and alerts[0]["title"].startswith("SOS")
    assert alerts[0]["kind"] == "keyword"
    fired = [e for e in iter(sub.get_nowait, None) if type(e).__name__ == "AlertFired"]
    assert fired
    events = (await api.lan.get("/api/v1/admin/alerts/events")).json()["events"]
    r = await api.lan.post(f"/api/v1/admin/alerts/events/{events[0]['id']}/ack", headers=api.h())
    assert r.status_code == 200


async def test_alert_rule_schemas_for_forms(api: Api) -> None:
    await api.login()
    body = (await api.lan.get("/api/v1/admin/alerts/rules/schema")).json()
    assert set(body["params"]) == {
        "keyword", "telemetry_threshold", "node_offline", "node_online", "new_node",
        "gateway_down", "system",
    }  # fmt: skip
    assert body["rule"]["properties"]["kind"]["enum"]
    minutes = body["params"]["gateway_down"]["properties"]["minutes"]
    assert minutes["minimum"] == 1 and minutes["default"] == 30


async def test_alert_rule_crud_and_validation(api: Api) -> None:
    await api.login()
    bad = {"name": "x", "kind": "keyword", "params": {"patterns": ["("]}, "channels": []}
    assert (
        await api.lan.post("/api/v1/admin/alerts/rules", headers=api.h(), json=bad)
    ).status_code == 422
    rule = {"name": "Batería techo", "kind": "telemetry_threshold",
            "params": {"scope": {"mode": "nodes", "nodes": ["!0b03cbf0"]}, "metric": "battery_level", "op": "<", "value": 30, "duration_s": 0},
            "channels": ["webpush"], "severity": "warning"}  # fmt: skip
    r = await api.lan.post("/api/v1/admin/alerts/rules", headers=api.h(), json=rule)
    assert r.status_code == 201
    rid = r.json()["id"]
    r = await api.lan.put(
        f"/api/v1/admin/alerts/rules/{rid}", headers=api.h(), json={**rule, "enabled": False}
    )
    assert r.status_code == 200
    assert (
        await api.lan.delete(f"/api/v1/admin/alerts/rules/{rid}", headers=api.h())
    ).status_code == 204
    ch = (await api.lan.get("/api/v1/admin/alerts/channels")).json()
    assert ch["telegram"]["bot_token"] == ""
    put = {"telegram_enabled": True, "telegram_chat_id": "123", "telegram_bot_token": "bot:token-de-prueba",
           "webhooks": [{"url": "https://example.com/hook"}], "mqtt_enabled": True}  # fmt: skip
    ch = (await api.lan.put("/api/v1/admin/alerts/channels", headers=api.h(), json=put)).json()
    assert ch["telegram"]["bot_token"] == "********" and ch["webhooks"][0]["secret"] == "********"
    assert "bot:token-de-prueba" not in str(ch)


# --------------------------------------------------------------------------- plugins y Cloudflare


async def test_plugins_station_layer(api: Api) -> None:
    await api.login()
    plugins = (await api.lan.get("/api/v1/admin/plugins")).json()["plugins"]
    assert {p["id"] for p in plugins} >= {"fires", "puente", "station"}
    with respx.mock(assert_all_called=False) as router:
        router.get("https://weather.example/api").mock(
            return_value=httpx.Response(
                200, json={"temperature": 12.5, "humidity": 70, "wind_speed": 18}
            )
        )
        r = await api.lan.put("/api/v1/admin/plugins/station", headers=api.h(),
                              json={"enabled": True, "settings": {"url": "https://weather.example/api", "lat": -40.8, "lon": -63.0}})  # fmt: skip
        assert r.status_code == 200 and r.json()["running"], r.text
        layers = (await api.pub.get("/api/v1/plugins/layers")).json()
        assert layers[0]["url"] == "/api/v1/plugins/station/layers/station"
        geo = (await api.pub.get(layers[0]["url"])).json()
        values = geo["features"][0]["properties"]["values"]
        assert {"label": "Temperatura", "value": 12.5, "unit": "°C"} in values
    r = await api.lan.put(
        "/api/v1/admin/plugins/fires", headers=api.h(), json={"enabled": True, "settings": {}}
    )
    assert r.status_code == 422  # falta map_key


async def test_cloudflare_token_and_api_modes(api: Api) -> None:
    await api.login()
    token = "eyJ" + "a" * 120
    r = await api.lan.post(
        "/api/v1/admin/cloudflare/token",
        headers=api.h(),
        json={"token": token, "public_hostname": "mesh.example.com"},
    )
    assert r.status_code == 200 and api.service.priv.tunnel_token == token  # type: ignore[union-attr]
    service = (await api.lan.get("/api/v1/admin/cloudflare/status")).json()["service"]
    assert service["active"] is True and service["state"] == "active"
    assert service["token_configured"] is True
    base = "https://api.cloudflare.com/client/v4"
    acc, zone, tun = "a" * 32, "b" * 32, "c" * 8
    with respx.mock() as cf:
        cf.get(f"{base}/user/tokens/verify").mock(
            return_value=httpx.Response(200, json={"success": True, "result": {"status": "active"}})
        )
        cf.get(f"{base}/zones").mock(return_value=httpx.Response(200, json={"success": True, "result": [
            {"id": zone, "name": "example.com", "account": {"id": acc, "name": "Ejemplo"}}]}))  # fmt: skip
        cf.get(f"{base}/accounts/{acc}/cfd_tunnel").mock(
            return_value=httpx.Response(200, json={"success": True, "result": []})
        )
        cf.post(f"{base}/accounts/{acc}/cfd_tunnel").mock(
            return_value=httpx.Response(
                200,
                json={"success": True, "result": {"id": tun, "token": "tunnel-token-" + "x" * 60}},
            )
        )
        cf.put(f"{base}/accounts/{acc}/cfd_tunnel/{tun}/configurations").mock(
            return_value=httpx.Response(200, json={"success": True, "result": {}})
        )
        cf.get(f"{base}/zones/{zone}/dns_records").mock(
            return_value=httpx.Response(200, json={"success": True, "result": []})
        )
        dns = cf.post(f"{base}/zones/{zone}/dns_records").mock(
            return_value=httpx.Response(200, json={"success": True, "result": {"id": "d1"}})
        )
        cf.get(f"{base}/accounts/{acc}/cfd_tunnel/{tun}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "result": {"id": tun, "status": "healthy", "connections": [{}]},
                },
            )
        )
        cf.get("https://mesh.example.com/api/v1/health").mock(
            return_value=httpx.Response(200, json={"status": "ok"})
        )
        r = await api.lan.post(
            "/api/v1/admin/cloudflare/api/verify", headers=api.h(), json={"api_token": "t" * 40}
        )
        assert r.status_code == 200 and r.json()["zones"][0]["name"] == "example.com"
        r = await api.lan.post("/api/v1/admin/cloudflare/api/provision", headers=api.h(),
                               json={"zone_id": zone, "public_hostname": "mesh.example.com"})  # fmt: skip
        assert r.status_code == 200, r.text
        assert r.json()["site_check"]["ok"] is True
        body = dns.calls.last.request.content
        assert f"{tun}.cfargotunnel.com".encode() in body and b'"proxied":true' in body.replace(
            b" ", b""
        )
    cfg = api.service.cfg.cloudflare
    assert cfg.mode == "api" and cfg.tunnel_id == tun
    assert api.service.priv.cloudflared_enabled  # type: ignore[union-attr]
    r = await api.lan.post(
        "/api/v1/admin/cloudflare/disconnect", headers=api.h(), json={"confirm": True}
    )
    assert r.status_code == 200 and api.service.cfg.cloudflare.mode == "none"
    assert api.service.priv.tunnel_token is None  # type: ignore[union-attr]
    service = (await api.lan.get("/api/v1/admin/cloudflare/status")).json()["service"]
    assert service["active"] is False and service["token_configured"] is False


async def test_system_status_and_logs(api: Api) -> None:
    """Formas que ve el panel: iguales con privd simulado y con el real (test_contract)."""
    await api.login()
    body = (await api.lan.get("/api/v1/admin/system/status")).json()
    services = body["services"]
    assert services["meshbox"]["active"] is True and services["meshbox"]["version"]
    assert services["mosquitto"]["active"] is True and services["mosquitto"]["state"] == "active"
    assert services["meshbox-cloudflared"]["active"] is False
    assert services["meshbox-cloudflared"]["state"] == "inactive"
    RING.emit(
        logging.LogRecord("meshbox.x", logging.WARNING, __file__, 1, "aviso %s", ("x",), None)
    )
    r = await api.lan.get("/api/v1/admin/system/logs", params={"unit": "mosquitto"})
    entries = r.json()["entries"]
    assert entries and set(entries[0]) == {"ts", "level", "msg", "logger", "unit"}
    assert entries[-1]["msg"] == "aviso x" and entries[-1]["level"] == "WARNING"
    net = (await api.lan.get("/api/v1/admin/network/status")).json()
    assert net["time"]["ntp_synchronized"] is True and net["wifi"]["ssid"] == "Casa"


async def test_updates_install_rollback_and_privd_errors(api: Api) -> None:
    """E10 con privd simulado: instalar, seguir el trabajo, volver atrás y errores de privd."""
    await api.login()
    source = api.service.cfg.updates.source
    with respx.mock() as gh:
        gh.get(source).mock(return_value=httpx.Response(200, json=[
            {"tag_name": "v9.0.0", "name": "9.0.0", "body": "notas", "assets": []}]))  # fmt: skip
        body = (await api.lan.get("/api/v1/admin/updates", params={"force": True})).json()
    current = api.service.version
    assert body["latest"] == "9.0.0" and body["update_available"]
    assert body["local"]["current"] == current
    r = await api.lan.post("/api/v1/admin/updates/install", headers=api.h(),
                           json={"version": "9.0.0", "confirm": True})  # fmt: skip
    assert r.status_code == 202, r.text
    job = (await api.lan.get(f"/api/v1/admin/updates/jobs/{r.json()['job']}")).json()
    assert job["state"] == "succeeded" and job["meta"]["from"] == current
    r = await api.lan.post(
        "/api/v1/admin/updates/rollback", headers=api.h(), json={"confirm": True}
    )
    assert r.status_code == 200
    job = (await api.lan.get(f"/api/v1/admin/updates/jobs/{r.json()['job']}")).json()
    assert job["meta"] == {"action": "rollback", "version": current, "from": "9.0.0"}
    # Errores de privd: mensaje legible y código, no un 500.
    priv = api.service.priv
    priv.fail["update.apply"] = PrivError("command_failed", "la firma de SHA256SUMS no es válida")  # type: ignore[union-attr]
    r = await api.lan.post("/api/v1/admin/updates/install", headers=api.h(),
                           json={"version": "9.0.1", "confirm": True})  # fmt: skip
    assert r.status_code == 502 and "firma" in r.json()["detail"]
    assert r.json()["code"] == "command_failed"
    r = await api.lan.get("/api/v1/admin/updates/jobs/ffffffffffff")
    assert r.status_code == 422


async def test_shared_mode_blocks_network_changes(tmp_path: Path) -> None:
    service, lan_app, _ = await _make(tmp_path, mode="shared")
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=lan_app), base_url="http://lan"
        ) as c:
            r = await c.post("/api/v1/setup/admin", json={"username": "admin", "password": ADMIN_PW},
                             headers={"X-Setup-Code": "ABCD2345"})  # fmt: skip
            csrf = r.json()["csrf_token"]
            for method, path, body in (
                ("PUT", "/api/v1/admin/system/hostname", {"name": "meshbox"}),
                (
                    "POST",
                    "/api/v1/admin/network/wifi/connect",
                    {"ssid": "x", "psk": "12345678", "confirm": True},
                ),
                ("POST", "/api/v1/admin/network/hotspot", {"enabled": True}),
            ):
                r = await c.request(method, path, json=body, headers={"X-CSRF-Token": csrf})
                assert r.status_code == 409, path
            assert (await c.get("/api/v1/admin/network/status")).json()["managed"] is False
    finally:
        await service.stop()


async def test_example_plugin_installs_by_copying_folder(tmp_path: Path) -> None:
    """Criterio de E9: el plugin de ejemplo de docs/plugins.md se instala copiando una carpeta."""
    import shutil

    example = Path(__file__).resolve().parents[3] / "docs" / "examples" / "plugins" / "charla"
    service, _, _ = await _make(tmp_path)
    try:
        shutil.copytree(example, service.cfg.paths.plugins / "charla")
        pm = service.extensions["plugins"]
        pm.discover()
        assert "charla" in pm.plugins and not pm.plugins["charla"].manifest.builtin
        out = await pm.update("charla", True, {"ventana_min": 30})
        assert out["running"], out["error"]
        await service.writer.run(
            lambda c: c.execute(
                __import__("sqlalchemy").text(
                    "INSERT INTO channels (name, hash, key_ref, is_public) VALUES ('MediumFast', 31, NULL, 1)"
                )
            )
        )
        await service.db.read(lambda c: service.state.load_channels(c, service.secrets.get))
        # un nodo con posición que escribe en el canal público
        pos = mesh_pb2.Position(latitude_i=-408100000, longitude_i=-629900000)
        for i, (port, payload) in enumerate(
            [(portnums_pb2.PortNum.POSITION_APP, pos.SerializeToString()),
             (portnums_pb2.PortNum.TEXT_MESSAGE_APP, b"hola desde el plugin")]
        ):  # fmt: skip
            pkt = mesh_pb2.MeshPacket()
            setattr(pkt, "from", 0x33334444)
            pkt.to, pkt.id = BROADCAST, 500 + i
            pkt.decoded.portnum, pkt.decoded.payload = port, payload
            service.processor.process(
                RawPacket("replay", "t", "!a1b2c3d4", "MediumFast", time.time() + i, pkt)
            )
        for _ in range(40):
            await asyncio.sleep(0.05)
            if pm.plugins["charla"].instance.mensajes:  # type: ignore[union-attr]
                break
        lan = create_app(service, "lan")  # las rutas del plugin se montan al crear la app
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=lan), base_url="http://lan"
        ) as c:
            layer = (await c.get("/api/v1/plugins/charla/layers/hablando")).json()
            assert layer["features"][0]["properties"]["id"] == "!33334444"
            r = await c.post("/api/v1/setup/admin", json={"username": "admin", "password": ADMIN_PW},
                             headers={"X-Setup-Code": "ABCD2345"})  # fmt: skip
            assert r.status_code == 200
            msgs = (await c.get("/api/v1/admin/plugins/charla/api/mensajes")).json()["mensajes"]
            assert msgs[0]["text"] == "hola desde el plugin"
            c.cookies.clear()
            assert (await c.get("/api/v1/admin/plugins/charla/api/mensajes")).status_code == 401
    finally:
        await service.stop()


async def test_remote_admin_password_mode(tmp_path: Path) -> None:
    """ADR 0014: panel por internet con usuario y clave, sin Access y con superficie reducida."""
    service, lan_app, _ = await _make(tmp_path)
    try:
        transport_lan = httpx.ASGITransport(app=lan_app)
        async with httpx.AsyncClient(transport=transport_lan, base_url="http://lan") as lan:
            r = await lan.post("/api/v1/setup/admin", json={"username": "admin", "password": ADMIN_PW},
                               headers={"X-Setup-Code": "ABCD2345"})  # fmt: skip
            assert r.status_code == 200, r.text
        # Por defecto el servidor remoto exige Cloudflare Access.
        strict = httpx.ASGITransport(app=create_app(service, "remote"))
        async with httpx.AsyncClient(transport=strict, base_url="https://remote") as c:
            r = await c.post(
                "/api/v1/admin/auth/login", json={"username": "admin", "password": ADMIN_PW}
            )
            assert r.status_code == 403
        service.cfg.cloudflare.remote_admin_auth = "password"
        remote = httpx.ASGITransport(app=create_app(service, "remote"))
        async with httpx.AsyncClient(transport=remote, base_url="https://remote") as c:
            r = await c.get("/", follow_redirects=False)
            assert r.status_code == 302 and r.headers["location"] == "/admin"
            assert (await c.get("/setup")).status_code == 404
            assert (await c.get("/api/v1/setup/state")).status_code == 404
            # Sin PWA en el hostname de administración y el sitio sabe en qué servidor está.
            sw = await c.get("/service-worker.js")
            assert sw.status_code == 200 and "registration.unregister()" in sw.text
            assert (await c.get("/api/v1/site")).json()["server"] == "remote"
            r = await c.post(
                "/api/v1/admin/auth/login", json={"username": "admin", "password": ADMIN_PW}
            )
            assert r.status_code == 200, r.text
            assert "secure" in r.headers["set-cookie"].lower()
            h = {"X-CSRF-Token": r.json()["csrf_token"]}
            r = await c.get("/api/v1/admin/system/status")
            assert r.status_code == 200 and r.headers["x-robots-tag"] == "noindex, nofollow"
            r = await c.post("/api/v1/admin/system/reboot", headers=h, json={"confirm": True})
            assert r.status_code == 403 and "red local" in r.json()["detail"]
            assert service.priv.calls == [] or all(  # type: ignore[union-attr]
                cmd != "system.reboot"
                for cmd, _ in service.priv.calls  # type: ignore[union-attr]
            )
    finally:
        await service.stop()


async def test_node_battery_trend(api: Api) -> None:
    from sqlalchemy import text

    from meshbox.state import NodeRecord

    num = 0x0A35B1D2
    now = time.time()
    api.service.state.nodes[num] = NodeRecord.new(num, now)
    rows = [{"t": now - 3600 + i * 60, "b": 101 if i > 30 else 90, "v": 4.0 + i / 1000}
            for i in range(60)]  # fmt: skip
    await api.service.writer.run(
        lambda c: c.execute(
            text(
                "INSERT INTO telemetry_device (node_num, ts, battery_level, voltage) "
                "VALUES (:n, :t, :b, :v)"
            ),
            [{**r, "n": num} for r in rows],
        )
    )
    assert (await api.login()).status_code == 200
    r = await api.lan.get("/api/v1/admin/nodes/!0a35b1d2/battery", params={"days": 2})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["node"] == "!0a35b1d2" and d["samples"] == 60 and len(d["per_day"]) == 2
    assert d["trend"]["verdict"] in {"recupera", "estable", "deficit", "sin_datos"}
    assert (await api.lan.get("/api/v1/admin/nodes/!00000001/battery")).status_code == 404
