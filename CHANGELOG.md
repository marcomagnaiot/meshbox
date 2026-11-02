# Cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versiones con [SemVer](https://semver.org/lang/es/).

## [Sin publicar]

## [0.9.7] - 2026-11-02

### Agregado

- Cliente Meshtastic → Nodos: **Pedir NodeInfo**. La placa le manda su NodeInfo al nodo y le pide el suyo: nombre, modelo y clave pública. Sirve con los nodos que se oyen pero de los que nunca llegó el NodeInfo, como un router lejano en una apertura troposférica. Sin la clave pública, la placa no puede leer las respuestas que ese nodo le manda cifradas de punta a punta (por ejemplo, la de un pedido de posición). Con la 0.9.6, la respuesta actualiza el nodo en el mapa.
- `POST /api/v1/admin/radio/{cid}/request-nodeinfo`.

## [0.9.6] - 2026-11-02

### Corregido

- Al reconectarse con una placa, meshbox copiaba encima del nombre real el nombre provisorio que la librería de Meshtastic arma para los nodos sin NodeInfo («Meshtastic abcd», modelo UNSET). Ya no lo usa, y borra el que haya quedado de antes.
- Cliente Meshtastic → Nodos muestra el nombre y el rol que conoce meshbox en lugar del provisorio.

### Cambiado

- Las respuestas a un pedido de posición o de NodeInfo hecho desde la estación actualizan el nodo en el mapa (posición, nombre, rol y modelo) cuando llegan por un canal público (ADR 0020). Antes solo se tomaban al reconectar la placa. El paquete sigue sin publicarse.

## [0.9.5] - 2026-11-02

### Corregido

- Cliente Meshtastic → Nodos muestra los nodos que la placa oyó después de conectarse con meshbox aunque no hayan mandado NodeInfo, posición ni telemetría, por ejemplo un router lejano que solo contestó un traceroute. La librería de Meshtastic no los sumaba a su copia de la base de la placa; ahora se completan con el estado de meshbox.
- Los nodos de la placa sin NodeInfo aparecen con su id y el nombre que conozca meshbox, y se pueden buscar y usar para mensaje directo, traceroute y pedido de posición. Antes quedaban sin id, no salían en la búsqueda y los botones no respondían.

### Cambiado

- En Transmisión → Traceroute, las sugerencias del nodo de destino muestran el nombre corto junto al largo, así se lo encuentra por cualquiera de los dos.

## [0.9.4] - 2026-11-01

### Agregado

- Mapa fuera del extracto (ADR 0019): fuera de la zona descargada en el equipo, las capas Claro y Oscuro siguen con el mapa gris de Esri, con calles y nombres hasta el zoom 16, ajustado para que el borde casi no se note. Dentro de la zona no cambia nada y el navegador no consulta a Esri.

### Cambiado

- En Sitio y mapa, «Capa satelital» pasa a **Mapas en línea de Esri** y controla también el mapa fuera del extracto. El aviso de privacidad de fábrica lo menciona; uno de fábrica guardado sin cambios se actualiza solo.

## [0.9.3] - 2026-11-01

### Agregado

- Límites de envío configurables (ADR 0018): en **Transmisión → Límites de envío** se cambian los segundos entre envíos y el tope por hora de mensajes, traceroute y pedidos de posición (de fábrica, 30 s y 20), y los de la administración remota de nodos (2 s y 60 por placa). Con 0 el límite no se aplica. Valen desde el próximo envío, sin reiniciar, y quedan en `[tx]` de config.toml y en la auditoría.
- `GET` y `PUT /api/v1/admin/tx/limits`.

### Cambiado

- Después de cada envío el panel cuenta la espera que informa el servidor (`wait_s`) en lugar de suponer 30 s. El aviso de límite dice dónde se cambia y en Mensajes y Nodos lleva un enlace a los límites.

### Corregido

- Las esperas por límite se miden con el reloj monotónico: si el reloj de la Pi saltaba hacia atrás al sincronizar la hora, la espera podía estirarse hasta una hora.

## [0.9.2] - 2026-11-01

### Agregado

- Traceroute como en la app: la ida y la vuelta salto por salto, con la señal (SNR) de cada tramo. En el panel (Cliente Meshtastic → Nodos y Transmisión) el pedido espera la respuesta y la muestra ahí mismo, junto con los anteriores; en el sitio público, la ficha del nodo suma **Ida y vuelta** a cada traceroute.
- `GET /api/v1/admin/traceroutes`: traceroutes de un nodo, incluidos los ocultos del sitio público.

### Corregido

- Los saltos que retransmiten sin anotarse en la ruta (firmware viejo o sin la clave del canal) se descartaban y corrían el SNR de los tramos siguientes. Ahora quedan como «Desconocido», cada SNR con su tramo, y no generan enlaces en el mapa.
- El traceroute desde Transmisión esperaba la respuesta hasta 300 s por salto (la misma función de la librería que trababa el Cliente Meshtastic en la 0.9.0). Ahora se manda y vuelve, igual que desde el cliente.

## [0.9.1] - 2026-10-28

### Corregido

- El Cliente Meshtastic de una placa quedaba cargando sin fin después de un traceroute o un pedido de posición a un nodo que no contestaba. Las funciones de la librería de Meshtastic esperan la respuesta hasta 300 s (posición) o 300 s por salto (traceroute, hasta 40 minutos) con la placa tomada, y reiniciar el conector no lo destrababa. Ahora el traceroute se manda sin esperar (la respuesta llega a Paquetes y al mapa), el pedido de posición espera hasta 45 s, y los dos van por la cola de la malla, aparte del estado y la configuración de la placa.
- Si una operación tiene tomada la placa más de 20 s, el panel lo avisa («la placa está ocupada») en lugar de quedarse cargando.
- Un nodo que contestaba NO_RESPONSE a un traceroute o a un pedido de posición podía cortar la lectura de la placa: la librería llamaba a `sys.exit` en ese hilo. Esas respuestas ya no pasan por la librería.

## [0.9.0] - 2026-10-28

### Agregado

- Administración remota de nodos propios por la malla, como en la app de Meshtastic (ADR 0017): pestaña **Remoto** del Cliente Meshtastic, con la clave pública de la placa para cargar en cada nodo, prueba de conexión, configuración sección por sección (lectura a pedido, copia antes de escribir y verificación después), nombre, posición fija y reinicio. A distancia no se cambian la sección Seguridad ni la región, el preset, la frecuencia o la transmisión de LoRa. Cada pedido espera hasta 40 s y no traba el resto del cliente; hay un límite de un pedido cada 2 s y 60 por hora por placa.
- Mensajes: tocar a quien escribió en un canal abre su ficha (modelo, rol, señal, saltos, batería) y desde ahí un mensaje directo, aunque nunca haya escrito por privado. Nodos y la ficha llevan también a **Administrar a distancia**.
- El estado de la placa informa su clave pública.

### Cambiado

- Los diálogos de nombre y posición fija de la placa se comparten con los de los nodos remotos.

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
