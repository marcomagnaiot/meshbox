"""Claves y firmas Ed25519 de los releases de meshbox (sección 28.3).

Uso:
    python scripts/sign-release.py --generate --out-dir <directorio fuera del repo> [--name N]
    python scripts/sign-release.py sign release/SHA256SUMS --key <privada.pem>
    python scripts/sign-release.py sign release/SHA256SUMS --key-env MESHBOX_SIGNING_KEY
    python scripts/sign-release.py verify release/SHA256SUMS --sig release/SHA256SUMS.sig \
        --pub <publica.pem>
    python scripts/sign-release.py pubkey --key <privada.pem>

La firma es Ed25519 pura sobre el archivo SHA256SUMS: 64 bytes crudos en SHA256SUMS.sig, que se
verifican en la Pi con OpenSSL 3:
    openssl pkeyutl -verify -pubin -inkey publica.pem -rawin -in SHA256SUMS -sigfile SHA256SUMS.sig
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

REPO_ROOT = Path(__file__).resolve().parents[1]
SIGNATURE_SIZE = 64


class SignError(Exception):
    pass


def _is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _restrict_private_file(path: Path) -> None:
    """0600 en POSIX; en Windows deja la ACL solo para el usuario actual (si se puede)."""
    if os.name == "posix":
        os.chmod(path, 0o600)
        return
    user = os.environ.get("USERNAME")
    if not user:
        return
    subprocess.run(
        ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"],
        check=False,
        capture_output=True,
    )


def public_pem(public_key: Ed25519PublicKey) -> str:
    return public_key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode("ascii")


def generate(out_dir: Path, name: str, *, force: bool = False) -> tuple[Path, Path, str]:
    if _is_inside(out_dir, REPO_ROOT):
        raise SignError(f"{out_dir} está dentro del repositorio: la clave privada no va ahí")
    out_dir.mkdir(parents=True, exist_ok=True)
    private_path = out_dir / f"{name}-private.pem"
    public_path = out_dir / f"{name}-public.pem"
    for path in (private_path, public_path):
        if path.exists() and not force:
            raise SignError(f"{path} ya existe (usa --force para reemplazarla)")
    key = Ed25519PrivateKey.generate()
    private_bytes = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(private_path, flags, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(private_bytes)
    _restrict_private_file(private_path)
    pem = public_pem(key.public_key())
    public_path.write_text(pem, encoding="ascii", newline="\n")
    return private_path, public_path, pem


def load_private_key(*, path: Path | None = None, env: str | None = None) -> Ed25519PrivateKey:
    if path is not None:
        data = path.read_bytes()
    elif env is not None:
        value = os.environ.get(env, "")
        if not value.strip():
            raise SignError(f"la variable {env} está vacía")
        data = value.encode("ascii")
    else:
        raise SignError("falta --key o --key-env")
    key = serialization.load_pem_private_key(data, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise SignError("la clave privada no es Ed25519")
    return key


def load_public_key(path: Path) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(path.read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise SignError("la clave pública no es Ed25519")
    return key


def sign_file(target: Path, key: Ed25519PrivateKey, out: Path | None = None) -> Path:
    signature = key.sign(target.read_bytes())
    if len(signature) != SIGNATURE_SIZE:  # pragma: no cover - Ed25519 siempre da 64
        raise SignError("firma de tamaño inesperado")
    out = out or target.with_name(target.name + ".sig")
    out.write_bytes(signature)
    return out


def verify_file(target: Path, signature_path: Path, public_key: Ed25519PublicKey) -> bool:
    signature = signature_path.read_bytes()
    if len(signature) != SIGNATURE_SIZE:
        return False
    try:
        public_key.verify(signature, target.read_bytes())
    except InvalidSignature:
        return False
    return True


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Claves y firmas Ed25519 de los releases de meshbox."
    )
    parser.add_argument("--generate", action="store_true", help="genera un par de claves nuevo")
    parser.add_argument("--out-dir", type=Path, help="destino del par (fuera del repositorio)")
    parser.add_argument("--name", default="meshbox-release", help="prefijo de los archivos")
    parser.add_argument("--force", action="store_true", help="reemplaza claves existentes")
    sub = parser.add_subparsers(dest="command")

    sign = sub.add_parser("sign", help="firma SHA256SUMS")
    sign.add_argument("file", type=Path)
    group = sign.add_mutually_exclusive_group(required=True)
    group.add_argument("--key", type=Path, help="clave privada PEM")
    group.add_argument("--key-env", help="variable de entorno con la clave privada PEM")
    sign.add_argument("--out", type=Path, help="destino de la firma (por defecto <archivo>.sig)")

    verify = sub.add_parser("verify", help="verifica una firma")
    verify.add_argument("file", type=Path)
    verify.add_argument("--sig", type=Path, required=True)
    verify.add_argument("--pub", type=Path, required=True)

    pub = sub.add_parser("pubkey", help="imprime la clave pública de una privada")
    pub_group = pub.add_mutually_exclusive_group(required=True)
    pub_group.add_argument("--key", type=Path)
    pub_group.add_argument("--key-env")
    return parser


def _utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _utf8_console()
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.generate:
            if args.out_dir is None:
                parser.error("--generate necesita --out-dir")
            private_path, public_path, pem = generate(args.out_dir, args.name, force=args.force)
            print(f"Clave privada: {private_path}", file=sys.stderr)
            print(f"Clave pública: {public_path}", file=sys.stderr)
            print(pem, end="")
            return 0
        if args.command == "sign":
            key = load_private_key(path=args.key, env=args.key_env)
            out = sign_file(args.file, key, args.out)
            print(f"Firma: {out}", file=sys.stderr)
            return 0
        if args.command == "verify":
            ok = verify_file(args.file, args.sig, load_public_key(args.pub))
            print("Firma válida" if ok else "Firma NO válida", file=sys.stderr)
            return 0 if ok else 1
        if args.command == "pubkey":
            key = load_private_key(path=args.key, env=args.key_env)
            print(public_pem(key.public_key()), end="")
            return 0
    except (SignError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
