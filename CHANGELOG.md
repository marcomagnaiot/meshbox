# Cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versiones con [SemVer](https://semver.org/lang/es/).

## [Sin publicar]

## [0.8.4] - 2026-10-28

### Corregido

- Actualizaciones: «Última actualización» mostraba `[object Object]`. Ahora muestra la fecha y la versión instalada.

## [0.8.3] - 2026-10-27

### Agregado

- Manual del usuario, de punta a punta y con capturas: `docs/manual.md` y su versión para imprimir `docs/manual.pdf`. Las capturas salen de una instalación de prueba con datos simulados (`scripts/manual_servidor.py` y `frontend/scripts/capturas-manual.mjs`) y el PDF se arma con `scripts/manual_pdf.py`.

### Corregido

- Buscar una ciudad en el selector del sitio la centraba en el medio de su caja, que en municipios con ejidos grandes queda lejos de la ciudad. Ahora el centro es el punto del lugar y el zoom sale de la caja, entre 10 y 13.
- Textos del panel y del archivo de permisos de Mosquitto que remitían a secciones del plan interno.

## [0.8.2] - 2026-10-27

### Corregido

- La descarga del mapa base fallaba con «pmtiles terminó con código 1» en redes cuyo router rechaza las consultas DNS del resolvedor propio de Go («server misbehaving»), aunque responda bien al del sistema. Ahora pmtiles baja a través de un proxy CONNECT local y efímero que resuelve con el DNS del sistema y solo deja pasar el host del mapa.
- El panel muestra el motivo completo cuando falla la descarga del mapa base, no solo el código de salida.

## [0.8.1] - 2026-10-27

### Corregido

- Al terminar, el instalador dice exactamente qué hacer: «entrá a http://<ip>/setup y usá el código …», además de las direcciones del sitio y del panel. Antes decía «Panel y asistente: http://<ip>», que abre el mapa.
- `get.sh` terminaba con `tmp: unbound variable` y dejaba una carpeta temporal.

### Agregado

- En la red local, mientras no haya ningún usuario, el sitio muestra «Falta configurar meshbox» con un enlace al asistente.
- Selectores de mapa del asistente, de Sitio y mapa y de Fijar posición: buscador de lugares por nombre (Nominatim de OpenStreetMap) y nombres de ciudades y rutas sobre la imagen satelital.
- Latitud y longitud como texto, sin flechitas: aceptan punto o coma decimal, y pegar «lat, lon» copiado de Google Maps (o un enlace, o grados, minutos y segundos) en cualquiera de los dos campos completa ambos.

### Cambiado

- Asistente, paso Radio: primero USB (se activa solo si hay un nodo enchufado) y después MQTT como alternativa para un Heltec por WiFi. Al terminar, primero la prueba del nodo USB.
- El menú de capas explica que Claro y Oscuro aparecen cuando se descarga el mapa base y dónde se descarga.

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
