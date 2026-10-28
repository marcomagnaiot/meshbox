"""Administración remota de nodos propios por la malla (ADR 0017).

Como la app Meshtastic: la placa conectada manda mensajes de administración (ADMIN_APP) cifrados
con PKI al nodo, que los acepta solo si tiene la clave pública de la placa en
`security.admin_key`. Cada pedido espera su respuesta por la malla (con varios saltos, decenas de
segundos), así que corre en su propia cola, aparte del estado y la configuración de la placa.

A distancia no se cambian la sección Seguridad (claves de administración) ni los parámetros de
radio de LoRa (región, preset, frecuencia, transmisión): un error deja el nodo fuera de la red y
hay que ir hasta él. Los demás cambios peligrosos piden confirmación como en la placa local, y
antes de escribir se guarda la sección leída en `<backups>/radio/remoto/`.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..models import node_id, node_num
from . import schema
from .service import BACKUPS_KEPT, DangerRequired, RadioError, RadioService, _to_dict

if TYPE_CHECKING:
    from google.protobuf.message import Message

    from ..connectors.serial import SerialConnector

ADMIN_TIMEOUT_S = 40.0
VERIFY_TIMEOUT_S = 15.0
# Una lectura reciente sirve de base para escribir; la clave de sesión del nodo dura 300 s.
READ_CACHE_S = 120.0
SESSION_FRESH_S = 150.0

REMOTE_READONLY = frozenset({"security"})
REMOTE_BLOCKED: dict[str, frozenset[str]] = {
    "lora": frozenset(
        {
            "region",
            "modem_preset",
            "use_preset",
            "bandwidth",
            "spread_factor",
            "coding_rate",
            "frequency_offset",
            "channel_num",
            "override_frequency",
            "tx_enabled",
            "serial_hal_only",
        }
    )
}
# Nombres del enum ModuleConfigType que no salen de sacar los guiones bajos.
MODULE_TYPES = {"external_notification": "EXTNOTIF_CONFIG", "canned_message": "CANNEDMSG_CONFIG"}

NOT_AUTHORIZED = (
    "El nodo no acepta administración de esta placa: falta cargar la clave pública de la placa "
    "en el nodo (Seguridad → Clave de administración)"
)
ROUTING_ERRORS: dict[str, tuple[int, str]] = {
    "NO_ROUTE": (504, "No hay ruta hacia el nodo"),
    "TIMEOUT": (504, "El pedido no llegó al nodo: no hubo acuse"),
    "MAX_RETRANSMIT": (504, "El pedido no llegó al nodo: se reintentó y no hubo acuse"),
    "GOT_NAK": (504, "El pedido no llegó al nodo"),
    "NO_RESPONSE": (502, "El nodo recibió el pedido pero no lo respondió"),
    "NO_CHANNEL": (409, "La placa no tiene un canal para llegar al nodo"),
    "TOO_LARGE": (422, "El pedido no entra en un paquete"),
    "BAD_REQUEST": (422, "El nodo rechazó el pedido"),
    "DUTY_CYCLE_LIMIT": (
        429,
        "La placa llegó al límite de tiempo de transmisión de la región: esperar unos minutos",
    ),
    "RATE_LIMIT_EXCEEDED": (429, "La placa frenó los envíos: esperar un momento"),
    "NOT_AUTHORIZED": (409, NOT_AUTHORIZED),
    "ADMIN_PUBLIC_KEY_UNAUTHORIZED": (409, NOT_AUTHORIZED),
    "ADMIN_BAD_SESSION_KEY": (
        409,
        "Venció la sesión de administración del nodo: volver a intentar",
    ),
    "PKI_FAILED": (502, "No se pudo cifrar el pedido para el nodo"),
    "PKI_UNKNOWN_PUBKEY": (
        409,
        "El nodo todavía no conoce la clave pública de esta placa: tiene que recibir su "
        "información (NodeInfo). Esperar a que la placa la anuncie o reiniciarla.",
    ),
    "PKI_SEND_FAIL_PUBLIC_KEY": (
        409,
        "Esta placa no tiene la clave pública del nodo: tiene que recibir su información "
        "(NodeInfo). Esperar a que el nodo la anuncie.",
    ),
}


class RemoteError(RadioError):
    """El pedido volvió con un error de ruteo (de la placa o del nodo)."""

    def __init__(self, reason: str) -> None:
        status, text = ROUTING_ERRORS.get(reason, (502, f"El pedido falló ({reason})"))
        super().__init__(status, text, code=f"routing_{reason.lower()}", reason=reason)
        self.reason = reason


class RemoteLimiter:
    """Cuida el aire: un pedido cada 2 s y 60 por hora por placa (cada uno son 1 a 3 paquetes)."""

    def __init__(self, gap_s: float = 2.0, per_hour: int = 60) -> None:
        self.gap_s, self.per_hour = gap_s, per_hour
        self.sent: deque[float] = deque()

    def check(self) -> float:
        now = time.time()
        while self.sent and now - self.sent[0] > 3600:
            self.sent.popleft()
        if self.sent and now - self.sent[-1] < self.gap_s:
            return self.gap_s - (now - self.sent[-1])
        if len(self.sent) >= self.per_hour:
            return 3600 - (now - self.sent[0])
        return 0.0

    def mark(self) -> None:
        self.sent.append(time.time())


def _path_value(msg: Any, path: str) -> Any:
    for part in path.split("."):
        msg = getattr(msg, part)
    return msg


def section_kind(section: str) -> str:
    from meshtastic.protobuf import localonly_pb2

    if section != "version":
        if section in localonly_pb2.LocalConfig.DESCRIPTOR.fields_by_name:
            return "config"
        if section in localonly_pb2.LocalModuleConfig.DESCRIPTOR.fields_by_name:
            return "module"
    raise RadioError(404, f"No existe la sección {section}")


def remote_writable(section: str) -> bool:
    return section in schema.WRITABLE and section not in REMOTE_READONLY


class RemoteAdmin:
    def __init__(self, radio: RadioService) -> None:
        self.radio = radio
        self._cache: dict[tuple[str, int, str], tuple[float, Any]] = {}
        self._session: dict[tuple[str, int], float] = {}
        self.limiters: dict[str, RemoteLimiter] = {}

    # ---------------------------------------------------------------- acceso

    def target(self, cid: str, node: str) -> tuple[SerialConnector, int]:
        conn = self.radio.connector(cid)
        try:
            num = node_num(node)
        except ValueError:
            raise RadioError(422, "id de nodo no válido") from None
        if conn.gateway_id and node_id(num) == conn.gateway_id.lower():
            raise RadioError(409, "Ese nodo es la placa conectada: usar la pestaña Configuración")
        return conn, num

    def limiter(self, cid: str) -> RemoteLimiter:
        return self.limiters.setdefault(cid, RemoteLimiter())

    async def _run(self, cid: str, fn: Any) -> Any:
        return await self.radio._run(cid, fn, lock_key=f"{cid}:remoto")

    # ---------------------------------------------------------------- pedidos (hilo)

    def _send(
        self, conn: SerialConnector, num: int, msg: Message, ack_ok: bool, timeout: float | None
    ) -> dict[str, Any]:
        """Un mensaje de administración al nodo; espera la respuesta (o el acuse si `ack_ok`)."""
        from meshtastic.protobuf import portnums_pb2

        timeout = timeout or ADMIN_TIMEOUT_S
        iface = conn.iface
        if iface is None:
            raise RadioError(409, "La placa se desconectó")
        key = iface._getOrCreateByNum(num).get("adminSessionPassKey")
        if key:
            msg.session_passkey = key
        else:
            msg.ClearField("session_passkey")
        done = threading.Event()
        box: list[dict[str, Any]] = []

        def on_response(packet: dict[str, Any]) -> None:
            box.append(packet)
            done.set()

        # Igual que la librería con `--dest`: canal "admin" si la placa lo tiene, y PKI.
        pkt = iface.sendData(
            msg,
            num,
            portNum=portnums_pb2.PortNum.ADMIN_APP,
            wantAck=True,
            wantResponse=True,
            onResponse=on_response,
            onResponseAckPermitted=ack_ok,
            channelIndex=iface.localNode._getAdminChannelIndex(),
            pkiEncrypted=True,
        )
        if not done.wait(timeout):
            with contextlib.suppress(Exception):
                iface.responseHandlers.pop(pkt.id, None)
            raise RadioError(
                504,
                f"El nodo no respondió en {int(timeout)} s. Con varios saltos puede tardar: volver "
                "a intentar. Si sigue igual, revisar que esté encendido y al alcance.",
                code="no_answer",
            )
        decoded = box[0].get("decoded") or {}
        if "admin" in decoded:
            # La librería ya guardó la clave de sesión que vino en la respuesta.
            self._session[(conn.id, num)] = time.monotonic()
        else:
            reason = (decoded.get("routing") or {}).get("errorReason", "NONE")
            if reason != "NONE":
                raise RemoteError(reason)
        return box[0]

    def _request(
        self,
        conn: SerialConnector,
        num: int,
        msg: Message,
        *,
        ack_ok: bool = False,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        try:
            return self._send(conn, num, msg, ack_ok, timeout)
        except RemoteError as e:
            if e.reason != "ADMIN_BAD_SESSION_KEY":
                raise
        self._renew(conn, num)  # el nodo se reinició o pasaron más de 300 s
        return self._send(conn, num, msg, ack_ok, timeout)

    def _renew(self, conn: SerialConnector, num: int) -> None:
        from meshtastic.protobuf import admin_pb2

        a = admin_pb2.AdminMessage
        self._send(conn, num, a(get_config_request=a.ConfigType.SESSIONKEY_CONFIG), False, None)

    def _ensure_session(self, conn: SerialConnector, num: int) -> None:
        """Los cambios llevan la clave de sesión del nodo: se renueva si está por vencer."""
        at = self._session.get((conn.id, num))
        if at is None or time.monotonic() - at > SESSION_FRESH_S:
            self._renew(conn, num)

    def _forget(self, conn: SerialConnector, num: int) -> None:
        """Después de un reinicio del nodo: ni la sesión ni lo leído siguen valiendo."""
        self._session.pop((conn.id, num), None)
        for k in [k for k in self._cache if k[:2] == (conn.id, num)]:
            del self._cache[k]

    @staticmethod
    def _admin(packet: dict[str, Any], expected: str) -> Any:
        admin = ((packet.get("decoded") or {}).get("admin") or {}).get("raw")
        if admin is None or admin.WhichOneof("payload_variant") != expected:
            raise RadioError(502, "El nodo respondió otra cosa de lo pedido")
        return getattr(admin, expected)

    def _read(
        self,
        conn: SerialConnector,
        num: int,
        section: str,
        timeout: float | None = None,
    ) -> Any:
        from meshtastic.protobuf import admin_pb2

        a = admin_pb2.AdminMessage
        msg = a()
        if section_kind(section) == "config":
            msg.get_config_request = a.ConfigType.Value(f"{section.upper()}_CONFIG")
            oneof = "get_config_response"
        else:
            name = MODULE_TYPES.get(section, section.replace("_", "").upper() + "_CONFIG")
            msg.get_module_config_request = a.ModuleConfigType.Value(name)
            oneof = "get_module_config_response"
        container = self._admin(self._request(conn, num, msg, timeout=timeout), oneof)
        if container.WhichOneof("payload_variant") != section:
            raise RadioError(502, f"El nodo no devolvió la sección {section} (¿firmware viejo?)")
        value = getattr(container, section)
        copy = type(value)()
        copy.CopyFrom(value)
        self._cache[(conn.id, num, section)] = (time.monotonic(), copy)
        return copy

    def _cached(self, conn: SerialConnector, num: int, section: str) -> Any:
        hit = self._cache.get((conn.id, num, section))
        if hit is None or time.monotonic() - hit[0] > READ_CACHE_S:
            return None
        return hit[1]

    # ---------------------------------------------------------------- copias

    def _backup_dir(self) -> Path:
        d = self.radio.backup_dir() / "remoto"
        d.mkdir(exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(d, 0o700)
        return d

    def _save_backup(self, conn: SerialConnector, num: int, section: str, msg: Any) -> str:
        node = node_id(num).lstrip("!")
        name = f"{node}-{time.strftime('%Y%m%d-%H%M%S')}-{section}.json"
        data = {
            "version": 1,
            "created": time.time(),
            "connector": conn.id,
            "board": conn.gateway_id,
            "node": node_id(num),
            "section": section,
            "kind": section_kind(section),
            "config": _to_dict(msg),
        }
        fd = os.open(self._backup_dir() / name, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        for old in sorted(self._backup_dir().glob(f"{node}-*.json"))[:-BACKUPS_KEPT]:
            with contextlib.suppress(OSError):
                old.unlink()
        return f"remoto/{name}"

    # ---------------------------------------------------------------- lectura

    @staticmethod
    def sections() -> list[dict[str, Any]]:
        from meshtastic.protobuf import localonly_pb2

        out = []
        for kind, root in (
            ("config", localonly_pb2.LocalConfig),
            ("module", localonly_pb2.LocalModuleConfig),
        ):
            for f in root.DESCRIPTOR.fields:
                if f.name != "version":
                    out.append(
                        {
                            "name": f.name,
                            "kind": kind,
                            "writable": remote_writable(f.name),
                            "danger": f.name in schema.DANGER_SECTIONS,
                        }
                    )
        return out

    async def info(self, cid: str, node: str) -> dict[str, Any]:
        """Lo que la placa sabe del nodo y su propia clave pública (no transmite)."""
        conn, num = self.target(cid, node)

        def read() -> dict[str, Any]:
            iface = conn.iface
            n = (iface.nodesByNum or {}).get(num) or {}
            user = n.get("user") or {}
            local = iface.localNode
            public_key = bytes(local.localConfig.security.public_key)
            return {
                "node": node_id(num),
                "known": bool(n),
                "long_name": user.get("longName"),
                "short_name": user.get("shortName"),
                "hw_model": user.get("hwModel"),
                "role": user.get("role", "CLIENT"),
                "has_pki": bool(user.get("publicKey")),
                "last_heard": n.get("lastHeard"),
                "hops": n.get("hopsAway"),
                "snr": n.get("snr"),
                "via_mqtt": bool(n.get("viaMqtt")),
                "board": conn.gateway_id,
                "board_public_key": base64.b64encode(public_key).decode() if public_key else None,
                "admin_channel": local._getAdminChannelIndex() > 0,
            }

        data: dict[str, Any] = await self.radio._run(cid, read)
        data["sections"] = self.sections()
        return data

    async def probe(self, cid: str, node: str) -> dict[str, Any]:
        """Prueba de conexión: pide los datos del equipo (exige la clave de administración)."""
        conn, num = self.target(cid, node)

        def do() -> dict[str, Any]:
            from meshtastic.protobuf import admin_pb2, config_pb2, mesh_pb2

            msg = admin_pb2.AdminMessage(get_device_metadata_request=True)
            started = time.monotonic()
            md = self._admin(self._request(conn, num, msg), "get_device_metadata_response")
            role = config_pb2.Config.DeviceConfig.Role
            return {
                "firmware": md.firmware_version,
                "role": role.Name(md.role) if md.role in role.values() else md.role,
                "hw_model": mesh_pb2.HardwareModel.Name(md.hw_model)
                if md.hw_model in mesh_pb2.HardwareModel.values()
                else md.hw_model,
                "has_wifi": md.hasWifi,
                "has_bluetooth": md.hasBluetooth,
                "seconds": round(time.monotonic() - started, 1),
            }

        result: dict[str, Any] = await self._run(cid, do)
        return result

    async def read_section(self, cid: str, node: str, section: str) -> dict[str, Any]:
        conn, num = self.target(cid, node)
        section_kind(section)

        def do() -> dict[str, Any]:
            return self._describe(section, self._read(conn, num, section))

        result: dict[str, Any] = await self._run(cid, do)
        return result

    @staticmethod
    def _describe(section: str, msg: Any) -> dict[str, Any]:
        fields = schema.describe_message(msg, section)
        blocked = REMOTE_BLOCKED.get(section, frozenset())
        for f in fields:
            if f["name"] in blocked:
                f["readonly"] = True
        return {
            "name": section,
            "kind": section_kind(section),
            "writable": remote_writable(section),
            "danger": section in schema.DANGER_SECTIONS,
            "fields": fields,
            "read_at": time.time(),
        }

    # ---------------------------------------------------------------- escritura

    async def write_section(
        self, cid: str, node: str, section: str, values: dict[str, Any], confirm_danger: bool
    ) -> dict[str, Any]:
        conn, num = self.target(cid, node)
        kind = section_kind(section)
        if not remote_writable(section):
            raise RadioError(422, f"La sección {section} no se cambia a distancia")
        blocked = sorted(set(values) & REMOTE_BLOCKED.get(section, frozenset()))
        if blocked:
            raise RadioError(
                422,
                "Los parámetros de radio no se cambian a distancia: si no coinciden con los de "
                "esta placa, el nodo queda fuera de la red y hay que ir hasta él.",
                fields=blocked,
            )

        def do() -> dict[str, Any]:
            from meshtastic.protobuf import admin_pb2

            live = self._cached(conn, num, section) or self._read(conn, num, section)
            copy = type(live)()
            copy.CopyFrom(live)
            changed, danger = schema.apply_values(copy, section, values)
            if not changed:
                return {"changed": [], "backup": None, "verified": True, "mismatch": []}
            if danger and not confirm_danger:
                raise DangerRequired(danger)
            backup = self._save_backup(conn, num, section, live)
            msg = admin_pb2.AdminMessage()
            target = msg.set_config if kind == "config" else msg.set_module_config
            getattr(target, section).CopyFrom(copy)
            self._ensure_session(conn, num)
            self._request(conn, num, msg, ack_ok=True)
            self._cache.pop((conn.id, num, section), None)
            # Se vuelve a leer para confirmar. Si el cambio reinicia el nodo, no contesta a
            # tiempo: queda sin verificar y se lee de nuevo en un minuto.
            verified: bool | None = None
            mismatch: list[str] = []
            fresh = None
            try:
                after = self._read(conn, num, section, timeout=VERIFY_TIMEOUT_S)
                mismatch = [p for p in changed if _path_value(after, p) != _path_value(copy, p)]
                verified = not mismatch
                fresh = self._describe(section, after)  # el panel la muestra sin volver a pedirla
            except RadioError:
                self._forget(conn, num)
            return {
                "changed": changed,
                "danger": danger,
                "backup": backup,
                "verified": verified,
                "mismatch": mismatch,
                "section": fresh,
            }

        result: dict[str, Any] = await self._run(cid, do)
        return result

    async def set_owner(
        self, cid: str, node: str, long_name: str, short_name: str
    ) -> dict[str, Any]:
        conn, num = self.target(cid, node)
        long_name, short_name = long_name.strip(), short_name.strip()
        if not long_name or len(long_name.encode()) > 39:
            raise RadioError(422, "Nombre largo: de 1 a 39 caracteres")
        if not short_name or len(short_name.encode()) > 4:
            raise RadioError(422, "Nombre corto: de 1 a 4 caracteres")

        def do() -> dict[str, Any]:
            from meshtastic.protobuf import admin_pb2

            # Se parte del usuario que tiene el nodo para no pisar licencia ni "no mensajeable".
            owner = self._admin(
                self._request(conn, num, admin_pb2.AdminMessage(get_owner_request=True)),
                "get_owner_response",
            )
            msg = admin_pb2.AdminMessage()
            msg.set_owner.CopyFrom(owner)
            msg.set_owner.long_name, msg.set_owner.short_name = long_name, short_name
            msg.set_owner.ClearField("public_key")
            self._request(conn, num, msg, ack_ok=True)
            user = conn.iface._getOrCreateByNum(num).setdefault("user", {})
            user["longName"], user["shortName"] = long_name, short_name
            return {"long_name": long_name, "short_name": short_name}

        result: dict[str, Any] = await self._run(cid, do)
        return result

    async def set_position(
        self, cid: str, node: str, lat: float, lon: float, alt: int
    ) -> dict[str, Any]:
        conn, num = self.target(cid, node)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
            raise RadioError(422, "Posición no válida")

        def do() -> dict[str, Any]:
            from meshtastic.protobuf import admin_pb2

            msg = admin_pb2.AdminMessage()
            msg.set_fixed_position.latitude_i = round(lat * 1e7)
            msg.set_fixed_position.longitude_i = round(lon * 1e7)
            msg.set_fixed_position.altitude = alt
            self._ensure_session(conn, num)
            self._request(conn, num, msg, ack_ok=True)
            self._cache.pop((conn.id, num, "position"), None)  # fixed_position pasó a true
            return {"fixed": True}

        result: dict[str, Any] = await self._run(cid, do)
        return result

    async def reboot(self, cid: str, node: str, seconds: int = 5) -> dict[str, Any]:
        conn, num = self.target(cid, node)

        def do() -> dict[str, Any]:
            from meshtastic.protobuf import admin_pb2

            self._ensure_session(conn, num)
            self._request(conn, num, admin_pb2.AdminMessage(reboot_seconds=seconds), ack_ok=True)
            self._forget(conn, num)
            return {"seconds": seconds}

        result: dict[str, Any] = await self._run(cid, do)
        return result


def get_remote(service: Any) -> RemoteAdmin:
    from .service import get_radio

    remote: RemoteAdmin | None = service.extensions.get("radio_remote")
    if remote is None:
        remote = RemoteAdmin(get_radio(service))
        service.extensions["radio_remote"] = remote
    return remote
