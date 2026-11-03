"""Mensajes nuevos de las placas del Cliente Meshtastic (ADR 0022).

La barra del panel y el Panel principal muestran, en cualquier pantalla, lo que llegó a las
placas conectadas por USB o TCP y el usuario todavía no leyó, y los últimos mensajes recibidos.
Lo leído es el mismo del Cliente (ADR 0016), por usuario, y los permisos son los de leer los
mensajes: operadores y administradores.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from starlette.responses import Response

from ...auth.sessions import SessionInfo
from ...models import node_num, placeholder_user
from ...radio.service import get_radio
from ..deps import get_ctx, require_operator
from ..http import JSON, NO_STORE

router = APIRouter(prefix="/api/v1/admin/inbox", tags=["administración: cliente Meshtastic"])


class _Names:
    """Nombres para mostrar, como en el Cliente: los de la base de cada placa conectada y, si no
    los tiene, los que conoce meshbox."""

    def __init__(self, ctx: Any) -> None:
        radio = get_radio(ctx)
        self.nodes = ctx.state.nodes
        self.boards = {b["gateway_id"]: b for b in radio.boards() if b["gateway_id"]}
        self.channels = {c.id: c.channel_names for c in radio.connectors()}
        self.ifaces = [c.iface for c in radio.connectors() if c.iface is not None]
        self.count = len(self.channels)

    def node(self, nid: str | None) -> tuple[str | None, str | None]:
        """Nombre largo y corto, si se conocen."""
        board = self.boards.get(nid or "")
        if board:
            return board["long_name"], board["short_name"]
        try:
            num = node_num(nid) if nid else None
        except ValueError:
            num = None
        if num is None:
            return None, None
        for iface in self.ifaces:
            user = ((getattr(iface, "nodesByNum", None) or {}).get(num) or {}).get("user") or {}
            if user and not placeholder_user(user, num):
                return user.get("longName"), user.get("shortName")
        rec = self.nodes.get(num)
        return (rec.long_name, rec.short_name) if rec and not rec.hidden else (None, None)

    def board(self, board: str) -> str:
        long_name, short_name = self.node(board)
        return short_name or long_name or board

    def conv(self, cid: str, conv: str, stored: str | None) -> dict[str, Any]:
        """Nombre de la conversación: el canal (el que tenía al llegar el mensaje) o el nodo."""
        if conv.startswith("dm:"):
            peer = conv[3:]
            long_name, short_name = self.node(peer)
            return {"dm": True, "peer": peer, "name": long_name or short_name, "short": short_name}
        idx = int(conv[3:]) if conv[3:].isdigit() else 0
        name = stored or self.channels.get(cid, {}).get(idx)
        return {"dm": False, "channel_index": idx, "name": name}

    def message(self, m: dict[str, Any]) -> dict[str, Any]:
        long_name, short_name = self.node(m["from"])
        return {
            "seq": m["seq"],
            "ts": m["ts"],
            "from": m["from"],
            "from_name": long_name,
            "from_short": short_name,
            "text": m["text"],
            "emoji": m["emoji"],
        }


@router.get("")
async def inbox(request: Request, info: SessionInfo = Depends(require_operator)) -> Response:
    """Conversaciones con mensajes sin leer (las placas juntas) y los últimos recibidos.

    `upto` es el último mensaje del historial al consultar: «marcar todo como leído» llega
    hasta ahí. Las cuentas llegan hasta 100 por conversación.
    """
    ctx = get_ctx(request)
    data = await ctx.radio_messages.inbox(info.user_id)
    names = _Names(ctx)
    convs = [
        {
            "key": g["key"],
            **names.conv(g["connector_id"], g["conv"], g["channel"]),
            "unread": g["unread"],
            "cid": g["connector_id"],
            "conv": g["conv"],
            "boards": [names.board(b) for b in g["boards"]],
            "last": names.message(g["last"]),
        }
        for g in data["conversations"]
    ]
    latest = [
        {
            **names.message(m),
            **names.conv(m["connector_id"], m["conv"], m["channel"]),
            "cid": m["connector_id"],
            "conv": m["conv"],
            "boards": [names.board(b) for b in m["boards"]],
            "unread": m["unread"],
        }
        for m in data["latest"]
    ]
    return JSON(
        {
            "boards": names.count,
            "unread": sum(c["unread"] for c in convs),
            "upto": data["upto"],
            "conversations": convs,
            "latest": latest,
        },
        headers=NO_STORE,
    )


class ReadAllIn(BaseModel):
    upto: int = Field(ge=1, description="el `upto` de la consulta")


@router.post("/read")
async def read_all(
    request: Request, body: ReadAllIn, info: SessionInfo = Depends(require_operator)
) -> Response:
    """Todo lo que había al consultar queda leído, en todas las placas. Lo que llegó después
    sigue sin leer."""
    n = await get_ctx(request).radio_messages.mark_all_read(info.user_id, body.upto)
    return JSON({"upto": body.upto, "conversations": n})
