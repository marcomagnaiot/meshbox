# Instalación de meshbox

Este documento describe cómo se instala meshbox en una Raspberry Pi: el instalador `install.sh`, la imagen de SD con primer arranque, el punto de acceso de configuración, la disposición en disco y la solución de problemas. La instalación rápida está en el README; acá está el detalle.

## Instalación en una línea

En una Raspberry Pi con Raspberry Pi OS Lite de 64 bits (Debian 13 trixie) y conexión a internet:

```bash
# equipo dedicado (puerto 80)
curl -fsSL https://raw.githubusercontent.com/marcomagnaiot/meshbox/main/deploy/get.sh | sudo bash
# equipo compartido con otros servicios (puertos 8090 a 8092)
curl -fsSL https://raw.githubusercontent.com/marcomagnaiot/meshbox/main/deploy/get.sh | sudo bash -s -- --shared
```

`get.sh` averigua la última versión publicada en GitHub, baja el `install.sh` de esa versión y lo ejecuta con `--version`. El instalador baja el paquete, verifica la firma Ed25519 de `SHA256SUMS` con la clave embebida y recién entonces instala. Las opciones que siguen a `--` pasan tal cual a `install.sh` (sección 3.2).

Desde un clon del repositorio es lo mismo: `sudo ./deploy/get.sh [opciones]`. Para instalar otra versión: `sudo MESHBOX_VERSION=X.Y.Z ./deploy/get.sh`.

## 1. Modos de instalación

meshbox se instala en uno de dos modos (ADR 0004). El modo queda guardado en `/etc/meshbox-privd/privd.toml` y lo respetan el instalador, `meshbox-privd` y las actualizaciones.

| Aspecto | `appliance` (equipo dedicado) | `shared` (equipo compartido) |
|---|---|---|
| Uso típico | Imagen de SD o Pi exclusiva para meshbox | Pi que ya corre otros servicios (por ejemplo Home Assistant, Pi-hole o un servidor web) |
| Servidor LAN (público + panel) | `0.0.0.0:80` | `0.0.0.0:8090` |
| Servidor público (destino del túnel) | `127.0.0.1:8081` | `127.0.0.1:8091` |
| Administración remota (Access) | `127.0.0.1:8082` | `127.0.0.1:8092` |
| Mosquitto | 1883 | 1883 |
| Nombre de host | `meshbox` (o el indicado) | no se toca |
| WiFi y punto de acceso | los administra el panel | solo lectura (`wifi.status`, `wifi.scan`) |
| NetworkManager | se instala si falta | no se instala ni se configura |
| journald (`SystemMaxUse=50M`) | sí | no (es global) |
| Portal cautivo (dnsmasq de NM) | sí | no |
| `meshbox-firstboot` | sí (imagen) | no |

En modo `shared`, `meshbox-privd` rechaza `system.hostname`, `wifi.connect`, `wifi.forget`, `hotspot.start` y `hotspot.stop` con el código `not_allowed_in_shared_mode`. `system.timezone`, `system.reboot` y `system.shutdown` siguen permitidos, pero afectan a todo el equipo: el panel lo advierte (reiniciar corta los demás servicios).

## 2. Requisitos

- Raspberry Pi de 64 bits (probada para la Zero 2 W) con **Raspberry Pi OS Lite de 64 bits**. Recomendado: trixie (Debian 13, Python 3.13 del sistema). Soportado: bookworm (Debian 12), en cuyo caso el instalador usa un CPython 3.13 de uv en `/opt/meshbox/python` (ADR 0005).
- Al menos 350 MiB de RAM visibles y 2 GB libres en la SD (512 MB si se reinstala la misma versión).
- Red con salida a internet durante la instalación (paquetes apt y repositorio de Cloudflare). Las ruedas de Python vienen en el paquete: en la Pi no se compila ni se descarga nada de PyPI.
- Puertos libres según el modo y el 1883. Si alguno está ocupado por otro programa, el instalador se detiene con un mensaje que dice cuál; si el que escucha es meshbox (reinstalación) o Mosquitto del sistema (en el 1883), sigue.
- Si Mosquitto ya está instalado, no debe tener configuración propia que choque con la de meshbox (`listener`, `port`, `password_file`, `acl_file` o `allow_anonymous` en `mosquitto.conf`, u otros archivos en `conf.d/`). En ese caso el instalador se detiene y explica qué revisar.

