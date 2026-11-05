"""Ficha pública «Cómo conectarse»: datos de radio de la red y enlace del canal para la app.

El enlace es el mismo que arma la app de Meshtastic al compartir un canal
(`https://meshtastic.org/e/#` más un ChannelSet en base64url): el canal primario con la clave de
fábrica y la configuración LoRa (región, preset, slot y saltos). Si la red usa otra clave, el
enlace no se publica: la clave no sale nunca del panel.
"""

from __future__ import annotations

import base64
from typing import Any

from .settings import JoinSettings

# Nombre que muestran las apps para el canal de fábrica de cada preset.
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
}


def channel_url(j: JoinSettings) -> str | None:
    if not (j.region and j.preset and j.default_key):
        return None
    try:
        from meshtastic.protobuf import apponly_pb2, channel_pb2, config_pb2
    except ImportError:  # pragma: no cover - meshtastic es dependencia del servidor
        return None
    lora = config_pb2.Config.LoRaConfig
    cs = apponly_pb2.ChannelSet()
    ch = channel_pb2.ChannelSettings(psk=b"\x01", name=j.channel_name)
    cs.settings.append(ch)
    cs.lora_config.use_preset = True
    cs.lora_config.modem_preset = lora.ModemPreset.Value(j.preset)
    cs.lora_config.region = lora.RegionCode.Value(j.region)
    cs.lora_config.hop_limit = j.hop_limit
    cs.lora_config.channel_num = j.slot
    cs.lora_config.tx_enabled = True
    raw = base64.urlsafe_b64encode(cs.SerializeToString()).decode().rstrip("=")
    return f"https://meshtastic.org/e/#{raw}"


def join_payload(j: JoinSettings) -> dict[str, Any] | None:
    """Lo que ve el público; None si la ficha está apagada o sin región ni preset."""
    if not j.enabled or not (j.region or j.preset):
        return None
    return {
        "region": j.region,
        "preset": j.preset,
        "preset_name": PRESET_NAMES.get(j.preset, j.preset),
        "slot": j.slot,
        "frequency_mhz": j.frequency_mhz,
        "channel_name": j.channel_name,
        "default_key": j.default_key,
        "role": j.role,
        "hop_limit": j.hop_limit,
        "contact": j.contact,
        "notes_md": j.notes_md,
        "url": channel_url(j),
    }
