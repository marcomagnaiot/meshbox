"""WiFi y punto de acceso con nmcli simulado (18.3 y 24.3)."""

from __future__ import annotations

import json
import stat
import threading
from pathlib import Path

import pytest
from privd_testkit import Call, Env, fail, ok

import meshbox_privd
from commands import wifi
from commands.core import CommandError

NMCLI = "/usr/bin/nmcli"
ACTIVE = [NMCLI, "-t", "-f", "NAME,UUID,TYPE,DEVICE", "connection", "show", "--active"]
DEVICE_SHOW = [NMCLI, "-t", "-f", "GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS", "device", "show"]
PROFILES = [NMCLI, "-t", "-f", "NAME,UUID,TYPE", "connection", "show"]
SCAN_YES = [NMCLI, "-t", "-f", "IN-USE,SSID,BSSID,SIGNAL,SECURITY,CHAN,FREQ", "device", "wifi"]
CURRENT = [NMCLI, "-t", "-f", "ACTIVE,SSID,SIGNAL", "device", "wifi", "list"]
PREV_UUID = "11111111-2222-3333-4444-555555555555"

SCAN_OUTPUT = "\n".join(
    [
        r"*:Casa:AA\:BB\:CC\:DD\:EE\:01:70:WPA2:6:2437 MHz",
        r" :Casa:AA\:BB\:CC\:DD\:EE\:02:82:WPA2:11:2462 MHz",
        r" :Vecino\:5G:AA\:BB\:CC\:DD\:EE\:03:40:WPA1 WPA2:1:2412 MHz",
        r" ::AA\:BB\:CC\:DD\:EE\:04:90::1:2412 MHz",
        r" :Abierta:AA\:BB\:CC\:DD\:EE\:05:x:--:?:?",
        "linea rota",
    ]
)


def set_mac(env: Env, mac: str = "b8:27:eb:12:3a:bc") -> None:
    iface = env.ctx.paths.sys_class_net / "wlan0"
    iface.mkdir(parents=True, exist_ok=True)
    (iface / "address").write_text(mac + "\n")


def setup_nm(
    env: Env,
    *,
    active: str = f"MiCasa:{PREV_UUID}:802-11-wireless:wlan0\nlo:x:loopback:lo",
    profiles: dict[str, tuple[str, str, str]] | None = None,
) -> dict[str, bool]:
    """nmcli simulado. Devuelve el estado mutable (conectado o no a la red nueva)."""
    state = {"connected": False, "up_ok": True}
    profiles = (
        profiles if profiles is not None else {PREV_UUID: ("MiCasa", "Casa", "infrastructure")}
    )
    env.runner.on(ACTIVE, ok(active))
    env.runner.on(
        PROFILES,
        ok("\n".join(f"{name}:{uid}:802-11-wireless" for uid, (name, _s, _m) in profiles.items())),
    )
    for uid, (_name, ssid, mode) in profiles.items():
        env.runner.on(
            [NMCLI, "-g", "802-11-wireless.ssid", "connection", "show", "uuid", uid],
            ok(ssid.replace(":", "\\:") + "\n"),
        )
        env.runner.on(
            [NMCLI, "-g", "802-11-wireless.mode", "connection", "show", "uuid", uid],
            ok(mode + "\n"),
        )

    def device_show(call: Call) -> object:
        if state["connected"]:
            return ok(
                "GENERAL.STATE:100 (connected)\nGENERAL.CONNECTION:Nueva\n"
                "IP4.ADDRESS[1]:192.168.0.30/24\n"
            )
        return ok("GENERAL.STATE:30 (disconnected)\nGENERAL.CONNECTION:--\n")

    env.runner.on(DEVICE_SHOW, device_show)  # type: ignore[arg-type]

    def up(call: Call) -> object:
        hotspot_uuid = wifi._read_uuid(env.ctx.paths.nm_connections_dir / wifi.HOTSPOT_FILE)
        if call.argv[3] == "device" or call.argv[-3] in (PREV_UUID, hotspot_uuid):
            return ok()
        if state["up_ok"]:
            state["connected"] = True
            return ok("Connection successfully activated")
        return fail(4, "Error: Connection activation failed: Secrets were required")

    env.runner.on([NMCLI, "--wait"], up)  # type: ignore[arg-type]
    return state


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def test_split_terse_handles_escapes() -> None:
    assert wifi.split_terse(r"*:Mi\:Red:AA\:BB:70") == ["*", "Mi:Red", "AA:BB", "70"]
    assert wifi.split_terse(r"a\\b:c") == ["a\\b", "c"]
    assert wifi.split_terse("") == [""]


