"""Red Meshtastic simulada (ADR 0008).

Genera grabaciones JSONL deterministas con los mensajes protobuf reales de la librería
instalada, y publica envelopes en un broker MQTT como lo haría un gateway Heltec.
Nada de esto se usa en producción: sirve para desarrollo, pruebas y demostraciones.
"""

from __future__ import annotations

import asyncio
import base64
import math
import random
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import orjson
from meshtastic.protobuf import config_pb2, mesh_pb2, mqtt_pb2, portnums_pb2, telemetry_pb2

from ..pipeline.crypto import DEFAULT_PSK, ChannelKey, decode_psk, encrypt_packet

PortNum = portnums_pb2.PortNum
Role = config_pb2.Config.DeviceConfig.Role
HW = mesh_pb2.HardwareModel
BROADCAST = 0xFFFFFFFF

# Viedma / Carmen de Patagones
CENTER = (-40.8135, -62.9967)
BASE_TS = 1792378800.0  # 2026-10-19 00:00 -03
PRIVATE_CHANNEL = ("Familia", "q0Kn3Ys7mQ5rUjXp2bF9tA==")  # clave de prueba, no real
PUBLIC_CHANNEL = "MediumFast"

MESSAGES = [
    "Buen día a todos desde Viedma",
    "¿Alguien me copia desde Patagones?",
    "Te recibo bien, 2 saltos",
    "Probando el nodo nuevo en el techo",
    "Excelente señal hoy",
    "¿Cómo está el viento en la costa?",
    "Mucho viento en El Cóndor, cuidado",
    "Voy saliendo para la ruta 3",
    "Hay neblina sobre el río",
    "Llegué bien, gracias",
    "¿Alguien tiene un repetidor cerca del puerto?",
    "El router de la torre anda de diez",
    "Mañana subo otro nodo a la loma",
    "Prueba de alcance: 18 km sin línea de vista",
    "¿Qué preset están usando?",
    "LongFast por ahora",
    "Bienvenidos los nodos nuevos 👋",
    "Corte de luz en el barrio, sigo con batería",
    "Volvió la luz",
    "Saludos desde la costanera",
    "¿Alguien vio el traceroute que hice?",
    "Llueve fuerte en el centro",
    "Temperatura bajando rápido",
    "Buenas noches, hasta mañana",
    "Nodo de prueba <script>alert(1)</script> no debería ejecutarse",
]
EMOJI_REACTIONS = ["👍", "❤️", "😂", "🙌"]


@dataclass
class SimNode:
    num: int
    long_name: str
    short_name: str
    role: int
    hw: int
    lat: float
    lon: float
    alt: int
    battery: int | None = 80
    voltage: float = 4.0
    has_env: bool = False
    has_power: bool = False
    mobile: bool = False
    precision_bits: int = 32
    path: list[tuple[float, float]] = field(default_factory=list)
    public_key: bytes = b""


def _num(rng: random.Random) -> int:
    return rng.randint(0x10000000, 0xFFFFFFFE)


def _offset(lat: float, lon: float, dn_km: float, de_km: float) -> tuple[float, float]:
    dlat = dn_km / 111.32
    dlon = de_km / (111.32 * math.cos(math.radians(lat)))
    return round(lat + dlat, 6), round(lon + dlon, 6)


