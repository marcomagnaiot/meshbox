# ADR 0001 · Decisiones tomadas del plan (T1-T10)

Estado: aceptada · 20/10/2026

## Contexto

El plan original del proyecto (sección 3.1) fija diez decisiones antes de empezar. Se registran acá para que cualquier cambio posterior tenga un ADR que lo reemplace.

## Decisión

| N.º | Decisión |
|---|---|
| T1 | Backend en Python 3.13, con la librería oficial `meshtastic` para el protocolo USB y las definiciones protobuf. |
| T2 | FastAPI con uvicorn, un solo proceso asyncio. |
| T3 | SQLite en modo WAL. |
| T4 | Mosquitto como broker del sistema. |
| T5 | Frontend SvelteKit + Svelte 5 compilado a estáticos (en la Pi no corre Node). |
| T6 | MapLibre GL JS + Protomaps; extracto PMTiles local servido como teselas `z/x/y`. |
| T7 | Tiempo real público por Server-Sent Events. |
| T8 | Servidores HTTP separados en el mismo proceso: público, LAN (público + administración) y administración remota opcional detrás de Cloudflare Access. |
| T9 | Operaciones root en `meshbox-privd`, con lista cerrada de comandos. |
| T10 | Releases firmados con Ed25519 y actualización con vuelta atrás. |

## Consecuencias

Se adoptan sin cambios. Los ajustes por instalar en un equipo compartido están en el ADR 0004 y no cambian ninguna de estas decisiones; cambian puertos y alcance del panel.
