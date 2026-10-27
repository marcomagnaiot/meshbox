"""Piezas comunes: ejecutor real de procesos, dueños, escritura atómica, salud HTTP y trabajos."""

from __future__ import annotations

import http.server
import json
import os
import stat
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from privd_testkit import Env

from commands import core
from commands.core import CommandError, OwnerOps, SubprocessRunner
from commands.jobs import JobManager

# ---------------------------------------------------------------------------
# Ejecutor real
# ---------------------------------------------------------------------------


def test_runner_requires_absolute_binary() -> None:
    with pytest.raises(CommandError) as exc:
        SubprocessRunner().run(["ls", "-l"])
    assert "ruta absoluta" in exc.value.message
    with pytest.raises(CommandError):
        SubprocessRunner().run([])


@pytest.mark.linux
def test_runner_captures_output_and_clean_env() -> None:
    result = SubprocessRunner().run(
        ["/bin/sh", "-c", 'echo "$LC_ALL:$PATH:${SECRETO:-nada}"; echo err >&2; exit 3'],
        env={"EXTRA": "1"},
    )
    assert result.returncode == 3
    assert result.out.strip() == f"C.UTF-8:{core.SAFE_PATH}:nada"
    assert result.err.strip() == "err"


@pytest.mark.linux
def test_runner_passes_stdin_and_umask(tmp_path: Path) -> None:
    target = tmp_path / "nuevo"
    result = SubprocessRunner().run(
        ["/bin/sh", "-c", f'cat > "{target}"'], input=b"hola", umask=0o077
    )
    assert result.returncode == 0
    assert target.read_bytes() == b"hola"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


@pytest.mark.linux
def test_runner_stdin_is_devnull_by_default() -> None:
    result = SubprocessRunner().run(["/bin/sh", "-c", "cat"], timeout=5)
    assert result.returncode == 0
    assert result.stdout == b""


@pytest.mark.linux
def test_runner_timeout() -> None:
    started = time.monotonic()
    with pytest.raises(CommandError) as exc:
        SubprocessRunner().run(["/bin/sleep", "5"], timeout=0.3)
    assert exc.value.code == "timeout"
    assert time.monotonic() - started < 4


@pytest.mark.linux
def test_runner_respects_request_deadline() -> None:
    with core.deadline(0.3), pytest.raises(CommandError) as exc:
        SubprocessRunner().run(["/bin/sleep", "5"], timeout=60)
    assert exc.value.code == "timeout"
    with core.deadline(-1), pytest.raises(CommandError) as exc:
        SubprocessRunner().run(["/bin/true"])
    assert exc.value.code == "timeout"


@pytest.mark.linux
def test_runner_missing_binary_and_not_executable(tmp_path: Path) -> None:
    with pytest.raises(CommandError, match="no se encontró"):
        SubprocessRunner().run(["/no/existe/binario"])
    script = tmp_path / "sin-permiso"
    script.write_text("#!/bin/sh\n")
    script.chmod(0o644)
    with pytest.raises(CommandError, match="no se pudo ejecutar"):
        SubprocessRunner().run([str(script)])


def test_deadline_is_per_thread() -> None:
    assert core.remaining_time(50) == 50
    with core.deadline(10):
        assert 9 < core.remaining_time(50) <= 10
        seen: list[float] = []
        thread = threading.Thread(target=lambda: seen.append(core.remaining_time(50)))
        thread.start()
        thread.join()
        assert seen == [50]
    assert core.remaining_time(50) == 50


def test_clean_text() -> None:
    assert core.clean_text("  hola\x1b[31m\n ") == "hola?[31m"
    assert core.clean_text("x" * 1000, limit=10) == "…" + "x" * 10


def test_run_checked_message(env: Env) -> None:
    from privd_testkit import fail

    env.runner.on(["/usr/bin/false"], fail(2, "", "salida estándar"))
    with pytest.raises(CommandError) as exc:
        core.run_checked(env.ctx, ["/usr/bin/false"])
    assert exc.value.message == "false falló (código 2): salida estándar"


def test_command_error_rejects_unknown_codes() -> None:
    with pytest.raises(ValueError):
        CommandError("otro", "x")


# ---------------------------------------------------------------------------
# Validaciones y archivos
# ---------------------------------------------------------------------------


def test_get_int_and_bool_and_str() -> None:
    assert core.get_int({}, "n", minimum=1, maximum=5, default=3) == 3
    with pytest.raises(CommandError):
        core.get_int({}, "n", minimum=1, maximum=5)
    with pytest.raises(CommandError):
        core.get_int({"n": 1.5}, "n", minimum=1, maximum=5)
    assert core.get_bool({"b": True}, "b") is True
    with pytest.raises(CommandError):
        core.get_bool({"b": 1}, "b")
    with pytest.raises(CommandError):
        core.get_str({"s": 1}, "s")
    with pytest.raises(CommandError):
        core.check_keys([], ())  # type: ignore[arg-type]


def test_version_key_orders_numerically() -> None:
    versions = ["0.10.0", "0.9.1", "1.0.0", "0.9.10"]
    assert sorted(versions, key=core.version_key) == ["0.9.1", "0.9.10", "0.10.0", "1.0.0"]


def test_parse_key_values() -> None:
    assert core.parse_key_values("A=1\nsin-igual\nB = dos=2\n") == {"A": "1", "B": "dos=2"}


def test_atomic_write_cleans_temp_on_error(env: Env) -> None:
    class Boom(Exception):
        pass

    def chown(path: Path, user: str, group: str) -> None:
        raise Boom

    env.owner.chown = chown  # type: ignore[method-assign]
    target = env.root / "archivo"
    with pytest.raises(Boom):
        core.atomic_write(env.ctx, target, b"datos", mode=0o600, owner=("x", "y"))
    assert list(env.root.glob(".archivo.*")) == []
    assert not target.exists()


