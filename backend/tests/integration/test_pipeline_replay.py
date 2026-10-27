"""Reproducción de la red simulada a través del pipeline completo y SQLite (criterio de E2)."""

from __future__ import annotations

import base64
from collections import Counter

import orjson
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from meshtastic.protobuf import mesh_pb2

from meshbox.connectors.replay import read_recording, record_to_packet
from meshbox.models import (
    BROADCAST,
    LinkObserved,
    MessageAdded,
    NodeUpserted,
    PacketProcessed,
    PositionAdded,
    RawPacket,
)

from ..conftest import FIXTURES, Pipe

SIM = FIXTURES / "sim-24h.jsonl"


def _fixture_stats() -> dict[str, object]:
    """Valores de referencia calculados de forma independiente sobre la grabación."""
    unique: set[tuple[int, int]] = set()
    receptions: set[tuple[int, int, str]] = set()
    invalid = 0
    for rec in read_recording(SIM):
        pkt = record_to_packet(rec)
        if pkt is None:
            invalid += 1
            continue
        key = (getattr(pkt, "from"), pkt.id)
        unique.add(key)
        receptions.add((*key, str(rec["gateway_id"])))
    return {"unique": len(unique), "receptions": len(receptions), "invalid": invalid}


async def test_replay_24h_tables(pipe: Pipe) -> None:
    sub = pipe.bus.subscribe("test", maxsize=200_000)
    ref = _fixture_stats()
    await pipe.feed_file(SIM)

    # paquetes y recepciones
    assert await pipe.scalar("SELECT count(*) FROM packets") == ref["unique"]
    assert await pipe.scalar("SELECT count(*) FROM receptions") == ref["receptions"]
    assert pipe.state.invalid_total == ref["invalid"] == 1
    assert pipe.state.duplicates_total == ref["receptions"] - ref["unique"]

    # mensajes: el directo y el del canal privado nunca se guardan
    texts = [r["text"] for r in await pipe.rows("SELECT text FROM messages")]
    assert not any("privado" in t for t in texts)
    assert not any("familia" in t.lower() for t in texts)
    assert any(t.startswith("SOS") for t in texts)
    assert "Mensaje cifrado del canal público" in texts  # cifrado con la clave por defecto
    assert any("<script>" in t for t in texts)  # se guarda tal cual; el frontend lo escapa
    alerts = await pipe.rows("SELECT text FROM messages WHERE is_alert = 1")
    assert len(alerts) == 1
    reactions = await pipe.scalar(
        "SELECT count(*) FROM messages WHERE emoji = 1 AND reply_id IS NOT NULL"
    )
    assert reactions and int(reactions) > 0  # type: ignore[call-overload]

    # canal privado y PKI: solo encabezado
    fam = await pipe.rows("SELECT * FROM packets WHERE channel_name = 'Familia'")
    assert fam and all(r["raw"] is None and r["is_public"] == 0 for r in fam)
    pki = await pipe.rows("SELECT * FROM packets WHERE encrypted = 1 AND decoded_ok = 0")
    assert pki and all(r["raw"] is None for r in pki)
    dm = await pipe.rows(
        "SELECT * FROM packets WHERE portnum = 'TEXT_MESSAGE_APP' AND to_num != :b", b=BROADCAST
    )
    assert dm and all(r["raw"] is None and r["is_public"] == 0 for r in dm)

    # el nodo lejano que entró por MQTT no se agrega (ignore_via_mqtt = true)
    assert await pipe.scalar("SELECT count(*) FROM nodes WHERE num = :n", n=0xDEADBEEF) == 0
    assert 0xDEADBEEF not in pipe.state.nodes

    # nodos, posiciones y telemetría
    n_nodes = await pipe.scalar("SELECT count(*) FROM nodes")
    assert n_nodes == len(pipe.state.nodes) == 27
    pos_packets = await pipe.scalar("SELECT count(*) FROM packets WHERE portnum = 'POSITION_APP'")
    stored = await pipe.scalar("SELECT count(*) FROM positions")
    assert 0 < int(stored) < int(pos_packets)  # type: ignore[call-overload]  # regla de 25 m / 15 min
    named = await pipe.scalar("SELECT count(*) FROM nodes WHERE long_name IS NOT NULL")
    assert named == 27
    enc_tel = await pipe.rows(
        "SELECT battery_level FROM telemetry_device WHERE battery_level BETWEEN 50 AND 55"
    )
    assert len(enc_tel) >= 6  # los seis paquetes de telemetría cifrados se descifraron
    env = await pipe.scalar("SELECT count(*) FROM telemetry_environment")
    assert int(env) > 90  # type: ignore[call-overload]
    power = await pipe.scalar("SELECT count(*) FROM telemetry_power")
    assert int(power) > 40  # type: ignore[call-overload]
    meteo = pipe.state.nodes[0x0B03CBF4]
    assert meteo.env is not None and meteo.env["temperature"] is not None

    # enlaces de las tres fuentes y traceroutes
    sources = {r["source"] for r in await pipe.rows("SELECT DISTINCT source FROM links")}
    assert sources == {"direct", "neighborinfo", "traceroute"}
    assert await pipe.scalar("SELECT count(*) FROM traceroutes") == 4
    tr = (await pipe.rows("SELECT * FROM traceroutes LIMIT 1"))[0]
    assert isinstance(orjson.loads(str(tr["route"])), list)

    # waypoint, informes de mapa del gateway
    assert await pipe.scalar("SELECT name FROM waypoints WHERE id = 4242") == "Punto de encuentro"
    gw = pipe.state.nodes[0xA1B2C3D4]
    assert gw.firmware_version and gw.region == "ANZ" and gw.modem_preset == "MEDIUM_FAST"
    assert pipe.state.gateways["!a1b2c3d4"].num_online_local_nodes

    # contadores de ruteo
    assert pipe.state.routing_errors["MAX_RETRANSMIT"] == 1

    # eventos
    events = []
    while (ev := sub.get_nowait()) is not None:
        events.append(ev)
    kinds = Counter(type(e).__name__ for e in events)
    assert kinds["PacketProcessed"] == ref["receptions"]
    assert kinds["MessageAdded"] == len(texts)
    assert kinds["PositionAdded"] > 0 and kinds["LinkObserved"] > 0 and kinds["NodeUpserted"] > 0
    seqs = [e.seq for e in events]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    msg = next(e for e in events if isinstance(e, MessageAdded))
    assert set(msg.message) >= {
        "pk",
        "ts",
        "from",
        "from_name",
        "channel",
        "text",
        "reply_id",
        "emoji",
    }
    assert all(e.node["id"] != "!deadbeef" for e in events if isinstance(e, NodeUpserted))
    assert any(isinstance(e, PacketProcessed) and e.duplicate for e in events)
    assert any(isinstance(e, PositionAdded) for e in events)
    assert any(isinstance(e, LinkObserved) and e.source == "traceroute" for e in events)


