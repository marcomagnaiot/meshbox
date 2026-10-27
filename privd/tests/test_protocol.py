"""Protocolo de privd (Anexo D): validación de la petición, errores y registro sin secretos."""

from __future__ import annotations

import json
import logging

import pytest
from privd_testkit import Env, fake_mosquitto_passwd

import commands
import meshbox_privd
from commands.core import Command, CommandError

EXPECTED_COMMANDS = {
    "ping",
    "system.info",
    "system.hostname",
    "system.timezone",
    "system.reboot",
    "system.shutdown",
    "time.status",
    "mosquitto.account.set",
    "mosquitto.account.delete",
    "mosquitto.account.list",
    "mosquitto.acl.write",
    "mosquitto.reload",
    "mosquitto.status",
    "cloudflared.set_token",
    "cloudflared.enable",
    "cloudflared.disable",
    "cloudflared.restart",
    "cloudflared.status",
    "wifi.scan",
    "wifi.status",
    "wifi.connect",
    "wifi.forget",
    "hotspot.start",
    "hotspot.stop",
    "service.restart",
    "service.status",
    "logs.read",
    "update.apply",
    "update.status",
    "update.rollback",
    "update.info",
}


def call(env: Env, payload: object) -> dict:
    raw = payload if isinstance(payload, (bytes, str)) else json.dumps(payload)
    return meshbox_privd.dispatch(env.ctx, raw)


def error_code(response: dict) -> str:
    assert response["ok"] is False, response
    return response["error"]["code"]


def test_registry_is_closed_list() -> None:
    assert set(commands.REGISTRY) == EXPECTED_COMMANDS


def test_shared_forbidden_matches_adr_0004() -> None:
    assert {
        "system.hostname",
        "wifi.connect",
        "wifi.forget",
        "hotspot.start",
        "hotspot.stop",
    } == commands.SHARED_FORBIDDEN


def test_secret_args_are_declared() -> None:
    reg = commands.REGISTRY
    assert reg["mosquitto.account.set"].secret_args == {"password"}
    assert reg["cloudflared.set_token"].secret_args == {"token"}
    assert reg["wifi.connect"].secret_args == {"psk"}


def test_ping_ok_echoes_request_id(env: Env) -> None:
    response = call(env, {"cmd": "ping", "args": {}, "request_id": "6f1c"})
    assert response == {
        "request_id": "6f1c",
        "ok": True,
        "result": {"version": commands.core.PRIVD_VERSION, "mode": "appliance"},
    }


def test_ping_integer_request_id_and_missing_args(env: Env) -> None:
    response = call(env, {"cmd": "ping", "request_id": 7})
    assert response["ok"] is True
    assert response["request_id"] == 7


def test_args_null_is_empty_object(env: Env) -> None:
    assert call(env, {"cmd": "ping", "args": None})["ok"] is True


@pytest.mark.parametrize(
    "raw",
    [
        b"{no es json",
        b"",
        b"\xff\xfe",
        "[1, 2, 3]",
        '"texto"',
        "42",
    ],
)
def test_invalid_json(env: Env, raw: bytes | str) -> None:
    response = call(env, raw)
    assert error_code(response) == "invalid_json"
    assert response["request_id"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {"args": {}},
        {"cmd": ""},
        {"cmd": 5},
        {"cmd": ["ping"]},
        {"cmd": "ping", "extra": 1},
        {"cmd": "ping", "request_id": True},
        {"cmd": "ping", "request_id": {"a": 1}},
        {"cmd": "ping", "request_id": "x" * 129},
        {"cmd": "ping", "request_id": "con\nsalto"},
    ],
)
def test_malformed_requests(env: Env, payload: dict) -> None:
    assert error_code(call(env, payload)) == "invalid_json"


def test_unknown_command(env: Env) -> None:
    response = call(env, {"cmd": "rm -rf /", "request_id": "r1"})
    assert error_code(response) == "unknown_command"
    assert response["request_id"] == "r1"


def test_unknown_command_message_is_clipped(env: Env) -> None:
    response = call(env, {"cmd": "x" * 500})
    assert error_code(response) == "unknown_command"
    assert len(response["error"]["message"]) < 120


@pytest.mark.parametrize("args", [[], "texto", 3, True])
def test_args_must_be_object(env: Env, args: object) -> None:
    assert error_code(call(env, {"cmd": "ping", "args": args})) == "invalid_args"


