# ADR 0008 · Grabaciones sintéticas mientras no haya grabaciones del Heltec

Estado: aceptada · 20/10/2026

## Contexto

El plan pedía grabar 24 h del Heltec interior en modo MQTT (`encryption_enabled = false`) y 1 h con `true`. Todavía no hay gateway configurado, y el desarrollo no puede esperar.

## Decisión

1. `meshbox simulate generate` (`devtools/sim.py`) genera una red simulada y determinista (semilla fija) alrededor de Viedma con los mensajes protobuf **reales** de la librería instalada: nodos con roles distintos, posiciones fijas y móviles, telemetría de dispositivo, ambiental y de energía, mensajes del canal público (incluido un SOS), un mensaje directo (que nunca debe guardarse), `NEIGHBORINFO`, `TRACEROUTE`, `ROUTING`, informes de mapa, puntos de interés, paquetes cifrados con la clave por defecto y con una clave privada, un paquete PKI, paquetes que entraron por MQTT y basura. Dos gateways reciben copias para probar deduplicación y recepciones.
2. El descifrado se verifica además contra paquetes cifrados **reales** emitidos por firmware, tomados del broker público de Meshtastic (solo lectura, solo telemetría de dispositivo, sin textos ni posiciones), para no validar el algoritmo contra sí mismo.
3. Cuando existan grabaciones del Heltec se agregan a `tests/fixtures/` y las pruebas con valores de referencia se amplían con ellas.

## Consecuencias

El criterio del plan ("al menos un paquete de cada portnum presente en la red local") queda cubierto por la simulación; la verificación con una red real queda pendiente hasta tener el gateway.
