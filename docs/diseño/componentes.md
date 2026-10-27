# Componentes (16.4)

Todos están en `frontend/src/lib/components/` y se ven con todos sus estados en el catálogo
`/dev/componentes` (solo con `pnpm dev`; en el build la ruta responde 404 y su código no se
incluye).

| Componente | Archivo | Estados y notas |
|---|---|---|
| Barra superior | `shell/TopBar.svelte` | PC y tableta (compacta); marca, buscador, paleta, Acerca, apariencia |
| Buscador con resultados | `shell/SearchBox.svelte` | combobox accesible (flechas, Enter, Escape), sin acentos |
| Paleta de comandos | `shell/CommandPalette.svelte` | `Ctrl+K`/`Cmd+K` y `/`; páginas, nodos, tema, modo sólido, idioma |
| Chips de filtro | `shell/FilterChips.svelte`, `ui/Chip.svelte` | `aria-pressed`, zona táctil de 44 px; filtran mapa y lista a la vez |
| Pila de controles del mapa | `shell/MapControls.svelte` | capas, acercar, alejar, norte (brújula girada), mi ubicación |
| Selector de capas y leyenda | `shell/LayerMenu.svelte`, `shell/MapLegend.svelte` | base deshabilitada si no hay extracto; capas de datos; leyenda con forma y trazo |
| Panel inferior con anclajes | `ui/BottomSheet.svelte` | 96 px, mitad, 92 %; ver la decisión más abajo |
| Panel lateral | layout público | 380 px (PC), 360 px plegable (tableta), apaisado |
| Barra de pestañas | `shell/TabBar.svelte`, `shell/MoreMenu.svelte` | Mapa, Nodos, Chat, Alertas (con conteo de activas), Más |
| Pestañas del panel | `shell/PanelTabs.svelte` | Nodos, Chat, Alertas, Estadísticas; solo íconos en apaisado |
| Resumen de la red | `shell/SummaryStrip.svelte` | conteo por estado con glifo, último paquete, conexión |
| Ficha de nodo | `node/NodeDetail.svelte` | carga, no encontrado, sin posición, con y sin ambiente |
| Tarjeta de nodo | `node/NodeCard.svelte` | estado, rol, batería, señal; `@container` oculta métricas si es angosta |
| Lista de nodos | `node/NodesList.svelte`, `ui/VirtualList.svelte` | virtualizada propia (filas de 64 px, `aria-setsize`/`aria-posinset`) |
| Anillo de batería | `ui/BatteryRing.svelte` | sin dato, crítica, baja, media, alta, alimentado (101) |
| Barras de señal | `ui/SignalBars.svelte` | 0-4 barras por SNR (o RSSI); el nivel se lee por cantidad, no solo color |
| Insignia de estado | `ui/StatusBadge.svelte`, `ui/StatusGlyph.svelte` | activo, reciente, tardío, inactivo; anillos de infraestructura y fijo |
| Insignia de rol | `ui/RoleBadge.svelte` | roles de Meshtastic traducidos; infraestructura resaltada |
| Gráfico mini | `ui/Sparkline.svelte` | SVG, gris de bajo énfasis con el punto actual en acento; resumen accesible |
| Gráfico de series | `ui/TimeSeriesChart.svelte`, `node/TelemetryDialog.svelte` | uPlot diferido; una serie y un eje; banda mín-máx; cruz con valor y hora; tabla equivalente |
| Deslizador con reproducción | `node/NodeHistory.svelte` | rangos 1 h a 7 d, reproducir/pausar, velocidad estimada |
| Burbuja de mensaje | `chat/MessageBubble.svelte` | normal, agrupada, respuesta (encontrada o no), reacciones como chips |
| Chat | `chat/ChatView.svelte` | días, búsqueda, anteriores, ir a lo último, anuncio con aria-live |
| Aviso SOS | `alerts/SosBanner.svelte` | SOS con `role="alert"` y región `aria-live="assertive"`; otras alertas `polite` |
| Lista de alertas | `alerts/AlertItem.svelte` | activa o resuelta, gravedad con ícono y texto |
| Notificaciones | `alerts/PushToggle.svelte` | sin soporte, iPhone sin instalar, bloqueadas, activas, no disponibles |
| Tarjeta de estadística | `stats/StatTile.svelte` | cifras proporcionales en el valor |
| Barras como tabla | `stats/BarList.svelte` | un color para categorías nominales, "Otros" para la cola |
| Diálogo | `ui/Modal.svelte` | bits-ui Dialog; en el celular se abre como hoja desde abajo |
| Diálogo de confirmación | `ui/ConfirmDialog.svelte` | bits-ui AlertDialog, variante de peligro |
| Avisos emergentes | `ui/Toaster.svelte` | información, éxito, aviso, error (este con `role="alert"`), con acción |
| Estado vacío | `ui/EmptyState.svelte` | con ícono, descripción y acciones |
| Esqueleto de carga | `ui/Skeleton.svelte` | con `role="status"` y texto para lectores |
| Indicador en vivo | `ui/LiveIndicator.svelte` | en vivo, conectando, reconectando, sin conexión (con reintentar) |
| Menú de apariencia | `shell/AppearanceMenu.svelte`, `shell/AppearanceControls.svelte` | tema oscuro/claro/sistema, modo sólido, idioma |
| Aviso de privacidad | `notice/NoticeBlocks.svelte` | bloques JSON del servidor, nunca HTML; enlaces solo http(s) y mailto |
| Sin conexión | `shell/OfflineBanner.svelte` | se muestran los últimos datos guardados |
| Nueva versión | `shell/UpdatePrompt.svelte` | aviso con botón "Actualizar" (service worker en espera) |
| Pantalla de arranque | `src/app.html` | estática (sin JS), tema guardado, aviso con "Recargar" a los 12 s; la quita el layout raíz |
| Base de los íconos | `ui/LucideIcon.svelte` | reemplaza en el build la base de `@lucide/svelte` (plugin en `vite.config.ts`); SVG armado una vez por ícono; `aria-hidden` salvo con etiqueta |
| Panel de administración | `routes/admin/+layout.svelte` | superficies sólidas; secciones por rol; aviso si se abre por URL una sección de otro rol |

