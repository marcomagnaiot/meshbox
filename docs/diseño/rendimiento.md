# Rendimiento del frontend (5.5)

Presupuestos del plan para el sitio público: **JS inicial comprimido sin MapLibre ≤ 180 KB**,
MapLibre y su estilo diferidos y en paralelo, LCP ≤ 2,5 s en 4G, Lighthouse 85 / 95 / 95
(rendimiento, accesibilidad, buenas prácticas) y 50 cuadros/s al arrastrar el mapa con 3 paneles
glass en un Android de gama media.

## Cómo se mide

`pnpm build && pnpm size` (`frontend/scripts/measure-bundle.mjs`). Lee el manifiesto de Vite del
build y suma el cierre de imports **estáticos** de lo que necesita la ruta `/`: la entrada de
SvelteKit, la app, el layout raíz, el layout público y la página de inicio. Los `import()`
(MapLibre, uPlot, el resto de las rutas) quedan afuera y se miden aparte. Comprime cada archivo
con gzip nivel 9 y con brotli. También verifica que el prefijo `-webkit-backdrop-filter` del glass
tenga valores escritos (16.1.6) y sale con error si se pasa del presupuesto.

## Paquetes (20 de octubre de 2026, con el panel y el asistente completos)

En toda la página, 1 KB = 1024 bytes.

| Paquete | Archivos | Sin comprimir | gzip -9 | brotli |
|---|---|---|---|---|
| JS inicial de `/` (sin MapLibre) | 53 | 348,3 KB | **122,8 KB** | 109,0 KB |
| CSS inicial | 11 | 49,3 KB | 13,7 KB | 11,7 KB |
| Mapa diferido (MapLibre 6, estilo de Protomaps y capas) | 5 | 1134,0 KB | 303,1 KB | 248,9 KB |
| Worker de MapLibre (diferido, archivo aparte) | 1 | 506,6 KB | 144,4 KB | 118,6 KB |
| uPlot diferido (gráfico completo y estadísticas) | 1 | 49,8 KB | 21,5 KB | 19,4 KB |

- Presupuesto del JS inicial: 122,8 KB de 180 KB (68 %). El panel y el asistente no entran al
  arranque del sitio público: son rutas aparte que se cargan al abrirlas.
- MapLibre 6 (actualizado por la vulnerabilidad GHSA-jrc7-96c5-q579) es solo ESM y trae el
  worker en un archivo propio: el mapa baja unos 368 KB con brotli entre los dos.
- Fuente Inter Variable (woff2, local): latín 47,1 KB y latín extendido 83,1 KB; el navegador
  baja solo los rangos que usa la página.
- Recursos del mapa versionados en `static/tiles-assets/`: 1383 KB en 23 archivos (glifos y
  sprites). No van en el precache: se guardan en caché la primera vez que se usan.
- Precache del service worker: **125 archivos, 2418 KB** sin comprimir (la app pública, MapLibre
  y su worker, para que el mapa funcione sin conexión). Lo que solo usan `/admin` y `/setup` queda
  afuera (sin eso eran 264 archivos y 2894 KB): esas rutas no funcionan sin el backend y sus
  archivos, inmutables, quedan en la caché HTTP. Lo calcula `precacheManifest` en
  `vite.config.ts` con el manifiesto de Vite.
- `build/` completo, con los recursos del mapa: 4402 KB, más 1573 KB de copias `.br` y `.gz` que
  el backend sirve según `Accept-Encoding`.

## Lighthouse móvil: antes y después

### Cómo se midió

- Lighthouse 13.5 (CLI) con el perfil móvil por defecto (red 4G lenta simulada: 150 ms de ida y
  vuelta y 1,6 Mbit/s; CPU 4× más lenta) y el de escritorio (`--preset=desktop`), en esta PC
  (Chromium sin ventana, GPU Intel Iris Xe por ANGLE/Direct3D 11).
- Contra el build servido por el backend, ahora con brotli y gzip (servidor público, HTTP/1.1):
  el backend aislado de e2e, que reproduce la red simulada a **10×** (prueba de esfuerzo, como
  hasta ahora), y una copia de sus datos reproducida a **1×** (tráfico real: unos 190 paquetes
  por hora).
- Tres corridas por caso y la mediana (escritorio, una corrida). Base satelital (sin extracto),
  con las teselas de Esri por internet.
- "Antes": e3fc3f2 (panel y asistente completos, sin estos cambios). "Después": ca20e35.

