"""Telegram y webhooks (sección 19.2)."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from typing import Any

import httpx
import orjson

from ... import __version__


class ChannelError(Exception):
    pass


async def send_telegram(
    token: str, chat_id: str, text: str, client: httpx.AsyncClient | None = None
) -> None:
    if not token or not chat_id:
        raise ChannelError("Telegram sin configurar (token del bot y chat id)")
    own = client is None
    client = client or httpx.AsyncClient(timeout=15)
    try:
        r = await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True},
        )
        if r.status_code != 200:
            try:
                desc = r.json().get("description", "")
            except ValueError:
                desc = r.text[:200]
            raise ChannelError(f"Telegram respondió {r.status_code}: {desc}")
    except httpx.HTTPError as e:
        raise ChannelError(f"no se pudo contactar a Telegram: {type(e).__name__}") from e
    finally:
        if own:
            await client.aclose()


def webhook_body(event: str, data: dict[str, Any]) -> bytes:
    """Cuerpo del webhook (Anexo B)."""
    return orjson.dumps(
        {"event": event, "version": 1, "sent_at": round(time.time(), 3), "data": data}
    )


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def send_webhook(
    url: str,
    secret: str,
    body: bytes,
    *,
    retries: int = 3,
    client: httpx.AsyncClient | None = None,
    backoff: float = 2.0,
) -> None:
    """POST con firma HMAC-SHA256 en `X-Meshbox-Signature`; 3 reintentos con espera creciente."""
    if not url.startswith(("https://", "http://")):
        raise ChannelError("URL de webhook no válida")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": f"meshbox/{__version__}",
        "X-Meshbox-Signature": sign(secret, body) if secret else "",
    }
    own = client is None
    client = client or httpx.AsyncClient(timeout=10)
    last = ""
    try:
        for attempt in range(retries + 1):
            try:
                r = await client.post(url, content=body, headers=headers)
                if 200 <= r.status_code < 300:
                    return
                last = f"HTTP {r.status_code}"
                if 400 <= r.status_code < 500 and r.status_code not in (408, 429):
                    break  # error del receptor: no tiene sentido reintentar
            except httpx.HTTPError as e:
                last = type(e).__name__
            if attempt < retries:
                await asyncio.sleep(backoff * (2**attempt))
    finally:
        if own:
            await client.aclose()
    raise ChannelError(f"el webhook falló: {last}")
