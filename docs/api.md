# API

Prefijo `/api/v1`, JSON, tiempos en segundos Unix. Errores en formato RFC 9457 (`application/problem+json` con `type`, `title`, `status`, `detail` y, en errores de validación, `errors[]`). Paginación por cursor `before=<ts>:<pk>` con `limit`; la respuesta trae `next` (o `null`).

La documentación interactiva (OpenAPI/Swagger) está en el servidor LAN, con sesión de administrador: `http://<pi>:8090/api/docs` (en desarrollo, `http://127.0.0.1:8000/api/docs` sin sesión).

## Servidores

| Servidor | Dirección (equipo compartido) | Rutas |
|---|---|---|
| Público (destino del túnel) | `127.0.0.1:8091` | `/api/v1/...` públicas, `/tiles`, sitio. `/admin`, `/setup`, `/api/v1/admin` y `/api/v1/setup` responden 404. |
| LAN | `0.0.0.0:8090` | Todo: público + panel + asistente. |
| Administración remota | `127.0.0.1:8092` | Como LAN; toda ruta de panel o asistente exige el JWT de Cloudflare Access. |

La IP del cliente sale de `CF-Connecting-IP` solo si la petición llega desde `127.0.0.1` (cloudflared).

## Pública

| Ruta | Respuesta |
|---|---|
| `GET /site` | Nombre, descripción, logo, acento, centro, zoom, límites, capas, `has_tiles`, umbrales de estado, funciones, aviso de privacidad **como bloques** (`notice`), canales públicos, zona horaria, idiomas, versión, atribuciones, capas de plugins. Con `ETag`. |
| `GET /nodes` | `{seq, ts, nodes:[Nodo]}` (sin caché) |
| `GET /nodes/{!id}` | Nodo + `firmware_version`, `region`, `modem_preset`, `position_ts`, `metrics_ts` |
| `GET /nodes/{!id}/positions?from&to&max_points=500` | `[{ts, lat, lon, alt, precision_m, speed_kmh}]`, reducido por tiempo |
| `GET /nodes/{!id}/telemetry?kind=device\|environment\|power&from&to` | Columnar: `{kind, resolution: raw\|hour\|day, ts:[], series:{métrica:[]}, min?, max?}`. Crudos hasta 48 h, horarios hasta 90 d, diarios más allá |
| `GET /nodes/{!id}/links` | Vecinos `[{a, b, snr, source, ts}]` |
| `GET /messages?before&limit=50` | `{messages:[Mensaje], next}` (sin ocultos) |
| `GET /alerts?before&limit=20` | `{alerts:[Alerta], next}` (solo públicas) |
| `GET /links?max_age=86400` | Enlaces para la capa del mapa |
| `GET /traceroutes?node&limit` | Últimos traceroutes |
| `GET /waypoints` | Puntos de interés vigentes |
| `GET /stats/summary` | Conteos por estado, paquetes de la última hora, utilización de canal, nodos nuevos |
| `GET /stats/timeseries?metric&range=24h\|7d\|30d` | Serie horaria: `packets`, `active_nodes`, `new_nodes`, `avg_channel_util`, `by_portnum`, `by_hops` |
| `GET /stats/breakdown?range=` | Totales del rango: paquetes por tipo, saltos y nodos que más retransmiten (`relays` con candidatos: el firmware informa solo el último byte del nodo) |
| `GET /stream` | SSE (ver abajo); `?activity=1` agrega actividad |
| `GET /push/vapid-public-key` | `{key}` (404 si push no está disponible) |
| `POST /push/subscriptions` / `DELETE` | `{endpoint, keys:{p256dh, auth}}` → 201 / 204. Solo alertas públicas. 5 por hora por IP |
| `GET /plugins/layers`, `GET /plugins/{id}/layers/{capa}` | Capas GeoJSON de plugins |
| `GET /health` | `{"status":"ok","version":"x.y.z"}` (503 mientras arranca) |
| `GET /tiles/v.json` | TileJSON del extracto (404 si no hay) |
| `GET /tiles/v/{z}/{x}/{y}.mvt` | Tesela vectorial (gzip), 204 si no existe, caché de 30 días |
| `GET /tiles/fonts/{fuente}/{rango}.pbf`, `GET /tiles/sprites/...` | Recursos del estilo, servidos localmente |

