# Privacidad

meshbox publica en internet lo que los nodos Meshtastic ya transmiten **por el canal público** de la red local. Se toma como criterio la Ley 25.326 de protección de datos personales: la web amplía la audiencia de datos que ya son públicos en la radio, así que se publica lo mínimo, por el tiempo mínimo, y se atienden las bajas.

## Qué se guarda y qué se publica

| Dato | Se guarda | Se publica |
|---|---|---|
| Paquetes del canal público (broadcast) | Sí, completos | Sí: nodos, posiciones, telemetría, mensajes |
| Paquetes de canales no públicos | Solo el encabezado (de quién, a quién, cuándo, tipo) | No |
| Paquetes dirigidos a un nodo | Solo el encabezado | No |
| Mensajes de texto directos | **Nunca** (ni el texto ni el contenido cifrado) | No |
| Mensajes PKI (cifrados de punta a punta) | Solo el encabezado | No |
| Traceroute y routing dirigidos | Encabezado + rutas y SNR (para la capa de enlaces) | Rutas y enlaces |
| Nodos que entraron a la red por MQTT (otro gateway) | Paquete; **no** se crean ni actualizan nodos ni posiciones (`ignore_via_mqtt`) | Solo sus mensajes del canal público |
| Nodo ocultado por el administrador | **Nada** (solo un contador) | Nada |

Con el gateway en `mqtt.encryption_enabled false`, los mensajes directos de terceros ni siquiera llegan al broker: el firmware no los publica (ver `docs/heltec.md`).

## Precisión de posición

Por defecto la posición se guarda como llega (cada dueño elige su precisión en la app). Se puede configurar **degradar** a una grilla de N metros para los nodos que no estén marcados como fijos (**Privacidad y retención** en el panel).

## Retención

| Datos | Por defecto |
|---|---|
| Paquetes y recepciones | 14 días |
| Posiciones | 90 días (se guarda una nueva solo si el nodo se movió más de 25 m o pasaron más de 15 min) |
| Telemetría cruda | 30 días |
| Telemetría agregada por hora | 1 año |
| Telemetría agregada por día | sin límite |
| Mensajes del canal público | 365 días |
| Traceroutes | 90 días |
| Enlaces | 30 días sin verse |
| Alertas, notificaciones, auditoría | 365 días |
| Sesiones vencidas | se borran a diario |

La limpieza corre a las 03:30 (hora del sitio). **Privacidad y retención → Purgar ahora** la aplica en el momento.

## Bajas a pedido

1. En **Nodos**, buscar el nodo y marcarlo **oculto**: desde ese momento no se guarda ni se publica nada de él, y desaparece del sitio.
2. **Borrar historial** elimina posiciones, telemetría, mensajes, enlaces, traceroutes y paquetes de ese nodo.
3. Las dos acciones quedan en la auditoría.

## Visitantes del sitio

- Sin analítica ni rastreo; **sin cookies** en el sitio público (la única cookie es la de sesión del panel).
- Peticiones a terceros desde el navegador del visitante: solo la capa satelital de Esri, si está activada (se menciona en el aviso).
- En el panel y el asistente, los selectores de mapa piden además los nombres de lugares y rutas de Esri, y el buscador de lugares consulta Nominatim de OpenStreetMap con el texto buscado (una consulta por búsqueda). El sitio público no lo hace.
- Cloudflare intermedia todo el tráfico público.
- Suscripciones push: se guarda solo lo necesario para enviar (endpoint y claves de la suscripción).

## Aviso de privacidad

Se edita en **Sitio y mapa → Aviso de privacidad** (Markdown simple: títulos, listas, negrita, cursiva, enlaces). Aparece en `/acerca`. El servidor lo convierte en bloques con una lista blanca; el navegador nunca recibe HTML.
