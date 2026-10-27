# Tokens del sistema de diseño (16.2)

Definidos en `frontend/src/app.css`, en OKLCH, con tema oscuro por defecto (`:root`,
`[data-theme='dark']`) y tema claro completo (`[data-theme='light']`). Tailwind 4 los expone con
`@theme inline` (por ejemplo `text-fg-2`, `bg-fill-1`, `rounded-lg`), así que cambiar de tema solo
cambia variables. El tema y el modo sólido se aplican antes de pintar con un script en línea de
`app.html` (el servidor agrega su hash a la CSP).

## Valores

| Grupo | Oscuro | Claro | Nota |
|---|---|---|---|
| Fondo `--bg` | `oklch(16% 0.02 255)` | `oklch(97% 0.005 255)` | detrás del mapa |
| Superficies sólidas `--surface-1/2/3` | 19 / 23 / 28 % L | 99 / 96 / 92 % L | panel, menús, diálogos, avisos |
| `--glass-bg` | `oklch(22% 0.02 255 / 0.55)` | `oklch(99% 0.005 255 / 0.7)` | claro: 0.62 → **0.7** (contraste) |
| `--glass-bg-strong` | `/ 0.78` | `/ 0.88` | |
| `--glass-bg-solid` (modo sólido) | `/ 0.95` | `/ 0.96` | modo sólido: alfa 0.95 y sin desenfoque |
| `--glass-border` | `oklch(100% 0 0 / 0.12)` | `oklch(20% 0.02 255 / 0.12)` | |
| `--glass-highlight` | `inset 0 1px 0 oklch(100% 0 0 / 0.08)` | `… / 0.65` | |
| `--glass-shadow` | `0 8px 32px oklch(0% 0 0 / 0.35)` | `0 8px 32px oklch(30% 0.03 255 / 0.18)` | |
| `--glass-blur` / `--glass-blur-small` | 16 px / 20 px | igual | se escriben literales en el CSS (ver abajo) |
| `--glass-saturate` | 140 % | igual | |
| `--fill-1/2/3` | blanco 6 / 10 / 16 % | tinta 4 / 7 / 12 % | tarjetas dentro de glass |
| `--scrim` | `oklch(15% 0.02 255 / 0.6)` | `oklch(98% 0.005 255 / 0.55)` | oscuro: 0.35 → **0.6** (contraste) |
| `--text-1` | `oklch(97% 0 0)` | `oklch(20% 0.02 255)` | |
| `--text-2` | `oklch(80% 0.01 255)` | `oklch(37% 0.02 255)` | |
| `--text-3` | `oklch(72% 0.01 255)` | `oklch(46% 0.02 255)` | oscuro: 65 % → **72 %**; solo gráficos y texto grande sobre glass |
| `--accent` | `oklch(72% 0.15 210)` | `oklch(64% 0.14 215)` | se reemplaza con el color del panel (`site.accent`) |
| `--accent-ink` | `max(l, 0.72)` del acento | `min(l, 0.42)` del acento | color relativo: legible con cualquier acento |
| `--on-accent` | calculado en JS (`onColor`) | igual | texto sobre botones de acento |
| Estados | activo `oklch(78% 0.17 150)`, reciente `85% 0.15 90`, tardío `68% 0.19 25`, inactivo `62% 0.01 255`, infra `75% 0.12 220`, alerta `65% 0.22 30` | más oscuros (66 / 76 / 60 / 58 / 60 / 58 % L) | |
| `--map-outline` | `oklch(15% 0.02 255)` | `oklch(18% 0.02 255)` | borde de los íconos del mapa |
| Gráficos | `--chart-line` = `--accent-ink`, grilla blanca 8 %, `--chart-muted` = `--text-3` | grilla tinta 8 % | una serie, un eje |
| Actividad del mapa | `--cat-1` `#3987e5`, `--cat-2` `#d95926`, `--cat-3` `#199e70`, gris | `#2a78d6`, `#eb6834`, `#1baf7a` | paleta de referencia validada (abajo) |
| Radios | 10 / 14 / 20 / 28 px | igual | 28 px: esquinas del panel inferior |
| Movimiento | `--dur-1` 160 ms, `--dur-2` 240 ms, `--ease cubic-bezier(.2,.8,.2,1)`, `--ease-spring` | igual | 0 ms con movimiento reducido |
| Capas (z) | mapa 0, controles 10, paneles 20, panel inferior 30, menús 40, avisos 50, modales 60 | igual | |
| Tipografía | Inter Variable local; 12, 13, 14, 16, 20, 24, 32 px; `tabular-nums` en datos | igual | `@fontsource-variable/inter`, sin CDN |

## Contraste medido (16.1.5)

`node frontend/scripts/contrast.mjs` compone las capas como el navegador (sRGB) y mide el texto
contra el **peor fondo**: una zona clara de la capa satelital (blanco puro) para el tema oscuro y
una zona oscura (negro) para el claro. Requisito: 4,5:1 en texto normal y 3:1 en texto grande,
íconos y gráficos.

Con los valores del plan, el texto secundario y el terciario no alcanzaban sobre satélite claro:

| Tema oscuro, plan | glass + scrim | + tarjeta (`fill-1`) |
|---|---|---|
| `--text-1` | 6,54 | 5,60 |
| `--text-2` | **3,82** | **3,27** |
| `--text-3` (65 %) | **2,21** | **1,89** |
| `--accent` como texto | **3,13** | **2,68** |

Valores finales (lo que hay en `app.css`):

| Tema oscuro, final | glass + scrim | + tarjeta | sobre mapa oscuro |
|---|---|---|---|
| `--text-1` | 10,38 | 8,64 | 17,58 |
| `--text-2` | 6,06 | 5,05 | 10,27 |
| `--text-3` (72 %) | 4,57 | 3,80 (solo gráficos y texto grande) | 7,74 |
| `--accent` como texto | 4,97 | 4,14 (texto grande o íconos) | 8,41 |

| Tema claro, final | glass + scrim | + tarjeta | sobre mapa claro |
|---|---|---|---|
| `--text-1` | 12,68 | 11,74 | 17,18 |
| `--text-2` | 7,30 | 6,76 | 9,89 |
| `--text-3` | 4,99 | 4,62 | 6,76 |
| `--accent-ink` (42 %) | 5,39 | 4,99 | 7,30 |

Consecuencias aplicadas en los componentes:

- Todo texto sobre glass lleva el `--scrim` como capa (`.glass-text`); los paneles quedan con una
  opacidad efectiva cercana a 0,8 sobre el mapa, y el desenfoque se sigue viendo en los bordes y
  a través del panel.
- Las etiquetas pequeñas dentro de tarjetas usan `--text-2`; `--text-3` solo se usa en el asa del
  panel inferior y en el anillo de batería sin dato (gráficos, ≥ 3:1).
- Los colores de estado nunca se usan como texto sobre glass: van en glifos con borde oscuro
  (≥ 5,4:1 contra el borde) y el texto del estado va en `--text-1`.
- Etiquetas del mapa: texto claro con halo oscuro sobre satélite y mapa oscuro; texto oscuro con
  halo blanco sobre el mapa claro (dependen de la capa base, no del tema de la interfaz).

## Glass: reglas de 16.1 tal como quedaron

1. Glass solo en la capa flotante: barra superior, buscador y chips (una sola superficie en el
   celular), pila de controles del mapa, panel inferior, barra de pestañas, paneles laterales.
   Menús, ventanas emergentes, diálogos, avisos y el aviso SOS son **sólidos**: abren encima de
   paneles glass y así no hay glass sobre glass.
2. Dentro de un panel glass las tarjetas usan `--fill-1/2`, nunca otro desenfoque.
3. Superficies glass visibles a la vez: celular 4 (arriba, controles, panel inferior, pestañas; con
   el panel al 92 % la barra de arriba se oculta y quedan 3); tableta 4; PC 4 (barra superior,
   panel izquierdo, ficha, controles).
4. Desenfoque fijo: 16 px en superficies grandes, 20 px en piezas chicas. Las transiciones animan
   solo `opacity` y `transform`.
5. Base sólida y glass progresivo:
   `@supports (backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))`. El compilador
   de CSS (Lightning CSS, vía Tailwind) copia el valor de `backdrop-filter` al prefijo
   `-webkit-`, así que **ambas propiedades llevan valores escritos** (`blur(16px) saturate(140%)`);
   `pnpm size` verifica en el build que el prefijo no tenga variables.
6. Modo sólido manual (menú de apariencia, guardado en `localStorage`), y además
   `prefers-reduced-transparency: reduce` (solo Chromium) y `prefers-contrast: more` (bordes de
   2 px visibles, superficies opacas, `--text-3` = `--text-2`).
7. `prefers-reduced-motion`: duraciones a 0, sin pulsos ni reproducción animada del recorrido,
   actividad del mapa como anillo fijo, mapa sin `flyTo`.
8. Si al arrastrar el mapa se miden menos de 40 cuadros/s durante 3 ventanas seguidas de 1 s, se
   sugiere una sola vez el modo sólido (aviso con botón; queda registrado en las preferencias).
9. El color nunca es la única señal: estado = color **y** relleno del glifo (lleno, tres cuartos,
   medio, vacío) **y** texto en listas y ficha; infraestructura = anillo grueso; fijo = anillo fino;
   enlaces = color **y** trazo (continuo, a trazos, punteado).

## Paleta de la capa de actividad

Tres categorías más gris (posición, mensajes, telemetría, otros), tomadas en orden de la paleta de
referencia validada para daltonismo. Validación con el script de la guía de visualización:

- Oscuro, superficie `#0f141b`, todos los pares: luminosidad, croma, CVD (peor ΔE 9,4),
  visión normal (peor ΔE 20,9) y contraste ≥ 3:1: **todo aprobado**.
- Claro, superficie `#f5f7fa`, todos los pares: aprobado, con aviso de contraste en naranja y
  verde agua (2,98 y 2,62): se compensa con el borde oscuro de los pulsos y la leyenda del menú de
  capas.

## Pendiente (16.8, puntos 5 y 6)

- Pruebas en un teléfono real: lectura al sol, uso con una mano, contraste real sobre la capa satelital de
  la región, cuadros por segundo con 3 paneles glass en un Android de gama media.
