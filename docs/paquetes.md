# Paquetes Meshtastic: lo que llega y cómo se interpreta

Referencia de los mensajes que procesa meshbox, con los nombres reales de la librería `meshtastic` 2.7.11 (protobuf 7.36) y lo observado en grabaciones. Para regenerar el resumen de una grabación:

```powershell
uv run python scripts/gen-paquetes-doc.py "data/rec/*.jsonl"
uv run meshbox inspect data/rec/archivo.jsonl            # cada paquete decodificado
```

## Envoltorio MQTT

Tópico `<root>/2/e/<canal>/<!gateway>` (por ejemplo `msh/AR/mizona/2/e/MediumFast/!a1b2c3d4`). El cuerpo es un `ServiceEnvelope` protobuf: `packet` (`MeshPacket`), `channel_id` (nombre del canal) y `gateway_id`. Los informes de mapa llegan en `<root>/2/map/`. La salida JSON del firmware no se usa (obsoleta).

## `MeshPacket`

| Campo | Uso |
|---|---|
| `from`, `to`, `id` | `from` es palabra reservada en Python: `getattr(pkt, "from")`. Id de nodo `!xxxxxxxx`. Broadcast: `to = 0xFFFFFFFF`. Deduplicación por `(from, id)`. |
| `decoded` / `encrypted` | Uno u otro. Con `mqtt.encryption_enabled false` llega `decoded`; los mensajes que el gateway no pudo descifrar no se publican. |
| `channel` | Índice si está decodificado; hash (1 byte) si está cifrado. |
| `hop_start`, `hop_limit` | Saltos recorridos = `hop_start - hop_limit` (si `hop_start > 0`). 0 = recepción directa → enlace `direct`. |
| `rx_snr`, `rx_rssi`, `rx_time` | Del gateway. 0 y 0 = desconocido (paquetes propios del gateway). Se usa la hora del servidor, no `rx_time`. |
| `relay_node`, `next_hop` | Solo el último byte del nodo (firmware 2.6+). |
| `via_mqtt`, `transport_mechanism` | `TRANSPORT_MQTT` o `via_mqtt` = entró a la red desde MQTT (ADR 0009). |
| `pki_encrypted` | Mensaje directo cifrado de punta a punta: no se intenta descifrar. |

`Data`: `portnum`, `payload`, `want_response`, `dest`, `source`, `request_id` (respuestas), `reply_id` (respuestas en el chat, apunta al `id` del original), `emoji` (la respuesta es una reacción), `bitfield` (bit 0 = OK to MQTT).

## Por `portnum`

| portnum | Mensaje | Qué hace meshbox |
|---|---|---|
| `TEXT_MESSAGE_APP` | texto UTF-8 (`errors="replace"`) | `messages` si es broadcast del canal público (recortado a 250); alertas por palabra clave |
| `ALERT_APP` | texto | `messages` con `is_alert`; dispara siempre las reglas de palabra clave |
| `POSITION_APP` | `Position` | `latitude_i`/`longitude_i` × 1e-7; descarta 0,0; `precision_bits`, `ground_speed`, `sats_in_view` |
| `NODEINFO_APP` | `User` | nombres (40/5 caracteres), `hw_model`, `role` (ausente = `CLIENT`), `is_licensed`, `public_key` |
| `TELEMETRY_APP` | `Telemetry` (oneof) | `device_metrics`, `environment_metrics`, `power_metrics` a sus tablas; `local_stats` del gateway al panel; el resto queda en `packets` |
| `NEIGHBORINFO_APP` | `NeighborInfo` | enlaces `neighborinfo` (`node_id` → `neighbors[].node_id`, `snr`) |
| `TRACEROUTE_APP` | `RouteDiscovery` | solo las respuestas (`request_id`): `traceroutes` y enlaces `traceroute`; SNR × 4, -128 = desconocido |
| `ROUTING_APP` | `Routing` | contadores por `error_reason` |
| `WAYPOINT_APP` | `Waypoint` | puntos de interés; `expire` vencido = borrado |
| `MAP_REPORT_APP` | `MapReport` | firmware, región, preset y nodos en línea del gateway |
| `RANGE_TEST_APP`, `STORE_FORWARD_APP`, `PAXCOUNTER_APP`, `DETECTION_SENSOR_APP` | según tipo | solo `packets` |
| otros (`KEY_VERIFICATION_APP`, `NODE_STATUS_APP`, `CAYENNE_APP`, `PRIVATE_APP`, …) | — | solo `packets` |

## Observado en una red real (cinco horas, canal MediumFast)

Gateway Heltec V4 (`CLIENT_BASE`), canal `MediumFast` con la clave por defecto. Cinco horas de tráfico real tomadas del broker de la Pi.

Grabaciones: 2 archivo(s), 95 paquetes, 1 gateway(s), 0 cifrados.

| portnum | paquetes | dirigidos | campos observados (veces) |
|---|---|---|---|
| `TELEMETRY_APP` | 34 | 0 | `time` (34), `device_metrics` (34) |
| `POSITION_APP` | 32 | 0 | `latitude_i` (32), `longitude_i` (32), `location_source` (32), `precision_bits` (32), `altitude` (29), `time` (29), `ground_speed` (29), `ground_track` (29), `PDOP` (22), `sats_in_view` (22), `altitude_hae` (3) |
| `NODEINFO_APP` | 24 | 6 | `id` (24), `long_name` (24), `short_name` (24), `macaddr` (24), `hw_model` (24), `public_key` (24), `is_unmessagable` (19), `role` (11) |
| `ROUTING_APP` | 3 | 3 | `error_reason` (3) |
| `TRACEROUTE_APP` | 2 | 2 | `route` (2), `snr_towards` (2) |

Variantes de telemetría: solo `device_metrics` (34). Precisión de posición: los 32 informes con `precision_bits = 13` (radio de unos 2,9 km: la posición se ajusta al centro de una celda, por eso varios nodos comparten coordenadas exactas). Saltos al llegar al gateway: 0 (48), 1 (46).

Notas:

- Unos 19 paquetes por hora; ningún mensaje de texto en el canal público en esas cinco horas.
- `role` falta en la mayoría de los NodeInfo: proto3 no transmite el valor por defecto, y ausente significa `CLIENT` (el plan lo preveía).
- Las respuestas NodeInfo dirigidas (`want_response`) se guardan solo como encabezado.
- Los traceroutes vistos son respuestas dirigidas: se procesan para enlaces aunque sean dirigidos.
- Los paquetes que origina el propio gateway llegan con `rx_snr = 0` y `rx_rssi = 0` (no pasaron por la radio) y `hop_start = hop_limit`: meshbox los guarda sin señal. El gateway originó solo 2 en cinco horas (NodeInfo cada 3 h; telemetría y posición apagadas en su configuración, ver ADR 0011). Desde 0.2.3 su estado sale del tráfico que pasa por él.
- La señal con que el gateway oye a los demás está entre -115 y -120 dBm (SNR de -4 a -9 dB), incluso para vecinos directos: margen chico para `MediumFast`.
