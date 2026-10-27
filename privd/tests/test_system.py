"""Comandos del sistema: nombre de host, zona horaria, apagado, información y hora."""

from __future__ import annotations

import os

import pytest
from privd_testkit import Env, fail, ok

from commands import system
from commands.core import CommandError


def test_ping(env: Env) -> None:
    assert system.ping(env.ctx, {})["mode"] == "appliance"
    with pytest.raises(CommandError):
        system.ping(env.ctx, {"x": 1})


# ---------------------------------------------------------------------------
# Nombre de host
# ---------------------------------------------------------------------------


def test_hostname_updates_system_hosts_and_cloud_init(env: Env) -> None:
    env.ctx.paths.etc_hosts.write_text(
        "127.0.0.1\tlocalhost\n::1\tlocalhost ip6-localhost\n127.0.1.1\traspberrypi\n"
    )
    env.ctx.paths.cloud_cfg_d.mkdir(parents=True)
    assert system.hostname(env.ctx, {"name": "MeshBox"}) == {"hostname": "meshbox"}
    assert env.runner.argvs() == [["/usr/bin/hostnamectl", "set-hostname", "meshbox"]]
    hosts = env.ctx.paths.etc_hosts.read_text().splitlines()
    assert hosts == ["127.0.0.1\tlocalhost", "::1\tlocalhost ip6-localhost", "127.0.1.1\tmeshbox"]
    dropin = (env.ctx.paths.cloud_cfg_d / system.CLOUD_INIT_DROPIN).read_text()
    assert "preserve_hostname: true" in dropin


def test_hostname_appends_hosts_entry_and_skips_cloud_init(env: Env) -> None:
    env.ctx.paths.etc_hosts.write_text("127.0.0.1\tlocalhost\n")
    system.hostname(env.ctx, {"name": "nodo-1"})
    assert env.ctx.paths.etc_hosts.read_text().endswith("127.0.1.1\tnodo-1\n")
    assert not env.ctx.paths.cloud_cfg_d.exists()


def test_hostname_without_hosts_file(env: Env) -> None:
    system.hostname(env.ctx, {"name": "meshbox"})
    assert "127.0.1.1\tmeshbox" in env.ctx.paths.etc_hosts.read_text()


@pytest.mark.parametrize(
    "name",
    ["", "-meshbox", "meshbox-", "mesh_box", "mesh.box", "a" * 64, "mesh box", "$(id)", 5, None],
)
def test_invalid_hostnames(env: Env, name: object) -> None:
    with pytest.raises(CommandError) as exc:
        system.hostname(env.ctx, {"name": name})
    assert exc.value.code == "invalid_args"
    assert env.runner.calls == []


def test_hostname_failure(env: Env) -> None:
    env.runner.on(["/usr/bin/hostnamectl"], fail(1, "Access denied"))
    with pytest.raises(CommandError) as exc:
        system.hostname(env.ctx, {"name": "meshbox"})
    assert "Access denied" in exc.value.message


# ---------------------------------------------------------------------------
# Zona horaria
# ---------------------------------------------------------------------------


@pytest.fixture
def zoneinfo(env: Env) -> Env:
    base = env.ctx.paths.zoneinfo_dir
    (base / "America/Argentina").mkdir(parents=True)
    (base / "America/Argentina/Buenos_Aires").write_bytes(b"TZif")
    (base / "Etc").mkdir()
    (base / "Etc/GMT+3").write_bytes(b"TZif")
    (base / "UTC").write_bytes(b"TZif")
    return env


@pytest.mark.parametrize("tz", ["America/Argentina/Buenos_Aires", "Etc/GMT+3", "UTC"])
def test_timezone_valid(zoneinfo: Env, tz: str) -> None:
    assert system.timezone(zoneinfo.ctx, {"tz": tz}) == {"timezone": tz}
    assert zoneinfo.runner.argvs() == [["/usr/bin/timedatectl", "set-timezone", tz]]


