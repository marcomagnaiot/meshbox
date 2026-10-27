"""Motor de alertas y canales (sección 19)."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from pathlib import Path
from typing import Any

import httpx
import orjson
import pytest
import respx
from sqlalchemy import text

from meshbox.alerts.channels import outbound
from meshbox.alerts.channels.mqtt_out import MqttOut
from meshbox.alerts.engine import AlertEngine, Rule
from meshbox.alerts.rules import KeywordParams, RuleIn, TelemetryThresholdParams
from meshbox.app import Service
from meshbox.models import AlertFired, AlertResolved, MessageAdded, NodeUpserted, TelemetryAdded
from meshbox.state import NodeRecord

from ..conftest import make_cfg


@pytest.fixture
async def service(tmp_path: Path) -> Any:
    cfg = make_cfg(tmp_path)
    cfg.connectors = []
    svc = Service(cfg, None, dev=True)
    await svc.start()
    try:
        yield svc
    finally:
        await svc.stop()


def _drain(sub: Any) -> list[Any]:
    out = []
    while (ev := sub.get_nowait()) is not None:
        out.append(ev)
    return out


async def _rule(engine: AlertEngine, body: dict[str, Any]) -> Rule:
    row = engine.rule_from_in(RuleIn(**body))
    now = time.time()
    row.update(created_at=now, updated_at=now)
    await engine.service.writer.run(
        lambda c: c.execute(
            text(
                "INSERT INTO alert_rules (name, kind, params, enabled, cooldown_s, channels, severity, is_public, "
                "created_at, updated_at) VALUES (:name, :kind, :params, :enabled, :cooldown_s, :channels, :severity, "
                ":is_public, :created_at, :updated_at)"
            ),
            row,
        )
    )
    await engine.reload()
    return next(r for r in engine.rules if r.name == body["name"])


def test_rule_params_validation() -> None:
    kw = KeywordParams()
    assert (
        kw.matcher().search("hola SOS ayuda")
        and kw.matcher().search("sos")
        and kw.matcher().search("\x07")
    )
    assert not kw.matcher().search("sosiego")
    plain = KeywordParams(patterns=["a.b"], regex=False, include_bell=False)
    assert plain.matcher().search("xa.bx") and not plain.matcher().search("axb")
    t = TelemetryThresholdParams(op=">=", value=5)
    assert t.test(5) and not t.test(4.9)
    with pytest.raises(ValueError):
        KeywordParams(patterns=["("])
    with pytest.raises(ValueError):
        RuleIn(
            name="x",
            kind="telemetry_threshold",
            params={"scope": {"mode": "nodes", "nodes": ["malo"]}},
        ).parsed_params()


async def test_event_and_condition_rules(service: Service) -> None:
    engine: AlertEngine = service.extensions["alerts"]
    sub = service.bus.subscribe("t", maxsize=1000, types=(AlertFired, AlertResolved))
    now = time.time()
    # nodo fijo para los alcances
    rec = NodeRecord.new(0x0B03CBF0, now - 30 * 3600)
    rec.long_name, rec.is_fixed, rec.last_heard = "Techo", 1, now - 30 * 3600
    service.state.nodes[rec.num] = rec
    off = await _rule(engine, {"name": "caído", "kind": "node_offline", "params": {"scope": {"mode": "fixed"}, "hours": 6},
                               "channels": [], "cooldown_s": 0})  # fmt: skip
    await _rule(
        engine,
        {
            "name": "vuelve",
            "kind": "node_online",
            "params": {"scope": {"mode": "fixed"}},
            "channels": [],
        },
    )
    await _rule(engine, {"name": "nuevo", "kind": "new_node", "params": {}, "channels": []})
    bat = await _rule(engine, {"name": "batería", "kind": "telemetry_threshold",
                               "params": {"scope": {"mode": "fixed"}, "metric": "battery_level", "op": "<", "value": 30, "duration_s": 0},
                               "channels": [], "cooldown_s": 0})  # fmt: skip
    await engine.evaluate_periodic(now)
    fired = [e for e in _drain(sub) if isinstance(e, AlertFired)]
    assert any(e.rule_id == off.id and "sin escucharse" in e.alert["title"] for e in fired)
    # el nodo vuelve: se resuelve "caído" y dispara "vuelve"
    rec.last_heard = now
    await engine._on_node(NodeUpserted(node=rec.public(), changed=("last_heard",)))
    evs = _drain(sub)
    assert any(isinstance(e, AlertResolved) and e.rule_id == off.id for e in evs)
    assert any(isinstance(e, AlertFired) and "volvió" in e.alert["title"] for e in evs)
    # nodo nuevo
    await engine._on_node(
        NodeUpserted(node={**rec.public(), "id": "!12345678", "long_name": "Nuevo"}, is_new=True)
    )
    assert any("Nodo nuevo" in e.alert["title"] for e in _drain(sub) if isinstance(e, AlertFired))
    # umbral de telemetría y resolución
    await engine._on_telemetry(
        TelemetryAdded(node_id=rec.id, kind="device", values={"battery_level": 20}, tel_ts=now)
    )
    assert any(isinstance(e, AlertFired) and e.rule_id == bat.id for e in _drain(sub))
    await engine._on_telemetry(
        TelemetryAdded(node_id=rec.id, kind="device", values={"battery_level": 80}, tel_ts=now + 60)
    )
    assert any(isinstance(e, AlertResolved) and e.rule_id == bat.id for e in _drain(sub))
    events = await service.db.read(
        lambda c: c.execute(text("SELECT state FROM alert_events")).scalars().all()
    )
    assert {"firing", "resolved"} <= set(events)


async def test_duration_threshold_waits(service: Service) -> None:
    engine: AlertEngine = service.extensions["alerts"]
    rec = NodeRecord.new(0x0B03CBF1, time.time())
    rec.is_fixed = 1
    service.state.nodes[rec.num] = rec
    rule = await _rule(engine, {"name": "temp", "kind": "telemetry_threshold",
                                "params": {"scope": {"mode": "all"}, "kind": "environment", "metric": "temperature", "op": ">", "value": 40, "duration_s": 600},
                                "channels": []})  # fmt: skip
    sub = service.bus.subscribe("d", types=(AlertFired,))
    t0 = time.time()
    await engine._on_telemetry(
        TelemetryAdded(node_id=rec.id, kind="environment", values={"temperature": 45.0}, tel_ts=t0)
    )
    assert _drain(sub) == []  # todavía no pasó la duración mínima
    await engine._on_telemetry(
        TelemetryAdded(
            node_id=rec.id, kind="environment", values={"temperature": 46.0}, tel_ts=t0 + 700
        )
    )
    assert [e.rule_id for e in _drain(sub)] == [rule.id]


async def test_gateway_down_and_system(service: Service) -> None:
    engine: AlertEngine = service.extensions["alerts"]
    from meshbox.config import MqttConnectorCfg

    service.cfg.connectors = [
        MqttConnectorCfg(id="mqtt-x", host="127.0.0.1", topics=["x/#"], enabled=True)
    ]
    service.started_at = time.time() - 7200
    service.last_system = {"cpu_system": 99, "mem_percent": 10, "temperature": 80, "disk": {"percent": 10},
                           "writer": {"queue": 0}, "rss_mb": 50}  # fmt: skip
    sub = service.bus.subscribe("g", types=(AlertFired, AlertResolved))
    await engine.evaluate_periodic(time.time())
    titles = [e.alert["title"] for e in _drain(sub) if isinstance(e, AlertFired)]
    assert any("sin paquetes" in t for t in titles)
    assert any("CPU" in t for t in titles) and any("temperatura" in t for t in titles)
    service.last_system = {**service.last_system, "cpu_system": 10, "temperature": 50}
    await engine.evaluate_periodic(time.time())
    assert any(isinstance(e, AlertResolved) for e in _drain(sub))


async def test_keyword_cooldown_and_notifications(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine: AlertEngine = service.extensions["alerts"]
    service.secrets.data.telegram.bot_token = "123:abc"
    service.secrets.data.webhooks["h1"] = "secreto-hmac"
    await engine.save_channels({"webpush": {"enabled": True}, "telegram": {"enabled": True, "chat_id": "42"},
                                "webhooks": [{"id": "h1", "url": "https://hook.example/x", "enabled": True}],
                                "mqtt": {"enabled": True}})  # fmt: skip
    rule = next(r for r in engine.rules if r.kind == "keyword")
    rule.cooldown_s = 3600
    sent_push: list[bytes] = []
    monkeypatch.setattr(
        engine.push,
        "_send_one",
        lambda sub, payload: sent_push.append(payload) or (True, None, None),
    )
    await engine.push.subscribe("https://push.example/1", "p" * 40, "a" * 16, "public", None)
    with respx.mock() as m:
        tg = m.post("https://api.telegram.org/bot123:abc/sendMessage").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        hook = m.post("https://hook.example/x").mock(return_value=httpx.Response(204))
        msg = {"pk": 1, "ts": time.time(), "from": "!11112222", "from_name": "Juan", "channel": "MediumFast",
               "text": "SOS necesito ayuda", "reply_id": None, "emoji": False}  # fmt: skip
        await engine._on_message(MessageAdded(message=msg))
        await engine._on_message(
            MessageAdded(message={**msg, "pk": 2})
        )  # dentro de la espera: sin segundo aviso
        await asyncio.wait(engine._notify_tasks, timeout=5) if engine._notify_tasks else None
        assert tg.call_count == 1 and hook.call_count == 1 and len(sent_push) == 1
        body = hook.calls.last.request.content
        expected = "sha256=" + hmac.new(b"secreto-hmac", body, hashlib.sha256).hexdigest()
        assert hook.calls.last.request.headers["X-Meshbox-Signature"] == expected
        assert orjson.loads(body)["event"] == "alert"
        assert orjson.loads(sent_push[0])["url"] == "/n/!11112222"
    log = await service.db.read(
        lambda c: c.execute(text("SELECT channel, ok FROM notification_log")).all()
    )
    assert {ch for ch, ok in log if ok} >= {"telegram", "webhook:h1", "webpush"}
    # dos eventos registrados (los dos SOS), pero una sola notificación
    n = await service.db.read(
        lambda c: c.execute(text("SELECT count(*) FROM alert_events")).scalar_one()
    )
    assert n == 2


async def test_channel_tests_and_errors(service: Service) -> None:
    engine: AlertEngine = service.extensions["alerts"]
    assert "Telegram" in (await engine.test_channel("telegram") or "")
    assert "webhooks" in (await engine.test_channel("webhook") or "")
    assert await engine.test_channel("desconocido") == "canal desconocido"
    with pytest.raises(KeyError):
        await engine.test_rule(9999)


async def test_webpush_subscription_cleanup(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    push = service.extensions["alerts"].push
    await push.subscribe("https://push.example/gone", "p" * 40, "a" * 16, "public", None)
    await push.subscribe("https://push.example/flaky", "p" * 40, "a" * 16, "admin", 1)

    def fake(sub: dict[str, Any], payload: bytes) -> tuple[bool, int | None, str | None]:
        return (False, 410, "gone") if sub["endpoint"].endswith("gone") else (False, 500, "error")

    monkeypatch.setattr(push, "_send_one", fake)
    alert = {"id": 1, "title": "x", "severity": "info", "ts": time.time(), "node": None}
    for _ in range(3):
        await push.send(alert, is_public=True)
    left = await service.db.read(
        lambda c: c.execute(text("SELECT endpoint FROM push_subscriptions")).scalars().all()
    )
    assert left == []  # 410 → se borra al toque; 500 → se borra tras 3 fallos
    assert await push.unsubscribe("https://push.example/nada") is False


async def test_webhook_retries_and_signature() -> None:
    body = outbound.webhook_body("alert", {"id": 1})
    with respx.mock() as m:
        route = m.post("https://hook.example/r").mock(
            side_effect=[httpx.Response(500), httpx.Response(503), httpx.Response(200)]
        )
        await outbound.send_webhook("https://hook.example/r", "s", body, retries=3, backoff=0.01)
        assert route.call_count == 3
        m.post("https://hook.example/bad").mock(return_value=httpx.Response(400))
        with pytest.raises(outbound.ChannelError):
            await outbound.send_webhook(
                "https://hook.example/bad", "s", body, retries=3, backoff=0.01
            )
    with pytest.raises(outbound.ChannelError):
        await outbound.send_webhook("ftp://x", "s", body)
    assert outbound.sign("k", b"x").startswith("sha256=")


async def test_mqtt_out_collects_and_publishes(service: Service) -> None:
    out: MqttOut = service.extensions["mqtt_out"]
    service.cfg.mqtt_out.enabled = True
    out.publish_now("alert", {"id": 1})
    topic, payload = out.queue.get_nowait()
    assert topic == "meshbox/events/alert" and orjson.loads(payload) == {"id": 1}
    service.bus.publish(NodeUpserted(node={"id": "!00000001"}))
    for _ in range(20):
        if not out.queue.empty():
            break
        await asyncio.sleep(0.02)
    topic, _ = out.queue.get_nowait()
    assert topic == "meshbox/events/node"
    assert out.status()["enabled"] is True
