# Inventario de pantallas y estados (16.8, punto 2)

Disposiciones (16.3): **celular** (< 768 px; panel inferior con anclajes 96 px, mitad y 92 % y
barra de pestañas), **celular apaisado** (alto < 500 px; panel lateral), **tableta**
(768-1199 px; panel izquierdo de 360 px plegable y ficha a la derecha o abajo según orientación) y
**PC** (≥ 1200 px; barra superior, panel izquierdo de 380 px con pestañas y ficha a la derecha de
420 px). El mapa ocupa siempre toda la pantalla y persiste entre rutas.

Estados transversales: cargando (esqueletos), sin datos (estado vacío con sugerencia), error de
red (mensaje y reintentar), **en vivo / conectando / reconectando / sin conexión** (indicador en el
resumen; sin conexión muestra los últimos datos guardados por el service worker), alerta activa
(aviso arriba en todas las pantallas públicas), nueva versión disponible (aviso con "Actualizar").

## Sitio público

| Ruta | Celular | PC | Estados propios |
|---|---|---|---|
| `/` | Mapa; panel en resumen (96 px) con conteo por estado, conexión y último paquete; al subirlo, la lista de nodos | Panel izquierdo con resumen, pestaña Nodos y lista | sin nodos, filtros sin resultados |
| `/n/!id` | Panel a la mitad con la ficha; el mapa centra el nodo encima del panel | Lista a la izquierda y ficha a la derecha | cargando, nodo no encontrado u oculto, sin posición, sin telemetría, sin ambiente, sin vecinos, sin traceroutes |
| `/nodos` | Panel al 92 % (la barra de arriba se oculta): búsqueda, filtros avanzados, orden y lista | Pestaña Nodos con filtros y orden | sin resultados (con "Quitar filtros") |
| `/chat` | Panel al 92 % con el chat | Pestaña Chat | cargando, vacío, búsqueda sin resultados, más mensajes anteriores, mensajes nuevos fuera de la vista ("Ir a los últimos") |
| `/alertas` | Panel al 92 %: notificaciones y lista | Pestaña Alertas | sin alertas, push no disponible, bloqueado, iPhone sin instalar, suscripto |
| `/estadisticas` | Desde "Más" | Pestaña Estadísticas | sin datos suficientes, recarga con el gráfico anterior atenuado |
| `/acerca` | Desde "Más" | Enlace en la barra superior | sin canales públicos, sin aviso |
| Paleta de comandos | Al tocar el buscador | `Ctrl+K` o `/` | sin coincidencias |
| Página no encontrada | `+error.svelte` | | 404 y otros errores |

### Ficha de nodo (17.2)

Encabezado (nombre, nombre corto, rol, estado con texto "Escuchado hace 12 minutos", centrar,
compartir); indicadores (anillo de batería o "Alimentado", voltaje, señal con barras, SNR, RSSI,
saltos, tiempo encendido, utilización de canal y de aire); ambiente (temperatura, humedad,
presión, luz) si existe; gráficos de 24 h (batería o voltaje y temperatura) que abren el gráfico
completo con tipo (dispositivo, ambiente, energía), métrica y rango (1 h a 30 d); historial de
posiciones con rango (1 h a 7 d), recorrido en el mapa, reproducción y velocidad estimada;
vecinos con SNR, origen y antigüedad; traceroutes recientes con "Ver en el mapa"; datos técnicos
(id, hardware, rol, firmware, región, preset, primera vez visto, precisión, hora de la posición).

### Mapa (16.5)

Capas base: oscuro y claro (si hay extracto), satélite (si está permitido y como respaldo sin
extracto); sin nada de eso, solo el fondo y las capas de datos. Capas de datos: nodos (grupos y
abanico), nodo seleccionado, incertidumbre, enlaces, recorrido, traceroute, actividad, puntos de
interés y mi ubicación. Estados: cargando, error de WebGL (mensaje; queda la lista como
alternativa), sugerencia de modo sólido por rendimiento.

## Panel de administración (`/admin`, solo LAN o Access)