@pytest.mark.parametrize(
    "tz",
    [
        "America/Argentina/Cordoba",
        "America/Argentina",
        "../../etc/passwd",
        "America/../UTC",
        "-UTC",
        "+UTC",
        "America//Argentina",
        "/UTC",
        "UTC; reboot",
        "A/B/C/D",
        "",
        7,
    ],
)
def test_timezone_invalid(zoneinfo: Env, tz: object) -> None:
    with pytest.raises(CommandError) as exc:
        system.timezone(zoneinfo.ctx, {"tz": tz})
    assert exc.value.code == "invalid_args"
    assert zoneinfo.runner.calls == []


@pytest.mark.linux
def test_timezone_symlink_outside_zoneinfo(zoneinfo: Env) -> None:
    outside = zoneinfo.root / "secreto"
    outside.write_text("x")
    (zoneinfo.ctx.paths.zoneinfo_dir / "Escape").symlink_to(outside)
    with pytest.raises(CommandError):
        system.timezone(zoneinfo.ctx, {"tz": "Escape"})


def test_time_status(env: Env) -> None:
    env.runner.on(
        ["/usr/bin/timedatectl", "show"],
        ok(
            "Timezone=America/Argentina/Buenos_Aires\nLocalRTC=no\nCanNTP=yes\nNTP=yes\n"
            "NTPSynchronized=no\nTimeUSec=Tue 2026-10-20 08:44:00 -03\n"
        ),
    )
    assert system.time_status(env.ctx, {}) == {
        "timezone": "America/Argentina/Buenos_Aires",
        "ntp": True,
        "ntp_synchronized": False,
        "can_ntp": True,
        "local_rtc": False,
        "time": "Tue 2026-10-20 08:44:00 -03",
    }


def test_time_status_missing_fields(env: Env) -> None:
    env.runner.on(["/usr/bin/timedatectl", "show"], ok("Timezone=UTC\n"))
    result = system.time_status(env.ctx, {})
    assert result["ntp_synchronized"] is None


# ---------------------------------------------------------------------------
# Reinicio y apagado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fn", "action"), [(system.reboot, "reboot"), (system.shutdown, "poweroff")]
)
def test_power_is_scheduled(env: Env, fn: object, action: str) -> None:
    result = fn(env.ctx, {})  # type: ignore[operator]
    assert result["scheduled"] is True
    assert result["action"] == action
    env.ctx.jobs.wait_all(5)
    assert env.runner.argvs() == [["/usr/bin/systemctl", action]]
    assert env.clock.sleeps == [system.POWER_DELAY_S]


def test_power_busy(env: Env) -> None:
    import threading

    gate = threading.Event()
    env.ctx.jobs.start("power", lambda job: gate.wait(5) and {}, group="power")
    try:
        with pytest.raises(CommandError) as exc:
            system.reboot(env.ctx, {})
        assert exc.value.code == "busy"
    finally:
        gate.set()
        env.ctx.jobs.wait_all(5)


# ---------------------------------------------------------------------------
# Información
# ---------------------------------------------------------------------------


def test_info(env: Env) -> None:
    paths = env.ctx.paths
    paths.device_tree_model.parent.mkdir(parents=True)
    paths.device_tree_model.write_bytes(b"Raspberry Pi Zero 2 W Rev 1.0\x00")
    (paths.proc_dir / "uptime").write_text("12345.67 40000.00\n")
    paths.os_release.write_text('PRETTY_NAME="Debian GNU/Linux 13 (trixie)"\nID=debian\n')
    paths.etc_hostname.write_text("otrapi\n")
    result = system.info(env.ctx, {})
    assert result["hostname"] == "otrapi"
    assert result["model"] == "Raspberry Pi Zero 2 W Rev 1.0"
    assert result["uptime_s"] == pytest.approx(12345.67)
    assert result["os"] == "Debian GNU/Linux 13 (trixie)"
    assert result["mode"] == "appliance"
    assert result["kernel"]
    assert result["privd_version"]


def test_info_without_files(env: Env) -> None:
    result = system.info(env.ctx, {})
    assert result["model"] is None
    assert result["uptime_s"] is None
    assert result["os"] is None
    assert result["hostname"]


def test_info_bad_uptime(env: Env) -> None:
    os.makedirs(env.ctx.paths.proc_dir, exist_ok=True)
    (env.ctx.paths.proc_dir / "uptime").write_text("no-es-numero\n")
    assert system.info(env.ctx, {})["uptime_s"] is None
