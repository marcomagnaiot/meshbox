# ADR 0009 · Diferencias entre el protobuf instalado y el plan

Estado: aceptada · 20/10/2026

## Contexto

La regla 0.1.3 manda usar los nombres reales de la librería `meshtastic` instalada (2.7.11, protobuf 7.36). Al volcar los descriptores aparecieron campos y valores que el plan no menciona.

## Hallazgos

| Elemento | Real | Plan |
|---|---|---|
| `MeshPacket.transport_mechanism` | enum `TRANSPORT_INTERNAL`, `TRANSPORT_LORA`, `TRANSPORT_LORA_ALT1..3`, `TRANSPORT_MQTT`, `TRANSPORT_MULTICAST_UDP`, `TRANSPORT_API` | no figura |
| `Telemetry` (oneof) | además de `device_metrics`, `environment_metrics`, `power_metrics`: `air_quality_metrics`, `local_stats`, `health_metrics`, `host_metrics`, `traffic_management_stats` | solo los tres primeros |
| `PortNum` | nuevos `KEY_VERIFICATION_APP`, `REMOTE_SHELL_APP`, `STORE_FORWARD_PLUSPLUS_APP`, `NODE_STATUS_APP`, `CAYENNE_APP`, `ATAK_PLUGIN_V2`, `GROUPALARM_APP` | no figuran |
| `Config.DeviceConfig.Role` | nuevo `CLIENT_BASE` | no figura |
| `MapReport` | campo `has_opted_report_location` | no figura |
| `User` | campo `is_unmessagable` | no figura |
| `HardwareModel` | `HELTEC_V4 = 110`, `HELTEC_V4_R8 = 132` | coincide con 25.3 |

## Decisión

- `transport_mechanism` se guarda en `receptions` (columna nueva, ver migración 0001) y se usa junto con `via_mqtt` para la regla de privacidad 10.5: un paquete con `TRANSPORT_MQTT` se trata igual que `via_mqtt = true`.
- Las variantes nuevas de telemetría se guardan crudas en `packets` (como dice el plan para "los demás") y `local_stats` del gateway se muestra en el panel (diagnóstico).
- Los portnums nuevos se tratan como "otros": solo `packets`.
- `CLIENT_BASE` no es infraestructura para `is_infra`.