| Caso | Rendimiento | Accesibilidad | Buenas prácticas | FCP | LCP | TBT | Speed Index | CLS |
|---|---|---|---|---|---|---|---|---|
| Móvil, 10×, antes | 36 | 100 | 100 | 3,6 s | 6,6 s | 5,6 s | 5,6 s | 0 |
| Móvil, 10×, después | **41** | 100 | 100 | **2,2 s** | 7,0 s | **4,1 s** | **4,6 s** | 0 |
| Móvil, 1×, antes | 37 | 100 | 100 | 3,5 s | 6,5 s | 5,8 s | 5,2 s | 0 |
| Móvil, 1×, después | **42** | 100 | 100 | **2,1 s** | 7,0 s | **4,1 s** | **4,6 s** | 0 |
| Escritorio, 10×, antes | 62 | 100 | 100 | 0,9 s | 1,5 s | 1,1 s | 1,9 s | 0 |
| Escritorio, 10×, después | **66** | 100 | 100 | **0,6 s** | 1,6 s | **0,7 s** | **1,7 s** | 0 |

Las corridas varían: el rendimiento móvil se mueve ±3 puntos entre corridas iguales y el FCP
estimado salta entre 2,1 y 3,1 s según el orden en que el navegador pide los 50 módulos del
arranque (Lighthouse cuenta como necesarios para pintar los pedidos que empezaron antes del
primer pintado, aunque no lo bloqueen). Con la primera medición, sin
compresión en el backend, el móvil daba 27.

Referencia de lo que logra la interfaz sin el mapa (MapLibre y el stream bloqueados en
Lighthouse): **78** en móvil después de los cambios (81 antes; dentro de la variación),
TBT 0,1 a 0,3 s.

### Qué cambió

1. **Pantalla de arranque estática** en `app.html`: fondo del tema guardado, marca, barra y
   "Cargando…", pintados con el HTML y el CSS en línea, sin esperar el JS. La quita el layout raíz
   al montarse. Si a los 12 s la app no arrancó aparece "La conexión con el equipo está lenta…"
   con "Recargar". FCP de 3,5 s a 2,1-2,2 s en Lighthouse; en la PC sin frenos, 0,2-0,4 s.
2. **Service worker sin competir**: se registra después de `load`, del primer dibujo completo
   del mapa (o 10 s) y con el navegador ocioso. En la primera visita, los 2,4 MB del precache
   ya no se bajan junto con el mapa y las teselas.
3. **MapLibre**: sin validar el estilo en producción (`validateStyle` solo en desarrollo: cada
   `addLayer` de las ~35 capas de datos validaba con el esquema), sin fundidos de símbolos ni de
   teselas raster (menos cuadros mientras llegan las teselas), los pulsos de actividad empiezan
   2 s después del primer dibujo completo (con la red a 10× eran un redibujo a 30 cuadros/s
   durante toda la carga) y el paquete del mapa se pide desde el layout raíz, una ida y vuelta
   antes.
4. **Íconos de Lucide livianos**: los de `@lucide/svelte` usan una base propia
   (`LucideIcon.svelte`, cambiada en el build por un plugin de Vite) que arma el SVG una vez por
   ícono en lugar de un `<svelte:element>` por trazo con varios `$derived` por instancia.
5. **Orden de nodos**: un solo `Intl.Collator`, creado solo al ordenar por nombre (crearlo en
   cada orden cargaba datos de ICU en el arranque).

Medido en Chromium con la CPU 4× (tareas largas reales, sin la simulación de Lighthouse): la
tarea larga del primer dibujo de la app bajó de unos 800 ms a 550 ms, y la suma de lo que pasa
de 50 ms en las tareas largas de los primeros 8 s, de 2,6 s a 1,8 s.

### Qué queda y por qué no llega a 85

- **TBT (4 s simulados)**: unos 3 s son de MapLibre (el primer dibujo compila los programas de
  WebGL de cada tipo de capa —en Direct3D tarda; en un teléfono con OpenGL ES suele ser menos—,
  el armado de las teselas y los cuadros mientras llegan) y alrededor de 1 s el primer render de
  Svelte de la interfaz. Las tareas del mapa no se pueden partir en pedazos de menos de 50 ms.
- **LCP (7 s simulados)**: el elemento más grande que Lighthouse ve es el texto de atribución de
  Esri, que aparece cuando MapLibre carga el estilo; el lienzo del mapa no cuenta para LCP. O sea
  que mide la llegada del mapa: los 368 KB de MapLibre y su worker a 1,6 Mbit/s más la CPU.
- Con un mapa WebGL a pantalla completa en la página de inicio, 85 en el perfil móvil de
  Lighthouse no es alcanzable sin diferir el mapa hasta una interacción, que se descartó porque
  el mapa es el contenido principal. En escritorio queda en 66 por el mismo motivo.
- Se probó agrupar los chunks del arranque con `codeSplitting` de Rolldown (grupos por conjunto
  de rutas y fusión de los chicos): el JS inicial pasó a 252 KB comprimidos porque módulos
  compartidos con el panel entraron al grupo inicial, y se descartó. Los ~50 módulos chicos del
  arranque son en su mayoría mensajes de Paraglide e íconos compartidos entre rutas.

