# meshbox

**Gateway, mapa web y panel de administración Meshtastic para Raspberry Pi Zero 2 W.**

meshbox recibe los paquetes de la red Meshtastic desde un nodo Heltec (por MQTT o USB), los decodifica, aplica reglas de privacidad, los guarda en SQLite y publica:

- un **sitio público**: mapa en vivo, nodos, chat del canal público, alertas, estadísticas y actividad en tiempo real, instalable como PWA y con notificaciones de SOS;
- un **panel de administración** en la red local: radio, broker MQTT, canales, captura de paquetes, nodos, moderación, alertas, mapa, privacidad, Cloudflare, plugins, usuarios, respaldos, actualizaciones y registros.

Se publica en internet con **Cloudflare Tunnel** (sin abrir puertos) y corre en 512 MB de RAM.

## Requisitos

- Raspberry Pi Zero 2 W (o superior) con Raspberry Pi OS Lite 64 bits (Debian 13 trixie).
- Un nodo Meshtastic (probado con Heltec V3 y V4) conectado por USB o configurado como gateway MQTT.
- Opcional: dominio administrado en Cloudflare.

## Instalación

En una Raspberry Pi con Raspberry Pi OS Lite de 64 bits, conectada a internet:

```bash
curl -fsSL https://raw.githubusercontent.com/marcomagnaiot/meshbox/main/deploy/get.sh | sudo bash
```

Instala la última versión en modo **equipo dedicado** (puerto 80). Si la Pi ya corre otros servicios, el modo **compartido** usa los puertos 8090 a 8092:

```bash
curl -fsSL https://raw.githubusercontent.com/marcomagnaiot/meshbox/main/deploy/get.sh | sudo bash -s -- --shared
```

El instalador verifica la firma del paquete antes de instalar. Al terminar muestra la dirección del asistente de primer uso (`http://<ip-de-la-pi>/setup`) y el **código de configuración**. El asistente pide el nombre del sitio, el canal público, cómo llega la radio (USB o MQTT) y crea el usuario administrador.

Otras formas (desde un clon con `sudo ./deploy/get.sh`, con el paquete bajado a mano o con la imagen de SD) en [`docs/instalacion.md`](docs/instalacion.md).

## Documentación

| Documento | Contenido |
|---|---|
| [`docs/instalacion.md`](docs/instalacion.md) | Instalador, imagen de SD, primer arranque, solución de problemas |
| [`docs/heltec.md`](docs/heltec.md) | Configurar el nodo gateway (MQTT y USB) |
| [`docs/cloudflare.md`](docs/cloudflare.md) | Publicar con Cloudflare Tunnel y administración remota con Access |
| [`docs/admin.md`](docs/admin.md) | Cada sección del panel |
| [`docs/privacidad.md`](docs/privacidad.md) | Qué se guarda, por cuánto tiempo y cómo pedir la baja |
| [`docs/arquitectura.md`](docs/arquitectura.md) | Módulos, flujo de paquetes y decisiones |
| [`docs/api.md`](docs/api.md) | API pública y de administración, SSE, webhooks |
| [`docs/plugins.md`](docs/plugins.md) | Cómo escribir un plugin |
| [`docs/desarrollo.md`](docs/desarrollo.md) | Entorno en Windows, pruebas y releases |
| [`docs/paquetes.md`](docs/paquetes.md) | Estructura de cada tipo de paquete |
| [`docs/adr/`](docs/adr/) | Decisiones de arquitectura |

## Autor y licencia

Autor: Marco Magnanelli junto a Claude Opus 5.5.

Apache-2.0. Ver [`LICENSE`](LICENSE). Mapa base © colaboradores de OpenStreetMap (ODbL), Protomaps. Meshtastic® es una marca registrada de Meshtastic LLC.
