"""WiFi y punto de acceso de configuración con NetworkManager (13.3, 18.3 y 24.3).

Las claves (psk) nunca pasan por la línea de comandos de `nmcli`: los perfiles se escriben como
archivos keyfile 0600 en /etc/NetworkManager/system-connections y se cargan con
`nmcli connection load`.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from .core import (
    Args,
    Command,
    CommandError,
    Context,
    Result,
    atomic_write,
    check_keys,
    ensure_dir,
    failed,
    get_bool,
    invalid,
    run_checked,
)

HOTSPOT_ID = "meshbox-hotspot"
HOTSPOT_FILE = "meshbox-hotspot.nmconnection"
HOTSPOT_ADDRESS = "10.42.0.1"
# Documentada en docs/instalacion.md: se usa solo si no hay /boot/firmware/meshbox-setup.txt.
DEFAULT_HOTSPOT_PASSWORD = "meshbox-setup"  # noqa: S105 - clave pública documentada (24.3)
WIFI_PROFILE_PREFIX = "meshbox-wifi-"
CONNECT_WINDOW_S = 120
SCAN_CACHE_NAME = "last-scan.json"
MAX_NETWORKS = 60

_MAC_RE = re.compile(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$")
_UUID_LINE = re.compile(r"^uuid=([0-9a-fA-F-]{36})\s*$", re.MULTILINE)
_SETUP_KEY = re.compile(
    r"^(?:hotspot_password|password|clave|contrase(?:ñ|n)a)\s*[=:]\s*(.*)$", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Validaciones
# ---------------------------------------------------------------------------


def validate_ssid(value: object) -> str:
    if not isinstance(value, str):
        raise invalid("ssid debe ser texto")
    size = len(value.encode("utf-8"))
    if not 1 <= size <= 32:
        raise invalid("ssid debe tener entre 1 y 32 bytes")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise invalid("ssid no puede tener caracteres de control")
    return value


def validate_psk(value: object) -> str:
    if not isinstance(value, str):
        raise invalid("psk debe ser texto")
    if not 8 <= len(value) <= 63:
        raise invalid("psk debe tener entre 8 y 63 caracteres")
    if any(not 0x20 <= ord(ch) <= 0x7E for ch in value):
        raise invalid("psk solo admite caracteres ASCII imprimibles")
    return value


# ---------------------------------------------------------------------------
# nmcli
# ---------------------------------------------------------------------------


def split_terse(line: str) -> list[str]:
    """Separa una línea de `nmcli -t` respetando los escapes `\\:` y `\\\\`."""
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for ch in line:
        if escaped:
            current.append(ch)
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(ch)
    fields.append("".join(current))
    return fields


def parse_terse_kv(text: str) -> dict[str, list[str]]:
    """`nmcli -t ... device show`: líneas `CAMPO:valor` (un campo puede repetirse)."""
    result: dict[str, list[str]] = {}
    for line in text.splitlines():
        parts = split_terse(line)
        if len(parts) < 2:
            continue
        key = re.sub(r"\[\d+\]$", "", parts[0])
        result.setdefault(key, []).append(":".join(parts[1:]))
    return result


def _nmcli(ctx: Context, *args: str, timeout: float = 30, what: str = "nmcli") -> str:
    return run_checked(ctx, [ctx.bins.nmcli, *args], what=what, timeout=timeout).out


def active_connections(ctx: Context) -> list[dict[str, str]]:
    out = _nmcli(ctx, "-t", "-f", "NAME,UUID,TYPE,DEVICE", "connection", "show", "--active")
    items = []
    for line in out.splitlines():
        parts = split_terse(line)
        if len(parts) == 4:
            items.append({"name": parts[0], "uuid": parts[1], "type": parts[2], "device": parts[3]})
    return items


def active_on_iface(ctx: Context) -> dict[str, str] | None:
    for conn in active_connections(ctx):
        if conn["device"] == ctx.wifi_iface:
            return conn
    return None


def device_info(ctx: Context) -> dict[str, Any]:
    out = _nmcli(
        ctx,
        "-t",
        "-f",
        "GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS",
        "device",
        "show",
        ctx.wifi_iface,
    )
    kv = parse_terse_kv(out)
    state_raw = (kv.get("GENERAL.STATE") or [""])[0]
    match = re.search(r"\(([^)]*)\)", state_raw)
    state = match.group(1) if match else (state_raw or None)
    connection = (kv.get("GENERAL.CONNECTION") or [""])[0] or None
    if connection == "--":
        connection = None
    ip4 = [addr for addr in kv.get("IP4.ADDRESS", []) if addr]
    return {"state": state, "connection": connection, "ip4": ip4}


def wifi_profiles(ctx: Context) -> list[dict[str, str]]:
    out = _nmcli(ctx, "-t", "-f", "NAME,UUID,TYPE", "connection", "show")
    profiles = []
    for line in out.splitlines():
        parts = split_terse(line)
        if len(parts) != 3 or parts[2] not in ("802-11-wireless", "wifi"):
            continue
        name, conn_uuid = parts[0], parts[1]
        ssid = split_terse(
            _nmcli(
                ctx, "-g", "802-11-wireless.ssid", "connection", "show", "uuid", conn_uuid
            ).rstrip("\n")
        )[0]
        mode = _nmcli(
            ctx, "-g", "802-11-wireless.mode", "connection", "show", "uuid", conn_uuid
        ).strip()
        profiles.append({"name": name, "uuid": conn_uuid, "ssid": ssid, "mode": mode})
    return profiles


def _parse_scan(out: str) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for line in out.splitlines():
        parts = split_terse(line)
        if len(parts) != 7:
            continue
        in_use, ssid, bssid, signal, security, chan, freq = parts
        if not ssid:
            continue
        try:
            signal_i = int(signal)
        except ValueError:
            signal_i = 0
        try:
            chan_i: int | None = int(chan)
        except ValueError:
            chan_i = None
        freq_match = re.match(r"(\d+)", freq)
        item = {
            "ssid": ssid,
            "bssid": bssid,
            "signal": signal_i,
            "security": security.strip() if security.strip() not in ("", "--") else None,
            "channel": chan_i,
            "freq_mhz": int(freq_match.group(1)) if freq_match else None,
            "in_use": in_use.strip() == "*",
        }
        previous = best.get(ssid)
        if previous is None or item["signal"] > previous["signal"]:
            if previous is not None and previous["in_use"]:
                item["in_use"] = True
            best[ssid] = item
        elif item["in_use"]:
            previous["in_use"] = True
    networks = sorted(best.values(), key=lambda n: (-n["signal"], n["ssid"]))
    return networks[:MAX_NETWORKS]


def scan_now(ctx: Context, *, rescan: bool = True) -> list[dict[str, Any]]:
    fields = "IN-USE,SSID,BSSID,SIGNAL,SECURITY,CHAN,FREQ"
    base = [ctx.bins.nmcli, "-t", "-f", fields, "device", "wifi", "list"]
    tail = ["ifname", ctx.wifi_iface]
    if rescan:
        result = ctx.runner.run([*base, "--rescan", "yes", *tail], timeout=45)
        if result.returncode == 0:
            return _parse_scan(result.out)
    # Sin rescan (por ejemplo, "Scanning not allowed" justo después de otro escaneo).
    out = run_checked(ctx, [*base, "--rescan", "no", *tail], what="nmcli wifi list", timeout=30).out
    return _parse_scan(out)


def _scan_cache_path(ctx: Context) -> Path:
    return ctx.paths.state_dir / SCAN_CACHE_NAME


def _write_scan_cache(ctx: Context, networks: list[dict[str, Any]]) -> None:
    try:
        ensure_dir(ctx.paths.state_dir, 0o700)
        data = json.dumps({"ts": time.time(), "networks": networks}, ensure_ascii=False)
        atomic_write(ctx, _scan_cache_path(ctx), data.encode("utf-8"), mode=0o600)
    except (OSError, CommandError):
        pass


def _read_scan_cache(ctx: Context) -> dict[str, Any]:
    try:
        data = json.loads(_scan_cache_path(ctx).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"ts": None, "networks": []}
    if not isinstance(data, dict) or not isinstance(data.get("networks"), list):
        return {"ts": None, "networks": []}
    return data


# ---------------------------------------------------------------------------
# Keyfiles
# ---------------------------------------------------------------------------


def keyfile_escape(value: str) -> str:
    """Escapa un valor de texto para GKeyFile (lo que lee NetworkManager)."""
    return (
        value.replace("\\", "\\\\")
        .replace(" ", "\\s")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
    )


def ssid_bytes(ssid: str) -> str:
    """SSID como lista de bytes (`72;111;108;97;`), sin ambigüedades de escape."""
    return "".join(f"{b};" for b in ssid.encode("utf-8"))


def wifi_keyfile(conn_id: str, conn_uuid: str, iface: str, ssid: str, psk: str) -> str:
    return "\n".join(
        [
            "[connection]",
            f"id={conn_id}",
            f"uuid={conn_uuid}",
            "type=wifi",
            f"interface-name={iface}",
            "autoconnect=true",
            "autoconnect-priority=10",
            "",
            "[wifi]",
            "mode=infrastructure",
            f"ssid={ssid_bytes(ssid)}",
            "",
            "[wifi-security]",
            "auth-alg=open",
            "key-mgmt=wpa-psk",
            f"psk={keyfile_escape(psk)}",
            "",
            "[ipv4]",
            "method=auto",
            "",
            "[ipv6]",
            "addr-gen-mode=default",
            "method=auto",
            "",
        ]
    )


def hotspot_keyfile(conn_uuid: str, iface: str, ssid: str, psk: str) -> str:
    # pmf=1 (desactivado): brcmfmac, el WiFi de la Pi, falla en modo AP con PMF.
    return "\n".join(
        [
            "[connection]",
            f"id={HOTSPOT_ID}",
            f"uuid={conn_uuid}",
            "type=wifi",
            f"interface-name={iface}",
            "autoconnect=false",
            "",
            "[wifi]",
            "band=bg",
            "mode=ap",
            f"ssid={ssid_bytes(ssid)}",
            "",
            "[wifi-security]",
            "group=ccmp;",
            "key-mgmt=wpa-psk",
            "pairwise=ccmp;",
            "pmf=1",
            "proto=rsn;",
            f"psk={keyfile_escape(psk)}",
            "",
            "[ipv4]",
            f"address1={HOTSPOT_ADDRESS}/24",
            "method=shared",
            "",
            "[ipv6]",
            "addr-gen-mode=default",
            "method=disabled",
            "",
        ]
    )


def _read_uuid(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = _UUID_LINE.search(text)
    return match.group(1).lower() if match else None


def _profile_path(ctx: Context, ssid: str) -> Path:
    digest = hashlib.sha256(ssid.encode("utf-8")).hexdigest()[:10]
    return ctx.paths.nm_connections_dir / f"{WIFI_PROFILE_PREFIX}{digest}.nmconnection"


def _require_nm(ctx: Context) -> None:
    if not ctx.paths.nm_connections_dir.is_dir():
        raise failed("NetworkManager no está instalado (falta system-connections)")


def _hotspot_uuid(ctx: Context) -> str | None:
    return _read_uuid(ctx.paths.nm_connections_dir / HOTSPOT_FILE)


def _is_hotspot(ctx: Context, conn: dict[str, str] | None) -> bool:
    if conn is None:
        return False
    return conn["name"] == HOTSPOT_ID or conn["uuid"] == _hotspot_uuid(ctx)


# ---------------------------------------------------------------------------
# Punto de acceso
# ---------------------------------------------------------------------------


def hotspot_ssid(ctx: Context) -> str:
    try:
        mac = (ctx.paths.sys_class_net / ctx.wifi_iface / "address").read_text().strip().lower()
    except OSError as exc:
        raise failed(f"no se encontró la interfaz {ctx.wifi_iface}") from exc
    if not _MAC_RE.fullmatch(mac):
        raise failed("dirección MAC no válida")
    return "meshbox-" + mac.replace(":", "")[-4:]


def read_setup_password(path: Path) -> str | None:
    """Clave del punto de acceso desde meshbox-setup.txt (partición de arranque, FAT).

    Formato: una línea `clave=...` (también `password=` o `hotspot_password=`), o un archivo
    con una sola línea que es la clave. Tolera BOM y fines de línea de Windows.
    """
    try:
        raw = path.read_bytes()[:4096]
    except OSError:
        return None
    text = raw.decode("utf-8-sig", "replace")
    loose: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        match = _SETUP_KEY.match(stripped)
        if match:
            value = match.group(1).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            return _valid_psk_or_none(value)
        loose.append(stripped)
    if len(loose) == 1:
        return _valid_psk_or_none(loose[0])
    return None


def _valid_psk_or_none(value: str) -> str | None:
    try:
        return validate_psk(value)
    except CommandError:
        return None


def hotspot_password(ctx: Context) -> tuple[str, str]:
    value = read_setup_password(ctx.paths.boot_setup_file)
    if value is not None:
        return value, "setup_file"
    return DEFAULT_HOTSPOT_PASSWORD, "default"


def start_hotspot(ctx: Context, *, scan_first: bool = True) -> Result:
    _require_nm(ctx)
    ssid = hotspot_ssid(ctx)
    password, source = hotspot_password(ctx)
    if scan_first:
        # Con una sola radio no se puede escanear en modo AP: se guarda el último escaneo
        # para que el asistente muestre las redes de la casa.
        with contextlib.suppress(CommandError):
            _write_scan_cache(ctx, scan_now(ctx, rescan=True))
    path = ctx.paths.nm_connections_dir / HOTSPOT_FILE
    conn_uuid = _read_uuid(path) or str(uuid.uuid4())
    atomic_write(
        ctx, path, hotspot_keyfile(conn_uuid, ctx.wifi_iface, ssid, password).encode(), mode=0o600
    )
    _nmcli(ctx, "connection", "load", str(path), what="nmcli connection load")
    _nmcli(
        ctx,
        "--wait",
        "30",
        "connection",
        "up",
        "uuid",
        conn_uuid,
        "ifname",
        ctx.wifi_iface,
        timeout=45,
        what="nmcli connection up",
    )
    return {"ssid": ssid, "address": HOTSPOT_ADDRESS, "password_source": source}


def _ensure_no_network_job(ctx: Context) -> None:
    job = ctx.jobs.running("network")
    if job is not None:
        raise CommandError("busy", f"hay un cambio de red en curso ({job.id})")


def hotspot_start(ctx: Context, args: Args) -> Result:
    check_keys(args)
    _ensure_no_network_job(ctx)
    return start_hotspot(ctx)


def hotspot_stop(ctx: Context, args: Args) -> Result:
    check_keys(args)
    _ensure_no_network_job(ctx)
    _require_nm(ctx)
    stopped = False
    conn_uuid = _hotspot_uuid(ctx)
    if conn_uuid:
        res = ctx.runner.run([ctx.bins.nmcli, "connection", "down", "uuid", conn_uuid], timeout=30)
        stopped = res.returncode == 0
    # Que NetworkManager vuelva a una red conocida (el punto de acceso no se autoconecta).
    reconnect = ctx.runner.run(
        [ctx.bins.nmcli, "--wait", "60", "device", "connect", ctx.wifi_iface], timeout=70
    )
    return {"stopped": stopped, "reconnected": reconnect.returncode == 0}


# ---------------------------------------------------------------------------
# WiFi
# ---------------------------------------------------------------------------


def wifi_scan(ctx: Context, args: Args) -> Result:
    check_keys(args)
    if _is_hotspot(ctx, active_on_iface(ctx)):
        cache = _read_scan_cache(ctx)
        return {"networks": cache["networks"], "cached": True, "scanned_at": cache["ts"]}
    networks = scan_now(ctx, rescan=True)
    _write_scan_cache(ctx, networks)
    return {"networks": networks, "cached": False, "scanned_at": time.time()}


def _current_ssid_signal(ctx: Context) -> tuple[str | None, int | None]:
    result = ctx.runner.run(
        [
            ctx.bins.nmcli,
            "-t",
            "-f",
            "ACTIVE,SSID,SIGNAL",
            "device",
            "wifi",
            "list",
            "--rescan",
            "no",
            "ifname",
            ctx.wifi_iface,
        ],
        timeout=20,
    )
    if result.returncode != 0:
        return None, None
    for line in result.out.splitlines():
        parts = split_terse(line)
        if len(parts) == 3 and parts[0] == "yes":
            try:
                return parts[1] or None, int(parts[2])
            except ValueError:
                return parts[1] or None, None
    return None, None


def wifi_status(ctx: Context, args: Args) -> Result:
    check_keys(args)
    info = device_info(ctx)
    active = active_on_iface(ctx)
    hotspot = _is_hotspot(ctx, active)
    ssid, signal = (None, None) if hotspot else _current_ssid_signal(ctx)
    saved = [
        {"ssid": p["ssid"], "name": p["name"], "uuid": p["uuid"]}
        for p in wifi_profiles(ctx)
        if p["mode"] != "ap"
    ]
    return {
        "device": ctx.wifi_iface,
        "state": info["state"],
        "connection": info["connection"],
        "ssid": hotspot_ssid(ctx) if hotspot else ssid,
        "signal": signal,
        "ip4": info["ip4"],
        "hotspot": hotspot,
        "saved": saved,
        "job": ctx.jobs.latest("wifi"),
    }


def _wait_ip(ctx: Context, deadline: float) -> list[str]:
    while True:
        with contextlib.suppress(CommandError):
            info = device_info(ctx)
            if info["state"] and info["state"].startswith("connected") and info["ip4"]:
                return list(info["ip4"])
        if ctx.monotonic() >= deadline:
            return []
        ctx.sleep(2)


def _connect_job(
    ctx: Context,
    job: Any,
    ssid: str,
    psk: str,
    previous: dict[str, str] | None,
) -> Result:
    start = ctx.monotonic()
    path = _profile_path(ctx, ssid)
    old_content = path.read_bytes() if path.exists() else None
    conn_uuid = _read_uuid(path) or str(uuid.uuid4())
    job.update(step="profile")
    atomic_write(
        ctx,
        path,
        wifi_keyfile(path.stem, conn_uuid, ctx.wifi_iface, ssid, psk).encode(),
        mode=0o600,
    )
    _nmcli(ctx, "connection", "load", str(path), what="nmcli connection load")

    job.update(step="connecting")
    wait_s = CONNECT_WINDOW_S - 10
    up = ctx.runner.run(
        [
            ctx.bins.nmcli,
            "--wait",
            str(wait_s),
            "connection",
            "up",
            "uuid",
            conn_uuid,
            "ifname",
            ctx.wifi_iface,
        ],
        timeout=wait_s + 10,
    )
    ip4: list[str] = []
    if up.returncode == 0:
        ip4 = _wait_ip(ctx, start + CONNECT_WINDOW_S)
    if ip4:
        return {"ssid": ssid, "ip4": ip4, "connection": path.stem}

    # Falló: se vuelve a la red anterior (o al punto de acceso) dentro de la ventana.
    job.update(step="fallback")
    ctx.runner.run([ctx.bins.nmcli, "connection", "down", "uuid", conn_uuid], timeout=30)
    if old_content is not None:
        atomic_write(ctx, path, old_content, mode=0o600)
        ctx.runner.run([ctx.bins.nmcli, "connection", "load", str(path)], timeout=30)
    else:
        ctx.runner.run([ctx.bins.nmcli, "connection", "delete", "uuid", conn_uuid], timeout=30)
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
    restored = False
    if previous is not None:
        back = ctx.runner.run(
            [
                ctx.bins.nmcli,
                "--wait",
                "60",
                "connection",
                "up",
                "uuid",
                previous["uuid"],
                "ifname",
                ctx.wifi_iface,
            ],
            timeout=70,
        )
        restored = back.returncode == 0
    elif ctx.mode == "appliance":
        try:
            start_hotspot(ctx, scan_first=False)
            restored = True
        except CommandError:
            restored = False
    detail = clean_reason(up.err or up.out)
    where = "se volvió a la red anterior" if restored else "no se pudo volver a la red anterior"
    raise failed(f"no se pudo conectar a la red ({detail or 'sin detalle'}); {where}")


def clean_reason(text: str) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text).strip()
    return text[-200:]


def wifi_connect(ctx: Context, args: Args) -> Result:
    check_keys(args, ("ssid", "psk"))
    ssid = validate_ssid(args["ssid"])
    psk = validate_psk(args["psk"])
    _require_nm(ctx)
    previous = active_on_iface(ctx)
    job = ctx.jobs.start(
        "wifi",
        lambda job: _connect_job(ctx, job, ssid, psk, previous),
        group="network",
        meta={"ssid": ssid},
    )
    return {"job": job.id, "state": job.state}


def wifi_forget(ctx: Context, args: Args) -> Result:
    check_keys(args, ("ssid",), ("force",))
    ssid = validate_ssid(args["ssid"])
    force = get_bool(args, "force")
    _ensure_no_network_job(ctx)
    active = active_on_iface(ctx)
    deleted = 0
    for profile in wifi_profiles(ctx):
        if profile["ssid"] != ssid or profile["mode"] == "ap":
            continue
        if active is not None and profile["uuid"] == active["uuid"] and not force:
            raise failed("es la red en uso; conéctate a otra antes de olvidarla")
        _nmcli(ctx, "connection", "delete", "uuid", profile["uuid"], what="nmcli connection delete")
        deleted += 1
    return {"ssid": ssid, "deleted": deleted}


COMMANDS = {
    "wifi.scan": Command(wifi_scan),
    "wifi.status": Command(wifi_status),
    "wifi.connect": Command(
        wifi_connect, shared_ok=False, secret_args=frozenset({"psk"}), exclusive=True
    ),
    "wifi.forget": Command(wifi_forget, shared_ok=False, exclusive=True),
    "hotspot.start": Command(hotspot_start, shared_ok=False, exclusive=True),
    "hotspot.stop": Command(hotspot_stop, shared_ok=False, exclusive=True),
}
