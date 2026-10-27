"""Conectores de radio (secciones 9, 12.4 y 18.2 "Radio").

Los conectores se definen solo en `config.toml`: el panel lo reescribe y reinicia el
conector afectado (sección 8). Las contraseñas MQTT son de solo escritura.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from starlette.responses import Response

from ...auth.sessions import SessionInfo
from ...config import (
    ID_RE,
    SECRET_MASK,
    MqttConnectorCfg,
    ReplayConnectorCfg,
    SerialConnectorCfg,
    TcpConnectorCfg,
)
from ..deps import audit, get_ctx, require_admin, require_operator
from ..http import JSON, NO_STORE, ProblemError

router = APIRouter(prefix="/api/v1/admin/connectors", tags=["administración: radio"])


class MqttIn(BaseModel):
    kind: Literal["mqtt"]
    id: str
    enabled: bool = True
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(1883, ge=1, le=65535)
    username: str | None = Field(None, max_length=64)
    password: str | None = Field(
        None, max_length=256, description="solo escritura; '********' = sin cambios"
    )
    topics: list[str] = Field(default_factory=list, max_length=10)
    tls: bool = False


class SerialIn(BaseModel):
    kind: Literal["serial"]
    id: str
    enabled: bool = True
    port: str = Field(min_length=1, max_length=200)


class TcpIn(BaseModel):
    kind: Literal["tcp"]
    id: str
    enabled: bool = True
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(4403, ge=1, le=65535)


class ReplayIn(BaseModel):
    kind: Literal["replay"]
    id: str
    enabled: bool = True
    file: str = Field(min_length=1, max_length=500)
    speed: float = Field(1.0, ge=0, le=1000)
    loop: bool = False


ConnectorIn = Annotated[MqttIn | SerialIn | TcpIn | ReplayIn, Field(discriminator="kind")]


def _public(ctx: Any, ccfg: Any) -> dict[str, Any]:
    d = ccfg.model_dump(mode="json")
    if isinstance(ccfg, MqttConnectorCfg):
        d.pop("password_ref", None)
        d["password"] = SECRET_MASK if ctx.secrets.get(ccfg.password_ref) else ""
    conn = ctx.connectors.get(ccfg.id)
    d["status"] = conn.status().as_dict() if conn is not None else {"state": "stopped"}
    out: dict[str, Any] = d
    return out


def _build(ctx: Any, body: Any, existing: Any = None) -> Any:
    if not ID_RE.match(body.id):
        raise ProblemError(422, "id no válido (minúsculas, números, - y _; 2 a 32)")
    if isinstance(body, MqttIn):
        for t in body.topics:
            if not t or len(t) > 200 or "\x00" in t:
                raise ProblemError(422, f"tópico no válido: {t!r}")
        ref = (
            existing.password_ref
            if isinstance(existing, MqttConnectorCfg) and existing.password_ref
            else None
        )
        if body.password and body.password != SECRET_MASK:
            ref = f"mqtt.{body.username or body.id}"
            ctx.secrets.set(ref, body.password)
        topics = body.topics or [f"{ctx.cfg.mqtt_root or 'msh/AR/' + ctx.cfg.site.slug}/2/e/#"]
        return MqttConnectorCfg(
            id=body.id,
            enabled=body.enabled,
            host=body.host,
            port=body.port,
            username=body.username or None,
            password_ref=ref,
            topics=topics,
            tls=body.tls,
        )
    if isinstance(body, SerialIn):
        return SerialConnectorCfg(id=body.id, enabled=body.enabled, port=body.port)
    if isinstance(body, TcpIn):
        return TcpConnectorCfg(id=body.id, enabled=body.enabled, host=body.host, port=body.port)
    path = Path(body.file)
    if not path.is_absolute():
        path = ctx.cfg.paths.recordings / path
    if not path.resolve().is_relative_to(ctx.cfg.paths.recordings.resolve()) and not ctx.dev:
        raise ProblemError(422, "las grabaciones deben estar en la carpeta de grabaciones")
    return ReplayConnectorCfg(
        id=body.id, enabled=body.enabled, file=path, speed=body.speed, loop=body.loop
    )


@router.get("")
async def list_connectors(request: Request, _: SessionInfo = Depends(require_operator)) -> Response:
    ctx = get_ctx(request)
    return JSON({"connectors": [_public(ctx, c) for c in ctx.cfg.connectors]}, headers=NO_STORE)


@router.post("", status_code=201)
async def create(
    request: Request, body: ConnectorIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    if ctx.cfg.connector(body.id) is not None:
        raise ProblemError(409, "ya existe un conector con ese id")
    ccfg = _build(ctx, body)
    ctx.cfg.connectors = [*ctx.cfg.connectors, ccfg]
    ctx.save_config()
    if ccfg.enabled:
        await ctx.connectors.start_one(ccfg)
    audit(request, info, "connector.create", ccfg.id, {"kind": ccfg.kind})
    return JSON(_public(ctx, ccfg), status_code=201)


@router.put("/{cid}")
async def update(
    request: Request, cid: str, body: ConnectorIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    existing = ctx.cfg.connector(cid)
    if existing is None:
        raise ProblemError(404, "Conector no encontrado")
    if body.id != cid:
        raise ProblemError(422, "el id no se puede cambiar")
    ccfg = _build(ctx, body, existing)
    ctx.cfg.connectors = [ccfg if c.id == cid else c for c in ctx.cfg.connectors]
    ctx.save_config()
    await ctx.connectors.restart(cid)
    audit(request, info, "connector.update", cid)
    return JSON(_public(ctx, ccfg))


@router.delete("/{cid}", status_code=204)
async def delete(
    request: Request, cid: str, info: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    if ctx.cfg.connector(cid) is None:
        raise ProblemError(404, "Conector no encontrado")
    await ctx.connectors.stop_one(cid)
    ctx.cfg.connectors = [c for c in ctx.cfg.connectors if c.id != cid]
    ctx.save_config()
    audit(request, info, "connector.delete", cid)
    return Response(status_code=204)


@router.post("/{cid}/restart")
async def restart(
    request: Request, cid: str, info: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    if ctx.cfg.connector(cid) is None:
        raise ProblemError(404, "Conector no encontrado")
    await ctx.connectors.restart(cid)
    audit(request, info, "connector.restart", cid)
    return JSON({"ok": True})


@router.post("/{cid}/release")
async def release(
    request: Request, cid: str, info: SessionInfo = Depends(require_admin)
) -> Response:
    """Liberar puerto: detiene el conector USB para usar la CLI de Meshtastic (9.3)."""
    ctx = get_ctx(request)
    await ctx.connectors.stop_one(cid)
    audit(request, info, "connector.release", cid)
    return JSON({"ok": True, "state": "stopped"})


@router.post("/{cid}/test")
async def test(request: Request, cid: str, _: SessionInfo = Depends(require_admin)) -> Response:
    """Prueba la conexión: MQTT escucha 8 s; USB lee la información del nodo."""
    ctx = get_ctx(request)
    ccfg = ctx.cfg.connector(cid)
    if ccfg is None:
        raise ProblemError(404, "Conector no encontrado")
    if isinstance(ccfg, MqttConnectorCfg):
        import aiomqtt

        from ...connectors.mqtt import parse_envelope

        t0 = time.monotonic()
        count = valid = 0
        try:
            async with aiomqtt.Client(
                hostname=ccfg.host,
                port=ccfg.port,
                username=ccfg.username,
                password=ctx.secrets.get(ccfg.password_ref),
                identifier=f"meshbox-test-{cid}",
                timeout=8,
            ) as client:
                for t in ccfg.topics:
                    await client.subscribe(t)

                async def listen() -> None:
                    nonlocal count, valid
                    async for m in client.messages:
                        count += 1
                        payload = m.payload if isinstance(m.payload, bytes | bytearray) else b""
                        valid += parse_envelope(bytes(payload)) is not None

                try:
                    await asyncio.wait_for(listen(), 8)
                except TimeoutError:
                    pass
        except aiomqtt.MqttError as e:
            return JSON({"ok": False, "error": str(e)})
        return JSON(
            {
                "ok": True,
                "connected_ms": round((time.monotonic() - t0) * 1000),
                "messages": count,
                "valid_envelopes": valid,
                "seconds": 8,
            }
        )
    if isinstance(ccfg, SerialConnectorCfg | TcpConnectorCfg):
        serial_conn = ctx.connectors.serial(cid)
        if serial_conn is not None and serial_conn.status().state == "connected":
            return JSON({"ok": True, "node": await serial_conn.node_info()})
        return JSON(
            {
                "ok": False,
                "error": "el conector no está conectado; revisar el puerto y los registros",
            }
        )
    exists = await asyncio.to_thread(Path(ccfg.file).exists)
    return JSON({"ok": exists, "file": str(ccfg.file)})


@router.get("/serial-ports")
async def serial_ports(request: Request, _: SessionInfo = Depends(require_admin)) -> Response:
    from ...connectors.serial import list_serial_ports

    return JSON({"ports": await asyncio.to_thread(list_serial_ports)}, headers=NO_STORE)


@router.get("/{cid}/node")
async def node(request: Request, cid: str, _: SessionInfo = Depends(require_admin)) -> Response:
    """Información del nodo por USB, en solo lectura (18.4)."""
    ctx = get_ctx(request)
    conn = ctx.connectors.serial(cid)
    if conn is None:
        raise ProblemError(404, "No hay un conector USB con ese id")
    try:
        return JSON(await conn.node_info(), headers=NO_STORE)
    except RuntimeError as e:
        raise ProblemError(409, str(e)) from None


class RebootIn(BaseModel):
    confirm: bool = False


@router.post("/{cid}/reboot-node")
async def reboot_node(
    request: Request, cid: str, body: RebootIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    ctx = get_ctx(request)
    conn = ctx.connectors.serial(cid)
    if conn is None:
        raise ProblemError(404, "No hay un conector USB con ese id")
    if not body.confirm:
        raise ProblemError(400, "Confirmar el reinicio del nodo")
    await conn.reboot_node(10)
    audit(request, info, "node.reboot", cid)
    return JSON({"ok": True, "message": "El nodo se reinicia en 10 s"})


class RecordIn(BaseModel):
    duration_s: int = Field(3600, ge=10, le=7 * 86400)


@router.post("/{cid}/record")
async def record(
    request: Request, cid: str, body: RecordIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    """Graba los paquetes de un conector a JSONL durante `duration_s` (9.4)."""
    ctx = get_ctx(request)
    if ctx.connectors.get(cid) is None:
        raise ProblemError(404, "El conector no está activo")
    from ...connectors.replay import Recorder

    recorder = Recorder(ctx.cfg.paths.recordings, {cid})
    ctx.processor.raw_hooks.append(recorder)

    async def stop_later() -> None:
        await asyncio.sleep(body.duration_s)
        if recorder in ctx.processor.raw_hooks:
            ctx.processor.raw_hooks.remove(recorder)
        recorder.close()

    ctx._spawn(stop_later(), f"record-{cid}")
    audit(request, info, "connector.record", cid, {"duration_s": body.duration_s})
    return JSON({"ok": True, "file": recorder.path.name, "until": time.time() + body.duration_s})


@router.get("/recordings")
async def recordings(request: Request, _: SessionInfo = Depends(require_admin)) -> Response:
    ctx = get_ctx(request)
    d = ctx.cfg.paths.recordings
    files = (
        sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if d.exists()
        else []
    )
    return JSON(
        {
            "files": [
                {"name": f.name, "size": f.stat().st_size, "mtime": f.stat().st_mtime}
                for f in files[:100]
            ]
        }
    )
