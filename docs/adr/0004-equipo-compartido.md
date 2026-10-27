# ADR 0004 · Instalación en un equipo compartido

Estado: aceptada · 20/10/2026

## Contexto

El plan supone una Raspberry dedicada (nombre `meshbox`, servidor LAN en el puerto 80, panel que administra WiFi, punto de acceso de configuración, imagen de SD propia). Pero muchas Pi ya corren otros servicios que no deben interrumpirse (por ejemplo Home Assistant, Pi-hole o un servidor web).

## Decisión

Se agrega un modo de instalación **compartido** (`[host] mode = "shared"`), además del modo **dedicado** (`"appliance"`, el del plan):

| Aspecto | Dedicado (plan) | Compartido |
|---|---|---|
| Servidor LAN (público + panel) | `0.0.0.0:80` | `0.0.0.0:8090` |
| Servidor público (destino del túnel) | `127.0.0.1:8081` | `127.0.0.1:8091` |
| Administración remota (Access) | `127.0.0.1:8082` | `127.0.0.1:8092` |
| Mosquitto | 1883 | 1883 |
| Nombre de host | lo cambia el panel (`meshbox`) | no se toca |
| WiFi y punto de acceso | los administra el panel | solo lectura de estado |
| journald (`SystemMaxUse`) | lo fija el instalador | no se toca (es global) |
| `meshbox-firstboot` | sí | no |

En modo compartido, `privd` rechaza `system.hostname`, `wifi.connect`, `wifi.forget`, `hotspot.start` y `hotspot.stop` con el código `not_allowed_in_shared_mode`, y el panel no muestra esas acciones.

Todo lo de meshbox vive en carpetas propias: `/opt/meshbox`, `/etc/meshbox`, `/etc/meshbox-tunnel`, `/var/lib/meshbox`, `/usr/local/lib/meshbox-privd`, con usuario de sistema `meshbox`.

## Consecuencias

- Acceso en la red local: `http://<ip-de-la-pi>:8090` o `http://<nombre>.local:8090`.
- La verificación de salud usa el puerto público configurado (`http://127.0.0.1:8091/api/v1/health` en modo compartido).
- El instalador detecta puertos ocupados antes de instalar y se detiene con un mensaje claro.
- Reiniciar o apagar la Pi desde el panel también corta los demás servicios: el diálogo de confirmación lo dice.