Límite: 300 peticiones por minuto por IP (sin contar teselas ni estáticos).

### Esquemas

| Recurso | Campos |
|---|---|
| Nodo | `id`, `short_name`, `long_name`, `role`, `hw_model`, `lat`, `lon`, `alt`, `precision_m`, `battery` (0-100; 101 = alimentación externa), `powered`, `voltage`, `channel_utilization`, `air_util_tx`, `uptime_s`, `last_heard`, `first_seen`, `hops`, `snr`, `rssi`, `is_infra`, `is_fixed`, `env` (`temperature`, `humidity`, `pressure`, `lux`, `ts`) |
| Mensaje | `pk`, `ts`, `from`, `from_name`, `channel`, `text`, `reply_id`, `emoji`, `packet_id` |
| Alerta | `id`, `state` (`firing`/`resolved`), `severity` (`info`/`warning`/`critical`), `kind`, `node`, `title`, `body`, `ts` |
| Actividad | `portnum`, `from`, `to` (`^all` = broadcast), `hops`, `snr`, `gateway`, `ts` |
| Enlace | `a` (quien recibe), `b` (quien transmite), `snr`, `source` (`neighborinfo`, `direct`, `traceroute`), `ts` |

`reply_id` de un mensaje es el `packet_id` del mensaje al que responde. Con `emoji: true` el texto es una reacción a ese mensaje.

## Tiempo real (SSE)

Protocolo sin pérdidas entre la foto inicial y el flujo:

1. Abrir `GET /api/v1/stream` y guardar los eventos que llegan.
2. Pedir `GET /api/v1/nodes`, que devuelve `seq`.
3. Aplicar la lista y después los eventos guardados con `seq` mayor.
4. Si el stream se corta, el navegador reconecta solo: repetir 2 y 3. El evento `resync` (cliente atrasado) indica lo mismo.

| `event:` | `data:` |
|---|---|
| `node` | Nodo público completo + `seq` |
| `node_remove` | `{seq, id}` (nodo ocultado) |
| `position` | `{seq, id, lat, lon, alt, precision_m, ts}` |
| `telemetry` | `{seq, id, kind, values, ts}` |
| `message` | Mensaje + `seq` |
| `message_remove` / `message_restore` | `{seq, pk}` (moderación) |
| `alert` | Alerta pública + `seq` |
| `link` | `{seq, a, b, snr, source, ts}` |
| `waypoint` | Punto de interés + `seq`, `deleted` |
| `stats` | Resumen cada 30 s |
| `activity` | Actividad (solo con `?activity=1`, máximo 10 por segundo, sin `seq`) |
| `resync` | `{}`: volver a pedir la foto |
| `: ping` | Comentario cada 15 s (mantiene viva la conexión a través de Cloudflare) |

Límites: 10 conexiones por IP y 200 en total en el servidor público.

El panel tiene su propio stream, `GET /api/v1/admin/stream?packets=1&logs=1&portnum=&node=&gateway=&max_packets_per_s=20`, con los eventos de arriba más `packet`, `connector`, `system`, `diagnostic`, `log` y `traceroute`.

## Administración

Sesión obligatoria (cookie `meshbox_session`, `HttpOnly`, `SameSite=Strict`). Toda petición que modifica lleva la cabecera `X-CSRF-Token` (el token lo devuelve el inicio de sesión) y queda en la auditoría. Roles: `admin` (todo) y `operator` (paquetes, nodos, mensajes, alertas, registros). Límite: 600 peticiones por minuto por sesión; inicio de sesión: 5 intentos por minuto por IP y espera creciente tras 10 fallos seguidos de un usuario.

Los secretos nunca se devuelven: los campos secretos son de solo escritura y al leer muestran `********`.

### Asistente de primer uso (`/api/v1/setup`)

Sin sesión solo mientras no existe ningún usuario, con el código de configuración en la cabecera `X-Setup-Code` y como máximo 60 min desde el arranque (en modo punto de acceso no se pide el código). `POST /setup/admin` crea el administrador e inicia su sesión; los pasos siguientes usan esa sesión.

## Webhook de alertas

`POST` a la URL configurada, con la cabecera `X-Meshbox-Signature: sha256=<hex de HMAC-SHA256 del cuerpo con el secreto>` y tres reintentos con espera creciente:

