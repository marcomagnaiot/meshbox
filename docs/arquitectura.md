# Arquitectura

meshbox es **un solo proceso Python** (asyncio) que recibe paquetes Meshtastic, los procesa, los guarda en SQLite y los publica por HTTP y SSE. Las operaciones que necesitan root las hace un servicio aparte, `meshbox-privd`, con una lista cerrada de comandos.

## Diagrama

```
                    ┌──────────────────────── Raspberry Pi ───────────────────────────────┐
[Heltec techo]      │                                                                      │
   ~~LoRa~~         │  mosquitto (:1883 LAN, usuario y contraseña, ACL por plantilla)      │
[Heltec gateway] ──WiFi/MQTT──► │                                                        │
       └───────USB serie──────┐ │                                                        │
                    │         ▼ ▼                                                        │
                    │  meshbox (1 proceso)                                               │
                    │  ├─ conectores: mqtt | serial | replay        (connectors/)        │
                    │  ├─ cola de ingreso acotada                    (connectors/manager)│
                    │  ├─ pipeline: dedup → límite → descifrado → privacidad →           │
                    │  │            decodificación → privacidad → estado (pipeline/)     │
                    │  ├─ estado en memoria + escritor por lotes SQLite WAL (state, store)│
                    │  ├─ bus de eventos → SSE, alertas, plugins, salida MQTT (bus)      │
                    │  ├─ servidor público   127.0.0.1:8091  ◄── cloudflared ◄── Internet │
                    │  ├─ servidor LAN       0.0.0.0:8090 (público + panel) ◄── red local │
                    │  └─ admin remoto       127.0.0.1:8092 (opcional, Access) ◄── túnel  │
                    │                                                                      │
                    │  meshbox-privd (root, /run/meshbox/privd.sock, lista cerrada)        │
                    │  meshbox-cloudflared (cloudflared tunnel run)                        │
                    └──────────────────────────────────────────────────────────────────────┘
```

Puertos en un **equipo compartido** (ADR 0004). En un equipo dedicado: LAN 80, público 8081, remoto 8082.

## Módulos

| Carpeta | Qué hace |
|---|---|
| `config.py` | `config.toml` + `secrets.toml` (pydantic-settings). Precedencia: código < archivo < `MESHBOX_*`. |
| `models.py`, `bus.py` | `RawPacket`, estado de conectores y eventos inmutables. Bus con `seq` global y una cola acotada por suscriptor: un suscriptor lento pierde eventos (con contador) y no frena a los demás. |
| `connectors/` | MQTT (`aiomqtt`, `ServiceEnvelope`), USB (`meshtastic.SerialInterface` en su hilo), reproducción y grabación JSONL. Reconexión 2-4-8-16-30-60 s ±20 %. |
| `pipeline/` | `dedup.py` (LRU 20 000 / 30 min, 120 paquetes/min por nodo), `crypto.py` (AES-CTR, igual que el firmware), `privacy.py`, `decode.py`, `process.py`. |
| `state.py` | Nodos, canales, gateways y métricas en vivo. Es la fuente de las respuestas en vivo; la base es la persistencia. |
| `store/` | Esquema (SQLAlchemy Core), migraciones (Alembic, en proceso aparte), escritor por lotes, consultas, agregados, retención, respaldos. |
| `api/` | Aplicaciones FastAPI (pública, LAN, remota), SSE, teselas, SPA, administración por área. |
| `auth/` | argon2id, sesiones, CSRF, JWT de Cloudflare Access, usuarios y auditoría. |
| `alerts/` | Motor de reglas y canales (Web Push, Telegram, webhook, MQTT). |
| `integrations/` | Mosquitto (cuentas y ACL vía privd), Cloudflare (API), actualizaciones. |
| `plugins/` | Carga de plugins, contexto con permisos, plugins incluidos (`fires`, `puente`, `station`). |
| `system/` | Métricas, guardia de memoria, registros JSON con filtro de secretos, cliente de privd (y uno simulado), `sd_notify`. |
| `tiles.py` | Teselas desde el extracto PMTiles local con caché de directorios. |
| `devtools/sim.py` | Red simulada para desarrollo y pruebas. |

## Flujo de un paquete (5.3)

1. El conector arma un `RawPacket` (origen, gateway, canal, hora del servidor, `MeshPacket`) y lo deja en la **cola de ingreso** (2000). Si se llena, los conectores en vivo descartan (protege la memoria); la reproducción espera.
2. **Deduplicación** por `(from, id)`: una copia de otro gateway solo agrega una fila en `receptions`.
3. **Límite por nodo**: más de 120 paquetes por minuto de un mismo nodo se descartan.
4. **Descifrado** si el paquete viene cifrado y hay una clave cuyo hash coincide (10.2). Los PKI no se intentan.
5. **Privacidad previa**: nodo oculto (nada), canal no público o paquete dirigido (solo encabezado; traceroute y routing dirigidos se procesan para enlaces).
6. **Decodificación** por `portnum`.
7. **Privacidad posterior**: lo que entró a la red por MQTT (`via_mqtt` o `transport_mechanism = TRANSPORT_MQTT`) no toca nodos ni posiciones; posición degradada si se configuró.
8. **Estado** en memoria y operaciones al **escritor por lotes** (cada 2 s o 200 operaciones, una transacción).
9. **Eventos** al bus: SSE público y del panel, alertas, plugins, salida MQTT.

## Decisiones que conviene conocer

- **`pk` asignados por la aplicación** (ADR 0010): las recepciones, posiciones y mensajes referencian el paquete antes de que el lote llegue a la base, y el SSE sale con el `pk`.
- **Un solo escritor** (11.1): todo lo que escribe (incluidas las acciones del panel) pasa por `BatchWriter`, en orden.
- **Migraciones en proceso aparte** (ADR 0010): Alembic no queda en la memoria del servicio.
- **Sin `MemoryMax` efectivo en la Pi** (ADR 0006): guardia propia de RSS (200 MB suave, 280 MB duro).
- **Lector de teselas propio**: el de la librería relee el directorio raíz en cada tesela (22 ms en la PC); el propio guarda el encabezado y los directorios (0,01 ms).
- **El frontend nunca interpreta HTML de datos**: el aviso de privacidad llega como bloques JSON (`api/markdown.py`).

## Memoria (medida en la Pi Zero 2 W)

| Componente | RSS acumulado |
|---|---|
| Python + FastAPI + uvicorn + pydantic | 46 MB |
| + SQLAlchemy | 58 MB |
| + MQTT, httpx, cryptography, JWT, argon2, pmtiles | 70 MB |
| + protobuf de meshtastic | 81 MB |
| + dos servidores uvicorn | 94 MB |

La librería serie y `pywebpush` se importan solo si se usan.
