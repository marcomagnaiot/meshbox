# ADR 0016 · Historial de mensajes del cliente Meshtastic en la base

Estado: aceptada · 26/10/2026 · reemplaza la parte de mensajes del ADR 0015

## Contexto

El ADR 0015 dejó los mensajes del cliente (todos los canales y los directos de cada placa) solo en la memoria de meshbox, los últimos 500 por placa, para no grabar en disco los mensajes privados. En la práctica se perdían con cada reinicio de meshbox (actualizaciones), con cada reinicio del conector desde el panel y con cada corte de luz. Un mensaje enviado desde la PC no aparecía después en el celular si entre medio se había instalado una versión.

Hace falta que la Pi guarde los mensajes aunque nadie tenga el panel abierto, y que el historial se vea igual desde cualquier dispositivo, en cualquier momento y después de reiniciar.

## Decisión

- Tabla `radio_messages` (migración 0003): cada mensaje de texto que entra o sale por una placa conectada por USB o TCP, con la placa (id del nodo), el conector, la conversación (`ch:<índice>` o `dm:<nodo>`), hora, canal, texto, señal, saltos y estado del envío. Se guarda por placa: si el conector cambia de nombre, el historial sigue con la placa.
- Las escrituras pasan por el escritor de la base, en orden: el acuse de un enviado se aplica después de guardarlo, y si llega antes (un error inmediato de la placa) se guarda aparte y se aplica al guardar el mensaje. Un mismo paquete repetido (al reconectar) queda una sola vez.
- Lo leído se guarda por usuario y conversación (`radio_reads`): si se lee en la PC, en el celular figura como leído.
- La API devuelve los últimos 1000 mensajes de la placa, lo nuevo desde un número (sondeo cada 3 s) y páginas anteriores.
- Retención propia, `[retention] radio_messages` (365 días por defecto), en Privacidad y retención; se aplica en la tarea diaria como el resto. Un administrador puede borrar el historial de una placa desde el panel.

## Privacidad

Esto cambia lo decidido en el ADR 0015: los textos de los canales privados y de los mensajes directos quedan escritos en la tarjeta de la Pi y en sus respaldos diarios de la base. Para acotarlo:

- solo los lee la API de administración (operadores y administradores, como antes en memoria); el sitio público y su API no tocan estas tablas;
- se borran solos al vencer la retención y se pueden borrar todos de una placa;
- los respaldos de la base quedan en la Pi y descargarlos sigue siendo de administradores.

## Consecuencias

- El historial sobrevive a actualizaciones, reinicios de meshbox o del conector y cortes de luz.
- Los mensajes que llegan a la placa mientras meshbox está detenido se pierden salvo los que la placa guarda en su cola para el próximo cliente (pocos); al reconectar, meshbox los recibe y los guarda con su hora original.
- Los mensajes que había en memoria antes de esta versión no se migran (se pierden en el reinicio de la actualización).
