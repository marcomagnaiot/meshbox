# ADR 0003 · Verificación de ruedas aarch64 para Python 3.13

Estado: aceptada · 20/10/2026

## Contexto

La sección 6.1 exige que todas las dependencias de producción tengan ruedas `manylinux aarch64` para CPython 3.13, para no compilar nada en la Raspberry.

## Verificación

En la Raspberry Pi Zero 2 W de destino (Debian 13 trixie, Python 3.13.5 del sistema) se creó un entorno temporal y se instaló con `pip install --only-binary=:all:` el conjunto completo:

`fastapi uvicorn[standard] pydantic pydantic-settings sqlalchemy aiosqlite alembic aiomqtt meshtastic cryptography argon2-cffi httpx sse-starlette pywebpush orjson psutil tomli-w pmtiles pyjwt[crypto]`

Resultado: 67 paquetes, 141 MB en disco, **ninguno requirió compilación**. Con `--only-binary=:all:` cualquier paquete sin rueda habría hecho fallar la instalación.

Mediciones en la Pi durante la misma prueba:

| Medida | Valor |
|---|---|
| RSS tras importar FastAPI, uvicorn y pydantic | 45,8 MB |
| + SQLAlchemy | 58,0 MB |
| + aiomqtt, httpx, cryptography, pyjwt, argon2, pmtiles | 70,2 MB |
| + protobuf de meshtastic | 80,9 MB |
| + `SerialInterface` | 81,1 MB |
| + pywebpush | 89,6 MB |
| Dos servidores uvicorn escuchando | 93,6 MB |
| argon2id (`t=3`, `m=32 MiB`, `p=1`) | 0,61 s por hash y por verificación |
| Import en frío (sin serial ni push) | 6,7 s |

## Decisión

No hay excepciones: todas las dependencias tienen rueda. El release incluirá las ruedas descargadas en la PC o en CI (`pip download --only-binary=:all: --platform manylinux_2_28_aarch64 --platform manylinux2014_aarch64 --python-version 3.13`), porque la descarga desde la Pi resultó lenta e inestable (reintentos en varias peticiones a PyPI).

## Consecuencias

- El presupuesto de 180 MB de RSS (5.5) deja unos 85 MB para datos, cachés y clientes SSE.
- `pywebpush` y la interfaz serie se importan solo cuando se usan, para no pagar su memoria si no hacen falta.
- Las migraciones (Alembic) corren en un proceso aparte antes de arrancar, para no dejar Alembic y Mako en la memoria del servicio (ADR 0010).
