"""Configuration loading and management for huehub.

Config is loaded from (in priority order):
1. Explicit CLI arguments (passed to :func:`load_config`).
2. Environment variables (``HUE_BRIDGE_HOST``, ``HUE_APPLICATION_KEY``,
   ``HUE_TLS_MODE``, ``HUE_CONFIG_DIR``).
3. TOML config file at the platform-appropriate path.
4. Built-in defaults.

The config file is stored at:
- Linux/macOS: ``~/.config/huehub/config.toml``
- Windows: ``%APPDATA%\\huehub\\config.toml``

Override the directory via the ``HUE_CONFIG_DIR`` environment variable.
"""

import logging
import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from platformdirs import user_cache_dir

log = logging.getLogger(__name__)

_APP_NAME = "huehub"
_APP_NAME_LOCAL = "huehub-local"


# ---------------------------------------------------------------------------
# Section dataclasses
# ---------------------------------------------------------------------------


@dataclass
class BridgeSection:
    """[bridge] section of the config file."""

    host: str | None = None
    application_key: str | None = None
    api_version: str = "2"
    bridge_id: str | None = None


@dataclass
class TlsSection:
    """[tls] section of the config file."""

    mode: str = "auto"  # auto | verify | skip


@dataclass
class ConnectionSection:
    """[connection] section of the config file."""

    request_timeout_s: int = 10
    sse_reconnect_delay_s: int = 2
    sse_reconnect_max_s: int = 60


@dataclass
class DiscoverySection:
    """[discovery] section of the config file."""

    mdns_timeout_s: int = 5
    use_cloud_fallback: bool = True
    use_hostname_fallback: bool = True
    subnet_scan: bool = False


@dataclass
class CacheSection:
    """[cache] section of the config file."""

    ttl_seconds: int = 300


@dataclass
class ColorSection:
    """[color] section of the config file."""

    default_transition_ms: int = 400


@dataclass
class HueConfig:
    """Full configuration for a huehub session.

    Construct via :func:`load_config` rather than directly.
    """

    bridge: BridgeSection = field(default_factory=BridgeSection)
    tls: TlsSection = field(default_factory=TlsSection)
    connection: ConnectionSection = field(default_factory=ConnectionSection)
    discovery: DiscoverySection = field(default_factory=DiscoverySection)
    cache: CacheSection = field(default_factory=CacheSection)
    color: ColorSection = field(default_factory=ColorSection)
    colors: dict[str, str] = field(default_factory=dict)
    config_path: Path | None = field(default=None, compare=False)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def config_dir() -> Path:
    """Return the config directory.

    On macOS and Linux returns ``~/.config/huehub-local``.
    On Windows falls back to ``%APPDATA%/huehub-local``.
    Respects the ``HUE_CONFIG_DIR`` environment variable.
    """
    custom = os.environ.get("HUE_CONFIG_DIR")
    if custom:
        return Path(custom)
    if sys.platform != "win32":
        return Path.home() / ".config" / _APP_NAME_LOCAL
    from platformdirs import user_config_dir

    return Path(user_config_dir(_APP_NAME_LOCAL))


def cache_dir(bridge_id: str = "default") -> Path:
    """Return the cache directory for a specific bridge.

    Args:
        bridge_id: Bridge identifier used as sub-directory name.
    """
    return Path(user_cache_dir(_APP_NAME)) / bridge_id


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------


def load_config(
    host: str | None = None,
    application_key: str | None = None,
    tls_mode: str | None = None,
) -> HueConfig:
    """Load configuration, applying all sources in priority order.

    Args:
        host: CLI override for bridge host/IP.
        application_key: CLI override for the application key.
        tls_mode: CLI override for the TLS mode.

    Returns:
        A fully populated :class:`HueConfig` instance.
    """
    cfg = HueConfig()
    config_path = config_dir() / "config.toml"
    cfg.config_path = config_path

    # 1. Load from TOML file
    if config_path.exists():
        _apply_toml(cfg, config_path)
    else:
        log.debug("No config file found at %s", config_path)

    # 2. Apply environment variables
    if env_host := os.environ.get("HUE_BRIDGE_HOST"):
        cfg.bridge.host = env_host
    if env_key := os.environ.get("HUE_APPLICATION_KEY"):
        cfg.bridge.application_key = env_key
    if env_tls := os.environ.get("HUE_TLS_MODE"):
        cfg.tls.mode = env_tls

    # 3. Apply CLI overrides (highest priority)
    if host:
        cfg.bridge.host = host
    if application_key:
        cfg.bridge.application_key = application_key
    if tls_mode:
        cfg.tls.mode = tls_mode

    return cfg