## Actualizar con un origen lento (la Pi detrás del túnel)

En la Pi, tras "Actualizar" en el aviso de nueva versión, la página quedó más de 10 s en blanco.
Se reprodujo el flujo en Chromium (con un script de Playwright): se instala
la versión servida, se sirve otra, se busca la actualización, se aplica una red lenta a la
página (900 ms de latencia y 400 kbit/s) y se toca "Actualizar".

| Versión | Del clic a la recarga | Primer pintado | App montada |
|---|---|---|---|
| Antes | 1,1 s | 1,2 s | 0,3 s después de la recarga |
| Después | 1,4 s | 1,1 s (pantalla de arranque) | 0,5 s después de la recarga |

- La recarga no espera al precache: el aviso aparece recién cuando el service worker nuevo
  terminó de instalarse (estado "en espera"), así que todo sale de la caché; el segundo largo
  hasta la recarga es la activación del service worker nuevo y su aviso de "controlando".
- No se reprodujo la página en blanco: con el service worker controlando, `index.html` y los
  módulos salen de la caché. La causa probable es una carga que no pasó por el service worker
  (recarga forzada, Ctrl+Shift+R, o "deshabilitar caché" de las herramientas de desarrollo):
  entonces `index.html` y unos 50 módulos van a la Pi por el túnel.
- Ahora, aunque pase eso, la pantalla de arranque se pinta con el `index.html` y a los 12 s
  ofrece recargar. Además el precache del sitio público es un 16 % más chico y ya no compite con
  la primera carga.

## Qué lo mantiene bajo

- MapLibre, el estilo de Protomaps y las capas de datos van en un paquete aparte que se pide al
  arrancar, en paralelo con `/api/v1/site` y `/api/v1/nodes`; el resumen y la lista se pintan
  antes que el mapa.
- uPlot se carga solo al abrir el gráfico completo de la ficha o Estadísticas; los gráficos mini
  son SVG propios.
- Íconos de Lucide importados de a uno (`@lucide/svelte/icons/…`) con la base liviana, mensajes
  de Paraglide compilados a funciones, formatos con `Intl` en caché (sin bibliotecas de fechas) y
  bits-ui solo en diálogos, menús y popovers.
- El catálogo `/dev/componentes` se importa solo en desarrollo: no entra al build.
- El panel y el asistente son rutas aparte: no suman al arranque del sitio ni a su precache.

## En ejecución

- Las capas GeoJSON se actualizan como máximo cada 500 ms; el resaltado usa `feature-state`;
  no hay marcadores DOM (los íconos se dibujan en un lienzo y se cargan con `addImage`).
- La capa de actividad se redibuja a unos 30 cuadros/s solo mientras hay pulsos (y recién 2 s
  después del primer dibujo completo); con movimiento reducido, solo cuando llega o vence un
  evento.
- Los eventos SSE se acumulan y la interfaz se actualiza como máximo cada 200 ms; el reloj de
  "hace N minutos" avanza cada 15 s.
- Listas virtualizadas (filas de 64 px en el sitio; tablas virtualizadas en el panel) y chat
  con carga de mensajes anteriores por páginas.
- El desenfoque nunca se anima: las transiciones mueven solo `opacity` y `transform`.
- Si al arrastrar el mapa se miden menos de 40 cuadros/s durante 3 s, se sugiere el modo sólido
  una sola vez (16.1.9).

## Caché del service worker (20)

| Recurso | Estrategia |
|---|---|
| App pública (JS, CSS, fuentes, íconos) | precache con aviso de nueva versión; se registra con la página ya cargada |
| Panel y asistente | fuera del precache (caché HTTP, archivos inmutables) |
| `/api/v1/site`, `/api/v1/nodes`, `/tiles/v.json` | red primero, con copia para usar sin conexión |
| Teselas `/tiles/v/` | caché primero, hasta 2000 teselas (unos 50 MB) por 60 días; se vacía si falta espacio |
| Glifos y sprites | caché primero |
| `/api/v1/admin`, `/api/v1/setup` | solo red, nunca en caché |

## Pendiente

- Medir en un Android de gama media (con GPU y OpenGL ES): cuadros por segundo al arrastrar el
  mapa (criterio del plan) y el costo real de compilar los programas de WebGL.
- Lighthouse CI (`@lhci/cli`) con los presupuestos de 5.5 contra el build servido por el backend,
  con la base vectorial (extracto) además de la satelital.
- Si hace falta bajar más el TBT: crear las capas de datos que no se ven al inicio (recorrido,
  traceroute, abanico, incertidumbre) recién cuando se usan, y partir el primer render de la
  interfaz (paleta de comandos y menús después del primer cuadro).
