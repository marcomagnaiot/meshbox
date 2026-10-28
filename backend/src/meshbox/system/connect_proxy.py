"""Proxy CONNECT local y efímero para un programa en Go (pmtiles).

El resolvedor DNS propio de Go no usa el del sistema, y algunos routers hogareños rechazan sus
consultas ("server misbehaving") aunque respondan bien a las de glibc. Con HTTPS_PROXY apuntando
acá, el programa le pide a este proxy el túnel hacia el servidor y el nombre lo resuelve Python
con el resolvedor del sistema. El TLS sigue siendo de punta a punta entre el programa y el
servidor: el proxy solo copia bytes, y únicamente hacia el host y el puerto permitidos.
"""

from __future__ import annotations

import asyncio
import contextlib
from types import TracebackType

CHUNK = 64 * 1024
TIMEOUT_S = 30


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(CHUNK):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, OSError):
        pass
    finally:
        with contextlib.suppress(Exception):
            writer.close()


class ConnectProxy:
    """`async with ConnectProxy("build.protomaps.com") as url:` da `http://127.0.0.1:<puerto>`."""

    def __init__(self, host: str, port: int = 443) -> None:
        self.host = host.lower()
        self.port = port
        self._server: asyncio.Server | None = None

    async def __aenter__(self) -> str:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        port = self._server.sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}"

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._server.wait_closed(), 5)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        upstream: asyncio.StreamWriter | None = None
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), TIMEOUT_S)
            method, target, _ = head.split(b"\r\n", 1)[0].decode("latin-1").split(" ", 2)
            host, _, port = target.rpartition(":")
            if method != "CONNECT" or host.lower() != self.host or port != str(self.port):
                writer.write(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                await writer.drain()
                return
            up_reader, up_writer = await asyncio.wait_for(
                asyncio.open_connection(host, self.port), TIMEOUT_S
            )
            upstream = up_writer
            writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            await writer.drain()
            await asyncio.gather(_pipe(reader, up_writer), _pipe(up_reader, writer))
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, TimeoutError, ValueError):
            with contextlib.suppress(Exception):
                writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
        except OSError:
            with contextlib.suppress(Exception):
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
        finally:
            for w in (writer, upstream):
                if w is not None:
                    with contextlib.suppress(Exception):
                        w.close()
