"""Cloudflare: modo token, modo API y administración remota con Access (sección 15)."""

from __future__ import annotations

import re
import time
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from starlette.responses import Response

from ...auth.sessions import SessionInfo
from ...integrations.cloudflare import CloudflareAPI, CloudflareError
from ...system.privclient import PrivError
from ..deps import audit, get_ctx, require_admin
from ..http import JSON, NO_STORE, ProblemError

router = APIRouter(prefix="/api/v1/admin/cloudflare", tags=["administración: Cloudflare"])
TOKEN_RE = re.compile(r"^[A-Za-z0-9_\-=.]{50,4096}$")
HOST_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def _api(ctx: Any) -> CloudflareAPI:
    token = ctx.secrets.data.cloudflare.api_token
    if not token:
        raise ProblemError(409, "Falta el token de API de Cloudflare")
    return CloudflareAPI(token)


def _cf_error(e: CloudflareError) -> ProblemError:
    return ProblemError(
        409 if e.status == 409 else 502, str(e), extra={"cloudflare_errors": e.errors}
    )


async def _probe_site(hostname: str) -> dict[str, Any]:
    if not hostname:
        return {"ok": None}
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            r = await client.get(f"https://{hostname}/api/v1/health")
        return {"ok": r.status_code == 200, "status": r.status_code, "checked_at": time.time()}
    except httpx.HTTPError as e:
        return {"ok": False, "error": type(e).__name__, "checked_at": time.time()}