def test_parse_terse_kv() -> None:
    kv = wifi.parse_terse_kv("IP4.ADDRESS[1]:10.0.0.2/24\nIP4.ADDRESS[2]:10.0.0.3/24\nX\n")
    assert kv == {"IP4.ADDRESS": ["10.0.0.2/24", "10.0.0.3/24"]}


@pytest.mark.parametrize("ssid", ["Casa", "a" * 32, "ñandú", "Red con espacios", "x:y;z#"])
def test_valid_ssids(ssid: str) -> None:
    assert wifi.validate_ssid(ssid) == ssid


@pytest.mark.parametrize("ssid", ["", "a" * 33, "ñ" * 17, "con\nsalto", "tab\t", "\x00", 5, None])
def test_invalid_ssids(ssid: object) -> None:
    with pytest.raises(CommandError) as exc:
        wifi.validate_ssid(ssid)
    assert exc.value.code == "invalid_args"


@pytest.mark.parametrize("psk", ["12345678", "a" * 63, "con espacio y \\ barra", "#;=[]abc"])
def test_valid_psk(psk: str) -> None:
    assert wifi.validate_psk(psk) == psk


@pytest.mark.parametrize("psk", ["1234567", "a" * 64, "clave\nnueva", "contraseña123", 12345678])
def test_invalid_psk(psk: object) -> None:
    with pytest.raises(CommandError):
        wifi.validate_psk(psk)


def test_keyfile_escape_and_ssid_bytes() -> None:
    assert wifi.keyfile_escape(r" a b\c ") == r"\sa\sb\\c\s"
    assert wifi.ssid_bytes("Hi") == "72;105;"
    assert wifi.ssid_bytes("ñ") == "195;177;"


def test_wifi_keyfile_contents() -> None:
    text = wifi.wifi_keyfile("meshbox-wifi-x", "uuid-1", "wlan0", "Casa", "mi clave\\1")
    assert "ssid=67;97;115;97;" in text
    assert r"psk=mi\sclave\\1" in text
    assert "key-mgmt=wpa-psk" in text
    assert "autoconnect=true" in text


def test_hotspot_keyfile_contents() -> None:
    text = wifi.hotspot_keyfile("uuid-2", "wlan0", "meshbox-3abc", "clave-setup")
    assert "mode=ap" in text
    assert "method=shared" in text
    assert "address1=10.42.0.1/24" in text
    assert "pmf=1" in text
    assert "autoconnect=false" in text


# ---------------------------------------------------------------------------
# Escaneo y estado
# ---------------------------------------------------------------------------


def test_scan_parses_dedupes_and_caches(env: Env) -> None:
    setup_nm(env)
    env.runner.on(SCAN_YES, ok(SCAN_OUTPUT))
    result = wifi.wifi_scan(env.ctx, {})
    assert result["cached"] is False
    nets = {n["ssid"]: n for n in result["networks"]}
    assert set(nets) == {"Casa", "Vecino:5G", "Abierta"}
    assert nets["Casa"]["signal"] == 82
    assert nets["Casa"]["in_use"] is True
    assert nets["Casa"]["channel"] == 11
    assert nets["Casa"]["freq_mhz"] == 2462
    assert nets["Vecino:5G"]["security"] == "WPA1 WPA2"
    assert nets["Abierta"]["signal"] == 0
    assert nets["Abierta"]["security"] is None
    assert result["networks"][0]["ssid"] == "Casa"
    cache = json.loads((env.ctx.paths.state_dir / "last-scan.json").read_text())
    assert len(cache["networks"]) == 3


def test_scan_falls_back_without_rescan(env: Env) -> None:
    setup_nm(env)

    def scan(call: Call) -> object:
        if "yes" in call.argv:
            return fail(1, "Error: Scanning not allowed immediately following previous scan")
        return ok(SCAN_OUTPUT)

    env.runner.on(SCAN_YES, scan)  # type: ignore[arg-type]
    assert len(wifi.wifi_scan(env.ctx, {})["networks"]) == 3


def test_scan_in_hotspot_mode_uses_cache(env: Env) -> None:
    hotspot_uuid = "99999999-2222-3333-4444-555555555555"
    setup_nm(env, active=f"meshbox-hotspot:{hotspot_uuid}:802-11-wireless:wlan0")
    (env.ctx.paths.state_dir).mkdir(parents=True, exist_ok=True)
    (env.ctx.paths.state_dir / "last-scan.json").write_text(
        json.dumps({"ts": 123.0, "networks": [{"ssid": "Casa"}]})
    )
    result = wifi.wifi_scan(env.ctx, {})
    assert result == {"networks": [{"ssid": "Casa"}], "cached": True, "scanned_at": 123.0}
    assert env.runner.argvs(SCAN_YES) == []


