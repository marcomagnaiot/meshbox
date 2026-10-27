# Desarrollo en Windows (sección 26.3): backend con reproducción + frontend con recarga en caliente.
#   ./scripts/dev.ps1              backend en 127.0.0.1:8000 (LAN) y :8001 (público) + Vite
#   ./scripts/dev.ps1 -SoloBackend
#   ./scripts/dev.ps1 -Rellenar    carga antes 24 h de la red simulada en la base de desarrollo
param(
    [switch]$SoloBackend,
    [switch]$Rellenar,
    [string]$Config = "dev/config.toml"
)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path "dev/data/meshbox.db")) {
    Write-Host "Base de desarrollo nueva: canal público MediumFast y 24 h de historia simulada"
    uv run meshbox channel add --config $Config --name MediumFast --key AQ== --public
    $Rellenar = $true
}
if ($Rellenar) {
    uv run meshbox replay backend/tests/fixtures/sim-24h.jsonl --config $Config --speed max
}

$backend = Start-Process -PassThru -NoNewWindow -FilePath "uv" -ArgumentList @("run", "meshbox", "dev", "--config", $Config)
try {
    if ($SoloBackend) {
        Wait-Process -Id $backend.Id
    } else {
        if (-not (Test-Path "frontend/node_modules")) { pnpm --dir frontend install }
        pnpm --dir frontend dev
    }
} finally {
    if (-not $backend.HasExited) { Stop-Process -Id $backend.Id -Force }
}