@router.get("/status")
async def status(
    request: Request, probe: bool = False, _: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    cf = ctx.cfg.cloudflare
    try:
        service = await ctx.priv.call("cloudflared.status")
    except PrivError as e:
        service = {"active": None, "error": e.message}
    tunnel = None
    if (
        cf.mode == "api"
        and cf.account_id
        and cf.tunnel_id
        and ctx.secrets.data.cloudflare.api_token
    ):
        try:
            async with _api(ctx) as api:
                tunnel = await api.tunnel(cf.account_id, cf.tunnel_id)
        except CloudflareError as e:
            tunnel = {"error": str(e)}
    site = await _probe_site(cf.public_hostname) if probe else None
    return JSON(
        {
            "mode": cf.mode,
            "public_hostname": cf.public_hostname,
            "admin_hostname": cf.admin_hostname,
            "service": service,
            "tunnel": tunnel,
            "site_check": site,
            "has_api_token": bool(ctx.secrets.data.cloudflare.api_token),
            "access": {"team_domain": cf.access_team_domain, "configured": bool(cf.access_aud)},
            "public_target": f"http://{ctx.cfg.server.public_bind}",
            "admin_target": f"http://{ctx.cfg.server.admin_remote_bind}",
        },
        headers=NO_STORE,
    )


class TokenIn(BaseModel):
    token: str = Field(min_length=50, max_length=4096)
    public_hostname: str = Field("", max_length=253)


@router.post("/token")
async def token_mode(
    request: Request, body: TokenIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    """Modo token (15.1): el túnel se crea en el panel de Cloudflare y acá se pega su token."""
    ctx = get_ctx(request)
    token = body.token.strip()
    if not TOKEN_RE.match(token):
        raise ProblemError(422, "El token del túnel no tiene un formato válido")
    if body.public_hostname and not HOST_RE.match(body.public_hostname.lower()):
        raise ProblemError(422, "Nombre de host no válido")
    try:
        await ctx.priv.call("cloudflared.set_token", token=token)
        st = await ctx.priv.call("cloudflared.enable")
    except PrivError as e:
        raise ProblemError(502, f"privd: {e.message}") from None
    ctx.cfg.cloudflare.mode = "token"
    ctx.cfg.cloudflare.public_hostname = body.public_hostname.lower()
    ctx.save_config()
    audit(request, info, "cloudflare.token", body.public_hostname)
    return JSON(
        {
            "ok": True,
            "service": st,
            "hint": f"En Cloudflare, el hostname público debe apuntar a http://{ctx.cfg.server.public_bind}",
        }
    )


class ApiTokenIn(BaseModel):
    api_token: str = Field(min_length=20, max_length=200)
    account_id: str | None = Field(None, pattern=r"^[0-9a-f]{32}$")


@router.post("/api/verify")
async def api_verify(
    request: Request, body: ApiTokenIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    try:
        async with CloudflareAPI(body.api_token.strip()) as api:
            verified = await api.verify(body.account_id)
            zones = await api.zones()
    except CloudflareError as e:
        raise _cf_error(e) from None
    ctx.secrets.data.cloudflare.api_token = body.api_token.strip()
    ctx.secrets.save()
    audit(
        request,
        info,
        "cloudflare.api.verify",
        None,
        {"status": verified.get("status"), "zones": len(zones)},
    )
    return JSON(
        {
            "token": {
                "status": verified.get("status"),
                "kind": verified.get("kind"),
                "expires_on": verified.get("expires_on"),
            },
            "zones": zones,
        }
    )


@router.get("/api/zones")
async def api_zones(request: Request, _: SessionInfo = Depends(require_admin)) -> Response:
    ctx = get_ctx(request)
    try:
        async with _api(ctx) as api:
            return JSON({"zones": await api.zones()}, headers=NO_STORE)
    except CloudflareError as e:
        raise _cf_error(e) from None


class ProvisionIn(BaseModel):
    zone_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    public_hostname: str
    admin_hostname: str = ""
    replace_dns: bool = False


@router.post("/api/provision")
async def provision(
    request: Request, body: ProvisionIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    """Modo API (15.2): túnel, reglas, DNS, token por privd, servicio y verificación."""
    ctx = get_ctx(request)
    host = body.public_hostname.lower().strip()
    admin_host = body.admin_hostname.lower().strip()
    for h in filter(None, (host, admin_host)):
        if not HOST_RE.match(h):
            raise ProblemError(422, f"Nombre de host no válido: {h}")
    steps: list[dict[str, Any]] = []
    try:
        async with _api(ctx) as api:
            zone = next((z for z in await api.zones() if z["id"] == body.zone_id), None)
            if zone is None:
                raise ProblemError(404, "Zona no encontrada para este token")
            if not (host == zone["name"] or host.endswith("." + zone["name"])):
                raise ProblemError(422, f"{host} no pertenece a la zona {zone['name']}")
            account = zone["account_id"]
            name = f"meshbox-{ctx.cfg.site.slug}"
            tunnel = await api.find_tunnel(account, name)
            if tunnel is None:
                created = await api.create_tunnel(account, name)
                tunnel_id, token = created["id"], created.get("token")
                steps.append({"step": "túnel creado", "id": tunnel_id})
            else:
                tunnel_id, token = tunnel["id"], None
                steps.append({"step": "túnel existente reutilizado", "id": tunnel_id})
            if not token:
                token = await api.tunnel_token(account, tunnel_id)
            rules = [{"hostname": host, "service": f"http://{ctx.cfg.server.public_bind}"}]
            if admin_host:
                rules.append(
                    {
                        "hostname": admin_host,
                        "service": f"http://{ctx.cfg.server.admin_remote_bind}",
                    }
                )
            await api.put_ingress(account, tunnel_id, rules)
            steps.append({"step": "reglas configuradas", "rules": rules})
            for h in filter(None, (host, admin_host)):
                await api.upsert_cname(body.zone_id, h, tunnel_id, body.replace_dns)
                steps.append({"step": "DNS", "hostname": h})
            await ctx.priv.call("cloudflared.set_token", token=token)
            await ctx.priv.call("cloudflared.enable")
            steps.append({"step": "servicio cloudflared habilitado"})
            ctx.cfg.cloudflare.mode = "api"
            ctx.cfg.cloudflare.public_hostname = host
            ctx.cfg.cloudflare.admin_hostname = admin_host
            ctx.cfg.cloudflare.account_id = account
            ctx.cfg.cloudflare.zone_id = body.zone_id
            ctx.cfg.cloudflare.tunnel_id = tunnel_id
            ctx.save_config()
            health = await api.wait_healthy(account, tunnel_id, max_wait_s=60)
            steps.append({"step": "estado del túnel", "status": health.get("status")})
    except CloudflareError as e:
        audit(request, info, "cloudflare.provision_failed", host, {"error": str(e), "steps": steps})
        raise _cf_error(e) from None
    except PrivError as e:
        raise ProblemError(502, f"privd: {e.message}", extra={"steps": steps}) from None
    site = await _probe_site(host)
    audit(
        request,
        info,
        "cloudflare.provision",
        host,
        {"tunnel_id": tunnel_id, "admin": admin_host or None},
    )
    return JSON(
        {
            "ok": True,
            "steps": steps,
            "site_check": site,
            "restart_needed_for_admin": bool(admin_host),
        }
    )


class AccessIn(BaseModel):
    emails: list[str] = Field(min_length=1, max_length=20)


@router.post("/access")
async def access(
    request: Request, body: AccessIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    """Administración remota (15.3): aplicación Access self-hosted para el hostname de administración."""
    ctx = get_ctx(request)
    cf = ctx.cfg.cloudflare
    if not (cf.admin_hostname and cf.account_id):
        raise ProblemError(409, "Primero configurar el hostname de administración (modo API)")
    for e in body.emails:
        if not re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,253}\.[a-z]{2,}", e, re.I):
            raise ProblemError(422, f"correo no válido: {e}")
    try:
        async with _api(ctx) as api:
            team = await api.access_team_domain(cf.account_id)
            app = await api.create_access_app(cf.account_id, cf.admin_hostname, body.emails)
    except CloudflareError as e:
        raise _cf_error(e) from None
    cf.access_team_domain, cf.access_aud, cf.access_app_id = team, app.get("aud") or "", app["id"]
    ctx.save_config()
    auth = ctx.extensions.get("auth")
    if auth is not None:
        auth.reload_access()
    audit(request, info, "cloudflare.access", cf.admin_hostname, {"emails": len(body.emails)})
    return JSON(
        {
            "ok": True,
            "team_domain": team,
            "aud": cf.access_aud,
            "note": "Reiniciar meshbox para levantar el servidor de administración remota.",
        }
    )


class DisconnectIn(BaseModel):
    confirm: bool = False
    delete_dns: bool = False
    delete_tunnel: bool = False


@router.post("/disconnect")
async def disconnect(
    request: Request, body: DisconnectIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    if not body.confirm:
        raise ProblemError(400, "Confirmar la desconexión (el sitio deja de estar publicado)")
    cf = ctx.cfg.cloudflare
    done: list[str] = []
    try:
        # El token del túnel no queda en el disco una vez desconectado.
        await ctx.priv.call("cloudflared.disable", forget_token=True)
        done.append("servicio detenido")
    except PrivError as e:
        done.append(f"servicio: {e.message}")
    if (
        cf.mode == "api"
        and ctx.secrets.data.cloudflare.api_token
        and (body.delete_dns or body.delete_tunnel)
    ):
        try:
            async with _api(ctx) as api:
                if body.delete_dns:
                    for h in filter(None, (cf.public_hostname, cf.admin_hostname)):
                        if await api.delete_dns(cf.zone_id, h):
                            done.append(f"DNS {h} borrado")
                if cf.access_app_id:
                    await api.delete_access_app(cf.account_id, cf.access_app_id)
                    done.append("aplicación Access borrada")
                if body.delete_tunnel and cf.tunnel_id:
                    await api.delete_tunnel(cf.account_id, cf.tunnel_id)
                    done.append("túnel borrado")
        except CloudflareError as e:
            done.append(f"Cloudflare: {e}")
    if body.delete_tunnel:
        cf.tunnel_id = ""
    cf.mode = "none"
    cf.access_aud = cf.access_app_id = ""
    ctx.save_config()
    audit(request, info, "cloudflare.disconnect", cf.public_hostname, {"done": done})
    return JSON({"ok": True, "done": done})
