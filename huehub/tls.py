"""TLS certificate management for the Hue Bridge connection.

The bridge uses a self-signed (or Signify-signed) HTTPS certificate.  Three
modes are supported:

- ``auto``   – use a stored ``bridge.pem`` if available, otherwise skip
               verification (emits a warning).
- ``verify`` – require a valid ``bridge.pem``; fail if absent.
- ``skip``   – disable TLS verification entirely (least secure, easiest).

Use ``hue setup`` to extract and store the certificate.
"""

import logging
import ssl
from enum import StrEnum
from pathlib import Path

import httpx

from huehub.config import cache_dir
from huehub.exceptions import CertificateError, TlsError

log = logging.getLogger(__name__)


class TlsMode(StrEnum):
    """TLS verification mode."""

    AUTO = "auto"
    VERIFY = "verify"
    SKIP = "skip"


def _cert_path(bridge_id: str) -> Path:
    """Return the path where the bridge certificate is stored.

    Args:
        bridge_id: Bridge identifier used as the cache sub-directory.
    """
    return cache_dir(bridge_id) / "bridge.pem"


def extract_cert(host: str, port: int = 443) -> str:
    """Extract the PEM certificate from the bridge over TLS.

    Does *not* verify the certificate – that is expected when bootstrapping.

    Args:
        host: Bridge hostname or IP address.
        port: TLS port (default 443).

    Returns:
        PEM-encoded certificate string.

    Raises:
        CertificateError: If the certificate cannot be retrieved.
    """
    try:
        pem = ssl.get_server_certificate((host, port))
        log.debug("Extracted certificate from %s:%d", host, port)
        return pem
    except (OSError, ssl.SSLError) as exc:
        raise CertificateError(
            f"Could not retrieve certificate from {host}:{port}: {exc}"
        ) from exc


def save_cert(host: str, bridge_id: str, port: int = 443) -> Path:
    """Extract and persist the bridge certificate to the cache directory.

    Args:
        host: Bridge hostname or IP.
        bridge_id: Bridge identifier (used as cache sub-directory).
        port: TLS port (default 443).

    Returns:
        Path where the PEM file was saved.

    Raises:
        CertificateError: If extraction fails.
    """
    pem = extract_cert(host, port)
    path = _cert_path(bridge_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pem)
    log.info("Certificate saved to %s", path)
    return path


def _pinned_ssl_ctx(cert_file: Path) -> ssl.SSLContext:
    """Return an SSL context that trusts *cert_file* and skips hostname checks.

    Hue bridges present a cert whose SAN contains the bridge-ID hostname
    (e.g. ``c42996fffec629f5.local``), not the IP address used to reach them.
    Disabling hostname checking allows connection by IP while still enforcing
    that the server presents the exact certificate we pinned during setup.
    """
    ctx = ssl.create_default_context(cafile=str(cert_file))
    ctx.check_hostname = False
    return ctx


def make_httpx_client(
    host: str,
    bridge_id: str,
    mode: TlsMode = TlsMode.AUTO,
    timeout: int = 10,
) -> httpx.AsyncClient:
    """Create an ``httpx.AsyncClient`` configured for the bridge TLS mode.

    Args:
        host: Bridge host (used to derive the base URL).
        bridge_id: Used to locate the stored certificate.
        mode: TLS verification mode.
        timeout: Request timeout in seconds.

    Returns:
        A configured :class:`httpx.AsyncClient`.

    Raises:
        TlsError: If ``mode="verify"`` but no certificate file exists.
    """
    cert_file = _cert_path(bridge_id)

    if mode == TlsMode.SKIP:
        log.warning("TLS verification disabled for bridge %s – not recommended", host)
        return httpx.AsyncClient(verify=False, timeout=timeout)  # noqa: S501

    if mode == TlsMode.VERIFY:
        if not cert_file.exists():
            raise TlsError(
                f"TLS mode is 'verify' but no certificate found at {cert_file}. "
                "Run 'hue setup' first."
            )
        log.debug("Using stored certificate %s", cert_file)
        return httpx.AsyncClient(verify=_pinned_ssl_ctx(cert_file), timeout=timeout)

    # mode == AUTO
    if cert_file.exists():
        log.debug("AUTO mode: using stored certificate %s", cert_file)
        return httpx.AsyncClient(verify=_pinned_ssl_ctx(cert_file), timeout=timeout)

    log.warning(
        "AUTO mode: no certificate for bridge %s, falling back to skip", bridge_id
    )
    return httpx.AsyncClient(verify=False, timeout=timeout)  # noqa: S501