async def test_via_mqtt_allowed_marks_node(pipe: Pipe) -> None:
    pipe.cfg.privacy.ignore_via_mqtt = False
    await pipe.feed_file(SIM)
    rec = pipe.state.nodes[0xDEADBEEF]
    assert rec.heard_via_mqtt_only == 1
    assert (
        await pipe.scalar("SELECT heard_via_mqtt_only FROM nodes WHERE num = :n", n=0xDEADBEEF) == 1
    )


async def test_hidden_node_is_dropped(pipe: Pipe) -> None:
    await pipe.feed_file(SIM, limit=300)
    num = next(iter(pipe.state.nodes))
    pipe.state.nodes[num].hidden = 1
    before = await pipe.scalar("SELECT count(*) FROM packets WHERE from_num = :n", n=num)
    await pipe.feed_file(SIM)
    after = await pipe.scalar("SELECT count(*) FROM packets WHERE from_num = :n", n=num)
    assert before == after
    assert pipe.state.hidden_dropped > 0


async def test_flood_protection(pipe: Pipe) -> None:
    pipe.proc.rate.max_per_min = 10
    pkt = mesh_pb2.MeshPacket()
    setattr(pkt, "from", 0x55555555)
    pkt.to = BROADCAST
    pkt.decoded.portnum = 1
    pkt.decoded.payload = b"spam"
    for i in range(30):
        p = mesh_pb2.MeshPacket()
        p.CopyFrom(pkt)
        p.id = i + 1
        pipe.proc.process(RawPacket("replay", "t", "!a1b2c3d4", "MediumFast", 1000.0 + i, p))
    await pipe.flush()
    assert await pipe.scalar("SELECT count(*) FROM packets WHERE from_num = :n", n=0x55555555) == 10
    assert pipe.state.flood_dropped == 20