def test_unknown_argument_rejected(env: Env) -> None:
    response = call(env, {"cmd": "ping", "args": {"inyectado": "; reboot"}})
    assert error_code(response) == "invalid_args"


@pytest.mark.parametrize(
    ("cmd", "args"),
    [
        ("system.hostname", {"name": "meshbox"}),
        ("wifi.connect", {"ssid": "Casa", "psk": "clave-segura"}),
        ("wifi.forget", {"ssid": "Casa"}),
        ("hotspot.start", {}),
        ("hotspot.stop", {}),
    ],
)
def test_shared_mode_rejects(shared_env: Env, cmd: str, args: dict) -> None:
    response = call(shared_env, {"cmd": cmd, "args": args})
    assert error_code(response) == "not_allowed_in_shared_mode"
    assert shared_env.runner.calls == []


def test_shared_mode_allows_other_commands(shared_env: Env) -> None:
    response = call(shared_env, {"cmd": "ping"})
    assert response["result"]["mode"] == "shared"
    response = call(shared_env, {"cmd": "mosquitto.account.list"})
    assert response["ok"] is True


def test_appliance_mode_runs_hostname(env: Env) -> None:
    response = call(env, {"cmd": "system.hostname", "args": {"name": "meshbox"}})
    assert response["ok"] is True


def test_internal_error_is_generic(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(ctx: object, args: object) -> dict:
        raise RuntimeError("detalle interno con /etc/shadow")

    monkeypatch.setitem(commands.REGISTRY, "ping", Command(boom))
    response = call(env, {"cmd": "ping"})
    assert error_code(response) == "command_failed"
    assert "shadow" not in response["error"]["message"]


def test_command_error_passes_code(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    def slow(ctx: object, args: object) -> dict:
        raise CommandError("timeout", "tardó demasiado")

    monkeypatch.setitem(commands.REGISTRY, "ping", Command(slow))
    response = call(env, {"cmd": "ping"})
    assert response["error"] == {"code": "timeout", "message": "tardó demasiado"}


def test_exclusive_commands_busy_during_update(env: Env) -> None:
    import threading

    gate = threading.Event()
    env.ctx.jobs.start("update", lambda job: gate.wait(5) and {}, group="update")
    try:
        response = call(env, {"cmd": "service.restart", "args": {"name": "meshbox"}})
        assert error_code(response) == "busy"
        response = call(env, {"cmd": "system.reboot"})
        assert error_code(response) == "busy"
        assert call(env, {"cmd": "ping"})["ok"] is True
    finally:
        gate.set()
        env.ctx.jobs.wait_all(5)


def test_secrets_never_logged(env: Env, caplog: pytest.LogCaptureFixture) -> None:
    env.runner.on([env.ctx.bins.mosquitto_passwd], fake_mosquitto_passwd)
    secret_pw = "SuperSecreta-123"
    secret_token = "eyJhIjoiMTIzIiwidCI6ImFiYyIsInMiOiJ4eXoifQ" + "A" * 40
    secret_psk = "psk-muy-secreta"
    with caplog.at_level(logging.INFO, logger="privd"):
        call(
            env,
            {
                "cmd": "mosquitto.account.set",
                "args": {"username": "gw-casa", "password": secret_pw},
            },
        )
        call(env, {"cmd": "cloudflared.set_token", "args": {"token": secret_token}})
        call(env, {"cmd": "wifi.connect", "args": {"ssid": "Casa", "psk": secret_psk}})
        call(env, {"cmd": "mosquitto.account.set", "args": {"password": secret_pw}})
    env.ctx.jobs.wait_all(5)
    text = caplog.text
    assert "cmd=mosquitto.account.set" in text
    assert "gw-casa" in text
    for secret in (secret_pw, secret_token, secret_psk):
        assert secret not in text


def test_describe_args_redacts_and_truncates() -> None:
    text = meshbox_privd.describe_args(
        {"password": "x", "long": "y" * 300, "items": list(range(30)), "nested": {"password": "z"}},
        frozenset({"password"}),
    )
    assert '"password": "***"' in text
    assert "y" * 70 not in text
    assert "30 en total" in text
    assert '"z"' not in text


def test_describe_args_limits_size() -> None:
    args = {f"k{i}": "v" * 60 for i in range(20)}
    assert len(meshbox_privd.describe_args(args, frozenset())) <= 401
