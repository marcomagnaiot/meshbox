# ADR 0018 · Límites de envío configurables

Estado: aceptada · 01/11/2026 · cambia la sección 22 del plan y los límites de los ADR 0015 y 0017

## Contexto

El plan (sección 22) fijó para la transmisión desde el panel un envío cada 30 s y 20 por hora. El Cliente Meshtastic (ADR 0015) usó el mismo límite para los mensajes, los pedidos de posición y el traceroute, y la administración remota (ADR 0017) sumó uno propio: un pedido cada 2 s y 60 por hora por placa. Los cuatro valores estaban en el código.

En el uso diario el de 30 s molesta: una conversación por el Cliente obliga a esperar medio minuto entre mensajes, cuando la app de Meshtastic no pone ninguna pausa. Configurar un nodo remoto lleva varias lecturas y escrituras seguidas, que también gastan el cupo de 60 por hora. El dueño del equipo pidió sacarlos o poder cambiarlos.

## Decisión

- Los valores pasan a `[tx]` de config.toml: `min_interval_s` (30) y `max_per_hour` (20) para mensajes, traceroute y pedidos de posición, entre todas las placas; `remote_min_interval_s` (2) y `remote_max_per_hour` (60) para la administración remota, por placa. Los de fábrica son los de antes y 0 deja ese límite sin efecto. El máximo de cada uno es 3600.
- Se cambian en **Transmisión → Límites de envío** (`GET` y `PUT /api/v1/admin/tx/limits`, solo administradores). El panel reescribe config.toml y el valor nuevo vale desde el próximo envío, sin reiniciar. Cada cambio queda en la auditoría (`tx.limits`).
- También se pueden cambiar desde el panel publicado en internet: los hace un administrador identificado, igual que transmitir.
- Cada respuesta de envío trae `wait_s`, los segundos hasta el próximo permitido, y el panel muestra esa cuenta en lugar de suponer 30 s. Un 429 por estos límites lleva `code: "send_limit"`, y el aviso dice dónde se cambian.
- Los envíos de la última hora se cuentan con el reloj monotónico. El reloj de la Pi salta al sincronizar la hora, y con el reloj de pared un salto hacia atrás podía estirar la espera hasta una hora.
- `[tx] enabled` sigue apagado de fábrica y solo se cambia en config.toml.

## Consecuencias

- Con todo en 0, el panel transmite tan seguido como se le pida. Lo que queda es la cola de transmisión de la placa: si la placa o la malla rechazan un envío, se ve como error del mensaje o del pedido.
- Los límites dejan de proteger contra una sesión de administrador robada, porque esa misma sesión puede sacarlos. Sirven para no ocupar el aire por apuro, y la auditoría registra quién los cambió.
- Los límites siguen siendo de meshbox y no se guardan en la placa: otra app conectada a la misma placa no los respeta.
- Con `[tx] enabled = false` la sección Transmisión no aparece, y los límites de la administración remota se cambian en config.toml (`remote_min_interval_s`, `remote_max_per_hour`).
