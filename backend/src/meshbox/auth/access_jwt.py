"""Validación del JWT de Cloudflare Access (sección 13.1).

`Cf-Access-Jwt-Assertion` se verifica contra las claves públicas del equipo
(`https://<equipo>.cloudflareaccess.com/cdn-cgi/access/certs`) y el `aud` de la aplicación.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import jwt
from jwt import PyJWKClient

log = logging.getLogger(__name__)
HEADER = "cf-access-jwt-assertion"


class AccessValidator:
    def __init__(self, team_domain: str, audience: str) -> None:
        domain = team_domain.strip().removeprefix("https://").rstrip("/")
        self.issuer = f"https://{domain}"
        self.audience = audience
        self._jwks = PyJWKClient(
            f"{self.issuer}/cdn-cgi/access/certs", cache_keys=True, lifespan=3600
        )
        self._ok_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    @property
    def configured(self) -> bool:
        return bool(self.audience) and self.issuer != "https://"

    def _decode(self, token: str) -> dict[str, Any]:
        key = self._jwks.get_signing_key_from_jwt(token)
        claims: dict[str, Any] = jwt.decode(
            token,
            key.key,
            algorithms=["RS256"],
            audience=self.audience,
            issuer=self.issuer,
            options={"require": ["exp", "iat", "aud", "iss"]},
        )
        return claims

    async def validate(self, token: str | None) -> dict[str, Any] | None:
        if not token or not self.configured:
            return None
        cached = self._ok_cache.get(token)
        now = time.time()
        if cached and cached[0] > now:
            return cached[1]
        try:
            claims = await asyncio.to_thread(self._decode, token)
        except Exception as e:
            log.warning("JWT de Access rechazado: %s", e)
            return None
        self._ok_cache[token] = (min(float(claims.get("exp", now)), now + 300), claims)
        if len(self._ok_cache) > 500:
            self._ok_cache = {k: v for k, v in self._ok_cache.items() if v[0] > now}
        return claims
