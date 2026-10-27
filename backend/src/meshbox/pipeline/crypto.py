"""Descifrado de canales Meshtastic (sección 10.2).

Reproduce el firmware (`Channels::getKey`, `Channels::generateHash`, `CryptoEngine::initNonce`):

- PSK de 1 byte: 0 = sin cifrado; n >= 1 = clave por defecto con el último byte + (n - 1).
- Claves de 2 a 15 bytes se rellenan con ceros a 16; de 17 a 31, a 32.
- 16 bytes → AES-128-CTR; 32 bytes → AES-256-CTR.
- Nonce: id del paquete (64 bits LE) + from (32 bits LE) + 4 bytes en cero.
- Hash de canal: XOR de los bytes del nombre XOR el XOR de los bytes de la clave expandida.
"""

from __future__ import annotations

import base64
import binascii
import struct
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from google.protobuf.message import DecodeError
from meshtastic.protobuf import mesh_pb2, portnums_pb2

DEFAULT_PSK = base64.b64decode("1PG7OiApB1nwvP+rz05pAQ==")
_VALID_PORTNUMS = frozenset(v.number for v in portnums_pb2.PortNum.DESCRIPTOR.values) - {0}


def decode_psk(text: str) -> bytes:
    """Clave en base64 (estándar o url-safe, como la muestra la app). ValueError si no es válida."""
    s = text.strip().replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)
    try:
        raw = base64.b64decode(s, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ValueError("la clave no es base64 válido") from e
    if len(raw) > 32:
        raise ValueError("la clave tiene más de 32 bytes")
    return raw


def expand_psk(psk: bytes) -> bytes:
    """Clave efectiva. Vacía = canal sin cifrado."""
    if len(psk) == 0:
        return b""
    if len(psk) == 1:
        index = psk[0]
        if index == 0:
            return b""
        key = bytearray(DEFAULT_PSK)
        key[-1] = (key[-1] + index - 1) & 0xFF
        return bytes(key)
    if len(psk) < 16:
        return psk + bytes(16 - len(psk))
    if 16 < len(psk) < 32:
        return psk + bytes(32 - len(psk))
    return psk


def xor_hash(data: bytes) -> int:
    h = 0
    for b in data:
        h ^= b
    return h


def channel_hash(name: str, psk: bytes) -> int:
    return xor_hash(name.encode("utf-8")) ^ xor_hash(expand_psk(psk))


def make_nonce(packet_id: int, from_num: int) -> bytes:
    return struct.pack("<QI", packet_id & 0xFFFFFFFFFFFFFFFF, from_num & 0xFFFFFFFF) + bytes(4)


def aes_ctr(key: bytes, packet_id: int, from_num: int, data: bytes) -> bytes:
    """Cifra o descifra (CTR es simétrico). Con clave vacía devuelve los datos tal cual."""
    if not key:
        return data
    if len(key) not in (16, 32):
        raise ValueError("la clave expandida debe tener 16 o 32 bytes")
    cipher = Cipher(algorithms.AES(key), modes.CTR(make_nonce(packet_id, from_num)))
    ctx = cipher.decryptor()
    return ctx.update(data) + ctx.finalize()


@dataclass(frozen=True, slots=True)
class ChannelKey:
    name: str
    key: bytes  # expandida
    hash: int
    is_public: bool = False

    @classmethod
    def from_psk(cls, name: str, psk: bytes, is_public: bool = False) -> ChannelKey:
        key = expand_psk(psk)
        return cls(
            name=name, key=key, hash=xor_hash(name.encode()) ^ xor_hash(key), is_public=is_public
        )


def parse_data(plaintext: bytes) -> mesh_pb2.Data | None:
    """Interpreta el texto plano como `Data`; None si no corresponde (clave equivocada).

    Igual que el firmware: si no decodifica o el portnum es UNKNOWN_APP (0) o desconocido,
    se considera que la clave no era la correcta.
    """
    data = mesh_pb2.Data()
    try:
        data.ParseFromString(plaintext)
    except (DecodeError, ValueError):
        return None
    if data.portnum not in _VALID_PORTNUMS:
        return None
    return data


def try_decrypt(
    packet: mesh_pb2.MeshPacket, keys: list[ChannelKey]
) -> tuple[mesh_pb2.Data, ChannelKey] | None:
    """Prueba las claves cuyo hash coincide con `packet.channel`."""
    if packet.pki_encrypted or not packet.encrypted:
        return None
    from_num = getattr(packet, "from")
    for ck in keys:
        if ck.hash != packet.channel:
            continue
        data = parse_data(aes_ctr(ck.key, packet.id, from_num, packet.encrypted))
        if data is not None:
            return data, ck
    return None


def encrypt_packet(packet: mesh_pb2.MeshPacket, data: mesh_pb2.Data, ck: ChannelKey) -> None:
    """Rellena `packet.encrypted` y `packet.channel` (hash) como lo haría el firmware.

    Se usa en el generador de grabaciones y en pruebas.
    """
    plaintext = data.SerializeToString()
    packet.encrypted = aes_ctr(ck.key, packet.id, getattr(packet, "from"), plaintext)
    packet.channel = ck.hash
