"""Arma el paquete de release de meshbox para la Raspberry Pi (sección 28.1).

Uso (desde la raíz del repositorio):
    uv run python scripts/build-release.py [--skip-frontend]
        [--sign-key RUTA | --sign-key-env VARIABLE] [--allow-key-mismatch]
        [--pmtiles-version X.Y.Z] [--out release]

Pasos:
 1. Frontend (si existe frontend/package.json): `pnpm install --frozen-lockfile`, `pnpm build` y
    copia de frontend/build/ a backend/src/meshbox/web/.
 2. Rueda de meshbox con `uv build --wheel`.
 3. Dependencias exactas de uv.lock (`uv export --no-dev --no-hashes --frozen`), con los
    marcadores evaluados para Linux aarch64 y CPython 3.13 (`uv pip compile --no-deps
    --python-platform aarch64-manylinux_2_28`): en Windows, `pip download` evaluaría los
    marcadores contra la PC y dejaría afuera, por ejemplo, uvloop y dbus-fast.
 4. Ruedas aarch64 cp313 con `pip download --only-binary=:all:`; las que solo publican sdist
    pura (por ejemplo http-ece) se construyen con `pip wheel --no-deps`.
 5. Binario `pmtiles` arm64 del último release de protomaps/go-pmtiles, verificado con el
    sha256 que publica GitHub para el asset.
 6. release/meshbox-X.Y.Z/ (wheels/ privd/ deploy/ bin/pmtiles install.sh VERSION) ->
    release/meshbox-X.Y.Z-linux-aarch64.tar.gz + release/SHA256SUMS (tar reproducible).
 7. Firma opcional: release/SHA256SUMS.sig (Ed25519, scripts/sign-release.py).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
import urllib.request
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[1]
TARGET_PLATFORM = "aarch64-manylinux_2_28"
PIP_PLATFORMS = ("manylinux_2_28_aarch64", "manylinux2014_aarch64", "manylinux_2_17_aarch64")
PIP_ABIS = ("cp313", "abi3", "none")
PMTILES_REPO = "protomaps/go-pmtiles"
PMTILES_ASSET = re.compile(r"^go-pmtiles_(?P<version>[0-9.]+)_Linux_arm64\.tar\.gz$")
EXECUTABLES = {"install.sh", "bin/pmtiles", "deploy/firstboot/meshbox-firstboot.sh"}
DEPLOY_PARTS = (
    "systemd",
    "mosquitto",
    "journald",
    "nm",
    "firstboot",
    "meshbox-privd.example.toml",
)
PEM_RE = re.compile(r"-----BEGIN PUBLIC KEY-----\n(?P<body>.+?)\n-----END PUBLIC KEY-----", re.S)


class BuildError(Exception):
    pass


def log(message: str) -> None:
    print(f"==> {message}", flush=True)


def warn(message: str) -> None:
    print(f"Aviso: {message}", file=sys.stderr, flush=True)


def run(
    cmd: list[str], *, cwd: Path = REPO, check: bool = True
) -> subprocess.CompletedProcess[str]:
    print("    $ " + " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=cwd, text=True, check=False)
    if check and proc.returncode != 0:
        raise BuildError(f"falló: {' '.join(cmd)} (código {proc.returncode})")
    return proc


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise BuildError(f"no se encontró {name} en el PATH")
    return path


def project_version() -> str:
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    version = data["project"]["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise BuildError(f"versión de pyproject.toml no válida: {version}")
    return str(version)


# ---------------------------------------------------------------------------
# 1. Frontend
# ---------------------------------------------------------------------------


def build_frontend(skip: bool) -> None:
    web = REPO / "backend/src/meshbox/web"
    if skip:
        warn("--skip-frontend: se usa lo que haya en backend/src/meshbox/web/")
        return
    if not (REPO / "frontend/package.json").exists():
        warn("no existe frontend/package.json: el paquete sale sin el sitio web compilado")
        return
    pnpm = require_tool("pnpm")
    log("Frontend: pnpm install y build")
    run([pnpm, "--dir", "frontend", "install", "--frozen-lockfile"])
    run([pnpm, "--dir", "frontend", "build"])
    build = REPO / "frontend/build"
    if not (build / "index.html").exists():
        raise BuildError("el build del frontend no generó frontend/build/index.html")
    for item in web.iterdir():
        if item.name in (".gitkeep", "README.md"):
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    shutil.copytree(build, web, dirs_exist_ok=True)


# ---------------------------------------------------------------------------
# 2-4. Ruedas
# ---------------------------------------------------------------------------


def build_wheel(uv: str, version: str, work: Path) -> Path:
    log("Rueda de meshbox (uv build --wheel)")
    dist = work / "dist"
    shutil.rmtree(dist, ignore_errors=True)
    run([uv, "build", "--wheel", "--out-dir", str(dist)])
    wheel = dist / f"meshbox-{version}-py3-none-any.whl"
    if not wheel.exists():
        raise BuildError(f"no se generó {wheel.name}")
    return wheel


def target_requirements(uv: str, work: Path) -> list[tuple[str, str]]:
    log("Dependencias de uv.lock para linux aarch64 + CPython 3.13")
    locked = work / "requirements-lock.txt"
    target = work / "requirements-aarch64.txt"
    run(
        [
            uv,
            "export",
            "--frozen",
            "--no-dev",
            "--no-hashes",
            "--no-emit-project",
            "--format",
            "requirements.txt",
            "-o",
            str(locked),
        ]
    )
    run(
        [
            uv,
            "pip",
            "compile",
            str(locked),
            "--python-platform",
            TARGET_PLATFORM,
            "--python-version",
            "3.13",
            "--no-deps",
            "--no-header",
            "--no-annotate",
            "--no-config",
            "-o",
            str(target),
        ]
    )
    pins = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;]+)", line)
        if not match:
            raise BuildError(f"línea inesperada en los requisitos: {line}")
        pins.append((match.group(1), match.group(2)))
    if not pins:
        raise BuildError("no hay dependencias para descargar")
    return pins


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "_", name).lower()


def wheel_tags(filename: str) -> tuple[str, str, str, str, str] | None:
    """(nombre, versión, python, abi, plataforma) de un nombre de rueda."""
    if not filename.endswith(".whl"):
        return None
    parts = filename[:-4].split("-")
    if len(parts) == 6:
        parts = [parts[0], parts[1], parts[3], parts[4], parts[5]]  # sin número de build
    if len(parts) != 5:
        return None
    return normalize(parts[0]), parts[1], parts[2], parts[3], parts[4]


_MANYLINUX = re.compile(r"^manylinux_2_(\d+)_aarch64$")
MAX_GLIBC_MINOR = 28  # manylinux_2_28: Debian 12 tiene glibc 2.36 y Debian 13, 2.41


def platform_rank(tag: str) -> int | None:
    """Menor es mejor (glibc más nuevo, hasta 2.28); None si no sirve en la Pi."""
    if tag == "any":
        return 1000
    if tag == "manylinux2014_aarch64":
        tag = "manylinux_2_17_aarch64"
    match = _MANYLINUX.fullmatch(tag)
    if match is None:
        return None
    minor = int(match.group(1))
    return MAX_GLIBC_MINOR - minor if minor <= MAX_GLIBC_MINOR else None


def wheel_score(platform: str, abi: str) -> tuple[int, int] | None:
    """Menor es mejor; None si la rueda no sirve para aarch64 + cp313."""
    plat_ranks = [r for r in (platform_rank(p) for p in platform.split(".")) if r is not None]
    abi_ranks = [PIP_ABIS.index(a) for a in abi.split(".") if a in PIP_ABIS]
    if not plat_ranks or not abi_ranks:
        return None
    return min(plat_ranks), min(abi_ranks)


def find_wheel(cache: Path, name: str, version: str) -> Path | None:
    best: tuple[tuple[int, int], Path] | None = None
    for path in cache.glob("*.whl"):
        tags = wheel_tags(path.name)
        if tags is None or tags[0] != normalize(name) or tags[1] != version:
            continue
        score = wheel_score(tags[4], tags[3])
        if score is None:
            continue
        if best is None or score < best[0]:
            best = (score, path)
    return best[1] if best else None


def pip_command(uv: str) -> list[str]:
    return [uv, "tool", "run", "--python", "3.13", "--from", "pip", "pip"]


def download_binary_wheels(pip: list[str], requirements: Path, cache: Path) -> bool:
    cmd = [
        *pip,
        "download",
        "--disable-pip-version-check",
        "--no-deps",
        "--only-binary=:all:",
        "--python-version",
        "3.13",
        "--implementation",
        "cp",
        "-d",
        str(cache),
    ]
    for platform in PIP_PLATFORMS:
        cmd += ["--platform", platform]
    for abi in PIP_ABIS:
        cmd += ["--abi", abi]
    cmd += ["-r", str(requirements)]
    return run(cmd, check=False).returncode == 0


def build_pure_wheel(pip: list[str], name: str, version: str, cache: Path, work: Path) -> None:
    """Para paquetes que solo publican sdist: se construye la rueda y se exige que sea pura."""
    log(f"{name}=={version} no tiene rueda: se construye desde el sdist")
    out = work / "pure-wheels"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    run(
        [
            *pip,
            "wheel",
            "--disable-pip-version-check",
            "--no-deps",
            "--no-binary",
            name,
            "-w",
            str(out),
            f"{name}=={version}",
        ]
    )
    built = list(out.glob("*.whl"))
    if len(built) != 1:
        raise BuildError(f"no se pudo construir la rueda de {name}")
    tags = wheel_tags(built[0].name)
    if tags is None or tags[3] != "none" or tags[4] != "any":
        raise BuildError(f"{name} no tiene rueda aarch64 y su sdist no es pura: {built[0].name}")
    shutil.copy2(built[0], cache / built[0].name)


def collect_wheels(uv: str, pins: list[tuple[str, str]], work: Path, cache: Path) -> list[Path]:
    log(f"Ruedas aarch64 cp313 ({len(pins)} paquetes; caché en {cache})")
    cache.mkdir(parents=True, exist_ok=True)
    pip = pip_command(uv)
    missing = [(n, v) for n, v in pins if find_wheel(cache, n, v) is None]
    if missing:
        requirements = work / "requirements-missing.txt"
        requirements.write_text("".join(f"{n}=={v}\n" for n, v in missing), encoding="utf-8")
        if not download_binary_wheels(pip, requirements, cache):
            # Alguno no tiene rueda: de a uno para saber cuál.
            for name, version in missing:
                if find_wheel(cache, name, version) is not None:
                    continue
                single = work / "requirement-single.txt"
                single.write_text(f"{name}=={version}\n", encoding="utf-8")
                if not download_binary_wheels(pip, single, cache):
                    build_pure_wheel(pip, name, version, cache, work)
    wheels = []
    for name, version in pins:
        found = find_wheel(cache, name, version)
        if found is None:
            raise BuildError(f"falta la rueda de {name}=={version}")
        wheels.append(found)
    return wheels


# ---------------------------------------------------------------------------
# 5. pmtiles
# ---------------------------------------------------------------------------


def github_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        request.add_unredirected_header("Authorization", f"Bearer {token}")
    # URL fija de la API de GitHub.
    with urllib.request.urlopen(request, timeout=60) as resp:  # nosec B310
        return json.loads(resp.read())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_pmtiles(version: str | None, cache: Path, work: Path) -> tuple[Path, str]:
    tag = f"tags/v{version}" if version else "latest"
    log(f"pmtiles arm64 ({PMTILES_REPO}, {tag})")
    release = github_json(f"https://api.github.com/repos/{PMTILES_REPO}/releases/{tag}")
    assets = release.get("assets", [])
    asset = next((a for a in assets if PMTILES_ASSET.fullmatch(a.get("name", ""))), None)
    if asset is None:
        raise BuildError("el release de go-pmtiles no tiene el asset Linux_arm64")
    expected = (asset.get("digest") or "").removeprefix("sha256:").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        expected = _sha_from_checksums(assets, asset["name"])
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / asset["name"]
    if not archive.exists() or sha256_file(archive) != expected:
        url = asset["browser_download_url"]  # asset de GitHub; se verifica su sha256
        with urllib.request.urlopen(url, timeout=120) as resp:  # nosec B310
            archive.write_bytes(resp.read())
    actual = sha256_file(archive)
    if actual != expected:
        raise BuildError(f"la suma de {asset['name']} no coincide ({actual} != {expected})")
    out = work / "pmtiles"
    with tarfile.open(archive, "r:gz") as tar:
        member = next((m for m in tar.getmembers() if Path(m.name).name == "pmtiles"), None)
        if member is None or not member.isfile():
            raise BuildError(f"{asset['name']} no contiene el binario pmtiles")
        source = tar.extractfile(member)
        if source is None:
            raise BuildError("no se pudo leer pmtiles del archivo")
        out.write_bytes(source.read())
    match = PMTILES_ASSET.fullmatch(asset["name"])
    return out, match.group("version") if match else "?"


def _sha_from_checksums(assets: list[dict], name: str) -> str:
    sums = next((a for a in assets if "checksums" in a.get("name", "").lower()), None)
    if sums is None:
        raise BuildError(f"GitHub no publica la suma de {name} y no hay checksums.txt")
    url = sums["browser_download_url"]  # asset de GitHub
    with urllib.request.urlopen(url, timeout=60) as resp:  # nosec B310
        text = resp.read().decode()
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == name:
            return parts[0].lower()
    raise BuildError(f"{name} no figura en {sums['name']}")


# ---------------------------------------------------------------------------
# 6. Paquete
# ---------------------------------------------------------------------------


def embedded_keys() -> tuple[str, str]:
    privd = PEM_RE.search((REPO / "privd/commands/update.py").read_text(encoding="utf-8"))
    install = PEM_RE.search((REPO / "deploy/install.sh").read_text(encoding="utf-8"))
    if privd is None or install is None:
        raise BuildError("no se encontró la clave pública embebida en privd o install.sh")
    return privd.group("body").strip(), install.group("body").strip()


def copy_privd(dest: Path, version: str) -> None:
    (dest / "commands").mkdir(parents=True)
    shutil.copy2(REPO / "privd/meshbox_privd.py", dest / "meshbox_privd.py")
    for source in sorted((REPO / "privd/commands").glob("*.py")):
        text = source.read_text(encoding="utf-8")
        if source.name == "core.py":
            text, count = re.subn(
                r'^PRIVD_VERSION = "[^"]*"$', f'PRIVD_VERSION = "{version}"', text, flags=re.M
            )
            if count != 1:
                raise BuildError("no se pudo fijar PRIVD_VERSION en privd/commands/core.py")
        (dest / "commands" / source.name).write_text(text, encoding="utf-8", newline="\n")


def copy_deploy(dest: Path) -> None:
    dest.mkdir(parents=True)
    for part in DEPLOY_PARTS:
        source = REPO / "deploy" / part
        if source.is_dir():
            shutil.copytree(source, dest / part)
        else:
            shutil.copy2(source, dest / part)


def assemble(
    version: str, out: Path, wheels: list[Path], meshbox_wheel: Path, pmtiles: Path | None
) -> Path:
    root = out / f"meshbox-{version}"
    shutil.rmtree(root, ignore_errors=True)
    (root / "wheels").mkdir(parents=True)
    (root / "bin").mkdir()
    (root / "VERSION").write_text(f"{version}\n", encoding="utf-8", newline="\n")
    shutil.copy2(REPO / "deploy/install.sh", root / "install.sh")
    for wheel in [*wheels, meshbox_wheel]:
        shutil.copy2(wheel, root / "wheels" / wheel.name)
    copy_privd(root / "privd", version)
    copy_deploy(root / "deploy")
    if pmtiles is not None:
        shutil.copy2(pmtiles, root / "bin/pmtiles")
    return root


def source_date_epoch() -> int:
    value = os.environ.get("SOURCE_DATE_EPOCH")
    if value and value.isdigit():
        return int(value)
    proc = subprocess.run(
        ["git", "log", "-1", "--format=%ct"], cwd=REPO, capture_output=True, text=True, check=False
    )
    return int(proc.stdout.strip()) if proc.returncode == 0 and proc.stdout.strip() else 0


def make_tarball(root: Path, tarball: Path, mtime: int) -> None:
    """tar.gz reproducible: orden fijo, dueño root, permisos normalizados, mtime fijo."""
    entries = sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix())
    with (
        open(tarball, "wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as gz,
        tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar,
    ):
        for path in [root, *entries]:
            rel = path.relative_to(root).as_posix()
            arcname = root.name if rel == "." else f"{root.name}/{rel}"
            info = tarfile.TarInfo(arcname)
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            info.mtime = mtime
            if path.is_dir():
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                tar.addfile(info)
            else:
                info.size = path.stat().st_size
                info.mode = 0o755 if rel in EXECUTABLES else 0o644
                with open(path, "rb") as fh:
                    tar.addfile(info, fh)


# ---------------------------------------------------------------------------
# 7. Firma
# ---------------------------------------------------------------------------


def load_signer() -> ModuleType:
    path = REPO / "scripts/sign-release.py"
    spec = importlib.util.spec_from_file_location("sign_release", path)
    if spec is None or spec.loader is None:
        raise BuildError("no se pudo cargar scripts/sign-release.py")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except ImportError as exc:
        raise BuildError("para firmar hace falta cryptography (uv run ...)") from exc
    return module


def sign(sums: Path, key_path: Path | None, key_env: str | None, allow_mismatch: bool) -> Path:
    signer = load_signer()
    key = signer.load_private_key(path=key_path, env=key_env)
    public = signer.public_pem(key.public_key())
    body = PEM_RE.search(public)
    privd_key, _ = embedded_keys()
    if body is None or body.group("body").strip() != privd_key:
        if not allow_mismatch:
            raise BuildError(
                "la clave de firma no corresponde a la pública embebida en privd e install.sh "
                "(para un release de transición de claves usa --allow-key-mismatch)"
            )
        warn("la clave de firma no es la embebida (--allow-key-mismatch)")
    signature = signer.sign_file(sums, key)
    if not signer.verify_file(sums, signature, key.public_key()):
        raise BuildError("la firma recién creada no verifica")
    return signature


# ---------------------------------------------------------------------------
# Principal
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Arma el paquete de release de meshbox.")
    parser.add_argument("--skip-frontend", action="store_true", help="no compila el frontend")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--sign-key", type=Path, help="clave privada Ed25519 (PEM) para firmar")
    group.add_argument("--sign-key-env", help="variable de entorno con la clave privada (PEM)")
    parser.add_argument(
        "--allow-key-mismatch",
        action="store_true",
        help="permite firmar con una clave distinta de la embebida (rotación de claves)",
    )
    parser.add_argument("--pmtiles-version", help="versión de go-pmtiles (por defecto la última)")
    parser.add_argument("--skip-pmtiles", action="store_true", help="paquete sin bin/pmtiles")
    parser.add_argument("--out", type=Path, default=REPO / "release", help="carpeta de salida")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    args = parse_args(argv)
    try:
        version = project_version()
        privd_key, install_key = embedded_keys()
        if privd_key != install_key:
            raise BuildError("la clave pública de privd y la de install.sh no coinciden")
        uv = require_tool("uv")
        out = args.out.resolve()
        work = out / ".work"
        cache = out / ".cache"
        work.mkdir(parents=True, exist_ok=True)
        log(f"meshbox {version}")

        build_frontend(args.skip_frontend)
        meshbox_wheel = build_wheel(uv, version, work)
        pins = target_requirements(uv, work)
        wheels = collect_wheels(uv, pins, work, cache / "wheels-cp313-aarch64")
        pmtiles: Path | None = None
        if args.skip_pmtiles:
            warn("--skip-pmtiles: el paquete sale sin bin/pmtiles")
        else:
            pmtiles, pmtiles_version = fetch_pmtiles(args.pmtiles_version, cache / "pmtiles", work)
            log(f"pmtiles {pmtiles_version} verificado")

        log("Armando el paquete")
        root = assemble(version, out, wheels, meshbox_wheel, pmtiles)
        tarball = out / f"meshbox-{version}-linux-aarch64.tar.gz"
        make_tarball(root, tarball, source_date_epoch())
        sums = out / "SHA256SUMS"
        sums.write_text(f"{sha256_file(tarball)}  {tarball.name}\n", encoding="utf-8", newline="\n")
        stale_sig = out / "SHA256SUMS.sig"
        if args.sign_key or args.sign_key_env:
            signature = sign(sums, args.sign_key, args.sign_key_env, args.allow_key_mismatch)
            log(f"Firma: {signature}")
        elif stale_sig.exists():
            stale_sig.unlink()  # una firma vieja no corresponde a este SHA256SUMS
            warn("paquete sin firmar (se borró la firma anterior)")
        else:
            warn("paquete sin firmar: en la Pi hace falta --insecure-skip-signature")
        size_mb = tarball.stat().st_size / 1e6
        log(f"Listo: {tarball} ({size_mb:.1f} MB, {len(wheels) + 1} ruedas)")
        print(tarball)
        return 0
    except BuildError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
