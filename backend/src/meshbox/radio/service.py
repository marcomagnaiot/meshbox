"""Operaciones del cliente Meshtastic del panel sobre una placa conectada por USB o TCP.

Todo lo que toca la librería corre en un hilo (`asyncio.to_thread`) y de a una operación por
placa. Antes de cada escritura se guarda una copia de la configuración (con claves, 0600) en
`<backups>/radio/`, que se puede restaurar desde el panel (ADR 0015).
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import os
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from . import schema

if TYPE_CHECKING:
    from ..app import Service
    from ..connectors.serial import SerialConnector

log = logging.getLogger(__name__)
T = TypeVar("T")
BACKUPS_KEPT = 30
# Cuánto espera una operación a que la placa termine la anterior antes de avisar.
LOCK_WAIT_S = 20.0
# Respuesta de un nodo por la malla (pedido de posición).
MESH_TIMEOUT_S = 45.0
BACKUP_RE = re.compile(r"^[A-Za-z0-9_.-]+\.json$")


class RadioError(Exception):
    def __init__(self, status: int, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.extra = extra


class DangerRequired(RadioError):
    def __init__(self, fields: list[str]) -> None:
        super().__init__(
            409,
            "Cambio peligroso: puede dejar la placa inalcanzable o fuera de su red. "
            "Hace falta confirmarlo.",
            code="danger_confirmation_required",
            fields=fields,
        )


def _to_dict(msg: Any) -> dict[str, Any]:
    from google.protobuf.json_format import MessageToDict

    if msg is None:
        return {}
    out: dict[str, Any] = MessageToDict(msg, preserving_proto_field_name=True)
    return out


def _plain(value: Any) -> Any:
    """Lo que guarda la librería, sin los protobuf que agrega (`raw` en posición y usuario)."""
    if isinstance(value, dict):
        return {
            str(k): _plain(v)
            for k, v in value.items()
            if isinstance(v, dict | list | str | int | float | bool) or v is None
        }
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


class RadioService:
    def __init__(self, service: Service) -> None:
        self.service = service
        self._locks: dict[str, asyncio.Lock] = {}
        self._since: dict[str, float] = {}

    # ---------------------------------------------------------------- acceso

    def connectors(self) -> list[SerialConnector]:
        from ..connectors.serial import SerialConnector

        return [
            c for c in self.service.connectors.connectors.values() if isinstance(c, SerialConnector)
        ]

    def connector(self, cid: str) -> SerialConnector:
        for conn in self.connectors():
            if conn.id == cid:
                if conn.iface is None or conn.status().state != "connected":
                    raise RadioError(409, f"La placa del conector {cid} no está conectada")
                return conn
        raise RadioError(404, "No hay una placa (USB o TCP) con ese conector")

    @staticmethod
    def mesh_key(cid: str) -> str:
        """Cola de lo que espera respuesta de otro nodo por la malla (pedido de posición,
        traceroute, administración remota): puede tardar y no debe trabar el estado ni la
        configuración de la placa, que van por la cola `<cid>`."""
        return f"{cid}:malla"

    async def _run(self, cid: str, fn: Callable[[], T], lock_key: str | None = None) -> T:
        key = lock_key or cid
        lock = self._locks.setdefault(key, asyncio.Lock())
        try:
            await asyncio.wait_for(lock.acquire(), LOCK_WAIT_S)
        except TimeoutError:
            since = self._since.get(key)
            busy = f" desde hace {int(time.monotonic() - since)} s" if since else ""
            raise RadioError(
                409,
                f"La placa está ocupada con otra operación{busy}: probar de nuevo en un momento",
                code="board_busy",
            ) from None
        self._since[key] = time.monotonic()
        try:

            def guarded() -> T:
                try:
                    return fn()
                except SystemExit as e:  # la librería llama a sys.exit ante algunos errores
                    raise RadioError(502, f"la placa rechazó la operación ({e})") from None

            try:
                return await asyncio.to_thread(guarded)
            except RadioError:
                raise
            except ValueError as e:
                raise RadioError(422, str(e)) from None
            except Exception as e:
                log.exception("operación sobre la placa %s falló", cid)
                raise RadioError(502, f"la placa no respondió: {type(e).__name__}: {e}") from None
        finally:
            self._since.pop(key, None)
            lock.release()

    # ---------------------------------------------------------------- lectura

    def boards(self) -> list[dict[str, Any]]:
        out = []
        for conn in self.connectors():
            st = conn.status()
            node = self._own_node(conn) if conn.iface is not None else {}
            user = node.get("user") or {}
            out.append(
                {
                    "id": conn.id,
                    "kind": conn.cfg.kind,
                    "via": conn.via,
                    "state": st.state,
                    "gateway_id": conn.gateway_id,
                    "long_name": user.get("longName"),
                    "short_name": user.get("shortName"),
                    "hw_model": user.get("hwModel"),
                }
            )
        return out

    @staticmethod
    def _own_node(conn: SerialConnector) -> dict[str, Any]:
        iface = conn.iface
        my = getattr(getattr(iface, "myInfo", None), "my_node_num", None)
        node: dict[str, Any] = (getattr(iface, "nodesByNum", None) or {}).get(my) or {}
        return node

    async def status(self, cid: str) -> dict[str, Any]:
        conn = self.connector(cid)

        def read() -> dict[str, Any]:
            iface = conn.iface
            node = iface.localNode
            lc, mc = node.localConfig, node.moduleConfig
            me = self._own_node(conn)
            user = me.get("user") or {}
            metadata = _to_dict(getattr(iface, "metadata", None))
            enum = schema._enum_name
            lora_f = lc.lora.DESCRIPTOR.fields_by_name
            dev_f = lc.device.DESCRIPTOR.fields_by_name
            preset_name = conn._read_channel_names(iface).get(0)
            return {
                "id": conn.id,
                "via": conn.via,
                "gateway_id": conn.gateway_id,
                "node": {
                    "id": conn.gateway_id,
                    "long_name": user.get("longName"),
                    "short_name": user.get("shortName"),
                    "hw_model": user.get("hwModel"),
                    "role": enum(dev_f["role"], lc.device.role),
                    "firmware": metadata.get("firmware_version"),
                    "region": enum(lora_f["region"], lc.lora.region),
                    "preset": enum(lora_f["modem_preset"], lc.lora.modem_preset),
                    "preset_name": preset_name,
                    "tx_power": lc.lora.tx_power,
                    "hop_limit": lc.lora.hop_limit,
                    "tx_enabled": lc.lora.tx_enabled,
                    "wifi_enabled": lc.network.wifi_enabled,
                    "bluetooth_enabled": lc.bluetooth.enabled,
                    "power_saving": lc.power.is_power_saving,
                    "fixed_position": lc.position.fixed_position,
                    "mqtt_enabled": mc.mqtt.enabled,
                    "map_reporting": mc.mqtt.map_reporting_enabled,
                    "has_wifi": metadata.get("hasWifi", metadata.get("has_wifi")),
                    "has_bluetooth": metadata.get("hasBluetooth", metadata.get("has_bluetooth")),
                    # La que se carga en los nodos a administrar a distancia (ADR 0017).
                    "public_key": base64.b64encode(bytes(lc.security.public_key)).decode() or None,
                },
                "metrics": _plain(me.get("deviceMetrics") or {}),
                "position": _plain(me.get("position") or {}),
                "nodes_in_db": len(iface.nodes or {}),
                "channels": schema.describe_channels(list(node.channels or []), preset_name or ""),
                "position_refreshed_at": conn.position_refreshed_at,
            }

        status = await self._run(cid, read)
        gw = self.service.state.gateways.get(conn.gateway_id or "")
        status["local_stats"] = gw.local_stats if gw is not None else None
        status["tx_enabled"] = self.service.cfg.tx.enabled
        return status

    async def nodes(self, cid: str) -> list[dict[str, Any]]:
        conn = self.connector(cid)

        def read() -> list[dict[str, Any]]:
            out = []
            for n in (conn.iface.nodesByNum or {}).values():
                user = n.get("user") or {}
                pos = n.get("position") or {}
                out.append(
                    {
                        "num": n.get("num"),
                        "id": user.get("id"),
                        "long_name": user.get("longName"),
                        "short_name": user.get("shortName"),
                        "hw_model": user.get("hwModel"),
                        "role": user.get("role", "CLIENT"),
                        "has_pki": bool(user.get("publicKey")),
                        "last_heard": n.get("lastHeard"),
                        "snr": n.get("snr"),
                        "hops": n.get("hopsAway"),
                        "via_mqtt": bool(n.get("viaMqtt")),
                        "favorite": bool(n.get("isFavorite")),
                        "channel": n.get("channel", 0),
                        "lat": pos.get("latitude"),
                        "lon": pos.get("longitude"),
                        "precision_bits": pos.get("precisionBits"),
                        "metrics": _plain(n.get("deviceMetrics") or {}),
                        "is_self": user.get("id") == conn.gateway_id,
                    }
                )
            out.sort(key=lambda x: -(x["last_heard"] or 0))
            return out

        return await self._run(cid, read)

    async def config(self, cid: str) -> dict[str, Any]:
        conn = self.connector(cid)

        def read() -> dict[str, Any]:
            node = conn.iface.localNode
            sections = []
            for kind, root in (("config", node.localConfig), ("module", node.moduleConfig)):
                for f in root.DESCRIPTOR.fields:
                    if f.name == "version":
                        continue
                    sections.append(
                        {
                            "name": f.name,
                            "kind": kind,
                            "writable": f.name in schema.WRITABLE,
                            "danger": f.name in schema.DANGER_SECTIONS,
                            "fields": schema.describe_message(getattr(root, f.name), f.name),
                        }
                    )
            return {"sections": sections}

        return await self._run(cid, read)

    # ---------------------------------------------------------------- copias de seguridad

    def backup_dir(self) -> Path:
        d = Path(self.service.cfg.paths.backups) / "radio"
        d.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(d, 0o700)
        return d

    def _snapshot(self, conn: SerialConnector, reason: str) -> dict[str, Any]:
        node = conn.iface.localNode
        me = self._own_node(conn)
        user = me.get("user") or {}
        return {
            "version": 1,
            "created": time.time(),
            "connector": conn.id,
            "node": conn.gateway_id,
            "reason": reason,
            "owner": {"long_name": user.get("longName"), "short_name": user.get("shortName")},
            "local_config": _to_dict(node.localConfig),
            "module_config": _to_dict(node.moduleConfig),
            "channels": [_to_dict(c) for c in (node.channels or [])],
        }

    def _save_backup(self, conn: SerialConnector, reason: str) -> str:
        """Copia completa (con claves) antes de un cambio. Devuelve el nombre del archivo."""
        data = self._snapshot(conn, reason)
        node = (conn.gateway_id or conn.id).lstrip("!")
        safe_reason = re.sub(r"[^a-z0-9]+", "-", reason.lower()).strip("-")[:30] or "copia"
        name = f"{node}-{time.strftime('%Y%m%d-%H%M%S')}-{safe_reason}.json"
        path = self.backup_dir() / name
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        self._prune(node)
        return name

    def _prune(self, node: str) -> None:
        files = sorted(self.backup_dir().glob(f"{node}-*.json"))
        for old in files[:-BACKUPS_KEPT]:
            with contextlib.suppress(OSError):
                old.unlink()

    def list_backups(self, cid: str) -> list[dict[str, Any]]:
        conn = next((c for c in self.connectors() if c.id == cid), None)
        if conn is None:
            raise RadioError(404, "No hay una placa (USB o TCP) con ese conector")
        node = (conn.gateway_id or cid).lstrip("!")
        out = []
        for p in sorted(self.backup_dir().glob(f"{node}-*.json"), reverse=True):
            st = p.stat()
            out.append({"name": p.name, "size": st.st_size, "created": st.st_mtime})
        return out

    def backup_path(self, name: str) -> Path:
        if not BACKUP_RE.match(name):
            raise RadioError(400, "nombre de copia no válido")
        path = self.backup_dir() / name
        if not path.is_file():
            raise RadioError(404, "No existe esa copia")
        return path

    async def create_backup(self, cid: str, reason: str = "manual") -> str:
        conn = self.connector(cid)
        return await self._run(cid, lambda: self._save_backup(conn, reason))

    async def restore(self, cid: str, name: str) -> dict[str, Any]:
        """Vuelve la placa a una copia: escribe solo las secciones y canales que difieren.

        Las secciones van en una transacción: la placa se reinicia una sola vez, al cerrarla.
        """
        conn = self.connector(cid)
        data = json.loads(self.backup_path(name).read_text(encoding="utf-8"))
        if data.get("node") != conn.gateway_id:
            raise RadioError(409, "La copia es de otra placa")

        def do() -> dict[str, Any]:
            from google.protobuf.json_format import ParseDict
            from meshtastic.protobuf import channel_pb2, localonly_pb2

            node = conn.iface.localNode
            before = self._save_backup(conn, "antes de restaurar")
            target_lc = ParseDict(data.get("local_config", {}), localonly_pb2.LocalConfig())
            target_mc = ParseDict(data.get("module_config", {}), localonly_pb2.LocalModuleConfig())
            pending = [
                (getattr(root, f.name), getattr(target, f.name), f.name)
                for root, target in ((node.localConfig, target_lc), (node.moduleConfig, target_mc))
                for f in root.DESCRIPTOR.fields
                if f.name != "version" and f.name in schema.WRITABLE
                and getattr(root, f.name).SerializeToString()
                != getattr(target, f.name).SerializeToString()
            ]  # fmt: skip
            sections = [name for _, _, name in pending]
            if pending:
                node.beginSettingsTransaction()
                for cur, new, name in pending:
                    cur.CopyFrom(new)
                    node.writeConfig(name)
                node.commitSettingsTransaction()
            channels: list[int] = []
            for i, chd in enumerate(data.get("channels", [])):
                target_ch = ParseDict(chd, channel_pb2.Channel())
                if i < len(node.channels) and (
                    node.channels[i].SerializeToString() != target_ch.SerializeToString()
                ):
                    node.channels[i].CopyFrom(target_ch)
                    node.writeChannel(i)
                    channels.append(i)
            owner = data.get("owner") or {}
            me = self._own_node(conn).get("user") or {}
            owner_changed = owner.get("long_name") and (
                owner.get("long_name") != me.get("longName")
                or owner.get("short_name") != me.get("shortName")
            )
            if owner_changed:
                node.setOwner(owner["long_name"], owner.get("short_name"))
            return {
                "sections": sections,
                "channels": channels,
                "owner": bool(owner_changed),
                "backup_before": before,
            }

        result = await self._run(cid, do)
        conn.reload_channel_names()
        return result

    # ---------------------------------------------------------------- escritura

    async def write_section(
        self, cid: str, section: str, values: dict[str, Any], confirm_danger: bool
    ) -> dict[str, Any]:
        conn = self.connector(cid)
        if section not in schema.WRITABLE:
            raise RadioError(422, f"La sección {section} no se puede escribir desde el panel")

        def do() -> dict[str, Any]:
            node = conn.iface.localNode
            root = node.localConfig
            if section not in {f.name for f in root.DESCRIPTOR.fields}:
                root = node.moduleConfig
            live = getattr(root, section)
            copy = type(live)()
            copy.CopyFrom(live)
            changed, danger = schema.apply_values(copy, section, values)
            if not changed:
                return {"changed": [], "backup": None}
            if danger and not confirm_danger:
                raise DangerRequired(danger)
            backup = self._save_backup(conn, f"antes de {section}")
            live.CopyFrom(copy)
            # Sin transacción: al cerrarla el firmware reinicia la placa siempre (medido en la
            # V3 con 2.7.26); suelta, reinicia solo si el campo lo necesita (región, preset…).
            node.writeConfig(section)
            return {"changed": changed, "danger": danger, "backup": backup}

        return await self._run(cid, do)

    async def write_channel(
        self, cid: str, index: int, values: dict[str, Any], confirm_danger: bool
    ) -> dict[str, Any]:
        conn = self.connector(cid)

        def do() -> dict[str, Any]:
            node = conn.iface.localNode
            if not 0 <= index < len(node.channels):
                raise RadioError(404, "No existe ese canal")
            live = node.channels[index]
            if live.role == 0:
                raise RadioError(409, "Ese canal está vacío: usar Agregar canal")
            copy = type(live)()
            copy.CopyFrom(live)
            changed, danger = schema.apply_channel(copy, values)
            if not changed:
                return {"changed": [], "backup": None}
            if danger and not confirm_danger:
                raise DangerRequired([f"canal {index}: {d}" for d in danger])
            backup = self._save_backup(conn, f"antes del canal {index}")
            live.CopyFrom(copy)
            node.writeChannel(index)
            return {"changed": changed, "danger": danger, "backup": backup}

        result = await self._run(cid, do)
        conn.reload_channel_names()
        return result

    async def add_channel(self, cid: str, values: dict[str, Any]) -> dict[str, Any]:
        conn = self.connector(cid)

        def do() -> dict[str, Any]:
            from meshtastic.protobuf import channel_pb2

            node = conn.iface.localNode
            free = next((c for c in node.channels if c.role == 0 and c.index > 0), None)
            if free is None:
                raise RadioError(409, "La placa ya tiene los 8 canales ocupados")
            if not str(values.get("name") or "").strip():
                raise RadioError(422, "El canal nuevo necesita un nombre")
            copy = channel_pb2.Channel()
            copy.CopyFrom(free)
            copy.role = channel_pb2.Channel.Role.SECONDARY
            schema.apply_channel(copy, {"psk": "random", **values})
            backup = self._save_backup(conn, "antes de agregar canal")
            free.CopyFrom(copy)
            node.writeChannel(free.index)
            return {"index": free.index, "backup": backup}

        result = await self._run(cid, do)
        conn.reload_channel_names()
        return result

    async def delete_channel(self, cid: str, index: int) -> dict[str, Any]:
        conn = self.connector(cid)

        def do() -> dict[str, Any]:
            node = conn.iface.localNode
            if not 0 < index < len(node.channels):
                raise RadioError(409, "El canal primario no se puede borrar")
            if node.channels[index].role == 0:
                raise RadioError(404, "Ese canal ya está vacío")
            backup = self._save_backup(conn, f"antes de borrar el canal {index}")
            node.deleteChannel(index)
            return {"deleted": index, "backup": backup}

        result = await self._run(cid, do)
        conn.reload_channel_names()
        return result

    async def set_owner(self, cid: str, long_name: str, short_name: str) -> dict[str, Any]:
        conn = self.connector(cid)
        long_name, short_name = long_name.strip(), short_name.strip()
        if not long_name or len(long_name.encode()) > 39:
            raise RadioError(422, "Nombre largo: de 1 a 39 caracteres")
        if not short_name or len(short_name.encode()) > 4:
            raise RadioError(422, "Nombre corto: de 1 a 4 caracteres")

        def do() -> dict[str, Any]:
            backup = self._save_backup(conn, "antes del nombre")
            conn.iface.localNode.setOwner(long_name, short_name)
            return {"long_name": long_name, "short_name": short_name, "backup": backup}

        return await self._run(cid, do)

    # ---------------------------------------------------------------- acciones

    async def set_position(self, cid: str, lat: float, lon: float, alt: int) -> dict[str, Any]:
        conn = self.connector(cid)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
            raise RadioError(422, "Posición no válida")

        def do() -> dict[str, Any]:
            node = conn.iface.localNode
            node.setFixedPosition(lat, lon, alt)
            # La librería no actualiza su copia de la configuración: sin esto, guardar después
            # la sección Posición le mandaría fixed_position = false a la placa.
            node.localConfig.position.fixed_position = True
            return {"fixed": True}

        result = await self._run(cid, do)
        conn.position_refreshed_at = time.time()
        return result

    async def refresh_position(self, cid: str) -> dict[str, Any]:
        conn = self.connector(cid)

        def do() -> dict[str, Any]:
            pos = self._own_node(conn).get("position") or {}
            lat, lon = pos.get("latitude"), pos.get("longitude")
            if not lat or not lon:
                raise RadioError(409, "La placa no tiene una posición guardada para reponer")
            conn.iface.localNode.setFixedPosition(lat, lon, int(pos.get("altitude") or 0))
            return {"lat": lat, "lon": lon}

        result = await self._run(cid, do)
        conn.position_refreshed_at = time.time()
        return result

    async def remove_fixed_position(self, cid: str) -> dict[str, Any]:
        conn = self.connector(cid)

        def do() -> dict[str, Any]:
            node = conn.iface.localNode
            node.removeFixedPosition()
            node.localConfig.position.fixed_position = False  # ídem: la copia local
            return {}

        return await self._run(cid, do)

    async def reboot(self, cid: str) -> None:
        conn = self.connector(cid)
        await self._run(cid, lambda: conn.iface.localNode.reboot(5))

    async def shutdown(self, cid: str) -> None:
        conn = self.connector(cid)
        await self._run(cid, lambda: conn.iface.localNode.shutdown(5))

    async def request_position(self, cid: str, dest: str, channel_index: int) -> dict[str, Any]:
        """Pide su posición a un nodo (transmite) y espera la respuesta hasta 45 s.

        Sin `sendPosition` de la librería: espera 300 s y, si el nodo contesta NO_RESPONSE,
        llama a `sys.exit` en el hilo que lee la placa.
        """
        conn = self.connector(cid)

        def do() -> dict[str, Any]:
            from meshtastic.protobuf import mesh_pb2, portnums_pb2

            done = threading.Event()
            box: list[dict[str, Any]] = []

            def on_response(packet: dict[str, Any]) -> None:
                box.append(packet)
                done.set()

            pkt = conn.iface.sendData(
                mesh_pb2.Position(),
                dest,
                portNum=portnums_pb2.PortNum.POSITION_APP,
                wantResponse=True,
                onResponse=on_response,
                channelIndex=channel_index,
            )
            if not done.wait(MESH_TIMEOUT_S):
                with contextlib.suppress(Exception):
                    conn.iface.responseHandlers.pop(pkt.id, None)
                return {"answered": False, "detail": f"sin respuesta en {int(MESH_TIMEOUT_S)} s"}
            decoded = box[0].get("decoded") or {}
            if decoded.get("portnum") == "ROUTING_APP":
                reason = (decoded.get("routing") or {}).get("errorReason", "NONE")
                return {"answered": False, "detail": reason}
            return {"answered": True}

        return await self._run(cid, do, lock_key=self.mesh_key(cid))

    async def traceroute(self, cid: str, dest: str, hop_limit: int, channel_index: int) -> None:
        """Manda el traceroute y vuelve: la respuesta llega como TRACEROUTE_APP (Paquetes y mapa).

        Sin `sendTraceRoute` de la librería, que espera 300 s por salto con la placa tomada.
        """
        conn = self.connector(cid)

        def do() -> None:
            from meshtastic.protobuf import mesh_pb2, portnums_pb2

            conn.iface.sendData(
                mesh_pb2.RouteDiscovery(),
                dest,
                portNum=portnums_pb2.PortNum.TRACEROUTE_APP,
                wantResponse=True,
                channelIndex=channel_index,
                hopLimit=hop_limit,
            )

        await self._run(cid, do, lock_key=self.mesh_key(cid))


def get_radio(service: Any) -> RadioService:
    radio: RadioService | None = service.extensions.get("radio")
    if radio is None:
        radio = RadioService(service)
        service.extensions["radio"] = radio
    return radio
