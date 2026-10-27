# Cómo escribir un plugin

Un plugin agrega funciones sin tocar meshbox: escucha eventos, consulta servicios externos, levanta alertas, publica por MQTT y muestra capas en el mapa.

> **Un plugin corre dentro del servicio: instalarlo equivale a confiar en su código.** El panel lo advierte. Revisar el código antes de copiarlo a la Pi.

## Instalación

1. Copiar la carpeta del plugin a `/var/lib/meshbox/plugins/<id>/` (en desarrollo, a `dev/data/plugins/<id>/`).
2. En el panel, **Plugins**: aparece en la lista; completar los ajustes y activarlo.
3. Si el plugin declara rutas propias (`router()`), reiniciar meshbox para que se monten.

El plugin de ejemplo de esta guía está en [`docs/examples/plugins/charla/`](examples/plugins/charla/) y una prueba automática (`test_example_plugin_installs_by_copying_folder`) verifica que se instala copiando la carpeta.

## Estructura

```
charla/
  plugin.toml             # manifiesto
  settings.schema.json    # ajustes (JSON Schema simple); el panel arma el formulario
  __init__.py
  plugin.py               # código: una clase que hereda de PluginBase
```

La carpeta es un paquete de Python: el nombre de la carpeta debe ser igual al `id`.

## Manifiesto (`plugin.toml`)

```toml
id = "charla"
name = "Quién está hablando"
version = "1.0.0"
api_version = 1
entrypoint = "charla.plugin:Plugin"
description = "Marca en el mapa los nodos que escribieron en la última hora."
permissions = ["events.read", "map.layers", "nodes.read"]
settings_schema = "settings.schema.json"

[[map_layers]]
id = "hablando"
name = "Nodos que escribieron"
geometry = "point"     # point | line | polygon
style = "point"        # estilos predefinidos: point, heat, line, polygon
refresh_s = 60         # cada cuánto se vuelve a pedir la capa
```

### Permisos

| Permiso | Habilita |
|---|---|
| `events.read` | Recibir eventos del bus en `on_event` |
| `http.outbound` | `ctx.http` (cliente HTTP con tiempo máximo de 20 s) |
| `alerts.raise` | `ctx.raise_alert(...)` |
| `map.layers` | Capas GeoJSON declaradas en el manifiesto |
| `mqtt.publish` | `ctx.publish_mqtt(subtópico, datos)` → `meshbox/events/plugins/<id>/...` |
| `nodes.read` | `ctx.nodes()` y `ctx.fixed_nodes()` (nodos públicos, solo lectura) |

Usar un método sin el permiso declarado lanza `PermissionError`.

## Ajustes (`settings.schema.json`)

Subconjunto de JSON Schema: `type` (`string`, `integer`, `number`, `boolean`, `array`, `object`), `properties`, `required`, `default`, `enum`, `minimum`, `maximum`, `minLength`, `maxLength`, `pattern`, `items`, `title`, `description`. Los campos con `"writeOnly": true` (claves de API, secretos) se guardan en `secrets.toml`, el panel nunca los devuelve (muestra `********`) y el plugin los lee en `ctx.secrets`.

## API (`PluginBase`)

```python
from meshbox.models import Event, MessageAdded
from meshbox.plugins.api import PluginBase, PluginContext


class Plugin(PluginBase):
    async def setup(self, ctx: PluginContext) -> None:   # al activarse (máximo 20 s)
        await super().setup(ctx)                          # deja ctx en self.ctx

    async def on_event(self, event: Event) -> None:      # requiere events.read (máximo 10 s por evento)
        if isinstance(event, MessageAdded): ...

    def router(self) -> APIRouter | None:                 # /api/v1/admin/plugins/<id>/api/... (con sesión de admin)
        ...

    async def layer(self, layer_id: str) -> dict:         # FeatureCollection de cada capa declarada
        ...

    async def teardown(self) -> None:                     # al desactivarse o al detener el servicio
        ...
```

`PluginContext`:

| Atributo | Qué es |
|---|---|
| `ctx.settings` | Ajustes validados (sin los secretos) |
| `ctx.secrets` | Secretos del plugin |
| `ctx.log` | Logger propio; sus registros se ven en **Plugins → Registros** |
| `ctx.http` | `httpx.AsyncClient` con tiempo máximo |
| `ctx.raise_alert(title, body, severity=, node=, is_public=, key=)` | Alerta por los canales de notificación |
| `ctx.publish_mqtt(subtópico, datos)` | JSON a `meshbox/events/plugins/<id>/<subtópico>` |
| `ctx.nodes()`, `ctx.fixed_nodes()` | Nodos públicos |
| `ctx.site` | Ajustes del sitio (centro, límites, nombre) |
| `await ctx.kv_get(clave)`, `await ctx.kv_set(clave, valor)` | Almacenamiento clave-valor propio (tabla `settings`, prefijo `plugin.<id>.`) |

Eventos disponibles (en `meshbox.models`): `PacketProcessed`, `NodeUpserted`, `NodeHidden`, `PositionAdded`, `TelemetryAdded`, `MessageAdded`, `LinkObserved`, `TracerouteAdded`, `WaypointChanged`, `AlertFired`, `AlertResolved`, `ConnectorStatusChanged`, `SystemStatus`, `StatsUpdated`.

## Qué ve el público

Los datos públicos de un plugin se exponen **solo como capas GeoJSON** declaradas en el manifiesto:

- `GET /api/v1/plugins/layers` → lista de capas activas.
- `GET /api/v1/plugins/<id>/layers/<capa>` → FeatureCollection (se cachea `refresh_s`).

El frontend no carga código de plugins: dibuja las capas con los estilos predefinidos y arma el formulario de ajustes desde el esquema. Así no hay JavaScript de terceros en el sitio.

## Plugins incluidos

| Plugin | Qué hace | Ajustes clave |
|---|---|---|
| `fires` | Focos de calor de NASA FIRMS (VIIRS NOAA-20, NOAA-21, SNPP) cada 30 min; capa con tamaño según FRP; alerta opcional si hay focos a menos de N km de un nodo fijo | `map_key` (gratuita en firms.modaps.eosdis.nasa.gov), área, días, `alert_km` |
| `puente` | Envía los eventos elegidos a otro sistema por MQTT o webhook firmado (HMAC-SHA256) | vía, eventos, URL y secreto |
| `station` | Lee una estación meteorológica por JSON (por ejemplo la API de una estación propia) y la muestra como punto fijo con sus valores | URL, posición, campos (ruta con puntos, etiqueta, unidad) |
