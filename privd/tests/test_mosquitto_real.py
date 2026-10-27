"""Integración con Mosquitto real: privd crea cuentas con `mosquitto_passwd -U` y escribe la ACL
de 14.2; un broker real con esa configuración debe aplicar exactamente esos permisos.

Busca los binarios en el sistema (paquetes mosquitto y mosquitto-clients) o bajo
MESHBOX_MOSQUITTO_ROOT (raíz con usr/bin y usr/sbin, por ejemplo paquetes .deb extraídos sin
root). Si no los encuentra, se saltea.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from privd_testkit import Env

from commands import mosquitto
from commands.core import CommandError, SubprocessRunner

pytestmark = [pytest.mark.linux, pytest.mark.integration]

ROOT = "msh/AR/viedma"
PASSWORDS = {
    "gw-heltec": "Gateway-clave-123",
    "meshbox-ingest": "Ingest-clave-456",
    "int-ejemplo": "Integracion-789",
    "dbg-dev": "Depuracion-0123",
}


def _binaries() -> dict[str, str] | None:
    prefix = os.environ.get("MESHBOX_MOSQUITTO_ROOT", "")
    found = {}
    for name, rel in {
        "broker": "usr/sbin/mosquitto",
        "passwd": "usr/bin/mosquitto_passwd",
        "pub": "usr/bin/mosquitto_pub",
        "sub": "usr/bin/mosquitto_sub",
    }.items():
        path = Path(prefix or "/") / rel
        if not path.exists():
            return None
        found[name] = str(path)
    return found


BINS = _binaries()
if BINS is None:
    pytestmark.append(pytest.mark.skip(reason="sin binarios de Mosquitto"))


def _lib_env() -> dict[str, str]:
    prefix = os.environ.get("MESHBOX_MOSQUITTO_ROOT")
    if not prefix:
        return {}
    return {"LD_LIBRARY_PATH": str(Path(prefix) / "usr/lib/x86_64-linux-gnu")}


class LibRunner(SubprocessRunner):
    """Ejecutor real que agrega LD_LIBRARY_PATH para binarios extraídos de .deb."""

    def run(self, argv, *, env=None, **kwargs):  # type: ignore[no-untyped-def,override]
        return super().run(argv, env={**_lib_env(), **(env or {})}, **kwargs)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class Broker:
    def __init__(self, env: Env) -> None:
        assert BINS is not None
        self.port = _free_port()
        paths = env.ctx.paths
        self.conf = env.root / "mosquitto-prueba.conf"
        self.conf.write_text(
            f"listener {self.port} 127.0.0.1\n"
            "allow_anonymous false\n"
            f"password_file {paths.mosquitto_passwd}\n"
            f"acl_file {paths.mosquitto_acl}\n"
            "persistence false\n"
            "log_dest stdout\n"
        )
        self.proc = subprocess.Popen(
            [BINS["broker"], "-c", str(self.conf)],
            env={**os.environ, **_lib_env()},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        end = time.monotonic() + 10
        while time.monotonic() < end:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                    return
            except OSError:
                if self.proc.poll() is not None:
                    break
                time.sleep(0.1)
        self.stop()
        raise RuntimeError("el broker no arrancó")

    def reload(self) -> None:
        self.proc.send_signal(signal.SIGHUP)
        time.sleep(0.5)

    def stop(self) -> str:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        return self.proc.stdout.read().decode(errors="replace") if self.proc.stdout else ""

    def _auth(self, user: str, password: str | None) -> list[str]:
        assert BINS is not None
        return [
            "-h",
            "127.0.0.1",
            "-p",
            str(self.port),
            "-u",
            user,
            "-P",
            password or PASSWORDS[user],
        ]

    def publish(self, user: str, topic: str, message: str, password: str | None = None) -> int:
        assert BINS is not None
        proc = subprocess.run(
            [BINS["pub"], *self._auth(user, password), "-t", topic, "-m", message, "-q", "1"],
            env={**os.environ, **_lib_env()},
            capture_output=True,
            timeout=10,
            check=False,
        )
        return proc.returncode

    def receives(self, user: str, sub_topic: str, publisher: str, pub_topic: str) -> bool:
        """¿`user` suscripto a `sub_topic` recibe lo que `publisher` publica en `pub_topic`?"""
        assert BINS is not None
        sub = subprocess.Popen(
            [BINS["sub"], *self._auth(user, None), "-t", sub_topic, "-C", "1", "-W", "3"],
            env={**os.environ, **_lib_env()},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(0.7)
        self.publish(publisher, pub_topic, "hola")
        out, _ = sub.communicate(timeout=10)
        return out.decode().strip() == "hola"


@pytest.fixture
def broker(env: Env) -> Iterator[Broker]:
    assert BINS is not None
    env.ctx.runner = LibRunner()
    env.ctx.bins.mosquitto_passwd = BINS["passwd"]
    for user, password in PASSWORDS.items():
        mosquitto.account_set(env.ctx, {"username": user, "password": password})
    mosquitto.acl_write(
        env.ctx,
        {
            "root": ROOT,
            "events_prefix": "meshbox",
            "accounts": [
                {"username": "gw-heltec", "purpose": "gateway"},
                {"username": "meshbox-ingest", "purpose": "ingest"},
                {"username": "int-ejemplo", "purpose": "integration"},
                {"username": "dbg-dev", "purpose": "debug"},
            ],
        },
    )
    instance = Broker(env)
    yield instance
    instance.stop()


def test_real_mosquitto_passwd_format(env: Env, broker: Broker) -> None:
    lines = env.ctx.paths.mosquitto_passwd.read_text().splitlines()
    assert sorted(line.split(":")[0] for line in lines) == sorted(PASSWORDS)
    assert all(line.split(":", 1)[1].startswith("$7$") for line in lines)
    for password in PASSWORDS.values():
        assert password not in env.ctx.paths.mosquitto_passwd.read_text()
    # mosquitto_passwd no dejó respaldos ni temporales en /etc/mosquitto.
    assert sorted(p.name for p in env.ctx.paths.mosquitto_dir.iterdir()) == [
        "acl",
        "conf.d",
        "passwd",
    ]


def test_wrong_password_is_rejected(broker: Broker) -> None:
    assert (
        broker.publish("gw-heltec", f"{ROOT}/2/e/LongFast/!a", "x", password="otra-clave-123") != 0
    )


def test_gateway_to_ingest(broker: Broker) -> None:
    assert broker.receives("meshbox-ingest", f"{ROOT}/#", "gw-heltec", f"{ROOT}/2/e/MediumFast/!a1")


def test_ingest_events_to_integration(broker: Broker) -> None:
    assert broker.receives(
        "int-ejemplo", "meshbox/events/#", "meshbox-ingest", "meshbox/events/node"
    )


def test_integration_cannot_read_raw_traffic(broker: Broker) -> None:
    assert not broker.receives(
        "int-ejemplo", f"{ROOT}/#", "gw-heltec", f"{ROOT}/2/e/MediumFast/!a2"
    )


def test_debug_reads_raw_but_cannot_publish(broker: Broker) -> None:
    assert broker.receives("dbg-dev", f"{ROOT}/#", "gw-heltec", f"{ROOT}/2/e/MediumFast/!a3")
    # Publicar sin permiso no da error en MQTT 3.1.1: el broker descarta en silencio.
    assert not broker.receives("meshbox-ingest", f"{ROOT}/#", "dbg-dev", f"{ROOT}/2/e/X/!a4")


def test_gateway_cannot_publish_events(broker: Broker) -> None:
    assert not broker.receives(
        "int-ejemplo", "meshbox/events/#", "gw-heltec", "meshbox/events/node"
    )


def test_rotate_and_delete_with_reload(env: Env, broker: Broker) -> None:
    mosquitto.account_set(env.ctx, {"username": "gw-heltec", "password": "Nueva-clave-999"})
    broker.reload()
    assert broker.publish("gw-heltec", f"{ROOT}/2/e/LongFast/!b", "x") != 0
    assert (
        broker.publish("gw-heltec", f"{ROOT}/2/e/LongFast/!b", "x", password="Nueva-clave-999") == 0
    )
    mosquitto.account_delete(env.ctx, {"username": "gw-heltec"})
    broker.reload()
    assert (
        broker.publish("gw-heltec", f"{ROOT}/2/e/LongFast/!b", "x", password="Nueva-clave-999") != 0
    )


def test_real_passwd_rejects_bad_input(env: Env) -> None:
    assert BINS is not None
    env.ctx.runner = LibRunner()
    env.ctx.bins.mosquitto_passwd = BINS["passwd"]
    with pytest.raises(CommandError):
        mosquitto.account_set(env.ctx, {"username": "gw-heltec", "password": "con:dos-puntos"})
