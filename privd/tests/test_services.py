"""service.restart, service.status y logs.read con listas cerradas."""

from __future__ import annotations

import json

import pytest
from privd_testkit import Env, make_env, ok

from commands import services
from commands.core import CommandError


@pytest.mark.parametrize(
    ("name", "unit"),
    [
        ("meshbox", "meshbox.service"),
        ("mosquitto", "mosquitto.service"),
        ("meshbox-cloudflared", "meshbox-cloudflared.service"),
        ("meshbox-privd", "meshbox-privd.service"),
    ],
)
def test_restart_allowed(env: Env, name: str, unit: str) -> None:
    result = services.restart(env.ctx, {"name": name})
    assert result == {"name": name, "unit": unit, "queued": True}
    assert env.runner.argvs() == [["/usr/bin/systemctl", "--no-block", "restart", unit]]


@pytest.mark.parametrize(
    "name",
    ["sshd", "nginx", "meshbox.service", "meshbox;reboot", "../meshbox", "", 3, None],
)
def test_restart_rejects_other_units(env: Env, name: object) -> None:
    with pytest.raises(CommandError) as exc:
        services.restart(env.ctx, {"name": name})
    assert exc.value.code == "invalid_args"
    assert env.runner.calls == []


def test_restart_privd_while_serving_exits(tmp_path: object) -> None:
    env = make_env(tmp_path, serving=True)  # type: ignore[arg-type]
    result = services.restart(env.ctx, {"name": "meshbox-privd"})
    assert result["queued"] is True
    assert env.ctx.exit_requested is True
    assert env.runner.calls == []


def test_status(env: Env) -> None:
    env.runner.on(["/usr/bin/systemctl", "show"], ok("ActiveState=failed\nResult=exit-code\n"))
    result = services.status(env.ctx, {"name": "meshbox"})
    assert result["name"] == "meshbox"
    assert result["unit"] == "meshbox.service"
    assert result["active"] == "failed"
    assert result["result"] == "exit-code"


JOURNAL = "\n".join(
    [
        json.dumps(
            {
                "__REALTIME_TIMESTAMP": "1792465562000000",
                "PRIORITY": "6",
                "MESSAGE": "arrancó",
                "_PID": "812",
                "SYSLOG_IDENTIFIER": "meshbox",
            }
        ),
        json.dumps(
            {
                "__REALTIME_TIMESTAMP": "1792465563000000",
                "PRIORITY": "3",
                "MESSAGE": list("hola\xff".encode("latin-1")),
            }
        ),
        "no es json",
        "[1, 2]",
        json.dumps({"MESSAGE": {"raro": True}, "_PID": "x"}),
        "",
    ]
)


def test_logs_read(env: Env) -> None:
    env.runner.on(["/usr/bin/journalctl"], ok(JOURNAL))
    result = services.logs_read(env.ctx, {"unit": "meshbox", "lines": 50, "since": "-1h"})
    assert result["unit"] == "meshbox.service"
    entries = result["entries"]
    assert len(entries) == 3
    assert entries[0] == {
        "ts": 1792465562.0,
        "priority": 6,
        "message": "arrancó",
        "pid": 812,
        "identifier": "meshbox",
    }
    assert entries[1]["message"].startswith("hola")
    assert entries[2]["message"] == ""
    assert entries[2]["pid"] is None
    assert env.runner.argvs() == [
        [
            "/usr/bin/journalctl",
            "--unit=meshbox.service",
            "--lines=50",
            "--output=json",
            "--no-pager",
            "--quiet",
            "--since=-1h",
        ]
    ]


def test_logs_defaults_and_full_unit_name(env: Env) -> None:
    services.logs_read(env.ctx, {"unit": "NetworkManager.service"})
    assert env.runner.argvs()[0][1:3] == ["--unit=NetworkManager.service", "--lines=200"]


def test_logs_message_is_truncated(env: Env) -> None:
    env.runner.on(["/usr/bin/journalctl"], ok(json.dumps({"MESSAGE": "x" * 10000})))
    result = services.logs_read(env.ctx, {"unit": "mosquitto"})
    assert len(result["entries"][0]["message"]) == services.MAX_MESSAGE


@pytest.mark.parametrize(
    "since",
    ["today", "yesterday", "now", "-30min", "-2d", "@1792465562", "2026-10-20", "2026-10-20 08:00"],
)
def test_logs_since_valid(env: Env, since: str) -> None:
    services.logs_read(env.ctx, {"unit": "meshbox", "since": since})
    assert env.runner.argvs()[0][-1] == f"--since={since}"


@pytest.mark.parametrize(
    "args",
    [
        {"unit": "sshd"},
        {"unit": "nginx.service"},
        {"unit": "meshbox", "lines": 0},
        {"unit": "meshbox", "lines": 2001},
        {"unit": "meshbox", "lines": "100"},
        {"unit": "meshbox", "lines": True},
        {"unit": "meshbox", "since": "--output=cat"},
        {"unit": "meshbox", "since": "1 hour ago; reboot"},
        {"unit": "meshbox", "since": "-1h --grep x"},
        {"unit": "meshbox", "since": 5},
        {"unit": "meshbox", "follow": True},
        {"lines": 10},
    ],
)
def test_logs_invalid(env: Env, args: dict) -> None:
    with pytest.raises(CommandError) as exc:
        services.logs_read(env.ctx, args)
    assert exc.value.code == "invalid_args"
    assert env.runner.calls == []
