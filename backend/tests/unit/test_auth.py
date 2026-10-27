"""Autenticación (13.2): contraseñas, sesiones, CSRF, JWT de Access, usuarios y auditoría."""

from __future__ import annotations

import base64
import time
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from meshbox.api.ratelimit import LoginGuard, RateLimiter
from meshbox.auth import passwords
from meshbox.auth.access_jwt import AccessValidator
from meshbox.auth.sessions import IDLE_S, SessionStore, csrf_ok, token_hash
from meshbox.auth.users import (
    audit,
    audit_page,
    cli_user,
    count_users,
    create_user,
    get_user,
    list_users,
    set_password,
)
from meshbox.config import Config
from meshbox.store.db import BatchWriter, Database

from ..conftest import make_cfg


def test_password_rules_and_hashing() -> None:
    assert passwords.validate_password("corta") is not None
    assert passwords.validate_password("aaaaaaaaaaaa") is not None  # repetitiva
    assert passwords.validate_password("operador-clave-2026", "operador") is not None
    assert passwords.validate_password("x" * 300) is not None
    assert passwords.validate_password("una clave larga 42") is None
    h = passwords.hash_password("una clave larga 42")
    assert h.startswith("$argon2id$v=19$m=32768,t=3,p=1$")
    assert passwords.verify_password(h, "una clave larga 42")
    assert not passwords.verify_password(h, "otra")
    assert not passwords.verify_password("no-es-un-hash", "x")
    assert not passwords.needs_rehash(h)
    assert passwords.needs_rehash("basura")


