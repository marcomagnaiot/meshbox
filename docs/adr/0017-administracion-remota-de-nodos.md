# ADR 0017 · Administración remota de nodos propios por la malla

Estado: aceptada · 28/10/2026 · amplía el ADR 0015

## Contexto

El Cliente Meshtastic del panel (ADR 0015) administra la placa conectada por USB o TCP. Los nodos que hacen de repetidor en torres o techos no se alcanzan así: para cambiarles algo hay que subir con el celular o bajarlos. La app de Meshtastic resuelve esto con la administración remota (firmware 2.5 en adelante): manda mensajes de administración (`ADMIN_APP`) cifrados con PKI a un nodo que tiene cargada la clave pública del administrador en `security.admin_key`.

## Decisión

- Pestaña **Remoto** en el Cliente Meshtastic, solo para administradores, y accesos desde **Nodos** y desde la ficha de un nodo en **Mensajes**. Muestra la clave pública de la placa conectada para copiarla en cada nodo (una vez, con la app y por Bluetooth o USB) y, para el nodo elegido, lo que la placa sabe de él sin transmitir.
- Los pedidos salen como los arma la librería con `--dest`: `ADMIN_APP`, `want_ack`, `want_response`, `pki_encrypted` y el canal `admin` si la placa tiene uno (administración heredada). La clave de sesión del nodo (`session_passkey`, 300 s en el firmware) la guarda la librería con cada respuesta; los cambios la llevan, y si vence (`ADMIN_BAD_SESSION_KEY`) se renueva con `SESSIONKEY_CONFIG` y se repite el pedido una vez.
- Cada pedido espera su respuesta con un tope de 40 s, no los 300 s de la librería, y corre en la cola de la malla de cada placa (`<conector>:malla`, la misma del pedido de posición y el traceroute desde la 0.9.1): mientras se espera a un nodo lejano, el estado y la configuración de la placa siguen respondiendo. Si la cola de la placa está tomada más de 20 s, el panel avisa que está ocupada en lugar de quedarse esperando.
- Operaciones: probar la conexión (datos del equipo, que el nodo solo entrega con la clave autorizada), leer una sección de `Config` o `ModuleConfig`, escribirla, cambiar el nombre (se parte del usuario que tiene el nodo para no pisar licencia ni «no mensajeable»), fijar la posición y reiniciar.
- Las secciones se leen de a una y solo a pedido, para no ocupar el aire. Una lectura de menos de 120 s sirve de base para escribir; si no, se lee de nuevo antes. Escribir aplica los cambios sobre esa copia con las mismas reglas que la placa local (secretos enmascarados, campos peligrosos con doble confirmación y solo desde la red local), guarda la sección leída en `<backups>/radio/remoto/` (30 por nodo, 0600) y vuelve a leer para verificar. Si el nodo no contesta la verificación (el cambio lo reinicia), queda «sin verificar».
- No se cambian a distancia la sección **Seguridad** (un error en `admin_key` deja el nodo sin administración) ni los parámetros de radio de **LoRa**: región, preset, ancho de banda, factor de dispersión, tasa de código, frecuencia, canal, transmisión y `serial_hal_only`. Si no coinciden con los de la placa, el nodo deja de oírla y hay que ir hasta él. Potencia, saltos y el resto sí se cambian.
- No dependen de `[tx] enabled`: son pedidos dirigidos y cifrados a nodos que ya confían en la placa, no mensajes a la malla. Tienen su propio límite, un pedido cada 2 s y 60 por hora por placa (cada uno son de 1 a 3 paquetes), y quedan en la auditoría los cambios, el nombre, la posición y los reinicios.
- Las respuestas de administración son paquetes dirigidos a la placa: el proceso de paquetes guarda solo su encabezado (privacidad, sección 10.5), así que las claves de WiFi o MQTT del nodo no quedan en la base.

## Consecuencias

- Los repetidores se configuran y se reinician desde el panel, también desde afuera de casa con el panel publicado (salvo los cambios peligrosos).
- Hace falta cargar la clave de la placa en cada nodo antes de llevarlo a su lugar. Si se cambia la placa conectada, hay que cargar la nueva (el nodo admite hasta tres claves).
- La placa tiene que conocer la clave pública del nodo (su NodeInfo); hasta que la recibe, los pedidos fallan con `PKI_SEND_FAIL_PUBLIC_KEY` y el panel lo explica.
- Las copias de las secciones de nodos remotos no se restauran desde el panel: son referencia. Si un cambio deja al nodo fuera de la red, tampoco recibiría la restauración.
- Canales del nodo remoto, módulos de solo lectura (`statusmessage`, `tak`) y apagado remoto quedan fuera por ahora.