```json
{"event": "alert", "version": 1, "sent_at": 1792465602.1,
 "data": {"id": 88, "state": "firing", "severity": "critical", "kind": "keyword",
          "node": "!31b8896d", "title": "SOS desde Nodo playa", "body": "SOS", "ts": 1792465601.0}}
```

Verificación en el receptor (Python):

```python
import hashlib, hmac
esperado = "sha256=" + hmac.new(secreto.encode(), cuerpo, hashlib.sha256).hexdigest()
assert hmac.compare_digest(esperado, request.headers["X-Meshbox-Signature"])
```

## Salida MQTT

Con la salida de eventos activa (**Broker MQTT**), meshbox publica JSON (mismo formato que el SSE) en `meshbox/events/node`, `message`, `telemetry`, `position` y `alert`. Las integraciones leen con una cuenta `int-<nombre>` (permiso `read meshbox/events/#`).

## Índice de rutas

Generado desde el OpenAPI de la aplicación (`scripts/gen-api-index.py`).

### administración: Cloudflare

| Método | Ruta |
|---|---|
| `POST` | `/api/v1/admin/cloudflare/access` |
| `POST` | `/api/v1/admin/cloudflare/api/provision` |
| `POST` | `/api/v1/admin/cloudflare/api/verify` |
| `GET` | `/api/v1/admin/cloudflare/api/zones` |
| `POST` | `/api/v1/admin/cloudflare/disconnect` |
| `GET` | `/api/v1/admin/cloudflare/status` |
| `POST` | `/api/v1/admin/cloudflare/token` |

### administración: alertas

| Método | Ruta |
|---|---|
| `GET` | `/api/v1/admin/alerts/channels` |
| `PUT` | `/api/v1/admin/alerts/channels` |
| `POST` | `/api/v1/admin/alerts/channels/{channel}/test` |
| `GET` | `/api/v1/admin/alerts/events` |
| `POST` | `/api/v1/admin/alerts/events/{eid}/ack` |
| `POST` | `/api/v1/admin/alerts/push/subscriptions` |
| `GET` | `/api/v1/admin/alerts/rules` |
| `POST` | `/api/v1/admin/alerts/rules` |
| `GET` | `/api/v1/admin/alerts/rules/schema` |
| `DELETE` | `/api/v1/admin/alerts/rules/{rid}` |
| `PUT` | `/api/v1/admin/alerts/rules/{rid}` |
| `POST` | `/api/v1/admin/alerts/rules/{rid}/test` |
| `GET` | `/api/v1/admin/alerts/webhooks/{hid}/secret` |

### administración: broker MQTT

| Método | Ruta |
|---|---|
| `GET` | `/api/v1/admin/mqtt/accounts` |
| `POST` | `/api/v1/admin/mqtt/accounts` |
| `DELETE` | `/api/v1/admin/mqtt/accounts/{username}` |
| `POST` | `/api/v1/admin/mqtt/accounts/{username}/rotate` |
| `GET` | `/api/v1/admin/mqtt/acl` |
| `PUT` | `/api/v1/admin/mqtt/out` |
| `GET` | `/api/v1/admin/mqtt/status` |

### administración: canales

| Método | Ruta |
|---|---|
| `GET` | `/api/v1/admin/channels` |
| `POST` | `/api/v1/admin/channels` |
| `DELETE` | `/api/v1/admin/channels/{cid}` |
| `PUT` | `/api/v1/admin/channels/{cid}` |

### administración: cliente Meshtastic

