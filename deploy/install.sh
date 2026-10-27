#!/usr/bin/env bash
# Instalador de meshbox para Raspberry Pi OS Lite de 64 bits (Debian 12 bookworm o 13 trixie).
#
#   sudo ./install.sh [--appliance | --shared] [--from PAQUETE] [opciones]
#
# Modos (ADR 0004):
#   --appliance  equipo dedicado (por defecto): puertos 80/8081/8082, nombre de host, journald,
#                portal cautivo y primer arranque.
#   --shared     equipo compartido con otros servicios: puertos 8090/8091/8092; no toca el
#                nombre de host, journald ni NetworkManager.
#
# Es idempotente: volver a ejecutarlo repara la instalación sin borrar datos. Ver
# docs/instalacion.md.
set -Eeuo pipefail
umask 022

# Clave pública Ed25519 de los releases (28.3). Debe coincidir con RELEASE_PUBLIC_KEY_PEM de
# privd/commands/update.py; para rotarla ver SECURITY.md.
readonly MESHBOX_RELEASE_PUBKEY='-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAFcM6F5vQWKziqfj+rf1S0ePm+z6zD5VNb8Pd3fDD9VE=
-----END PUBLIC KEY-----'

# Base de descarga de releases (<base>/v<versión>/...); se puede cambiar con --updates-url.
readonly DEFAULT_UPDATES_URL="https://github.com/marcomagnaiot/meshbox/releases/download"

readonly OPT_DIR=/opt/meshbox
readonly STAGING_ROOT=$OPT_DIR/.staging
readonly PRIVD_DIR=/usr/local/lib/meshbox-privd
readonly PRIVD_CONF_DIR=/etc/meshbox-privd
readonly PRIVD_CONF=$PRIVD_CONF_DIR/privd.toml
readonly PRIVD_STATE=/var/lib/meshbox-privd
readonly ETC_DIR=/etc/meshbox
readonly CONFIG=$ETC_DIR/config.toml
readonly SECRETS=$ETC_DIR/secrets.toml
readonly TUNNEL_DIR=/etc/meshbox-tunnel
readonly VAR_DIR=/var/lib/meshbox
readonly SYSTEMD_DIR=/etc/systemd/system
readonly MOSQ_DIR=/etc/mosquitto
readonly FIRSTBOOT_BIN=/usr/local/sbin/meshbox-firstboot
readonly JOURNALD_CONF=/etc/systemd/journald.conf.d/meshbox.conf
readonly NM_CAPTIVE_CONF=/etc/NetworkManager/dnsmasq-shared.d/meshbox-captive.conf
readonly SOCKET_PATH=/run/meshbox/privd.sock
readonly UV_VERSION=0.13.3
readonly MIN_FREE_KB=$((2 * 1024 * 1024))
readonly MIN_RAM_KB=$((350 * 1024))
readonly CORE_UNITS=(meshbox.service meshbox-privd.socket meshbox-privd.service
    meshbox-cloudflared.service meshbox-backup.service meshbox-backup.timer)

MODE=""
FROM=""
VERSION_ARG=""
INSECURE=0
IMAGE=0
NO_CLOUDFLARED=0
SITE_SLUG=""
MQTT_ROOT=""
HOSTNAME_ARG=""
UPDATES_URL=""
CHANGE_MODE=0

VERSION=""
PKG_DIR=""
TARBALL=""
STAGE=""
PYTHON=""
LAN_PORT=""
PUBLIC_PORT=""
ADMIN_PORT=""
MOSQ_CHANGED=0
SETUP_CODE=""

if [[ -t 1 ]]; then
    RED=$'\033[1;31m' YELLOW=$'\033[1;33m' GREEN=$'\033[1;32m' BOLD=$'\033[1m' RESET=$'\033[0m'
else
    RED="" YELLOW="" GREEN="" BOLD="" RESET=""
fi

info() { printf '%s==>%s %s\n' "$BOLD" "$RESET" "$*"; }
warn() { printf '%sAviso:%s %s\n' "$YELLOW" "$RESET" "$*" >&2; }
die() {
    printf '%sError:%s %s\n' "$RED" "$RESET" "$*" >&2
    exit 1
}
on_error() { printf '%sError:%s falló "%s" (línea %s).\n' "$RED" "$RESET" "$2" "$1" >&2; }
trap 'on_error "$LINENO" "$BASH_COMMAND"' ERR

usage() {
    cat <<'EOF'
Uso: sudo ./install.sh [opciones]

  --appliance               Equipo dedicado (por defecto en instalaciones nuevas).
  --shared                  Equipo compartido: puertos 8090/8091/8092, sin tocar nombre de
                            host, journald ni NetworkManager (ADR 0004).
  --from RUTA               Paquete meshbox-X.Y.Z-linux-aarch64.tar.gz (con SHA256SUMS y
                            SHA256SUMS.sig al lado) o carpeta ya descomprimida.
  --version X.Y.Z           Descarga esa versión desde --updates-url.
  --updates-url URL         Base de descarga de releases (<base>/vX.Y.Z/...).
  --site-slug SLUG          Identificador del sitio (por ejemplo mizona).
  --mqtt-root RAIZ          Raíz de tópicos (por defecto msh/AR/<slug>).
  --hostname NOMBRE         Nombre de host (solo appliance; por defecto meshbox).
  --no-cloudflared          No instala cloudflared ni su repositorio.
  --image                   Dentro del chroot de pi-gen: no verifica RAM ni puertos, no
                            arranca servicios; deja pendiente meshbox-firstboot.
  --insecure-skip-signature Solo desarrollo: no verifica la firma del paquete.
  --change-mode             Permite cambiar el modo de una instalación existente.
  -h, --help                Muestra esta ayuda.
EOF
}

