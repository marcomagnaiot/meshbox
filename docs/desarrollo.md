# Desarrollo

Entorno: Windows con PowerShell (también funciona en Linux y macOS). El código corre igual en la PC y en la Pi: rutas con `pathlib`, sin dependencias de la shell de Linux en el backend.

## Herramientas

| Herramienta | Uso |
|---|---|
| `uv` | Python 3.13, entorno y dependencias (`uv sync`) |
| Node 22 + pnpm | Frontend (`pnpm --dir frontend install`) |
| Mosquitto para Windows (opcional) | Pruebas con un broker local |
| CLI de Meshtastic (`uv tool install meshtastic`) | Configurar el Heltec |
| VS Code: Python, Pylance, Ruff, Svelte, Tailwind CSS, Playwright | |

## Arrancar

```powershell
uv sync
./scripts/dev.ps1                 # backend (reproducción x10) + frontend con recarga en caliente
./scripts/dev.ps1 -SoloBackend
```

| Servidor | Dirección |
|---|---|
| LAN simulada (público + panel) | http://127.0.0.1:8000 |
| Público | http://127.0.0.1:8001 |
| Vite (frontend) | http://localhost:5173 (reenvía `/api` y `/tiles` al 8000) |
| OpenAPI | http://127.0.0.1:8000/api/docs (en modo dev no pide sesión) |

En Windows `privd` es simulado (`system/privclient.py`): los comandos se registran y devuelven respuestas de prueba.

Para tener un usuario: `uv run meshbox user create admin --config dev/config.toml` (pide la contraseña), o el asistente en `/setup` con el código que figura en `dev/secrets.toml` (`setup_code`).

## Modos de trabajo (26.2)

| Modo | Cómo | Para qué |
|---|---|---|
| Reproducción | conector `replay` con `backend/tests/fixtures/*.jsonl` (activo en `dev/config.toml`) | Desarrollo diario sin radio |
| MQTT remoto | conector `mqtt-pi` contra el Mosquitto de la Pi con la cuenta `dbg-dev` (solo lectura): `enabled = true` en `dev/config.toml` | Datos reales sin tocar la Pi |
| USB | conector serie con el Heltec en `COMx` | Probar el conector USB |

## Comandos útiles

```powershell
uv run meshbox record --connector mqtt-pi --config dev/config.toml --duration 3600   # graba 1 h real
uv run meshbox inspect dev/data/rec/20261020-1200.jsonl                              # decodifica cada paquete
uv run meshbox replay archivo.jsonl --config dev/config.toml --speed max              # carga en la base
uv run meshbox simulate generate --out sim.jsonl --hours 24 --seed 1                  # red simulada
uv run meshbox simulate publish --file sim.jsonl --host 192.168.0.10 --username gw-sim --password-stdin --speed 10
uv run meshbox channel list --config dev/config.toml
uv run meshbox backup create --config dev/config.toml
```

## Pruebas y calidad

```powershell
uv run pytest                              # backend (unitarias, integración, hypothesis)
uv run pytest --cov=meshbox --cov-report=term-missing
uv run ruff check backend; uv run ruff format backend
uv run mypy                                # estricto
pnpm --dir frontend check; pnpm --dir frontend lint; pnpm --dir frontend test
pnpm --dir frontend e2e                    # Playwright contra el backend real con reproducción
```

Las pruebas del backend usan una base SQLite temporal, `privd` simulado y la red simulada de `backend/tests/fixtures/sim-24h.jsonl` (ADR 0008). `real-vectors.json` tiene paquetes cifrados reales emitidos por firmware para verificar el descifrado.

## Estructura

Ver `docs/arquitectura.md`. Reglas del proyecto (`CONTRIBUTING.md`): commits chicos y convencionales, ningún secreto en el repositorio, nada de `{@html}` sobre datos, toda decisión de arquitectura como ADR en `docs/adr/`.

## Desplegar en la Pi

`./scripts/deploy-dev.ps1 -Pi mipi` compila, arma el paquete, lo copia a la Pi y ejecuta el instalador en modo compartido (pide la contraseña de sudo; nunca la guarda). Ver `docs/instalacion.md`.

## Releases

`scripts/build-release.py` arma `meshbox-X.Y.Z-linux-aarch64.tar.gz` con las ruedas aarch64, `privd`, `deploy/` y el binario `pmtiles`; `scripts/sign-release.py` firma `SHA256SUMS` con Ed25519. En GitHub lo hace `release.yml` al etiquetar `vX.Y.Z`.
