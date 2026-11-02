# ADR 0020 · Respuestas a pedidos de la estación

Estado: aceptada · 02/11/2026 · amplía la sección 10.5 del plan

## Contexto

Los paquetes dirigidos a un nodo se guardan solo con su encabezado y no se procesan, salvo traceroute y routing (sección 10.5). Eso alcanzaba a las respuestas de los pedidos de posición o de NodeInfo que la estación manda desde el panel: el nodo contesta por mensaje directo al gateway que preguntó. El 02/11/2026 un router a 247 km contestó dos pedidos de posición y no apareció en el mapa. Al reconectar la placa, en cambio, la siembra sí toma esa misma posición de la base de nodos del gateway.

En la misma siembra apareció otro problema. Para un nodo del que no llegó NodeInfo, la librería de Meshtastic arma un usuario provisorio («Meshtastic abcd», «abcd», modelo UNSET), y la siembra lo copiaba encima del nombre real.

## Decisión

- Una respuesta de posición o de NodeInfo (con `request_id`) dirigida al gateway que la recibió, por un canal público, se decodifica y actualiza el nodo igual que un paquete público: la posición, con la política de precisión de siempre, y el nombre, el rol y el modelo. El paquete se sigue guardando solo con su encabezado y no se publica.
- El firmware contesta un pedido de posición con la precisión que el nodo tiene configurada para el canal del pedido, y no contesta si la tiene en 0.
- La siembra y la lista de nodos del Cliente Meshtastic reconocen el usuario provisorio de la librería y no lo usan. La siembra borra el que haya quedado de antes, que se reconoce por el modelo UNSET.

## Alternativas descartadas

- Esperar a que el nodo transmita su posición a todos: los routers lejanos lo hacen pocas veces, y con un conducto troposférico pasajero puede no llegar nunca.
- Usar también las posiciones que alguien manda por directo sin que se las pidan: es una decisión de quien la manda y puede ser privada.

## Consecuencias

- Pedir la posición desde el panel ubica en el mapa a nodos que nunca transmitieron su posición a la red local.
- Si un nodo contesta con más precisión de la que transmite a todos, la respuesta se usa igual. La degradación configurable de **Privacidad y retención** sigue valiendo para los nodos no fijos.
