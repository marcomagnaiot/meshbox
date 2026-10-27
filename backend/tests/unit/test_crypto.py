from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from meshtastic.protobuf import mesh_pb2, portnums_pb2, telemetry_pb2
from meshtastic.util import generate_channel_hash

from meshbox.pipeline.crypto import (
    DEFAULT_PSK,
    ChannelKey,
    aes_ctr,
    channel_hash,
    decode_psk,
    encrypt_packet,
    expand_psk,
    make_nonce,
    parse_data,
    try_decrypt,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_expand_psk_short_keys() -> None:
    assert expand_psk(b"") == b""
    assert expand_psk(b"\x00") == b""  # índice 0: sin cifrado
    assert expand_psk(b"\x01") == DEFAULT_PSK
    k2 = expand_psk(b"\x02")
    assert k2[:-1] == DEFAULT_PSK[:-1] and k2[-1] == DEFAULT_PSK[-1] + 1
    k10 = expand_psk(b"\x0a")
    assert k10[-1] == (DEFAULT_PSK[-1] + 9) & 0xFF


def test_expand_psk_padding() -> None:
    assert expand_psk(b"abc") == b"abc" + bytes(13)
    assert len(expand_psk(bytes(16))) == 16
    assert expand_psk(bytes(range(20))) == bytes(range(20)) + bytes(12)
    assert len(expand_psk(bytes(32))) == 32


@pytest.mark.parametrize(
    "name", ["LongFast", "MediumFast", "ShortFast", "LongSlow", "VLongSlow", "Familia"]
)
@pytest.mark.parametrize("psk", ["AQ==", "Ag==", "q0Kn3Ys7mQ5rUjXp2bF9tA=="])
def test_channel_hash_matches_reference_library(name: str, psk: str) -> None:
    assert channel_hash(name, decode_psk(psk)) == generate_channel_hash(name, psk)


def test_known_hashes() -> None:
    assert channel_hash("LongFast", b"\x01") == 8
    assert channel_hash("MediumFast", b"\x01") == 31


def test_nonce_layout() -> None:
    n = make_nonce(0x11223344, 0xAABBCCDD)
    assert len(n) == 16
    assert n[:8] == bytes.fromhex("4433221100000000")
    assert n[8:12] == bytes.fromhex("ddccbbaa")
    assert n[12:] == bytes(4)


def test_decode_psk_urlsafe_and_errors() -> None:
    assert decode_psk("AQ") == b"\x01"
    assert decode_psk("q0Kn3Ys7mQ5rUjXp2bF9tA") == base64.b64decode("q0Kn3Ys7mQ5rUjXp2bF9tA==")
    with pytest.raises(ValueError):
        decode_psk("***no-base64***")
    with pytest.raises(ValueError):
        decode_psk(base64.b64encode(bytes(40)).decode())


def _packet(from_num: int = 0x12345678, pid: int = 0xCAFEBABE) -> mesh_pb2.MeshPacket:
    pkt = mesh_pb2.MeshPacket()
    setattr(pkt, "from", from_num)
    pkt.to = 0xFFFFFFFF
    pkt.id = pid
    return pkt


def test_roundtrip_and_hash_selection() -> None:
    ck = ChannelKey.from_psk("MediumFast", b"\x01")
    other = ChannelKey.from_psk("Familia", decode_psk("q0Kn3Ys7mQ5rUjXp2bF9tA=="))
    data = mesh_pb2.Data(portnum=portnums_pb2.PortNum.TEXT_MESSAGE_APP, payload=b"hola")
    pkt = _packet()
    encrypt_packet(pkt, data, ck)
    assert pkt.channel == 31
    assert pkt.encrypted != data.SerializeToString()
    res = try_decrypt(pkt, [other, ck])
    assert res is not None
    got, used = res
    assert used.name == "MediumFast"
    assert got.payload == b"hola"


def test_wrong_key_is_rejected() -> None:
    ck = ChannelKey.from_psk("MediumFast", b"\x01")
    wrong = ChannelKey(name="MediumFast", key=bytes(16), hash=ck.hash)
    data = mesh_pb2.Data(portnum=portnums_pb2.PortNum.TEXT_MESSAGE_APP, payload=b"x" * 40)
    pkt = _packet()
    encrypt_packet(pkt, data, ck)
    assert try_decrypt(pkt, [wrong]) is None


def test_pki_not_attempted() -> None:
    ck = ChannelKey.from_psk("MediumFast", b"\x01")
    pkt = _packet()
    pkt.pki_encrypted = True
    pkt.encrypted = b"\x00" * 20
    pkt.channel = ck.hash
    assert try_decrypt(pkt, [ck]) is None


def test_parse_data_rejects_unknown_portnum() -> None:
    assert parse_data(mesh_pb2.Data(portnum=0, payload=b"x").SerializeToString()) is None
    assert parse_data(b"\xff\xff\xff") is None


def test_unencrypted_channel_passthrough() -> None:
    assert aes_ctr(b"", 1, 2, b"abc") == b"abc"


def test_real_firmware_vectors() -> None:
    """Paquetes cifrados por firmware real (broker público, solo telemetría de dispositivo).

    Verifica expansión de clave, hash de canal, nonce y AES-CTR contra el firmware (10.2).
    """
    vectors = json.loads((FIXTURES / "real-vectors.json").read_text())
    assert len(vectors) >= 3
    for v in vectors:
        pkt = mesh_pb2.MeshPacket.FromString(base64.b64decode(v["packet_b64"]))
        ck = ChannelKey.from_psk(v["channel"], b"\x01")
        res = try_decrypt(pkt, [ck])
        assert res is not None, v
        data, _ = res
        assert portnums_pb2.PortNum.Name(data.portnum) == v["expect_portnum"]
        tel = telemetry_pb2.Telemetry.FromString(data.payload)
        assert tel.WhichOneof("variant") == v["expect_variant"]