## 3. Instalación con `install.sh`

### 3.1 Paquete de un release

Cada release publica tres archivos:

| Archivo | Contenido |
|---|---|
| `meshbox-X.Y.Z-linux-aarch64.tar.gz` | `wheels/`, `privd/`, `deploy/`, `bin/pmtiles`, `install.sh`, `VERSION` |
| `SHA256SUMS` | suma SHA-256 del paquete |
| `SHA256SUMS.sig` | firma Ed25519 de `SHA256SUMS` (64 bytes) |

```bash
mkdir -p ~/meshbox && cd ~/meshbox
# copiar aquí los tres archivos (scp, navegador, etc.)
tar -xzf meshbox-X.Y.Z-linux-aarch64.tar.gz meshbox-X.Y.Z/install.sh
sudo ./meshbox-X.Y.Z/install.sh --shared --from ~/meshbox/meshbox-X.Y.Z-linux-aarch64.tar.gz
```

Sin `--shared` el modo por defecto de una instalación nueva es `appliance`. El instalador verifica la firma con la clave pública embebida y la suma **antes** de tocar el sistema; si algo no coincide, se detiene sin instalar.

El instalador también puede descargar el release:

```bash
sudo ./install.sh --appliance --version X.Y.Z --updates-url https://github.com/marcomagnaiot/meshbox/releases/download
```

Si se ejecuta `install.sh` desde un paquete ya descomprimido y el `.tar.gz` está en la carpeta de al lado, usa el `.tar.gz` (para poder verificarlo).

### 3.2 Opciones

| Opción | Efecto |
|---|---|
| `--appliance` / `--shared` | Modo (ver sección 1). En una reinstalación se conserva el modo existente; cambiarlo exige `--change-mode`. |
| `--from RUTA` | `.tar.gz` con `SHA256SUMS` y `SHA256SUMS.sig` al lado, o una carpeta descomprimida (solo con `--insecure-skip-signature`). |
| `--version X.Y.Z` | Descarga esa versión desde `--updates-url`. |
| `--updates-url URL` | Base de releases (`<base>/vX.Y.Z/...`). Queda en `privd.toml` para las actualizaciones desde el panel. |
| `--site-slug SLUG` | Identificador del sitio para el bootstrap (por ejemplo `mizona`). |
| `--mqtt-root RAIZ` | Raíz de tópicos (por defecto `msh/AR/<slug>`). |
| `--hostname NOMBRE` | Solo `appliance`: nombre de host (por defecto `meshbox` si el actual es `raspberrypi`). |
| `--no-cloudflared` | No agrega el repositorio de Cloudflare ni instala `cloudflared`. |
| `--image` | Dentro del chroot de pi-gen: no verifica RAM ni puertos, no arranca servicios y deja pendiente `meshbox-firstboot`. |
| `--insecure-skip-signature` | Solo desarrollo: no verifica la firma (sí la suma, si hay `SHA256SUMS`). Avisa en rojo. |
| `--change-mode` | Permite pasar de un modo al otro en una instalación existente. |

### 3.3 Qué hace

