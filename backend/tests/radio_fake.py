"""Placa Meshtastic simulada con la interfaz de la librería que usa el cliente del panel."""

from __future__ import annotations

import asyncio
import itertools
import time
from types import SimpleNamespace
from typing import Any

from google.protobuf.json_format import MessageToDict
from meshtastic.protobuf import (
    admin_pb2,
    channel_pb2,
    config_pb2,
    localonly_pb2,
    mesh_pb2,
    portnums_pb2,
)

from meshbox.config import SerialConnectorCfg
from meshbox.connectors.serial import SerialConnector

MY_NUM = 0x0A0B0C0D
MY_ID = "!0a0b0c0d"
MY_PUBLIC_KEY = bytes(range(100, 132))
REMOTE_NUM = 0x11112222
REMOTE_ID = "!11112222"
_ids = itertools.count(1000)
Admin = admin_pb2.AdminMessage
# Algunos módulos del enum ModuleConfigType (escritos a mano para no repetir la regla del código).
MODULE_FIELDS = {
    "MQTT_CONFIG": "mqtt",
    "TELEMETRY_CONFIG": "telemetry",
    "EXTNOTIF_CONFIG": "external_notification",
    "NEIGHBORINFO_CONFIG": "neighbor_info",
}


class FakeRemote:
    """Nodo remoto que acepta administración de la placa simulada (ADR 0017)."""

    def __init__(self) -> None:
        lc = localonly_pb2.LocalConfig()
        lc.device.role = config_pb2.Config.DeviceConfig.Role.ROUTER
        lc.lora.region = config_pb2.Config.LoRaConfig.RegionCode.ANZ
        lc.lora.modem_preset = config_pb2.Config.LoRaConfig.ModemPreset.MEDIUM_FAST
        lc.lora.use_preset = True
        lc.lora.tx_power = 27
        lc.lora.hop_limit = 3
        lc.lora.tx_enabled = True
        lc.display.screen_on_secs = 600
        lc.security.public_key = bytes(range(32))
        lc.security.private_key = bytes(range(32, 64))
        lc.security.admin_key.append(MY_PUBLIC_KEY)
        self.config = lc
        mc = localonly_pb2.LocalModuleConfig()
        mc.telemetry.device_update_interval = 1800
        mc.mqtt.password = "clave-remota"
        self.modules = mc
        self.owner = mesh_pb2.User(id=REMOTE_ID, long_name="Repetidor del cerro",
                                   short_name="RCER", is_unmessagable=True)  # fmt: skip
        self.passkey = b"\x01\x02\x03\x04"
        self.authorized = True
        self.answers = True  # False: el nodo no contesta (fuera de alcance)
        self.reboot_on_write = False  # el cambio lo reinicia: no contesta la verificación
        self.bad_session_once = False
        self.delay_s = 0.0  # lo que tarda en contestar (para las capturas del manual)
        self.position: tuple[int, int, int] | None = None
        self.reboots: list[int] = []
        self.received: list[Any] = []

    def handle(self, msg: Any) -> Any:
        """Respuesta: AdminMessage, nombre de error de ruteo, "ack" o None (silencio)."""
        self.received.append(msg)
        time.sleep(self.delay_s)
        if not self.answers:
            return None
        if not self.authorized:
            return "ADMIN_PUBLIC_KEY_UNAUTHORIZED"
        which = msg.WhichOneof("payload_variant")
        out = Admin(session_passkey=self.passkey)
        if which == "get_config_request":
            kind = Admin.ConfigType.Name(msg.get_config_request)
            if kind == "SESSIONKEY_CONFIG":
                out.get_config_response.sessionkey.SetInParent()
            else:
                name = kind.removesuffix("_CONFIG").lower()
                getattr(out.get_config_response, name).CopyFrom(getattr(self.config, name))
            return out
        if which == "get_module_config_request":
            name = MODULE_FIELDS[Admin.ModuleConfigType.Name(msg.get_module_config_request)]
            getattr(out.get_module_config_response, name).CopyFrom(getattr(self.modules, name))
            return out
        if which == "get_device_metadata_request":
            md = out.get_device_metadata_response
            md.firmware_version = "2.7.15.test"
            md.role = config_pb2.Config.DeviceConfig.Role.ROUTER
            md.hw_model = mesh_pb2.HardwareModel.TRACKER_T1000_E
            return out
        if which == "get_owner_request":
            out.get_owner_response.CopyFrom(self.owner)
            return out
        if msg.session_passkey != self.passkey or self.bad_session_once:
            self.bad_session_once = False
            return "ADMIN_BAD_SESSION_KEY"
        if which in ("set_config", "set_module_config"):
            inner = getattr(msg, which)
            name = inner.WhichOneof("payload_variant")
            root = self.config if which == "set_config" else self.modules
            getattr(root, name).CopyFrom(getattr(inner, name))
            if self.reboot_on_write:
                self.answers = False
        elif which == "set_owner":
            self.owner.CopyFrom(msg.set_owner)
        elif which == "set_fixed_position":
            p = msg.set_fixed_position
            self.position = (p.latitude_i, p.longitude_i, p.altitude)
            self.config.position.fixed_position = True
        elif which == "reboot_seconds":
            self.reboots.append(msg.reboot_seconds)
        return "ack"


