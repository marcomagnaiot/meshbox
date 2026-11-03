# ADR 0022 · Mensajes nuevos en la barra del panel

Estado: aceptada · 02/11/2026 · amplía la sección 18 del plan y el ADR 0016

## Contexto

Los mensajes de las placas del Cliente Meshtastic (ADR 0016) se veían solo en **Cliente Meshtastic → Mensajes**, placa por placa. Con el panel abierto en otra sección no había forma de enterarse de que llegó uno, y un mensaje directo podía quedar días sin leer.

Con dos placas en la misma red, por ejemplo una en el techo por TCP y otra por USB, cada mensaje queda guardado una vez por cada placa que lo oyó. En la estación de prueba, de los 143 mensajes que recibió la segunda placa en una semana, 110 eran los mismos que recibió la primera. Además, un canal puede tener otro número en cada placa: ViedmaMesh era el 1 en una y el 2 en la otra.

## Decisión

- `GET /api/v1/admin/inbox` devuelve, para el usuario de la sesión, las conversaciones con mensajes sin leer de todas las placas y los últimos recibidos. `POST /api/v1/admin/inbox/read` deja leído todo lo que había al consultar (`upto`), y lo que llegó después sigue sin leer. Lo leído es el mismo del Cliente, por usuario, y los permisos son los de leer los mensajes.
- Un mensaje oído por varias placas (mismo remitente y mismo número de paquete) cuenta una vez, en la placa que lo guardó primero, y leído en cualquiera de ellas está leído. Lo que mandó una placa propia y oyó otra no es un mensaje nuevo. Las conversaciones se juntan por el nombre del canal o por el nodo del directo, y se abren en la placa del último mensaje sin leer.
- La barra del panel lleva un ícono con la cuenta en todas las secciones, que abre la lista por conversación. El Panel principal muestra los últimos mensajes recibidos con los sin leer marcados, y el título de la pestaña lleva la cuenta adelante. Cada mensaje lleva a su conversación con `/admin/cliente?placa=<conector>&conv=<conversación>`.
- El panel consulta cada 10 s con la pestaña a la vista y cada 60 s en segundo plano. El servidor no lee el historial entero: recorre el índice (placa, conversación) de a una conversación, revisa como mucho los 500 mensajes sin leer más nuevos de cada una y cuenta hasta 100 (más se muestra como «99+»). La cuenta se guarda por usuario hasta que llega un mensaje o cambia lo leído, y se rehace igual cada minuto por los borrados de la retención.

## Alternativas descartadas

- Avisar por el stream del panel (SSE): sería instantáneo, pero suma una conexión abierta por pestaña. En la red local el panel va por HTTP/1.1, y el navegador abre como mucho seis conexiones por equipo entre todas las pestañas: con varias pestañas del panel abiertas se trabarían los pedidos. Diez segundos de demora alcanzan para no perder un mensaje.
- Contar con una sola consulta agrupada: con 50.000 mensajes tarda 20 ms en una PC, unos 200 ms en la Pi Zero 2 W, y el panel la repetiría cada 10 s en cada pestaña.
- Contar por placa, como la lista de conversaciones del Cliente: con dos placas en la misma red cada mensaje contaría dos veces y, leído en una, seguiría como nuevo en la otra.

## Consecuencias

- Más de 100 sin leer en una conversación se muestra como «99+», sin el número exacto.
- Un mensaje sin número de paquete no se reconoce entre placas: cuenta una vez en cada una.
- La lista de conversaciones de cada placa en el Cliente sigue contando por placa.
