"""Asistente de primer uso (secciones 18.1, 13.2 y 24.3).

Sin sesión solo mientras no exista ningún usuario, con el código de configuración
(`X-Setup-Code`) y como máximo 60 min desde el arranque. En modo punto de acceso no se pide
el código: la contraseña del punto de acceso ya limita quién llega. Creado el administrador,
el resto de los pasos se hace con su sesión.
"""

from __future__ import annotations

import hmac
import time
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from starlette.responses import RedirectResponse, Response

from ...auth.passwords import MIN_LENGTH
from ...auth.sessions import COOKIE, SessionInfo, csrf_ok
from ...auth.users import count_users, create_user
from ...config import MqttConnectorCfg, SerialConnectorCfg
from ...integrations.mosquitto import MosquittoAdmin, heltec_commands, lan_ip
from ...settings import SITE_KEY, put_setting
from ...system.privclient import PrivError
from ..deps import audit, get_ctx, ip_of
from ..http import JSON, NO_STORE, ProblemError

router = APIRouter(prefix="/api/v1/setup", tags=["asistente de primer uso"])
portal = APIRouter(tags=["portal cautivo"], include_in_schema=False)
STATE_KEY = "setup.state"
STEPS = [
    "wifi",
    "code",
    "locale",
    "admin",
    "site",
    "radio",
    "channel",
    "privacy",
    "tiles",
    "cloudflare",
    "finish",
]


async def _hotspot_active(ctx: Any) -> bool:
    if ctx.cfg.host.mode != "appliance":
        return False
    cached = ctx.extensions.get("hotspot_cache")
    now = time.time()
    if cached and now - cached[0] < 15:
        return bool(cached[1])
    try:
        st = await ctx.priv.call("wifi.status")
        active = bool(st.get("hotspot"))
    except PrivError:
        active = False
    ctx.extensions["hotspot_cache"] = (now, active)
    return active


class Access:
    def __init__(self, session: SessionInfo | None, users: int, via: str) -> None:
        self.session = session
        self.users = users
        self.via = via  # "session" | "code" | "hotspot"


async def setup_access(
    request: Request, *, allow_without_users: bool = True, code_override: str | None = None
) -> Access:
    ctx = get_ctx(request)
    users = await ctx.db.read(count_users)
    auth = ctx.extensions["auth"]
    session = await auth.sessions.get(request.cookies.get(COOKIE))
    if session is not None:
        if session.role != "admin":
            raise ProblemError(403, "Solo administradores")
        if request.method != "GET" and not csrf_ok(session, request.headers.get("x-csrf-token")):
            raise ProblemError(403, "Falta o no coincide el token CSRF")
        return Access(session, users, "session")
    if users > 0 or not allow_without_users:
        raise ProblemError(401, "Iniciar sesión para continuar el asistente")
    if not ctx.setup_window_open():
        raise ProblemError(
            403,
            "El asistente sin usuario se cerró (60 min desde el arranque): reiniciar el equipo para reabrirlo",
        )
    if await _hotspot_active(ctx):
        return Access(None, users, "hotspot")
    code = ctx.secrets.data.setup_code
    given = (code_override or request.headers.get("x-setup-code") or "").strip().upper()
    if not code or not given or not hmac.compare_digest(code, given):
        wait = auth.login_guard.check(ip_of(request), "__setup__")
        if wait > 0:
            raise ProblemError(
                429, "Demasiados intentos", headers={"Retry-After": str(int(wait) + 1)}
            )
        if given:
            auth.login_guard.failure("__setup__", ip_of(request))
        raise ProblemError(
            401, "Código de configuración incorrecto o faltante", extra={"code_required": True}
        )
    return Access(None, users, "code")


async def _state(ctx: Any) -> dict[str, Any]:
    raw = ctx.state.settings.get(STATE_KEY)
    return dict(raw) if isinstance(raw, dict) else {"completed": [], "done": False}


async def _mark(ctx: Any, step: str, **extra: Any) -> dict[str, Any]:
    st = await _state(ctx)
    if step not in st["completed"]:
        st["completed"].append(step)
    st.update(extra)
    await put_setting(ctx.writer, ctx.state.settings, STATE_KEY, st)
    return st


