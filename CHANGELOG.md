# Cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versiones con [SemVer](https://semver.org/lang/es/).

## [Sin publicar]

## [0.8.1] - 2026-10-27

### Corregido

- Al terminar, el instalador dice exactamente qué hacer: «entrá a http://<ip>/setup y usá el código …», además de las direcciones del sitio y del panel. Antes decía «Panel y asistente: http://<ip>», que abre el mapa.
- `get.sh` terminaba con `tmp: unbound variable` y dejaba una carpeta temporal.

### Agregado

- En la red local, mientras no haya ningún usuario, el sitio muestra «Falta configurar meshbox» con un enlace al asistente.

## [0.8.0] - 2026-10-27

Primera versión pública.

### Agregado

- Instalación en una línea (`deploy/get.sh`): averigua la última versión publicada en GitHub, baja su instalador y lo ejecuta. El instalador verifica la firma Ed25519 del paquete antes de instalar.
- Las actualizaciones del panel bajan directo de los releases de GitHub.
- Clave de firma definitiva de los releases (ver `SECURITY.md`).

### Incluye

- Sitio público: mapa en vivo con capas (claro, oscuro y satelital), nodos con su color, chat del canal público, alertas y SOS, estadísticas, actividad en tiempo real, instalable como PWA.
- Panel de administración: radio (MQTT, USB y TCP), Cliente Meshtastic (estado, mensajes guardados en la base, configuración de la placa, fijar posición, batería con tendencia de carga a 2 y 7 días), broker MQTT, canales, captura de paquetes, nodos y moderación, alertas, mapa, privacidad, Cloudflare Tunnel, plugins, usuarios, respaldos, actualizaciones y registros.
- Instalador para Raspberry Pi OS de 64 bits en modo equipo dedicado o compartido, e imagen de SD con primer arranque.
