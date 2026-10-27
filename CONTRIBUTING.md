# Cómo contribuir

## Reglas del proyecto

- Toda decisión de arquitectura se registra como ADR en `docs/adr/NNNN-titulo.md` (contexto, decisión, consecuencias).
- No inventar nombres de campos de Meshtastic: usar los del protobuf de la librería `meshtastic` instalada y verificar contra grabaciones (`meshbox inspect`).
- No agregar dependencias sin explicar por qué (ADR).
- Commits chicos con mensajes convencionales: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.
- Ningún secreto en el repositorio: claves WiFi, MQTT, tokens de Cloudflare, claves VAPID, claves de firma. `dev/secrets.toml` y `*.pem` están en `.gitignore`.
- Ningún texto que venga de la radio se inserta como HTML: en Svelte, `{@html}` está prohibido por lint.
- El código corre en Windows (desarrollo) y en Linux arm64 con 512 MB (producción): rutas con `pathlib`, nada de la shell de Linux en el backend.

## Terminado significa

- Pruebas escritas y pasando; `ruff`, `mypy` (estricto), `svelte-check` y `eslint` sin errores.
- Cobertura de al menos 85 % en `pipeline`, `store`, `auth`, `alerts` y `privd` (`scripts/coverage-summary.py`).
- Documentación del usuario y del desarrollador actualizada, y entrada en `CHANGELOG.md`.
- Si toca memoria o rendimiento: medición en una Pi Zero 2 W con `scripts/pi-bench.py`.
- Si toca la Pi: probado en la Pi.

## Entorno

Ver `docs/desarrollo.md`.