1. Verifica root, `aarch64`, Debian 12 o posterior, RAM, puertos y la configuración previa de Mosquitto.
2. Prepara un área de trabajo root en `/opt/meshbox/.staging/` (en la SD: nada grande va a `/tmp`, que es RAM; `TMPDIR` apunta ahí).
3. Obtiene el paquete y verifica firma (`openssl pkeyutl -verify -pubin -rawin`) y suma (`sha256sum -c`).
4. `apt`: `mosquitto mosquitto-clients avahi-daemon sqlite3 openssl curl ca-certificates python3-venv iproute2`, más `network-manager dnsmasq-base` solo en `appliance`.
5. Repositorio apt de Cloudflare (`cloudflare-main.gpg`, distribución `any`) y `cloudflared`, con su origen agregado a `unattended-upgrades` (salvo `--no-cloudflared`).
6. Usuarios de sistema `meshbox` (grupo `dialout`) y `cloudflared`.
7. Directorios y permisos de la sección 4 (repara dueños y permisos de lo que ya exista).
8. Python 3.13: `/usr/bin/python3` si es 3.13; si no, uv 0.13.3 (binario verificado con su suma) y CPython 3.13 en `/opt/meshbox/python`.
9. `releases/<v>`: copia del paquete, entorno con `python -m venv` e instalación sin red (`pip install --no-index --find-links wheels/ meshbox==<v>`). Si la misma versión ya está instalada con las mismas ruedas, conserva el entorno; si las ruedas cambiaron (desarrollo), lo rehace y vuelve a la copia anterior si falla. Cambia `current` de forma atómica y conserva la versión actual, las dos anteriores y las posteriores.
10. `meshbox-privd` en `/usr/local/lib/meshbox-privd/` (root, 0755) y `/etc/meshbox-privd/privd.toml` (root, 0644).
11. Unidades systemd, `/etc/mosquitto/conf.d/meshbox.conf` y, en `appliance`, primer arranque, journald y portal cautivo.
12. `/etc/mosquitto/passwd` y `/etc/mosquitto/acl`: los crea vacíos si faltan; **si existen se conservan** (por ejemplo, cuentas creadas a mano) y solo se corrigen dueño y permisos (`mosquitto:mosquitto`, 0640).
13. `bin/pmtiles` en `/opt/meshbox/bin/pmtiles`.
14. Habilita y arranca `meshbox-privd.socket` y Mosquitto (lo reinicia solo si cambió su configuración efectiva).
15. `appliance`: nombre de host (vía privd) y avahi.
16. `meshbox bootstrap` como usuario `meshbox`: crea `config.toml` si falta, los secretos que falten, la cuenta `meshbox-ingest` y la ACL, y recarga Mosquitto. Es idempotente.
17. Arranca `meshbox.service` y el temporizador de respaldo, espera `GET /api/v1/health` hasta 90 s y muestra la dirección del asistente y el código de configuración.

Volver a ejecutarlo repara la instalación sin borrar datos (base, configuración, secretos, cuentas de Mosquitto).

### 3.4 Al terminar

```
meshbox X.Y.Z instalado (modo shared).
  Panel y asistente: http://192.168.0.10:8090  (o http://meshbox.local:8090)
  Código de configuración: ABCD1234 (se pide hasta crear el primer usuario)
```

El asistente sin usuario se cierra a los 60 minutos de cada arranque del servicio (13.2): si se vence, alcanza con reiniciar `meshbox`.

### 3.5 Desarrollo desde Windows

`scripts/deploy-dev.ps1 -Pi mipi` arma el paquete sin firma, lo copia con `scp` a `~/meshbox-deploy/` en la Pi y ejecuta allí `install.sh --shared --from ... --insecure-skip-signature`. Pide la clave de `sudo` con `Read-Host -AsSecureString` y la envía por la entrada estándar de `ssh` (nunca en la línea de comandos). Opciones: `-Mode appliance`, `-SkipBuild`, `-SkipFrontend`, `-SiteSlug`.

## 4. Disposición en disco y permisos

