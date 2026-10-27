"""Servidor por socket Unix: protocolo, credenciales, inactividad y activación por systemd."""

from __future__ import annotations

import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from privd_testkit import Env, RecordingOwner

import meshbox_privd

pytestmark = pytest.mark.linux

PRIVD = Path(meshbox_privd.__file__).resolve()


@pytest.fixture
def short_dir() -> Iterator[Path]:
    """AF_UNIX admite rutas de hasta 108 bytes: se usa un directorio corto en /tmp."""
    path = Path(tempfile.mkdtemp(prefix="pv-", dir="/tmp"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


def request(path: Path, payload: bytes, timeout: float = 5.0) -> bytes:
    """Cliente mínimo: envía, cierra la escritura (EOF) y lee hasta que el servidor corta."""
    chunks = []
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(str(path))
        try:
            client.sendall(payload)
            client.shutdown(socket.SHUT_WR)
            while True:
                data = client.recv(65536)
                if not data:
                    break
                chunks.append(data)
        except (ConnectionResetError, BrokenPipeError):
            pass  # el servidor cortó sin leer todo (petición rechazada o demasiado larga)
    return b"".join(chunks)


class Server:
    def __init__(self, env: Env, path: Path, idle: float) -> None:
        self.env = env
        self.path = path
        self.sock = meshbox_privd.bind_socket(path)
        self.result: list[int] = []
        self.thread = threading.Thread(
            target=lambda: self.result.append(meshbox_privd.serve(env.ctx, self.sock, idle)),
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        self.env.ctx.exit_requested = True
        self.thread.join(5)
        self.sock.close()


@pytest.fixture
def server(env: Env, short_dir: Path) -> Iterator[Server]:
    srv = Server(env, short_dir / "privd.sock", idle=60)
    yield srv
    srv.stop()


def test_socket_permissions(server: Server) -> None:
    mode = os.stat(server.path).st_mode
    assert stat.S_ISSOCK(mode)
    assert stat.S_IMODE(mode) == 0o660


def test_ping_roundtrip(server: Server) -> None:
    raw = request(server.path, b'{"cmd":"ping","request_id":"x1"}\n')
    assert raw.endswith(b"\n")
    assert raw.count(b"\n") == 1
    response = json.loads(raw)
    assert response["ok"] is True
    assert response["request_id"] == "x1"


def test_only_first_line_is_processed(server: Server) -> None:
    raw = request(server.path, b'{"cmd":"ping"}\r\n{"cmd":"system.reboot"}\n')
    assert json.loads(raw)["ok"] is True
    assert server.env.runner.calls == []


def test_invalid_json_over_socket(server: Server) -> None:
    response = json.loads(request(server.path, b"hola\n"))
    assert response["error"]["code"] == "invalid_json"


def test_request_too_long(server: Server) -> None:
    payload = b"a" * (meshbox_privd.MAX_REQUEST_BYTES + 10)
    response = json.loads(request(server.path, payload))
    assert response["error"]["message"] == "petición demasiado larga"


def test_eof_without_newline_and_silent_client(server: Server) -> None:
    response = json.loads(request(server.path, b'{"cmd":"ping"}'))
    assert response["ok"] is True
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(server.path))
    # El servidor sigue atendiendo después de un cliente que no mandó nada.
    assert json.loads(request(server.path, b'{"cmd":"ping"}\n'))["ok"] is True


def test_rejected_peer_gets_no_answer(server: Server, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(meshbox_privd, "peer_allowed", lambda ctx, peer: False)
    assert request(server.path, b'{"cmd":"ping"}\n') == b""


def test_exit_requested_stops_server(env: Env, short_dir: Path) -> None:
    env.ctx.serving = True
    srv = Server(env, short_dir / "p.sock", idle=60)
    raw = request(srv.path, b'{"cmd":"service.restart","args":{"name":"meshbox-privd"}}\n')
    assert json.loads(raw)["ok"] is True
    srv.thread.join(5)
    assert not srv.thread.is_alive()
    assert srv.result == [0]
    srv.sock.close()


def test_idle_timeout_waits_for_jobs(env: Env, short_dir: Path) -> None:
    gate = threading.Event()
    env.ctx.jobs.start("update", lambda job: gate.wait(10) and {}, group="update")
    srv = Server(env, short_dir / "p.sock", idle=0.2)
    time.sleep(1.5)
    assert srv.thread.is_alive()
    gate.set()
    srv.thread.join(5)
    assert not srv.thread.is_alive()
    srv.sock.close()


def test_peer_allowed_rules(env: Env) -> None:
    uid = os.geteuid()
    assert meshbox_privd.peer_allowed(env.ctx, None) is True
    assert meshbox_privd.peer_allowed(env.ctx, (1, uid, 1)) is True
    assert meshbox_privd.peer_allowed(env.ctx, (1, 0, 0)) is True
    assert meshbox_privd.peer_allowed(env.ctx, (1, 4242, 4242)) is False
    env.ctx.owner = RecordingOwner(meshbox_ids=(999, 998))  # type: ignore[assignment]
    assert meshbox_privd.peer_allowed(env.ctx, (1, 999, 1)) is True
    assert meshbox_privd.peer_allowed(env.ctx, (1, 4242, 998)) is True
    assert meshbox_privd.peer_allowed(env.ctx, (1, 4242, 4242)) is False


def test_peer_credentials(short_dir: Path) -> None:
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    with left, right:
        creds = meshbox_privd.peer_credentials(left)
        assert creds is not None
        assert creds[0] == os.getpid()
        assert creds[1] == os.geteuid()


def test_read_request_in_chunks() -> None:
    left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    with left, right:
        right.sendall(b'{"cmd":')
        right.sendall(b'"ping"}\nresto')
        assert meshbox_privd.read_request(left) == b'{"cmd":"ping"}'


def test_bind_socket_replaces_stale_socket(short_dir: Path) -> None:
    path = short_dir / "viejo.sock"
    old = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old.bind(str(path))
    old.close()
    sock = meshbox_privd.bind_socket(path)
    sock.close()
    assert stat.S_ISSOCK(os.stat(path).st_mode)


def test_systemd_listen_socket_ignores_foreign_pid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LISTEN_FDS", "1")
    monkeypatch.setenv("LISTEN_PID", str(os.getpid() + 1))
    assert meshbox_privd.systemd_listen_socket() is None
    monkeypatch.setenv("LISTEN_PID", "x")
    assert meshbox_privd.systemd_listen_socket() is None
    monkeypatch.delenv("LISTEN_FDS")
    assert meshbox_privd.systemd_listen_socket() is None


def _wait_for(predicate: object, timeout: float = 10.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():  # type: ignore[operator]
            return True
        time.sleep(0.05)
    return False


def test_socket_activation_like_systemd(short_dir: Path) -> None:
    """Simula systemd: socket heredado en el fd 3 con LISTEN_FDS/LISTEN_PID del propio proceso."""
    path = short_dir / "privd.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    listener.listen(4)
    wrapper = short_dir / "wrap.py"
    wrapper.write_text(
        "import os, sys\n"
        "os.dup2(int(os.environ.pop('TEST_FD')), 3)\n"
        "os.environ['LISTEN_FDS'] = '1'\n"
        "os.environ['LISTEN_PID'] = str(os.getpid())\n"
        f"os.execv(sys.executable, [sys.executable, {str(PRIVD)!r}, '--config', "
        f"{str(short_dir / 'no-existe.toml')!r}, 'serve', '--idle-timeout', '1'])\n"
    )
    env = dict(os.environ, TEST_FD=str(listener.fileno()))
    proc = subprocess.Popen(
        [sys.executable, str(wrapper)],
        pass_fds=(listener.fileno(),),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        response = json.loads(request(path, b'{"cmd":"ping"}\n', timeout=10))
        assert response["ok"] is True
        assert response["result"]["mode"] == "shared"
        assert proc.wait(15) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
        listener.close()
    output = proc.stdout.read().decode() if proc.stdout else ""
    assert "<6>privd: cmd=ping" in output
    assert "<4>privd: no existe" in output
    # El socket es de systemd: privd no lo borra al salir.
    assert path.exists()


def test_serve_binds_own_socket_and_cleans_up(short_dir: Path) -> None:
    path = short_dir / "propio.sock"
    proc = subprocess.Popen(
        [
            sys.executable,
            str(PRIVD),
            "--config",
            str(short_dir / "no-existe.toml"),
            "serve",
            "--socket",
            str(path),
            "--idle-timeout",
            "1",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert _wait_for(path.exists)
        assert json.loads(request(path, b'{"cmd":"ping"}\n'))["ok"] is True
        assert proc.wait(15) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
    assert not path.exists()


def test_serve_stops_on_sigterm(short_dir: Path) -> None:
    path = short_dir / "sig.sock"
    proc = subprocess.Popen(
        [sys.executable, str(PRIVD), "--config", "/no/existe", "serve", "--socket", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert _wait_for(path.exists)
        proc.terminate()
        assert proc.wait(10) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
