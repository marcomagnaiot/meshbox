"""Actualizaciones (sección 23.5): consulta de releases y pedido de instalación a privd.

La aplicación solo lista versiones y pide a privd que instale: la descarga, la verificación
de la firma Ed25519 y el cambio de versión los hace privd con la clave pública embebida.
"""

from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING, Any

import httpx

from ..system.privclient import PrivError

if TYPE_CHECKING:
    from ..app import Service

log = logging.getLogger(__name__)
VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
CACHE_S = 3600


def parse_version(v: str) -> tuple[int, int, int] | None:
    m = VERSION_RE.match(v.strip())
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


class Updates:
    def __init__(self, service: Service) -> None:
        self.service = service
        self._cache: tuple[float, list[dict[str, Any]]] | None = None
        self.last_error: str | None = None
        self.jobs: dict[str, dict[str, Any]] = {}

    async def releases(self, force: bool = False) -> list[dict[str, Any]]:
        if self._cache and not force and time.time() - self._cache[0] < CACHE_S:
            return self._cache[1]
        url = self.service.cfg.updates.source
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                r = await client.get(url, headers={"Accept": "application/vnd.github+json"})
                r.raise_for_status()
                data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            self.last_error = f"no se pudo consultar {url}: {e}"
            log.warning(self.last_error)
            return self._cache[1] if self._cache else []
        out = []
        for rel in data if isinstance(data, list) else []:
            tag = str(rel.get("tag_name", ""))
            ver = parse_version(tag)
            if ver is None or rel.get("draft"):
                continue
            assets = {a.get("name"): a.get("browser_download_url") for a in rel.get("assets", [])}
            out.append(
                {
                    "version": ".".join(map(str, ver)),
                    "tag": tag,
                    "name": rel.get("name") or tag,
                    "notes": (rel.get("body") or "")[:20_000],
                    "published_at": rel.get("published_at"),
                    "prerelease": bool(rel.get("prerelease")),
                    "has_package": any(n and n.endswith("-linux-aarch64.tar.gz") for n in assets),
                    "signed": "SHA256SUMS.sig" in assets,
                }
            )
        out.sort(key=lambda r: parse_version(r["version"]) or (0, 0, 0), reverse=True)
        self._cache = (time.time(), out)
        self.last_error = None
        return out

    async def status(self) -> dict[str, Any]:
        current = self.service.version
        releases = await self.releases()
        cur = parse_version(current) or (0, 0, 0)
        newer = [
            r
            for r in releases
            if (parse_version(r["version"]) or (0, 0, 0)) > cur and not r["prerelease"]
        ]
        try:
            # Lo instalado en el equipo (versiones para volver atrás, último trabajo).
            local = await self.service.priv.call("update.info")
        except PrivError as e:
            local = {"error": e.message}
        return {
            "current": current,
            "local": local,
            "latest": releases[0]["version"] if releases else None,
            "update_available": bool(newer),
            "releases": releases[:10],
            "auto_check": self.service.cfg.updates.auto_check,
            "source": self.service.cfg.updates.source,
            "error": self.last_error,
        }

    async def install(self, version: str) -> dict[str, Any]:
        if parse_version(version) is None:
            raise ValueError("versión no válida")
        result = await self.service.priv.call("update.apply", version=version)
        job = str(result.get("job", ""))
        self.jobs[job] = {"job": job, "version": version, "started_at": time.time()}
        return result

    async def job_status(self, job: str) -> dict[str, Any]:
        return await self.service.priv.call("update.status", job=job)

    async def rollback(self) -> dict[str, Any]:
        return await self.service.priv.call("update.rollback")