parse_args() {
    while (($#)); do
        case $1 in
        --appliance | --shared)
            [[ -z $MODE || $MODE == "${1#--}" ]] || die "--appliance y --shared son excluyentes."
            MODE=${1#--}
            ;;
        --from)
            [[ $# -ge 2 ]] || die "--from necesita una ruta."
            FROM=$2
            shift
            ;;
        --version)
            [[ $# -ge 2 ]] || die "--version necesita X.Y.Z."
            VERSION_ARG=$2
            shift
            ;;
        --updates-url)
            [[ $# -ge 2 ]] || die "--updates-url necesita una URL."
            UPDATES_URL=$2
            shift
            ;;
        --site-slug)
            [[ $# -ge 2 ]] || die "--site-slug necesita un valor."
            SITE_SLUG=$2
            shift
            ;;
        --mqtt-root)
            [[ $# -ge 2 ]] || die "--mqtt-root necesita un valor."
            MQTT_ROOT=$2
            shift
            ;;
        --hostname)
            [[ $# -ge 2 ]] || die "--hostname necesita un nombre."
            HOSTNAME_ARG=$2
            shift
            ;;
        --no-cloudflared) NO_CLOUDFLARED=1 ;;
        --image) IMAGE=1 ;;
        --insecure-skip-signature) INSECURE=1 ;;
        --change-mode) CHANGE_MODE=1 ;;
        -h | --help)
            usage
            exit 0
            ;;
        *) die "Opción desconocida: $1 (ver --help)." ;;
        esac
        shift
    done
    if [[ -n $VERSION_ARG && ! $VERSION_ARG =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        die "--version debe tener la forma X.Y.Z."
    fi
    if [[ -n $UPDATES_URL && ! $UPDATES_URL =~ ^(https?|file)://[^\"\\[:space:]]+$ ]]; then
        die "--updates-url no es una URL válida."
    fi
    if [[ -n $SITE_SLUG && ! $SITE_SLUG =~ ^[a-z0-9][a-z0-9-]{0,31}$ ]]; then
        die "--site-slug admite minúsculas, números y guiones (hasta 32)."
    fi
    if [[ -n $MQTT_ROOT ]]; then
        if [[ ! $MQTT_ROOT =~ ^[A-Za-z0-9_/-]{1,64}$ || $MQTT_ROOT == /* || $MQTT_ROOT == */ ||
            $MQTT_ROOT == *//* ]]; then
            die "--mqtt-root no es válido (por ejemplo msh/AR/mizona)."
        fi
    elif [[ -n $SITE_SLUG ]]; then
        MQTT_ROOT=msh/AR/$SITE_SLUG
    fi
    if [[ -n $HOSTNAME_ARG && ! $HOSTNAME_ARG =~ ^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$ ]]; then
        die "--hostname no es un nombre válido (RFC 1123)."
    fi
}

# ---------------------------------------------------------------------------
# Verificaciones previas
# ---------------------------------------------------------------------------

check_platform() {
    [[ $(id -u) -eq 0 ]] || die "Ejecútalo como root (sudo ./install.sh ...)."
    local arch
    arch=$(uname -m)
    if [[ $arch != aarch64 && ${MESHBOX_INSTALL_ANY_ARCH:-0} != 1 ]]; then
        die "meshbox necesita Raspberry Pi OS de 64 bits (aarch64); este sistema es $arch."
    fi
    [[ -r /etc/os-release ]] || die "No se encontró /etc/os-release."
    local os_id os_like os_version
    os_id=$(sed -n 's/^ID=//p' /etc/os-release | tr -d '"')
    os_like=$(sed -n 's/^ID_LIKE=//p' /etc/os-release | tr -d '"')
    os_version=$(sed -n 's/^VERSION_ID=//p' /etc/os-release | tr -d '"')
    if [[ $os_id != debian && $os_like != *debian* ]]; then
        die "Sistema no soportado ($os_id): se necesita Raspberry Pi OS o Debian."
    fi
    if [[ $os_id == debian && $os_version =~ ^[0-9]+ && ${os_version%%.*} -lt 12 ]]; then
        die "Debian $os_version es muy viejo: se necesita 12 (bookworm) o posterior."
    fi
    command -v systemctl >/dev/null || die "Se necesita systemd."
    if ((!IMAGE)); then
        local ram_kb
        ram_kb=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
        if ((ram_kb < MIN_RAM_KB)); then
            die "Hay $((ram_kb / 1024)) MiB de RAM; meshbox necesita al menos $((MIN_RAM_KB / 1024))."
        fi
    fi
}

check_space() {
    local required=$MIN_FREE_KB free_kb target=/
    [[ -d $OPT_DIR ]] && target=$OPT_DIR
    if [[ -f $OPT_DIR/releases/$VERSION/.meshbox-installed ]]; then
        required=$((512 * 1024)) # reinstalación de la misma versión
    fi
    free_kb=$(df -Pk "$target" | awk 'NR == 2 {print $4}')
    if ((free_kb < required)); then
        die "Hay $((free_kb / 1024)) MiB libres en $target; se necesitan $((required / 1024)) MiB."
    fi
}

existing_mode() {
    [[ -f $PRIVD_CONF ]] || return 0
    sed -n 's/^[[:space:]]*mode[[:space:]]*=[[:space:]]*"\(shared\|appliance\)".*/\1/p' \
        "$PRIVD_CONF" | head -n 1
}

resolve_mode() {
    local previous
    previous=$(existing_mode)
    if [[ -z $MODE ]]; then
        MODE=${previous:-appliance}
    elif [[ -n $previous && $previous != "$MODE" && $CHANGE_MODE -ne 1 ]]; then
        die "Este equipo está instalado en modo $previous. Para pasarlo a $MODE agrega --change-mode (y revisa los puertos de $CONFIG)."
    fi
    if [[ $MODE == shared && -n $HOSTNAME_ARG ]]; then
        die "--hostname no se usa en modo shared: el nombre de host del equipo no se toca."
    fi
}

# Puerto de una dirección de config.toml ([server] <clave> = "host:puerto"), o el valor por
# defecto si no existe el archivo o la clave.
config_port() {
    local key=$1 default=$2
    if [[ ! -r $CONFIG ]]; then
        echo "$default"
        return
    fi
    python3 - "$CONFIG" "$key" "$default" <<'PY'
import sys
import tomllib

path, key, default = sys.argv[1:4]
try:
    with open(path, "rb") as fh:
        value = str(tomllib.load(fh).get("server", {}).get(key, ""))
except Exception:
    value = ""
port = value.rsplit(":", 1)[-1] if ":" in value else ""
print(port if port.isdigit() else default)
PY
}

resolve_ports() {
    if [[ $MODE == shared ]]; then
        LAN_PORT=$(config_port lan_bind 8090)
        PUBLIC_PORT=$(config_port public_bind 8091)
        ADMIN_PORT=$(config_port admin_remote_bind 8092)
    else
        LAN_PORT=$(config_port lan_bind 80)
        PUBLIC_PORT=$(config_port public_bind 8081)
        ADMIN_PORT=$(config_port admin_remote_bind 8082)
    fi
}

# Detiene la instalación si un puerto está ocupado por un programa ajeno a meshbox.
check_port() {
    local port=$1 what=$2 allowed=$3 line pid owner comm
    line=$(ss -Htlnp "sport = :$port" 2>/dev/null | head -n 1 || true)
    [[ -n $line ]] || return 0
    pid=$(grep -o 'pid=[0-9]*' <<<"$line" | head -n 1 | cut -d= -f2 || true)
    owner="" comm=""
    if [[ -n $pid && -r /proc/$pid/status ]]; then
        # UID efectivo de /proc/<pid>/status: un proceso que bajó privilegios con setuid (como
        # Mosquitto) queda "no volcable" y /proc/<pid> figura como de root.
        local euid
        euid=$(awk '/^Uid:/ {print $3}' "/proc/$pid/status" 2>/dev/null || true)
        [[ -n $euid ]] && owner=$(getent passwd "$euid" | cut -d: -f1 || true)
        comm=$(cat "/proc/$pid/comm" 2>/dev/null || true)
    fi
    if [[ -n $owner && $owner == "$allowed" ]]; then
        return 0
    fi
    die "El puerto $port ($what) está ocupado por ${comm:-otro programa} (pid ${pid:-?}, usuario ${owner:-?}). meshbox no se instala para no interferir: libéralo o usa el otro modo (--shared usa 8090-8092)."
}

check_ports() {
    ((IMAGE)) && return 0
    command -v ss >/dev/null || return 0
    check_port "$LAN_PORT" "servidor LAN" meshbox
    check_port "$PUBLIC_PORT" "servidor público" meshbox
    check_port "$ADMIN_PORT" "administración remota" meshbox
    check_port 1883 "MQTT" mosquitto
}

# Mosquitto con configuración propia que choque con la de meshbox (listener 1883, usuarios).
check_mosquitto_config() {
    [[ -d $MOSQ_DIR ]] || return 0
    local file conflicts=()
    for file in "$MOSQ_DIR"/conf.d/*.conf; do
        [[ -e $file && $(basename "$file") != meshbox.conf ]] || continue
        conflicts+=("$file")
    done
    if [[ -f $MOSQ_DIR/mosquitto.conf ]] &&
        grep -Eq '^[[:space:]]*(listener|port|password_file|acl_file|allow_anonymous)[[:space:]]' \
            "$MOSQ_DIR/mosquitto.conf"; then
        conflicts+=("$MOSQ_DIR/mosquitto.conf")
    fi
    if ((${#conflicts[@]})); then
        die "Mosquitto ya tiene configuración propia (${conflicts[*]}). meshbox agrega $MOSQ_DIR/conf.d/meshbox.conf con el listener 1883 y usuarios; revisa esos archivos (docs/instalacion.md) y vuelve a ejecutar."
    fi
}

# ---------------------------------------------------------------------------
# Paquete
# ---------------------------------------------------------------------------

prepare_staging() {
    install -d -o root -g root -m 0755 "$OPT_DIR"
    install -d -o root -g root -m 0700 "$STAGING_ROOT"
    STAGE=$(mktemp -d "$STAGING_ROOT/install-XXXXXX")
    # pip y tar escriben temporales grandes: en la SD (área root), nunca en /tmp (RAM).
    export TMPDIR=$STAGE
    trap 'rm -rf -- "$STAGE"' EXIT
}

ensure_tool() {
    local tool=$1 package=$2
    command -v "$tool" >/dev/null && return 0
    info "Instalando $package (necesario para obtener o verificar el paquete)..."
    apt-get update </dev/null
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$package" </dev/null
}

verify_tarball() {
    local tarball=$1 dir name sums sig line
    dir=$(cd "$(dirname "$tarball")" && pwd)
    name=$(basename "$tarball")
    sums=$dir/SHA256SUMS
    sig=$dir/SHA256SUMS.sig
    if ((INSECURE)); then
        printf '%s\n' "${RED}AVISO: --insecure-skip-signature: NO se verifica la firma del paquete. Úsalo solo en desarrollo.${RESET}" >&2
    else
        [[ -f $sums && -f $sig ]] ||
            die "Faltan SHA256SUMS y SHA256SUMS.sig junto a $name (en desarrollo: --insecure-skip-signature)."
        [[ $(stat -c %s "$sig") -eq 64 ]] || die "SHA256SUMS.sig no tiene 64 bytes (firma Ed25519)."
        ensure_tool openssl openssl
        printf '%s\n' "$MESHBOX_RELEASE_PUBKEY" >"$STAGE/release-public.pem"
        if ! openssl pkeyutl -verify -pubin -inkey "$STAGE/release-public.pem" -rawin \
            -in "$sums" -sigfile "$sig" >"$STAGE/verify.out" 2>&1 ||
            ! grep -q 'Signature Verified Successfully' "$STAGE/verify.out"; then
            die "La firma de SHA256SUMS no es válida: el paquete no se instala."
        fi
        info "Firma Ed25519 de SHA256SUMS verificada."
    fi
    if [[ -f $sums ]]; then
        line=$(grep -E "^[0-9a-fA-F]{64} [ *]${name//./\\.}$" "$sums" | head -n 1 || true)
        [[ -n $line ]] || die "$name no figura en SHA256SUMS."
        (cd "$dir" && printf '%s\n' "$line" | sha256sum -c --status -) ||
            die "La suma SHA-256 de $name no coincide."
        info "Suma SHA-256 de $name verificada."
    else
        warn "No hay SHA256SUMS junto a $name: no se verifica la suma."
    fi
}

extract_tarball() {
    local tarball=$1 name version
    name=$(basename "$tarball")
    [[ $name =~ ^meshbox-([0-9]+\.[0-9]+\.[0-9]+)-linux-aarch64\.tar\.gz$ ]] ||
        die "Nombre de paquete inesperado: $name (se espera meshbox-X.Y.Z-linux-aarch64.tar.gz)."
    version=${BASH_REMATCH[1]}
    mkdir -p "$STAGE/extract"
    tar -xzf "$tarball" -C "$STAGE/extract" --no-same-owner
    PKG_DIR=$STAGE/extract/meshbox-$version
    [[ -d $PKG_DIR ]] || die "El paquete no contiene la carpeta meshbox-$version."
}

download_release() {
    local base=${UPDATES_URL:-$DEFAULT_UPDATES_URL} name file
    [[ -n $base ]] || die "Para descargar una versión indica --updates-url (o usa --from)."
    ensure_tool curl curl
    name=meshbox-$VERSION_ARG-linux-aarch64.tar.gz
    mkdir -p "$STAGE/download"
    for file in SHA256SUMS SHA256SUMS.sig "$name"; do
        info "Descargando $file..."
        curl -fL --retry 3 --connect-timeout 20 -o "$STAGE/download/$file" \
            "${base%/}/v$VERSION_ARG/$file" || die "No se pudo descargar $file."
    done
    TARBALL=$STAGE/download/$name
}

acquire_package() {
    local script_dir
    script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
    if [[ -n $FROM ]]; then
        if [[ -f $FROM ]]; then
            TARBALL=$(cd "$(dirname "$FROM")" && pwd)/$(basename "$FROM")
        elif [[ -d $FROM ]]; then
            ((INSECURE)) ||
                die "Una carpeta no se puede verificar: usa el .tar.gz (o --insecure-skip-signature en desarrollo)."
            PKG_DIR=$(cd "$FROM" && pwd)
        else
            die "No existe $FROM."
        fi
    elif [[ -n $VERSION_ARG ]]; then
        download_release
    elif [[ -f $script_dir/VERSION && -d $script_dir/wheels ]]; then
        # install.sh dentro de un paquete descomprimido: se prefiere el .tar.gz de al lado.
        local version candidate
        version=$(tr -d '[:space:]' <"$script_dir/VERSION")
        candidate=$(dirname "$script_dir")/meshbox-$version-linux-aarch64.tar.gz
        if [[ -f $candidate ]]; then
            TARBALL=$candidate
        else
            ((INSECURE)) ||
                die "No se encontró $candidate para verificar la firma (o usa --insecure-skip-signature en desarrollo)."
            PKG_DIR=$script_dir
        fi
    else
        die "Indica el paquete con --from (o --version y --updates-url)."
    fi
    if [[ -n $TARBALL ]]; then
        verify_tarball "$TARBALL"
        extract_tarball "$TARBALL"
    elif ((INSECURE)); then
        printf '%s\n' "${RED}AVISO: --insecure-skip-signature: se instala una carpeta sin verificar.${RESET}" >&2
    fi
    [[ -f $PKG_DIR/VERSION ]] || die "Al paquete le falta VERSION."
    VERSION=$(tr -d '[:space:]' <"$PKG_DIR/VERSION")
    [[ $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "VERSION no válida: $VERSION."
    if [[ -n $VERSION_ARG && $VERSION != "$VERSION_ARG" ]]; then
        die "El paquete es de la versión $VERSION, no de $VERSION_ARG."
    fi
    local required
    for required in wheels privd/meshbox_privd.py deploy/systemd/meshbox.service \
        deploy/mosquitto/meshbox.conf; do
        [[ -e $PKG_DIR/$required ]] || die "Al paquete le falta $required."
    done
    compgen -G "$PKG_DIR/wheels/meshbox-$VERSION-*.whl" >/dev/null ||
        die "Al paquete le falta la rueda de meshbox $VERSION."
    info "Paquete meshbox $VERSION listo."
}

# ---------------------------------------------------------------------------
# Sistema
# ---------------------------------------------------------------------------

install_apt_packages() {
    local packages=(mosquitto mosquitto-clients avahi-daemon sqlite3 openssl curl ca-certificates
        python3-venv iproute2)
    # En modo shared no se instala NetworkManager: la red es de un equipo ajeno (ADR 0004).
    [[ $MODE == appliance ]] && packages+=(network-manager dnsmasq-base)
    info "Instalando paquetes del sistema: ${packages[*]}"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update </dev/null
    apt-get install -y --no-install-recommends "${packages[@]}" </dev/null
}

install_cloudflared() {
    if ((NO_CLOUDFLARED)); then
        info "Se omite cloudflared (--no-cloudflared)."
        return 0
    fi
    info "Repositorio apt de Cloudflare y cloudflared..."
    install -d -m 0755 /usr/share/keyrings
    if curl -fsSL --retry 3 https://pkg.cloudflare.com/cloudflare-main.gpg \
        -o "$STAGE/cloudflare-main.gpg"; then
        install -o root -g root -m 0644 "$STAGE/cloudflare-main.gpg" \
            /usr/share/keyrings/cloudflare-main.gpg
    elif [[ ! -f /usr/share/keyrings/cloudflare-main.gpg ]]; then
        die "No se pudo descargar la clave del repositorio de Cloudflare (o usa --no-cloudflared)."
    fi
    printf '%s\n' 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' \
        >/etc/apt/sources.list.d/cloudflared.list
    if ! dpkg -s cloudflared >/dev/null 2>&1; then
        apt-get update </dev/null
        apt-get install -y --no-install-recommends cloudflared </dev/null
    fi
    if [[ -d /etc/apt/apt.conf.d ]]; then
        cat >/etc/apt/apt.conf.d/52meshbox-cloudflared <<'EOF'
// meshbox: actualizaciones automáticas de cloudflared desde el repositorio de Cloudflare.
Unattended-Upgrade::Origins-Pattern {
        "site=pkg.cloudflare.com";
};
EOF
    fi
}

create_users() {
    if ! getent group meshbox >/dev/null; then
        groupadd --system meshbox
    fi
    if ! id -u meshbox >/dev/null 2>&1; then
        useradd --system --gid meshbox --home-dir "$VAR_DIR" --no-create-home \
            --shell /usr/sbin/nologin --comment "meshbox" meshbox
    fi
    usermod -a -G dialout meshbox
    if ! getent group cloudflared >/dev/null; then
        groupadd --system cloudflared
    fi
    if ! id -u cloudflared >/dev/null 2>&1; then
        useradd --system --gid cloudflared --home-dir /nonexistent --no-create-home \
            --shell /usr/sbin/nologin --comment "cloudflared (meshbox)" cloudflared
    fi
}

# Crea o repara un directorio: dueño, grupo y permisos.
ensure_dir() {
    local mode=$1 owner=$2 dir
    shift 2
    for dir in "$@"; do
        [[ -L $dir ]] && die "$dir es un enlace simbólico: revísalo a mano."
        mkdir -p "$dir"
        chown "$owner" "$dir"
        chmod "$mode" "$dir"
    done
}

create_directories() {
    ensure_dir 0755 root:root "$OPT_DIR" "$OPT_DIR/releases" "$OPT_DIR/bin"
    ensure_dir 0700 root:root "$STAGING_ROOT" "$TUNNEL_DIR" "$PRIVD_STATE"
    ensure_dir 0755 root:root "$PRIVD_CONF_DIR" "$PRIVD_DIR" "$PRIVD_DIR/commands"
    ensure_dir 0750 meshbox:meshbox "$ETC_DIR" "$VAR_DIR" "$VAR_DIR/tiles" "$VAR_DIR/plugins" \
        "$VAR_DIR/rec"
    ensure_dir 0700 meshbox:meshbox "$VAR_DIR/backups" "$VAR_DIR/tmp"
    # Reparación: todo lo de /var/lib/meshbox es de meshbox; config y secretos con sus permisos.
    chown -R -P meshbox:meshbox "$VAR_DIR"
    if [[ -f $CONFIG ]]; then
        chown meshbox:meshbox "$CONFIG"
        chmod 0640 "$CONFIG"
    fi
    if [[ -f $SECRETS ]]; then
        chown meshbox:meshbox "$SECRETS"
        chmod 0600 "$SECRETS"
    fi
    if [[ -f $TUNNEL_DIR/cloudflared.env ]]; then
        chown root:root "$TUNNEL_DIR/cloudflared.env"
        chmod 0600 "$TUNNEL_DIR/cloudflared.env"
    fi
}

# Python 3.13: el del sistema si corresponde (ADR 0005); si no, CPython de uv.
select_python() {
    if /usr/bin/python3 -c 'import sys; raise SystemExit(sys.version_info[:2] != (3, 13))' \
        2>/dev/null; then
        PYTHON=/usr/bin/python3
        /usr/bin/python3 -c 'import ensurepip, venv' 2>/dev/null ||
            die "Falta python3-venv (ensurepip) para crear el entorno."
        info "Python del sistema: $(/usr/bin/python3 --version 2>&1)."
        return 0
    fi
    info "El Python del sistema no es 3.13: se instala CPython 3.13 con uv en $OPT_DIR/python."
    local name=uv-aarch64-unknown-linux-gnu
    local url=https://github.com/astral-sh/uv/releases/download/$UV_VERSION/$name.tar.gz
    if [[ ! -x $OPT_DIR/bin/uv ]] || ! "$OPT_DIR/bin/uv" --version | grep -q " $UV_VERSION"; then
        curl -fL --retry 3 -o "$STAGE/$name.tar.gz" "$url" || die "No se pudo descargar uv."
        curl -fL --retry 3 -o "$STAGE/$name.tar.gz.sha256" "$url.sha256" ||
            die "No se pudo descargar la suma de uv."
        (cd "$STAGE" && sha256sum -c --status "$name.tar.gz.sha256") ||
            die "La suma de uv no coincide."
        tar -xzf "$STAGE/$name.tar.gz" -C "$STAGE"
        install -o root -g root -m 0755 "$STAGE/$name/uv" "$OPT_DIR/bin/uv"
    fi
    ensure_dir 0755 root:root "$OPT_DIR/python"
    UV_PYTHON_INSTALL_DIR=$OPT_DIR/python UV_NO_CONFIG=1 "$OPT_DIR/bin/uv" python install 3.13
    local found
    found=$(UV_PYTHON_INSTALL_DIR=$OPT_DIR/python UV_NO_CONFIG=1 \
        "$OPT_DIR/bin/uv" python find --managed-python 3.13)
    [[ -x $found ]] || die "No se encontró el CPython 3.13 instalado por uv."
    ln -sfn "$(dirname "$(dirname "$found")")" "$OPT_DIR/python/current"
    PYTHON=$OPT_DIR/python/current/bin/python3.13
    [[ -x $PYTHON ]] || PYTHON=$found
}

package_digest() {
    (cd "$PKG_DIR" && find wheels -type f -name '*.whl' -print0 | sort -z |
        xargs -0 sha256sum | sha256sum | cut -d ' ' -f 1)
}

# releases/<v>: copia del paquete, entorno propio y enlace `current` (atómico).
install_release() {
    local dest=$OPT_DIR/releases/$VERSION digest marker_ok=0 backup=""
    digest=$(package_digest)
    if [[ -f $dest/.meshbox-installed && -x $dest/.venv/bin/python ]] &&
        grep -qxF "$VERSION $digest" "$dest/.meshbox-installed" &&
        (cd / && "$dest/.venv/bin/python" -c 'import meshbox' 2>/dev/null); then
        marker_ok=1
    fi
    if ((marker_ok)); then
        info "meshbox $VERSION ya está instalado con las mismas ruedas: se conserva el entorno."
    else
        info "Instalando meshbox $VERSION en $dest..."
        if [[ -e $dest ]]; then
            backup=$OPT_DIR/releases/.$VERSION.anterior.$$
            mv -T "$dest" "$backup"
        fi
        if ! install_release_files "$dest"; then
            rm -rf -- "$dest"
            [[ -n $backup ]] && mv -T "$backup" "$dest"
            die "No se pudo crear el entorno de meshbox $VERSION."
        fi
        [[ -n $backup ]] && rm -rf -- "$backup"
        printf '%s %s\n' "$VERSION" "$digest" >"$dest/.meshbox-installed"
        chmod 0644 "$dest/.meshbox-installed"
    fi
    ln -sfn "releases/$VERSION" "$OPT_DIR/.current.tmp.$$"
    mv -Tf "$OPT_DIR/.current.tmp.$$" "$OPT_DIR/current"
    prune_releases "$VERSION"
}

# Se llama dentro de un `if` (ahí `set -e` no actúa): cada paso corta con `|| return 1`.
install_release_files() {
    local dest=$1
    mkdir -p "$dest" || return 1
    cp -a "$PKG_DIR/." "$dest/" || return 1
    chown -R root:root "$dest" || return 1
    chmod -R u+rwX,go+rX,go-w "$dest" || return 1
    "$PYTHON" -m venv "$dest/.venv" || return 1
    "$dest/.venv/bin/python" -m pip install --no-index --find-links "$dest/wheels" \
        --no-input --disable-pip-version-check --no-cache-dir "meshbox==$VERSION" || return 1
    (cd / && "$dest/.venv/bin/python" -c 'import meshbox')
}

# Conserva la versión actual, las 2 anteriores más recientes y las posteriores.
prune_releases() {
    local current=$1 version lower=() keep=()
    while IFS= read -r version; do
        [[ $version == "$current" ]] && continue
        if [[ $(printf '%s\n%s\n' "$version" "$current" | sort -V | head -n 1) == "$version" ]]; then
            lower+=("$version")
        else
            keep+=("$version")
        fi
    done < <(find "$OPT_DIR/releases" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' |
        grep -E '^[0-9]+\.[0-9]+\.[0-9]+$' | sort -V)
    local count=${#lower[@]} i
    for ((i = 0; i < count; i++)); do
        if ((i < count - 2)); then
            info "Se borra la versión vieja ${lower[i]}."
            rm -rf -- "${OPT_DIR:?}/releases/${lower[i]}"
        fi
    done
}

install_privd() {
    install -o root -g root -m 0644 "$PKG_DIR/privd/meshbox_privd.py" "$PRIVD_DIR/meshbox_privd.py"
    local file name
    for file in "$PKG_DIR"/privd/commands/*.py; do
        install -o root -g root -m 0644 "$file" "$PRIVD_DIR/commands/"
    done
    for file in "$PRIVD_DIR"/commands/*.py; do
        name=$(basename "$file")
        [[ -e $PKG_DIR/privd/commands/$name ]] || rm -f -- "$file"
    done
    rm -rf -- "$PRIVD_DIR/__pycache__" "$PRIVD_DIR/commands/__pycache__"
}

existing_updates_url() {
    [[ -f $PRIVD_CONF ]] || return 0
    sed -n 's/^[[:space:]]*updates_base_url[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' \
        "$PRIVD_CONF" | head -n 1
}

write_privd_config() {
    local updates=${UPDATES_URL:-}
    [[ -n $updates ]] || updates=$(existing_updates_url)
    [[ -n $updates ]] || updates=$DEFAULT_UPDATES_URL
    cat >"$STAGE/privd.toml" <<EOF
# Generado por install.sh (meshbox $VERSION). Referencia: deploy/meshbox-privd.example.toml.
mode = "$MODE"
health_url = "http://127.0.0.1:$PUBLIC_PORT/api/v1/health"
updates_base_url = "$updates"
opt_dir = "$OPT_DIR"
python = "$PYTHON"
idle_timeout_s = 600
EOF
    install -o root -g root -m 0644 "$STAGE/privd.toml" "$PRIVD_CONF"
}

# Instala un archivo si cambió. Devuelve 0 si hubo cambio.
install_if_changed() {
    local mode=$1 src=$2 dst=$3
    if [[ -f $dst ]] && cmp -s "$src" "$dst"; then
        chmod "$mode" "$dst"
        chown root:root "$dst"
        return 1
    fi
    install -D -o root -g root -m "$mode" "$src" "$dst"
}

# Líneas efectivas (sin comentarios ni vacías) de una configuración.
effective_lines() { grep -Ev '^[[:space:]]*(#|$)' "$1" 2>/dev/null || true; }

install_system_files() {
    local unit
    for unit in "${CORE_UNITS[@]}"; do
        install -o root -g root -m 0644 "$PKG_DIR/deploy/systemd/$unit" "$SYSTEMD_DIR/$unit"
    done
    if [[ $MODE == appliance ]]; then
        install -o root -g root -m 0644 "$PKG_DIR/deploy/systemd/meshbox-firstboot.service" \
            "$SYSTEMD_DIR/meshbox-firstboot.service"
        install -o root -g root -m 0755 "$PKG_DIR/deploy/firstboot/meshbox-firstboot.sh" \
            "$FIRSTBOOT_BIN"
        if install_if_changed 0644 "$PKG_DIR/deploy/journald/meshbox.conf" "$JOURNALD_CONF" &&
            ((!IMAGE)); then
            systemctl restart systemd-journald || warn "No se pudo reiniciar journald."
        fi
        install_if_changed 0644 "$PKG_DIR/deploy/nm/dnsmasq-shared.d/meshbox-captive.conf" \
            "$NM_CAPTIVE_CONF" || true
    else
        # Restos de una instalación anterior en modo appliance (archivos propios de meshbox).
        if [[ -f $SYSTEMD_DIR/meshbox-firstboot.service ]]; then
            systemctl disable meshbox-firstboot.service 2>/dev/null || true
            rm -f -- "$SYSTEMD_DIR/meshbox-firstboot.service" "$FIRSTBOOT_BIN"
        fi
        rm -f -- "$JOURNALD_CONF" "$NM_CAPTIVE_CONF"
    fi
    local conf=$MOSQ_DIR/conf.d/meshbox.conf
    if [[ "$(effective_lines "$PKG_DIR/deploy/mosquitto/meshbox.conf")" != "$(effective_lines "$conf")" ]]; then
        MOSQ_CHANGED=1
    fi
    install -D -o root -g root -m 0644 "$PKG_DIR/deploy/mosquitto/meshbox.conf" "$conf"
    ((IMAGE)) || systemctl daemon-reload
}

# passwd y acl deben existir antes de arrancar Mosquitto. Los existentes se conservan (por
# ejemplo, cuentas creadas a mano): solo se corrigen dueño y permisos.
prepare_mosquitto_files() {
    local file
    for file in passwd acl; do
        if [[ ! -e $MOSQ_DIR/$file ]]; then
            if [[ $file == acl ]]; then
                # Sin reglas: nadie tiene permisos hasta que el bootstrap escriba la ACL.
                printf '# meshbox: la ACL la genera meshbox-privd (mosquitto.acl.write).\n' \
                    >"$MOSQ_DIR/$file"
            else
                : >"$MOSQ_DIR/$file" # mosquitto_passwd no admite comentarios en este archivo
            fi
            MOSQ_CHANGED=1
        fi
        chown mosquitto:mosquitto "$MOSQ_DIR/$file"
        chmod 0640 "$MOSQ_DIR/$file"
    done
}

install_pmtiles() {
    if [[ -f $PKG_DIR/bin/pmtiles ]]; then
        install -o root -g root -m 0755 "$PKG_DIR/bin/pmtiles" "$OPT_DIR/bin/pmtiles"
    else
        warn "El paquete no trae bin/pmtiles: la descarga del mapa base no va a funcionar."
    fi
}

privd_call() {
    printf '%s' "$1" | /usr/bin/python3 -I "$PRIVD_DIR/meshbox_privd.py" call
}

set_hostname() {
    [[ $MODE == appliance ]] || return 0
    local current wanted
    current=$(hostname)
    wanted=$HOSTNAME_ARG
    if [[ -z $wanted && ($current == raspberrypi || $current == localhost || -z $current) ]]; then
        wanted=meshbox
    fi
    [[ -n $wanted && $wanted != "$current" ]] || return 0
    info "Nombre de host: $wanted"
    privd_call "{\"cmd\":\"system.hostname\",\"args\":{\"name\":\"$wanted\"}}" >/dev/null ||
        warn "No se pudo cambiar el nombre de host."
}

wait_for_socket() {
    local i
    for ((i = 0; i < 50; i++)); do
        [[ -S $SOCKET_PATH ]] && return 0
        sleep 0.2
    done
    die "No apareció el socket de privd ($SOCKET_PATH)."
}

start_services() {
    info "Habilitando y arrancando servicios..."
    systemctl enable --now meshbox-privd.socket
    # Si privd quedó corriendo con el código anterior, que lo recargue.
    systemctl try-restart meshbox-privd.service || true
    wait_for_socket
    systemctl enable mosquitto.service
    if ((MOSQ_CHANGED)) || ! systemctl is-active --quiet mosquitto.service; then
        systemctl restart mosquitto.service ||
            die "Mosquitto no arrancó. Revisa: journalctl -u mosquitto -n 50"
    fi
    if [[ $MODE == appliance ]]; then
        systemctl enable --now avahi-daemon.service || warn "No se pudo activar avahi-daemon."
    fi
}

run_bootstrap() {
    local args=(--config "$CONFIG" --mode "$MODE" --json) out
    [[ -n $SITE_SLUG ]] && args+=(--site-slug "$SITE_SLUG")
    [[ -n $MQTT_ROOT ]] && args+=(--mqtt-root "$MQTT_ROOT")
    info "Configuración inicial (secretos, cuenta meshbox-ingest y ACL de Mosquitto)..."
    out=$(cd / && runuser -u meshbox -- env HOME="$VAR_DIR" TMPDIR="$VAR_DIR/tmp" \
        "$OPT_DIR/current/.venv/bin/python" -m meshbox bootstrap "${args[@]}") ||
        die "Falló meshbox bootstrap. Revisa el mensaje anterior."
    SETUP_CODE=$(printf '%s\n' "$out" | tail -n 1 | python3 -c '
import json, sys
try:
    data = json.loads(sys.stdin.read())
except ValueError:
    data = {}
code = data.get("setup_code") if isinstance(data, dict) else None
print(code or "")
')
}

start_meshbox() {
    systemctl enable meshbox.service meshbox-backup.timer
    systemctl restart meshbox.service ||
        die "meshbox no arrancó. Revisa: journalctl -u meshbox -n 100"
    systemctl start meshbox-backup.timer
}

wait_health() {
    local url=http://127.0.0.1:$PUBLIC_PORT/api/v1/health body end=$((SECONDS + 90))
    info "Esperando que meshbox responda en $url (hasta 90 s)..."
    while ((SECONDS < end)); do
        if body=$(curl -fsS --max-time 3 "$url" 2>/dev/null) &&
            python3 -c '
import json, sys
data = json.loads(sys.argv[1])
raise SystemExit(0 if data.get("status") == "ok" and data.get("version") == sys.argv[2] else 1)
' "$body" "$VERSION" 2>/dev/null; then
            return 0
        fi
        sleep 3
    done
    die "meshbox no respondió en $url en 90 s. Revisa: journalctl -u meshbox -n 100"
}

show_summary() {
    local ip host suffix=""
    ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    host=$(hostname)
    [[ $LAN_PORT != 80 ]] && suffix=":$LAN_PORT"
    printf '\n%smeshbox %s instalado (modo %s).%s\n' "$GREEN" "$VERSION" "$MODE" "$RESET"
    printf '  Panel y asistente: http://%s%s  (o http://%s.local%s)\n' "${ip:-<ip>}" "$suffix" \
        "$host" "$suffix"
    if [[ -n $SETUP_CODE ]]; then
        printf '  Código de configuración: %s%s%s (se pide hasta crear el primer usuario)\n' \
            "$BOLD" "$SETUP_CODE" "$RESET"
    fi
    printf '  Registros: journalctl -u meshbox -f\n'
}

enable_for_image() {
    info "Modo imagen: se habilitan las unidades sin arrancarlas."
    systemctl enable meshbox-privd.socket mosquitto.service meshbox.service \
        meshbox-backup.timer meshbox-firstboot.service avahi-daemon.service
}

main() {
    parse_args "$@"
    # No interactivo: nadie lee la entrada estándar (por ejemplo, si `sudo -S` no consumió la
    # clave que manda deploy-dev.ps1 porque el usuario tiene NOPASSWD).
    exec </dev/null
    check_platform
    resolve_mode
    resolve_ports
    prepare_staging
    check_ports
    check_mosquitto_config
    acquire_package
    check_space
    install_apt_packages
    install_cloudflared
    create_users
    create_directories
    select_python
    install_release
    install_privd
    write_privd_config
    install_system_files
    prepare_mosquitto_files
    install_pmtiles
    if ((IMAGE)); then
        [[ $MODE == appliance ]] || die "--image solo tiene sentido en modo appliance."
        enable_for_image
        info "Listo: meshbox-firstboot completará la configuración en el primer arranque."
        return 0
    fi
    start_services
    set_hostname
    run_bootstrap
    # Los puertos reales salen de config.toml (lo crea el bootstrap si faltaba).
    resolve_ports
    write_privd_config
    start_meshbox
    wait_health
    show_summary
}

# Ejecutado (no incluido con `source`, como hacen las pruebas de deploy/tests).
if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
    main "$@"
fi