async def test_sessions_lifecycle(migrated_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = Database(migrated_db)
    w = BatchWriter(db, flush_interval_s=0.05)
    await w.start()
    try:
        uid = await create_user(w, "admin", "clave segura 99", "admin")
        store = SessionStore(db, w)
        token, info = await store.create(uid, "admin", "admin", False, "1.2.3.4", "prueba/1.0")
        assert info.token_hash == token_hash(token) and len(token) >= 43
        assert csrf_ok(info, info.csrf_token) and not csrf_ok(info, "x") and not csrf_ok(info, None)
        store._cache.clear()  # forzar lectura desde la base
        got = await store.get(token)
        assert got is not None and got.username == "admin" and got.is_admin
        assert await store.get("token-falso") is None
        assert await store.get("x" * 500) is None
        listed = await store.list_all()
        assert listed[0]["username"] == "admin"
        # inactividad de más de 12 h: vence
        got.last_seen_at = time.time() - IDLE_S - 10
        assert await store.get(token) is None
        token2, info2 = await store.create(uid, "admin", "admin", False, None, None)
        token3, _ = await store.create(uid, "admin", "admin", False, None, None)
        await store.delete_user_sessions(uid, except_hash=info2.token_hash)
        assert await store.get(token3) is None and await store.get(token2) is not None
        assert await store.delete_by_prefix(info2.token_hash[:16])
        assert not await store.delete_by_prefix("corto")
        assert await store.get(token2) is None
        # usuario deshabilitado: sus sesiones dejan de valer
        token4, _ = await store.create(uid, "admin", "admin", False, None, None)
        await w.run(lambda c: c.exec_driver_sql("UPDATE users SET disabled = 1"))
        store._cache.clear()
        assert await store.get(token4) is None
    finally:
        await w.stop()
        await db.dispose()


async def test_users_and_audit(migrated_db: Path) -> None:
    db = Database(migrated_db)
    w = BatchWriter(db, flush_interval_s=0.05)
    await w.start()
    try:
        assert await db.read(count_users) == 0
        uid = await create_user(w, "Operador1", "turno noche 77", "operator", must_change=True)
        with pytest.raises(ValueError, match="ya existe"):
            await create_user(w, "operador1", "turno noche 77", "operator")
        with pytest.raises(ValueError, match="usuario no válido"):
            await create_user(w, "A B", "turno noche 77", "operator")
        with pytest.raises(ValueError, match="rol"):
            await create_user(w, "otro", "turno noche 77", "root")
        u = await db.read(lambda c: get_user(c, username="operador1"))
        assert u is not None and u["must_change_password"] == 1
        await set_password(w, uid, "operador1", "nueva clave segura 1")
        u = await db.read(lambda c: get_user(c, user_id=uid))
        assert passwords.verify_password(u["password_hash"], "nueva clave segura 1")  # type: ignore[index]
        assert [x["username"] for x in await db.read(list_users)] == ["operador1"]
        audit(w, uid, "prueba.accion", "objetivo", {"k": 1}, "10.0.0.1")
        audit(w, None, "otra.cosa")
        await w.flush()
        entries = await db.read(lambda c: audit_page(c, None, 10))
        assert {e["action"] for e in entries} == {"prueba.accion", "otra.cosa"}
        filtered = await db.read(lambda c: audit_page(c, time.time() + 10, 10, "prueba"))
        assert len(filtered) == 1 and filtered[0]["username"] == "operador1"
    finally:
        await w.stop()
        await db.dispose()


async def test_cli_user(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cfg: Config = make_cfg(tmp_path)
    assert await cli_user(cfg, "create", "admin", "admin", "clave de prueba 1") == 0
    assert await cli_user(cfg, "create", "admin", "admin", "clave de prueba 1") == 1  # ya existe
    assert await cli_user(cfg, "list", None, "admin", None) == 0
    assert await cli_user(cfg, "passwd", "admin", "admin", "clave nueva 22 ok") == 0
    assert await cli_user(cfg, "disable", "admin", "admin", None) == 0
    assert await cli_user(cfg, "enable", "nadie", "admin", None) == 1
    out = capsys.readouterr().out
    assert "creado" in out and "deshabilitado" in out


def test_rate_limiter_and_login_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    rl = RateLimiter(3, 60)
    assert [rl.hit("ip")[0] for _ in range(4)] == [True, True, True, False]
    assert rl.hit("otra")[0]
    g = LoginGuard()
    for _ in range(10):
        g.failure("operador")
    wait = g.check("1.1.1.1", "operador")
    assert wait > 0
    g.success("operador")
    assert g.check("1.1.1.2", "operador") == 0


def _rsa_jwk() -> tuple[rsa.RSAPrivateKey, dict[str, str]]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nums = key.public_key().public_numbers()

    def b64(n: int) -> str:
        return (
            base64.urlsafe_b64encode(n.to_bytes((n.bit_length() + 7) // 8, "big"))
            .rstrip(b"=")
            .decode()
        )

    return key, {
        "kty": "RSA",
        "kid": "k1",
        "use": "sig",
        "alg": "RS256",
        "n": b64(nums.n),
        "e": b64(nums.e),
    }


async def test_access_jwt_validation() -> None:
    key, jwk = _rsa_jwk()
    team = "miequipo.cloudflareaccess.com"
    aud = "aud-de-la-app"
    v = AccessValidator(team, aud)
    now = int(time.time())
    good = jwt.encode({"aud": aud, "iss": f"https://{team}", "iat": now, "exp": now + 300, "email": "a@b.c"},
                      key, algorithm="RS256", headers={"kid": "k1"})  # fmt: skip
    bad_aud = jwt.encode({"aud": "otra", "iss": f"https://{team}", "iat": now, "exp": now + 300}, key,
                         algorithm="RS256", headers={"kid": "k1"})  # fmt: skip
    expired = jwt.encode({"aud": aud, "iss": f"https://{team}", "iat": now - 900, "exp": now - 600}, key,
                         algorithm="RS256", headers={"kid": "k1"})  # fmt: skip
    # PyJWKClient descarga el JWKS con urllib (no con httpx): se simula la descarga.
    calls: list[int] = []

    def fake_fetch() -> dict[str, object]:
        calls.append(1)
        return {"keys": [jwk]}

    v._jwks.fetch_data = fake_fetch  # type: ignore[method-assign]
    assert v._jwks.uri == f"https://{team}/cdn-cgi/access/certs"
    claims = await v.validate(good)
    assert claims is not None and claims["email"] == "a@b.c"
    assert await v.validate(good) is not None  # caché
    assert await v.validate(bad_aud) is None
    assert await v.validate(expired) is None
    assert await v.validate(None) is None
    assert calls
    assert not AccessValidator("", "").configured


def test_password_minimum_is_eight() -> None:
    # Mínimo de NIST 800-63B para claves elegidas por la persona.
    assert passwords.validate_password("tucanari") is None
    assert passwords.validate_password("tucanar") is not None
