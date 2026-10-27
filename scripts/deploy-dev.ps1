<#
.SYNOPSIS
    Arma meshbox sin firmar y lo instala en la Raspberry Pi por SSH (solo desarrollo).

.DESCRIPTION
    1. Arma el paquete con scripts/build-release.py (sin firma).
    2. Lo copia con scp a ~/meshbox-deploy/ en la Pi (nunca a /tmp, que es RAM).
    3. Ejecuta install.sh por ssh con sudo -S: la clave de sudo se pide con Read-Host
       -AsSecureString y viaja por la entrada estándar de ssh, nunca en la línea de comandos.

    Requiere ssh y scp (OpenSSH de Windows) con acceso por clave a la Pi, y uv en el PATH.
    install.sh se ejecuta con --insecure-skip-signature: verifica la suma SHA-256, no la firma.

.PARAMETER Pi
    Host o alias de ~/.ssh/config (por ejemplo mipi o usuario@192.168.0.10).

.PARAMETER Mode
    shared (equipo compartido, puertos 8090-8092) o appliance (equipo dedicado).

.PARAMETER SkipBuild
    Usa el paquete que ya está en release/ sin volver a armarlo.

.PARAMETER SkipFrontend
    Arma sin compilar el frontend (usa lo que haya en backend/src/meshbox/web).

.PARAMETER SiteSlug
    Identificador del sitio para el bootstrap (por ejemplo mizona).

.EXAMPLE
    ./scripts/deploy-dev.ps1 -Pi mipi
#>
[CmdletBinding()]
param(
    [string]$Pi = 'mipi',
    [ValidateSet('shared', 'appliance')]
    [string]$Mode = 'shared',
    [switch]$SkipBuild,
    [switch]$SkipFrontend,
    [string]$SiteSlug = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Invoke-Native {
    param([string]$File, [string[]]$Arguments)
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Falló: $File $($Arguments -join ' ') (código $LASTEXITCODE)"
    }
}

# El nombre del equipo y el slug van dentro del comando remoto: solo caracteres seguros.
if ($Pi -notmatch '^[A-Za-z0-9._@-]+$') {
    throw "Nombre de equipo no válido: $Pi"
}
if ($SiteSlug -and $SiteSlug -notmatch '^[a-z0-9][a-z0-9-]{0,31}$') {
    throw "SiteSlug no válido: $SiteSlug"
}

$repo = Split-Path -Parent $PSScriptRoot
$versionMatch = Select-String -Path (Join-Path $repo 'pyproject.toml') -Pattern '^version = "(\d+\.\d+\.\d+)"'
if (-not $versionMatch) {
    throw 'No se encontró la versión en pyproject.toml'
}
$version = $versionMatch.Matches[0].Groups[1].Value
$name = "meshbox-$version-linux-aarch64.tar.gz"
$releaseDir = Join-Path $repo 'release'
$tarball = Join-Path $releaseDir $name
$sums = Join-Path $releaseDir 'SHA256SUMS'

if (-not $SkipBuild) {
    Write-Host "==> Armando meshbox $version (sin firma)"
    $buildArgs = @('run', '--no-project', '--python', '3.13', 'python', 'scripts/build-release.py')
    if ($SkipFrontend) {
        $buildArgs += '--skip-frontend'
    }
    Push-Location $repo
    try {
        Invoke-Native -File 'uv' -Arguments $buildArgs
    }
    finally {
        Pop-Location
    }
}
foreach ($file in @($tarball, $sums)) {
    if (-not (Test-Path -LiteralPath $file)) {
        throw "No existe $file (arma el paquete o quita -SkipBuild)"
    }
}

$remoteDir = 'meshbox-deploy'
Write-Host "==> Copiando el paquete a ${Pi}:~/$remoteDir/"
Invoke-Native -File 'ssh' -Arguments @($Pi, "mkdir -p ~/$remoteDir && rm -f ~/$remoteDir/SHA256SUMS.sig")
Invoke-Native -File 'scp' -Arguments @($tarball, $sums, "${Pi}:$remoteDir/")

$installArgs = "--$Mode --from ~/$remoteDir/$name --insecure-skip-signature"
if ($SiteSlug) {
    $installArgs += " --site-slug $SiteSlug"
}
# El install.sh del paquete se extrae al lado; `sudo -k -S` siempre lee la clave de stdin.
$remote = "cd ~/$remoteDir && rm -rf meshbox-$version && " +
    "tar -xzf $name meshbox-$version/install.sh && " +
    "sudo -k -S -p '' bash meshbox-$version/install.sh $installArgs"

$secure = Read-Host -AsSecureString "Clave de sudo en $Pi"
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
$previousEncoding = $OutputEncoding
try {
    # UTF-8 sin BOM para que una clave con acentos llegue igual a sudo.
    $OutputEncoding = New-Object System.Text.UTF8Encoding $false
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    Write-Host "==> Ejecutando install.sh --$Mode en $Pi"
    $plain | & ssh -T $Pi $remote
    $code = $LASTEXITCODE
}
finally {
    $plain = $null
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    $OutputEncoding = $previousEncoding
}
if ($code -ne 0) {
    throw "install.sh terminó con código $code en $Pi"
}
Write-Host "==> Listo: meshbox $version instalado en $Pi (modo $Mode)"