| Pantalla | Estados |
|---|---|
| Inicio de sesión (`/admin/login`) | campos vacíos, credenciales incorrectas (401), demasiados intentos (429 con cuenta regresiva), sin red, sesión vencida |
| Verificando sesión | esqueleto; error de red con reintentar |
| Disposición del panel | aviso de HTTP en la LAN, aviso de cambio de contraseña obligatorio, menú lateral (menú desplegable en pantallas angostas), usuario y rol, apariencia, cerrar sesión; una sección de otro rol (o Transmisión deshabilitada) abierta por URL muestra un aviso en lugar de errores |

Estados comunes a todas las secciones: esqueleto al cargar; error RFC 9457 con `detail`, código y
reintentar (`ProblemNote`); datos viejos con aviso si falla una recarga; 401 → inicio de sesión
con `next`; 403 → "no hay permiso"; 422 → error en el campo exacto (ruta completa, por ejemplo
`params.patterns.0`); 429 → espera de `Retry-After`; en un equipo compartido (409 `shared_mode` o
`not_allowed_in_shared_mode`) la explicación de ADR 0004. Las acciones peligrosas piden
confirmación, algunas con una palabra escrita (restaurar, reiniciar, apagar, borrar historial,
instalar la versión).

| Sección (18.2) | Contenido y estados |
|---|---|
| Panel | servicios (`active` y `state`, reinicio con confirmación), CPU, memoria, temperatura (sin sensor: "—"), disco, paquetes por minuto, resumen, contadores, paquetes por tipo, conectores, gateways y alertas recientes; se actualiza cada 10 s |
| Radio | conectores MQTT, USB, TCP y reproducción: estado, probar, reiniciar, grabar, liberar el puerto, nodo conectado (reiniciarlo), alta, edición y baja; grabaciones |
| Broker MQTT | estado del broker, salida de eventos, cuentas (crear, rotar, borrar), ACL vigente; la contraseña nueva y los comandos del Heltec se muestran una sola vez |
| Canales | tarjetas con hash y clave; alta, edición, baja |
| Paquetes | en vivo (pausa, limpiar, duplicados) e historial paginado; filtros por tipo, origen, destino, canal, gateway, SNR, saltos y texto; detalle con recepciones y hex; exportación CSV o JSONL |
| Nodos | tabla virtualizada con búsqueda y filtros; ficha con ocultar, fijo, nota y borrar historial; el gateway se marca como tal |
| Mensajes | lista con cargar anteriores, ocultar y mostrar |
| Alertas | reglas con formulario desde el JSON Schema del servidor (18.3), probar, activar; eventos con reconocer; canales (Web Push, Telegram, webhooks, MQTT) con prueba |
| Sitio y mapa | identidad, logo, centro y límites en el mapa, capas, umbrales, aviso; extracto de teselas (caja, zoom máximo, progreso, borrar) |
| Privacidad y retención | privacidad, retención por tipo de dato y purga con confirmación |
| Cloudflare | estado y prueba del sitio; modo token, modo API (verificar, dominios, publicar), Access y desconectar |
| Red y sistema | WiFi, IP, hora y NTP, zona horaria, servicios, métricas internas, reinicio y apagado; en un equipo dedicado además redes, conectar (con aviso de la vuelta atrás a los 2 min), olvidar, punto de acceso y nombre del equipo; en uno compartido se explica que los administra el anfitrión |
| Plugins | permisos, capas, estado, ajustes desde `settings_schema` (secretos solo de escritura), registros; activar uno de terceros pide confirmación |
| Usuarios | usuarios (alta, edición, baja), sesiones (cerrar), auditoría con filtro y la propia contraseña |
| Respaldo | respaldos (crear, descargar, restaurar), subir y restaurar, exportar e importar la configuración con secretos cifrados |
| Actualizaciones | versión actual, instaladas, publicadas con notas; instalar con confirmación, seguimiento del trabajo (incluido el reinicio), volver a la anterior y búsqueda semanal |
| Registros | servicio, nivel, período, líneas y texto; meshbox en vivo; detalle con la traza; descarga `.log` |
| Transmisión | solo con `[tx] enabled`: texto y traceroute en dos pasos (vista previa y confirmación), límite de 1 cada 30 s con cuenta regresiva, aviso si no hay nodo USB |

## Asistente de primer uso (`/setup`, 18.1)

