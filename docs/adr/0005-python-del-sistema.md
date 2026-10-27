# ADR 0005 · Python del sistema cuando es 3.13

Estado: aceptada · 20/10/2026

## Contexto

El plan (23.2) instala `uv` y un CPython 3.13 administrado en `/opt/meshbox/python`. Raspberry Pi OS basado en Debian 13 (trixie) ya trae Python 3.13 (3.13.5 en la Pi de pruebas) y `python3-venv`.

## Decisión

El instalador usa `/usr/bin/python3` si su versión es 3.13.x; crea el entorno de cada release con `python3 -m venv` e instala las ruedas incluidas con `pip install --no-index --find-links wheels/`. Solo si el Python del sistema no es 3.13 instala `uv` y un CPython 3.13 administrado, como dice el plan.

## Consecuencias

- Una descarga menos (unos 30 MB) y nada que mantener fuera de `apt` en trixie.
- Las actualizaciones de seguridad de Python llegan por `apt`. Una actualización menor (3.13.x) no rompe el entorno; una mayor (3.14) obliga a recrear el entorno, que es lo que hace cada actualización de meshbox de todos modos.
- `privd` sigue usando `/usr/bin/python3` y solo la biblioteca estándar.