def test_scan_cache_missing_or_broken(env: Env) -> None:
    setup_nm(env, active="meshbox-hotspot:x:802-11-wireless:wlan0")
    assert wifi.wifi_scan(env.ctx, {})["networks"] == []
    env.ctx.paths.state_dir.mkdir(parents=True, exist_ok=True)
    (env.ctx.paths.state_dir / "last-scan.json").write_text("[1]")
    assert wifi.wifi_scan(env.ctx, {})["networks"] == []


def test_status(env: Env) -> None:
    setup_nm(
        env,
        profiles={
            PREV_UUID: ("MiCasa", "Casa", "infrastructure"),
            "aaaaaaaa-2222-3333-4444-555555555555": ("meshbox-hotspot", "meshbox-3abc", "ap"),
        },
    )
    env.runner.on(
        DEVICE_SHOW,
        ok(
            "GENERAL.STATE:100 (connected)\nGENERAL.CONNECTION:MiCasa\n"
            "IP4.ADDRESS[1]:192.168.0.10/24"
        ),
    )
    env.runner.on(CURRENT, ok("no:Otra:30\nyes:Casa:72\n"))
    result = wifi.wifi_status(env.ctx, {})
    assert result["state"] == "connected"
    assert result["connection"] == "MiCasa"
    assert result["ssid"] == "Casa"
    assert result["signal"] == 72
    assert result["ip4"] == ["192.168.0.10/24"]
    assert result["hotspot"] is False
    assert result["saved"] == [{"ssid": "Casa", "name": "MiCasa", "uuid": PREV_UUID}]
    assert result["job"] is None


def test_status_in_hotspot(env: Env) -> None:
    set_mac(env)
    setup_nm(env, active="meshbox-hotspot:x:802-11-wireless:wlan0", profiles={})
    result = wifi.wifi_status(env.ctx, {})
    assert result["hotspot"] is True
    assert result["ssid"] == "meshbox-3abc"
    assert env.runner.argvs(CURRENT) == []


def test_status_requires_device(env: Env) -> None:
    env.runner.on(DEVICE_SHOW, fail(10, "Error: Device 'wlan0' not found."))
    with pytest.raises(CommandError) as exc:
        wifi.wifi_status(env.ctx, {})
    assert "not found" in exc.value.message


# ---------------------------------------------------------------------------
# Conexión con ventana de 2 minutos
# ---------------------------------------------------------------------------


def connect(env: Env, ssid: str = "Nueva", psk: str = "clave secreta 123") -> dict:
    result = wifi.wifi_connect(env.ctx, {"ssid": ssid, "psk": psk})
    env.ctx.jobs.wait_all(10)
    job = env.ctx.jobs.get(result["job"])
    assert job is not None
    return job


def test_connect_success(env: Env) -> None:
    setup_nm(env)
    job = connect(env)
    assert job["state"] == "succeeded", job
    assert job["result"]["ip4"] == ["192.168.0.30/24"]
    assert job["meta"] == {"ssid": "Nueva"}
    profiles = list(env.ctx.paths.nm_connections_dir.glob("meshbox-wifi-*.nmconnection"))
    assert len(profiles) == 1
    content = profiles[0].read_text()
    assert r"psk=clave\ssecreta\s123" in content
    # La clave no pasa por argumentos ni queda en el estado persistido del trabajo.
    assert "clave secreta 123" not in env.runner.all_text()
    persisted = (env.ctx.paths.state_dir / "jobs" / f"{job['job']}.json").read_text()
    assert "secreta" not in persisted
    up = env.runner.argvs([NMCLI, "--wait"])
    assert up[0][:4] == [NMCLI, "--wait", "110", "connection"]


@pytest.mark.linux
def test_connect_profile_permissions(env: Env) -> None:
    setup_nm(env)
    connect(env)
    (profile,) = env.ctx.paths.nm_connections_dir.glob("meshbox-wifi-*.nmconnection")
    assert stat.S_IMODE(profile.stat().st_mode) == 0o600


def test_connect_failure_returns_to_previous(env: Env) -> None:
    state = setup_nm(env)
    state["up_ok"] = False
    job = connect(env)
    assert job["state"] == "failed"
    assert "se volvió a la red anterior" in job["message"]
    assert "Secrets were required" in job["message"]
    assert list(env.ctx.paths.nm_connections_dir.glob("meshbox-wifi-*")) == []
    reactivated = [a for a in env.runner.argvs([NMCLI, "--wait"]) if PREV_UUID in a]
    assert reactivated, env.runner.argvs()
    assert env.runner.argvs([NMCLI, "connection", "delete"])


