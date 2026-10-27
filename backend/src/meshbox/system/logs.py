"""Registros (sección 29): JSON por salida estándar hacia journald, con filtro de secretos.

Además guarda los últimos registros en memoria: el panel los muestra en vivo y sirven de
respaldo donde no hay journal (Windows, pruebas).
"""

from __future__ import annotations

import logging
import re
import sys
import time
from collections import deque
from collections.abc import Callable
from typing import Any

import orjson

SECRET_PATTERNS = (
    re.compile(
        r"(?i)(password|passwd|psk|token|secret|api[_-]?key|private[_-]?key)(\s*[=:]\s*)(\S+)"
    ),
    re.compile(r"(?i)(TUNNEL_TOKEN=)(\S+)"),
    re.compile(r"(?i)(authorization:\s*bearer\s+)(\S+)"),
)
MASK = "********"


class SecretFilter(logging.Filter):
    """Enmascara valores secretos conocidos y patrones típicos (clave=valor)."""

    def __init__(self, secrets_provider: Callable[[], list[str]] | None = None) -> None:
        super().__init__()
        self.secrets_provider = secrets_provider
        self._cache: list[str] = []
        self._cache_at = 0.0

    def _secrets(self) -> list[str]:
        now = time.monotonic()
        if self.secrets_provider is not None and now - self._cache_at > 30:
            try:
                self._cache = sorted(self.secrets_provider(), key=len, reverse=True)
            except Exception:
                self._cache = []
            self._cache_at = now
        return self._cache

    def mask(self, text: str) -> str:
        for value in self._secrets():
            if value and value in text:
                text = text.replace(value, MASK)
        for pat in SECRET_PATTERNS:
            if pat.groups == 3:
                text = pat.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", text)
            else:
                text = pat.sub(lambda m: f"{m.group(1)}{MASK}", text)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        masked = self.mask(msg)
        if masked != msg:
            record.msg = masked
            record.args = ()
        if record.exc_info and not record.exc_text:
            record.exc_text = self.mask(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = self.mask(record.exc_text)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": round(record.created, 3),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_text:
            out["exc"] = record.exc_text
        elif record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return orjson.dumps(out).decode()


class RingHandler(logging.Handler):
    """Últimos N registros en memoria para el panel."""

    def __init__(self, capacity: int = 2000) -> None:
        super().__init__()
        self.records: deque[dict[str, Any]] = deque(maxlen=capacity)
        self.listeners: list[Callable[[dict[str, Any]], None]] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            item = {
                "ts": record.created,
                "level": record.levelname,
                "logger": record.name,
                "msg": record.getMessage(),
                "unit": "meshbox",
            }
            if record.exc_text:
                item["exc"] = record.exc_text
            self.records.append(item)
            for fn in list(self.listeners):
                fn(item)
        except Exception:
            self.handleError(record)

    def tail(
        self, lines: int = 200, level: str | None = None, q: str | None = None
    ) -> list[dict[str, Any]]:
        levels = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
        min_level = levels.get((level or "").upper(), 0)
        out = [
            r
            for r in self.records
            if levels.get(r["level"], 0) >= min_level and (not q or q.lower() in r["msg"].lower())
        ]
        return out[-lines:]


RING = RingHandler()
SECRET_FILTER = SecretFilter()


def setup_logging(
    level: str = "INFO",
    json_output: bool = True,
    secrets_provider: Callable[[], list[str]] | None = None,
) -> None:
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    SECRET_FILTER.secrets_provider = secrets_provider
    stream = logging.StreamHandler(sys.stdout)
    if json_output:
        stream.setFormatter(JsonFormatter())
    else:
        stream.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
        )
    for h in (stream, RING):
        h.addFilter(SECRET_FILTER)
        root.addHandler(h)
    root.setLevel(level)
    # Librerías ruidosas
    for name in ("uvicorn.access", "aiosqlite", "httpx", "httpcore", "meshtastic", "bleak"):
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(level)
