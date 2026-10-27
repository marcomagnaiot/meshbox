"""Configuración (config.toml) y secretos (secrets.toml). Secciones 8 y Anexo A del plan.

Precedencia: valores por defecto del código < config.toml < variables de entorno
``MESHBOX_<SECCION>__<CLAVE>`` (solo para desarrollo y pruebas).
"""

from __future__ import annotations

import base64
import os
import re
import secrets as pysecrets
import sys
import tomllib
from pathlib import Path, PurePath
from typing import Annotated, Any, Literal

import tomli_w
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$")
DEFAULT_CONFIG_PATH = Path("/etc/meshbox/config.toml")


class _Section(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)


# --------------------------------------------------------------------------- secciones


class SiteCfg(_Section):
    slug: str = "meshbox"
    timezone: str = "America/Argentina/Buenos_Aires"
    language: Literal["es", "en"] = "es"


class HostCfg(_Section):
    # "appliance": equipo dedicado (plan). "shared": equipo compartido (ADR 0004).
    mode: Literal["appliance", "shared"] = "appliance"


def parse_bind(bind: str) -> tuple[str, int]:
    host, _, port = bind.rpartition(":")
    if not host or not port.isdigit():
        raise ValueError(f"dirección no válida: {bind!r} (se espera host:puerto)")
    return host.strip("[]"), int(port)


class ServerCfg(_Section):
    public_bind: str = "127.0.0.1:8081"
    lan_bind: str = "0.0.0.0:80"
    admin_remote_bind: str = "127.0.0.1:8082"
    trust_cf_headers_from: list[str] = Field(default_factory=lambda: ["127.0.0.1"])

    @field_validator("public_bind", "lan_bind", "admin_remote_bind")
    @classmethod
    def _check_bind(cls, v: str) -> str:
        if v:
            parse_bind(v)
        return v


class PathsCfg(_Section):
    db: Path = Path("/var/lib/meshbox/meshbox.db")
    tiles: Path = Path("/var/lib/meshbox/tiles")
    backups: Path = Path("/var/lib/meshbox/backups")
    plugins: Path = Path("/var/lib/meshbox/plugins")
    recordings: Path = Path("/var/lib/meshbox/rec")
    tmp: Path = Path("/var/lib/meshbox/tmp")  # /tmp es RAM en la Pi: temporales grandes acá
    secrets: Path = Path("/etc/meshbox/secrets.toml")
    web: Path | None = None  # estáticos del frontend; por defecto, meshbox/web del paquete
    pmtiles_bin: Path = Path("/opt/meshbox/bin/pmtiles")


class _ConnectorBase(_Section):
    id: str
    enabled: bool = True

    @field_validator("id")
    @classmethod
    def _check_id(cls, v: str) -> str:
        if not ID_RE.match(v):
            raise ValueError("id de conector no válido (minúsculas, números, - y _; 2 a 32)")
        return v


class MqttConnectorCfg(_ConnectorBase):
    kind: Literal["mqtt"] = "mqtt"
    host: str = "127.0.0.1"
    port: int = 1883
    username: str | None = None
    password_ref: str | None = None  # clave dentro de secrets.toml, p. ej. "mqtt.meshbox-ingest"
    topics: list[str] = Field(default_factory=list)
    tls: bool = False
    client_id: str | None = None
    keepalive: int = 60


class SerialConnectorCfg(_ConnectorBase):
    kind: Literal["serial"] = "serial"
    port: str = ""


class TcpConnectorCfg(_ConnectorBase):
    """API del nodo por la red (puerto 4403): igual que USB, para un gateway en WiFi (ADR 0012)."""

    kind: Literal["tcp"] = "tcp"
    host: str = ""
    port: int = 4403


class ReplayConnectorCfg(_ConnectorBase):
    kind: Literal["replay"] = "replay"
    file: Path = Path("backend/tests/fixtures/sim-24h.jsonl")
    speed: float = 1.0  # 0 = máxima velocidad
    loop: bool = False
    rebase_time: bool = True  # corre las horas para que la grabación parezca en vivo
    id_salt: int | None = None  # None: al azar si rebase_time (ver connectors/replay.py)


ConnectorCfg = Annotated[
    MqttConnectorCfg | SerialConnectorCfg | TcpConnectorCfg | ReplayConnectorCfg,
    Field(discriminator="kind"),
]


class MqttOutCfg(_Section):
    enabled: bool = False
    prefix: str = "meshbox/events"
    host: str = "127.0.0.1"
    port: int = 1883
    username: str | None = "meshbox-ingest"
    password_ref: str | None = "mqtt.meshbox-ingest"  # noqa: S105 - referencia, no clave


class PrivacyCfg(_Section):
    ignore_via_mqtt: bool = True
    position_policy: Literal["as_received", "degrade"] = "as_received"
    degrade_meters: int = Field(default=500, ge=50, le=50_000)


