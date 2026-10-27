# Publicar en internet con Cloudflare

El sitio público se publica con **Cloudflare Tunnel**: la Pi abre una conexión saliente hacia Cloudflare y no hace falta abrir puertos en el router. El túnel apunta **solo al servidor público** (`127.0.0.1:8091` en modo compartido, `127.0.0.1:8081` en modo dedicado), que no tiene panel: `/admin` y `/setup` no existen ahí.

Hay dos formas de configurarlo, ambas desde **Panel → Cloudflare**.

## Modo token (simple)

1. En Cloudflare: **Zero Trust → Networks → Tunnels → Create a tunnel** (tipo *Cloudflared*), con un nombre como `meshbox-mizona`.
2. En la pestaña *Public Hostname*, agregar el hostname público (por ejemplo `mesh.tudominio.com.ar`) con servicio **`http://127.0.0.1:8091`**. Usar `127.0.0.1`, no `localhost` (puede resolver a IPv6).
3. Copiar el **token** del túnel (el comando de instalación lo muestra después de `--token`).
4. En el panel de meshbox, **Cloudflare → Modo token**: pegar el token y el hostname. `privd` guarda el token en `/etc/meshbox-tunnel/cloudflared.env` (root, 0600) y habilita `meshbox-cloudflared.service`.
5. El panel muestra el estado del servicio y prueba `https://<hostname>/api/v1/health`.

## Modo API (automático)

El panel crea el túnel, sus reglas y el DNS con un **token de API**.

### Token de API

En Cloudflare: **My Profile → API Tokens → Create Token → Custom token**, con estos permisos y nada más:

| Alcance | Permiso | Nivel |
|---|---|---|
| Cuenta | Cloudflare Tunnel | Edit |
| Zona | DNS | Edit |
| Zona | Zone | Read |
| Cuenta (solo para administración remota) | Access: Apps and Policies | Edit |

En *Zone Resources*, limitarlo a la zona del dominio.

### Pasos

1. **Cloudflare → Modo API → Verificar token**: el panel valida el token y lista las zonas.
2. Elegir la zona y escribir el hostname público (`mesh.<dominio>`) y, opcionalmente, el de administración (`admin-mesh.<dominio>`).
3. **Publicar**. El panel:
   1. crea (o reutiliza) el túnel `meshbox-<slug>` con configuración administrada por Cloudflare;
   2. configura las reglas: `mesh.<dominio>` → `http://127.0.0.1:8091` y, si corresponde, `admin-mesh.<dominio>` → `http://127.0.0.1:8092`, más la regla final `http_status:404`;
   3. crea los registros DNS `CNAME <id>.cfargotunnel.com` con proxy. Si ya existe un registro con ese nombre, pide confirmación para reemplazarlo;
   4. guarda el token del túnel con `privd` y habilita el servicio;
   5. espera hasta 60 s a que el túnel esté `healthy` y prueba el sitio.

## Administración remota con Access

Para entrar al panel desde fuera de casa por HTTPS:

1. Publicar con un hostname de administración (modo API).
2. **Cloudflare → Administración remota**: escribir los correos autorizados. El panel crea una aplicación Access *self-hosted* para ese hostname con una política que solo permite esos correos, y guarda el dominio del equipo y el `aud` en `config.toml`.
3. Reiniciar meshbox: se levanta el servidor de administración remota (`127.0.0.1:8092`), que exige un JWT válido de Access (`Cf-Access-Jwt-Assertion`, verificado contra las claves públicas del equipo) en toda ruta del panel y del asistente, además de la sesión normal.

En la red local el panel sigue por HTTP (el panel lo advierte). Desde internet, solo por el hostname con Access.

### Sin Access: solo usuario y clave (ADR 0014)

Si no se activa Zero Trust (Cloudflare pide tarjeta aunque el plan Free cuesta $0), el servidor remoto puede funcionar solo con la autenticación de meshbox: `[server] admin_remote_bind = "127.0.0.1:8092"` y `[cloudflare] remote_admin_auth = "password"`. En ese modo el asistente no existe por internet y reiniciar o apagar el equipo solo se puede desde la LAN. En Cloudflare se agregan la regla del túnel para el hostname de administración y una regla de firewall que lo limita al país. Usar una clave larga.

## Desconectar

**Cloudflare → Desconectar** detiene el servicio. Opcionalmente borra los registros DNS, la aplicación Access y el túnel.

## Nombres de host

El certificado universal gratuito de Cloudflare cubre el dominio y **un** nivel de subdominio (`*.dominio`). Usar `meshbox.dominio` o `meshbox-admin.dominio`; `www.meshbox.dominio` o `admin.meshbox.dominio` dan error de certificado salvo con un certificado avanzado (pago).

## Por línea de comandos

`cloudflared` también sirve desde una PC para administrar túneles y su DNS:

```powershell
winget install --id Cloudflare.cloudflared
cloudflared tunnel login          # abre el navegador: elegir la zona y autorizar (deja ~/.cloudflared/cert.pem)
cloudflared tunnel list
cloudflared tunnel route dns <túnel> meshbox.<dominio>   # CNAME con proxy hacia el túnel
cloudflared tunnel token <túnel>  # token para el modo token del panel
```

Las reglas de un túnel con configuración remota se cambian en el panel de Cloudflare o con la API (`PUT /accounts/<cuenta>/cfd_tunnel/<id>/configurations`).

## Reutilizar un túnel viejo

Un túnel existente se puede usar en modo token, pero **antes de conectarlo hay que reemplazar sus reglas**: las viejas pueden apuntar a puertos que hoy usa otro servicio del equipo, y conectarlo sin cambiarlas lo publicaría. Pasos:

1. Guardar la configuración actual (`GET .../configurations`).
2. Reemplazarla por `meshbox.<dominio> → http://127.0.0.1:8091` y la regla final `http_status:404` (el túnel pasa a configuración remota).
3. `cloudflared tunnel route dns <túnel> meshbox.<dominio>` y `cloudflared tunnel token <túnel>` → modo token del panel.

Los registros DNS viejos que siguen apuntando al túnel responden 404.

## Estado

El panel muestra modo, hostnames, estado del servicio `cloudflared`, estado del túnel (en modo API: `healthy`, `degraded`, `inactive`, cantidad de conexiones), última verificación del sitio y los botones para volver a probar, reiniciar y desconectar.

## Caché recomendada

Crear en Cloudflare una regla de caché para `/_app/immutable/*` y `/tiles/*` (respetar los encabezados del origen). Los datos en vivo (`/api/v1/nodes`, `/api/v1/stream`) salen con `no-store` y no se cachean.
