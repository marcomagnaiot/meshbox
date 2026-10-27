"""Cabeceras de seguridad y CSP (sección 13.5)."""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import re
import time
from collections.abc import Callable
from pathlib import Path

from starlette.types import ASGIApp, Message, Receive, Scope, Send

INLINE_SCRIPT_RE = re.compile(rb"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S | re.I)
ESRI = "https://server.arcgisonline.com"
# Búsqueda de lugares por nombre en los selectores de mapa del panel y del asistente.
GEOCODER = "https://nominatim.openstreetmap.org"
PAGES = ("index.html", "200.html", "404.html")


def inline_script_hashes(web_dir: Path | None) -> list[str]:
    """Hashes sha256 de los scripts en línea de las páginas del frontend.

    SvelteKit genera un script de arranque en línea; en vez de exportar los hashes en el
    build, se calculan al arrancar leyendo el HTML servido (siempre coinciden).
    """
    hashes: set[str] = set()
    if web_dir is None or not web_dir.exists():
        return []
    for name in PAGES:
        page = web_dir / name
        if not page.exists():
            continue
        for m in INLINE_SCRIPT_RE.finditer(page.read_bytes()):
            digest = hashlib.sha256(m.group(1)).digest()
            hashes.add(f"'sha256-{base64.b64encode(digest).decode()}'")
    return sorted(hashes)


class ScriptHashes:
    """Hashes de los scripts en línea, recalculados si cambia el HTML compilado.

    Sin esto, reemplazar el build sin reiniciar deja el script de arranque nuevo fuera de la CSP
    y la página queda en blanco. Revisa las fechas de modificación cada `check_every_s`.
    """

    def __init__(self, web_dir: Callable[[], Path | None], check_every_s: float = 2.0) -> None:
        self.web_dir = web_dir
        self.check_every_s = check_every_s
        self._stamp: tuple[object, ...] | None = None
        self._checked = 0.0
        self._hashes: list[str] = []

    def _stamp_now(self) -> tuple[object, ...]:
        base = self.web_dir()
        if base is None:
            return (None,)
        stamp: list[object] = [str(base)]
        for name in PAGES:
            try:
                stamp.append((base / name).stat().st_mtime_ns)
            except OSError:
                stamp.append(None)
        return tuple(stamp)

    def get(self) -> list[str]:
        now = time.monotonic()
        if self._stamp is None or now - self._checked >= self.check_every_s:
            self._checked = now
            stamp = self._stamp_now()
            if stamp != self._stamp:
                self._stamp = stamp
                self._hashes = inline_script_hashes(self.web_dir())
        return self._hashes


def build_csp(script_hashes: list[str], satellite: bool = True, geocoder: bool = False) -> str:
    esri = f" {ESRI}" if satellite else ""
    search = f" {GEOCODER}" if geocoder else ""
    script_src = " ".join(["'self'", *script_hashes])
    return (
        "default-src 'self'; "
        f"script-src {script_src}; "
        "style-src 'self' 'unsafe-inline'; "
        f"img-src 'self' data: blob:{esri}; "
        f"connect-src 'self'{esri}{search}; "
        "worker-src 'self' blob:; "
        "font-src 'self'; "
        "manifest-src 'self'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )


class SecurityHeaders:
    """Middleware ASGI liviano (no usa BaseHTTPMiddleware, que rompe el streaming SSE)."""

    def __init__(self, app: ASGIApp, csp_provider: object) -> None:
        self.app = app
        self.csp_provider = csp_provider

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        csp = self.csp_provider() if callable(self.csp_provider) else str(self.csp_provider)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {k.lower() for k, _ in headers}
                extra = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"permissions-policy", b"geolocation=(self), camera=(), microphone=()"),
                    (b"x-frame-options", b"DENY"),
                ]
                if b"content-security-policy" not in present:
                    extra.append((b"content-security-policy", csp.encode()))
                headers += [h for h in extra if h[0] not in present]
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


def client_ip(
    scope_client: tuple[str, int] | None, headers: dict[str, str], trusted: list[str]
) -> str:
    """IP del cliente: `CF-Connecting-IP` solo si la petición viene de cloudflared (12.5)."""
    peer = scope_client[0] if scope_client else "0.0.0.0"  # noqa: S104 - valor por defecto, no se escucha
    cf = headers.get("cf-connecting-ip")
    if cf and peer in trusted:
        try:
            ipaddress.ip_address(cf.strip())
            return cf.strip()
        except ValueError:
            return peer
    return peer