def _dist_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    dy = (a[0] - b[0]) * 111.32
    dx = (a[1] - b[1]) * 111.32 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def build_network(rng: random.Random, n_clients: int = 18) -> tuple[list[SimNode], list[SimNode]]:
    lat0, lon0 = CENTER
    gw1 = SimNode(
        0xA1B2C3D4,
        "Gateway Interior",
        "GWIN",
        Role.CLIENT_MUTE,
        HW.HELTEC_V4,
        lat0,
        lon0,
        12,
        battery=101,
        voltage=5.1,
    )
    gw2 = SimNode(
        0xA1B2C3D5,
        "Gateway Patagones",
        "GWPA",
        Role.CLIENT_MUTE,
        HW.HELTEC_V3,
        *_offset(lat0, lon0, 1.8, 1.4),
        20,
        battery=101,
        voltage=5.0,
    )
    nodes = [
        SimNode(
            0x0B03CBF0,
            "Techo Magna",
            "TECH",
            Role.CLIENT_BASE,
            HW.HELTEC_V4,
            lat0 + 0.0004,
            lon0 + 0.0003,
            14,
            battery=88,
            voltage=4.1,
            has_power=True,
        ),
        SimNode(
            0x0B03CBF1,
            "Torre del Agua",
            "TORR",
            Role.ROUTER,
            HW.STATION_G2,
            *_offset(lat0, lon0, 2.5, -3.0),
            45,
            battery=101,
            voltage=5.0,
        ),
        SimNode(
            0x0B03CBF2,
            "Loma Patagones",
            "LOMA",
            Role.ROUTER_LATE,
            HW.RAK4631,
            *_offset(lat0, lon0, 4.2, 3.5),
            60,
            battery=96,
            voltage=4.2,
        ),
        SimNode(
            0x0B03CBF3,
            "Repetidor Costa",
            "RCOS",
            Role.REPEATER,
            HW.RAK4631,
            *_offset(lat0, lon0, -22.0, 14.0),
            30,
            battery=75,
            voltage=3.95,
        ),
        SimNode(
            0x0B03CBF4,
            "Estación Meteo",
            "METE",
            Role.SENSOR,
            HW.HELTEC_WSL_V3,
            *_offset(lat0, lon0, -1.2, 2.0),
            18,
            battery=101,
            voltage=5.0,
            has_env=True,
        ),
        SimNode(
            0x0B03CBF5,
            "Camioneta Ruta 3",
            "CAMI",
            Role.TRACKER,
            HW.HELTEC_WIRELESS_TRACKER,
            *_offset(lat0, lon0, -3.0, -2.0),
            5,
            battery=70,
            voltage=3.9,
            mobile=True,
        ),
        SimNode(
            0x0B03CBF6,
            "Bici Costanera",
            "BICI",
            Role.CLIENT,
            HW.T_ECHO,
            *_offset(lat0, lon0, 0.5, 0.8),
            3,
            battery=60,
            voltage=3.8,
            mobile=True,
            precision_bits=16,
        ),
        gw1,
        gw2,
    ]
    first_names = ["Nodo", "Casa", "Base", "Móvil", "Radio", "Antena"]
    places = [
        "Centro",
        "Puerto",
        "Barrio Lavalle",
        "Costanera",
        "Aeropuerto",
        "Zatti",
        "Mitre",
        "San Martín",
        "El Cóndor",
        "Ruta 251",
        "Cerro",
        "Balneario",
        "IDEVI",
        "Parque",
        "Río",
        "Sur",
        "Norte",
        "Chacras",
        "Estación",
        "Escuela",
    ]
    hws = [HW.HELTEC_V3, HW.HELTEC_V4, HW.TBEAM, HW.T_ECHO, HW.RAK4631, HW.HELTEC_WIRELESS_PAPER]
    for i in range(n_clients):
        ang = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(0.5, 9.0) if i < n_clients - 3 else rng.uniform(12, 30)
        lat, lon = _offset(lat0, lon0, r * math.sin(ang), r * math.cos(ang))
        name = f"{rng.choice(first_names)} {places[i % len(places)]}"
        short = "".join(w[0] for w in name.split())[:2].upper() + f"{i:02d}"
        nodes.append(
            SimNode(
                _num(rng),
                name,
                short[:4],
                rng.choice([Role.CLIENT] * 5 + [Role.CLIENT_MUTE]),
                rng.choice(hws),
                lat,
                lon,
                rng.randint(2, 40),
                battery=rng.randint(30, 100),
                voltage=round(rng.uniform(3.6, 4.15), 2),
                has_env=(i % 7 == 3),
                precision_bits=rng.choice([32, 32, 32, 13, 15]),
            )
        )
    for n in nodes:
        n.public_key = bytes(rng.getrandbits(8) for _ in range(32))
        if n.mobile:
            n.path = [_offset(n.lat, n.lon, 0.9 * k * math.sin(k / 3), 0.7 * k) for k in range(30)]
    return nodes, [gw1, gw2]


