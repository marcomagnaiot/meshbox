# Configuración del Heltec (gateway)

meshbox recibe los paquetes de la red Meshtastic desde un nodo "gateway". Hay dos modos, que se pueden usar a la vez:

| Modo | Cómo llega a la Pi | Cuándo conviene |
|---|---|---|
| **MQTT** | El nodo se conecta por WiFi al Mosquitto de la Pi y publica cada paquete | El nodo está lejos de la Pi o en otro lugar de la casa |
| **USB** | El nodo va enchufado al micro-USB de datos de la Pi | El nodo está al lado de la Pi; no depende del WiFi |

## Modo MQTT

### 1. Crear la cuenta del gateway

En el panel: **Broker MQTT → Nueva cuenta → propósito "gateway"**. El panel genera una contraseña de 24 caracteres y la muestra **una sola vez** junto con los comandos listos para copiar. Si se pierde, se rota la cuenta y se vuelven a cargar.

### 2. Configurar el nodo

Con la [CLI de Meshtastic](https://meshtastic.org/docs/software/python/cli/usage/) (`uv tool install meshtastic`). Por USB se usa `--port COM5` (Windows) o `--port /dev/ttyUSB0`; si el nodo ya está en el WiFi, `--host <ip-del-nodo>`. Cada comando con `--set` reinicia el nodo.

```powershell
meshtastic --host <ip-del-nodo> --set mqtt.enabled true --set mqtt.address <ip-de-la-pi> `
  --set mqtt.username gw-heltec --set mqtt.password "<generada>" `
  --set mqtt.encryption_enabled false --set mqtt.json_enabled false --set mqtt.tls_enabled false `
  --set mqtt.proxy_to_client_enabled false --set mqtt.root msh/AR/<zona> --set mqtt.map_reporting_enabled true

meshtastic --host <ip-del-nodo> --ch-index 0 --ch-set uplink_enabled true --ch-set downlink_enabled false
```

Por qué cada valor:

| Ajuste | Valor | Motivo |
|---|---|---|
| `mqtt.address` | **IP literal** de la Pi | Desde el firmware 2.5 el gateway descarta los paquetes de nodos que no marcaron "OK to MQTT", **salvo** que el broker esté en una IP privada. Con un nombre de host no se detecta como privada. |
| `mqtt.encryption_enabled` | `false` | Publica el paquete ya decodificado. Los mensajes directos de terceros (PKI) no se pueden decodificar y entonces **no se publican**: nunca llegan al broker. |
| `mqtt.json_enabled` | `false` | La salida JSON está obsoleta; meshbox usa protobuf. |
| `mqtt.map_reporting_enabled` | `true` | El gateway publica cada hora su firmware, región, preset y cantidad de nodos en línea; meshbox lo muestra en el panel. Con un broker propio no sale de la casa. |
| canal 0 `uplink_enabled` | `true` | Solo el canal público sube al broker. |
| canal 0 `downlink_enabled` | `false` | Nada que llegue por MQTT se transmite por radio (evita inyección de paquetes). |
| otros canales | `uplink_enabled false` | Los canales privados nunca llegan a la Pi. |

Opcional, **solo si el nodo no tiene que retransmitir** (hay otro nodo en el techo que lo hace):

```powershell
meshtastic --host <ip-del-nodo> --set device.role CLIENT_MUTE --set lora.tx_power 10
```

### 3. Verificar

- En el registro de Mosquitto aparece `New client connected ... as !a1b2c3d4 (... u'gw-heltec')`.
- En el panel, **Radio** muestra el conector `mqtt-local` en estado *conectado* y el contador de paquetes sube.
- Desde la PC, con la cuenta de diagnóstico: `uv run meshbox record --connector mqtt-pi --config dev/config.toml` (graba en `dev/data/rec/`) y `uv run meshbox inspect <archivo>`.

Una red con poco tráfico puede pasar varios minutos sin paquetes: la telemetría de cada nodo sale cada 30 min y la información de nodo cada 3 h.

### Al activar el WiFi

En el ESP32 activar el WiFi **apaga el Bluetooth**: el nodo deja de verse desde la app del celular por BT. Se administra por la red (`meshtastic --host`, o el cliente web del nodo en `http://<ip>`) o por USB.

## Modo USB

```powershell
meshtastic --port COM5 --set device.role CLIENT_MUTE --set lora.tx_power 10   # solo si no retransmite
```

- Va al micro-USB de **datos** de la Pi Zero 2 W con un adaptador OTG. La fuente de la Pi tiene que ser de 5 V y 2,5 A.
- En el panel: **Radio → Nuevo conector → USB**. La ruta estable del puerto está en `/dev/serial/by-id/` (el panel la lista).
- La API del nodo atiende **un cliente a la vez**: mientras meshbox usa el puerto, la CLI no puede abrirlo. **Radio → Liberar puerto** detiene el conector; después se reinicia desde el mismo lugar.
- Por USB el panel muestra la configuración del nodo en solo lectura y permite reiniciarlo (18.4).

## Común

- Firmware actual para `heltec-v4` (no el de V4-R8).
- Canal primario igual al de la red de la zona: por ejemplo **MediumFast** (preset `MEDIUM_FAST`).
- **Limitación conocida:** el sistema ve lo que recibe el gateway. Un paquete que llega al techo sin saltos disponibles no se retransmite y el gateway no lo oye. Se puede medir comparando la lista de nodos del panel con la de la app conectada al nodo del techo.