@router.get("/state")
async def state(request: Request) -> Response:
    ctx = get_ctx(request)
    users = await ctx.db.read(count_users)
    st = await _state(ctx)
    hotspot = await _hotspot_active(ctx)
    # Mapa base y Cloudflare también se hacen desde el panel: cuentan como hechos si ya están.
    completed = list(st["completed"])
    tiles = ctx.extensions.get("tiles")
    if tiles is not None and tiles.available and "tiles" not in completed:
        completed.append("tiles")
    if ctx.cfg.cloudflare.mode != "none" and "cloudflare" not in completed:
        completed.append("cloudflare")
    return JSON(
        {
            "needs_setup": users == 0 or not st.get("done"),
            "users_exist": users > 0,
            "code_required": users == 0 and not hotspot,
            "window_open": ctx.setup_window_open(),
            "window_closes_at": ctx.started_at + 3600,
            "hotspot": hotspot,
            "mode": ctx.cfg.host.mode,
            "lan_ip": lan_ip(),
            "lan_bind": ctx.cfg.server.lan_bind,
            "steps": [s for s in STEPS if s != "wifi" or hotspot],
            "completed": completed,
            "done": bool(st.get("done")),
        },
        headers=NO_STORE,
    )


class CodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=12)


@router.post("/code")
async def check_code(request: Request, body: CodeIn) -> Response:
    access = await setup_access(request, code_override=body.code)
    return JSON({"ok": True, "via": access.via})


class WifiIn(BaseModel):
    ssid: str = Field(min_length=1, max_length=32)
    psk: str = Field(min_length=8, max_length=63)


@router.get("/wifi/scan")
async def wifi_scan(request: Request) -> Response:
    """Redes visibles para el paso 0 (punto de acceso), con el mismo acceso que el asistente."""
    access = await setup_access(request)
    ctx = get_ctx(request)
    if access.via != "hotspot" and ctx.cfg.host.mode != "appliance":
        raise ProblemError(409, "Este paso solo existe en modo punto de acceso")
    try:
        result = await ctx.priv.call("wifi.scan")
    except PrivError as e:
        raise ProblemError(502, e.message) from None
    return JSON(result, headers=NO_STORE)


@router.post("/wifi")
async def wifi(request: Request, body: WifiIn) -> Response:
    """Paso 0, solo en modo punto de acceso: conectarse a la red de la casa."""
    access = await setup_access(request)
    ctx = get_ctx(request)
    if access.via != "hotspot" and ctx.cfg.host.mode != "appliance":
        raise ProblemError(409, "Este paso solo existe en modo punto de acceso")
    try:
        result = await ctx.priv.call("wifi.connect", ssid=body.ssid, psk=body.psk)
    except PrivError as e:
        raise ProblemError(502, e.message) from None
    await _mark(ctx, "wifi")
    return JSON(
        {
            "ok": True,
            "result": result,
            "next": "Volver el celular a la red de la casa y abrir http://meshbox.local",
        }
    )


class LocaleIn(BaseModel):
    language: Literal["es", "en"] = "es"
    timezone: str = Field(
        "America/Argentina/Buenos_Aires", pattern=r"^[A-Za-z_]+(/[A-Za-z0-9_+-]+){0,2}$"
    )


@router.post("/locale")
async def locale(request: Request, body: LocaleIn) -> Response:
    await setup_access(request)
    ctx = get_ctx(request)
    ctx.cfg.site.language = body.language
    ctx.cfg.site.timezone = body.timezone
    ctx.save_config()
    if ctx.cfg.host.mode == "appliance":
        try:
            await ctx.priv.call("system.timezone", tz=body.timezone)
        except PrivError:
            pass
    site = ctx.site.model_dump()
    site["default_language"] = body.language
    await put_setting(ctx.writer, ctx.state.settings, SITE_KEY, site)
    await _mark(ctx, "locale")
    return JSON({"ok": True})


class AdminIn(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=MIN_LENGTH, max_length=256)


@router.post("/admin")
async def admin(request: Request, body: AdminIn) -> Response:
    access = await setup_access(request)
    ctx = get_ctx(request)
    if access.users > 0:
        raise ProblemError(409, "Ya existe un usuario administrador")
    try:
        uid = await create_user(ctx.writer, body.username, body.password, "admin")
    except ValueError as e:
        raise ProblemError(422, str(e)) from None
    # el código era de un solo uso
    ctx.secrets.data.setup_code = ""
    ctx.secrets.save()
    auth = ctx.extensions["auth"]
    token, info = await auth.sessions.create(
        uid,
        body.username.lower(),
        "admin",
        False,
        ip_of(request),
        request.headers.get("user-agent"),
    )
    audit(request, info, "setup.admin", body.username.lower())
    await _mark(ctx, "admin")
    from .auth import set_session_cookie

    response = JSON({**info.public(), "ok": True}, headers=NO_STORE)
    set_session_cookie(request, response, token)
    return response


class SiteIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    description: str = Field("", max_length=300)
    center: list[float] = Field(min_length=2, max_length=2)
    zoom: float = Field(11, ge=1, le=18)
    bounds: list[float] | None = None
    slug: str | None = Field(None, pattern=r"^[a-z0-9-]{2,32}$")


@router.post("/site")
async def site(request: Request, body: SiteIn) -> Response:
    access = await setup_access(request, allow_without_users=False)
    ctx = get_ctx(request)
    from ...settings import SiteSettings

    current = ctx.site.model_dump()
    current.update(
        name=body.name,
        description=body.description,
        center=body.center,
        zoom=body.zoom,
        bounds=body.bounds,
    )
    try:
        data = SiteSettings(**current).model_dump()
    except ValueError as e:
        raise ProblemError(422, str(e)) from None
    await put_setting(ctx.writer, ctx.state.settings, SITE_KEY, data)
    if body.slug:
        ctx.cfg.site.slug = body.slug
        ctx.save_config()
    audit(request, access.session, "setup.site", body.name)
    await _mark(ctx, "site")
    return JSON({"ok": True, "site": data})


class RadioIn(BaseModel):
    mqtt: bool = True
    gateway_name: str = Field("interior", pattern=r"^[a-z0-9][a-z0-9_-]{1,20}$")
    root: str | None = Field(None, pattern=r"^[A-Za-z0-9_/-]{3,64}$")
    usb: bool = False
    usb_port: str | None = Field(None, max_length=200)
    serial_port_hint: str = Field("COM5", max_length=40)


@router.post("/radio")
async def radio(request: Request, body: RadioIn) -> Response:
    access = await setup_access(request, allow_without_users=False)
    ctx = get_ctx(request)
    out: dict[str, Any] = {}
    if body.mqtt:
        root = body.root or ctx.cfg.mqtt_root or f"msh/AR/{ctx.cfg.site.slug}"
        topics = [f"{root}/2/e/#", f"{root}/2/map/#"]
        existing = next(
            (
                c
                for c in ctx.cfg.connectors
                if isinstance(c, MqttConnectorCfg) and c.host in ("127.0.0.1", "localhost")
            ),
            None,
        )
        if existing is None:
            ccfg = MqttConnectorCfg(
                id="mqtt-local",
                host="127.0.0.1",
                port=1883,
                username="meshbox-ingest",
                password_ref="mqtt.meshbox-ingest",  # noqa: S106 - referencia, no clave
                topics=topics,
            )
            ctx.cfg.connectors = [*ctx.cfg.connectors, ccfg]
        else:
            existing.topics = topics
            ccfg = existing
        ctx.save_config()
        mq = MosquittoAdmin(ctx)
        try:
            await mq.ensure_ingest()
            accounts = {a["username"] for a in await mq.accounts()}
            gw_user = f"gw-{body.gateway_name}"
            if gw_user in accounts:
                password = await mq.rotate(gw_user)
            else:
                gw_user, password = await mq.create(
                    body.gateway_name, "gateway", "creada por el asistente"
                )
            await mq.write_acl()
        except (PrivError, ValueError) as e:
            raise ProblemError(502, f"Mosquitto: {e}") from None
        await ctx.connectors.restart(ccfg.id)
        host = lan_ip()
        out["mqtt"] = {
            "username": gw_user,
            "password": password,
            "root": root,
            "heltec": heltec_commands(
                host=host,
                username=gw_user,
                password=password,
                root=root,
                port=body.serial_port_hint,
            ),
        }
    if body.usb:
        if not body.usb_port:
            raise ProblemError(422, "Elegir el puerto USB")
        scfg = SerialConnectorCfg(id="usb-heltec", port=body.usb_port, enabled=True)
        ctx.cfg.connectors = [c for c in ctx.cfg.connectors if c.id != scfg.id] + [scfg]
        ctx.save_config()
        await ctx.connectors.start_one(scfg)
        out["usb"] = {"connector": scfg.id, "port": body.usb_port}
    audit(request, access.session, "setup.radio", None, {"mqtt": body.mqtt, "usb": body.usb})
    await _mark(ctx, "radio", radio={"mqtt": body.mqtt, "usb": body.usb})
    return JSON(out, headers=NO_STORE)


class ChannelIn(BaseModel):
    name: str = Field("MediumFast", min_length=1, max_length=11)
    key: str = Field("AQ==", max_length=64)