### Panel y asistente

En `frontend/src/lib/components/admin/` (estilos comunes en `admin.css`) y
`frontend/src/lib/components/setup/`. La lógica sin interfaz está en `frontend/src/lib/admin/`:
cliente tipado por área (`api.ts`), recursos con recarga y sondeo (`resource.svelte.ts`), errores
RFC 9457 (`errors.ts`), formularios desde JSON Schema (`schema.ts`), stream del panel
(`stream.svelte.ts`) y textos de estados (`labels.ts`).

| Componente | Archivo | Estados y notas |
|---|---|---|
| Campos | `Field`, `TextField`, `NumberField`, `SelectField`, `TextArea`, `SecretField`, `TagsField`, `CheckGroup` | etiqueta, ayuda y error enlazados (`aria-describedby`, `aria-invalid`); obligatorio marcado; `trailing` alinea un botón con el control; secreto de solo escritura con "ver" |
| Tabla virtualizada | `DataTable.svelte` | roles ARIA de tabla, `aria-rowcount`/`aria-rowindex`, orden por columna, fila activable con teclado (Enter, flechas, Inicio, Fin), vacío, desplazamiento lateral en pantallas angostas |
| Formulario desde JSON Schema | `SchemaForm.svelte` | `$ref`/`$defs`, `anyOf` con null, enum, listas de textos, números y objetos; columnas para campos cortos; etiquetas y opciones propias por ruta; errores por ruta (`params.patterns.0`) |
| Confirmación | `ConfirmAction.svelte` | bits-ui AlertDialog; palabra a escribir opcional; queda abierto con el error del servidor |
| Contenedores | `Panel.svelte`, `PageHeader.svelte`, `KeyValue.svelte` | región con título, acciones, variante de peligro; encabezado con título y descripción de la sección; pares clave-valor en columnas |
| Errores | `ProblemNote.svelte` | `detail`, código y reintentar |
| Progreso de trabajos | `JobProgress.svelte` | `role="progressbar"`, determinado o no, paso traducido, error |
| Estado y medidores | `StatusPill.svelte`, `Meter.svelte` | activo, detenido, con fallas, sin datos (forma, no solo color); medidor con "elevado"/"alto" en texto, sin rol `meter` cuando no hay dato |
| Copiar | `CopyBlock.svelte` | portapapeles y, sin permiso (HTTP en la LAN), selección del texto |
| Mapa para elegir | `MapPicker.svelte` | MapLibre diferido; centro y zoom, o caja (extracto) |
| Específicos | `system/ServiceList`, `radio/ConnectorForm`, `radio/MqttSecretView`, `alerts/RuleForm`, `alerts/ChannelsForm`, `site/TilesPanel`, `packets/PacketDetail` | servicios con reinicio; conectores por tipo; credenciales MQTT de una sola vez con los comandos del Heltec (también en el asistente); reglas y canales de alertas; extracto de teselas; detalle de paquete |
| Asistente | `setup/Stepper.svelte`, `setup/StepFrame.svelte`, `setup/Step*.svelte` | pasos con `aria-current="step"` y "Paso N de M" en el celular; cada paso es un formulario con atrás, omitir y continuar; el foco va al título |

