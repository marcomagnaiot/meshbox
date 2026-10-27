# Referencias de diseño (16.8, punto 1)

Resumen de lo que se tomó de cada referencia para el sitio público y el panel. Los sitios de
redes locales se miraron solo como referencia visual (no publican licencia).

## Apple: "Meet Liquid Glass" (WWDC25) y Apple Maps

- El vidrio pertenece a la **capa de navegación** que flota sobre el contenido; el contenido
  (listas, tablas, texto largo) no es de vidrio. → Glass solo en barra, controles, paneles y
  pestañas; tarjetas con rellenos sutiles adentro (16.1.1-2).
- **Nada de vidrio sobre vidrio**. → Menús, diálogos, avisos y el aviso SOS son sólidos porque
  abren encima de paneles de vidrio.
- La legibilidad la garantiza una capa que oscurece o aclara detrás del texto, adaptada al fondo.
  → `--scrim`, medido contra el peor fondo (satélite claro) y subido de 0,35 a 0,6.
- Respetar "reducir transparencia" y "aumentar contraste". → Modo sólido manual,
  `prefers-reduced-transparency` y `prefers-contrast: more`.
- Apple Maps: hoja inferior con tres alturas, la búsqueda arriba de todo y el mapa siempre vivo
  detrás; al elegir un lugar la hoja sube a media altura y el mapa centra el lugar en el espacio
  libre. → Panel inferior propio con anclajes 96 px / mitad / 92 % y relleno del mapa.

## Google Maps

- Fila de chips de filtro con desplazamiento horizontal bajo el buscador tipo píldora. → Chips
  en la misma superficie que el buscador (una sola superficie de vidrio).
- Pila vertical de controles a la derecha (capas, brújula que aparece girada, mi ubicación). →
  Pila única con botones de 44 px.
- Selector de capas con vista previa y capas de detalle aparte. → Base (oscuro, claro, satélite) y
  capas de datos con interruptores y leyenda en el mismo menú.

## Flightradar24

- Cada objeto en vivo es un ícono simple sobre un mapa base apagado; el foco está en los datos.
  → Mapa base de Protomaps atenuado (menos saturación, etiquetas discretas, puntos de interés solo
  de cerca).
- Al elegir un objeto, ficha lateral (PC) o inferior (celular) con datos densos y su recorrido en
  el mapa. → Ficha a la derecha en PC y a media altura en el celular, con recorrido y reproducción.
- Indicador de datos en vivo siempre visible. → Indicador "en vivo / reconectando / sin conexión".

## Windy

- Capas superpuestas sobre el mapa con una leyenda compacta y un control de tiempo abajo. →
  Leyenda en el menú de capas y deslizador de tiempo con reproducción en el historial.
- Animaciones discretas que no tapan el mapa. → Actividad en vivo como pulso breve y trazo hacia
  el gateway, sin animar con movimiento reducido.

## Material 3: hojas inferiores

- Hoja estándar (no modal) con asa visible, estados expandido, parcial y oculto, gesto de arrastre
  y equivalente accesible para quien no puede arrastrar. → El asa es un botón con
  `aria-expanded`, Enter/Espacio y flechas; el contenido oculto queda `inert`.
- Esquinas superiores de 28 dp. → `--r-xl` de 28 px.

## Redes Meshtastic locales

- **somesh.com.ar (SOMesh)**: panel de estado con contadores por frescura (activos, última hora,
  24 h, más de 24 h, total), buscador de nodos, últimos nodos vistos y los mensajes del canal
  MediumFast. → Mismo corte de estados (17.3) en el resumen, con forma además de color; el chat del
  canal público es central.
- **mesh.surc.ar (surc.AR, General Roca)**: pestañas Mapa / Chat / Alertas, contadores
  (activos, > 1 h, < 24 h, + 24 h, total), "últimos vistos", indicador "Conectando…", aviso de que el
  canal Medium Fast es público y de solo lectura, historial de alertas ("Sin alertas recientes"),
  enlaces a telemetría, incendios y pronóstico. → Pestañas equivalentes, aviso de solo lectura en el
  chat, indicador de conexión y alertas con estado vacío explícito; capas de plugins (incendios)
  quedan previstas (16.5).

## Proyectos de referencia

- **Meshview** (AGPL, solo ideas): listado de paquetes y gráficos de actividad por tipo. → Paquetes
  por tipo y distribución de saltos en Estadísticas (barras como tabla).
- **Potato Mesh** (Apache-2.0): estado de nodos por antigüedad, tabla filtrable, chat del canal. →
  Lista de nodos con filtros (estado, rol, infraestructura, posición, telemetría) y orden.
- **MeshDash** (GPL, solo ideas): panel denso de telemetría por nodo con gráficos por rango. →
  Gráfico completo con selector de tipo, métrica y rango (1 h a 30 d) y banda mínimo-máximo.

## Visualización de datos

Criterios de visualización: una serie y un solo eje por gráfico (nunca dos
escalas), línea de 2 px con relleno al 10 %, grilla en línea fina, gráficos mini de bajo énfasis
con el punto actual en acento, barras de un solo color para categorías nominales con "Otros" para
la cola, tabla equivalente para cada gráfico y paleta categórica validada para daltonismo (tres
categorías en la capa de actividad).
