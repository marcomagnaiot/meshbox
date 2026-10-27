"""Cliente del socket de `meshbox-privd` (sección 13.3 y Anexo D).

En Windows y en las pruebas se usa `FakePrivClient`, que registra los comandos y devuelve
respuestas simuladas con las mismas formas que privd (`privd/commands/`).
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import sys
import time
from pathlib import Path
from typing import Any

import orjson

log = logging.getLogger(__name__)
SHARED_FORBIDDEN = frozenset(
    {"system.hostname", "wifi.connect", "wifi.forget", "hotspot.start", "hotspot.stop"}
)
UNIT_COMMANDS = frozenset({"service.status", "mosquitto.status", "cloudflared.status"})
ENABLED_STATES = frozenset({"enabled", "enabled-runtime", "static", "alias", "indirect"})


class PrivError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def normalize(cmd: str, result: dict[str, Any]) -> dict[str, Any]:
    """Respuesta de privd → forma que usa el panel.

    Los `*.status` de unidades traen `active` = ActiveState de systemd ("active", "failed"…) y
    `enabled` = UnitFileState; el panel recibe booleanos y el texto queda en `state` y
    `unit_file_state`.
    """
    if cmd in UNIT_COMMANDS:
        state = result.get("active")
        if isinstance(state, str) or state is None:
            result["state"] = state
            result["active"] = None if state is None else state == "active"
        unit_file = result.get("enabled")
        if isinstance(unit_file, str) or unit_file is None:
            result["unit_file_state"] = unit_file
            result["enabled"] = None if unit_file is None else unit_file in ENABLED_STATES
    return result


class PrivClient:
    fake = False

    def __init__(self, socket_path: Path, timeout: float = 130.0) -> None:
        self.socket_path = socket_path
        self.timeout = timeout

    async def call(self, cmd: str, **args: Any) -> dict[str, Any]:
        request_id = secrets.token_hex(4)
        payload = orjson.dumps({"cmd": cmd, "args": args, "request_id": request_id}) + b"\n"
        try:
            reader, writer = await asyncio.wait_for(
                getattr(asyncio, "open_unix_connection")(str(self.socket_path)),  # noqa: B009 - solo Linux
                5,
            )
        except (OSError, TimeoutError) as e:
            raise PrivError("unavailable", f"no se pudo conectar con privd: {e}") from e
        try:
            writer.write(payload)
            await writer.drain()
            line = await asyncio.wait_for(reader.readline(), self.timeout)
        except TimeoutError as e:
            raise PrivError("timeout", f"privd no respondió a {cmd}") from e
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
        if not line:
            raise PrivError("unavailable", "privd cerró la conexión sin responder")
        resp = orjson.loads(line)
        if not resp.get("ok"):
            err = resp.get("error") or {}
            raise PrivError(str(err.get("code", "command_failed")), str(err.get("message", "")))
        result = resp.get("result") or {}
        return normalize(cmd, result if isinstance(result, dict) else {"value": result})


class FakePrivClient:
    """privd simulado: Windows, desarrollo y pruebas. Mismas formas que `privd/commands/`."""

    fake = True

    def __init__(self, mode: str = "appliance") -> None:
        self.mode = mode
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.accounts: dict[str, str] = {}
        self.acl: dict[str, Any] = {}
        self.tunnel_token: str | None = None
        self.cloudflared_enabled = False
        self.hostname = "meshbox-dev"
        self.timezone = "America/Argentina/Buenos_Aires"
        self.jobs: dict[str, dict[str, Any]] = {}
        self.fail: dict[str, PrivError] = {}
        self.started_at = time.time()
        self.hotspot = False
        self.ssid = "Casa"
        from .. import __version__

        self.current = __version__
        self.installed = [__version__]

    async def call(self, cmd: str, **args: Any) -> dict[str, Any]:
        safe_args = {
            k: ("***" if k in ("password", "psk", "token") else v) for k, v in args.items()
        }
        self.calls.append((cmd, safe_args))
        log.info("privd (simulado): %s %s", cmd, safe_args)
        if cmd in self.fail:
            raise self.fail[cmd]
        if self.mode == "shared" and cmd in SHARED_FORBIDDEN:
            raise PrivError("not_allowed_in_shared_mode", "no permitido en un equipo compartido")
        await asyncio.sleep(0)
        handler = getattr(self, "_" + cmd.replace(".", "_"), None)
        if handler is None:
            return {}
        result: dict[str, Any] = handler(**args)
        return normalize(cmd, result)

    def _job(self, kind: str, meta: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        now = time.time()
        job: dict[str, Any] = {
            "job": secrets.token_hex(6),
            "kind": kind,
            "state": "succeeded",
            "step": "done",
            "progress": 1.0,
            "message": "simulado",
            "error_code": None,
            "started_at": now,
            "finished_at": now,
            "meta": meta,
            "result": result,
        }
        self.jobs[job["job"]] = job
        return job

    def _latest(self, kind: str) -> dict[str, Any] | None:
        found = [j for j in self.jobs.values() if j["kind"] == kind]
        return found[-1] if found else None

    def _unit(self, unit: str, active: bool) -> dict[str, Any]:
        return {
            "unit": unit,
            "load": "loaded",
            "active": "active" if active else "inactive",
            "sub": "running" if active else "dead",
            "enabled": "enabled" if active else "disabled",
            "pid": 4242 if active else None,
            "restarts": 0,
            "result": "success",
            "since": int(self.started_at) if active else None,
        }

    # ---------------------------------------------------------------- comandos simulados

    def _ping(self) -> dict[str, Any]:
        return {"version": "fake", "mode": self.mode}

    def _mosquitto_account_set(self, username: str, password: str) -> dict[str, Any]:
        self.accounts[username] = password
        return {}

    def _mosquitto_account_delete(self, username: str) -> dict[str, Any]:
        self.accounts.pop(username, None)
        return {}

    def _mosquitto_account_list(self) -> dict[str, Any]:
        return {"accounts": [{"username": u} for u in sorted(self.accounts)]}

    def _mosquitto_acl_write(self, **kw: Any) -> dict[str, Any]:
        self.acl = kw
        return {}

    def _mosquitto_status(self) -> dict[str, Any]:
        result = self._unit("mosquitto.service", True)
        result["accounts"] = sorted(self.accounts)
        result["acl_present"] = bool(self.acl)
        return result

    def _cloudflared_set_token(self, token: str) -> dict[str, Any]:
        self.tunnel_token = token
        return {}

    def _cloudflared_enable(self) -> dict[str, Any]:
        if self.tunnel_token is None:
            raise PrivError("command_failed", "no hay token configurado (cloudflared.set_token)")
        self.cloudflared_enabled = True
        return {"enabled": True}

    def _cloudflared_disable(self, forget_token: bool = False) -> dict[str, Any]:
        self.cloudflared_enabled = False
        removed = forget_token and self.tunnel_token is not None
        if forget_token:
            self.tunnel_token = None
        return {"enabled": False, "token_removed": removed}

    def _cloudflared_restart(self) -> dict[str, Any]:
        if self.tunnel_token is None:
            raise PrivError("command_failed", "no hay token configurado (cloudflared.set_token)")
        return {"queued": True}

    def _cloudflared_status(self) -> dict[str, Any]:
        result = self._unit("meshbox-cloudflared.service", self.cloudflared_enabled)
        result["token_configured"] = self.tunnel_token is not None
        return result

    def _wifi_status(self) -> dict[str, Any]:
        return {
            "device": "wlan0",
            "state": "connected",
            "connection": "meshbox-hotspot" if self.hotspot else self.ssid,
            "ssid": "meshbox-0000" if self.hotspot else self.ssid,
            "signal": None if self.hotspot else 72,
            "ip4": ["10.42.0.1/24"] if self.hotspot else ["192.168.0.10/24"],
            "hotspot": self.hotspot,
            "saved": [{"ssid": self.ssid, "name": self.ssid, "uuid": "0" * 8}],
            "job": self._latest("wifi"),
        }

    def _wifi_scan(self, rescan: bool = True) -> dict[str, Any]:
        networks = [
            {"ssid": "Casa", "bssid": "AA:BB:CC:00:00:01", "signal": 72, "security": "WPA2",
             "channel": 6, "freq_mhz": 2437, "in_use": self.ssid == "Casa"},
            {"ssid": "Vecino", "bssid": "AA:BB:CC:00:00:02", "signal": 40, "security": "WPA2",
             "channel": 11, "freq_mhz": 2462, "in_use": self.ssid == "Vecino"},
        ]  # fmt: skip
        return {"networks": networks, "cached": False, "scanned_at": time.time()}

    def _wifi_connect(self, ssid: str, psk: str) -> dict[str, Any]:
        self.ssid = ssid
        self.hotspot = False
        job = self._job("wifi", {"ssid": ssid}, {"ssid": ssid, "ip4": ["192.168.0.10/24"]})
        return {"job": job["job"], "state": "running"}

    def _wifi_forget(self, ssid: str, force: bool = False) -> dict[str, Any]:
        return {"ssid": ssid, "deleted": 1}

    def _hotspot_start(self) -> dict[str, Any]:
        self.hotspot = True
        return {"ssid": "meshbox-0000", "address": "10.42.0.1", "password_source": "generated"}

    def _hotspot_stop(self) -> dict[str, Any]:
        self.hotspot = False
        return {"stopped": True, "reconnected": True}

    def _system_hostname(self, name: str) -> dict[str, Any]:
        self.hostname = name
        return {"hostname": name}

    def _system_timezone(self, tz: str) -> dict[str, Any]:
        self.timezone = tz
        return {"timezone": tz}

    def _power(self, action: str) -> dict[str, Any]:
        job = self._job("power", {"action": action}, {"action": action})
        return {"scheduled": True, "action": action, "delay_s": 3, "job": job["job"]}

    def _system_reboot(self) -> dict[str, Any]:
        return self._power("reboot")

    def _system_shutdown(self) -> dict[str, Any]:
        return self._power("poweroff")

    def _system_info(self) -> dict[str, Any]:
        return {
            "hostname": self.hostname,
            "mode": self.mode,
            "kernel": sys.platform,
            "arch": "x86_64",
            "model": "PC de desarrollo",
            "uptime_s": round(time.monotonic(), 1),
            "os": None,
            "python": sys.version.split()[0],
            "privd_version": "fake",
        }

    def _service_restart(self, name: str) -> dict[str, Any]:
        return {"name": name, "unit": f"{name}.service", "queued": True}

    def _service_status(self, name: str) -> dict[str, Any]:
        active = name != "meshbox-cloudflared" or self.cloudflared_enabled
        result = self._unit(f"{name}.service", active)
        result["name"] = name
        return result

    def _logs_read(self, unit: str, lines: int = 200, since: str | None = None) -> dict[str, Any]:
        from .logs import RING

        entries = [
            {
                "ts": e.get("ts"),
                "priority": 6,
                "message": orjson.dumps(e).decode(),
                "pid": None,
                "identifier": "meshbox",
            }
            for e in RING.tail(lines)
        ]
        return {"unit": f"{unit}.service", "entries": entries}

    def _time_status(self) -> dict[str, Any]:
        return {
            "timezone": self.timezone,
            "ntp": True,
            "ntp_synchronized": True,
            "can_ntp": True,
            "local_rtc": False,
            "time": time.strftime("%a %Y-%m-%d %H:%M:%S %Z"),
        }

    def _update_apply(self, version: str) -> dict[str, Any]:
        if version == self.current:
            raise PrivError("command_failed", f"la versión {version} ya está instalada")
        previous, self.current = self.current, version
        if version not in self.installed:
            self.installed.append(version)
        job = self._job(
            "update",
            {"action": "apply", "version": version, "from": previous},
            {"version": version, "previous": previous},
        )
        return {"job": job["job"], "state": "running"}

    def _update_status(self, job: str) -> dict[str, Any]:
        found = self.jobs.get(job)
        if found is None:
            raise PrivError("invalid_args", "trabajo desconocido")
        return found

    def _update_rollback(self, version: str | None = None) -> dict[str, Any]:
        others = [v for v in self.installed if v != self.current]
        target = version or (others[-1] if others else None)
        if target is None:
            raise PrivError("command_failed", "no hay una versión anterior instalada")
        previous, self.current = self.current, target
        job = self._job(
            "update",
            {"action": "rollback", "version": target, "from": previous},
            {"version": target, "previous": previous, "db_restored": True},
        )
        return {"job": job["job"], "state": "running"}

    def _update_info(self) -> dict[str, Any]:
        others = [v for v in self.installed if v != self.current]
        return {
            "current": self.current,
            "installed": sorted(self.installed),
            "previous": others[-1] if others else None,
            "last_update": None,
            "job": self._latest("update"),
            "updates_base_url": None,
        }


def make_privclient(kind: str, socket_path: Path, mode: str) -> PrivClient | FakePrivClient:
    if kind == "fake" or (kind == "auto" and (sys.platform == "win32" or not socket_path.exists())):
        if kind == "auto" and sys.platform != "win32":
            log.warning("no existe %s: se usa privd simulado", socket_path)
        return FakePrivClient(mode)
    return PrivClient(socket_path)
