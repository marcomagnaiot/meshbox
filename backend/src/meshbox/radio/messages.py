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

from sqlalchemy import Connection, bindparam, text

from ..store.db import BatchWriter, Database

PAGE_MAX = 1000
EARLY_ACK_TTL_S = 300
# Mensajes nuevos (ADR 0022). Se cuentan hasta INBOX_CAP sin leer por conversación (más se
# muestra como «99+») entre los INBOX_SCAN recibidos más nuevos sin leer, para no recorrer el
# historial entero de un canal que nunca se abrió. La cuenta se guarda hasta que llega un
# mensaje o cambia lo leído, y se rehace igual cada INBOX_TTL_S (por la retención).
INBOX_CAP = 100
INBOX_SCAN = 500
INBOX_TTL_S = 60

INSERT = text("""
    INSERT OR IGNORE INTO radio_messages (board, connector_id, conv, ts, direction, packet_id,
      from_id, to_id, dm, channel_index, channel, text, snr, rssi, hops, reply_id, emoji, status)
    VALUES (:board, :connector_id, :conv, :ts, :direction, :packet_id, :from_id, :to_id, :dm,
      :channel_index, :channel, :text, :snr, :rssi, :hops, :reply_id, :emoji, :status)
""")
MARK_READ = text(
    "INSERT INTO radio_reads (user_id, board, conv, seq) VALUES (:u, :b, :c, :s) "
    "ON CONFLICT(user_id, board, conv) DO UPDATE SET seq = MAX(radio_reads.seq, excluded.seq)"
)
FIRST_CONV = text("SELECT board, conv FROM radio_messages ORDER BY board, conv LIMIT 1")
NEXT_CONV = text(
    "SELECT board, conv FROM radio_messages WHERE board = :b AND conv > :c ORDER BY conv LIMIT 1"
)
NEXT_BOARD = text(
    "SELECT board, conv FROM radio_messages WHERE board > :b ORDER BY board, conv LIMIT 1"
)
UNREAD = """
SELECT COUNT(*) AS n, MAX(id) AS newest FROM (
  SELECT m.id FROM (
    SELECT id, from_id, packet_id FROM radio_messages
    WHERE board = :b AND conv = :c AND id > :s AND direction = 'in'
    ORDER BY id DESC LIMIT :scan
  ) AS m {dedupe}
  LIMIT :n
)"""
# Con varias placas, el mismo mensaje queda guardado en cada una que lo oyó: cuenta una sola vez
# (en la placa que lo guardó primero) y, leído en cualquiera, está leído. Lo que mandó una placa
# propia y oyó otra no es un mensaje nuevo.
DEDUPE = """
  WHERE COALESCE(m.from_id, '') NOT IN :boards AND (m.packet_id = 0 OR NOT EXISTS (
    SELECT 1 FROM radio_messages AS o
    WHERE o.board IN :boards AND o.board != :b AND o.from_id = m.from_id
      AND o.packet_id = m.packet_id AND o.packet_id != 0
      AND (o.id < m.id OR o.id <= COALESCE((SELECT r.seq FROM radio_reads AS r
           WHERE r.user_id = :u AND r.board = o.board AND r.conv = o.conv), 0))))"""
UNREAD_ONE = text(UNREAD.format(dedupe=""))
UNREAD_MANY = text(UNREAD.format(dedupe=DEDUPE)).bindparams(bindparam("boards", expanding=True))
BY_IDS = text("SELECT * FROM radio_messages WHERE id IN :ids").bindparams(
    bindparam("ids", expanding=True)
)


def _conversations(c: Connection) -> list[tuple[str, str]]:
    """Placas y conversaciones del historial, salteando por el índice (placa, conversación):
    una búsqueda por conversación en lugar de leer todos los mensajes."""
    out: list[tuple[str, str]] = []
    row = c.execute(FIRST_CONV).first()
    while row is not None:
        out.append((row.board, row.conv))
        row = (
            c.execute(NEXT_CONV, {"b": row.board, "c": row.conv}).first()
            or c.execute(NEXT_BOARD, {"b": row.board}).first()
        )
    return out


