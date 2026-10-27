"""Contraseñas con argon2id (sección 13.2): t=3, m=32 MiB, p=1 (0,61 s medido en la Pi)."""

from __future__ import annotations

import asyncio

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher(time_cost=3, memory_cost=32768, parallelism=1)
MIN_LENGTH = 8  # NIST SP 800-63B: mínimo para claves elegidas por la persona
MAX_LENGTH = 256


def validate_password(password: str, username: str | None = None) -> str | None:
    """Devuelve un mensaje de error o None si la contraseña es aceptable."""
    if len(password) < MIN_LENGTH:
        return f"la contraseña debe tener al menos {MIN_LENGTH} caracteres"
    if len(password) > MAX_LENGTH:
        return "la contraseña es demasiado larga"
    if username and username.lower() in password.lower():
        return "la contraseña no puede contener el nombre de usuario"
    if len(set(password)) < 5:
        return "la contraseña es demasiado repetitiva"
    return None


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored: str, password: str) -> bool:
    try:
        return _hasher.verify(stored, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored: str) -> bool:
    try:
        return _hasher.check_needs_rehash(stored)
    except InvalidHashError:
        return True


async def hash_password_async(password: str) -> str:
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(stored: str, password: str) -> bool:
    return await asyncio.to_thread(verify_password, stored, password)


# Hash fijo para gastar el mismo tiempo cuando el usuario no existe (evita enumerar usuarios).
DUMMY_HASH = _hasher.hash("meshbox-dummy-password")
