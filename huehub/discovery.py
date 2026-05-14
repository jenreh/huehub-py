"""Hue Bridge discovery via multiple methods.

Discovery order (each skipped if disabled or unavailable):
1. mDNS / Bonjour  (``_hue._tcp.local.`` service)
2. Hostname fallback  (``Philips-hue.local``)
3. Hue Cloud API  (``https://discovery.meethue.com/``)

Returns a list of ``{"host": str, "bridge_id": str}`` dicts.
The caller may also specify a manual IP in the config file, bypassing
discovery entirely.
"""

import asyncio
import logging
import socket

import httpx

log = logging.getLogger(__name__)

_CLOUD_URL = "https://discovery.meethue.com/"
_HUE_HOSTNAME = "Philips-hue.local"
_HUE_SERVICE = "_hue._tcp.local."


async def discover_mdns(timeout_s: float = 5.0) -> list[dict]:
    """Discover Hue bridges on the local network via mDNS.

    Args:
        timeout_s: How many seconds to listen for announcements.

    Returns:
        List of ``{"host": str, "bridge_id": str}`` dicts (may be empty).
    """
    try:
        from zeroconf import ServiceBrowser, ServiceStateChange, Zeroconf
    except ImportError:
        log.warning("zeroconf not installed; mDNS discovery unavailable")
        return []

    results: dict[str, dict] = {}

    def on_service_state_change(
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ) -> None:
        if state_change != ServiceStateChange.Added:
            return
        info = zeroconf.get_service_info(service_type, name)
        if not info:
            return
        if not info.addresses:
            return
        host = socket.inet_ntoa(info.addresses[0])
        props = info.properties or {}
        bridge_id = props.get(b"bridgeid", b"").decode("utf-8", errors="replace")
        log.debug("mDNS found bridge %s at %s", bridge_id, host)
        results[bridge_id or host] = {"host": host, "bridge_id": bridge_id}

    zc = Zeroconf()
    try:
        browser = ServiceBrowser(zc, _HUE_SERVICE, handlers=[on_service_state_change])
        await asyncio.sleep(timeout_s)
        browser.cancel()
    finally:
        zc.close()

    return list(results.values())


async def discover_hostname() -> list[dict]:
    """Discover via the fallback hostname ``Philips-hue.local``.

    Args: none.

    Returns:
        List with one entry if the hostname resolves, empty otherwise.
    """
    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(
            None,
            lambda: socket.getaddrinfo(_HUE_HOSTNAME, 443, type=socket.SOCK_STREAM),
        )
        if info:
            host = info[0][4][0]
            log.debug("Hostname fallback resolved %s to %s", _HUE_HOSTNAME, host)
            return [{"host": host, "bridge_id": ""}]
    except OSError as exc:
        log.debug("Hostname fallback failed: %s", exc)
    return []


async def discover_cloud(
    client: httpx.AsyncClient | None = None,
) -> list[dict]:
    """Query the Hue Cloud discovery API.

    Requires internet access.  Used as a last resort when local discovery
    fails.

    Args:
        client: Optional existing ``httpx.AsyncClient``.  A temporary one
            is created if not provided.

    Returns:
        List of ``{"host": str, "bridge_id": str}`` dicts.
    """
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=10)
    try:
        response = await client.get(_CLOUD_URL)
        response.raise_for_status()
        bridges = response.json()
        results = []
        for b in bridges:
            host = b.get("internalipaddress", "")
            bridge_id = b.get("id", "")
            if host:
                log.debug("Cloud discovery found bridge %s at %s", bridge_id, host)
                results.append({"host": host, "bridge_id": bridge_id})
        return results
    except httpx.HTTPError as exc:
        log.warning("Cloud discovery request failed: %s", exc)
        return []
    finally:
        if own_client:
            await client.aclose()


async def discover(
    mdns_timeout_s: float = 5.0,
    use_mdns: bool = True,
    use_hostname: bool = True,
    use_cloud: bool = True,
) -> list[dict]:
    """Discover Hue bridges using all enabled methods.

    Methods are tried in order; the first non-empty result is returned.

    Args:
        mdns_timeout_s: mDNS listen timeout.
        use_mdns: Whether to attempt mDNS discovery.
        use_hostname: Whether to try the ``Philips-hue.local`` hostname.
        use_cloud: Whether to fall back to the Hue Cloud API.

    Returns:
        List of ``{"host": str, "bridge_id": str}`` dicts.
    """
    if use_mdns:
        results = await discover_mdns(timeout_s=mdns_timeout_s)
        if results:
            return results

    if use_hostname:
        results = await discover_hostname()
        if results:
            return results

    if use_cloud:
        results = await discover_cloud()
        if results:
            return results

    return []