class RetentionCfg(_Section):  # días
    packets: int = Field(default=14, ge=1)
    positions: int = Field(default=90, ge=1)
    telemetry_raw: int = Field(default=30, ge=1)
    rollup_hourly: int = Field(default=365, ge=1)
    messages: int = Field(default=365, ge=1)
    # mensajes del cliente Meshtastic: todos los canales y directos de cada placa (ADR 0016)
    radio_messages: int = Field(default=365, ge=1)
    traceroutes: int = Field(default=90, ge=1)
    links: int = Field(default=30, ge=1)
    alerts: int = Field(default=365, ge=1)
    audit: int = Field(default=365, ge=1)


class IngestCfg(_Section):
    dedup_cache: int = 20_000
    dedup_ttl_s: int = 1800
    per_node_max_per_min: int = 120
    position_min_move_m: float = 25
    position_min_interval_s: float = 900
    wait_ntp_s: int = 300
    queue_size: int = 2000


class WriterCfg(_Section):
    flush_interval_s: float = 2
    flush_max_ops: int = 200
    max_queue: int = 10_000


class SseCfg(_Section):
    public_max_clients: int = 200
    public_max_per_ip: int = 10
    heartbeat_s: float = 15
    activity_max_per_s: int = 10
    stats_interval_s: float = 30


class CloudflareCfg(_Section):
    mode: Literal["none", "token", "api"] = "none"
    public_hostname: str = ""
    admin_hostname: str = ""
    account_id: str = ""
    zone_id: str = ""
    tunnel_id: str = ""
    access_team_domain: str = ""
    access_aud: str = ""
    access_app_id: str = ""
    # Panel por internet (servidor remoto): "access" exige Cloudflare Access (plan); "password",
    # solo usuario y clave de meshbox, con el asistente cerrado y sin reinicio remoto (ADR 0014).
    remote_admin_auth: Literal["access", "password"] = "access"


class PushCfg(_Section):
    subject: str = "mailto:admin@example.com"


class UpdatesCfg(_Section):
    source: str = "https://api.github.com/repos/marcomagnaiot/meshbox/releases"
    auto_check: bool = True


class TxCfg(_Section):
    enabled: bool = False


class LoggingCfg(_Section):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    json_output: bool = True


class LimitsCfg(_Section):
    # Guardia propia de memoria (ADR 0006): el kernel de la Pi no aplica MemoryMax.
    rss_soft_mb: int = 200
    rss_hard_mb: int = 280


class SystemCfg(_Section):
    privd: Literal["auto", "socket", "fake"] = "auto"
    privd_socket: Path = Path("/run/meshbox/privd.sock")
    systemd_notify: bool = True


# --------------------------------------------------------------------------- raíz


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MESHBOX_", env_nested_delimiter="__", extra="ignore", validate_assignment=True
    )

    site: SiteCfg = Field(default_factory=SiteCfg)
    host: HostCfg = Field(default_factory=HostCfg)
    server: ServerCfg = Field(default_factory=ServerCfg)
    paths: PathsCfg = Field(default_factory=PathsCfg)
    connectors: list[ConnectorCfg] = Field(default_factory=list)
    mqtt_out: MqttOutCfg = Field(default_factory=MqttOutCfg)
    privacy: PrivacyCfg = Field(default_factory=PrivacyCfg)
    retention: RetentionCfg = Field(default_factory=RetentionCfg)
    ingest: IngestCfg = Field(default_factory=IngestCfg)
    writer: WriterCfg = Field(default_factory=WriterCfg)
    sse: SseCfg = Field(default_factory=SseCfg)
    cloudflare: CloudflareCfg = Field(default_factory=CloudflareCfg)
    push: PushCfg = Field(default_factory=PushCfg)
    updates: UpdatesCfg = Field(default_factory=UpdatesCfg)
    tx: TxCfg = Field(default_factory=TxCfg)
    logging: LoggingCfg = Field(default_factory=LoggingCfg)
    limits: LimitsCfg = Field(default_factory=LimitsCfg)
    system: SystemCfg = Field(default_factory=SystemCfg)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # El TOML llega como argumentos de inicio; el entorno lo pisa.
        return (env_settings, init_settings)

    def connector(self, connector_id: str) -> ConnectorCfg | None:
        return next((c for c in self.connectors if c.id == connector_id), None)

    @property
    def shared_host(self) -> bool:
        return self.host.mode == "shared"

    @property
    def mqtt_root(self) -> str | None:
        """Raíz de tópicos (`msh/AR/zona`) deducida del primer conector MQTT local."""
        for c in self.connectors:
            if isinstance(c, MqttConnectorCfg):
                for t in c.topics:
                    if "/2/e/" in t:
                        return t.split("/2/e/")[0]
        return None


def load_config(path: Path | None) -> Config:
    data: dict[str, Any] = {}
    if path is not None and path.exists():
        with path.open("rb") as f:
            data = tomllib.load(f)
    cfg = Config(**data)
    if path is not None:
        _resolve_relative_paths(cfg, path.parent)
    return cfg