async def test_duplicate_after_restart_reuses_pk(pipe: Pipe) -> None:
    """Tras un reinicio (caché vacía) un duplicado no rompe la clave foránea."""
    await pipe.feed_file(SIM, limit=50)
    pipe.proc.dedup = type(pipe.proc.dedup)()  # simula reinicio
    pipe.writer.on_remap = pipe.proc.dedup.remap
    await pipe.feed_file(SIM, limit=50)
    assert pipe.writer.failed_ops == 0
    n_packets = await pipe.scalar("SELECT count(*) FROM packets")
    assert int(n_packets) <= 50  # type: ignore[call-overload]


@settings(
    max_examples=150, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(st.binary(max_size=300))
async def test_random_bytes_never_break_pipeline(pipe: Pipe, blob: bytes) -> None:
    try:
        pkt = mesh_pb2.MeshPacket.FromString(blob)
    except Exception:
        pkt = mesh_pb2.MeshPacket(encrypted=blob)
        setattr(pkt, "from", 0x1000 + len(blob))
    pipe.proc._process(RawPacket("replay", "fuzz", "!a1b2c3d4", "MediumFast", 2000.0, pkt))


@settings(
    max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    st.integers(min_value=0, max_value=0x1FF), st.binary(max_size=200), st.integers(0, 0xFFFFFFFF)
)
async def test_random_payloads_per_portnum(pipe: Pipe, port: int, payload: bytes, to: int) -> None:
    pkt = mesh_pb2.MeshPacket()
    setattr(pkt, "from", 0x2000_0000 + port)
    pkt.to = to
    pkt.id = 1 + (len(payload) << 9) + port
    pkt.decoded.portnum = port
    pkt.decoded.payload = payload
    pkt.hop_start, pkt.hop_limit = 3, 1
    pipe.proc._process(RawPacket("replay", "fuzz", "!a1b2c3d4", "MediumFast", 3000.0, pkt))


def test_fixture_contains_every_relevant_portnum() -> None:
    ports: Counter[str] = Counter()
    for rec in read_recording(SIM):
        pkt = record_to_packet(rec)
        if pkt is not None and pkt.HasField("decoded"):
            from meshbox.pipeline.decode import portnum_name

            ports[portnum_name(pkt.decoded.portnum)] += 1
    for p in ("TEXT_MESSAGE_APP", "POSITION_APP", "NODEINFO_APP", "TELEMETRY_APP", "NEIGHBORINFO_APP",
              "TRACEROUTE_APP", "ROUTING_APP", "WAYPOINT_APP", "MAP_REPORT_APP", "ALERT_APP",
              "RANGE_TEST_APP", "STORE_FORWARD_APP", "PAXCOUNTER_APP", "DETECTION_SENSOR_APP"):  # fmt: skip
        assert ports[p] > 0, p


@pytest.mark.parametrize("line", [b"", b"{}", b'{"packet_b64": "!!"}'])
def test_bad_records_are_skipped(tmp_path, line: bytes) -> None:  # type: ignore[no-untyped-def]
    f = tmp_path / "x.jsonl"
    f.write_bytes(
        line + b"\n" + orjson.dumps({"packet_b64": base64.b64encode(b"").decode()}) + b"\n"
    )
    recs = list(read_recording(f))
    for r in recs:
        record_to_packet(r)  # nunca lanza


async def test_state_reload_from_db_matches_memory(pipe: Pipe) -> None:
    """Lo que se recarga al reiniciar el servicio coincide con el estado en memoria."""
    from meshbox.state import MeshState

    await pipe.feed_file(SIM)
    fresh = MeshState()
    await pipe.db.read(lambda c: fresh.load_from_db(c, pipe.secrets.get))
    assert set(fresh.nodes) == set(pipe.state.nodes)
    volatile = {"is_gateway", "is_infra"}  # el gateway se reconstruye y se completa con tráfico
    for num, rec in pipe.state.nodes.items():
        other = fresh.nodes[num]
        mine = {k: v for k, v in rec.public().items() if k not in volatile}
        assert {k: v for k, v in other.public().items() if k not in volatile} == mine, num
        assert not other.is_gateway or rec.is_gateway, num
        assert other.stored_pos is not None or rec.stored_pos is None
    assert any(r.is_gateway for r in fresh.nodes.values())
    assert [c.name for c in fresh.channels] == ["MediumFast", "Familia"]
    assert fresh.channel_is_public("MediumFast") and not fresh.channel_is_public("Familia")
    # El sitio no dice "sin paquetes todavía" después de reiniciar.
    assert fresh.last_packet_at == max(r.last_heard for r in pipe.state.nodes.values())


def test_replay_shift_moves_reply_and_request_ids() -> None:
    from meshtastic.protobuf import mesh_pb2

    from meshbox.connectors.replay import shift_ids

    pkt = mesh_pb2.MeshPacket()
    pkt.id = 0xFFFFFFF0
    pkt.decoded.reply_id = 100
    pkt.decoded.request_id = 200
    shift_ids(pkt, 0x20)
    assert (pkt.id, pkt.decoded.reply_id, pkt.decoded.request_id) == (0x10, 0x84, 0xE8)
    plain = mesh_pb2.MeshPacket()
    plain.id = 5
    plain.encrypted = b"x"
    shift_ids(plain, 1)
    assert plain.id == 6 and plain.encrypted == b"x"


async def test_gateway_node_alive_by_traffic(pipe: Pipe) -> None:
    """El gateway figura activo por el tráfico que pasa por él, no solo por sus paquetes."""
    from meshtastic.protobuf import mesh_pb2, portnums_pb2

    from meshbox.models import BROADCAST, RawPacket

    gw, gw_num, t0 = "!0a0b0c0d", 0x0A0B0C0D, 1_792_500_000.0

    def feed(pid: int, t: float) -> None:
        pkt = mesh_pb2.MeshPacket()
        setattr(pkt, "from", 0x11112222)
        pkt.to, pkt.id = BROADCAST, pid
        pkt.decoded.portnum = portnums_pb2.PortNum.TEXT_MESSAGE_APP
        pkt.decoded.payload = b"hola"
        pipe.proc.process(RawPacket("mqtt", "mqtt-local", gw, "MediumFast", t, pkt))

    feed(1, t0)
    rec = pipe.state.nodes[gw_num]
    assert rec.is_gateway and rec.last_heard == t0
    public = rec.public()
    assert public["is_gateway"] and public["is_infra"] and public["snr"] is None
    feed(2, t0 + 30)  # dentro del minuto no se reescribe
    assert rec.last_heard == t0
    feed(3, t0 + 90)
    assert rec.last_heard == t0 + 90
    await pipe.flush()
    assert await pipe.scalar("SELECT last_heard FROM nodes WHERE num = :n", n=gw_num) == t0 + 90


async def test_seed_nodes_respects_channel_privacy(pipe: Pipe) -> None:
    """La siembra por USB/TCP no publica nodos de canales privados ni la casa del gateway."""
    gw = "!0a0b0c0d"
    pos13 = {"latitudeI": -408158208, "longitudeI": -629932032, "precisionBits": 13}
    exact = {"latitudeI": -408135000, "longitudeI": -629967000}  # sin precisión declarada
    nodes = [
        {"num": 0x0A0B0C0D, "user": {"longName": "Gateway"}, "position": exact, "_channel_name": "MediumFast"},
        {"num": 0x0000AAA1, "user": {"longName": "Público"}, "position": pos13, "_channel_name": "MediumFast"},
        {"num": 0x0000AAA2, "user": {"longName": "Privado"}, "position": pos13, "_channel_name": "Familia"},
        {"num": 0x0000AAA3, "user": {"longName": "Sin precisión"}, "position": exact, "_channel_name": "MediumFast"},
        {"num": 0x0000AAA4, "user": {"longName": "Canal desconocido"}, "_channel_name": None},
    ]  # fmt: skip
    pipe.proc.seed_nodes(gw, nodes, 1_792_500_000.0)
    state = pipe.state.nodes
    assert 0x0000AAA2 not in state and 0x0000AAA4 not in state
    assert state[0x0A0B0C0D].long_name == "Gateway" and state[0x0A0B0C0D].lat is None
    assert state[0x0000AAA1].lat is not None and state[0x0000AAA1].precision_bits == 13
    assert state[0x0000AAA3].long_name == "Sin precisión" and state[0x0000AAA3].lat is None


async def test_local_only_packets_are_not_mesh_traffic(pipe: Pipe) -> None:
    """La telemetría que la placa manda solo a su cliente actualiza la batería pero no cuenta."""
    from meshtastic.protobuf import mesh_pb2, portnums_pb2, telemetry_pb2

    from meshbox.models import BROADCAST, RawPacket

    gw, gw_num, t0 = "!0a0b0c0d", 0x0A0B0C0D, 1_792_500_000.0
    before = int(await pipe.scalar("SELECT count(*) FROM packets"))  # type: ignore[call-overload]

    def telemetry(pid: int, battery: int, hop_start: int, source: str) -> RawPacket:
        tel = telemetry_pb2.Telemetry(time=int(t0))
        tel.device_metrics.battery_level = battery
        tel.device_metrics.voltage = 3.9
        pkt = mesh_pb2.MeshPacket()
        setattr(pkt, "from", gw_num)
        pkt.to, pkt.id, pkt.hop_start, pkt.hop_limit = BROADCAST, pid, hop_start, 7
        pkt.decoded.portnum = portnums_pb2.PortNum.TELEMETRY_APP
        pkt.decoded.payload = tel.SerializeToString()
        return RawPacket(source, "usb", gw, "MediumFast", t0 + pid, pkt)  # type: ignore[arg-type]

    pipe.proc.process(telemetry(1, 55, 0, "serial"))  # local: no pasó por el aire
    assert pipe.state.nodes[gw_num].battery_level == 55
    assert pipe.state.local_packets == 1
    await pipe.flush()
    assert int(await pipe.scalar("SELECT count(*) FROM packets")) == before  # type: ignore[call-overload]
    assert (
        await pipe.scalar("SELECT count(*) FROM telemetry_device WHERE node_num = :n", n=gw_num)
        == 1
    )
    pipe.proc.process(telemetry(2, 54, 7, "serial"))  # la misma telemetría, pero transmitida
    await pipe.flush()
    assert int(await pipe.scalar("SELECT count(*) FROM packets")) == before + 1  # type: ignore[call-overload]


async def test_map_report_updates_position_without_spoiling_exact(pipe: Pipe) -> None:
    """El informe de mapa actualiza la posición, pero no pisa la exacta reciente (ADR 0011)."""
    from meshtastic.protobuf import mesh_pb2, mqtt_pb2, portnums_pb2

    from meshbox.models import BROADCAST, RawPacket

    num, nid, t0 = 0x11223344, "!11223344", 1_792_500_000.0
    seq = iter(range(100, 200))

    def packet(portnum: int, payload: bytes, at: float, source: str) -> RawPacket:
        pkt = mesh_pb2.MeshPacket()
        setattr(pkt, "from", num)
        pkt.to, pkt.id, pkt.hop_start, pkt.hop_limit = BROADCAST, next(seq), 3, 3
        pkt.decoded.portnum = portnum
        pkt.decoded.payload = payload
        gw = nid if source == "mqtt" else "!0a0b0c0d"
        return RawPacket(source, "c", gw, "MediumFast", at, pkt)  # type: ignore[arg-type]

    def report(lat: float, lon: float, bits: int, at: float) -> RawPacket:
        mr = mqtt_pb2.MapReport(long_name="Nodo", short_name="ND", position_precision=bits,
                                latitude_i=int(lat * 1e7), longitude_i=int(lon * 1e7))  # fmt: skip
        return packet(portnums_pb2.PortNum.MAP_REPORT_APP, mr.SerializeToString(), at, "mqtt")

    def position(lat: float, lon: float, bits: int, at: float) -> RawPacket:
        pos = mesh_pb2.Position(latitude_i=int(lat * 1e7), longitude_i=int(lon * 1e7),
                                precision_bits=bits)  # fmt: skip
        return packet(portnums_pb2.PortNum.POSITION_APP, pos.SerializeToString(), at, "serial")

    def where() -> tuple[float | None, float | None, int | None]:
        rec = pipe.state.nodes[num]
        return (
            round(rec.lat, 4) if rec.lat else None,
            round(rec.lon, 4) if rec.lon else None,
            rec.precision_bits,
        )

    pipe.proc.process(report(-40.80, -62.98, 14, t0))  # sin posición: la toma
    assert where() == (-40.8, -62.98, 14)
    pipe.proc.process(report(-40.81, -62.99, 16, t0 + 3600))  # más precisa: la reemplaza
    assert where() == (-40.81, -62.99, 16)
    pipe.proc.process(position(-40.8135, -62.9967, 32, t0 + 3700))  # exacta por radio
    assert where() == (-40.8135, -62.9967, 32)
    pipe.proc.process(report(-40.81, -62.99, 16, t0 + 7200))  # aproximada y reciente: no pisa
    assert where() == (-40.8135, -62.9967, 32)
    pipe.proc.process(report(-40.82, -63.0, 16, t0 + 3700 + 86_401))  # exacta de hace un día
    assert where() == (-40.82, -63.0, 16)
    await pipe.flush()
    rows = await pipe.rows(
        "SELECT precision_bits FROM positions WHERE node_num = :n ORDER BY ts", n=num
    )
    assert [r["precision_bits"] for r in rows] == [14, 16, 32, 16]