@router.post("/channel")
async def channel(request: Request, body: ChannelIn) -> Response:
    access = await setup_access(request, allow_without_users=False)
    ctx = get_ctx(request)
    from sqlalchemy import text

    from ...pipeline.crypto import channel_hash, decode_psk

    try:
        h = channel_hash(body.name, decode_psk(body.key))
    except ValueError as e:
        raise ProblemError(422, str(e)) from None
    ref = f"channels.{body.name}"
    ctx.secrets.set(ref, body.key)

    def upsert(conn: Any) -> None:
        row = conn.execute(
            text("SELECT id FROM channels WHERE name = :n"), {"n": body.name}
        ).first()
        if row:
            conn.execute(
                text("UPDATE channels SET hash = :h, key_ref = :r, is_public = 1 WHERE id = :i"),
                {"h": h, "r": ref, "i": row[0]},
            )
        else:
            conn.execute(
                text(
                    "INSERT INTO channels (name, hash, key_ref, is_public) VALUES (:n, :h, :r, 1)"
                ),
                {"n": body.name, "h": h, "r": ref},
            )

    await ctx.writer.run(upsert)
    await ctx.db.read(lambda c: ctx.state.load_channels(c, ctx.secrets.get))
    audit(request, access.session, "setup.channel", body.name)
    await _mark(ctx, "channel")
    return JSON({"ok": True, "name": body.name, "hash": h})


class PrivacyIn(BaseModel):
    ignore_via_mqtt: bool = True
    position_policy: Literal["as_received", "degrade"] = "as_received"
    degrade_meters: int = Field(500, ge=50, le=50_000)
    notice_md: str | None = Field(None, max_length=20_000)


@router.post("/privacy")
async def privacy(request: Request, body: PrivacyIn) -> Response:
    access = await setup_access(request, allow_without_users=False)
    ctx = get_ctx(request)
    ctx.cfg.privacy.ignore_via_mqtt = body.ignore_via_mqtt
    ctx.cfg.privacy.position_policy = body.position_policy
    ctx.cfg.privacy.degrade_meters = body.degrade_meters
    ctx.save_config()
    if body.notice_md:
        site = ctx.site.model_dump()
        site["notice_md"] = body.notice_md
        await put_setting(ctx.writer, ctx.state.settings, SITE_KEY, site)
    audit(request, access.session, "setup.privacy", None, body.model_dump(exclude={"notice_md"}))
    await _mark(ctx, "privacy")
    return JSON({"ok": True})


@router.post("/skip/{step}")
async def skip(request: Request, step: Literal["tiles", "cloudflare"]) -> Response:
    await setup_access(request, allow_without_users=False)
    await _mark(get_ctx(request), step, **{f"{step}_skipped": True})
    return JSON({"ok": True})


@router.get("/verify")
async def verify(request: Request) -> Response:
    """Resumen y verificación: llega al menos un paquete y el sitio responde (paso 10)."""
    await setup_access(request, allow_without_users=False)
    ctx = get_ctx(request)
    last = ctx.state.last_packet_at
    return JSON(
        {
            "packets_total": ctx.state.packets_total,
            "last_packet_at": last,
            "packet_received": bool(last and time.time() - last < 3600),
            "connectors": ctx.connectors.statuses(),
            "nodes": len(ctx.state.nodes),
            "public_channels": ctx.state.public_channel_names(),
            "site_ok": ctx.ready,
            "tiles": ctx.extensions["tiles"].available if ctx.extensions.get("tiles") else False,
        },
        headers=NO_STORE,
    )


@router.post("/finish")
async def finish(request: Request) -> Response:
    access = await setup_access(request, allow_without_users=False)
    ctx = get_ctx(request)
    st = await _mark(ctx, "finish", done=True, finished_at=time.time())
    audit(request, access.session, "setup.finish")
    return JSON({"ok": True, "state": st})


# --------------------------------------------------------------------------- portal cautivo (24.3)

DETECTION_PATHS = (
    "/generate_204",
    "/gen_204",
    "/hotspot-detect.html",
    "/library/test/success.html",
    "/connecttest.txt",
    "/ncsi.txt",
    "/redirect",
    "/canonical.html",
    "/success.txt",
)


async def _captive(request: Request) -> Response:
    ctx = get_ctx(request)
    if await _hotspot_active(ctx):
        return RedirectResponse("http://10.42.0.1/setup", status_code=302)
    raise ProblemError(404)


for _path in DETECTION_PATHS:
    portal.add_api_route(_path, _captive, methods=["GET"])
