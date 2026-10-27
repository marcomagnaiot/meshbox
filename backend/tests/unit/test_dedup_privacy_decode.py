from __future__ import annotations

import pytest
from meshtastic.protobuf import mesh_pb2, mqtt_pb2, portnums_pb2, telemetry_pb2

from meshbox.models import BROADCAST
from meshbox.pipeline.decode import (
    clip,
    decode_data,
    device_metrics_values,
    position_latlon,
    precision_meters,
    traceroute_snrs,
)
from meshbox.pipeline.dedup import Deduplicator, NodeRateLimiter
from meshbox.pipeline.privacy import (
    bits_for_meters,
    degrade_position,
    entered_via_mqtt,
    haversine_m,
    pre_filter,
)

PortNum = portnums_pb2.PortNum


# --------------------------------------------------------------------------- deduplicación


def test_dedup_basic_and_ttl() -> None:
    d = Deduplicator(max_entries=10, ttl_s=100)
    assert d.lookup(1, 2, 0) is None
    d.add(1, 2, pk=55, now=0)
    assert d.lookup(1, 2, 50) == 55
    assert d.lookup(1, 2, 101) is None  # vencido
    assert d.lookup(1, 2, 102) is None


def test_dedup_lru_eviction_and_expire() -> None:
    d = Deduplicator(max_entries=3, ttl_s=1000)
    for i in range(5):
        d.add(i, i, pk=i, now=i)
    assert len(d) == 3
    assert d.lookup(0, 0, 10) is None
    assert d.lookup(4, 4, 10) == 4
    d2 = Deduplicator(ttl_s=10)
    d2.add(1, 1, 1, now=0)
    d2.add(2, 2, 2, now=5)
    assert d2.expire(now=12) == 1
    assert len(d2) == 1


def test_dedup_remap() -> None:
    d = Deduplicator()
    d.add(7, 8, pk=100, now=0)
    d.remap(100, 42)
    assert d.lookup(7, 8, 1) == 42


def test_rate_limiter() -> None:
    r = NodeRateLimiter(max_per_min=3)
    assert all(r.allow(9, 0.0) for _ in range(3))
    assert not r.allow(9, 1.0)
    assert r.first_drop_in_window(9)
    assert not r.allow(9, 2.0)
    assert not r.first_drop_in_window(9)
    assert r.allow(9, 61.0)  # ventana nueva
    assert r.allow(10, 1.0)  # otro nodo
    assert r.dropped_total == 2


# --------------------------------------------------------------------------- privacidad

CASES = [
    # to, portnum, canal público, decodificado → (header_only, process, public)
    (BROADCAST, "TEXT_MESSAGE_APP", True, True, (False, True, True)),
    (BROADCAST, "TEXT_MESSAGE_APP", False, True, (True, False, False)),
    (0x1234, "TEXT_MESSAGE_APP", True, True, (True, False, False)),
    (0x1234, "TRACEROUTE_APP", True, True, (True, True, False)),
    (0x1234, "ROUTING_APP", True, True, (True, True, False)),
    (0x1234, "TRACEROUTE_APP", False, True, (True, False, False)),
    (BROADCAST, "POSITION_APP", True, True, (False, True, True)),
    (BROADCAST, None, True, False, (True, False, False)),
    (BROADCAST, "MAP_REPORT_APP", False, True, (False, True, False)),
]


@pytest.mark.parametrize(("to", "port", "public", "decoded", "expected"), CASES)
def test_pre_filter_table(
    to: int, port: str | None, public: bool, decoded: bool, expected: tuple[bool, bool, bool]
) -> None:
    d = pre_filter(to_num=to, portnum=port, channel_public=public, decoded=decoded)
    assert (d.header_only, d.process, d.public) == expected


def test_entered_via_mqtt() -> None:
    p = mesh_pb2.MeshPacket()
    assert not entered_via_mqtt(p)
    p.via_mqtt = True
    assert entered_via_mqtt(p)
    q = mesh_pb2.MeshPacket(
        transport_mechanism=mesh_pb2.MeshPacket.TransportMechanism.TRANSPORT_MQTT
    )
    assert entered_via_mqtt(q)


