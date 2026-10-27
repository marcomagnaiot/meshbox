# ADR 0012 · Conector TCP (API del nodo por la red)

Estado: aceptada · 20/10/2026

## Contexto

El plan define tres conectores: MQTT, USB serie y reproducción. Las funciones directas sobre el nodo (leer su configuración, reiniciarlo, transmitir texto o traceroute, secciones 18.4 y 22) solo existen por USB. El gateway de las pruebas está en la red WiFi y no enchufado a la Pi. La librería `meshtastic` ofrece `TCPInterface` (puerto 4403) con la misma API que `SerialInterface`.

## Decisión

Se agrega el conector `tcp` (`host`, `port = 4403`), implementado como subclase del conector serie: comparte la siembra de nodos, los nombres de canal, la lectura de configuración enmascarada, el reinicio y la transmisión. Las recepciones quedan con `source = "tcp"`.

Verificado el 20/10/2026 contra un Heltec real: conexión, siembra de 13 nodos, el canal primario y dos canales privados, configuración con claves enmascaradas y recepción de paquetes por la librería. Esto valida además el código del conector USB, que es el mismo.

## Consecuencias

- La API del nodo atiende **un cliente a la vez**: mientras el conector TCP está activo, la CLI y el cliente web del nodo por WiFi no pueden conectarse. Por eso viene apagado por defecto y el modo recomendado sigue siendo MQTT.
- Si se usa junto con MQTT, la deduplicación unifica los paquetes (mismo `from` e `id`).
- La transmisión (sección 22) acepta el conector TCP igual que el USB.
