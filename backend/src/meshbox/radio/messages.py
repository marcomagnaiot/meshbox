"""Historial de mensajes del cliente Meshtastic (ADR 0016).

Lo que entra y sale por cada placa conectada por USB o TCP (todos los canales y los directos)
queda en la base, aunque nadie tenga el panel abierto, y se ve igual desde cualquier
dispositivo y después de reiniciar. Solo lo lee la API de administración, nunca el sitio
público. Lo leído se guarda por usuario. Las escrituras van por el escritor, en orden: el
acuse de un mensaje enviado se aplica después de guardarlo.
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import Connection, text

from ..store.db import BatchWriter, Database

PAGE_MAX = 1000
EARLY_ACK_TTL_S = 300

INSERT = text("""
    INSERT OR IGNORE INTO radio_messages (board, connector_id, conv, ts, direction, packet_id,
      from_id, to_id, dm, channel_index, channel, text, snr, rssi, hops, reply_id, emoji, status)
    VALUES (:board, :connector_id, :conv, :ts, :direction, :packet_id, :from_id, :to_id, :dm,
      :channel_index, :channel, :text, :snr, :rssi, :hops, :reply_id, :emoji, :status)
""")


def conv_key(direction: str, dm: bool, from_id: str | None, to_id: str | None, idx: int) -> str:
    """Conversación: `ch:<índice>` para un canal, `dm:<nodo>` para los directos."""
    if dm:
        return f"dm:{(to_id if direction == 'out' else from_id) or '?'}"
    return f"ch:{idx}"


def ack_status(current: str | None, reason: str, from_id: str | None, board: str) -> str | None:
    """Estado de un mensaje enviado al llegar un acuse de ruteo."""
    if reason != "NONE":
        return f"error: {reason}"
    if from_id and from_id != board:
        return "entregado"  # confirmó el destino
    if current == "entregado":
        return current
    return "retransmitido"  # la placa oyó a otro nodo repetirlo (acuse implícito)


def _row(r: Any) -> dict[str, Any]:
    return {
        "seq": r.id,
        "id": r.packet_id or None,
        "ts": r.ts,
        "direction": r.direction,
        "from": r.from_id,
        "to": r.to_id,
        "dm": bool(r.dm),
        "conv": r.conv,
        "channel_index": r.channel_index,
        "channel": r.channel,
        "text": r.text,
        "snr": r.snr,
        "rssi": r.rssi,
        "hops": r.hops,
        "reply_id": r.reply_id,
        "emoji": bool(r.emoji),
        "status": r.status,
    }


class MessageStore:
    def __init__(self, db: Database, writer: BatchWriter) -> None:
        self.db = db
        self.writer = writer
        # Acuses que llegaron antes de guardar el mensaje enviado: (placa, paquete) → acuses.
        self._early: dict[tuple[str, int], list[tuple[str, str | None, float]]] = {}

    # ---------------------------------------------------------------- escritura

    def on_event(self, kind: str, payload: dict[str, Any]) -> None:
        """Lo llama el conector desde el loop: `text` (mensaje) o `ack` (acuse de uno enviado)."""
        if kind == "text":
            self.writer.enqueue_fn(lambda c: self._insert(c, payload), now=True)
        elif kind == "ack":
            self.writer.enqueue_fn(lambda c: self._ack(c, payload), now=True)

    async def sync(self) -> None:
        """Espera a que lo encolado quede en la base (después de enviar, para verlo ya)."""
        await self.writer.flush()

    def _insert(self, conn: Connection, item: dict[str, Any]) -> None:
        if item["direction"] == "out" and item.get("packet_id"):
            for reason, frm, _ts in self._early.pop((item["board"], item["packet_id"]), []):
                item = {**item, "status": ack_status(item["status"], reason, frm, item["board"])}
        conn.execute(INSERT, item)

    def _ack(self, conn: Connection, a: dict[str, Any]) -> None:
        row = conn.execute(
            text(
                "SELECT id, status FROM radio_messages WHERE board = :b AND direction = 'out' "
                "AND packet_id = :p ORDER BY id DESC LIMIT 1"
            ),
            {"b": a["board"], "p": a["packet_id"]},
        ).first()
        if row is None:
            now = time.time()
            self._early = {k: v for k, v in self._early.items() if now - v[-1][2] < EARLY_ACK_TTL_S}
            entry = (a["reason"], a.get("from_id"), now)
            self._early.setdefault((a["board"], a["packet_id"]), []).append(entry)
            return
        new = ack_status(row.status, a["reason"], a.get("from_id"), a["board"])
        if new != row.status:
            conn.execute(
                text("UPDATE radio_messages SET status = :s WHERE id = :i"), {"s": new, "i": row.id}
            )

    # ---------------------------------------------------------------- lectura

    async def last_board(self, connector_id: str) -> str | None:
        """Placa que tuvo el conector la última vez (si hoy no está conectada)."""

        def q(c: Connection) -> str | None:
            return c.execute(
                text(
                    "SELECT board FROM radio_messages WHERE connector_id = :c "
                    "ORDER BY id DESC LIMIT 1"
                ),
                {"c": connector_id},
            ).scalar()

        return await self.db.read(q)

    async def page(
        self, board: str, *, after: int = 0, before: int | None = None, limit: int = PAGE_MAX
    ) -> tuple[list[dict[str, Any]], bool]:
        """Mensajes de una placa en orden: nuevos desde `after`, o los últimos (antes de `before`).

        Devuelve también si quedan anteriores sin traer.
        """
        limit = max(1, min(limit, PAGE_MAX))

        def q(c: Connection) -> tuple[list[dict[str, Any]], bool]:
            if after:
                rows = c.execute(
                    text(
                        "SELECT * FROM radio_messages WHERE board = :b AND id > :a "
                        "ORDER BY id LIMIT :n"
                    ),
                    {"b": board, "a": after, "n": limit},
                ).all()
                return [_row(r) for r in rows], False
            rows = c.execute(
                text(
                    "SELECT * FROM radio_messages WHERE board = :b AND id < :before "
                    "ORDER BY id DESC LIMIT :n"
                ),
                {"b": board, "before": before or 2**62, "n": limit + 1},
            ).all()
            more = len(rows) > limit
            return [_row(r) for r in reversed(rows[:limit])], more

        return await self.db.read(q)

    async def reads(self, user_id: int, board: str) -> dict[str, int]:
        def q(c: Connection) -> dict[str, int]:
            rows = c.execute(
                text("SELECT conv, seq FROM radio_reads WHERE user_id = :u AND board = :b"),
                {"u": user_id, "b": board},
            ).all()
            return {r.conv: r.seq for r in rows}

        return await self.db.read(q)

    async def mark_read(self, user_id: int, board: str, conv: str, seq: int) -> None:
        await self.writer.run(
            lambda c: c.execute(
                text(
                    "INSERT INTO radio_reads (user_id, board, conv, seq) VALUES (:u, :b, :c, :s) "
                    "ON CONFLICT(user_id, board, conv) DO UPDATE SET "
                    "seq = MAX(radio_reads.seq, excluded.seq)"
                ),
                {"u": user_id, "b": board, "c": conv, "s": seq},
            )
        )

    async def clear(self, board: str) -> int:
        """Borra el historial de una placa (y lo leído). Devuelve cuántos mensajes borró."""

        def do(c: Connection) -> int:
            n = c.execute(text("DELETE FROM radio_messages WHERE board = :b"), {"b": board})
            c.execute(text("DELETE FROM radio_reads WHERE board = :b"), {"b": board})
            return n.rowcount or 0

        return int(await self.writer.run(do))