## Panel inferior: implementación propia (no `vaul-svelte`)

El plan dejaba elegir entre `vaul-svelte` y una implementación propia (6.2). Se eligió la propia:

- `vaul-svelte` estable es la 0.3.2, hecha para Svelte 4 sobre `bits-ui` 0.21; la rama para
  Svelte 5 (1.0.0-next.7) no tiene versión estable desde marzo de 2025. Usarla traería una segunda
  versión de `bits-ui` (el proyecto usa la 2.x) y código en modo de compatibilidad.
- vaul es un cajón **modal** (Dialog) con puntos de anclaje. Acá el panel es parte permanente de la
  disposición: el mapa sigue usable detrás, el contenido de cada ruta vive adentro, el anclaje lo
  fija la ruta (resumen en el inicio, mitad en la ficha, 92 % en listas y chat) y el alto visible
  alimenta el relleno del mapa para centrar nodos. Todo eso cuesta más adaptar que escribirlo.
- La implementación propia pesa unas 250 líneas: Pointer Events con captura sobre el asa y el
  encabezado, resistencia elástica fuera de los extremos, ajuste al anclaje más cercano o al
  siguiente según la velocidad (> 0,55 px/ms), resorte con `transform` (el desenfoque nunca se
  anima), cuerpo con el alto del anclaje (las listas virtualizadas calculan bien su ventana),
  `inert` en el resumen para que el teclado no entre al contenido oculto, y el asa como botón con
  `aria-expanded`, Enter/Espacio para alternar y flechas, Inicio y Fin para elegir anclaje.
- En el celular apaisado el mismo contenido pasa a un panel lateral (no hay hoja).

## Otras decisiones

- Íconos de nodo en el mapa dibujados en un lienzo y cargados con `addImage` (sin marcadores
  DOM): 16 combinaciones de estado × infraestructura × fijo, regeneradas al cambiar de tema.
- El nodo seleccionado se dibuja en una capa aparte por encima de los grupos: siempre se ve
  resaltado aunque esté agrupado o lo oculten los filtros.
- Grupos hasta zoom 15; si un grupo sigue junto al ampliarlo, se abre en abanico.
- MapLibre, el estilo de Protomaps y las capas de datos van en un paquete aparte que el layout
  pide al arrancar, en paralelo con `/api/v1/site` y `/api/v1/nodes`.