def test_connect_up_ok_but_no_ip_falls_back(env: Env) -> None:
    setup_nm(env)

    def up_without_ip(call: Call) -> object:
        return ok()

    env.runner.on([NMCLI, "--wait"], up_without_ip)  # type: ignore[arg-type]
    job = connect(env)
    assert job["state"] == "failed"
    assert env.clock.now >= 1000.0 + 120


def test_connect_failure_restores_existing_profile(env: Env) -> None:
    state = setup_nm(env)
    state["up_ok"] = False
    path = wifi._profile_path(env.ctx, "Nueva")
    original = wifi.wifi_keyfile(
        path.stem, "12345678-1234-1234-1234-123456789abc", "wlan0", "Nueva", "vieja-clave"
    )
    path.write_text(original)
    job = connect(env)
    assert job["state"] == "failed"
    assert path.read_text() == original
    assert env.runner.argvs([NMCLI, "connection", "delete"]) == []


def test_connect_failure_without_previous_starts_hotspot(env: Env) -> None:
    set_mac(env)
    state = setup_nm(env, active="")
    state["up_ok"] = False
    job = connect(env)
    assert job["state"] == "failed"
    assert "se volvió a la red anterior" in job["message"]
    assert (env.ctx.paths.nm_connections_dir / "meshbox-hotspot.nmconnection").exists()


def test_connect_is_exclusive(env: Env) -> None:
    gate = threading.Event()
    env.ctx.jobs.start("wifi", lambda job: gate.wait(5) and {}, group="network")
    try:
        with pytest.raises(CommandError) as exc:
            wifi.wifi_connect(env.ctx, {"ssid": "Nueva", "psk": "12345678"})
        assert exc.value.code == "busy"
        for fn, args in (
            (wifi.wifi_forget, {"ssid": "Casa"}),
            (wifi.hotspot_start, {}),
            (wifi.hotspot_stop, {}),
        ):
            with pytest.raises(CommandError) as exc:
                fn(env.ctx, args)
            assert exc.value.code == "busy"
    finally:
        gate.set()
        env.ctx.jobs.wait_all(5)


def test_connect_requires_network_manager(env: Env) -> None:
    env.ctx.paths.nm_connections_dir.rmdir()
    with pytest.raises(CommandError) as exc:
        wifi.wifi_connect(env.ctx, {"ssid": "Nueva", "psk": "12345678"})
    assert "NetworkManager" in exc.value.message


def test_connect_via_dispatch_is_job(env: Env) -> None:
    setup_nm(env)
    response = meshbox_privd.dispatch(
        env.ctx, json.dumps({"cmd": "wifi.connect", "args": {"ssid": "Nueva", "psk": "12345678"}})
    )
    assert response["ok"] is True
    assert response["result"]["state"] == "running"
    env.ctx.jobs.wait_all(10)
    status = meshbox_privd.dispatch(
        env.ctx, json.dumps({"cmd": "update.status", "args": {"job": response["result"]["job"]}})
    )
    assert status["result"]["kind"] == "wifi"


# ---------------------------------------------------------------------------
# Olvidar
# ---------------------------------------------------------------------------


def test_forget_deletes_matching_profiles(env: Env) -> None:
    other = "bbbbbbbb-2222-3333-4444-555555555555"
    ap = "cccccccc-2222-3333-4444-555555555555"
    setup_nm(
        env,
        active="",
        profiles={
            PREV_UUID: ("MiCasa", "Casa", "infrastructure"),
            other: ("Casa-2", "Casa", "infrastructure"),
            ap: ("meshbox-hotspot", "Casa", "ap"),
        },
    )
    assert wifi.wifi_forget(env.ctx, {"ssid": "Casa"}) == {"ssid": "Casa", "deleted": 2}
    deleted = [a[-1] for a in env.runner.argvs([NMCLI, "connection", "delete"])]
    assert sorted(deleted) == sorted([PREV_UUID, other])


def test_forget_refuses_active_network(env: Env) -> None:
    setup_nm(env)
    with pytest.raises(CommandError) as exc:
        wifi.wifi_forget(env.ctx, {"ssid": "Casa"})
    assert "en uso" in exc.value.message
    assert wifi.wifi_forget(env.ctx, {"ssid": "Casa", "force": True})["deleted"] == 1