def _resolve_relative_paths(cfg: Config, base: Path) -> None:
    """Las rutas relativas del config se interpretan desde la carpeta del archivo
    (en desarrollo, `dev/config.toml` usa rutas relativas a `dev/`)."""
    for name in ("db", "tiles", "backups", "plugins", "recordings", "tmp", "secrets", "web"):
        value = getattr(cfg.paths, name)
        if value is not None and not value.is_absolute():
            setattr(cfg.paths, name, (base / value).resolve())
    for c in cfg.connectors:
        if isinstance(c, ReplayConnectorCfg) and not c.file.is_absolute():
            candidate = (base / c.file).resolve()
            if candidate.exists() or not (Path.cwd() / c.file).exists():
                c.file = candidate
            else:
                c.file = (Path.cwd() / c.file).resolve()


def _toml_safe(value: Any) -> Any:
    if isinstance(value, PurePath):
        return value.as_posix()  # "/opt/meshbox/..." aunque se guarde desde Windows
    if isinstance(value, dict):
        return {k: _toml_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_toml_safe(v) for v in value]
    return value


def config_to_dict(cfg: Config) -> dict[str, Any]:
    data: dict[str, Any] = _toml_safe(cfg.model_dump(mode="python", exclude_none=True))
    return data


def atomic_write(path: Path, data: bytes, mode: int = 0o640) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if sys.platform != "win32":
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def save_config(cfg: Config, path: Path) -> None:
    header = (
        b"# meshbox: configuracion de arranque. La reescribe el panel; editar a mano solo\n"
        b"# con el servicio detenido. Ver docs/instalacion.md.\n\n"
    )
    atomic_write(path, header + tomli_w.dumps(config_to_dict(cfg)).encode(), 0o640)


# --------------------------------------------------------------------------- secretos


class VapidSecrets(_Section):
    public_key: str = ""
    private_key: str = ""


class CloudflareSecrets(_Section):
    api_token: str = ""


class TelegramSecrets(_Section):
    bot_token: str = ""
    chat_id: str = ""


class Secrets(_Section):
    session_key: str = ""
    setup_code: str = ""
    vapid: VapidSecrets = Field(default_factory=VapidSecrets)
    mqtt: dict[str, str] = Field(default_factory=dict)
    channels: dict[str, str] = Field(default_factory=dict)
    cloudflare: CloudflareSecrets = Field(default_factory=CloudflareSecrets)
    telegram: TelegramSecrets = Field(default_factory=TelegramSecrets)
    webhooks: dict[str, str] = Field(default_factory=dict)
    plugins: dict[str, dict[str, str]] = Field(default_factory=dict)


SECRET_MASK = "********"  # noqa: S105 - máscara, no clave


class SecretStore:
    """Acceso a secrets.toml (0600). Las referencias son rutas con punto: "mqtt.meshbox-ingest"."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = Secrets()
        self.reload()

    def reload(self) -> None:
        if self.path.exists():
            with self.path.open("rb") as f:
                self.data = Secrets(**tomllib.load(f))
        else:
            self.data = Secrets()

    def save(self) -> None:
        dumped = self.data.model_dump(mode="json")
        atomic_write(self.path, tomli_w.dumps(dumped).encode(), 0o600)

    def get(self, ref: str | None) -> str | None:
        if not ref:
            return None
        section, _, key = ref.partition(".")
        value: Any = getattr(self.data, section, None)
        if value is None:
            return None
        if not key:
            return value if isinstance(value, str) else None
        if isinstance(value, dict):
            got = value.get(key)
            return got if isinstance(got, str) else None
        got = getattr(value, key, None)
        return got if isinstance(got, str) else None

    def set(self, ref: str, value: str, *, save: bool = True) -> None:
        section, _, key = ref.partition(".")
        if not key:
            setattr(self.data, section, value)
        else:
            container = getattr(self.data, section)
            if isinstance(container, dict):
                container[key] = value
            else:
                setattr(container, key, value)
        if save:
            self.save()

    def delete(self, ref: str, *, save: bool = True) -> None:
        section, _, key = ref.partition(".")
        container = getattr(self.data, section, None)
        if isinstance(container, dict):
            container.pop(key, None)
        elif container is not None and key:
            setattr(container, key, "")
        if save:
            self.save()

    def values(self) -> list[str]:
        """Todos los valores secretos no vacíos (para el filtro de registros)."""
        out: list[str] = []

        def walk(v: Any) -> None:
            if isinstance(v, str):
                if len(v) >= 6:
                    out.append(v)
            elif isinstance(v, dict):
                for x in v.values():
                    walk(x)
            elif isinstance(v, BaseModel):
                for x in v.model_dump().values():
                    walk(x)

        walk(self.data)
        return out


def generate_password(length: int = 24) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    return "".join(pysecrets.choice(alphabet) for _ in range(length))


def generate_setup_code() -> str:
    # 8 caracteres sin ambigüedades (sin 0/O, 1/I/L)
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(pysecrets.choice(alphabet) for _ in range(8))


def generate_session_key() -> str:
    return base64.b64encode(pysecrets.token_bytes(32)).decode()