| Ruta | Dueño | Modo | Contenido |
|---|---|---|---|
| `/opt/meshbox/releases/<v>/` | root | 0755 | paquete del release y su `.venv` |
| `/opt/meshbox/current` | root | enlace | `releases/<v>` (cambio atómico) |
| `/opt/meshbox/python/` | root | 0755 | CPython 3.13 de uv (solo si el del sistema no es 3.13) |
| `/opt/meshbox/bin/pmtiles` | root | 0755 | binario arm64 de go-pmtiles |
| `/opt/meshbox/.staging/` | root | 0700 | temporales de instalación y actualización |
| `/usr/local/lib/meshbox-privd/` | root | 0755 | código de privd (no escribible por `meshbox`) |
| `/etc/meshbox-privd/privd.toml` | root | 0644 | modo, salud, base de releases, Python |
| `/var/lib/meshbox-privd/` | root | 0700 | estado de trabajos de privd, último escaneo WiFi |
| `/etc/meshbox/` | meshbox | 0750 | `config.toml` (0640) y `secrets.toml` (0600) |
| `/etc/meshbox-tunnel/` | root | 0700 | `cloudflared.env` (0600, lo escribe privd) |
| `/var/lib/meshbox/` | meshbox | 0750 | `meshbox.db`, `tiles/`, `plugins/`, `rec/` |
| `/var/lib/meshbox/backups/` | meshbox | 0700 | respaldos |
| `/var/lib/meshbox/tmp/` | meshbox | 0700 | `TMPDIR` de la aplicación |
| `/etc/mosquitto/conf.d/meshbox.conf` | root | 0644 | configuración de 14.1 |
| `/etc/mosquitto/passwd`, `/etc/mosquitto/acl` | mosquitto | 0640 | cuentas y ACL (los administra privd) |
| `/etc/systemd/journald.conf.d/meshbox.conf` | root | 0644 | solo `appliance` |
| `/etc/NetworkManager/dnsmasq-shared.d/meshbox-captive.conf` | root | 0644 | solo `appliance` |
| `/usr/local/sbin/meshbox-firstboot` | root | 0755 | solo `appliance` |

## 5. Servicios

| Unidad | Usuario | Notas |
|---|---|---|
| `meshbox.service` | meshbox | `Type=notify` (`READY=1`, `WATCHDOG=1` cada 20 s, `WatchdogSec=60`); `ExecStartPre` con `meshbox migrate`; endurecido (13.4); `TMPDIR=/var/lib/meshbox/tmp`; se saltea si no hay `config.toml` |
| `meshbox-privd.socket` | root | `/run/meshbox/privd.sock`, `root:meshbox` 0660, `Accept=no` |
| `meshbox-privd.service` | root | `python3 -I .../meshbox_privd.py serve`; sale tras 10 min sin actividad ni trabajos |
| `mosquitto.service` | mosquitto | del sistema, con `conf.d/meshbox.conf` |
| `meshbox-cloudflared.service` | cloudflared | `cloudflared --no-autoupdate tunnel run` con `TUNNEL_TOKEN` del archivo de entorno; se saltea si no hay token |
| `meshbox-backup.timer` / `.service` | meshbox | 03:00 con hasta 15 min de demora; `meshbox backup create` |
| `meshbox-firstboot.service` | root | solo `appliance`, una vez |

## 6. meshbox-privd

Servicio root con una lista cerrada de comandos (13.3). Protocolo: una línea JSON por conexión al socket (`{"cmd", "args", "request_id"}` → `{"request_id", "ok", "result" | "error"}`); la referencia completa de comandos está en el encabezado de `privd/meshbox_privd.py`. Para el instalador y el primer arranque hay un modo de una sola vez con las mismas validaciones:

```bash
echo '{"cmd":"ping"}' | sudo python3 -I /usr/local/lib/meshbox-privd/meshbox_privd.py call
```

Registra cada comando en el journal sin secretos (`journalctl -u meshbox-privd`). Si `privd.toml` falta, no es de root o es escribible por otros usuarios, lo ignora y usa valores seguros (modo `shared`, sin actualizaciones).

## 7. Actualizaciones

Desde el panel, `update.apply {version}` corre como trabajo en segundo plano (`update.status {job}` informa el paso):

1. Descarga `SHA256SUMS`, `SHA256SUMS.sig` y el paquete desde `updates_base_url/vX.Y.Z/` a `/opt/meshbox/.staging/`.
2. Verifica la firma con la clave pública embebida en privd y la suma.
3. Descomprime en `releases/<v>`, crea el entorno e instala las ruedas sin red.
4. Respaldo de la base con sufijo `pre-<v>` (como `meshbox`).
5. Instala privd, unidades y configuración de Mosquitto del release, cambia `current` y reinicia meshbox.
6. Espera la salud 90 s (`status: ok` y `version` igual a la nueva). Si no responde, vuelve a la versión anterior (y a sus unidades y su privd) y, si la revisión de Alembic cambió, restaura el respaldo.
7. Conserva dos versiones anteriores; privd sale y el socket lo levanta con el código nuevo.

