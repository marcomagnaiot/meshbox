"""Proxy CONNECT para pmtiles: túnel solo hacia el host y el puerto permitidos."""

from __future__ import annotations

import asyncio

from meshbox.system.connect_proxy import ConnectProxy


async def _echo_server() -> tuple[asyncio.Server, int]:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        while data := await reader.read(1024):
            writer.write(data)
            await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


async def _connect(
    proxy_url: str, target: str
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter, bytes]:
    port = int(proxy_url.rsplit(":", 1)[1])
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
    await writer.drain()
    status = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
    return reader, writer, status


async def test_tunnel_to_allowed_host() -> None:
    server, port = await _echo_server()
    async with server, ConnectProxy("127.0.0.1", port) as url:
        reader, writer, status = await _connect(url, f"127.0.0.1:{port}")
        assert status.startswith(b"HTTP/1.1 200")
        writer.write(b"hola por el tunel")
        await writer.drain()
        assert await asyncio.wait_for(reader.readexactly(17), 5) == b"hola por el tunel"
        writer.close()


async def test_rejects_other_host_or_port() -> None:
    server, port = await _echo_server()
    async with server, ConnectProxy("127.0.0.1", port) as url:
        _, w1, status = await _connect(url, "example.com:443")
        assert status.startswith(b"HTTP/1.1 403")
        w1.close()
        _, w2, status = await _connect(url, f"127.0.0.1:{port + 1}")
        assert status.startswith(b"HTTP/1.1 403")
        w2.close()