| Paso | Estados |
|---|---|
| Acceso | cargando; error con reintentar; sin usuarios y ventana de 60 min cerrada (reiniciar el equipo); usuarios creados y sin sesión (iniciar sesión con `next=/setup`); ya configurado (ir al panel, ver el mapa o revisar los pasos) |
| Pasos | lista con el actual, los hechos (con tilde) y los alcanzables; en el celular "Paso N de M" y barra; el foco va al título de cada paso; retoma en el primer pendiente |
| Red WiFi | solo con el punto de acceso: red y contraseña, instrucciones para seguir desde la red de la casa (meshbox.local, router o PC) y la vuelta atrás a los 2 min |
| Código | código de un solo uso (dónde encontrarlo), incorrecto, demasiados intentos; queda solo en memoria |
| Idioma y hora | idioma (cambia la página al instante) y zona horaria |
| Administrador | usuario y contraseña con las reglas del servidor; ya existe uno (iniciar sesión); al crearlo queda la sesión iniciada |
| Sitio | nombre, identificador corto (raíz MQTT), descripción, centro y zoom en el mapa |
| Radio | MQTT (gateway, raíz, puerto del Heltec en la PC) y/o USB (detectar puertos o escribirlo); resultado con la contraseña única, los comandos del Heltec y la prueba del nodo USB |
| Canal público | nombre (presets) y clave por defecto |
| Privacidad | ignorar nodos solo por MQTT, posiciones tal cual o con precisión reducida, aviso |
| Mapa base | el mismo panel de extracto de Sitio y mapa; "Hacerlo después" |
| Cloudflare | explicación y enlace a la sección; "Hacerlo después" |
| Verificación | paquetes (esperando o llegando), conectores, nodos, canales, sitio y mapa base, cada 5 s; terminar → "¡Listo!" con enlaces al mapa y al panel |

## Capturas

En `docs/diseño/capturas/`. Se regeneran con `node frontend/scripts/capturas.mjs` (Chromium de
Playwright, `es-AR`, movimiento reducido) contra `pnpm dev` y el backend de desarrollo, que
reproduce la red simulada de 24 h a 10× y no tiene extracto de mapa (por eso la base es la capa
satelital). Dos efectos de la demostración, no del diseño: la velocidad estimada sale multiplicada
por la velocidad de reproducción, y las respuestas y reacciones figuran "a un mensaje anterior"
porque la reproducción renumera los paquetes pero no los `reply_id`.

| Archivo | Qué muestra |
|---|---|
| `pc-mapa.jpg` | PC (1440 × 900), tema oscuro: mapa, resumen, lista y controles |
| `pc-ficha.jpg` | PC: ficha de un nodo móvil con su recorrido |
| `pc-capas.jpg` | PC: selector de capas con la leyenda completa |
| `pc-estadisticas-claro-solido.jpg` | PC, tema claro y modo sólido: estadísticas |
| `celular-mapa.jpg` | Pixel 7: mapa con el panel en resumen y la barra de pestañas |
| `celular-ficha.jpg` | Pixel 7: ficha a la mitad con el nodo resaltado arriba |
| `celular-chat.jpg` | Pixel 7: chat con respuestas y reacciones |
| `tableta-ficha.jpg` | Tableta apaisada (1180 × 820): lista y ficha |
| `apaisado-chat.jpg` | Pixel 7 apaisado: panel lateral compacto con el chat |
| `panel-resumen.jpg` | Panel: servicios, recursos, paquetes por minuto, conectores y gateways (página entera) |
| `panel-paquetes.jpg` | Paquetes en vivo con filtros |
| `panel-alertas-regla.jpg` | Alertas: regla nueva con el formulario generado desde el JSON Schema |
| `panel-registros.jpg` | Registros de meshbox en vivo |
| `panel-celular-nodos.jpg` | Pixel 7: nodos en el panel |
| `asistente.jpg` | Asistente con usuarios creados: retoma en el primer paso pendiente |
| `asistente-celular.jpg` | Pixel 7: asistente con "Paso N de M" |
| `asistente-codigo.jpg` | Asistente en un equipo nuevo (sin usuarios): código incorrecto |
| `asistente-wifi.jpg` | Paso WiFi con el punto de acceso (estado simulado: el backend de desarrollo no tiene punto de acceso) |
| `asistente-verificacion.jpg` | Verificación final en un equipo nuevo con la red simulada |

Las tres últimas salen de un backend de prueba con datos nuevos (sin usuarios, puertos propios)
y no las regenera `capturas.mjs`.