`update.rollback` vuelve a la versión anterior a pedido; si la actualización había migrado la base, restaura el respaldo `pre-<v>` (se pierden los datos posteriores a la actualización).

## 8. Imagen de SD (modo appliance)

### 8.1 Cómo se genera

`release.yml` arma el paquete firmado y, en el job `image`, ejecuta pi-gen (rama `arm64`, Raspberry Pi OS trixie Lite) con el stage propio `deploy/image/stage-meshbox`, que copia el paquete al rootfs y ejecuta `install.sh --image --appliance` dentro del chroot (la firma se verifica igual que en la Pi). El resultado, `meshbox-X.Y.Z-arm64.img.xz`, se publica con `SHA256SUMS-image` y su firma.

### 8.2 Raspberry Pi Imager y cloud-init

En trixie la personalización de Raspberry Pi Imager (red WiFi, usuario, clave, SSH, nombre de host) llega por **cloud-init**: Imager escribe `user-data`, `network-config` y `meta-data` en la partición de arranque, y `cmdline.txt` lleva `ds=nocloud` para que cloud-init los lea. La imagen de meshbox se genera con cloud-init activo, así que esa personalización funciona igual que en la imagen oficial.

- `meshbox-firstboot` se ordena después de `cloud-init.service` y `cloud-init-network.service`: si Imager fijó un nombre de host, se respeta; si no, queda `meshbox`.
- Cuando el panel cambia el nombre de host, privd deja `/etc/cloud/cloud.cfg.d/99-meshbox-hostname.cfg` con `preserve_hostname: true` y `manage_etc_hosts: false` para que cloud-init no lo revierta.
- Sin personalización de Imager no hay usuario de Linux habilitado; meshbox funciona igual (se administra desde el navegador) y el punto de acceso cubre la configuración de la red.
- Las redes WiFi que configura cloud-init (vía netplan) aparecen en NetworkManager como conexiones generadas: `wifi.forget` las borra hasta el próximo arranque, pero cloud-init las vuelve a generar mientras sigan en `network-config`.

### 8.3 Primer arranque

`meshbox-firstboot.service` corre una sola vez (hasta que existe `/var/lib/meshbox/.firstboot-done`):

1. `meshbox bootstrap --mode appliance` como `meshbox` (secretos, `config.toml`, cuenta `meshbox-ingest`, ACL). El código de configuración queda en `/boot/firmware/meshbox-codigo.txt` (se lee sacando la tarjeta o por SSH; conviene borrarlo al terminar).
2. Nombre de host `meshbox` si el actual es `raspberrypi`.
3. La base la crea `meshbox.service` (migraciones), que arranca después.
4. Espera red 90 s; si NetworkManager no queda conectado, levanta el punto de acceso.
5. Marca `.firstboot-done`. Si algo falla, no marca y se reintenta en el próximo arranque.

### 8.4 Punto de acceso de configuración

- SSID `meshbox-XXXX` (últimos 4 dígitos hexadecimales de la MAC de `wlan0`), WPA2-PSK (CCMP, PMF desactivado por compatibilidad con el WiFi de la Pi), dirección `10.42.0.1/24`, DHCP y DNS de NetworkManager en modo compartido.
- Clave: la de `/boot/firmware/meshbox-setup.txt` si existe y es válida (8 a 63 caracteres ASCII imprimibles). Formato: una línea `clave=MiClaveSegura` (también se acepta `password=` o `hotspot_password=`, o un archivo con una sola línea que es la clave; se toleran BOM y fines de línea de Windows). Si no, la clave por defecto **`meshbox-setup`**.
- Portal cautivo: `address=/#/10.42.0.1` en el dnsmasq de NetworkManager resuelve cualquier nombre hacia la Pi; el servidor LAN redirige las URLs de detección de Android, iOS y Windows a `/setup`. Si el teléfono no lo detecta, abrir `http://10.42.0.1`.
- Antes de levantar el punto de acceso, privd escanea las redes y guarda el resultado: con una sola radio no se puede escanear en modo AP, y `wifi.scan` devuelve ese escaneo guardado (`cached: true`).
- `wifi.connect {ssid, psk}` es un trabajo con ventana de 2 minutos: si la red nueva no conecta, vuelve a la anterior o, si no había, al punto de acceso. La clave nunca pasa por la línea de comandos: el perfil se escribe como keyfile 0600 en `/etc/NetworkManager/system-connections/`.
- Pendiente del backend: apagar el punto de acceso después de 30 minutos sin uso (`hotspot.stop`, que además reintenta la red conocida).

