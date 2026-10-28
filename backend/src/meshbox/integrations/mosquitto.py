"""Cuentas y ACL de Mosquitto vía privd (secciones 14.2 y 14.4)."""

from __future__ import annotations

import re
import socket
import time
from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection, text

from ..config import generate_password

if TYPE_CHECKING:
    from ..app import Service

PURPOSE_PREFIX = {"gateway": "gw-", "integration": "int-", "debug": "dbg-"}
INGEST_USER = "meshbox-ingest"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,27}$")


def purpose_from_username(username: str) -> str | None:
    if username == INGEST_USER:
        return "ingest"
    for purpose, prefix in PURPOSE_PREFIX.items():
        if username.startswith(prefix):
            return purpose
    return None


def lan_ip() -> str:
    """IP de la interfaz con ruta por defecto (sin enviar nada: UDP no conecta de verdad)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("192.0.2.1", 9))  # TEST-NET-1, no se envían datos
            return str(s.getsockname()[0])
        except OSError:
            return "127.0.0.1"


def heltec_commands(
    *, host: str, username: str, password: str, root: str, port: str = "COM5"
) -> dict[str, Any]:
    """Comandos de la CLI de Meshtastic para el gateway (25.1), listos para PowerShell."""
    mqtt = (
        f"meshtastic --port {port} --set mqtt.enabled true --set mqtt.address {host} "
        f'--set mqtt.username {username} --set mqtt.password "{password}" '
        "--set mqtt.encryption_enabled false --set mqtt.json_enabled false --set mqtt.tls_enabled false "
        f"--set mqtt.proxy_to_client_enabled false --set mqtt.root {root} --set mqtt.map_reporting_enabled true"
    )
    channel = f"meshtastic --port {port} --ch-index 0 --ch-set uplink_enabled true --ch-set downlink_enabled false"
    wifi = f'meshtastic --port {port} --set network.wifi_enabled true --set network.wifi_ssid "<red>" --set network.wifi_psk "<clave>"'
    optional = f"meshtastic --port {port} --set device.role CLIENT_MUTE --set lora.tx_power 10"
    return {
        "commands": [mqtt, channel, wifi],
        "optional_gateway_only": optional,
        "notes": [
            f"mqtt.address es la IP literal de este equipo ({host}): así el firmware sube también "
            'los paquetes de nodos que no marcaron "OK to MQTT" (broker en IP privada).',
            "Con el nodo en la red WiFi se puede usar --host <ip-del-heltec> en lugar de --port.",
            "Cada --set reinicia el nodo. Los canales distintos del público deben quedar con uplink_enabled false.",
            "El rol CLIENT_MUTE y la potencia baja solo convienen si el nodo no tiene que retransmitir (ADR 0011).",
        ],
    }


class MosquittoAdmin:
    def __init__(self, service: Service) -> None:
        self.service = service

    @property
    def root(self) -> str:
        return self.service.cfg.mqtt_root or f"msh/AR/{self.service.cfg.site.slug}"

    @property
    def events_prefix(self) -> str:
        return self.service.cfg.mqtt_out.prefix.split("/")[0] or "meshbox"

    async def accounts(self) -> list[dict[str, Any]]:
        def q(conn: Connection) -> list[dict[str, Any]]:
            rows = (
                conn.execute(
                    text(
                        "SELECT username, purpose, created_at, note FROM mqtt_accounts ORDER BY username"
                    )
                )
                .mappings()
                .all()
            )
            return [dict(r) for r in rows]

        return await self.service.db.read(q)

    async def _insert(self, username: str, purpose: str, note: str | None) -> None:
        await self.service.writer.run(
            lambda c: c.execute(
                text(
                    "INSERT INTO mqtt_accounts (username, purpose, created_at, note) VALUES (:u, :p, :t, :n) "
                    "ON CONFLICT(username) DO UPDATE SET purpose = excluded.purpose"
                ),
                {"u": username, "p": purpose, "t": time.time(), "n": note},
            )
        )

    async def adopt_existing(self) -> list[str]:
        """Registra en la base las cuentas que ya estaban en /etc/mosquitto/passwd (instalación a mano)."""
        try:
            listed = await self.service.priv.call("mosquitto.account.list")
        except Exception:
            return []
        known = {a["username"] for a in await self.accounts()}
        adopted = []
        for item in listed.get("accounts", []):
            username = str(item.get("username", ""))
            purpose = purpose_from_username(username)
            if purpose and username not in known:
                await self._insert(username, purpose, "adoptada de passwd")
                adopted.append(username)
        return adopted

    def acl_payload(self, accounts: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "root": self.root,
            "events_prefix": self.events_prefix,
            "accounts": [{"username": a["username"], "purpose": a["purpose"]} for a in accounts],
        }

    def acl_preview(self, accounts: list[dict[str, Any]]) -> str:
        lines = ["# ACL generada por meshbox"]
        for a in accounts:
            lines.append(f"\nuser {a['username']}")
            match a["purpose"]:
                case "gateway":
                    lines.append(f"topic readwrite {self.root}/#")
                case "ingest":
                    lines += [f"topic read {self.root}/#", f"topic write {self.events_prefix}/#"]
                case "integration":
                    lines.append(f"topic read {self.events_prefix}/events/#")
                case "debug":
                    lines.append(f"topic read {self.root}/#")
        return "\n".join(lines) + "\n"

    async def write_acl(self) -> None:
        accounts = await self.accounts()
        await self.service.priv.call("mosquitto.acl.write", **self.acl_payload(accounts))
        await self.service.priv.call("mosquitto.reload")

    async def create(self, name: str, purpose: str, note: str | None = None) -> tuple[str, str]:
        if purpose not in PURPOSE_PREFIX:
            raise ValueError("propósito no válido (gateway, integration, debug)")
        name = name.strip().lower()
        if not NAME_RE.match(name):
            raise ValueError("nombre no válido (minúsculas, números, - y _)")
        username = PURPOSE_PREFIX[purpose] + name
        if any(a["username"] == username for a in await self.accounts()):
            raise ValueError("la cuenta ya existe")
        password = generate_password(24)
        await self.service.priv.call("mosquitto.account.set", username=username, password=password)
        await self._insert(username, purpose, note)
        await self.write_acl()
        return username, password

    async def ensure_ingest(self) -> str | None:
        """Crea la cuenta `meshbox-ingest` si falta su clave; devuelve la clave nueva o None."""
        secrets = self.service.secrets
        if secrets.get(f"mqtt.{INGEST_USER}"):
            await self._insert(INGEST_USER, "ingest", None)
            return None
        password = generate_password(24)
        await self.service.priv.call(
            "mosquitto.account.set", username=INGEST_USER, password=password
        )
        secrets.set(f"mqtt.{INGEST_USER}", password)
        await self._insert(INGEST_USER, "ingest", None)
        return password

    async def rotate(self, username: str) -> str:
        accounts = {a["username"]: a for a in await self.accounts()}
        if username not in accounts:
            raise KeyError(username)
        password = generate_password(24)
        await self.service.priv.call("mosquitto.account.set", username=username, password=password)
        if username == INGEST_USER:
            self.service.secrets.set(f"mqtt.{INGEST_USER}", password)
        await self.service.priv.call("mosquitto.reload")
        return password

    async def delete(self, username: str) -> None:
        if username == INGEST_USER:
            raise ValueError("la cuenta de la aplicación no se puede borrar")
        await self.service.priv.call("mosquitto.account.delete", username=username)
        await self.service.writer.run(
            lambda c: c.execute(
                text("DELETE FROM mqtt_accounts WHERE username = :u"), {"u": username}
            )
        )
        await self.write_acl()
