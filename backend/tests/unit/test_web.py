"""Estáticos del frontend: precomprimidos, HTML sin transformar, manifiesto y CSP al día."""

from __future__ import annotations

import gzip
import os
import time
from pathlib import Path

import httpx
import pytest

from meshbox.api.factory import create_app
from meshbox.api.security import ScriptHashes, inline_script_hashes
from meshbox.api.web import accepted_encodings
from meshbox.app import Service

from ..conftest import make_cfg

INDEX = b"<!doctype html><html><head><script>boot(1)</script></head><body></body></html>"


def test_accepted_encodings() -> None:
    assert accepted_encodings("gzip, deflate, br;q=1.0, zstd") == {"gzip", "deflate", "br", "zstd"}
    assert accepted_encodings("br;q=0, gzip") == {"gzip"}
    assert accepted_encodings("") == set()


def test_script_hashes_follow_new_build(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_bytes(INDEX)
    hashes = ScriptHashes(lambda: tmp_path, check_every_s=0)
    first = hashes.get()
    assert first == inline_script_hashes(tmp_path) and len(first) == 1
    (tmp_path / "index.html").write_bytes(INDEX.replace(b"boot(1)", b"boot(2)"))
    later = time.time() + 5
    os.utime(tmp_path / "index.html", (later, later))
    assert hashes.get() != first


@pytest.fixture
async def web(tmp_path: Path):  # type: ignore[no-untyped-def]
    site = tmp_path / "web"
    (site / "_app/immutable").mkdir(parents=True)
    (site / "index.html").write_bytes(INDEX)
    (site / "_app/immutable/app.js").write_text("console.log('plano')" * 100)
    (site / "_app/immutable/app.js.br").write_bytes(b"BROTLI")
    (site / "_app/immutable/app.js.gz").write_bytes(gzip.compress(b"plano"))
    (site / "manifest.webmanifest").write_text('{"name": "meshbox", "short_name": "meshbox"}')
    cfg = make_cfg(tmp_path)
    cfg.paths.web = site
    cfg.connectors = []
    cfg.server.admin_remote_bind = ""
    service = Service(cfg, tmp_path / "config.toml", dev=True)
    await service.start()
    service.ready = True
    app = create_app(service, "public")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://pub"
    ) as c:
        yield c, site
    await service.stop()


async def test_precompressed_assets(web) -> None:  # type: ignore[no-untyped-def]
    c, _ = web
    r = await c.get("/_app/immutable/app.js", headers={"Accept-Encoding": "gzip, br"})
    assert r.headers["content-encoding"] == "br" and r.headers["vary"] == "Accept-Encoding"
    assert r.headers["content-type"].startswith(("text/javascript", "application/javascript"))
    r = await c.get("/_app/immutable/app.js", headers={"Accept-Encoding": "gzip"})
    assert r.headers["content-encoding"] == "gzip" and r.text == "plano"
    r = await c.get("/_app/immutable/app.js", headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in r.headers and r.text.startswith("console.log")


async def test_html_no_transform_and_csp(web) -> None:  # type: ignore[no-untyped-def]
    c, site = web
    r = await c.get("/nodos")
    assert r.headers["cache-control"] == "no-cache, no-transform"
    assert inline_script_hashes(site)[0] in r.headers["content-security-policy"]


async def test_manifest_uses_site_name(web) -> None:  # type: ignore[no-untyped-def]
    c, _ = web
    r = await c.get("/manifest.webmanifest")
    data = r.json()
    assert r.headers["content-type"].startswith("application/manifest+json")
    assert data["name"] == "Red Meshtastic" and data["short_name"] == "meshbox"
    assert data["lang"] == "es"


async def test_api_gzip(web) -> None:  # type: ignore[no-untyped-def]
    c, _ = web
    r = await c.get("/api/v1/site", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    if len(r.content) >= 1024:
        assert r.headers.get("content-encoding") == "gzip"
