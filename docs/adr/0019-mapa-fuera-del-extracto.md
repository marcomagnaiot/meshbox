# ADR 0019 · Mapa en línea fuera del extracto

Estado: aceptada · 01/11/2026 · amplía la sección 16.5 del plan

## Contexto

Las capas Claro y Oscuro salen del extracto PMTiles guardado en el equipo (sección 16.5), una caja de hasta 25 grados cuadrados elegida en el asistente o en Sitio y mapa. Fuera de esa caja el mapa queda vacío: se ve el recuadro descargado y alrededor nada. Con condiciones de propagación especiales la malla trae nodos de 200 a 400 km (el 01/11/2026 aparecieron de golpe unos 50 de Bahía Blanca y la zona), que quedaban sobre un fondo negro.

## Decisión

- Debajo del mapa vectorial del extracto va el mapa gris de Esri (`Canvas/World_*_Gray_Base` y los nombres de `Canvas/World_*_Gray_Reference`, de `server.arcgisonline.com`, el mismo servidor de la capa satelital), hasta el zoom 16; más arriba MapLibre agranda esas teselas. Donde hay extracto, el vectorial lo tapa.
- Las teselas de Esri pasan por un protocolo propio de MapLibre (`fuera://`, `frontend/src/lib/map/outside.ts`), que no las pide si caen enteras dentro de la caja del extracto: dentro de la zona el navegador del visitante no consulta a Esri, igual que antes.
- Para que el borde casi no se note, el fondo de Esri se ajusta con las propiedades de color del ráster, medido contra el vectorial. En el oscuro se usa el fondo claro invertido, porque en el gris oscuro de Esri la tierra es más clara que el mar, al revés del Protomaps oscuro. En el claro, el mar gris de Esri pasa al celeste del vectorial. El giro de tono también cambia los parques: quedan arena en el claro y oliva en el oscuro.
- Va atado al permiso que ya existía para Esri (`satellite_enabled`), que en el panel pasa a llamarse **Mapas en línea de Esri**: apagado, el sitio no consulta a nadie fuera del equipo. La política de contenido (CSP) no cambia: ya permitía ese servidor con la capa satelital.
- El aviso de privacidad de fábrica nombra el mapa fuera de la zona descargada. Un aviso de fábrica guardado sin cambios se actualiza solo; uno editado no se toca.

## Alternativas descartadas

- API de Protomaps: mismo esquema y mismo estilo, sin borde visible, pero pide registrar una clave.
- Que el equipo pida a demanda las teselas al planeta de `build.protomaps.com`: esos archivos se rotan cada pocos días y la Pi Zero tendría que leer directorios grandes por cada zona nueva.
- OpenFreeMap: sin clave, pero otro esquema (habría que mantener un segundo estilo) y un tercero más en el aviso.
- Un extracto más grande: el borde sigue existiendo, solo se corre.

## Consecuencias

- Fuera del extracto el mapa necesita internet; dentro sigue funcionando sin conexión.
- Hay una diferencia leve de estilo entre las dos zonas (tipografía de los nombres, parques). En la caja del extracto no cambia nada.
- Las teselas del borde, en parte fuera de la caja, sí se piden a Esri.
