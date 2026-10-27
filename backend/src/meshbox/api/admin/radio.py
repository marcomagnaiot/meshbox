"""Cliente Meshtastic del panel (ADR 0015): estado, nodos, mensajes, canales y configuración de
cada placa conectada por USB o TCP.

Lectura para operadores; escritura y transmisión para administradores. Los mensajes quedan en la
base (ADR 0016), así que el historial es el mismo desde cualquier dispositivo. Transmitir (mensajes,
pedidos de posición, traceroute) respeta `[tx] enabled` y sus límites (sección 22). Los cambios
peligrosos piden `confirm_danger` y no se permiten desde el hostname remoto sin Access.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from starlette.responses import FileResponse, Response

from ...auth.sessions import SessionInfo
from ...models import node_num
from ...radio.service import RadioError, RadioService, get_radio
from ..deps import audit, get_ctx, require_admin, require_operator
from ..http import JSON, NO_STORE, ProblemError

router = APIRouter(prefix="/api/v1/admin/radio", tags=["administración: cliente Meshtastic"])
NODE_RE = r"^![0-9a-fA-F]{8}$"


def _radio(request: Request) -> RadioService:
    return get_radio(get_ctx(request))


def _remote(request: Request) -> bool:
    return bool(getattr(request.app.state, "kind", "") == "remote")


def _lan_only(request: Request, what: str) -> None:
    if _remote(request):
        raise ProblemError(403, f"Por seguridad, {what} solo se puede desde la red local")


async def _call(coro: Any) -> Any:
    try:
        return await coro
    except RadioError as e:
        raise ProblemError(e.status, e.message, extra=e.extra or None) from None


def _tx_allowed(request: Request) -> Any:
    from .plugins import TxLimiter

    ctx = get_ctx(request)
    if not ctx.cfg.tx.enabled:
        raise ProblemError(
            403, "La transmisión está desactivada ([tx] enabled = false en config.toml)"
        )
    limiter: TxLimiter = ctx.extensions.setdefault("tx_limiter", TxLimiter())
    wait = limiter.check()
    if wait > 0:
        raise ProblemError(
            429,
            f"Límite de transmisión: esperar {int(wait)} s",
            headers={"Retry-After": str(int(wait) + 1)},
        )
    return limiter


class ConfirmIn(BaseModel):
    confirm: bool = False


# --------------------------------------------------------------------------- lectura


@router.get("")
async def boards(request: Request, _: SessionInfo = Depends(require_operator)) -> Response:
    return JSON({"boards": _radio(request).boards(), "remote": _remote(request)}, headers=NO_STORE)


@router.get("/{cid}")
async def status(
    request: Request, cid: str, _: SessionInfo = Depends(require_operator)
) -> Response:
    data = await _call(_radio(request).status(cid))
    data["remote"] = _remote(request)
    return JSON(data, headers=NO_STORE)


@router.get("/{cid}/nodes")
async def nodes(request: Request, cid: str, _: SessionInfo = Depends(require_operator)) -> Response:
    return JSON({"nodes": await _call(_radio(request).nodes(cid))}, headers=NO_STORE)


async def _board(request: Request, cid: str) -> tuple[Any, str | None]:
    """Conector y placa de su historial (la de la última conexión si hoy no está conectada)."""
    conn = next((c for c in _radio(request).connectors() if c.id == cid), None)
    if conn is None:
        raise ProblemError(404, "No hay una placa (USB o TCP) con ese conector")
    board = conn.gateway_id or await get_ctx(request).radio_messages.last_board(cid)
    return conn, board


@router.get("/{cid}/messages")
async def messages(
    request: Request,
    cid: str,
    after: int = Query(0, ge=0, description="solo los posteriores a este número (sondeo)"),
    before: int | None = Query(None, ge=1, description="página anterior a este número"),
    limit: int = Query(1000, ge=1, le=1000),
    info: SessionInfo = Depends(require_operator),
) -> Response:
    """Historial de la placa (ADR 0016): sin `after`, los últimos `limit` y si hay anteriores."""
    ctx = get_ctx(request)
    conn, board = await _board(request, cid)
    items: list[dict[str, Any]] = []
    more, reads = False, {}
    if board:
        store = ctx.radio_messages
        items, more = await store.page(board, after=after, before=before, limit=limit)
        reads = await store.reads(info.user_id, board)
    return JSON(
        {
            "messages": items,
            "more": more,
            "reads": reads,
            "channels": conn.channel_names,
            "board": board,
            "retention_days": ctx.cfg.retention.radio_messages,
        },
        headers=NO_STORE,
    )


class ReadIn(BaseModel):
    conv: str = Field(pattern=r"^(ch:[0-7]|dm:![0-9a-fA-F]{8})$")
    seq: int = Field(ge=1)


@router.put("/{cid}/reads")
async def mark_read(
    request: Request, cid: str, body: ReadIn, info: SessionInfo = Depends(require_operator)
) -> Response:
    """Lo leído de una conversación, por usuario: se ve igual en todos sus dispositivos."""
    _, board = await _board(request, cid)
    if not board:
        raise ProblemError(409, "La placa todavía no tiene historial")
    await get_ctx(request).radio_messages.mark_read(info.user_id, board, body.conv, body.seq)
    return JSON({"conv": body.conv, "seq": body.seq})


@router.delete("/{cid}/messages")
async def clear_messages(
    request: Request, cid: str, body: ConfirmIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    if not body.confirm:
        raise ProblemError(400, "Confirmar el borrado del historial de mensajes")
    _, board = await _board(request, cid)
    deleted = await get_ctx(request).radio_messages.clear(board) if board else 0
    audit(request, info, "radio.messages_clear", cid, {"board": board, "deleted": deleted})
    return JSON({"deleted": deleted})


@router.get("/{cid}/config")
async def config(request: Request, cid: str, _: SessionInfo = Depends(require_admin)) -> Response:
    data = await _call(_radio(request).config(cid))
    data["remote"] = _remote(request)
    return JSON(data, headers=NO_STORE)


# --------------------------------------------------------------------------- mensajes


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=200)
    channel_index: int = Field(0, ge=0, le=7)
    to: str | None = Field(None, pattern=NODE_RE, description="nodo para mensaje directo")
    confirm: bool = False


@router.post("/{cid}/messages")
async def send(
    request: Request, cid: str, body: MessageIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    radio = _radio(request)
    conn = await _call(_ready(radio, cid))
    preview = {
        "text": body.text,
        "channel": conn.channel_names.get(body.channel_index),
        "channel_index": body.channel_index,
        "to": body.to,
        "bytes": len(body.text.encode()),
        "from": conn.gateway_id,
    }
    if body.channel_index not in conn.channel_names:
        raise ProblemError(422, "Ese canal no está configurado en la placa")
    if not body.confirm:
        return JSON({"preview": preview, "confirm_required": True})
    limiter = _tx_allowed(request)
    try:
        packet_id = await conn.send_message(body.text, body.channel_index, body.to)
    except RuntimeError as e:
        raise ProblemError(409, str(e)) from None
    limiter.mark()
    audit(request, info, "radio.message", cid, {**preview, "packet_id": packet_id})
    await get_ctx(request).radio_messages.sync()  # que el próximo sondeo ya lo traiga
    return JSON({"ok": True, "packet_id": packet_id})


async def _ready(radio: RadioService, cid: str) -> Any:
    return radio.connector(cid)


class NodeIn(BaseModel):
    node: str = Field(pattern=NODE_RE)
    channel_index: int = Field(0, ge=0, le=7)
    hop_limit: int = Field(3, ge=1, le=7)


@router.post("/{cid}/request-position")
async def request_position(
    request: Request, cid: str, body: NodeIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    limiter = _tx_allowed(request)
    result = await _call(_radio(request).request_position(cid, body.node, body.channel_index))
    limiter.mark()
    audit(request, info, "radio.request_position", cid, {"node": body.node})
    return JSON(result)


@router.post("/{cid}/traceroute")
async def traceroute(
    request: Request, cid: str, body: NodeIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    try:
        node_num(body.node)
    except ValueError:
        raise ProblemError(422, "id de nodo no válido") from None
    limiter = _tx_allowed(request)
    await _call(_radio(request).traceroute(cid, body.node, body.hop_limit, body.channel_index))
    limiter.mark()
    audit(request, info, "radio.traceroute", cid, {"node": body.node, "hop_limit": body.hop_limit})
    return JSON({"ok": True, "note": "La respuesta llega como TRACEROUTE_APP (Paquetes y mapa)"})


# --------------------------------------------------------------------------- configuración


class SectionIn(BaseModel):
    values: dict[str, Any]
    confirm_danger: bool = False


@router.put("/{cid}/config/{section}")
async def write_section(
    request: Request,
    cid: str,
    section: str,
    body: SectionIn,
    info: SessionInfo = Depends(require_admin),
) -> Response:
    if body.confirm_danger:
        _lan_only(request, "un cambio peligroso de la placa")
    result = await _call(
        _radio(request).write_section(cid, section, body.values, body.confirm_danger)
    )
    if result.get("changed"):
        audit(request, info, "radio.config", f"{cid}:{section}", {"changed": result["changed"]})
    return JSON(result)


class ChannelIn(BaseModel):
    name: str | None = Field(None, max_length=11)
    psk: str | None = Field(None, max_length=64, description="keep, default, none, random o base64")
    uplink: bool | None = None
    downlink: bool | None = None
    position_precision: int | None = Field(None, ge=0, le=32)
    muted: bool | None = None
    confirm_danger: bool = False

    def values(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True, exclude={"confirm_danger"})


@router.put("/{cid}/channels/{index}")
async def write_channel(
    request: Request,
    cid: str,
    index: int,
    body: ChannelIn,
    info: SessionInfo = Depends(require_admin),
) -> Response:
    if body.confirm_danger:
        _lan_only(request, "un cambio peligroso de un canal")
    result = await _call(
        _radio(request).write_channel(cid, index, body.values(), body.confirm_danger)
    )
    if result.get("changed"):
        audit(request, info, "radio.channel", f"{cid}:{index}", {"changed": result["changed"]})
    return JSON(result)


@router.post("/{cid}/channels", status_code=201)
async def add_channel(
    request: Request, cid: str, body: ChannelIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    result = await _call(_radio(request).add_channel(cid, body.values()))
    audit(request, info, "radio.channel_add", cid, {"index": result["index"], "name": body.name})
    return JSON(result, status_code=201)


class DangerIn(BaseModel):
    confirm_danger: bool = False


@router.delete("/{cid}/channels/{index}")
async def delete_channel(
    request: Request,
    cid: str,
    index: int,
    body: DangerIn,
    info: SessionInfo = Depends(require_admin),
) -> Response:
    _lan_only(request, "borrar un canal")
    if not body.confirm_danger:
        raise ProblemError(
            409,
            "Borrar un canal corta la comunicación con quienes lo usan. Hace falta confirmarlo.",
            extra={"code": "danger_confirmation_required", "fields": [f"canal {index}"]},
        )
    result = await _call(_radio(request).delete_channel(cid, index))
    audit(request, info, "radio.channel_delete", f"{cid}:{index}")
    return JSON(result)


class OwnerIn(BaseModel):
    long_name: str = Field(min_length=1, max_length=39)
    short_name: str = Field(min_length=1, max_length=4)


@router.put("/{cid}/owner")
async def owner(
    request: Request, cid: str, body: OwnerIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    result = await _call(_radio(request).set_owner(cid, body.long_name, body.short_name))
    audit(request, info, "radio.owner", cid, {"long_name": body.long_name})
    return JSON(result)


class PositionIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    alt: int = Field(0, ge=-500, le=9000)


@router.put("/{cid}/position")
async def set_position(
    request: Request, cid: str, body: PositionIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    result = await _call(_radio(request).set_position(cid, body.lat, body.lon, body.alt))
    audit(request, info, "radio.position", cid)
    return JSON(result)


@router.post("/{cid}/position/refresh")
async def refresh_position(
    request: Request, cid: str, info: SessionInfo = Depends(require_admin)
) -> Response:
    result = await _call(_radio(request).refresh_position(cid))
    audit(request, info, "radio.position_refresh", cid)
    return JSON(result)


@router.delete("/{cid}/position")
async def remove_position(
    request: Request, cid: str, info: SessionInfo = Depends(require_admin)
) -> Response:
    result = await _call(_radio(request).remove_fixed_position(cid))
    audit(request, info, "radio.position_remove", cid)
    return JSON(result)


@router.post("/{cid}/reboot")
async def reboot(
    request: Request, cid: str, body: ConfirmIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    if not body.confirm:
        raise ProblemError(400, "Confirmar el reinicio de la placa")
    await _call(_radio(request).reboot(cid))
    audit(request, info, "radio.reboot", cid)
    return JSON({"ok": True, "message": "La placa se reinicia en 5 s"})


@router.post("/{cid}/shutdown")
async def shutdown(
    request: Request, cid: str, body: DangerIn, info: SessionInfo = Depends(require_admin)
) -> Response:
    _lan_only(request, "apagar la placa")
    if not body.confirm_danger:
        raise ProblemError(
            409,
            "Apagada, la placa solo vuelve con el botón o cortando la energía. Hace falta "
            "confirmarlo.",
            extra={"code": "danger_confirmation_required", "fields": ["apagar"]},
        )
    await _call(_radio(request).shutdown(cid))
    audit(request, info, "radio.shutdown", cid)
    return JSON({"ok": True, "message": "La placa se apaga en 5 s"})


# --------------------------------------------------------------------------- copias


@router.get("/{cid}/backups")
async def backups(request: Request, cid: str, _: SessionInfo = Depends(require_admin)) -> Response:
    return JSON({"backups": await _call(_list_backups(_radio(request), cid))}, headers=NO_STORE)


async def _list_backups(radio: RadioService, cid: str) -> list[dict[str, Any]]:
    return radio.list_backups(cid)


@router.post("/{cid}/backups", status_code=201)
async def create_backup(
    request: Request, cid: str, info: SessionInfo = Depends(require_admin)
) -> Response:
    name = await _call(_radio(request).create_backup(cid))
    audit(request, info, "radio.backup", cid, {"name": name})
    return JSON({"name": name}, status_code=201)


@router.get("/{cid}/backups/{name}")
async def download_backup(
    request: Request, cid: str, name: str, info: SessionInfo = Depends(require_admin)
) -> Response:
    _lan_only(request, "descargar una copia con las claves de la placa")
    try:
        path = _radio(request).backup_path(name)
    except RadioError as e:
        raise ProblemError(e.status, e.message) from None
    audit(request, info, "radio.backup_download", cid, {"name": name})
    return FileResponse(
        path,
        media_type="application/json",
        filename=name,
        headers={"Cache-Control": "no-store"},
    )


@router.post("/{cid}/backups/{name}/restore")
async def restore(
    request: Request,
    cid: str,
    name: str,
    body: DangerIn,
    info: SessionInfo = Depends(require_admin),
) -> Response:
    _lan_only(request, "restaurar la configuración de la placa")
    if not body.confirm_danger:
        raise ProblemError(
            409,
            "Restaurar reescribe la configuración y los canales de la placa. Hace falta "
            "confirmarlo.",
            extra={"code": "danger_confirmation_required", "fields": ["restaurar"]},
        )
    result = await _call(_radio(request).restore(cid, name))
    audit(request, info, "radio.restore", cid, {"name": name, **result})
    return JSON(result)