class Sim:
    def __init__(self, seed: int = 1, hours: float = 24, start_ts: float = BASE_TS) -> None:
        self.rng = random.Random(seed)
        self.hours = hours
        self.start = start_ts
        self.nodes, self.gateways = build_network(self.rng)
        self.by_num = {n.num: n for n in self.nodes}
        self.routers = [
            n for n in self.nodes if n.role in (Role.ROUTER, Role.ROUTER_LATE, Role.REPEATER)
        ]
        self.default_key = ChannelKey.from_psk(PUBLIC_CHANNEL, bytes([1]))
        self.private_key = ChannelKey.from_psk(PRIVATE_CHANNEL[0], decode_psk(PRIVATE_CHANNEL[1]))
        self.events: list[tuple[float, dict[str, object]]] = []
        self.last_text_ids: list[int] = []

    # ---------------------------------------------------------------- utilidades

    def _pid(self) -> int:
        return self.rng.randint(1, 0xFFFFFFFE)

    def _pos(self, n: SimNode, t: float) -> tuple[float, float]:
        if not n.mobile or not n.path:
            return n.lat, n.lon
        k = (t - self.start) / 900.0  # un tramo cada 15 min
        i = int(k) % (len(n.path) - 1)
        f = k - int(k)
        a, b = n.path[i], n.path[i + 1]
        return round(a[0] + (b[0] - a[0]) * f, 6), round(a[1] + (b[1] - a[1]) * f, 6)

    def _hops_to(self, n: SimNode, gw: SimNode, t: float) -> int | None:
        d = _dist_km(self._pos(n, t), (gw.lat, gw.lon))
        if d < 3:
            return 0
        if d < 10:
            return 1
        if d < 25:
            return 2
        if d < 35:
            return 3
        return None

    def _emit(
        self,
        t: float,
        src: SimNode,
        portnum: int,
        payload: bytes,
        *,
        to: int = BROADCAST,
        want_ack: bool = False,
        reply_id: int = 0,
        emoji: int = 0,
        request_id: int = 0,
        channel: str = PUBLIC_CHANNEL,
        encrypt_for: ChannelKey | None = None,
        via_mqtt: bool = False,
        pki: bool = False,
        gateways: list[SimNode] | None = None,
        pid: int | None = None,
    ) -> int:
        pid = pid or self._pid()
        data = mesh_pb2.Data(
            portnum=portnum,
            payload=payload,
            reply_id=reply_id,
            emoji=emoji,
            request_id=request_id,
            bitfield=1,
        )
        for gw in gateways or self.gateways:
            # Lo que entra por MQTT lo inyecta un gateway cercano: llega a pocos saltos.
            hops = 0 if src is gw else (1 if via_mqtt else self._hops_to(src, gw, t))
            if hops is None:
                continue
            if gw is self.gateways[1] and src is not gw and self.rng.random() < 0.55:
                continue  # el segundo gateway oye menos
            pkt = mesh_pb2.MeshPacket()
            setattr(pkt, "from", src.num)
            pkt.to = to
            pkt.id = pid
            pkt.hop_start = 3
            pkt.hop_limit = 3 - hops
            pkt.want_ack = want_ack
            pkt.via_mqtt = via_mqtt
            pkt.priority = mesh_pb2.MeshPacket.Priority.RELIABLE if want_ack else 0
            if src is not gw:
                d = 4.0 if via_mqtt else _dist_km(self._pos(src, t), (gw.lat, gw.lon))
                pkt.rx_snr = round(max(-18.0, 11 - d * 0.9 + self.rng.uniform(-2, 2)) * 4) / 4
                pkt.rx_rssi = int(-55 - d * 3.2 + self.rng.uniform(-4, 4))
                pkt.rx_time = int(t)
                if hops and self.routers:
                    pkt.relay_node = self.rng.choice(self.routers).num & 0xFF
            pkt.transport_mechanism = (
                mesh_pb2.MeshPacket.TransportMechanism.TRANSPORT_MQTT
                if via_mqtt
                else mesh_pb2.MeshPacket.TransportMechanism.TRANSPORT_LORA
            )
            if pki:
                pkt.pki_encrypted = True
                pkt.encrypted = bytes(self.rng.getrandbits(8) for _ in range(len(payload) + 16))
                pkt.channel = 0
            elif encrypt_for is not None:
                encrypt_packet(pkt, data, encrypt_for)
            else:
                pkt.decoded.CopyFrom(data)
                pkt.channel = 0
            jitter = self.rng.uniform(0.05, 0.9) if gw is not self.gateways[0] else 0.0
            self.events.append(
                (
                    t + jitter,
                    {
                        "source": "mqtt",
                        "connector_id": "mqtt-local",
                        "gateway_id": f"!{gw.num:08x}",
                        "channel_id": channel,
                        "rx_time": round(t + jitter, 3),
                        "packet_b64": base64.b64encode(pkt.SerializeToString()).decode(),
                    },
                )
            )
        return pid

    # ---------------------------------------------------------------- generadores

    def _nodeinfo(self, n: SimNode, t: float) -> None:
        u = mesh_pb2.User(
            id=f"!{n.num:08x}",
            long_name=n.long_name,
            short_name=n.short_name,
            hw_model=n.hw,
            role=n.role,
            public_key=n.public_key,
        )
        self._emit(t, n, PortNum.NODEINFO_APP, u.SerializeToString())

    def _position(self, n: SimNode, t: float) -> None:
        lat, lon = self._pos(n, t)
        p = mesh_pb2.Position(
            latitude_i=int(lat * 1e7),
            longitude_i=int(lon * 1e7),
            altitude=n.alt,
            time=int(t),
            precision_bits=n.precision_bits,
            sats_in_view=self.rng.randint(6, 14),
        )
        if n.mobile:
            p.ground_speed = self.rng.randint(3, 25)
        self._emit(t, n, PortNum.POSITION_APP, p.SerializeToString())

    def _device(self, n: SimNode, t: float) -> None:
        hour = ((t - self.start) / 3600) % 24
        dm = telemetry_pb2.DeviceMetrics()
        if n.battery is not None:
            if n.battery > 100:
                dm.battery_level = 101
                dm.voltage = round(n.voltage + self.rng.uniform(-0.05, 0.05), 3)
            else:
                solar = n.has_power
                swing = 12 * math.sin((hour - 9) / 24 * 2 * math.pi) if solar else -0.4 * hour
                level = max(5, min(100, int(n.battery + swing + self.rng.uniform(-2, 2))))
                dm.battery_level = level
                dm.voltage = round(3.3 + level / 100 * 0.9, 3)
        dm.channel_utilization = round(
            6 + 10 * max(0, math.sin((hour - 7) / 24 * 2 * math.pi)) + self.rng.uniform(0, 4), 2
        )
        dm.air_util_tx = round(self.rng.uniform(0.1, 2.5), 3)
        dm.uptime_seconds = int(t - self.start) + 3600 * 5
        tel = telemetry_pb2.Telemetry(time=int(t), device_metrics=dm)
        self._emit(t, n, PortNum.TELEMETRY_APP, tel.SerializeToString())

    def _environment(self, n: SimNode, t: float) -> None:
        hour = ((t - self.start) / 3600) % 24
        em = telemetry_pb2.EnvironmentMetrics(
            temperature=round(
                14 + 7 * math.sin((hour - 9) / 24 * 2 * math.pi) + self.rng.uniform(-0.5, 0.5), 2
            ),
            relative_humidity=round(
                55 - 15 * math.sin((hour - 9) / 24 * 2 * math.pi) + self.rng.uniform(-2, 2), 1
            ),
            barometric_pressure=round(
                1012 + 3 * math.sin(hour / 12 * math.pi) + self.rng.uniform(-0.3, 0.3), 1
            ),
        )
        if n.role == Role.SENSOR:
            em.wind_speed = round(abs(6 + 5 * math.sin(hour / 5) + self.rng.uniform(-2, 2)), 1)
            em.wind_gust = round(em.wind_speed * 1.4, 1)
            em.wind_direction = self.rng.randint(180, 260)
            em.lux = round(max(0.0, 40000 * math.sin((hour - 6) / 12 * math.pi)), 1)
            em.rainfall_1h = 0.0 if hour < 15 or hour > 17 else 2.4
            em.rainfall_24h = 3.8
        tel = telemetry_pb2.Telemetry(time=int(t), environment_metrics=em)
        self._emit(t, n, PortNum.TELEMETRY_APP, tel.SerializeToString())

    def _power(self, n: SimNode, t: float) -> None:
        hour = ((t - self.start) / 3600) % 24
        sun = max(0.0, math.sin((hour - 6) / 12 * math.pi))
        pm = telemetry_pb2.PowerMetrics(
            ch1_voltage=round(5.0 * sun + 0.1, 3),
            ch1_current=round(800 * sun, 1),
            ch2_voltage=round(3.7 + 0.4 * sun, 3),
            ch2_current=round(120 + 300 * sun, 1),
        )
        tel = telemetry_pb2.Telemetry(time=int(t), power_metrics=pm)
        self._emit(t, n, PortNum.TELEMETRY_APP, tel.SerializeToString())

    def _neighbors(self, n: SimNode, t: float) -> None:
        others = sorted(self.nodes, key=lambda o: _dist_km((n.lat, n.lon), (o.lat, o.lon)))[1:6]
        ni = mesh_pb2.NeighborInfo(
            node_id=n.num, last_sent_by_id=n.num, node_broadcast_interval_secs=14400
        )
        for o in others:
            d = _dist_km((n.lat, n.lon), (o.lat, o.lon))
            ni.neighbors.add(node_id=o.num, snr=round(max(-15.0, 10 - d), 2))
        self._emit(t, n, PortNum.NEIGHBORINFO_APP, ni.SerializeToString())

    def _text(self, n: SimNode, t: float, text: str, reply_id: int = 0, emoji: int = 0) -> int:
        pid = self._emit(
            t, n, PortNum.TEXT_MESSAGE_APP, text.encode(), reply_id=reply_id, emoji=emoji
        )
        self.last_text_ids.append(pid)
        return pid

    def _traceroute(self, a: SimNode, b: SimNode, t: float) -> None:
        req = self._emit(
            t,
            a,
            PortNum.TRACEROUTE_APP,
            mesh_pb2.RouteDiscovery().SerializeToString(),
            to=b.num,
            want_ack=True,
        )
        mid = [r.num for r in self.routers[:2] if r is not a and r is not b]
        rd = mesh_pb2.RouteDiscovery(
            route=mid,
            snr_towards=[self.rng.randint(-40, 40) for _ in range(len(mid) + 1)],
            route_back=mid[::-1],
            snr_back=[self.rng.randint(-40, 40) for _ in range(len(mid) + 1)],
        )
        self._emit(
            t + 4, b, PortNum.TRACEROUTE_APP, rd.SerializeToString(), to=a.num, request_id=req
        )

    def _routing_ack(self, n: SimNode, dest: SimNode, t: float, req: int, error: int = 0) -> None:
        r = mesh_pb2.Routing(error_reason=error)
        self._emit(t, n, PortNum.ROUTING_APP, r.SerializeToString(), to=dest.num, request_id=req)

    def _map_report(self, gw: SimNode, t: float) -> None:
        mr = mqtt_pb2.MapReport(
            long_name=gw.long_name,
            short_name=gw.short_name,
            role=gw.role,
            hw_model=gw.hw,
            firmware_version="2.7.12.abc1234",
            region=config_pb2.Config.LoRaConfig.RegionCode.ANZ,
            modem_preset=config_pb2.Config.LoRaConfig.ModemPreset.MEDIUM_FAST,
            has_default_channel=True,
            latitude_i=int(gw.lat * 1e7),
            longitude_i=int(gw.lon * 1e7),
            altitude=gw.alt,
            position_precision=13,
            num_online_local_nodes=self.rng.randint(12, 26),
        )
        self._emit(t, gw, PortNum.MAP_REPORT_APP, mr.SerializeToString(), gateways=[gw])

    # ---------------------------------------------------------------- escenario

    def build(self) -> list[dict[str, object]]:
        rng = self.rng
        end = self.start + self.hours * 3600
        for n in self.nodes:
            off = rng.uniform(0, 1800)
            t = self.start + off
            while t < end:
                self._nodeinfo(n, t)
                t += 3 * 3600 + rng.uniform(-300, 300)
            interval = 240 if n.mobile else rng.choice([600, 900, 1800, 3600])
            t = self.start + rng.uniform(0, interval)
            while t < end:
                self._position(n, t)
                t += interval + rng.uniform(-30, 30)
            t = self.start + rng.uniform(0, 1800)
            while t < end:
                self._device(n, t)
                if n.has_env:
                    self._environment(n, t + 5)
                if n.has_power:
                    self._power(n, t + 9)
                t += 1800 + rng.uniform(-60, 60)
            if n.role == Role.SENSOR:
                t = self.start + 900
                while t < end:
                    self._environment(n, t)
                    t += 900
            if n in self.routers:
                t = self.start + rng.uniform(600, 3600)
                while t < end:
                    self._neighbors(n, t)
                    t += 4 * 3600
        for gw in self.gateways:
            t = self.start + 120
            while t < end:
                self._map_report(gw, t)
                t += 3600
        # conversación del canal público
        talkers = [n for n in self.nodes if n.role in (Role.CLIENT, Role.CLIENT_BASE, Role.TRACKER)]
        n_msgs = max(6, int(self.hours * 2.5))
        for i in range(n_msgs):
            t = self.start + (i + rng.random()) * (self.hours * 3600 / n_msgs)
            who = rng.choice(talkers)
            text = MESSAGES[i % len(MESSAGES)]
            pid = self._text(who, t, text)
            if rng.random() < 0.35:
                other = rng.choice(talkers)
                self._text(
                    other,
                    t + rng.uniform(20, 120),
                    rng.choice(["Te copio", "Recibido 👍", "Dale!"]),
                    reply_id=pid,
                )
            if rng.random() < 0.25:
                other = rng.choice(talkers)
                self._text(
                    other,
                    t + rng.uniform(5, 60),
                    rng.choice(EMOJI_REACTIONS),
                    reply_id=pid,
                    emoji=1,
                )
        mid = self.start + self.hours * 3600 / 2
        a, b = talkers[0], talkers[1]
        # SOS por texto y por ALERT_APP
        self._text(talkers[2], mid, "SOS necesito ayuda en la costanera, sin señal de celular")
        self._emit(
            mid + 600, talkers[3], PortNum.ALERT_APP, "Alerta: caída de un nodo de la red".encode()
        )
        # mensaje directo (nunca debe guardarse su texto)
        dm = self._emit(
            mid + 30,
            a,
            PortNum.TEXT_MESSAGE_APP,
            b"Mensaje privado: no publicar",
            to=b.num,
            want_ack=True,
        )
        self._routing_ack(b, a, mid + 33, dm)
        self._routing_ack(
            self.routers[0], a, mid + 40, dm, error=mesh_pb2.Routing.Error.MAX_RETRANSMIT
        )
        # canal privado con clave conocida (se descifra pero no se publica)
        self._emit(
            mid + 90,
            a,
            PortNum.TEXT_MESSAGE_APP,
            b"Hola familia",
            channel=PRIVATE_CHANNEL[0],
            encrypt_for=self.private_key,
        )
        # paquetes cifrados del canal público (gateway con encryption_enabled = true)
        for k in range(6):
            n = talkers[(k + 4) % len(talkers)]
            u = telemetry_pb2.Telemetry(
                time=int(mid),
                device_metrics=telemetry_pb2.DeviceMetrics(battery_level=50 + k, voltage=3.9),
            )
            self._emit(
                mid + 120 + k * 60,
                n,
                PortNum.TELEMETRY_APP,
                u.SerializeToString(),
                encrypt_for=self.default_key,
            )
        self._emit(
            mid + 500,
            b,
            PortNum.TEXT_MESSAGE_APP,
            "Mensaje cifrado del canal público".encode(),
            encrypt_for=self.default_key,
        )
        # mensaje directo PKI (no se puede descifrar)
        self._emit(mid + 700, a, PortNum.TEXT_MESSAGE_APP, b"secreto", to=b.num, pki=True)
        # traceroutes y waypoint
        for k in range(4):
            self._traceroute(talkers[k], talkers[-1 - k], self.start + 3600 * (2 + k * 5))
        wp = mesh_pb2.Waypoint(
            id=4242,
            latitude_i=int(-40.809 * 1e7),
            longitude_i=int(-62.985 * 1e7),
            expire=int(self.start + 86400 * 30),
            name="Punto de encuentro",
            description="Plaza San Martín",
            icon=0x1F4CD,
        )
        self._emit(mid + 1200, a, PortNum.WAYPOINT_APP, wp.SerializeToString())
        # otros portnums
        self._emit(mid + 1300, a, PortNum.RANGE_TEST_APP, b"seq 1")
        self._emit(mid + 1310, a, PortNum.RANGE_TEST_APP, b"seq 2")
        self._emit(mid + 1400, b, PortNum.DETECTION_SENSOR_APP, b"Puerta abierta")
        self._emit(mid + 1500, b, PortNum.PAXCOUNTER_APP, bytes([8, 12, 16, 3, 24, 120]))
        self._emit(mid + 1600, a, PortNum.STORE_FORWARD_APP, bytes([8, 1]))
        self._emit(mid + 1700, a, PortNum.PRIVATE_APP, b"\x01\x02\x03")
        # un nodo lejano que llegó por MQTT (otro gateway lo inyectó en la red)
        remote = SimNode(
            0xDEADBEEF, "Nodo Lejano MQTT", "LEJ", Role.CLIENT, HW.TBEAM, -34.6, -58.4, 10
        )
        self.by_num[remote.num] = remote
        self._emit(
            mid + 1800,
            remote,
            PortNum.NODEINFO_APP,
            mesh_pb2.User(
                long_name=remote.long_name, short_name=remote.short_name
            ).SerializeToString(),
            via_mqtt=True,
            gateways=[self.gateways[0]],
        )
        p = mesh_pb2.Position(latitude_i=int(-34.6 * 1e7), longitude_i=int(-58.4 * 1e7))
        self._emit(
            mid + 1801,
            remote,
            PortNum.POSITION_APP,
            p.SerializeToString(),
            via_mqtt=True,
            gateways=[self.gateways[0]],
        )
        self.events.sort(key=lambda e: e[0])
        records = [rec for _, rec in self.events]
        # basura al final: paquete ilegible
        records.append(
            {
                "source": "mqtt",
                "connector_id": "mqtt-local",
                "gateway_id": "!a1b2c3d4",
                "channel_id": PUBLIC_CHANNEL,
                "rx_time": end,
                "packet_b64": base64.b64encode(b"\xff\x00garbage").decode(),
            }
        )
        return records


