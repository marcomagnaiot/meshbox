"""Modo de una sola vez (`call`) que usan el instalador y el primer arranque."""

from __future__ import annotations

import io
import json
import logging
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from privd_testkit import Env, fail

import meshbox_privd
from commands.core import PRIVD_VERSION

PRIVD = Path(meshbox_privd.__file__).resolve()


def run_cli(stdin: bytes, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, str(PRIVD), "--config", "no-existe.toml", *args],
        input=stdin,
        capture_output=True,
        check=False,
        timeout=60,
    )


def test_cli_ping() -> None:
    proc = run_cli(b'{"cmd": "ping", "request_id": "cli"}\n', "call")
    assert proc.returncode == 0
    response = json.loads(proc.stdout)
    assert response == {
        "request_id": "cli",
        "ok": True,
        "result": {"version": PRIVD_VERSION, "mode": "shared"},
    }
    assert b"cmd=ping" in proc.stderr


def test_cli_pretty_printed_json() -> None:
    proc = run_cli(b'{\n  "cmd": "ping"\n}\n', "call")
    assert proc.returncode == 0


def test_cli_invalid_json() -> None:
    proc = run_cli(b"no es json", "call")
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["error"]["code"] == "invalid_json"


def test_cli_same_validations_as_socket() -> None:
    proc = run_cli(json.dumps({"cmd": "hotspot.start"}).encode(), "call")
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["error"]["code"] == "not_allowed_in_shared_mode"


def test_cli_version() -> None:
    proc = run_cli(b"", "version")
    assert proc.returncode == 0
    assert proc.stdout.decode().strip() == PRIVD_VERSION


@pytest.fixture
def restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


def test_main_in_process(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    restore_logging: None,
) -> None:
    stdin = io.TextIOWrapper(io.BytesIO(b'{"cmd":"ping"}'))
    monkeypatch.setattr(sys, "stdin", stdin)
    assert meshbox_privd.main(["--config", "no-existe.toml", "call"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_run_call_waits_for_jobs(env: Env) -> None:
    response, code = meshbox_privd.run_call(env.ctx, b'{"cmd":"system.reboot"}')
    assert code == 0
    assert response["result"]["state"] == "succeeded"
    assert response["result"]["kind"] == "power"
    assert env.runner.argvs() == [["/usr/bin/systemctl", "reboot"]]


def test_run_call_failed_job_exit_code(env: Env) -> None:
    env.runner.on(["/usr/bin/systemctl", "poweroff"], fail(1, "no se pudo"))
    response, code = meshbox_privd.run_call(env.ctx, b'{"cmd":"system.shutdown"}')
    assert code == 1
    assert response["ok"] is True
    assert response["result"]["state"] == "failed"
    assert "no se pudo" in response["result"]["message"]


def test_run_call_too_long(env: Env) -> None:
    response, code = meshbox_privd.run_call(env.ctx, b"x" * (meshbox_privd.MAX_REQUEST_BYTES + 1))
    assert code == 1
    assert response["error"]["code"] == "invalid_json"


def test_journal_formatter_prefixes() -> None:
    formatter = meshbox_privd.JournalFormatter("%(message)s")
    record = logging.LogRecord("privd", logging.WARNING, __file__, 1, "uno\ndos", None, None)
    assert formatter.format(record) == "<4>uno\n<4>dos"
    record = logging.LogRecord("privd", logging.INFO, __file__, 1, "info", None, None)
    assert formatter.format(record) == "<6>info"


def test_setup_logging_modes(restore_logging: None) -> None:
    meshbox_privd.setup_logging(journal=True)
    handler = logging.getLogger().handlers[0]
    assert isinstance(handler.formatter, meshbox_privd.JournalFormatter)
    meshbox_privd.setup_logging(journal=False)
    handler = logging.getLogger().handlers[0]
    assert not isinstance(handler.formatter, meshbox_privd.JournalFormatter)


def test_build_context_uses_embedded_key() -> None:
    config, _ = meshbox_privd.load_config(Path("no-existe.toml"))
    ctx = meshbox_privd.build_context(config, serving=False)
    assert "BEGIN PUBLIC KEY" in ctx.public_key_pem
    assert ctx.serving is False
