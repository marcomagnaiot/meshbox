"""Servicio de autenticación: sesiones, límites de inicio de sesión y Cloudflare Access."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..api.ratelimit import LoginGuard, RateLimiter
from .access_jwt import AccessValidator
from .sessions import SessionStore

if TYPE_CHECKING:
    from ..app import Service


class AuthService:
    def __init__(self, service: Service) -> None:
        self.service = service
        self.sessions = SessionStore(service.db, service.writer)
        self.login_guard = LoginGuard()
        self.admin_limit = RateLimiter(600, 60)  # 600 peticiones/min por sesión (12.5)
        self.access: AccessValidator | None = None
        self.reload_access()

    def reload_access(self) -> None:
        cf = self.service.cfg.cloudflare
        if cf.access_team_domain and cf.access_aud:
            self.access = AccessValidator(cf.access_team_domain, cf.access_aud)
        else:
            self.access = None


def make_auth(service: Service) -> AuthService:
    return AuthService(service)