| Método | Ruta |
|---|---|
| `GET` | `/api/v1/admin/radio` |
| `GET` | `/api/v1/admin/radio/{cid}` |
| `GET` | `/api/v1/admin/radio/{cid}/backups` |
| `POST` | `/api/v1/admin/radio/{cid}/backups` |
| `GET` | `/api/v1/admin/radio/{cid}/backups/{name}` |
| `POST` | `/api/v1/admin/radio/{cid}/backups/{name}/restore` |
| `POST` | `/api/v1/admin/radio/{cid}/channels` |
| `DELETE` | `/api/v1/admin/radio/{cid}/channels/{index}` |
| `PUT` | `/api/v1/admin/radio/{cid}/channels/{index}` |
| `GET` | `/api/v1/admin/radio/{cid}/config` |
| `PUT` | `/api/v1/admin/radio/{cid}/config/{section}` |
| `DELETE` | `/api/v1/admin/radio/{cid}/messages` |
| `GET` | `/api/v1/admin/radio/{cid}/messages` |
| `POST` | `/api/v1/admin/radio/{cid}/messages` |
| `GET` | `/api/v1/admin/radio/{cid}/nodes` |
| `PUT` | `/api/v1/admin/radio/{cid}/owner` |
| `DELETE` | `/api/v1/admin/radio/{cid}/position` |
| `PUT` | `/api/v1/admin/radio/{cid}/position` |
| `POST` | `/api/v1/admin/radio/{cid}/position/refresh` |
| `PUT` | `/api/v1/admin/radio/{cid}/reads` |
| `POST` | `/api/v1/admin/radio/{cid}/reboot` |
| `POST` | `/api/v1/admin/radio/{cid}/request-position` |
| `POST` | `/api/v1/admin/radio/{cid}/shutdown` |
| `POST` | `/api/v1/admin/radio/{cid}/traceroute` |

### administración: paquetes, nodos y mensajes

| Método | Ruta |
|---|---|
| `GET` | `/api/v1/admin/messages` |
| `PATCH` | `/api/v1/admin/messages/{pk}` |
| `GET` | `/api/v1/admin/nodes` |
| `PATCH` | `/api/v1/admin/nodes/{nid}` |
| `DELETE` | `/api/v1/admin/nodes/{nid}/history` |
| `GET` | `/api/v1/admin/packets` |
| `GET` | `/api/v1/admin/packets/export` |
| `GET` | `/api/v1/admin/packets/{pk}` |

### administración: plugins y transmisión

| Método | Ruta |
|---|---|
| `GET` | `/api/v1/admin/plugins` |
| `PUT` | `/api/v1/admin/plugins/{pid}` |
| `GET` | `/api/v1/admin/plugins/{pid}/logs` |
| `POST` | `/api/v1/admin/tx/text` |
| `POST` | `/api/v1/admin/tx/traceroute` |

### administración: radio

| Método | Ruta |
|---|---|
| `GET` | `/api/v1/admin/connectors` |
| `POST` | `/api/v1/admin/connectors` |
| `GET` | `/api/v1/admin/connectors/recordings` |
| `GET` | `/api/v1/admin/connectors/serial-ports` |
| `DELETE` | `/api/v1/admin/connectors/{cid}` |
| `PUT` | `/api/v1/admin/connectors/{cid}` |
| `GET` | `/api/v1/admin/connectors/{cid}/node` |
| `POST` | `/api/v1/admin/connectors/{cid}/reboot-node` |
| `POST` | `/api/v1/admin/connectors/{cid}/record` |
| `POST` | `/api/v1/admin/connectors/{cid}/release` |
| `POST` | `/api/v1/admin/connectors/{cid}/restart` |
| `POST` | `/api/v1/admin/connectors/{cid}/test` |

### administración: respaldos y actualizaciones

| Método | Ruta |
|---|---|
| `GET` | `/api/v1/admin/backups` |
| `POST` | `/api/v1/admin/backups` |
| `POST` | `/api/v1/admin/backups/restore` |
| `POST` | `/api/v1/admin/backups/upload` |
| `GET` | `/api/v1/admin/backups/{name}` |
| `POST` | `/api/v1/admin/config/export` |
| `POST` | `/api/v1/admin/config/import` |
| `GET` | `/api/v1/admin/updates` |
| `POST` | `/api/v1/admin/updates/install` |
| `GET` | `/api/v1/admin/updates/jobs/{job}` |
| `POST` | `/api/v1/admin/updates/rollback` |
| `PUT` | `/api/v1/admin/updates/settings` |

### administración: sesión

| Método | Ruta |
|---|---|
| `POST` | `/api/v1/admin/auth/login` |
| `POST` | `/api/v1/admin/auth/logout` |
| `GET` | `/api/v1/admin/auth/me` |
| `POST` | `/api/v1/admin/auth/password` |

### administración: sistema

