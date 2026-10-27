"""Firma Ed25519 de releases: cryptography firma y OpenSSL verifica (28.3)."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

REPO = Path(__file__).resolve().parents[2]
SUMS = "0" * 64 + "  meshbox-0.2.0-linux-aarch64.tar.gz\n"


@pytest.fixture
def keypair(tmp_path: Path, sign_release: ModuleType) -> tuple[Path, Path]:
    private, public, _ = sign_release.generate(tmp_path / "claves", "prueba")
    return private, public


def test_generate_writes_pem_pair(tmp_path: Path, sign_release: ModuleType) -> None:
    private, public, pem = sign_release.generate(tmp_path / "claves", "meshbox-dev")
    assert private.name == "meshbox-dev-private.pem"
    assert public.read_text() == pem
    assert pem.startswith("-----BEGIN PUBLIC KEY-----")
    key = serialization.load_pem_public_key(pem.encode())
    assert isinstance(key, Ed25519PublicKey)
    assert b"PRIVATE KEY" in private.read_bytes()
    if os.name == "posix":
        assert private.stat().st_mode & 0o777 == 0o600
    with pytest.raises(sign_release.SignError, match="ya existe"):
        sign_release.generate(tmp_path / "claves", "meshbox-dev")
    sign_release.generate(tmp_path / "claves", "meshbox-dev", force=True)


def test_generate_refuses_repository(sign_release: ModuleType) -> None:
    with pytest.raises(sign_release.SignError, match="repositorio"):
        sign_release.generate(REPO / "release" / "claves", "x")


def test_sign_and_verify(
    tmp_path: Path, sign_release: ModuleType, keypair: tuple[Path, Path]
) -> None:
    sums = tmp_path / "SHA256SUMS"
    sums.write_text(SUMS)
    key = sign_release.load_private_key(path=keypair[0])
    signature = sign_release.sign_file(sums, key)
    assert signature.name == "SHA256SUMS.sig"
    assert len(signature.read_bytes()) == 64
    public = sign_release.load_public_key(keypair[1])
    assert sign_release.verify_file(sums, signature, public) is True
    sums.write_text(SUMS.replace("0", "1", 1))
    assert sign_release.verify_file(sums, signature, public) is False
    signature.write_bytes(b"corta")
    assert sign_release.verify_file(sums, signature, public) is False


def test_cryptography_signature_verifies_with_openssl(
    tmp_path: Path, sign_release: ModuleType, keypair: tuple[Path, Path], openssl: str
) -> None:
    """La compatibilidad que importa: así verifican privd e install.sh en la Pi."""
    sums = tmp_path / "SHA256SUMS"
    sums.write_text(SUMS)
    signature = sign_release.sign_file(sums, sign_release.load_private_key(path=keypair[0]))
    cmd = [
        openssl,
        "pkeyutl",
        "-verify",
        "-pubin",
        "-inkey",
        str(keypair[1]),
        "-rawin",
        "-in",
        str(sums),
        "-sigfile",
        str(signature),
    ]
    ok = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert ok.returncode == 0, ok.stderr
    assert "Signature Verified Successfully" in ok.stdout
    sums.write_text(SUMS + "otro\n")
    bad = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert bad.returncode != 0


def test_openssl_signature_verifies_with_cryptography(
    tmp_path: Path, sign_release: ModuleType, keypair: tuple[Path, Path], openssl: str
) -> None:
    sums = tmp_path / "SHA256SUMS"
    sums.write_text(SUMS)
    signature = tmp_path / "SHA256SUMS.sig"
    subprocess.run(
        [
            openssl,
            "pkeyutl",
            "-sign",
            "-inkey",
            str(keypair[0]),
            "-rawin",
            "-in",
            str(sums),
            "-out",
            str(signature),
        ],
        check=True,
    )
    public = sign_release.load_public_key(keypair[1])
    assert sign_release.verify_file(sums, signature, public) is True


def test_privd_verifies_cryptography_signature(
    tmp_path: Path, sign_release: ModuleType, keypair: tuple[Path, Path], openssl: str
) -> None:
    """privd (biblioteca estándar + openssl) acepta lo que firma sign-release.py."""
    sys.path.insert(0, str(REPO / "privd"))
    try:
        from commands.core import Bins, Config, Context, ProcResult
        from commands.jobs import JobManager
        from commands.update import verify_signature
    finally:
        sys.path.remove(str(REPO / "privd"))

    class Runner:
        def run(self, argv, **kwargs):  # type: ignore[no-untyped-def]
            proc = subprocess.run([openssl, *argv[1:]], capture_output=True, check=False)
            return ProcResult(proc.returncode, proc.stdout, proc.stderr)

    sums = tmp_path / "SHA256SUMS"
    sums.write_text(SUMS)
    signature = sign_release.sign_file(sums, sign_release.load_private_key(path=keypair[0]))
    ctx = Context(
        Config(), Runner(), JobManager(None), bins=Bins(), public_key_pem=keypair[1].read_text()
    )
    verify_signature(ctx, sums, signature, tmp_path)


def test_embedded_public_key_is_valid_ed25519() -> None:
    text = (REPO / "privd/commands/update.py").read_text(encoding="utf-8")
    match = re.search(r"-----BEGIN PUBLIC KEY-----\n.+?\n-----END PUBLIC KEY-----\n", text, re.S)
    assert match is not None
    key = serialization.load_pem_public_key(match.group(0).encode())
    assert isinstance(key, Ed25519PublicKey)


def test_load_private_key_from_env(
    sign_release: ModuleType, keypair: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAVE_PRUEBA", keypair[0].read_text())
    key = sign_release.load_private_key(env="CLAVE_PRUEBA")
    assert sign_release.public_pem(key.public_key()) == keypair[1].read_text()
    monkeypatch.setenv("CLAVE_PRUEBA", "  ")
    with pytest.raises(sign_release.SignError, match="vacía"):
        sign_release.load_private_key(env="CLAVE_PRUEBA")
    with pytest.raises(sign_release.SignError):
        sign_release.load_private_key()


def test_rejects_non_ed25519_keys(tmp_path: Path, sign_release: ModuleType) -> None:
    from cryptography.hazmat.primitives.asymmetric import ec

    other = ec.generate_private_key(ec.SECP256R1())
    private = tmp_path / "ec.pem"
    private.write_bytes(
        other.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public = tmp_path / "ec.pub.pem"
    public.write_bytes(
        other.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    with pytest.raises(sign_release.SignError, match="Ed25519"):
        sign_release.load_private_key(path=private)
    with pytest.raises(sign_release.SignError, match="Ed25519"):
        sign_release.load_public_key(public)


def test_cli(tmp_path: Path, sign_release: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    keys = tmp_path / "claves"
    assert sign_release.main(["--generate", "--out-dir", str(keys), "--name", "cli"]) == 0
    assert "BEGIN PUBLIC KEY" in capsys.readouterr().out
    sums = tmp_path / "SHA256SUMS"
    sums.write_text(SUMS)
    private = keys / "cli-private.pem"
    public = keys / "cli-public.pem"
    assert sign_release.main(["sign", str(sums), "--key", str(private)]) == 0
    sig = tmp_path / "SHA256SUMS.sig"
    assert sign_release.main(["verify", str(sums), "--sig", str(sig), "--pub", str(public)]) == 0
    sums.write_text("cambiado\n")
    assert sign_release.main(["verify", str(sums), "--sig", str(sig), "--pub", str(public)]) == 1
    assert sign_release.main(["pubkey", "--key", str(private)]) == 0
    assert capsys.readouterr().out.strip() == public.read_text().strip()
    assert sign_release.main(["sign", str(tmp_path / "no-existe"), "--key", str(private)]) == 2
    assert sign_release.main([]) == 2
    with pytest.raises(SystemExit):
        sign_release.main(["--generate"])
