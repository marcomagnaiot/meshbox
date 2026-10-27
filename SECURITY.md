# Seguridad

## Reportar una vulnerabilidad

Escribir a **marcomagna@gmail.com** con el asunto `meshbox: seguridad`, sin abrir un issue público. Incluir versión, pasos para reproducir e impacto. Se responde en una semana; los avisos se publican junto con la versión que corrige el problema.

## Modelo de seguridad (resumen)

Detalle en `docs/arquitectura.md` y `docs/privacidad.md`.

| Amenaza | Mitigación |
|---|---|
| Texto malicioso en nombres o mensajes recibidos por radio | El frontend nunca interpreta HTML de datos (`{@html}` prohibido por lint); el aviso de privacidad llega como bloques JSON; recorte de longitudes |
| Panel expuesto a internet | El servidor público (destino del túnel) no tiene rutas de panel; el remoto exige el JWT de Cloudflare Access además de la sesión |
| Fuerza bruta en el login | argon2id (t=3, m=32 MiB), 5 intentos por minuto por IP, espera creciente por usuario |
| CSRF | Cookie `SameSite=Strict` y token por sesión en `X-CSRF-Token` |
| Escalada desde la aplicación | El servicio corre sin privilegios y endurecido; las operaciones root pasan por `meshbox-privd` con lista cerrada de comandos, validación estricta y sin `shell=True` |
| Inyección de paquetes en la radio por MQTT | Bajada apagada en el gateway (`downlink_enabled false`); ACL de Mosquitto por propósito |
| Actualización adulterada | Firma Ed25519 verificada por privd con la clave pública embebida (ver abajo) |
| Fuga de secretos | `secrets.toml` 0600, campos de solo escritura en la API, filtro de secretos en los registros, exportación de secretos solo cifrada |
| Robo de la tarjeta SD | Riesgo aceptado: los secretos quedan legibles. Si se pierde el equipo, revocar el token del túnel y el de la API de Cloudflare, y rotar las cuentas MQTT |
| Dependencias vulnerables | `uv.lock` y `pnpm-lock.yaml`; `pip-audit`, `pnpm audit` y `bandit` en CI |

# Claves de firma de releases

## Cómo se firman los releases

- Cada release publica `meshbox-X.Y.Z-linux-aarch64.tar.gz`, `SHA256SUMS` y `SHA256SUMS.sig`. La imagen de SD se publica con `SHA256SUMS-image` y `SHA256SUMS-image.sig`.
- La firma es **Ed25519 pura** sobre el archivo de sumas: `SHA256SUMS.sig` tiene exactamente 64 bytes. La genera `scripts/sign-release.py` (biblioteca `cryptography`) con la clave privada del secreto de GitHub `MESHBOX_SIGNING_KEY`.
- La clave pública está **embebida** en dos lugares, que deben coincidir:
  - `privd/commands/update.py`, constante `RELEASE_PUBLIC_KEY_PEM` (actualizaciones desde el panel);
  - `deploy/install.sh`, variable `MESHBOX_RELEASE_PUBKEY` (instalación nueva).
  `scripts/build-release.py` se niega a armar un paquete si no coinciden, y una prueba de CI lo verifica.
- En la Pi la firma se verifica con OpenSSL 3 del sistema, sin dependencias de Python:

  ```bash
  openssl pkeyutl -verify -pubin -inkey publica.pem -rawin -in SHA256SUMS -sigfile SHA256SUMS.sig
  sha256sum -c --ignore-missing SHA256SUMS
  ```

  Una prueba de CI firma con `cryptography` y verifica con `openssl pkeyutl -rawin` para asegurar la compatibilidad.
- `build-release.py --sign-key` (o `--sign-key-env`) exige que la clave de firma corresponda a la pública embebida; solo `--allow-key-mismatch` (rotación, ver abajo) lo permite.

## Clave actual

Los releases se firman desde la versión 0.8.0 con esta clave. La privada no está en el repositorio: vive en el secreto `MESHBOX_SIGNING_KEY` de GitHub y en una copia fuera de línea del autor.

