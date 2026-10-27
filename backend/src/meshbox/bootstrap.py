"""`meshbox bootstrap`: config, secretos y cuentas iniciales (secciones 23.2 y 24.2).

Lo ejecuta el instalador (y el primer arranque de la imagen) como usuario `meshbox`, con
privd ya escuchando. Es idempotente: no pisa lo que ya existe.
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from .config import (
    Config,
    MqttConnectorCfg,
    SecretStore,
    generate_session_key,
    generate_setup_code,
    load_config,
    save_config,
)

SHARED_BINDS = {
    "lan_bind": "0.0.0.0:8090",
    "public_bind": "127.0.0.1:8091",
    "admin_remote_bind": "127.0.0.1:8092",
}
APPLIANCE_BINDS = {
    "lan_bind": "0.0.0.0:80",
    "public_bind": "127.0.0.1:8081",
    "admin_remote_bind": "127.0.0.1:8082",
}


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def generate_vapid() -> tuple[str, str]:
    """(pública sin comprimir en base64url, privada cruda de 32 bytes en base64url)."""
    key = ec.generate_private_key(ec.SECP256R1())
    private_raw = key.private_numbers().private_value.to_bytes(32, "big")
    public_raw = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return b64url(public_raw), b64url(private_raw)


def default_config(
    mode: str, slug: str, mqtt_root: str | None, secrets_path: Path | None
) -> Config:
    cfg = Config()
    cfg.host.mode = mode  # type: ignore[assignment]
    for k, v in (SHARED_BINDS if mode == "shared" else APPLIANCE_BINDS).items():
        setattr(cfg.server, k, v)
    cfg.site.slug = slug
    root = mqtt_root or f"msh/AR/{slug}"
    cfg.connectors = [
        MqttConnectorCfg(
            id="mqtt-local",
            host="127.0.0.1",
            port=1883,
            username="meshbox-ingest",
            password_ref="mqtt.meshbox-ingest",  # noqa: S106 - referencia, no clave
            topics=[f"{root}/2/e/#", f"{root}/2/map/#"],
        )
    ]
    if secrets_path is not None:
        cfg.paths.secrets = secrets_path
    return cfg


def ensure_secrets(store: SecretStore) -> list[str]:
    created = []
    d = store.data
    if not d.session_key:
        d.session_key = generate_session_key()
        created.append("session_key")
    if not d.vapid.public_key or not d.vapid.private_key:
        d.vapid.public_key, d.vapid.private_key = generate_vapid()
        created.append("vapid")
    if not d.setup_code:
        d.setup_code = generate_setup_code()
        created.append("setup_code")
    if created:
        store.save()
    return created


@dataclass
class _Mini:
    """Lo mínimo que necesita MosquittoAdmin, sin levantar el servicio completo."""

    cfg: Config
    secrets: SecretStore
    db: Any
    writer: Any
    priv: Any


async def _mosquitto(cfg: Config, secrets: SecretStore) -> dict[str, Any]:
    from . import __version__
    from .auth.users import count_users
    from .integrations.mosquitto import MosquittoAdmin
    from .store.db import BatchWriter, Database
    from .store.migrate import migrate
    from .system.privclient import make_privclient

    for d in (
        cfg.paths.db.parent,
        cfg.paths.backups,
        cfg.paths.tmp,
        cfg.paths.tiles,
        cfg.paths.recordings,
        cfg.paths.plugins,
    ):
        d.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(migrate, cfg.paths.db, cfg.paths.backups, __version__, cfg.paths.tmp)
    db = Database(cfg.paths.db)
    writer = BatchWriter(db)
    await writer.start()
    priv = make_privclient(cfg.system.privd, cfg.system.privd_socket, cfg.host.mode)
    try:
        admin = MosquittoAdmin(_Mini(cfg, secrets, db, writer, priv))  # type: ignore[arg-type]
        adopted = await admin.adopt_existing()
        new_ingest = await admin.ensure_ingest()
        await admin.write_acl()
        users = await db.read(count_users)
        return {
            "mqtt_adopted": adopted,
            "ingest_created": new_ingest is not None,
            "users": users,
            "privd": "simulado" if priv.fake else "socket",
        }
    finally:
        await writer.stop()
        await db.dispose()


def bootstrap(
    config_path: Path,
    *,
    mode: str = "appliance",
    site_slug: str | None = None,
    mqtt_root: str | None = None,
    secrets_path: Path | None = None,
) -> dict[str, Any]:
    created = False
    if not config_path.exists():
        cfg = default_config(mode, site_slug or "meshbox", mqtt_root, secrets_path)
        save_config(cfg, config_path)
        created = True
    cfg = load_config(config_path)
    if cfg.host.mode != mode:
        # Cambio de modo: actualizar puertos solo si eran los del otro modo (no pisar ajustes a mano)
        old = SHARED_BINDS if cfg.host.mode == "shared" else APPLIANCE_BINDS
        new = SHARED_BINDS if mode == "shared" else APPLIANCE_BINDS
        for k in new:
            if getattr(cfg.server, k) == old[k]:
                setattr(cfg.server, k, new[k])
        cfg.host.mode = mode  # type: ignore[assignment]
        save_config(cfg, config_path)
    secrets = SecretStore(cfg.paths.secrets)
    secrets_created = ensure_secrets(secrets)
    from .__main__ import run_async

    mq = run_async(_mosquitto(cfg, secrets))
    lan = cfg.server.lan_bind.rsplit(":", 1)
    return {
        "config_created": created,
        "mode": cfg.host.mode,
        "secrets_created": secrets_created,
        "setup_code": secrets.data.setup_code if mq["users"] == 0 else None,
        "lan_port": int(lan[1]) if len(lan) == 2 else None,
        "health_url": f"http://{cfg.server.public_bind}/api/v1/health",
        **mq,
    }
