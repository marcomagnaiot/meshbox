"""Cliente de la API de Cloudflare (secciones 15.2 y 15.3).

Aislado en un módulo (riesgo "cambios en la API de Cloudflare", sección 33) y probado con
respuestas simuladas (`respx`). Permisos que necesita el token:
Cuenta → Cloudflare Tunnel → Edit; Zona → DNS → Edit; Zona → Zone → Read; y para la
administración remota, Cuenta → Access: Apps and Policies → Edit.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

log = logging.getLogger(__name__)
BASE = "https://api.cloudflare.com/client/v4"


class CloudflareError(Exception):
    def __init__(
        self, message: str, status: int = 0, errors: list[dict[str, Any]] | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.errors = errors or []


class CloudflareAPI:
    def __init__(
        self, token: str, client: httpx.AsyncClient | None = None, timeout: float = 20
    ) -> None:
        self.token = token
        self._client = client
        self.timeout = timeout

    async def __aenter__(self) -> CloudflareAPI:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
            self._own = True
        return self

    async def __aexit__(self, *exc: object) -> None:
        if getattr(self, "_own", False) and self._client is not None:
            await self._client.aclose()

    async def _req(self, method: str, path: str, **kw: Any) -> Any:
        assert self._client is not None, "usar `async with CloudflareAPI(...)`"
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        try:
            r = await self._client.request(method, BASE + path, headers=headers, **kw)
        except httpx.HTTPError as e:
            raise CloudflareError(f"no se pudo contactar a Cloudflare: {e}") from e
        try:
            body = r.json()
        except ValueError:
            raise CloudflareError(
                f"respuesta inesperada de Cloudflare ({r.status_code})", r.status_code
            ) from None
        if r.status_code >= 400 or not body.get("success", False):
            errors = body.get("errors") or []
            msg = (
                "; ".join(f"{e.get('code')}: {e.get('message')}" for e in errors)
                or f"HTTP {r.status_code}"
            )
            raise CloudflareError(msg, r.status_code, errors)
        return body.get("result")

    # ---------------------------------------------------------------- token y zonas

    async def verify(self, account_id: str | None = None) -> dict[str, Any]:
        """Token de usuario (`/user/tokens/verify`) o de cuenta (`/accounts/{id}/tokens/verify`)."""
        try:
            result = await self._req("GET", "/user/tokens/verify")
            return {"kind": "user", **(result or {})}
        except CloudflareError:
            if not account_id:
                raise
        result = await self._req("GET", f"/accounts/{account_id}/tokens/verify")
        return {"kind": "account", **(result or {})}

    async def zones(self) -> list[dict[str, Any]]:
        result = await self._req("GET", "/zones", params={"per_page": 50, "status": "active"})
        return [
            {
                "id": z["id"],
                "name": z["name"],
                "account_id": z["account"]["id"],
                "account_name": z["account"].get("name"),
            }
            for z in result or []
        ]

    # ---------------------------------------------------------------- túnel

    async def create_tunnel(self, account_id: str, name: str) -> dict[str, Any]:
        result = await self._req(
            "POST",
            f"/accounts/{account_id}/cfd_tunnel",
            json={"name": name, "config_src": "cloudflare"},
        )
        return {"id": result["id"], "token": result.get("token"), "name": result.get("name")}

    async def find_tunnel(self, account_id: str, name: str) -> dict[str, Any] | None:
        result = await self._req(
            "GET",
            f"/accounts/{account_id}/cfd_tunnel",
            params={"name": name, "is_deleted": "false"},
        )
        return result[0] if result else None

    async def tunnel_token(self, account_id: str, tunnel_id: str) -> str:
        result = await self._req("GET", f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/token")
        return str(result)

    async def put_ingress(
        self, account_id: str, tunnel_id: str, rules: list[dict[str, str]]
    ) -> None:
        ingress = [*rules, {"service": "http_status:404"}]
        await self._req(
            "PUT",
            f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations",
            json={"config": {"ingress": ingress}},
        )

    async def tunnel(self, account_id: str, tunnel_id: str) -> dict[str, Any]:
        result = await self._req("GET", f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}")
        return {
            "id": result.get("id"),
            "name": result.get("name"),
            "status": result.get("status"),
            "connections": len(result.get("connections") or []),
        }

    async def wait_healthy(
        self, account_id: str, tunnel_id: str, max_wait_s: float = 60
    ) -> dict[str, Any]:
        deadline = time.monotonic() + max_wait_s
        last: dict[str, Any] = {}
        while time.monotonic() < deadline:
            last = await self.tunnel(account_id, tunnel_id)
            if last.get("status") == "healthy":
                return last
            await asyncio.sleep(3)
        return last

    async def delete_tunnel(self, account_id: str, tunnel_id: str) -> None:
        await self._req("DELETE", f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}")

    # ---------------------------------------------------------------- DNS

    async def find_dns(self, zone_id: str, name: str) -> dict[str, Any] | None:
        result = await self._req("GET", f"/zones/{zone_id}/dns_records", params={"name": name})
        return result[0] if result else None

    async def upsert_cname(
        self, zone_id: str, name: str, tunnel_id: str, replace: bool
    ) -> dict[str, Any]:
        content = f"{tunnel_id}.cfargotunnel.com"
        record = {
            "type": "CNAME",
            "name": name,
            "content": content,
            "proxied": True,
            "comment": "meshbox (Cloudflare Tunnel)",
        }
        existing = await self.find_dns(zone_id, name)
        if existing is None:
            return await self._req("POST", f"/zones/{zone_id}/dns_records", json=record)  # type: ignore[no-any-return]
        if existing.get("content") == content and existing.get("type") == "CNAME":
            return existing
        if not replace:
            raise CloudflareError(
                f"ya existe un registro {existing.get('type')} para {name}; confirmar para reemplazarlo",
                409,
            )
        return await self._req("PUT", f"/zones/{zone_id}/dns_records/{existing['id']}", json=record)  # type: ignore[no-any-return]

    async def delete_dns(self, zone_id: str, name: str) -> bool:
        existing = await self.find_dns(zone_id, name)
        if existing is None:
            return False
        await self._req("DELETE", f"/zones/{zone_id}/dns_records/{existing['id']}")
        return True

    # ---------------------------------------------------------------- Access

    async def access_team_domain(self, account_id: str) -> str:
        result = await self._req("GET", f"/accounts/{account_id}/access/organizations")
        return str(result.get("auth_domain", ""))

    async def create_access_app(
        self, account_id: str, hostname: str, emails: list[str]
    ) -> dict[str, Any]:
        app = await self._req(
            "POST",
            f"/accounts/{account_id}/access/apps",
            json={
                "name": f"meshbox admin ({hostname})",
                "domain": hostname,
                "type": "self_hosted",
                "session_duration": "24h",
                "app_launcher_visible": False,
                "policies": [
                    {
                        "name": "meshbox administradores",
                        "decision": "allow",
                        "include": [{"email": {"email": e}} for e in emails],
                    }
                ],
            },
        )
        return {"id": app["id"], "aud": app.get("aud"), "domain": app.get("domain")}

    async def delete_access_app(self, account_id: str, app_id: str) -> None:
        await self._req("DELETE", f"/accounts/{account_id}/access/apps/{app_id}")
