# ADR 0013 · Rendimiento de Lighthouse móvil con el mapa WebGL en la portada

Estado: aceptada · 20/10/2026

## Contexto

La sección 5.5 fija 85 de rendimiento en Lighthouse (perfil móvil). La portada es el mapa: MapLibre GL a pantalla completa, cargado en diferido. Medido el 20/10 con el build servido por el backend (br/gzip), mediana de 3 corridas:

| Caso | Rendimiento | FCP | TBT | LCP |
|---|---|---|---|---|
| Móvil (CPU 4×, red simulada) | 41-42 | 2,2 s | 4,1 s | 7,0 s |
| La misma interfaz sin mapa | 78 | | | |
| Escritorio | 66 | | | |

Accesibilidad y buenas prácticas: 100 y 100. JS inicial 122,8 KB comprimido (presupuesto 180 KB).

Unos 3 s del TBT son de MapLibre: compilar los programas WebGL, armar las teselas y los primeros cuadros. Son tareas que no se pueden partir en pedazos de menos de 50 ms. El LCP que mide Lighthouse es el texto de atribución, que aparece cuando el mapa termina de cargar. El detalle de lo probado está en `docs/diseño/rendimiento.md`.

## Decisión

- Para v1 se acepta que el perfil móvil de Lighthouse quede por debajo de 85 mientras la portada sea el mapa WebGL.
- No se difiere el mapa hasta una interacción: es el contenido principal del sitio.
- Se mantienen y se vigilan los presupuestos que sí dependen de nosotros: el JS inicial (180 KB), la interfaz sin mapa (78) y el primer pintado (pantalla de arranque estática, sin página en blanco).
- El criterio que manda es la prueba en un teléfono real (16.8.5): 50 cuadros/s al arrastrar en un Android de gama media y la lectura al sol.

## Opciones para más adelante

- Una vista previa estática del mapa (imagen liviana) como primer pintado, y el mapa WebGL al quedar libre el hilo principal.
- Crear las capas de datos que no se ven al inicio recién cuando se usan.
- Lighthouse CI con un umbral realista (40 en móvil) para detectar retrocesos, y un umbral propio de 78 para las páginas sin mapa (`/nodos`, `/acerca`).

## Consecuencias

Si se nota lentitud en un teléfono, se prueba primero la vista previa estática.
