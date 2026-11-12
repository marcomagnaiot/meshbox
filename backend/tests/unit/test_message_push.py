"""Avisos push de mensajes de las placas del Cliente Meshtastic (ADR 0023)."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import orjson
import pytest

from meshbox.app import Service
from meshbox.radio.notify import MessageNotifier, conv_url

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


def _msg(**over: Any) -> dict[str, Any]:
    base = {
        "board": "!aaaa0001",
        "connector_id": "placa-1",
        "direction": "in",
        "packet_id": 77,
        "from_id": "!0000beef",
        "to_id": "!aaaa0001",
        "dm": True,
        "channel_index": 0,
        "channel": None,
        "text": "hola, ¿me oís?",
        "ts": time.time(),
    }
    base["conv"] = "dm:!0000beef" if base["dm"] else "ch:0"
    return {**base, **over}


async def test_message_push_modes_and_dedupe(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    notifier: MessageNotifier = service.extensions["message_push"]
    push = notifier.push
    sent: list[tuple[str, dict[str, Any], str]] = []
    monkeypatch.setattr(
        push,
        "_send_one",
        lambda sub, payload, urgency="normal", ttl=3600: (
            sent.append((sub["endpoint"], orjson.loads(payload), urgency)) or (True, None, None)
        ),
    )
    monkeypatch.setattr(notifier, "_own_boards", lambda: {"!aaaa0001", "!aaaa0002"})
    keys = ("p" * 40, "a" * 16)
    await push.set_device("https://push.example/directos", *keys, 1, True, "dm")
    await push.set_device("https://push.example/todo", *keys, 1, False, "all")
    await push.set_device("https://push.example/nada", *keys, 1, True, "off")
    await push.subscribe("https://push.example/publico", *keys, "public", None)

    async def settle() -> None:
        if notifier._tasks:
            await asyncio.wait(notifier._tasks, timeout=5)

    # Directo: a los dos equipos que lo pidieron, con urgencia alta y la conversación.
    notifier.on_message(_msg())
    await settle()
    assert sorted(e for e, _, _ in sent) == [
        "https://push.example/directos",
        "https://push.example/todo",
    ]
    _, payload, urgency = sent[0]
    assert (
        urgency == "high" and payload["kind"] == "message" and payload["body"] == "hola, ¿me oís?"
    )
    assert (
        payload["url"]
        == conv_url("placa-1", "dm:!0000beef")
        == ("/admin/cliente?placa=placa-1&conv=dm%3A%210000beef")
    )
    # El mismo paquete oído por la otra placa no avisa otra vez.
    sent.clear()
    notifier.on_message(_msg(board="!aaaa0002", connector_id="placa-2"))
    await settle()
    assert sent == []
    # Canal: solo el que pidió todo. Lo que manda una placa propia no avisa.
    notifier.on_message(
        _msg(packet_id=78, dm=False, conv="ch:0", to_id="^all", channel="MediumFast")
    )
    notifier.on_message(_msg(packet_id=79, from_id="!aaaa0002"))
    notifier.on_message(_msg(packet_id=80, direction="out"))
    await settle()
    assert [e for e, _, _ in sent] == ["https://push.example/todo"]
    assert sent[0][1]["title"].startswith("# MediumFast · ")
    # Las alertas siguen yendo a los equipos con alertas (no al que solo quiere mensajes).
    sent.clear()
    alert = {"id": 5, "title": "x", "severity": "info", "ts": time.time(), "node": None}
    await push.send(alert, is_public=False)
    assert sorted(e for e, _, _ in sent) == [
        "https://push.example/directos",
        "https://push.example/nada",
    ]
    assert (await push.device("https://push.example/publico")) is None
    assert (await push.device("https://push.example/todo")) == {
        "alerts": False,
        "messages": "all",
        "last_ok_at": pytest.approx(time.time(), abs=60),
    }


async def test_store_calls_listeners(service: Service) -> None:
    got: list[dict[str, Any]] = []
    service.radio_messages.listeners.append(got.append)
    service.radio_messages.on_event("text", _msg())
    service.radio_messages.on_event("text", _msg(packet_id=90, direction="out"))
    assert [m["packet_id"] for m in got] == [77]
