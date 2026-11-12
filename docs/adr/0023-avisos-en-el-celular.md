# ADR 0023 · Panel instalable y avisos de mensajes en el celular

Estado: aceptada · 12/11/2026 · amplía el ADR 0022 y la sección 19.2 del plan, y cambia el ADR 0014

## Contexto

La barra del panel avisa los mensajes nuevos de las placas (ADR 0022), pero solo con el panel abierto. Fuera de la casa, un mensaje directo a la placa del techo o a la de la casa se ve recién al entrar al panel.

El sitio público ya es una PWA con push para las alertas públicas, y las alertas tienen una suscripción de administración. En el hostname de administración por internet (ADR 0014) eso no servía: el servidor mandaba un service worker que se daba de baja, para que la caché de la app no mostrara el mapa en `/` en lugar de pasar al panel. Sin service worker el navegador no ofrece instalar el panel ni puede recibir push.

## Decisión

**Service worker propio del hostname de administración.** El servidor remoto sirve, en las mismas direcciones que el de la app (`/service-worker.js` y `/sw.js`), uno escrito a mano que:

- no guarda nada en caché y borra la que haya dejado el de la app, así `/` sigue pasando por el servidor;
- responde las navegaciones desde la red y, sin conexión, con una página que dice que no hay conexión con el panel;
- muestra los avisos push y, al tocarlos, abre la dirección del aviso en el panel.

La página lo registra apenas sabe que está en el servidor remoto. El manifiesto de ese hostname es el del panel (`id` y `start_url` en `/admin`, nombre «<sitio> · Panel», accesos directos a Mensajes y Alertas), así que se instala aparte del mapa.

**Lo que recibe cada equipo.** Cada suscripción de administración guarda dos preferencias (migración 0004):

- `alerts`: las alertas de las reglas, como hasta ahora (1 por defecto, así las suscripciones viejas siguen igual);
- `messages`: los mensajes que llegan a las placas del Cliente: `off` (por defecto), `dm` (solo directos) o `all` (directos y canales).

Se eligen en el Panel («Avisos en este equipo») y en el menú de mensajes nuevos, con `PUT /api/v1/admin/notifications/device`. `POST .../device/state` dice qué recibe el equipo, `DELETE .../device` lo da de baja y `POST .../device/test` le manda un aviso de prueba. Con las dos cosas apagadas, el equipo se da de baja. Permisos: los de leer los mensajes (operador y administrador).

**El aviso.** El historial de mensajes (ADR 0016) avisa a sus oyentes cada mensaje que entra, y el avisador (`radio/notify.py`) manda el push:

- con urgencia alta (el teléfono lo entrega aunque esté en reposo) y vigencia de un día;
- un mensaje que oyen dos placas avisa una vez (se recuerdan los últimos 500 paquetes por remitente y número), y lo que manda una placa propia y oye otra no avisa;
- el título es el remitente (y la placa, si hay más de una) en un directo, o `# canal · remitente`; el cuerpo es el texto;
- la etiqueta es la conversación: cada mensaje nuevo reemplaza el aviso anterior de esa conversación y vuelve a sonar;
- al tocarlo se abre la conversación en el Cliente (`/admin/cliente?placa=…&conv=…`).

El texto viaja cifrado de punta a punta hasta el navegador (Web Push), así que el servicio de push del navegador no lo lee.

## Consecuencias

- El panel se puede instalar en el celular y avisa como cualquier otra app, aunque esté cerrado.
- En iPhone y iPad, push funciona solo con el panel agregado a la pantalla de inicio (iOS 16.4 o posterior). El panel lo explica en vez de ofrecer el selector.
- Los navegadores en modo incógnito no admiten push.
- Si el teléfono está sin conexión más de un día, los avisos de ese tiempo se pierden. Los mensajes quedan igual en el historial y en la cuenta de sin leer.
- En la red local, el panel usa el service worker de la app, que también muestra los avisos de mensajes y abre la conversación.