class FakeNode:
    def __init__(self, iface: FakeIface) -> None:
        self.iface = iface
        self.calls: list[tuple[str, Any]] = []
        lc = localonly_pb2.LocalConfig()
        lc.device.role = config_pb2.Config.DeviceConfig.Role.CLIENT_BASE
        lc.lora.region = config_pb2.Config.LoRaConfig.RegionCode.ANZ
        lc.lora.modem_preset = config_pb2.Config.LoRaConfig.ModemPreset.MEDIUM_FAST
        lc.lora.use_preset = True
        lc.lora.tx_power = 30
        lc.lora.hop_limit = 7
        lc.lora.tx_enabled = True
        lc.network.wifi_enabled = True
        lc.network.wifi_ssid = "Casa"
        lc.network.wifi_psk = "clave-wifi"
        lc.position.fixed_position = True
        lc.display.screen_on_secs = 60
        lc.security.public_key = MY_PUBLIC_KEY
        self.localConfig = lc
        mc = localonly_pb2.LocalModuleConfig()
        mc.mqtt.enabled = True
        mc.mqtt.password = "secreta"
        mc.mqtt.map_reporting_enabled = True
        mc.telemetry.device_update_interval = 3600
        self.moduleConfig = mc
        self.channels: list[Any] = []
        for i in range(8):
            ch = channel_pb2.Channel(index=i)
            if i == 0:
                ch.role = channel_pb2.Channel.Role.PRIMARY
                ch.settings.psk = b"\x01"
                ch.settings.uplink_enabled = True
                ch.settings.module_settings.position_precision = 13
            elif i == 1:
                ch.role = channel_pb2.Channel.Role.SECONDARY
                ch.settings.name = "Familia"
                ch.settings.psk = bytes(range(32))
            self.channels.append(ch)

    def _getAdminChannelIndex(self) -> int:
        return 0

    def beginSettingsTransaction(self) -> None:
        self.calls.append(("begin", None))

    def commitSettingsTransaction(self) -> None:
        self.calls.append(("commit", None))

    def writeConfig(self, name: str) -> None:
        self.calls.append(("writeConfig", name))

    def writeChannel(self, index: int, adminIndex: int = 0) -> None:
        self.calls.append(("writeChannel", index))

    def deleteChannel(self, index: int) -> None:
        self.calls.append(("deleteChannel", index))
        self.channels.pop(index)
        self.channels.append(channel_pb2.Channel())
        for i, ch in enumerate(self.channels):
            ch.index = i

    def setOwner(self, long_name: str, short_name: str | None = None) -> None:
        self.calls.append(("setOwner", (long_name, short_name)))
        user = self.iface.nodesByNum[MY_NUM]["user"]
        user["longName"], user["shortName"] = long_name, short_name

    def setFixedPosition(self, lat: float, lon: float, alt: int) -> None:
        self.calls.append(("setFixedPosition", (lat, lon, alt)))

    def removeFixedPosition(self) -> None:
        self.calls.append(("removeFixedPosition", None))

    def reboot(self, secs: int = 10) -> None:
        self.calls.append(("reboot", secs))

    def shutdown(self, secs: int = 10) -> None:
        self.calls.append(("shutdown", secs))


