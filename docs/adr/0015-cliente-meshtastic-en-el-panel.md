# ADR 0015 · Cliente Meshtastic en el panel: leer y escribir la configuración de la placa

Estado: aceptada · 25/10/2026

## Contexto

Hasta ahora meshbox solo escuchaba la placa conectada por USB o por la red (TCP, ADR 0012): la usaba como gateway y, con `[tx] enabled`, mandaba un texto o un traceroute (sección 22). Para cambiar algo de la placa (rol, potencia, canales, MQTT, posición fija) había que llevar el teléfono con la app o la PC con la CLI, y muchas veces la placa está en un techo, alimentada por un panel solar.

Hace falta una pestaña aparte que haga de cliente Meshtastic: estado, nodos que ve la placa, mensajes de los canales y directos, acciones (reiniciar, fijar posición, traceroute, pedir posición), la batería en el tiempo y, en una segunda etapa, la edición de canales y de la configuración, con copia antes de cada cambio y doble confirmación para lo peligroso.

## Decisión

### Lectura y acciones (`/api/v1/admin/radio/{conector}`)

- Usa la misma conexión del conector (la librería `meshtastic`): no abre otra. Cada operación corre en un hilo y de a una por placa (un candado por conector), porque la librería no es segura para usos simultáneos.
- La librería llama a `sys.exit` ante algunos errores: se captura y vuelve como 502.
- Estado, nodos y configuración se pueden mirar con rol operador; la configuración completa y todo lo que escribe o transmite es de administradores.
- Los mensajes (de todos los canales y directos) se guardaban solo en memoria, los últimos 500 por placa. **Reemplazado por el ADR 0016**: ahora quedan en la base, con retención propia. No son el historial público de la sección 17. Los enviados muestran el acuse: `enviado` → `retransmitido` (otro nodo lo repitió, el acuse implícito) → `entregado` (confirmó el destino, en directos) o el error del ruteo.
- Enviar, pedir posición y traceroute transmiten: respetan `[tx] enabled` y el mismo límite (1 cada 30 s, 20 por hora).
- La batería en el tiempo sale de la telemetría que meshbox ya guarda de la placa.

### Escritura (segunda etapa)

- La configuración se describe desde los descriptores de protobuf (`LocalConfig` y `LocalModuleConfig` de la versión de la librería instalada), así el panel muestra todos los campos sin mantener una lista a mano. Se escribe con `writeConfig`, solo las secciones que la librería sabe escribir; `statusmessage` y `tak` se muestran sin editar.
- **Sin transacción para una sola sección**: medido en un Heltec V3 con 2.7.26, al cerrar una transacción (`commitSettingsTransaction`) el firmware reinicia la placa siempre. Suelto, `writeConfig` deja que el firmware decida: cambiar `lora.hop_limit` (ida y vuelta) no la reinició, y `display.screen_on_secs` sí (el firmware avisa `rebooted` a los 8 s y meshbox se reconecta solo). Restaurar una copia usa la transacción, para reiniciar una sola vez al final, y solo si alguna sección difiere.
- Lo que la librería guarda de cada nodo trae objetos protobuf (`raw` en la posición y el usuario): se limpian antes de responder.
- Se manda solo lo que cambió. Las claves (WiFi, MQTT, PIN de Bluetooth, claves de seguridad) salen enmascaradas y no cambian si se reenvía la máscara; las claves en bytes no se editan desde el panel.
- **Copia previa**: antes de cada escritura se guarda la configuración completa de la placa (con claves) en `<backups>/radio/`, con permisos 0600, y quedan las últimas 30 por placa. Restaurar escribe solo las secciones, canales y nombre que difieren, y antes guarda una copia del estado actual.
- **Doble confirmación**: los campos que pueden dejar la placa fuera de la red o inalcanzable (región, preset y parámetros de radio, rol, `tx_enabled`, ahorro de energía, MQTT, red, Bluetooth, seguridad, serie; en canales el nombre, la clave, la bajada por MQTT y la subida del primario) devuelven 409 `danger_confirmation_required` con la lista de campos, y el panel pide escribir una palabra antes de repetir con `confirm_danger`.
- **Desde internet** (servidor remoto, ADR 0014): no se permiten los cambios peligrosos, borrar canales, apagar la placa ni descargar o restaurar copias (tienen las claves). Sí los cambios inocuos, mensajes y reiniciar.
- Todo lo que escribe queda en la auditoría.

### Posición fija al arrancar

Sin GPS, el firmware 2.7 no vuelve a cargar la posición fija en memoria después de un reinicio y deja de mandar el informe de mapa (ADR 0011). Al conectarse, meshbox repone la posición guardada una vez por cada arranque de la placa (lo reconoce por el tiempo encendida que informa la placa).

## Consecuencias

- Cambiar la configuración de una placa lejana ya no requiere subir al techo ni llevar el teléfono, pero un error puede dejarla fuera de la red: por eso la copia previa, la doble confirmación y el bloqueo desde internet. Un cambio de región o de preset que la deja sin contacto con meshbox solo se arregla con la placa a mano.
- ~~Los mensajes del cliente se pierden al reiniciar meshbox.~~ Desde el ADR 0016 quedan en la base.
- Si la librería cambia los protobuf, el panel muestra los campos nuevos sin cambios en meshbox; los campos peligrosos nuevos no piden doble confirmación hasta agregarlos a la lista (`meshbox/radio/schema.py`).