| Dato | Valor |
|---|---|
| Huella (SHA-256 de la clave pública en DER) | `2f015b6e2c35dbd59174f5edfcb6fd8c4c6344819ef044f792424765d9999585` |

```
-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAFcM6F5vQWKziqfj+rf1S0ePm+z6zD5VNb8Pd3fDD9VE=
-----END PUBLIC KEY-----
```

La huella de cualquier clave pública se calcula con:

```bash
openssl pkey -pubin -in publica.pem -outform DER | sha256sum
```

## Generar un par de claves (fork propio o rotación)

1. En una máquina de confianza, fuera del repositorio:

   ```bash
   uv run --no-project --with "cryptography>=44" python scripts/sign-release.py --generate      --out-dir ~/.meshbox/signing --name meshbox-release
   ```

   Genera `meshbox-release-private.pem` (PKCS#8 sin cifrar; 0600 en Linux, ACL solo del usuario en Windows) y `meshbox-release-public.pem`, e imprime la pública. El script se niega a escribir dentro del repositorio, y `.gitignore` excluye `*.pem`, `*.key` y `signing/`.
2. Guardar una **copia fuera de línea** de la privada (por ejemplo, un pendrive cifrado y un gestor de contraseñas). Sin ella no se puede firmar ni rotar en orden.
3. Cargarla como secreto del repositorio (o, mejor, de un *environment* `release` con revisores obligatorios):

   ```bash
   gh secret set MESHBOX_SIGNING_KEY < ~/.meshbox/signing/meshbox-release-private.pem
   ```

4. Reemplazar la pública embebida por la nueva en `privd/commands/update.py` y `deploy/install.sh` (el bloque PEM completo), y actualizar la huella en este documento.
5. Verificar y publicar: `uv run pytest privd/tests deploy/tests scripts/tests` (incluye la coincidencia de las claves) y un release de prueba firmado con `--sign-key` que privd e `install.sh` acepten.

Si ya hay equipos instalados con la clave anterior, corresponde el procedimiento de rotación.

## Rotación planificada

Los equipos solo aceptan actualizaciones firmadas con la clave que tienen embebida. Para cambiarla sin dejarlos atrás:

1. Generar el par nuevo (pasos 1 y 2 de arriba).
2. **Release puente**: cambiar la pública embebida por la nueva y firmar ese release con la clave **vieja**:

   ```bash
   uv run python scripts/build-release.py --sign-key vieja-private.pem --allow-key-mismatch
   ```

   Los equipos lo verifican con la clave vieja y, al instalarlo, quedan con la nueva.
3. Cambiar el secreto `MESHBOX_SIGNING_KEY` por la clave nueva. Todos los releases siguientes se firman con ella.
4. Los equipos que no instalaron el release puente necesitan pasar por él (instalándolo antes de seguir) o reinstalar con `install.sh` de una versión nueva, que trae la clave nueva y verifica con ella.
5. Publicar en el release puente y en este documento la huella de la clave nueva.

## Si la clave privada se filtra

No hay revocación automática: un equipo acepta cualquier paquete firmado con la clave que tiene embebida.

1. Generar un par nuevo y retirar la clave filtrada del secreto de GitHub.
2. Publicar un aviso con la huella de la clave nueva por un canal independiente del repositorio (por ejemplo, el sitio del autor).
3. Publicar un release firmado con la clave nueva. Los equipos **no** lo van a aceptar desde el panel (verifican con la clave filtrada): hay que reinstalarlos a mano con `install.sh` de ese release, después de verificar la huella de la clave embebida en el `install.sh` descargado.
4. Hasta reinstalar, no aplicar actualizaciones desde el panel en esos equipos.

## Verificación manual de un release

```bash
# 1. Clave pública (del repositorio o del aviso) y su huella
openssl pkey -pubin -in meshbox-release-public.pem -outform DER | sha256sum
# 2. Firma de las sumas y suma del paquete
openssl pkeyutl -verify -pubin -inkey meshbox-release-public.pem -rawin \
  -in SHA256SUMS -sigfile SHA256SUMS.sig
sha256sum -c --ignore-missing SHA256SUMS
```