def test_degrade_position_snaps_to_grid() -> None:
    lat, lon = degrade_position(-40.81234, -62.99876, 500)
    assert haversine_m(lat, lon, -40.81234, -62.99876) < 500
    # el centro de la celda es estable y los puntos cercanos al centro caen en la misma celda
    assert degrade_position(lat, lon, 500) == (lat, lon)
    assert degrade_position(lat + 0.0001, lon - 0.0001, 500) == (lat, lon)
    # celdas distintas para puntos lejanos
    assert degrade_position(lat + 0.02, lon, 500) != (lat, lon)


def test_bits_for_meters_inverse() -> None:
    for bits in range(10, 20):
        m = precision_meters(bits)
        assert m is not None
        assert bits_for_meters(m) == bits


def test_haversine() -> None:
    # Viedma - Carmen de Patagones ~ 2 km
    d = haversine_m(-40.8135, -62.9967, -40.7980, -62.9817)
    assert 1500 < d < 2500


# --------------------------------------------------------------------------- decodificación


def test_precision_meters() -> None:
    assert precision_meters(None) is None
    assert precision_meters(0) is None
    assert precision_meters(32) is None
    assert precision_meters(10) == 23300.0
    assert precision_meters(13) == pytest.approx(2912.5)
    assert precision_meters(19) == pytest.approx(45.5, abs=0.1)


def test_position_latlon_discards_zero() -> None:
    assert position_latlon(mesh_pb2.Position()) is None
    assert position_latlon(mesh_pb2.Position(latitude_i=0, longitude_i=0)) is None
    assert position_latlon(
        mesh_pb2.Position(latitude_i=-408135000, longitude_i=-629967000)
    ) == pytest.approx((-40.8135, -62.9967))
    assert position_latlon(mesh_pb2.Position(latitude_i=1_900_000_000, longitude_i=0)) is None


def test_decode_each_portnum() -> None:
    cases = {
        PortNum.TEXT_MESSAGE_APP: ("text", "hola ñ".encode()),
        PortNum.POSITION_APP: (
            "position",
            mesh_pb2.Position(latitude_i=1, longitude_i=2).SerializeToString(),
        ),
        PortNum.NODEINFO_APP: ("user", mesh_pb2.User(long_name="x").SerializeToString()),
        PortNum.TELEMETRY_APP: (
            "telemetry",
            telemetry_pb2.Telemetry(
                device_metrics=telemetry_pb2.DeviceMetrics(battery_level=5)
            ).SerializeToString(),
        ),
        PortNum.NEIGHBORINFO_APP: (
            "neighborinfo",
            mesh_pb2.NeighborInfo(node_id=1).SerializeToString(),
        ),
        PortNum.TRACEROUTE_APP: (
            "traceroute",
            mesh_pb2.RouteDiscovery(route=[1]).SerializeToString(),
        ),
        PortNum.ROUTING_APP: ("routing", mesh_pb2.Routing(error_reason=1).SerializeToString()),
        PortNum.WAYPOINT_APP: ("waypoint", mesh_pb2.Waypoint(id=3).SerializeToString()),
        PortNum.MAP_REPORT_APP: (
            "map_report",
            mqtt_pb2.MapReport(long_name="gw").SerializeToString(),
        ),
        PortNum.PAXCOUNTER_APP: ("raw", b"\x08\x01"),
        PortNum.ALERT_APP: ("text", b"alerta"),
    }
    for port, (kind, payload) in cases.items():
        dec = decode_data(mesh_pb2.Data(portnum=port, payload=payload))
        assert dec.ok, (port, dec.error)
        assert dec.kind == kind, port


def test_decode_corrupt_payload_does_not_raise() -> None:
    dec = decode_data(mesh_pb2.Data(portnum=PortNum.POSITION_APP, payload=b"\xff\xff\xff\xff"))
    assert not dec.ok
    assert dec.error


def test_text_invalid_utf8_replaced() -> None:
    dec = decode_data(mesh_pb2.Data(portnum=PortNum.TEXT_MESSAGE_APP, payload=b"ok\xff"))
    assert dec.ok and dec.obj == "ok�"


def test_device_metrics_optional_fields() -> None:
    vals = device_metrics_values(telemetry_pb2.DeviceMetrics(voltage=4.123456))
    assert vals["battery_level"] is None
    assert vals["voltage"] == pytest.approx(4.123, abs=1e-3)


def test_traceroute_snr_scaling() -> None:
    assert traceroute_snrs([40, -128, -10]) == [10.0, None, -2.5]


def test_clip() -> None:
    assert clip("a\x00b" * 100, 5) == "abab" + "a"
    assert clip(None, 3) is None
