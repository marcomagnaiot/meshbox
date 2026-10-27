# ADR 0002 · Decisiones abiertas (D1-D6) con su valor por defecto

Estado: aceptada · 20/10/2026

## Contexto

El plan deja seis decisiones abiertas con un valor por defecto (sección 3.2). Se tomaron los valores por defecto.

## Decisión

| N.º | Decisión | Valor adoptado | Pendiente |
|---|---|---|---|
| D1 | Nombre | `meshbox` | Verificar GitHub y PyPI antes de publicar. |
| D2 | Licencia | Apache-2.0 | No se copió código de terceros; si se toma algo de Potato Mesh o Malla, citarlo en `NOTICE`. |
| D3 | Repositorio | Git local; después GitHub | Publicado en GitHub. |
| D4 | Idiomas | Español por defecto e inglés | — |
| D5 | Capa satelital | Esri World Imagery con atribución, desactivable desde el panel | Revisar términos de Esri antes de publicar. |
| D6 | Dominio | `mesh.<dominio>` público y `admin-mesh.<dominio>` opcional | Lo define quien instala, al configurar Cloudflare. |

## Consecuencias

Todos los valores son configurables; cambiarlos no requiere tocar código.