def test_forget_unknown_ssid(env: Env) -> None:
    setup_nm(env)
    assert wifi.wifi_forget(env.ctx, {"ssid": "Nada"})["deleted"] == 0


# ---------------------------------------------------------------------------
# Punto de acceso
# ---------------------------------------------------------------------------


def test_hotspot_ssid_from_mac(env: Env) -> None:
    set_mac(env, "B8:27:EB:12:3A:BC")
    assert wifi.hotspot_ssid(env.ctx) == "meshbox-3abc"


def test_hotspot_ssid_errors(env: Env) -> None:
    with pytest.raises(CommandError):
        wifi.hotspot_ssid(env.ctx)
    set_mac(env, "no-es-una-mac")
    with pytest.raises(CommandError):
        wifi.hotspot_ssid(env.ctx)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"clave=MiClaveSegura\n", "MiClaveSegura"),
        (b"\xef\xbb\xbfclave = Mi Clave 2026\r\n", "Mi Clave 2026"),
        (b'# comentario\nhotspot_password="entre comillas"\n', "entre comillas"),
        (b"password: dos-puntos-ok\n", "dos-puntos-ok"),
        ("contraseña=con-eñe-no\n".encode(), None),
        (b"solo-la-clave\n", "solo-la-clave"),
        (b"clave=corta\n", None),
        (b"una\ndos\n", None),
        (b"", None),
    ],
)
def test_read_setup_password(tmp_path: Path, content: bytes, expected: str | None) -> None:
    path = tmp_path / "meshbox-setup.txt"
    path.write_bytes(content)
    assert wifi.read_setup_password(path) == expected


def test_read_setup_password_missing(tmp_path: Path) -> None:
    assert wifi.read_setup_password(tmp_path / "no-existe.txt") is None


def test_hotspot_start_with_default_password(env: Env) -> None:
    set_mac(env)
    setup_nm(env)
    env.runner.on(SCAN_YES, ok(SCAN_OUTPUT))
    result = wifi.hotspot_start(env.ctx, {})
    assert result == {
        "ssid": "meshbox-3abc",
        "address": "10.42.0.1",
        "password_source": "default",
    }
    keyfile = (env.ctx.paths.nm_connections_dir / "meshbox-hotspot.nmconnection").read_text()
    assert f"psk={wifi.DEFAULT_HOTSPOT_PASSWORD}" in keyfile
    # Escanea antes de levantar el AP (después no se puede) y guarda el resultado.
    assert (env.ctx.paths.state_dir / "last-scan.json").exists()
    assert env.runner.argvs([NMCLI, "connection", "load"])
    assert any("up" in a for a in env.runner.argvs([NMCLI, "--wait"]))
    assert wifi.DEFAULT_HOTSPOT_PASSWORD not in env.runner.all_text()


def test_hotspot_start_with_setup_file_reuses_uuid(env: Env) -> None:
    set_mac(env)
    setup_nm(env)
    env.ctx.paths.boot_setup_file.parent.mkdir(parents=True)
    env.ctx.paths.boot_setup_file.write_text("clave=ClaveDelUsuario\n")
    assert wifi.hotspot_start(env.ctx, {})["password_source"] == "setup_file"
    path = env.ctx.paths.nm_connections_dir / "meshbox-hotspot.nmconnection"
    first_uuid = wifi._read_uuid(path)
    wifi.hotspot_start(env.ctx, {})
    assert wifi._read_uuid(path) == first_uuid
    assert "psk=ClaveDelUsuario" in path.read_text()


def test_hotspot_start_failure(env: Env) -> None:
    set_mac(env)
    setup_nm(env)
    env.runner.on([NMCLI, "--wait"], fail(4, "Error: AP mode not supported"))
    with pytest.raises(CommandError) as exc:
        wifi.hotspot_start(env.ctx, {})
    assert "AP mode" in exc.value.message


def test_hotspot_stop(env: Env) -> None:
    set_mac(env)
    setup_nm(env)
    wifi.hotspot_start(env.ctx, {})
    result = wifi.hotspot_stop(env.ctx, {})
    assert result == {"stopped": True, "reconnected": True}
    assert env.runner.argvs([NMCLI, "connection", "down"])
    assert [NMCLI, "--wait", "60", "device", "connect", "wlan0"] in env.runner.argvs()


def test_hotspot_stop_without_profile(env: Env) -> None:
    env.runner.on([NMCLI, "--wait", "60", "device"], fail(1, "no hay red"))
    assert wifi.hotspot_stop(env.ctx, {}) == {"stopped": False, "reconnected": False}
