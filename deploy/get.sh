#!/usr/bin/env bash
# Instalación de meshbox en una línea, para Raspberry Pi OS Lite de 64 bits:
#
#   curl -fsSL https://raw.githubusercontent.com/marcomagnaiot/meshbox/main/deploy/get.sh | sudo bash
#   curl -fsSL https://raw.githubusercontent.com/marcomagnaiot/meshbox/main/deploy/get.sh | sudo bash -s -- --shared
#
# Desde un clon del repositorio: sudo ./deploy/get.sh [opciones de install.sh]
#
# Averigua la última versión publicada en GitHub (o MESHBOX_VERSION), baja el install.sh de esa
# versión y lo ejecuta con --version: el instalador baja el paquete y verifica la firma Ed25519
# de SHA256SUMS antes de instalar nada. Las opciones pasan tal cual a install.sh.
set -Eeuo pipefail

readonly REPO="marcomagnaiot/meshbox"
readonly RELEASES="https://github.com/$REPO/releases"

die() {
    printf 'meshbox: %s\n' "$*" >&2
    exit 1
}

# Todo dentro de main: con `curl | bash`, bash lee el script entero antes de ejecutar algo.
main() {
    [[ $EUID -eq 0 ]] || die "hay que ejecutarlo con sudo."
    [[ $(uname -m) == aarch64 ]] ||
        die "meshbox necesita Raspberry Pi OS de 64 bits (aarch64); este equipo es $(uname -m)."
    command -v curl >/dev/null || die "falta curl: sudo apt install curl"

    local version=${MESHBOX_VERSION:-} url tmp
    if [[ -z $version ]]; then
        url=$(curl -fsSLI -o /dev/null -w '%{url_effective}' "$RELEASES/latest") ||
            die "no se pudo consultar la última versión en $RELEASES."
        version=${url##*/v}
    fi
    [[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] ||
        die "no hay una versión publicada en $RELEASES (o MESHBOX_VERSION no es X.Y.Z)."

    tmp=$(mktemp -d)
    trap 'rm -rf "$tmp"' EXIT
    printf 'meshbox: instalando la versión %s\n' "$version"
    curl -fsSL --retry 3 -o "$tmp/install.sh" \
        "https://raw.githubusercontent.com/$REPO/v$version/deploy/install.sh" ||
        die "no se pudo bajar el instalador de la versión $version."
    # Sin entrada estándar: con `curl | bash` es el propio script, no una terminal.
    bash "$tmp/install.sh" --version "$version" --updates-url "$RELEASES/download" "$@" </dev/null
}

main "$@"
