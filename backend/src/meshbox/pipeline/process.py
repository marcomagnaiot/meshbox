"""Procesamiento de cada paquete (sección 5.3).

Orden: deduplicación → límite por nodo → descifrado → privacidad (filtro previo) →
decodificación → privacidad (reglas posteriores) → estado en memoria + cola de escritura
→ eventos. Un paquete roto nunca detiene el pipeline.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import orjson
from meshtastic.protobuf import config_pb2, mesh_pb2

from ..bus import EventBus
from ..config import Config
from ..models import (
    BROADCAST,
    Diagnostic,
    LinkObserved,
    MessageAdded,
    NodeUpserted,
    PacketProcessed,
    PositionAdded,
    RawPacket,
    RawPacketReceived,
    TelemetryAdded,
    TracerouteAdded,
    WaypointChanged,
    node_id,
)
from ..state import GatewayInfo, MeshState, NodeRecord, env_public
from ..store.db import BatchWriter
from .crypto import try_decrypt
from .decode import (
    MAX_LONG_NAME,
    MAX_SHORT_NAME,
    MAX_TEXT,
    Decoded,
    clip,
    decode_data,
    device_metrics_values,
    enum_name,
    environment_values,
    hw_model_name,
    message_to_dict,
    portnum_name,
    position_latlon,
    power_values,
    precision_meters,
    role_name,
    traceroute_snrs,
)
from .dedup import Deduplicator, NodeRateLimiter
from .privacy import bits_for_meters, degrade_position, entered_via_mqtt, haversine_m, pre_filter

LinkSource = Literal["neighborinfo", "direct", "traceroute"]

log = logging.getLogger(__name__)

RegionCode = config_pb2.Config.LoRaConfig.RegionCode
ModemPreset = config_pb2.Config.LoRaConfig.ModemPreset
Priority = mesh_pb2.MeshPacket.Priority
GATEWAY_TOUCH_S = 60  # actividad del gateway: como mucho una escritura por minuto
MAP_REPORT_STALE_S = 86_400  # una posición más precisa pero de más de un día la reemplaza


def _bits_rank(bits: int | None) -> int:
    """Precisión comparable: sin dato (0) o 32 es la posición completa."""
    return 32 if not bits or bits >= 32 else bits


def map_report_wins(rec: NodeRecord, bits: int | None, now: float) -> bool:
    """El informe de mapa actualiza la posición si no hay otra, si es igual o más preciso que
    la que hay, o si la que hay tiene más de un día (el nodo pudo moverse). Así no pisa la
    posición exacta que el nodo manda por radio con la aproximada del informe."""
    if rec.lat is None or rec.position_ts is None:
        return True
    if _bits_rank(bits) >= _bits_rank(rec.precision_bits):
        return True
    return now - rec.position_ts >= MAP_REPORT_STALE_S


@dataclass(slots=True)
class _Ctx:
    """Datos de un paquete en proceso, para no pasar diez argumentos."""

    raw: RawPacket
    pk: int
    now: float
    from_num: int
    to_num: int
    data: mesh_pb2.Data
    gateway: str
    hops: int | None
    via_mqtt: bool
    ignore_node: bool
    is_public: bool
    channel_name: str | None
    rec: NodeRecord | None


class Processor:
    def __init__(
        self,
        cfg: Config,
        state: MeshState,
        writer: BatchWriter,
        bus: EventBus,
    ) -> None:
        self.cfg = cfg
        self.state = state
        self.writer = writer
        self.bus = bus
        self.dedup = Deduplicator(cfg.ingest.dedup_cache, cfg.ingest.dedup_ttl_s)
        self.rate = NodeRateLimiter(cfg.ingest.per_node_max_per_min)
        self.writer.on_remap = self.dedup.remap
        self._dirty: set[int] = set()
        self.raw_hooks: list[Callable[[RawPacket], None]] = []

    # ---------------------------------------------------------------- entrada

    def process(self, raw: RawPacket) -> None:
        try:
            self._process(raw)
        except Exception:
            self.state.invalid_total += 1
            log.exception("error procesando paquete de %s", raw.connector_id)

    def _process(self, raw: RawPacket) -> None:
        for hook in self.raw_hooks:
            try:
                hook(raw)
            except Exception:
                log.exception("gancho de paquete crudo falló")
        pkt = raw.packet
        now = raw.rx_time
        from_num = getattr(pkt, "from")
        if from_num == 0 or from_num == BROADCAST:
            self.state.invalid_total += 1
            return
        rec = self.state.nodes.get(from_num)
        if rec is not None and rec.hidden:
            self.state.hidden_dropped += 1
            return

        gateway = raw.gateway_id or f"@{raw.connector_id}"
        via_mqtt = entered_via_mqtt(pkt)
        hops = None
        if pkt.hop_start > 0 and pkt.hop_start >= pkt.hop_limit:
            hops = pkt.hop_start - pkt.hop_limit
        if pkt.rx_snr == 0 and pkt.rx_rssi == 0:
            snr, rssi = None, None
        else:
            snr, rssi = round(pkt.rx_snr, 2), (pkt.rx_rssi or None)

        reception = {
            "gateway": gateway,
            "source": raw.source,
            "rx_time": now,
            "rx_snr": snr,
            "rx_rssi": rssi,
            "hop_limit": pkt.hop_limit,
            "relay_node": pkt.relay_node or None,
            "via_mqtt": int(via_mqtt),
            "transport": pkt.transport_mechanism or None,
        }
        self._touch_gateway(raw, now)

        # 0. Paquetes que la placa genera solo para su cliente USB/TCP (telemetría cada minuto,
        # estadísticas locales): no pasaron por el aire. No son tráfico de la malla.
        if self._local_only(raw, pkt, from_num):
            self._on_local_packet(raw, pkt, from_num, now)
            return

        # 1. Deduplicación: otra copia (otro gateway) solo agrega la recepción.
        existing = self.dedup.lookup(from_num, pkt.id, now)
        if existing is not None:
            self.state.duplicates_total += 1
            self.writer.enqueue("reception", {**reception, "packet_pk": existing})
            if hops == 0 and not via_mqtt and raw.gateway_id:
                self._direct_link(raw.gateway_id, from_num, snr, now)
            self.bus.publish(
                PacketProcessed(
                    pk=existing,
                    portnum=None,
                    from_num=from_num,
                    to_num=pkt.to,
                    packet_id=pkt.id,
                    channel=raw.channel_id,
                    hops=hops,
                    snr=snr,
                    rssi=rssi,
                    gateway=gateway,
                    source=raw.source,
                    connector_id=raw.connector_id,
                    is_public=False,
                    encrypted=pkt.HasField("encrypted"),
                    decoded_ok=False,
                    duplicate=True,
                    via_mqtt=via_mqtt,
                    rx_time=now,
                )
            )
            return

        # 2. Límite por nodo (inundaciones)
        if not self.rate.allow(from_num, now):
            self.state.flood_dropped += 1
            if self.rate.first_drop_in_window(from_num):
                self.bus.publish(
                    Diagnostic(
                        code="flood",
                        message=f"{node_id(from_num)} supera {self.rate.max_per_min} paquetes/min",
                        details={"node": node_id(from_num)},
                    )
                )
            return

        pk = self.writer.ids.next("packets")
        self.dedup.add(from_num, pkt.id, pk, now)

        # 3. Descifrado
        data: mesh_pb2.Data | None = None
        channel_name = raw.channel_id or None
        channel_index: int | None = None
        channel_hash: int | None = None
        which = pkt.WhichOneof("payload_variant")
        encrypted = which == "encrypted"
        if which == "decoded":
            data = pkt.decoded
            channel_index = pkt.channel
        elif encrypted:
            channel_hash = pkt.channel
            result = None if pkt.pki_encrypted else try_decrypt(pkt, self.state.channel_keys())
            if result is not None:
                data, ck = result
                channel_name = ck.name
            else:
                self.state.undecryptable += 1
        else:
            self.state.invalid_total += 1

        portnum = portnum_name(data.portnum) if data is not None else None

        # 4. Privacidad, filtro previo
        pre = pre_filter(
            to_num=pkt.to,
            portnum=portnum,
            channel_public=self.state.channel_is_public(channel_name),
            decoded=data is not None,
        )

        # 5. Decodificación
        decoded: Decoded | None = None
        if data is not None and pre.process:
            decoded = decode_data(data)
            if not decoded.ok:
                self.state.decode_errors += 1
                log.warning(
                    "paquete %d (%s) no se pudo decodificar: %s", pk, portnum, decoded.error
                )
        decoded_ok = data is not None and (decoded is None or decoded.ok)
        is_public = pre.public and decoded_ok

        self.writer.enqueue(
            "packet",
            {
                "pk": pk,
                "from_num": from_num,
                "packet_id": pkt.id,
                "to_num": pkt.to,
                "channel_index": channel_index,
                "channel_name": channel_name,
                "channel_hash": channel_hash,
                "portnum": portnum,
                "first_rx": now,
                "hop_start": pkt.hop_start or None,
                "want_ack": int(pkt.want_ack),
                "priority": enum_name(Priority, pkt.priority),
                "encrypted": int(encrypted),
                "decoded_ok": int(decoded_ok),
                "is_public": int(is_public),
                "payload_len": len(data.payload) if data is not None else len(pkt.encrypted),
                "raw": None if pre.header_only else pkt.SerializeToString(),
            },
        )
        self.writer.enqueue("reception", {**reception, "packet_pk": pk})
        self.state.count_packet(portnum, raw.connector_id, now)

        # 6. Privacidad, reglas posteriores: lo que entró por MQTT no toca nodos ni posiciones.
        ignore_node = via_mqtt and self.cfg.privacy.ignore_via_mqtt
        changed: set[str] = set()
        is_new = False
        if not ignore_node:
            rec, is_new = self._touch_node(from_num, now, snr, rssi, hops, gateway, via_mqtt)
            changed.update(("last_heard", "snr", "rssi", "hops"))
            if hops == 0 and not via_mqtt and raw.gateway_id:
                self._direct_link(raw.gateway_id, from_num, snr, now)
        else:
            rec = self.state.nodes.get(from_num)

        # 7. Efectos por tipo de contenido
        if decoded is not None and decoded.ok and data is not None:
            ctx = _Ctx(
                raw=raw,
                pk=pk,
                now=now,
                from_num=from_num,
                to_num=pkt.to,
                data=data,
                gateway=gateway,
                hops=hops,
                via_mqtt=via_mqtt,
                ignore_node=ignore_node,
                is_public=is_public,
                channel_name=channel_name,
                rec=rec,
            )
            try:
                changed |= self._apply(decoded, ctx)
            except Exception:
                self.state.decode_errors += 1
                log.exception("efectos del paquete %d (%s) fallaron", pk, portnum)

        # 8. Eventos
        if rec is not None and not rec.hidden and (changed or is_new):
            self._dirty.add(rec.num)
            self.bus.publish(
                NodeUpserted(node=rec.public(), changed=tuple(sorted(changed)), is_new=is_new)
            )
        self.bus.publish(
            PacketProcessed(
                pk=pk,
                portnum=portnum,
                from_num=from_num,
                to_num=pkt.to,
                packet_id=pkt.id,
                channel=channel_name,
                hops=hops,
                snr=snr,
                rssi=rssi,
                gateway=gateway,
                source=raw.source,
                connector_id=raw.connector_id,
                is_public=is_public,
                encrypted=encrypted,
                decoded_ok=decoded_ok,
                duplicate=False,
                via_mqtt=via_mqtt,
                rx_time=now,
            )
        )
        self.bus.publish(RawPacketReceived(raw=raw))

    # ---------------------------------------------------------------- nodos y enlaces

    def _touch_node(
        self,
        num: int,
        now: float,
        snr: float | None,
        rssi: int | None,
        hops: int | None,
        gateway: str,
        via_mqtt: bool,
    ) -> tuple[NodeRecord, bool]:
        rec = self.state.nodes.get(num)
        is_new = rec is None
        if rec is None:
            rec = NodeRecord.new(num, now)
            rec.heard_via_mqtt_only = int(via_mqtt)
            self.state.nodes[num] = rec
        elif not via_mqtt:
            rec.heard_via_mqtt_only = 0
        if now >= rec.last_heard:
            rec.last_heard = now
            rec.last_snr, rec.last_rssi, rec.last_hops, rec.last_gateway = snr, rssi, hops, gateway
        rec.updated_at = now
        self._dirty.add(num)
        return rec, is_new

    def _direct_link(self, gateway_id: str, from_num: int, snr: float | None, now: float) -> None:
        try:
            gw_num = int(gateway_id.lstrip("!"), 16)
        except ValueError:
            return
        if gw_num == from_num:
            return
        self._link(gw_num, from_num, snr, "direct", now)

    def _link(
        self, receiver: int, transmitter: int, snr: float | None, source: LinkSource, now: float
    ) -> None:
        if receiver in (0, BROADCAST) or transmitter in (0, BROADCAST) or receiver == transmitter:
            return
        if self.state.is_hidden(receiver) or self.state.is_hidden(transmitter):
            return
        self.writer.enqueue(
            "link",
            {
                "node_num": receiver,
                "neighbor_num": transmitter,
                "source": source,
                "snr": snr,
                "ts": now,
            },
        )
        self.bus.publish(
            LinkObserved(
                a=node_id(receiver), b=node_id(transmitter), snr=snr, source=source, link_ts=now
            )
        )

    def _touch_gateway(self, raw: RawPacket, now: float) -> None:
        if not raw.gateway_id:
            return
        gw = self.state.gateways.get(raw.gateway_id)
        if gw is None:
            gw = GatewayInfo(id=raw.gateway_id, last_seen=now)
            self.state.gateways[raw.gateway_id] = gw
        gw.last_seen = now
        gw.packets += 1
        gw.connectors.add(raw.connector_id)
        self._gateway_alive(raw.gateway_id, now)

    @staticmethod
    def _local_only(raw: RawPacket, pkt: mesh_pb2.MeshPacket, from_num: int) -> bool:
        """Paquete propio de la placa que solo vio su cliente: sin `hop_start` (no lo envió el
        enrutador) y llegado por la API del nodo (USB o TCP)."""
        if raw.source not in ("serial", "tcp") or not raw.gateway_id or pkt.hop_start:
            return False
        try:
            return from_num == int(raw.gateway_id.lstrip("!"), 16)
        except ValueError:
            return False

    def _on_local_packet(
        self, raw: RawPacket, pkt: mesh_pb2.MeshPacket, from_num: int, now: float
    ) -> None:
        """De lo local solo interesa la telemetría (batería, voltaje, uso del canal)."""
        self.state.local_packets += 1
        if not pkt.HasField("decoded") or portnum_name(pkt.decoded.portnum) != "TELEMETRY_APP":
            return
        decoded = decode_data(pkt.decoded)
        rec = self.state.nodes.get(from_num)
        if not decoded.ok or rec is None or rec.hidden:
            return
        ctx = _Ctx(
            raw=raw,
            pk=0,
            now=now,
            from_num=from_num,
            to_num=pkt.to,
            data=pkt.decoded,
            gateway=raw.gateway_id or "",
            hops=0,
            via_mqtt=False,
            ignore_node=False,
            is_public=False,
            channel_name=None,
            rec=rec,
        )
        if self._on_telemetry(decoded.obj, ctx):
            self._dirty.add(rec.num)
            self.bus.publish(NodeUpserted(node=rec.public(), changed=("metrics",), is_new=False))

    def _gateway_alive(self, gateway_id: str, now: float) -> None:
        """El nodo gateway está vivo mientras pasan paquetes por él.

        Casi no origina paquetes propios (NodeInfo cada 3 h, telemetría a menudo apagada): sin
        esto figura "tardío" aunque esté recibiendo. Se escribe a lo sumo una vez por minuto.
        """
        try:
            num = int(gateway_id.lstrip("!"), 16)
        except ValueError:
            return
        if num in (0, BROADCAST) or self.state.is_hidden(num):
            return
        rec = self.state.nodes.get(num)
        is_new = rec is None
        if rec is None:
            rec = NodeRecord.new(num, now)
            self.state.nodes[num] = rec
        elif rec.is_gateway and now - rec.last_heard < GATEWAY_TOUCH_S:
            return
        rec.is_gateway = True
        rec.last_heard = max(rec.last_heard, now)
        rec.updated_at = now
        self._dirty.add(num)
        self.bus.publish(NodeUpserted(node=rec.public(), changed=("gateway",), is_new=is_new))

    def mark_dirty(self, num: int) -> None:
        self._dirty.add(num)

    def flush_dirty_nodes(self) -> int:
        """Encola la escritura de los nodos cambiados (se agrupan: una fila por lote)."""
        n = 0
        for num in list(self._dirty):
            rec = self.state.nodes.get(num)
            if rec is not None:
                self.writer.enqueue("node", rec.db_row())
                n += 1
        self._dirty.clear()
        return n

    async def run_dirty_flusher(self, interval_s: float) -> None:
        while True:
            await asyncio.sleep(interval_s)
            self.flush_dirty_nodes()

    # ---------------------------------------------------------------- contenido

    def _apply(self, dec: Decoded, c: _Ctx) -> set[str]:
        match dec.kind:
            case "text":
                return self._on_text(dec, c)
            case "position":
                return self._on_position(dec.obj, c)
            case "user":
                return self._on_user(dec.obj, c)
            case "telemetry":
                return self._on_telemetry(dec.obj, c)
            case "neighborinfo":
                self._on_neighborinfo(dec.obj, c)
            case "traceroute":
                self._on_traceroute(dec.obj, c)
            case "routing":
                err = enum_name(mesh_pb2.Routing.Error, dec.obj.error_reason, "UNKNOWN")
                if dec.obj.WhichOneof("variant") == "error_reason":
                    self.state.routing_errors[err or "UNKNOWN"] += 1
            case "waypoint":
                self._on_waypoint(dec.obj, c)
            case "map_report":
                return self._on_map_report(dec.obj, c)
        return set()

    def _on_text(self, dec: Decoded, c: _Ctx) -> set[str]:
        if not c.is_public or c.to_num != BROADCAST:
            return set()
        text = clip(str(dec.obj), MAX_TEXT) or ""
        is_alert = dec.portnum == "ALERT_APP"
        msg_pk = self.writer.ids.next("messages")
        reply_id = c.data.reply_id or None
        emoji = 1 if c.data.emoji else 0
        self.writer.enqueue(
            "message",
            {
                "pk": msg_pk,
                "packet_pk": c.pk,
                "ts": c.now,
                "from_num": c.from_num,
                "to_num": c.to_num,
                "channel_name": c.channel_name,
                "text": text,
                "reply_id": reply_id,
                "emoji": emoji,
                "is_alert": int(is_alert),
            },
        )
        message = {
            "pk": msg_pk,
            "ts": c.now,
            "from": node_id(c.from_num),
            "from_name": self.state.display_name(c.from_num),
            "channel": c.channel_name,
            "text": text,
            "reply_id": reply_id,
            "emoji": bool(emoji),
            "packet_id": c.raw.packet.id,
        }
        self.bus.publish(MessageAdded(message=message, is_alert=is_alert))
        return set()

    def _on_position(self, pos: mesh_pb2.Position, c: _Ctx) -> set[str]:
        if c.ignore_node or c.rec is None or not c.is_public:
            return set()
        ll = position_latlon(pos)
        if ll is None:
            return set()
        lat, lon = ll
        self._apply_position(
            c.rec,
            c,
            lat,
            lon,
            pos.altitude if pos.HasField("altitude") else None,
            pos.precision_bits or None,
            ground_speed=pos.ground_speed if pos.HasField("ground_speed") else None,
            sats=pos.sats_in_view or None,
        )
        return {"position"}

    def _apply_position(
        self,
        rec: NodeRecord,
        c: _Ctx,
        lat: float,
        lon: float,
        alt: int | None,
        bits: int | None,
        *,
        ground_speed: int | None = None,
        sats: int | None = None,
    ) -> None:
        """Posición nueva de un nodo (paquete de posición o informe de mapa): privacidad,
        historial (si se movió o pasó el intervalo) y aviso en vivo."""
        pcfg = self.cfg.privacy
        if pcfg.position_policy == "degrade" and not rec.is_fixed:
            lat, lon = degrade_position(lat, lon, pcfg.degrade_meters)
            bits = min(bits or 32, bits_for_meters(pcfg.degrade_meters))
        rec.lat, rec.lon, rec.alt, rec.precision_bits, rec.position_ts = lat, lon, alt, bits, c.now
        icfg = self.cfg.ingest
        stored = rec.stored_pos
        if (
            stored is None
            or c.now - stored[0] >= icfg.position_min_interval_s
            or haversine_m(stored[1], stored[2], lat, lon) >= icfg.position_min_move_m
        ):
            self.writer.enqueue(
                "position",
                {
                    "node_num": rec.num,
                    "ts": c.now,
                    "lat": lat,
                    "lon": lon,
                    "alt": alt,
                    "precision_bits": bits,
                    "ground_speed": ground_speed,
                    "sats": sats,
                    "packet_pk": c.pk or None,
                },
            )
            rec.stored_pos = (c.now, lat, lon)
        self.bus.publish(
            PositionAdded(
                node_id=rec.id,
                lat=lat,
                lon=lon,
                alt=alt,
                precision_m=precision_meters(bits),
                pos_ts=c.now,
            )
        )

    def _on_user(self, user: mesh_pb2.User, c: _Ctx) -> set[str]:
        if c.ignore_node or c.rec is None:
            return set()
        rec = c.rec
        rec.long_name = clip(user.long_name, MAX_LONG_NAME) or None
        rec.short_name = clip(user.short_name, MAX_SHORT_NAME) or None
        rec.hw_model = hw_model_name(user.hw_model)
        rec.role = role_name(user.role)
        rec.is_licensed = int(user.is_licensed)
        if user.public_key:
            rec.public_key = bytes(user.public_key)
        return {"user"}

    def _on_telemetry(self, tel: Any, c: _Ctx) -> set[str]:
        if c.ignore_node or c.rec is None:
            return set()
        rec = c.rec
        variant = tel.WhichOneof("variant")
        if variant == "device_metrics":
            vals = device_metrics_values(tel.device_metrics)
            for col in (
                "battery_level",
                "voltage",
                "channel_utilization",
                "air_util_tx",
                "uptime_s",
            ):
                if vals[col] is not None:
                    setattr(rec, col, vals[col])
            rec.metrics_ts = c.now
            self.writer.enqueue("tel_device", {"node_num": rec.num, "ts": c.now, **vals})
            self._emit_telemetry(rec, "device", vals, c.now)
            return {"metrics"}
        if variant == "environment_metrics":
            vals = environment_values(tel.environment_metrics)
            self.writer.enqueue("tel_environment", {"node_num": rec.num, "ts": c.now, **vals})
            env = env_public(vals, c.now)
            if env is not None:
                rec.env = env
            self._emit_telemetry(rec, "environment", vals, c.now)
            return {"env"}
        if variant == "power_metrics":
            vals = power_values(tel.power_metrics)
            self.writer.enqueue("tel_power", {"node_num": rec.num, "ts": c.now, **vals})
            self._emit_telemetry(rec, "power", vals, c.now)
            return set()
        if variant == "local_stats" and c.raw.gateway_id == rec.id:
            gw = self.state.gateways.get(rec.id)
            if gw is not None:
                gw.local_stats = message_to_dict(tel.local_stats)
                gw.local_stats_ts = c.now
        return set()

    def _emit_telemetry(self, rec: NodeRecord, kind: str, vals: dict[str, Any], ts: float) -> None:
        self.bus.publish(TelemetryAdded(node_id=rec.id, kind=kind, values=vals, tel_ts=ts))  # type: ignore[arg-type]

    def _on_neighborinfo(self, ni: mesh_pb2.NeighborInfo, c: _Ctx) -> None:
        if c.ignore_node:
            return
        reporter = ni.node_id or c.from_num
        for n in ni.neighbors:
            if n.node_id:
                self._link(reporter, n.node_id, round(n.snr, 2), "neighborinfo", c.now)

    def _on_traceroute(self, rd: mesh_pb2.RouteDiscovery, c: _Ctx) -> None:
        # Solo las respuestas traen la ruta completa (request_id apunta al pedido).
        if c.ignore_node or not c.data.request_id:
            return
        requester, target = c.to_num, c.from_num
        if requester == BROADCAST:
            return
        route = [n for n in rd.route if n not in (0, BROADCAST)]
        route_back = [n for n in rd.route_back if n not in (0, BROADCAST)]
        snr_t = traceroute_snrs(list(rd.snr_towards))
        snr_b = traceroute_snrs(list(rd.snr_back))
        towards = [requester, *route, target]
        for i in range(len(towards) - 1):
            if i < len(snr_t):
                self._link(towards[i + 1], towards[i], snr_t[i], "traceroute", c.now)
        if snr_b:
            back = [target, *route_back, requester]
            for i in range(len(back) - 1):
                if i < len(snr_b):
                    self._link(back[i + 1], back[i], snr_b[i], "traceroute", c.now)
        row = {
            "packet_pk": c.pk,
            "ts": c.now,
            "from_num": requester,
            "to_num": target,
            "route": orjson.dumps([node_id(n) for n in route]).decode(),
            "snr_towards": orjson.dumps(snr_t).decode(),
            "route_back": orjson.dumps([node_id(n) for n in route_back]).decode(),
            "snr_back": orjson.dumps(snr_b).decode(),
        }
        self.writer.enqueue("traceroute", row)
        self.bus.publish(
            TracerouteAdded(
                traceroute={
                    "ts": c.now,
                    "from": node_id(requester),
                    "to": node_id(target),
                    "route": [node_id(n) for n in route],
                    "snr_towards": snr_t,
                    "route_back": [node_id(n) for n in route_back],
                    "snr_back": snr_b,
                }
            )
        )

    def _on_waypoint(self, wp: mesh_pb2.Waypoint, c: _Ctx) -> None:
        if not c.is_public or not wp.id:
            return
        expire = float(wp.expire) if wp.expire else None
        if expire is not None and expire <= time.time():
            self.writer.enqueue("waypoint_delete", {"id": wp.id})
            self.bus.publish(WaypointChanged(waypoint={"id": wp.id}, deleted=True))
            return
        lat = wp.latitude_i * 1e-7 if wp.HasField("latitude_i") else None
        lon = wp.longitude_i * 1e-7 if wp.HasField("longitude_i") else None
        row = {
            "id": wp.id,
            "from_num": c.from_num,
            "ts": c.now,
            "name": clip(wp.name, 30),
            "description": clip(wp.description, 100),
            "lat": lat,
            "lon": lon,
            "icon": wp.icon or None,
            "expire": expire,
        }
        self.writer.enqueue("waypoint", row)
        self.bus.publish(WaypointChanged(waypoint={**row, "from": node_id(c.from_num)}))

    def _on_map_report(self, mr: Any, c: _Ctx) -> set[str]:
        rec = c.rec
        if rec is None:
            rec, _ = self._touch_node(c.from_num, c.now, None, None, None, c.gateway, False)
            c.rec = rec
        if mr.long_name:
            rec.long_name = clip(mr.long_name, MAX_LONG_NAME)
        if mr.short_name:
            rec.short_name = clip(mr.short_name, MAX_SHORT_NAME)
        rec.role = role_name(mr.role)
        rec.hw_model = hw_model_name(mr.hw_model)
        rec.firmware_version = clip(mr.firmware_version, 40) or rec.firmware_version
        rec.region = enum_name(RegionCode, mr.region)
        rec.modem_preset = enum_name(ModemPreset, mr.modem_preset)
        gw = self.state.gateways.get(rec.id)
        if gw is not None:
            gw.firmware_version = rec.firmware_version
            gw.region = rec.region
            gw.modem_preset = rec.modem_preset
            gw.num_online_local_nodes = mr.num_online_local_nodes
            gw.has_default_channel = mr.has_default_channel
        bits = mr.position_precision or None
        if (
            mr.latitude_i
            and mr.longitude_i
            and not c.ignore_node
            and map_report_wins(rec, bits, c.now)
        ):
            self._apply_position(
                rec, c, mr.latitude_i * 1e-7, mr.longitude_i * 1e-7, mr.altitude or None, bits
            )
            return {"map_report", "position"}
        return {"map_report"}

    # ---------------------------------------------------------------- siembra (USB)

    def seed_nodes(self, gateway_id: str, nodes: list[dict[str, Any]], now: float) -> int:
        """Siembra de nodos desde `interface.nodes` de la librería al conectar por USB o TCP.

        Privacidad: la base del nodo mezcla todos sus canales. Solo se siembran los nodos oídos en
        un canal público (`_channel_name`, que agrega el conector); la posición del propio
        gateway nunca (es la ubicación del dueño: llega por el informe de mapa, con precisión
        reducida), y las demás solo si declaran su precisión, con la misma política que los
        paquetes de posición.
        """
        try:
            gw_num: int | None = int(gateway_id.lstrip("!"), 16)
        except ValueError:
            gw_num = None
        count = 0
        for n in nodes:
            num = n.get("num")
            if not isinstance(num, int) or num in (0, BROADCAST):
                continue
            if not self.state.channel_is_public(n.get("_channel_name")):
                continue
            rec = self.state.nodes.get(num)
            if rec is not None and rec.hidden:
                continue
            via_mqtt = bool(n.get("viaMqtt"))
            if via_mqtt and self.cfg.privacy.ignore_via_mqtt:
                continue
            last_heard = float(n.get("lastHeard") or 0) or None
            if rec is None:
                rec = NodeRecord.new(num, last_heard or now)
                rec.last_heard = last_heard or now
                rec.heard_via_mqtt_only = int(via_mqtt)
                self.state.nodes[num] = rec
            elif last_heard and last_heard > rec.last_heard:
                rec.last_heard = last_heard
            user = n.get("user") or {}
            if user.get("longName"):
                rec.long_name = clip(user["longName"], MAX_LONG_NAME)
            if user.get("shortName"):
                rec.short_name = clip(user["shortName"], MAX_SHORT_NAME)
            if user.get("hwModel"):
                rec.hw_model = str(user["hwModel"])
            rec.role = str(user.get("role") or rec.role or "CLIENT")
            pos = n.get("position") or {}
            lat_i, lon_i = pos.get("latitudeI"), pos.get("longitudeI")
            bits = int(pos.get("precisionBits") or 0)
            if lat_i and lon_i and rec.lat is None and num != gw_num and 0 < bits <= 32:
                lat, lon = lat_i * 1e-7, lon_i * 1e-7
                pcfg = self.cfg.privacy
                if pcfg.position_policy == "degrade" and not rec.is_fixed:
                    lat, lon = degrade_position(lat, lon, pcfg.degrade_meters)
                    bits = min(bits, bits_for_meters(pcfg.degrade_meters))
                rec.lat, rec.lon, rec.precision_bits = lat, lon, bits
                rec.alt = pos.get("altitude")
                rec.position_ts = float(pos.get("time") or 0) or None
            dm = n.get("deviceMetrics") or {}
            for src, dst in (
                ("batteryLevel", "battery_level"),
                ("voltage", "voltage"),
                ("channelUtilization", "channel_utilization"),
                ("airUtilTx", "air_util_tx"),
                ("uptimeSeconds", "uptime_s"),
            ):
                if dm.get(src) is not None and getattr(rec, dst) is None:
                    setattr(rec, dst, dm[src])
            if n.get("snr") is not None and rec.last_snr is None:
                rec.last_snr = float(n["snr"])
            if n.get("hopsAway") is not None and rec.last_hops is None:
                rec.last_hops = int(n["hopsAway"])
            rec.updated_at = now
            self._dirty.add(num)
            self.bus.publish(NodeUpserted(node=rec.public(), changed=("seed",), is_new=False))
            count += 1
        log.info("siembra desde %s: %d nodos", gateway_id, count)
        return count