def _inbox(c: Connection, user_id: int, latest: int) -> dict[str, Any]:
    """Cuenta de `MessageStore.inbox`, sin la caché."""
    seen = {
        (r.board, r.conv): r.seq
        for r in c.execute(
            text("SELECT board, conv, seq FROM radio_reads WHERE user_id = :u"), {"u": user_id}
        )
    }
    convs = _conversations(c)
    boards = sorted({b for b, _ in convs})
    unread: list[tuple[str, str, int, int]] = []
    for board, conv in convs:
        args: dict[str, Any] = {"b": board, "c": conv, "s": seen.get((board, conv), 0)}
        args |= {"scan": INBOX_SCAN, "n": INBOX_CAP, "u": user_id, "boards": boards}
        row = c.execute(UNREAD_MANY if len(boards) > 1 else UNREAD_ONE, args).one()
        if row.n:
            unread.append((board, conv, row.n, row.newest))
    newest = {r.id: r for r in c.execute(BY_IDS, {"ids": [u[3] for u in unread]})} if unread else {}
    groups: dict[str, dict[str, Any]] = {}
    for board, conv, n, last_id in unread:
        last = newest[last_id]
        dm = conv.startswith("dm:")
        key = conv if dm else f"ch:{last.channel}" if last.channel else f"{board}/{conv}"
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"key": key, "dm": dm, "unread": 0, "boards": []}
        g["unread"] += n
        g["boards"].append(board)
        if "last" not in g or last.id > g["last"]["seq"]:
            # Se abre en la placa que tiene el último sin leer.
            g |= {"board": board, "connector_id": last.connector_id, "conv": conv}
            g |= {"channel": last.channel, "last": _row(last)}
    # Los últimos recibidos, una vez cada uno, con las placas que lo oyeron (se abre en la que
    # lo guardó primero): sin leer si no se leyó en ninguna.
    recent: list[dict[str, Any]] = []
    copies: dict[tuple[Any, ...], dict[str, Any]] = {}
    for r in c.execute(
        text("SELECT * FROM radio_messages WHERE direction = 'in' ORDER BY id DESC LIMIT :n"),
        {"n": latest * 4},
    ):
        if r.from_id in boards:
            continue  # lo mandó una placa propia y lo oyó otra
        is_unread = r.id > seen.get((r.board, r.conv), 0)
        k = (r.from_id, r.packet_id) if r.packet_id else ("", r.id)
        item = copies.get(k)
        if item is None:
            item = copies[k] = {"unread": is_unread, "boards": []}
            recent.append(item)
        item |= {**_row(r), "board": r.board, "connector_id": r.connector_id}
        item["unread"] = item["unread"] and is_unread
        item["boards"].insert(0, r.board)
    return {
        "conversations": sorted(groups.values(), key=lambda g: g["last"]["seq"], reverse=True),
        "latest": recent[:latest],
    }


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
        # Mensajes nuevos por usuario: (clave, hora, cuenta), ver `inbox`.
        self._inbox_cache: dict[int, tuple[tuple[Any, ...], float, dict[str, Any]]] = {}

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
            lambda c: c.execute(MARK_READ, {"u": user_id, "b": board, "c": conv, "s": seq})
        )

    async def inbox(self, user_id: int, latest: int = 8) -> dict[str, Any]:
        """Lo nuevo para un usuario en todas las placas (ADR 0022).

        `conversations`: las que tienen recibidos sin leer, juntando las placas (un canal por su
        nombre, un directo por el nodo), con cuántos son, el último y dónde abrirlo (la placa
        del último). `latest`: los últimos `latest` recibidos, leídos o no, sin repetir.
        """

        def q(c: Connection) -> dict[str, Any]:
            reads = c.execute(
                text("SELECT COUNT(*), COALESCE(SUM(seq), 0) FROM radio_reads WHERE user_id = :u"),
                {"u": user_id},
            ).one()
            key = (c.execute(text("SELECT MAX(id) FROM radio_messages")).scalar(), *reads, latest)
            hit = self._inbox_cache.get(user_id)
            if hit and hit[0] == key and time.monotonic() - hit[1] < INBOX_TTL_S:
                return hit[2]
            data = {**_inbox(c, user_id, latest), "upto": key[0] or 0}
            self._inbox_cache[user_id] = (key, time.monotonic(), data)
            return data

        return await self.db.read(q)

    async def mark_all_read(self, user_id: int, upto: int) -> int:
        """Todo lo que llegó hasta el mensaje `upto` queda leído, en todas las placas y
        conversaciones (lo que llegó después, no). Devuelve cuántas conversaciones tocó."""

        def do(c: Connection) -> int:
            n = 0
            for board, conv in _conversations(c):
                last = c.execute(
                    text(
                        "SELECT MAX(id) FROM radio_messages WHERE board = :b AND conv = :c "
                        "AND id <= :u"
                    ),
                    {"b": board, "c": conv, "u": upto},
                ).scalar()
                if last:
                    c.execute(MARK_READ, {"u": user_id, "b": board, "c": conv, "s": last})
                    n += 1
            return n

        return int(await self.writer.run(do))

    async def clear(self, board: str) -> int:
        """Borra el historial de una placa (y lo leído). Devuelve cuántos mensajes borró."""

        def do(c: Connection) -> int:
            n = c.execute(text("DELETE FROM radio_messages WHERE board = :b"), {"b": board})
            c.execute(text("DELETE FROM radio_reads WHERE board = :b"), {"b": board})
            return n.rowcount or 0

        deleted = int(await self.writer.run(do))
        self._inbox_cache.clear()
        return deleted