| Método | Ruta |
|---|---|
| `POST` | `/api/v1/admin/network/hotspot` |
| `GET` | `/api/v1/admin/network/status` |
| `POST` | `/api/v1/admin/network/wifi/connect` |
| `GET` | `/api/v1/admin/network/wifi/scan` |
| `DELETE` | `/api/v1/admin/network/wifi/{ssid}` |
| `PUT` | `/api/v1/admin/system/hostname` |
| `GET` | `/api/v1/admin/system/logs` |
| `GET` | `/api/v1/admin/system/metrics` |
| `POST` | `/api/v1/admin/system/reboot` |
| `POST` | `/api/v1/admin/system/services/{name}/restart` |
| `POST` | `/api/v1/admin/system/shutdown` |
| `GET` | `/api/v1/admin/system/status` |
| `PUT` | `/api/v1/admin/system/timezone` |

### administración: sitio, mapa y privacidad

| Método | Ruta |
|---|---|
| `GET` | `/api/v1/admin/privacy` |
| `PUT` | `/api/v1/admin/privacy` |
| `POST` | `/api/v1/admin/privacy/purge` |
| `GET` | `/api/v1/admin/site` |
| `PUT` | `/api/v1/admin/site` |
| `DELETE` | `/api/v1/admin/site/logo` |
| `POST` | `/api/v1/admin/site/logo` |
| `DELETE` | `/api/v1/admin/tiles` |
| `POST` | `/api/v1/admin/tiles/download` |
| `GET` | `/api/v1/admin/tiles/status` |

### administración: usuarios

| Método | Ruta |
|---|---|
| `GET` | `/api/v1/admin/audit` |
| `GET` | `/api/v1/admin/sessions` |
| `DELETE` | `/api/v1/admin/sessions/{sid}` |
| `GET` | `/api/v1/admin/users` |
| `POST` | `/api/v1/admin/users` |
| `DELETE` | `/api/v1/admin/users/{uid}` |
| `PUT` | `/api/v1/admin/users/{uid}` |

### asistente de primer uso

| Método | Ruta |
|---|---|
| `POST` | `/api/v1/setup/admin` |
| `POST` | `/api/v1/setup/channel` |
| `POST` | `/api/v1/setup/code` |
| `POST` | `/api/v1/setup/finish` |
| `POST` | `/api/v1/setup/locale` |
| `POST` | `/api/v1/setup/privacy` |
| `POST` | `/api/v1/setup/radio` |
| `POST` | `/api/v1/setup/site` |
| `POST` | `/api/v1/setup/skip/{step}` |
| `GET` | `/api/v1/setup/state` |
| `GET` | `/api/v1/setup/verify` |
| `POST` | `/api/v1/setup/wifi` |
| `GET` | `/api/v1/setup/wifi/scan` |

### mapa

| Método | Ruta |
|---|---|
| `GET` | `/tiles/fonts/{fontstack}/{rng}.pbf` |
| `GET` | `/tiles/sprites/{path}` |
| `GET` | `/tiles/v.json` |
| `GET` | `/tiles/v/{z}/{x}/{y}.mvt` |

### público

| Método | Ruta |
|---|---|
| `GET` | `/api/v1/alerts` |
| `GET` | `/api/v1/health` |
| `GET` | `/api/v1/links` |
| `GET` | `/api/v1/messages` |
| `GET` | `/api/v1/nodes` |
| `GET` | `/api/v1/nodes/{node}` |
| `GET` | `/api/v1/nodes/{node}/links` |
| `GET` | `/api/v1/nodes/{node}/positions` |
| `GET` | `/api/v1/nodes/{node}/telemetry` |
| `GET` | `/api/v1/plugins/layers` |
| `GET` | `/api/v1/plugins/{plugin_id}/layers/{layer_id}` |
| `DELETE` | `/api/v1/push/subscriptions` |
| `POST` | `/api/v1/push/subscriptions` |
| `GET` | `/api/v1/push/vapid-public-key` |
| `GET` | `/api/v1/site` |
| `GET` | `/api/v1/stats/breakdown` |
| `GET` | `/api/v1/stats/summary` |
| `GET` | `/api/v1/stats/timeseries` |
| `GET` | `/api/v1/traceroutes` |
| `GET` | `/api/v1/waypoints` |

### tiempo real

| Método | Ruta |
|---|---|
| `GET` | `/api/v1/admin/stream` |
| `GET` | `/api/v1/stream` |
