"""Respuestas JSON, errores RFC 9457 y paginación por cursor (sección 12.1)."""

from __future__ import annotations

import logging
from typing import Any

import orjson
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from ..system.privclient import PrivError

log = logging.getLogger(__name__)

NO_STORE = {"Cache-Control": "no-store"}
TITLES = {
    400: "Petición no válida",
    401: "No autenticado",
    403: "Prohibido",
    404: "No encontrado",
    405: "Método no permitido",
    409: "Conflicto",
    413: "Contenido demasiado grande",
    422: "Datos no válidos",
    429: "Demasiadas peticiones",
    500: "Error interno",
    502: "Error del servicio externo",
    503: "Servicio no disponible",
}


def _default(obj: Any) -> Any:
    if isinstance(obj, bytes):
        return obj.hex()
    if isinstance(obj, set | frozenset | tuple):
        return list(obj)
    raise TypeError


def dumps(data: Any) -> bytes:
    return orjson.dumps(data, default=_default, option=orjson.OPT_NON_STR_KEYS)


class JSON(Response):
    media_type = "application/json"

    def render(self, content: Any) -> bytes:
        return dumps(content)


def json_no_store(content: Any, status_code: int = 200) -> JSON:
    return JSON(content, status_code=status_code, headers=NO_STORE)


class ProblemError(Exception):
    def __init__(
        self,
        status: int,
        detail: str | None = None,
        *,
        title: str | None = None,
        type_: str = "about:blank",
        extra: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail or title or str(status))
        self.status = status
        self.detail = detail
        self.title = title or TITLES.get(status, "Error")
        self.type = type_
        self.extra = extra or {}
        self.headers = headers


def problem(
    status: int,
    detail: str | None = None,
    *,
    title: str | None = None,
    type_: str = "about:blank",
    instance: str | None = None,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    body: dict[str, Any] = {
        "type": type_,
        "title": title or TITLES.get(status, "Error"),
        "status": status,
    }
    if detail:
        body["detail"] = detail
    if instance:
        body["instance"] = instance
    if extra:
        body.update(extra)
    return Response(
        dumps(body), status_code=status, media_type="application/problem+json", headers=headers
    )


PRIV_STATUS = {
    "not_allowed_in_shared_mode": 409,
    "busy": 409,
    "invalid_args": 422,
    "unavailable": 503,
    "timeout": 504,
}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemError)
    async def _problem(request: Request, exc: ProblemError) -> Response:
        return problem(
            exc.status,
            exc.detail,
            title=exc.title,
            type_=exc.type,
            instance=request.url.path,
            extra=exc.extra,
            headers=exc.headers,
        )

    @app.exception_handler(PrivError)
    async def _priv(request: Request, exc: PrivError) -> Response:
        # privd rechazó o no pudo ejecutar el comando: el panel muestra su mensaje.
        status = PRIV_STATUS.get(exc.code, 502)
        return problem(
            status,
            f"privd: {exc.message or exc.code}",
            instance=request.url.path,
            extra={"code": exc.code},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> Response:
        detail = exc.detail if isinstance(exc.detail, str) else None
        headers = dict(exc.headers) if exc.headers else None
        return problem(exc.status_code, detail, instance=request.url.path, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> Response:
        errors = [
            {"loc": list(e.get("loc", ())), "msg": e.get("msg"), "type": e.get("type")}
            for e in exc.errors()
        ]
        return problem(
            422, "Revisar los campos indicados", instance=request.url.path, extra={"errors": errors}
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> Response:
        log.exception("error no controlado en %s %s", request.method, request.url.path)
        return problem(500, instance=request.url.path)


# --------------------------------------------------------------------------- cursores


def parse_cursor(cursor: str | None) -> tuple[float, int] | None:
    """`before=<ts>:<pk>`. None si no hay cursor; ProblemError si es inválido."""
    if not cursor:
        return None
    ts_s, _, pk_s = cursor.partition(":")
    try:
        return float(ts_s), int(pk_s or 0)
    except ValueError:
        raise ProblemError(400, "cursor no válido (se espera ts:pk)") from None


def make_cursor(ts: float, pk: int) -> str:
    return f"{ts:.3f}:{pk}"
