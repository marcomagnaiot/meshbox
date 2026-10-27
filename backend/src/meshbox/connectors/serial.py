"""Conector USB serie (sección 9.3).

`meshtastic.serial_interface.SerialInterface` corre en su propio hilo. Los callbacks de
pubsub pasan los paquetes al loop asyncio con `call_soon_threadsafe`; nunca se toca la base
ni el bus desde el hilo de la librería. La librería se importa solo si hay un conector USB
(ahorra memoria en la Pi).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..config import SerialConnectorCfg, TcpConnectorCfg
from ..models import RawPacket, node_id
from ..radio.messages import conv_key
from .base import BaseConnector, StatusCallback

log = logging.getLogger(__name__)

SeedCallback = Callable[[str, list[dict[str, Any]], float], None]
# Mensajes del cliente del panel: ("text", mensaje) o ("ack", acuse); se llama en el loop.
MessageCallback = Callable[[str, dict[str, Any]], None]
# Arranques de placa en los que ya se repuso la posición fija: (gateway, minuto del arranque/5).
_POSITION_REFRESHED: set[tuple[str | None, int | None]] = set()

PRESET_NAMES = {
    "LONG_FAST": "LongFast",
    "LONG_SLOW": "LongSlow",
    "VERY_LONG_SLOW": "VLongSlow",
    "MEDIUM_SLOW": "MediumSlow",
    "MEDIUM_FAST": "MediumFast",
    "SHORT_SLOW": "ShortSlow",
    "SHORT_FAST": "ShortFast",
    "LONG_MODERATE": "LongMod",
    "SHORT_TURBO": "ShortTurbo",
    "LONG_TURBO": "LongTurbo",
}
SECRET_KEYS = ("psk", "password", "private_key", "admin_key", "wifi_psk", "session_passkey")


def preset_display_name(preset: str) -> str:
    if preset in PRESET_NAMES:
        return PRESET_NAMES[preset]
    return "".join(p.capitalize() for p in preset.split("_"))


def mask_secrets(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if any(s in lk for s in SECRET_KEYS):
                out[k] = "********" if v else v
            else:
                out[k] = mask_secrets(v)
        return out
    if isinstance(obj, list):
        return [mask_secrets(x) for x in obj]
    return obj


def list_serial_ports() -> list[dict[str, Any]]:
    from serial.tools import list_ports

    by_id: dict[str, str] = {}
    by_id_dir = Path("/dev/serial/by-id")
    if by_id_dir.exists():
        for link in by_id_dir.iterdir():
            with contextlib.suppress(OSError):
                by_id[str(link.resolve())] = str(link)
    ports = []
    for p in list_ports.comports():
        ports.append(
            {
                "device": p.device,
                "stable_path": by_id.get(p.device),
                "description": p.description,
                "hwid": p.hwid,
                "vid": p.vid,
                "pid": p.pid,
                "serial_number": p.serial_number,
                "manufacturer": p.manufacturer,
            }
        )
    return ports


class SerialConnector(BaseConnector):
    kind = "serial"

    def __init__(
        self,
        cfg: SerialConnectorCfg | TcpConnectorCfg,
        on_status: StatusCallback | None = None,
        on_seed: SeedCallback | None = None,
        on_message: MessageCallback | None = None,
    ) -> None:
        super().__init__(cfg.id, on_status)
        self.cfg = cfg
        self._on_seed = on_seed
        self._on_message = on_message
        self._iface: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lost: asyncio.Event | None = None
        self._channel_names: dict[int, str] = {}
        self._pending: set[asyncio.Future[None]] = set()
        self.gateway_id: str | None = None
        self.position_refreshed_at: float | None = None
        # pypubsub guarda referencias débiles: hay que retener los métodos ligados.
        self._cb_receive = self._on_receive_thread
        self._cb_lost = self._on_lost_thread
        if isinstance(cfg, TcpConnectorCfg):
            self._set_detail(host=cfg.host, port=cfg.port)
        else:
            self._set_detail(port=cfg.port)

    # ---------------------------------------------------------------- conexión

    def _open(self) -> Any:
        try:
            if isinstance(self.cfg, TcpConnectorCfg):
                from meshtastic.tcp_interface import TCPInterface

                return TCPInterface(
                    hostname=self.cfg.host, portNumber=self.cfg.port, connectNow=True
                )
            from meshtastic.serial_interface import SerialInterface

            return SerialInterface(devPath=self.cfg.port, noProto=False, connectNow=True)
        except SystemExit as e:  # la librería llama a sys.exit si no encuentra el dispositivo
            raise ConnectionError(f"la librería meshtastic abortó: {e}") from None

    async def _run_once(self) -> None:
        if isinstance(self.cfg, TcpConnectorCfg):
            if not self.cfg.host:
                raise ValueError("host del nodo no configurado")
        elif not self.cfg.port:
            raise ValueError("puerto serie no configurado")
        from pubsub import pub

        self._loop = asyncio.get_running_loop()
        self._lost = asyncio.Event()
        iface = await asyncio.to_thread(self._open)
        self._iface = iface
        pub.subscribe(self._cb_receive, "meshtastic.receive")
        pub.subscribe(self._cb_lost, "meshtastic.connection.lost")
        try:
            my = iface.myInfo
            self.gateway_id = node_id(my.my_node_num) if my is not None else None
            self._channel_names = self._read_channel_names(iface)
            self._set_state("connected")
            self._set_detail(
                gateway_id=self.gateway_id, channels=self._channel_names, connected_at=time.time()
            )
            log.info("conector %s conectado por %s (%s)", self.id, self.via, self.gateway_id)
            with contextlib.suppress(Exception):
                if await asyncio.to_thread(self._refresh_fixed_position, iface):
                    self.position_refreshed_at = time.time()
                    self._set_detail(position_refreshed_at=self.position_refreshed_at)
            if self._on_seed is not None and self.gateway_id:
                nodes = []
                for n in (iface.nodes or {}).values():
                    item = dict(n)
                    # Canal en que el nodo oyó a cada uno: la siembra solo publica los públicos.
                    item["_channel_name"] = self._channel_names.get(int(item.get("channel") or 0))
                    nodes.append(item)
                self._on_seed(self.gateway_id, nodes, time.time())
            await self._lost.wait()
            raise ConnectionError(f"conexión {self.via} perdida")
        finally:
            with contextlib.suppress(Exception):
                pub.unsubscribe(self._cb_receive, "meshtastic.receive")
                pub.unsubscribe(self._cb_lost, "meshtastic.connection.lost")
            await self._cleanup()

    async def _cleanup(self) -> None:
        iface, self._iface = self._iface, None
        if iface is not None:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(iface.close)

    @staticmethod
    def _read_channel_names(iface: Any) -> dict[int, str]:
        names: dict[int, str] = {}
        try:
            from meshtastic.protobuf import config_pb2

            lora = iface.localNode.localConfig.lora
            preset = config_pb2.Config.LoRaConfig.ModemPreset.Name(lora.modem_preset)
            default_name = preset_display_name(preset) if lora.use_preset else "Custom"
            for ch in iface.localNode.channels or []:
                if ch.role == 0:  # DISABLED
                    continue
                names[ch.index] = ch.settings.name or default_name
        except Exception:
            log.exception("no se pudieron leer los canales del nodo")
        return names

    # ---------------------------------------------------------------- callbacks (hilo)

    def _on_receive_thread(self, packet: dict[str, Any], interface: Any) -> None:
        if interface is not self._iface or self._loop is None:
            return
        mp = packet.get("raw")
        if mp is None:
            return
        with contextlib.suppress(Exception):
            self._track_message(packet)
        raw = RawPacket(
            source="tcp" if isinstance(self.cfg, TcpConnectorCfg) else "serial",
            connector_id=self.id,
            gateway_id=self.gateway_id,
            channel_id=self._channel_names.get(mp.channel) if mp.HasField("decoded") else None,
            rx_time=time.time(),
            packet=mp,
        )
        self._loop.call_soon_threadsafe(self._schedule_delivery, raw)

    # ---------------------------------------------------------------- mensajes (cliente del panel)

    def _message(self, **fields: Any) -> dict[str, Any]:
        """Fila del historial (ADR 0016) con los datos que no cambian."""
        item: dict[str, Any] = {
            "board": self.gateway_id,
            "connector_id": self.id,
            "snr": None,
            "rssi": None,
            "hops": None,
            "reply_id": None,
            "emoji": False,
            "status": None,
            **fields,
        }
        item["conv"] = conv_key(
            item["direction"], item["dm"], item["from_id"], item["to_id"], item["channel_index"]
        )
        return item

    def _emit_message(self, kind: str, payload: dict[str, Any]) -> None:
        if self._on_message is not None and payload.get("board"):
            try:
                self._on_message(kind, payload)
            except Exception:
                log.exception("no se pudo guardar un mensaje de %s", self.id)

    def _track_message(self, packet: dict[str, Any]) -> None:
        """Hilo de la librería: textos y acuses van al historial por el loop."""
        decoded = packet.get("decoded") or {}
        port = decoded.get("portnum")
        if port == "TEXT_MESSAGE_APP" and decoded.get("text") is not None:
            frm = packet.get("fromId") or node_id(int(packet.get("from") or 0))
            to = packet.get("toId") or node_id(int(packet.get("to") or 0))
            hop_start, hop_limit = packet.get("hopStart"), packet.get("hopLimit")
            rx_time = packet.get("rxTime")
            # Sin hora (placa sin GPS ni NTP) vale la de llegada a meshbox.
            ts = (
                float(rx_time)
                if isinstance(rx_time, int | float) and rx_time > 1e9
                else time.time()
            )
            payload = self._message(
                packet_id=int(packet.get("id") or 0),
                ts=ts,
                direction="out" if frm == self.gateway_id else "in",
                from_id=frm,
                to_id=to,
                dm=to not in ("^all", "!ffffffff"),
                channel_index=int(packet.get("channel") or 0),
                channel=self._channel_names.get(int(packet.get("channel") or 0)),
                text=str(decoded["text"])[:500],
                snr=packet.get("rxSnr"),
                rssi=packet.get("rxRssi"),
                hops=hop_start - hop_limit
                if isinstance(hop_start, int) and isinstance(hop_limit, int)
                else None,
                reply_id=decoded.get("replyId"),
                emoji=bool(decoded.get("emoji")),
            )
            kind = "text"
        elif port == "ROUTING_APP" and decoded.get("requestId"):
            payload = {
                "board": self.gateway_id,
                "packet_id": int(decoded["requestId"]),
                "from_id": packet.get("fromId"),
                "reason": (decoded.get("routing") or {}).get("errorReason", "NONE"),
            }
            kind = "ack"
        else:
            return
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._emit_message, kind, payload)

    async def send_message(self, text: str, channel_index: int, dest: str | None = None) -> int:
        """Texto al canal o directo a un nodo, pidiendo confirmación (queda en el historial)."""
        iface = self._require_iface()
        pkt = await asyncio.to_thread(
            iface.sendText,
            text,
            destinationId=dest or "^all",
            wantAck=True,
            channelIndex=channel_index,
        )
        packet_id = int(pkt.id) if pkt is not None else 0
        self._emit_message(
            "text",
            self._message(
                packet_id=packet_id,
                ts=time.time(),
                direction="out",
                from_id=self.gateway_id,
                to_id=dest or "^all",
                dm=bool(dest),
                channel_index=channel_index,
                channel=self._channel_names.get(channel_index),
                text=text,
                status="enviado",
            ),
        )
        return packet_id

    # ---------------------------------------------------------------- posición fija (ADR 0011)

    def _refresh_fixed_position(self, iface: Any) -> bool:
        """Vuelve a fijar la posición guardada, una vez por arranque de la placa.

        Sin GPS, el firmware no repone la posición fija en memoria al arrancar y no manda el
        informe de mapa (verificado con un Heltec real, ADR 0011).
        """
        lc = iface.localNode.localConfig
        if not lc.position.fixed_position:
            return False
        my = getattr(iface.myInfo, "my_node_num", None)
        me = (getattr(iface, "nodesByNum", None) or {}).get(my) or {}
        pos = me.get("position") or {}
        lat, lon = pos.get("latitude"), pos.get("longitude")
        if not lat or not lon:
            return False
        uptime = (me.get("deviceMetrics") or {}).get("uptimeSeconds")
        boot = round((time.time() - float(uptime)) / 300) if uptime else None
        key = (self.gateway_id, boot)
        if boot is not None and key in _POSITION_REFRESHED:
            return False
        iface.localNode.setFixedPosition(lat, lon, int(pos.get("altitude") or 0))
        _POSITION_REFRESHED.add(key)
        log.info("posición fija repuesta en %s (arranque de la placa)", self.gateway_id)
        return True

    def _schedule_delivery(self, raw: RawPacket) -> None:
        task = asyncio.ensure_future(self._deliver(raw))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    def _on_lost_thread(self, interface: Any) -> None:
        if interface is self._iface and self._loop is not None and self._lost is not None:
            self._loop.call_soon_threadsafe(self._lost.set)

    # ---------------------------------------------------------------- funciones USB (18.4, 22)

    def _require_iface(self) -> Any:
        if self._iface is None:
            raise RuntimeError(f"el conector {self.via} no está conectado")
        return self._iface

    @property
    def iface(self) -> Any:
        """Interfaz de la librería (None si no está conectado). Usarla desde un hilo."""
        return self._iface

    def reload_channel_names(self) -> None:
        if self._iface is not None:
            self._channel_names = self._read_channel_names(self._iface)
            self._set_detail(channels=self._channel_names)

    async def node_info(self) -> dict[str, Any]:
        iface = self._require_iface()

        def read() -> dict[str, Any]:
            from google.protobuf.json_format import MessageToDict

            def to_dict(m: Any) -> dict[str, Any]:
                if m is None:
                    return {}
                out: dict[str, Any] = MessageToDict(m, preserving_proto_field_name=True)
                return out

            node = iface.localNode
            masked: dict[str, Any] = mask_secrets(
                {
                    "gateway_id": self.gateway_id,
                    "my_info": to_dict(iface.myInfo),
                    "metadata": to_dict(getattr(iface, "metadata", None)),
                    "local_config": to_dict(node.localConfig),
                    "module_config": to_dict(node.moduleConfig),
                    "channels": [to_dict(c) for c in (node.channels or [])],
                    "nodes_in_db": len(iface.nodes or {}),
                }
            )
            return masked

        return await asyncio.to_thread(read)

    async def reboot_node(self, seconds: int = 10) -> None:
        iface = self._require_iface()
        await asyncio.to_thread(iface.localNode.reboot, seconds)

    async def send_text(self, text: str, channel_index: int) -> int:
        return await self.send_message(text, channel_index)

    async def send_traceroute(self, dest: int, hop_limit: int, channel_index: int) -> None:
        iface = self._require_iface()
        await asyncio.to_thread(iface.sendTraceRoute, dest, hop_limit, channel_index)

    @property
    def channel_names(self) -> dict[int, str]:
        return dict(self._channel_names)

    @property
    def via(self) -> str:
        return "TCP" if isinstance(self.cfg, TcpConnectorCfg) else "USB"


class TcpConnector(SerialConnector):
    """Misma API que USB pero por la red (TCPInterface, puerto 4403). La API del nodo atiende
    un cliente a la vez: mientras está conectado, la CLI o el cliente web no pueden usarla."""

    kind = "tcp"
