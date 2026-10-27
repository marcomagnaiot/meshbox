# ADR 0014 · Panel por internet con usuario y clave, sin Cloudflare Access

Estado: aceptada · 21/10/2026

## Contexto

El plan (15.3) publica el panel por internet solo detrás de Cloudflare Access: un hostname propio, un JWT de Access verificado en el servidor remoto y, además, la sesión normal. Para usar Access hay que activar Zero Trust, y Cloudflare pide una tarjeta aunque el plan Free cuesta $0. Hace falta otra forma de entrar por un hostname de administración, con usuario y clave, para quien no quiera cargar la tarjeta.

## Decisión

El servidor remoto (`admin_remote_bind`, 127.0.0.1:8092 en modo compartido) tiene dos modos, elegidos con `[cloudflare] remote_admin_auth`:

- `access` (por defecto, el del plan): exige el JWT de Access en todo el panel y el asistente.
- `password`: el panel queda protegido solo por la autenticación de meshbox (argon2id, sesión con cookie `Secure`, `HttpOnly` y `SameSite=Strict`, CSRF, roles y auditoría). Para achicar lo expuesto:
  - el asistente `/setup` y `/api/v1/setup` no existen en ese servidor (404);
  - reiniciar o apagar el equipo solo se hace desde la red local (403), porque en un equipo compartido corta otros servicios;
  - las respuestas llevan `X-Robots-Tag: noindex, nofollow`;
  - los límites de inicio de sesión siguen igual: 5 fallos por minuto por IP (la IP real, de `CF-Connecting-IP`, en la que se confía solo si viene de cloudflared) y espera creciente de hasta 1 h para el usuario después de 10 fallos seguidos.

En Cloudflare, con el plan gratuito:

- una regla del túnel `meshbox-admin.<dominio> → http://127.0.0.1:8092`, con la regla final 404 de siempre;
- una regla de firewall (WAF, regla personalizada) que bloquea ese hostname para conexiones de fuera del país del sitio.

## Riesgos que quedan

- La clave es la única barrera. Una clave corta o de diccionario se puede adivinar con tiempo, aunque los límites lo hacen lento. Con el panel en internet, conviene una clave larga (tres o cuatro palabras).
- Un fallo de seguridad en el panel queda expuesto a internet; con Access, solo a quien pasó el control de Cloudflare.
- Intentar con un usuario existente puede bloquearlo hasta 1 h (es una forma de molestar, no de entrar).

Lo que no se puede hacer desde el panel, ni siquiera con la clave: instalar código (las actualizaciones tienen que venir firmadas y los plugins se instalan copiando carpetas en el equipo) ni tocar la red del equipo (bloqueado en modo compartido).

## Para volver al plan

Activar Zero Trust, crear la aplicación de Access para el hostname (desde el panel, modo API de Cloudflare) y poner `remote_admin_auth = "access"`.
