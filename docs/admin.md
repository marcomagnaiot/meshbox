# Panel de administración

Ruta `/admin` en el servidor de la red local (`http://<ip-de-la-pi>/admin`, o en el puerto 8090 en modo compartido) o, si se habilitó, en el hostname de administración detrás de Cloudflare Access. El servidor público no lo tiene.

En la red local el panel va por HTTP: el aviso arriba lo recuerda. Para entrar desde fuera de casa, usar el hostname con Access (HTTPS).

## Primer uso: asistente (`/setup`)

1. Solo en modo punto de acceso: elegir la red WiFi de la casa.
2. **Código de configuración** (8 caracteres). El instalador lo muestra al terminar; en una imagen de SD se escribe en `/boot/firmware/meshbox-codigo.txt`. Es de un solo uso y el asistente sin usuario se cierra a los 60 min del arranque (reiniciar lo reabre).
3. Idioma y zona horaria.
4. Usuario y contraseña del administrador (no hay contraseña por defecto).
5. Nombre del sitio, descripción y ubicación (centro y límites en el mapa).
6. Radio: **MQTT** (crea `meshbox-ingest` y la cuenta del gateway, y muestra los comandos para el Heltec con botón copiar) y/o **USB** (detecta puertos y prueba).
7. Canal público: nombre (por ejemplo `MediumFast`) y clave (por defecto `AQ==`).
8. Privacidad: aviso, ignorar nodos que llegan por MQTT, precisión.
9. Mapa base: descarga del extracto de la región.
10. Cloudflare (se puede hacer después).
11. Resumen y verificación: llegó al menos un paquete y el sitio responde.

## Secciones

| Sección | Qué permite | Rol |
|---|---|---|
| **Panel** | Estado de servicios (meshbox, mosquitto, cloudflared, privd), CPU, RAM, temperatura, disco, base, paquetes por minuto, conectores, clientes en vivo, último paquete, alertas recientes, versión | operador |
| **Radio** | Conectores MQTT, USB y reproducción: alta, edición, baja, reinicio, prueba, contadores, último error, grabación a archivo. Por USB: información del nodo (solo lectura), reiniciar nodo, liberar puerto | admin (ver: operador) |
| **Cliente Meshtastic** | Lo que ofrece la app para cada placa conectada por USB o TCP (ADR 0015): estado, batería en el tiempo, tráfico propio, mensajes de canales y directos con acuse, guardados en la base con lo leído por usuario (ADR 0016), nodos que ve la placa (mensaje directo, traceroute, pedir posición), canales, configuración completa por sección, nombre, posición fija (fijarla en un mapa satelital, reponerla o quitarla), reiniciar y apagar. Copia de la configuración antes de cada cambio (descargar y restaurar desde la LAN) y doble confirmación para lo peligroso; desde internet no se permiten los cambios peligrosos | operador mira; admin escribe y transmite |
| **Broker MQTT** | Cuentas por propósito (gateway, integración, diagnóstico) con contraseña generada que se muestra una vez, rotar, borrar, ACL vigente, comandos para el gateway, salida de eventos | admin |
| **Canales** | Nombre, clave (solo escritura) y si es público | admin |
| **Paquetes** | Captura en vivo y desde la base con filtros (tipo, origen, destino, canal, gateway, SNR, saltos, texto), detalle (campos, contenido decodificado, hexadecimal, recepciones por gateway), exportación CSV y JSONL | operador |
| **Nodos** | Tabla completa (incluye ocultos): ocultar (baja a pedido), marcar como fijo, nota interna, borrar historial | operador |
| **Mensajes** | Moderación: ocultar del sitio público (queda en la auditoría) | operador |
| **Alertas** | Reglas (palabra clave, umbral de telemetría, nodo caído o que vuelve, nodo nuevo, gateway sin paquetes, sistema), canales (Web Push, Telegram, webhook, MQTT), prueba, historial y confirmación | operador (canales: admin) |
| **Sitio y mapa** | Nombre, descripción, logo (PNG o WebP), color de acento, capa por defecto, centro y límites, capa satelital, umbrales de estado, idioma, aviso de privacidad, extracto del mapa (caja, zoom máximo, descargar, borrar) | admin |
| **Privacidad y retención** | Ignorar MQTT, precisión de posición, retención por tabla, purga inmediata | admin |
| **Cloudflare** | Modo token o API, estado, hostnames, administración remota con Access, desconectar (ver `docs/cloudflare.md`) | admin |
| **Red** | Estado WiFi, IP, hora y NTP. En un equipo dedicado además: buscar y conectar redes, olvidar, punto de acceso, nombre de host. En un equipo compartido es solo lectura (ADR 0004) | admin |
| **Plugins** | Lista, activar, ajustes (formulario generado del esquema), registros | admin |
| **Usuarios** | Alta y baja, roles, contraseñas, sesiones activas con cierre remoto, auditoría | admin |
| **Respaldo** | Respaldos (diario automático y manuales), descargar, restaurar (valida con `integrity_check`), exportar e importar configuración (secretos solo cifrados con contraseña) | admin |
| **Actualizaciones** | Versión actual y disponibles con notas, instalar (firma verificada por privd), volver a la anterior, búsqueda automática | admin |
| **Registros** | Journal de meshbox, mosquitto, cloudflared y privd, con filtros y en vivo | operador |
| **Transmisión** | Solo si `[tx] enabled = true` y hay conector USB o TCP: texto al canal y traceroute, con vista previa, límites (1 cada 30 s, 20 por hora) y auditoría | admin |

## Comportamiento común

- Toda acción que modifica pide confirmación si es destructiva o corta la conexión (reinicio, cambio de red, restauración, desconexión de Cloudflare) y queda en la **auditoría** (quién, qué, cuándo, desde qué IP).
- Los campos secretos (claves, tokens, contraseñas) son de solo escritura: al volver a abrir el formulario muestran `********`.
- Reiniciar o apagar la Pi desde el panel en un equipo compartido también corta los demás servicios que corren en él: el diálogo lo advierte.
