#!/usr/bin/env bash
# Primer arranque de la imagen de SD de meshbox (24.2). Solo modo appliance.
#
# Lo ejecuta meshbox-firstboot.service una sola vez (ConditionPathExists de
# /var/lib/meshbox/.firstboot-done). Pasos:
#   1. secretos, config.toml, cuenta meshbox-ingest y ACL (meshbox bootstrap, como meshbox);
#      el código de configuración queda en /boot/firmware/meshbox-codigo.txt;
#   2. nombre de host meshbox si no se definió otro (por ejemplo, con Raspberry Pi Imager);
#   3. la base la crea meshbox.service (migraciones), que arranca después;
#   4. espera red 90 s y, si no hay, levanta el punto de acceso meshbox-XXXX;
#   5. marca .firstboot-done.
# Si algo falla no se marca, y se reintenta en el próximo arranque.
set -Eeuo pipefail
umask 022

readonly PRIVD=/usr/local/lib/meshbox-privd/meshbox_privd.py
readonly SOCKET_PATH=/run/meshbox/privd.sock
readonly CONFIG=/etc/meshbox/config.toml
readonly VAR_DIR=/var/lib/meshbox
readonly DONE=$VAR_DIR/.firstboot-done
readonly BOOT_DIR=/boot/firmware
readonly CODE_FILE=$BOOT_DIR/meshbox-codigo.txt
readonly APP_PYTHON=/opt/meshbox/current/.venv/bin/python
readonly NETWORK_WAIT_S=90

log() { printf 'meshbox-firstboot: %s\n' "$*"; }

privd_call() {
    printf '%s' "$1" | /usr/bin/python3 -I "$PRIVD" call
}

wait_for_socket() {
    local i
    for ((i = 0; i < 300; i++)); do
        [[ -S $SOCKET_PATH ]] && return 0
        sleep 0.2
    done
    log "no apareció el socket de privd ($SOCKET_PATH)"
    return 1
}

write_setup_code() {
    local code=$1
    [[ -n $code ]] || return 0
    if [[ ! -d $BOOT_DIR ]]; then
        log "no existe $BOOT_DIR: el código de configuración es $code"
        return 0
    fi
    # Texto con CRLF para que se lea bien al abrir la tarjeta en Windows.
    {
        printf 'Código de configuración de meshbox: %s\r\n' "$code"
        printf '\r\n'
        printf 'Lo pide el asistente (http://meshbox.local/setup) hasta crear el primer usuario.\r\n'
        printf 'En el punto de acceso de configuración no se pide. Borra este archivo al terminar.\r\n'
    } >"$CODE_FILE"
    chmod 0600 "$CODE_FILE" 2>/dev/null || true
    log "código de configuración escrito en $CODE_FILE"
}

bootstrap() {
    local out code
    wait_for_socket
    log "configuración inicial (secretos, cuenta meshbox-ingest y ACL)"
    out=$(cd / && runuser -u meshbox -- env HOME="$VAR_DIR" TMPDIR="$VAR_DIR/tmp" \
        "$APP_PYTHON" -m meshbox bootstrap --config "$CONFIG" --mode appliance --json)
    code=$(printf '%s\n' "$out" | tail -n 1 | /usr/bin/python3 -c '
import json, sys
try:
    data = json.loads(sys.stdin.read())
except ValueError:
    data = {}
print((data.get("setup_code") if isinstance(data, dict) else None) or "")
')
    write_setup_code "$code"
}

set_hostname() {
    local current
    current=$(hostname)
    # Respeta un nombre elegido en Raspberry Pi Imager (cloud-init ya corrió antes que esto).
    case $current in
    raspberrypi | localhost | "")
        log "nombre de host: meshbox"
        privd_call '{"cmd":"system.hostname","args":{"name":"meshbox"}}' >/dev/null ||
            log "no se pudo cambiar el nombre de host"
        ;;
    *) log "se conserva el nombre de host $current" ;;
    esac
}

network_ready() {
    local state
    state=$(nmcli -t -f STATE general 2>/dev/null || true)
    [[ $state == connected* ]]
}

ensure_network() {
    local waited=0
    while ((waited < NETWORK_WAIT_S)); do
        if network_ready; then
            log "red disponible"
            return 0
        fi
        sleep 2
        waited=$((waited + 2))
    done
    log "sin red después de ${NETWORK_WAIT_S} s: se inicia el punto de acceso de configuración"
    privd_call '{"cmd":"hotspot.start"}' || log "no se pudo iniciar el punto de acceso"
}

main() {
    bootstrap
    set_hostname
    ensure_network
    touch "$DONE"
    log "listo"
}

main "$@"