def generate(out: Path, hours: float = 24, seed: int = 1, start_ts: float = BASE_TS) -> int:
    sim = Sim(seed=seed, hours=hours, start_ts=start_ts)
    records = sim.build()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as f:
        f.write(f"# meshbox: red simulada (ADR 0008), semilla {seed}, {hours} h\n".encode())
        for rec in records:
            f.write(orjson.dumps(rec) + b"\n")
    return len(records)


def default_psk_b64() -> str:
    return base64.b64encode(DEFAULT_PSK).decode()


def _iter_envelopes(path: Path) -> Iterator[tuple[float, str | None, str | None, bytes]]:
    from ..connectors.replay import read_recording

    for rec in read_recording(path):
        try:
            pkt = mesh_pb2.MeshPacket.FromString(base64.b64decode(str(rec["packet_b64"])))
        except Exception:
            continue
        env = mqtt_pb2.ServiceEnvelope(
            packet=pkt,
            channel_id=str(rec.get("channel_id") or ""),
            gateway_id=str(rec.get("gateway_id") or ""),
        )
        yield (
            float(rec.get("rx_time") or 0),
            rec.get("channel_id"),
            rec.get("gateway_id"),
            env.SerializeToString(),
        )


async def publish(
    path: Path,
    *,
    host: str,
    port: int,
    root: str,
    username: str | None,
    password: str | None,
    speed: float = 10.0,
    limit: int | None = None,
) -> int:
    """Publica la grabación como envelopes protobuf en `<root>/2/e/<canal>/<gw>` (como un Heltec)."""
    import aiomqtt

    sent = 0
    async with aiomqtt.Client(
        hostname=host,
        port=port,
        username=username,
        password=password,
        identifier=f"meshbox-sim-{random.randint(1000, 9999)}",
    ) as client:
        first: float | None = None
        wall0 = time.monotonic()
        for rx, channel, gw, payload in _iter_envelopes(path):
            if first is None:
                first = rx
            if speed > 0:
                delay = (rx - first) / speed - (time.monotonic() - wall0)
                if delay > 0:
                    await asyncio.sleep(delay)
            pkt = mqtt_pb2.ServiceEnvelope.FromString(payload).packet
            is_map = pkt.HasField("decoded") and pkt.decoded.portnum == PortNum.MAP_REPORT_APP
            topic = (
                f"{root}/2/map/"
                if is_map
                else f"{root}/2/e/{channel or PUBLIC_CHANNEL}/{gw or '!00000000'}"
            )
            await client.publish(topic, payload, qos=0)
            sent += 1
            if limit and sent >= limit:
                break
    return sent
