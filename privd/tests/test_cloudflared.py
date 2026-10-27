"""Túnel de Cloudflare en modo token (15.1)."""

from __future__ import annotations

import base64
import json
import stat

import pytest
from privd_testkit import Env, ok

from commands import cloudflared
from commands.core import CommandError

# Forma real de un token de túnel: base64 de {"a": cuenta, "t": túnel, "s": secreto}.
TOKEN = base64.b64encode(
    json.dumps(
        {
            "a": "0123456789abcdef0123456789abcdef",
            "t": "6ff42ae2-765d-4adf-8112-31c55c1551ef",
            "s": "c2VjcmV0bw==",
        }
    ).encode()
).decode()


def test_realistic_token_is_valid() -> None:
    assert len(TOKEN) > 100
    assert cloudflared.validate_token(TOKEN) == TOKEN


@pytest.mark.parametrize(
    "token",
    [
        "corto",
        "a" * 49,
        "a" * 4097,
        TOKEN + " ",
        TOKEN + "\nOTRA=1",
        '"' + TOKEN + '"',
        "$(reboot)" + "a" * 60,
        "a" * 60 + "\\",
        "a" * 60 + "===",
        12345,
    ],
)
def test_invalid_tokens(token: object) -> None:
    with pytest.raises(CommandError) as exc:
        cloudflared.validate_token(token)
    assert exc.value.code == "invalid_args"


def test_set_token_writes_env_file(env: Env) -> None:
    assert cloudflared.set_token(env.ctx, {"token": TOKEN}) == {"written": True}
    path = env.ctx.paths.tunnel_dir / "cloudflared.env"
    assert path.read_text() == f"TUNNEL_TOKEN={TOKEN}\n"
    assert env.runner.calls == []


@pytest.mark.linux
def test_set_token_permissions(env: Env) -> None:
    cloudflared.set_token(env.ctx, {"token": TOKEN})
    assert stat.S_IMODE(env.ctx.paths.tunnel_dir.stat().st_mode) == 0o700
    path = env.ctx.paths.tunnel_dir / "cloudflared.env"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_enable_requires_token(env: Env) -> None:
    with pytest.raises(CommandError) as exc:
        cloudflared.enable(env.ctx, {})
    assert exc.value.code == "command_failed"
    assert env.runner.calls == []


def test_enable_and_restart(env: Env) -> None:
    cloudflared.set_token(env.ctx, {"token": TOKEN})
    assert cloudflared.enable(env.ctx, {}) == {"enabled": True}
    assert env.runner.argvs() == [
        ["/usr/bin/systemctl", "enable", "meshbox-cloudflared.service"],
        ["/usr/bin/systemctl", "--no-block", "restart", "meshbox-cloudflared.service"],
    ]
    assert cloudflared.restart(env.ctx, {}) == {"queued": True}


def test_restart_requires_token(env: Env) -> None:
    with pytest.raises(CommandError):
        cloudflared.restart(env.ctx, {})


def test_disable_keeps_or_forgets_token(env: Env) -> None:
    cloudflared.set_token(env.ctx, {"token": TOKEN})
    assert cloudflared.disable(env.ctx, {}) == {"enabled": False, "token_removed": False}
    assert (env.ctx.paths.tunnel_dir / "cloudflared.env").exists()
    result = cloudflared.disable(env.ctx, {"forget_token": True})
    assert result == {"enabled": False, "token_removed": True}
    assert not (env.ctx.paths.tunnel_dir / "cloudflared.env").exists()
    assert env.runner.argvs()[0] == [
        "/usr/bin/systemctl",
        "disable",
        "--now",
        "meshbox-cloudflared.service",
    ]


def test_disable_rejects_non_bool(env: Env) -> None:
    with pytest.raises(CommandError):
        cloudflared.disable(env.ctx, {"forget_token": "yes"})


def test_status(env: Env) -> None:
    env.runner.on(["/usr/bin/systemctl", "show"], ok("ActiveState=active\nSubState=running\n"))
    result = cloudflared.status(env.ctx, {})
    assert result["active"] == "active"
    assert result["token_configured"] is False
    assert TOKEN not in str(result)