class FakeIface:
    def __init__(self) -> None:
        self.myInfo = SimpleNamespace(my_node_num=MY_NUM)
        self.metadata = mesh_pb2.DeviceMetadata(firmware_version="2.7.26.test")
        self.nodesByNum: dict[int, dict[str, Any]] = {
            MY_NUM: {
                "num": MY_NUM,
                "user": {"id": MY_ID, "longName": "Placa de prueba", "shortName": "PRB",
                         "hwModel": "HELTEC_V3"},
                # La librería deja el protobuf en `raw` (no se puede pasar a JSON).
                "position": {"latitude": -40.8, "longitude": -63.0, "altitude": 8,
                             "raw": mesh_pb2.Position(latitude_i=-408000000)},
                "deviceMetrics": {"batteryLevel": 80, "voltage": 4.0, "uptimeSeconds": 120},
                "lastHeard": 1792500000,
            },
            0x11112222: {
                "num": 0x11112222,
                "user": {"id": REMOTE_ID, "longName": "Repetidor del cerro", "shortName": "RCER",
                         "hwModel": "TRACKER_T1000_E", "role": "ROUTER",
                         "publicKey": "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="},
                "snr": 5.5,
                "hopsAway": 1,
                "lastHeard": 1792500100,
            },
        }  # fmt: skip
        self.nodes = {n["user"]["id"]: n for n in self.nodesByNum.values()}
        self.localNode = FakeNode(self)
        self.remote = FakeRemote()
        self.responseHandlers: dict[int, Any] = {}
        self.sent: list[dict[str, Any]] = []

    def _getOrCreateByNum(self, num: int) -> dict[str, Any]:
        return self.nodesByNum.setdefault(num, {"num": num, "user": {"id": f"!{num:08x}"}})

    def sendData(self, data: Any, destinationId: Any, portNum: int = 0, wantAck: bool = False,
                 wantResponse: bool = False, onResponse: Any = None,
                 onResponseAckPermitted: bool = False, channelIndex: int = 0,
                 pkiEncrypted: bool = False, **_: Any) -> Any:  # fmt: skip
        """Solo administración al nodo remoto: contesta como la librería, en el mismo hilo."""
        pkt = mesh_pb2.MeshPacket(id=next(_ids))
        self.sent.append({"admin": destinationId, "pki": pkiEncrypted, "ch": channelIndex})
        if portNum != portnums_pb2.PortNum.ADMIN_APP or destinationId != REMOTE_NUM:
            return pkt
        if onResponse is not None:
            self.responseHandlers[pkt.id] = onResponse
        reply = self.remote.handle(Admin.FromString(data.SerializeToString()))
        if reply is None or onResponse is None:
            return pkt
        decoded: dict[str, Any] = {"requestId": pkt.id}
        if isinstance(reply, str):
            if reply == "ack" and not onResponseAckPermitted:
                return pkt  # la librería no le pasa los acuses a quien espera datos
            decoded.update(portnum="ROUTING_APP",
                           routing={} if reply == "ack" else {"errorReason": reply})  # fmt: skip
        else:
            self._getOrCreateByNum(REMOTE_NUM)["adminSessionPassKey"] = reply.session_passkey
            decoded.update(portnum="ADMIN_APP", admin={**MessageToDict(reply), "raw": reply})
        self.responseHandlers.pop(pkt.id, None)
        onResponse({"from": REMOTE_NUM, "decoded": decoded})
        return pkt

    def sendText(self, text: str, destinationId: Any = "^all", wantAck: bool = False,
                 channelIndex: int = 0, **_: Any) -> Any:  # fmt: skip
        pkt = mesh_pb2.MeshPacket(id=next(_ids))
        self.sent.append({"text": text, "to": destinationId, "ack": wantAck, "ch": channelIndex})
        return pkt

    def sendPosition(self, **kw: Any) -> None:
        self.sent.append({"position": kw})

    def sendTraceRoute(self, dest: Any, hopLimit: int, channelIndex: int = 0) -> None:
        self.sent.append({"traceroute": dest, "hops": hopLimit})


def attach_fake_board(service: Any, cid: str = "usb-prueba") -> tuple[SerialConnector, FakeIface]:
    """Registra una placa simulada como conector USB conectado (llamar dentro del loop)."""
    conn = SerialConnector(
        SerialConnectorCfg(id=cid, port="/dev/ttyFAKE"),
        on_message=service.radio_messages.on_event,
    )
    iface = FakeIface()
    conn._iface = iface
    conn._loop = asyncio.get_running_loop()
    conn.gateway_id = MY_ID
    conn._channel_names = {0: "MediumFast", 1: "Familia"}
    conn._set_state("connected")
    service.connectors.connectors[cid] = conn
    return conn, iface
