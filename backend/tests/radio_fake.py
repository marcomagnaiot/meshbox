"""Placa Meshtastic simulada con la interfaz de la librería que usa el cliente del panel."""

from __future__ import annotations

import asyncio
import itertools
from types import SimpleNamespace
from typing import Any

from meshtastic.protobuf import channel_pb2, config_pb2, localonly_pb2, mesh_pb2

from meshbox.config import SerialConnectorCfg
from meshbox.connectors.serial import SerialConnector

MY_NUM = 0x0A0B0C0D
MY_ID = "!0a0b0c0d"
_ids = itertools.count(1000)


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
                "user": {"id": "!11112222", "longName": "Vecino", "shortName": "VEC"},
                "snr": 5.5,
                "hopsAway": 1,
                "lastHeard": 1792500100,
            },
        }  # fmt: skip
        self.nodes = {n["user"]["id"]: n for n in self.nodesByNum.values()}
        self.localNode = FakeNode(self)
        self.sent: list[dict[str, Any]] = []

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