_CONFIG_TEMPLATE = """\
# huehub configuration
# Override any value with environment variables:
#   HUE_BRIDGE_HOST, HUE_APPLICATION_KEY, HUE_TLS_MODE, HUE_CONFIG_DIR

[bridge]
# host = "192.168.1.10"          # Bridge IP or hostname (set by hue setup)
# application_key = "..."        # App key (set by hue authenticate)
# bridge_id = "c42996fffec629f5" # Bridge serial (detected automatically)
# api_version = "2"              # CLIP API version – keep at 2
{bridge_lines}
[tls]
# mode = "auto"   # auto: use cert if present, else skip (with warning)
# mode = "verify" # verify: require pinned cert – set by hue setup
# mode = "skip"   # skip:   disable TLS verification (not recommended)
mode = "{tls_mode}"

[connection]
# request_timeout_s    = 10  # HTTP request timeout in seconds
# sse_reconnect_delay_s = 2  # Initial SSE reconnect delay
# sse_reconnect_max_s  = 60  # Maximum SSE reconnect back-off
request_timeout_s = {request_timeout_s}
sse_reconnect_delay_s = {sse_reconnect_delay_s}
sse_reconnect_max_s = {sse_reconnect_max_s}

[discovery]
# mdns_timeout_s         = 5     # Seconds to listen for mDNS responses
# use_cloud_fallback     = true  # Fall back to Philips cloud discovery
# use_hostname_fallback  = true  # Try <bridge_id>.local if mDNS fails
# subnet_scan            = false # Scan the local subnet (slow)
mdns_timeout_s = {mdns_timeout_s}
use_cloud_fallback = {use_cloud_fallback}
use_hostname_fallback = {use_hostname_fallback}

[cache]
# ttl_seconds = 300  # How long to keep the resource cache on disk (0 = disabled)
ttl_seconds = {ttl_seconds}

[color]
# default_transition_ms = 400  # Light transition time in milliseconds
default_transition_ms = {default_transition_ms}

# [colors]
# Name your own colours for use with --color on any set command.
# warm_evening = "#FF6B35"
# reading      = "3000K"
{colors_section}"""


def save_config(cfg: HueConfig) -> None:
    """Persist config to the TOML file.

    Creates parent directories as needed.

    Args:
        cfg: Configuration to save.
    """
    path = cfg.config_path or (config_dir() / "config.toml")
    path.parent.mkdir(parents=True, exist_ok=True)

    bridge_lines: list[str] = []
    if cfg.bridge.host:
        bridge_lines.append(f'host = "{cfg.bridge.host}"')
    if cfg.bridge.application_key:
        bridge_lines.append(f'application_key = "{cfg.bridge.application_key}"')
    if cfg.bridge.bridge_id:
        bridge_lines.append(f'bridge_id = "{cfg.bridge.bridge_id}"')
    bridge_lines.append(f'api_version = "{cfg.bridge.api_version}"')

    colors_section = ""
    if cfg.colors:
        color_lines = ["[colors]"]
        for name, value in cfg.colors.items():
            color_lines.append(f'{name} = "{value}"')
        colors_section = "\n".join(color_lines) + "\n"

    content = _CONFIG_TEMPLATE.format(
        bridge_lines="\n".join(bridge_lines) + "\n",
        tls_mode=cfg.tls.mode,
        request_timeout_s=cfg.connection.request_timeout_s,
        sse_reconnect_delay_s=cfg.connection.sse_reconnect_delay_s,
        sse_reconnect_max_s=cfg.connection.sse_reconnect_max_s,
        mdns_timeout_s=cfg.discovery.mdns_timeout_s,
        use_cloud_fallback=str(cfg.discovery.use_cloud_fallback).lower(),
        use_hostname_fallback=str(cfg.discovery.use_hostname_fallback).lower(),
        ttl_seconds=cfg.cache.ttl_seconds,
        default_transition_ms=cfg.color.default_transition_ms,
        colors_section=colors_section,
    )

    path.write_text(content)
    log.debug("Config saved to %s", path)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _apply_toml(cfg: HueConfig, path: Path) -> None:
    """Apply TOML file values to an existing config object in-place.

    Args:
        cfg: Config object to mutate.
        path: Path to the TOML file to read.
    """
    with path.open("rb") as fh:
        data = tomllib.load(fh)

    if bridge := data.get("bridge", {}):
        if v := bridge.get("host"):
            cfg.bridge.host = v
        if v := bridge.get("application_key"):
            cfg.bridge.application_key = v
        if v := bridge.get("api_version"):
            cfg.bridge.api_version = v
        if v := bridge.get("bridge_id"):
            cfg.bridge.bridge_id = v

    if tls := data.get("tls", {}):  # noqa: SIM102
        if v := tls.get("mode"):
            cfg.tls.mode = v

    if conn := data.get("connection", {}):  # noqa: SIM102
        if v := conn.get("request_timeout_s"):
            cfg.connection.request_timeout_s = int(v)
        if v := conn.get("sse_reconnect_delay_s"):
            cfg.connection.sse_reconnect_delay_s = int(v)
        if v := conn.get("sse_reconnect_max_s"):
            cfg.connection.sse_reconnect_max_s = int(v)

    if disc := data.get("discovery", {}):  # noqa: SIM102
        if v := disc.get("mdns_timeout_s"):
            cfg.discovery.mdns_timeout_s = int(v)
        if "use_cloud_fallback" in disc:
            cfg.discovery.use_cloud_fallback = bool(disc["use_cloud_fallback"])
        if "use_hostname_fallback" in disc:
            cfg.discovery.use_hostname_fallback = bool(disc["use_hostname_fallback"])

    if cache := data.get("cache", {}):  # noqa: SIM102
        if v := cache.get("ttl_seconds"):
            cfg.cache.ttl_seconds = int(v)

    if color := data.get("color", {}):  # noqa: SIM102
        if v := color.get("default_transition_ms"):
            cfg.color.default_transition_ms = int(v)

    if colors := data.get("colors", {}):
        cfg.colors.update({k: str(v) for k, v in colors.items()})
