# ADR 0021 · Páginas propias en el sitio público

Estado: aceptada · 02/11/2026 · amplía las secciones 12.2 y 20 del plan

## Contexto

Quien administra una red quiere publicar documentos junto al mapa: el informe de una apertura troposférica, un boletín en PDF, los datos para verificarlo. Copiarlos dentro de la carpeta del build no alcanza por tres razones:

- Cada actualización reemplaza esa carpeta y los borra.
- El service worker respondía con la aplicación en caché a toda navegación del sitio. Quien ya había abierto el mapa veía el mapa en lugar del documento.
- La CSP del sitio bloquea los scripts en línea y los recursos de otros dominios. Un informe con su script escrito en el HTML y tipografías de Google Fonts se ve, pero sin esas partes.

## Decisión

- `paths.pages` (por defecto `/var/lib/meshbox/pages`) es una carpeta de páginas propias. El sitio público y el de la red local sirven sus archivos con la misma ruta, y una carpeta con `index.html` como página (sin la barra final, redirige con 301). El panel desde afuera no las sirve.
- El build se revisa antes: una página no tapa un archivo de la aplicación. Tampoco se publican los prefijos `admin`, `setup`, `api`, `tiles` y `_app`, ni archivos o carpetas que empiezan con punto, ni nada fuera de la carpeta.
- Las páginas llevan la CSP y las cabeceras del sitio, sin excepciones.
- El service worker responde con la aplicación solo en sus rutas públicas, que están listadas en `frontend/src/lib/pwa/routes.ts`. Una prueba recorre `src/routes/(public)` y falla si falta alguna. Lo demás va a la red.
- La instalación crea la carpeta. Las actualizaciones no la tocan.

## Alternativas descartadas

- Una CSP más permisiva para las páginas (scripts en línea, Google Fonts): abre en el mismo origen del sitio lo que la CSP cierra. Un documento que siga las reglas del sitio se arma igual, con el script en un archivo aparte y las tipografías en la carpeta.
- Una regla del túnel de Cloudflare hacia otro servidor de archivos: suma un servicio en la Pi y no resuelve el service worker, porque es el mismo origen.
- Subir las páginas desde el panel: queda para más adelante. Por ahora se copian por SSH, como los plugins.

## Consecuencias

- Una ruta pública nueva de la aplicación tiene que sumarse a `routes.ts` para abrir sin conexión. Si falta, la ruta igual funciona con red.
- Las páginas propias necesitan red: el service worker no las guarda.
- Todo lo que esté en la carpeta es público.
