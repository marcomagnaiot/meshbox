"""meshbox: gateway, mapa web y panel de administración Meshtastic."""

from importlib.metadata import PackageNotFoundError, version

try:
    # Una sola fuente de verdad: la versión de pyproject.toml (la exigen install.sh y privd).
    __version__ = version("meshbox")
except PackageNotFoundError:  # pragma: no cover - código sin instalar
    __version__ = "0.0.0"