def test_ensure_dir_rejects_symlink(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "enlace"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("sin permiso para crear enlaces")
    with pytest.raises(CommandError, match="enlace"):
        core.ensure_dir(link, 0o700)


@pytest.mark.linux
def test_owner_ops_with_current_user(tmp_path: Path) -> None:
    import grp
    import pwd

    user = pwd.getpwuid(os.getuid()).pw_name
    group = grp.getgrgid(os.getgid()).gr_name
    target = tmp_path / "archivo"
    target.write_text("x")
    ops = OwnerOps()
    ops.chown(target, user, group)
    assert target.stat().st_uid == os.getuid()
    assert ops.user_ids(user) == (os.getuid(), pwd.getpwuid(os.getuid()).pw_gid)
    assert ops.user_ids("usuario-que-no-existe-meshbox") is None
    with pytest.raises(CommandError, match="usuario"):
        ops.ids("usuario-que-no-existe-meshbox", group)
    with pytest.raises(CommandError, match="grupo"):
        ops.ids(user, "grupo-que-no-existe-meshbox")


# ---------------------------------------------------------------------------
# Salud por HTTP
# ---------------------------------------------------------------------------


class _Health(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/api/v1/health":
            body = json.dumps({"status": "ok", "version": "0.2.0"}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(503)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def health_server() -> Iterator[str]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Health)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_default_http_get(health_server: str) -> None:
    code, body = core._default_http_get(f"{health_server}/api/v1/health", 3)
    assert code == 200
    assert json.loads(body)["version"] == "0.2.0"
    code, body = core._default_http_get(f"{health_server}/otra", 3)
    assert code == 503
    assert body == b""


# ---------------------------------------------------------------------------
# Trabajos
# ---------------------------------------------------------------------------


def test_job_lifecycle_and_persistence(tmp_path: Path) -> None:
    manager = JobManager(tmp_path / "estado")
    finished: list[str] = []
    manager.on_finished(lambda job: finished.append(job.state))

    def work(job: object) -> dict:
        job.update(step="paso", progress=0.5, result={"parcial": 1})  # type: ignore[attr-defined]
        return {"final": 2}

    job = manager.start("update", work, group="update", meta={"version": "0.2.0"})
    manager.wait(job.id, 5)
    data = manager.get(job.id)
    assert data is not None
    assert data["state"] == "succeeded"
    assert data["result"] == {"parcial": 1, "final": 2}
    assert data["meta"] == {"version": "0.2.0"}
    assert finished == ["succeeded"]
    on_disk = json.loads((tmp_path / "estado/jobs" / f"{job.id}.json").read_text())
    assert on_disk["state"] == "succeeded"
    assert manager.latest("update")["job"] == job.id  # type: ignore[index]
    assert manager.latest("otro") is None


def test_job_errors(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    manager = JobManager(tmp_path)
    manager.on_finished(lambda job: 1 / 0)  # el aviso que falla no rompe nada

    def broken(job: object) -> dict:
        raise RuntimeError("detalle interno")

    def refused(job: object) -> dict:
        raise CommandError("command_failed", "no se pudo")

    a = manager.start("x", broken, group="a")
    b = manager.start("x", refused, group="b")
    manager.wait_all(5)
    assert manager.get(a.id)["state"] == "failed"  # type: ignore[index]
    assert "detalle" not in manager.get(a.id)["message"]  # type: ignore[index]
    assert manager.get(b.id)["message"] == "no se pudo"  # type: ignore[index]
    assert manager.get(b.id)["error_code"] == "command_failed"  # type: ignore[index]
    with pytest.raises(ValueError):
        manager.update(a, desconocido=1)


def test_jobs_interrupted_and_pruned(tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    running = {"job": "aaaaaaaaaaaa", "kind": "update", "state": "running", "started_at": 1.0}
    done = {"job": "bbbbbbbbbbbb", "kind": "update", "state": "succeeded", "started_at": 2.0}
    (jobs_dir / "aaaaaaaaaaaa.json").write_text(json.dumps(running))
    (jobs_dir / "bbbbbbbbbbbb.json").write_text(json.dumps(done))
    (jobs_dir / "roto.json").write_text("{no json")
    for i in range(40):
        old = jobs_dir / f"{i:012x}.json"
        old.write_text(json.dumps({"job": old.stem, "kind": "wifi", "state": "succeeded"}))
        os.utime(old, (1, 1))
    manager = JobManager(tmp_path)
    manager.load_persisted()
    assert manager.get("aaaaaaaaaaaa")["state"] == "interrupted"  # type: ignore[index]
    assert manager.get("bbbbbbbbbbbb")["state"] == "succeeded"  # type: ignore[index]
    assert len(list(jobs_dir.glob("*.json"))) <= 30
    assert manager.latest("update")["job"] == "bbbbbbbbbbbb"  # type: ignore[index]
    assert manager.get("cccccccccccc") is None


def test_job_manager_without_state_dir() -> None:
    manager = JobManager(None)
    job = manager.start("power", lambda job: None, group="power")
    manager.wait_all(5)
    assert manager.get(job.id)["state"] == "succeeded"  # type: ignore[index]
    assert manager.latest("otro") is None
    manager.load_persisted()


def test_job_persist_failure_is_tolerated(tmp_path: Path) -> None:
    blocker = tmp_path / "estado"
    blocker.write_text("es un archivo, no un directorio")
    manager = JobManager(blocker)
    job = manager.start("power", lambda job: {"ok": True}, group="power")
    manager.wait_all(5)
    assert manager.get(job.id)["state"] == "succeeded"  # type: ignore[index]
