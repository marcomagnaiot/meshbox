# ADR 0011 · Un gateway que ya retransmite conserva su rol y su potencia

Estado: aceptada · 20/10/2026

## Contexto

La guía del gateway (`docs/heltec.md`) recomienda, para un nodo interior dedicado a MQTT, `device.role CLIENT_MUTE` y `lora.tx_power 10`, suponiendo que otro nodo en el techo retransmite para la red. Muchas veces el nodo disponible para hacer de gateway es justamente el del techo: `CLIENT_BASE` o `ROUTER`, con potencia alta, retransmitiendo para la red local. Pasarlo a `CLIENT_MUTE` y 10 dBm cortaría ese servicio a otros usuarios.

## Decisión

En un nodo que retransmite para la red se configura **solo lo necesario para la Pi**: MQTT (IP de la Pi, cuenta del gateway, `encryption_enabled false`, `json_enabled false`, `proxy_to_client_enabled false`, raíz y `map_reporting_enabled true`) y, en el canal 0, `uplink_enabled true` y `downlink_enabled false`. Rol, potencia, región, preset y canales quedan como estaban; los canales privados mantienen `uplink_enabled false` y nunca llegan al broker.

### Informe de mapa y posición

Comprobado contra el código del firmware 2.7 (`src/mqtt/MQTT.cpp`):

- La precisión del informe de mapa solo admite 12 a 15 bits; un valor fuera de rango vuelve al de fábrica (14, ±1,4 km). El firmware la lee al arrancar.
- El informe sale solo si la posición local en memoria (`localPosition`) no es 0,0. Un nodo sin GPS con posición fija no la repone ahí al arrancar: **después de cada reinicio hay que volver a fijar la posición** (`--setlat`, `--setlon`, `--setalt`, o el botón Fijar posición del panel, ADR 0015) para que sigan los informes.
- Con la configuración de fábrica un gateway casi no origina paquetes propios (NodeInfo cada 3 h, telemetría apagada). Conviene `telemetry.device_telemetry_enabled true` con `device_update_interval 3600` y `mqtt.map_report_settings.publish_interval_secs 3600`.

El informe de mapa va solo al broker de la Pi: meshbox toma de ahí la posición (con esa precisión), el firmware, la región y el preset del gateway, y marca el gateway como activo por el tráfico que pasa por él.

## Consecuencias

- Si más adelante se instala un nodo interior dedicado, se le aplica la configuración completa de la guía y el del techo vuelve a ser solo repetidor (se apaga su MQTT).
- La contraseña de la cuenta del gateway la genera el panel y se muestra una sola vez; meshbox no la guarda en claro.