## 9. Memoria (ADR 0006)

La Pi Zero 2 W arranca con `cgroup_disable=memory`: `MemoryHigh` y `MemoryMax` de las unidades no se aplican y la aplicación tiene su propia guardia de RSS. Opcional, con reinicio (en un equipo compartido, coordinarlo): agregar `cgroup_enable=memory` al final de la línea de `/boot/firmware/cmdline.txt` y `gpu_mem=16` en `/boot/firmware/config.txt` (recupera unos 48 MB sin pantalla). El instalador no lo hace solo.

## 10. Solución de problemas

| Síntoma | Qué revisar |
|---|---|
| "El puerto N está ocupado por ..." | `sudo ss -tlnp 'sport = :N'`. Liberarlo o usar el otro modo. |
| "Mosquitto ya tiene configuración propia" | Los archivos que nombra el mensaje: mover a `conf.d/meshbox.conf` lo que haga falta o quitar el `listener` duplicado. |
| "La firma de SHA256SUMS no es válida" | El paquete no viene del release oficial o está alterado: descargarlo de nuevo y verificar a mano (ver `SECURITY.md`). |
| Mosquitto no arranca | `journalctl -u mosquitto -n 50`; dueño y permisos de `passwd` y `acl` (`mosquitto:mosquitto`, 0640); que no haya dos `listener 1883`. |
| meshbox no responde al terminar | `journalctl -u meshbox -n 100`; `systemctl status meshbox`; `sudo -u meshbox /opt/meshbox/current/.venv/bin/python -m meshbox migrate --config /etc/meshbox/config.toml`. |
| El panel no puede cambiar algo del sistema | `journalctl -u meshbox-privd -n 50` (cada comando queda registrado con su resultado); `systemctl status meshbox-privd.socket`. |
| Actualización que no avanza | `update.status` en el panel; `journalctl -u meshbox-privd`. Un trabajo cortado por un reinicio de privd queda `interrupted`; `update.rollback` vuelve a la versión anterior. |
| Túnel de Cloudflare caído | `systemctl status meshbox-cloudflared`; que exista `/etc/meshbox-tunnel/cloudflared.env`. |
| No aparece `meshbox.local` | Algunos Android no resuelven `.local`: usar la IP (lista de dispositivos del router o `hostname -I`). |

## 11. Desinstalación (manual)

No hay desinstalador. Para quitar meshbox conservando o no los datos:

```bash
sudo systemctl disable --now meshbox.service meshbox-backup.timer meshbox-cloudflared.service \
  meshbox-privd.socket meshbox-privd.service meshbox-firstboot.service
sudo rm -f /etc/systemd/system/meshbox*.service /etc/systemd/system/meshbox*.socket \
  /etc/systemd/system/meshbox*.timer /etc/mosquitto/conf.d/meshbox.conf \
  /etc/systemd/journald.conf.d/meshbox.conf /etc/NetworkManager/dnsmasq-shared.d/meshbox-captive.conf \
  /usr/local/sbin/meshbox-firstboot /etc/apt/apt.conf.d/52meshbox-cloudflared
sudo systemctl daemon-reload
sudo rm -rf /opt/meshbox /usr/local/lib/meshbox-privd /etc/meshbox-privd /var/lib/meshbox-privd \
  /etc/meshbox-tunnel
# Datos y configuración (irreversible): /var/lib/meshbox y /etc/meshbox
```

`passwd` y `acl` de Mosquitto quedan en su lugar (pueden tener cuentas usadas por otros sistemas).
