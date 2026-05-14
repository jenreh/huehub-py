"""Server-Sent Events (SSE) stream for real-time Hue Bridge events.

Connects to ``GET /eventstream/clip/v2`` and yields :class:`~huehub.models.HueEvent`
objects.  Automatically reconnects with exponential back-off when the stream
drops.
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

import httpx
from httpx_sse import aconnect_sse

from huehub.models import HueEvent

log = logging.getLogger(__name__)

_SSE_PATH = "/eventstream/clip/v2"


async def stream(
    host: str,
    application_key: str,
    client: httpx.AsyncClient,
    reconnect_delay_s: int = 2,
    reconnect_max_s: int = 60,
) -> AsyncGenerator[HueEvent, None]:
    """Yield :class:`~huehub.models.HueEvent` objects from the bridge SSE stream.

    Reconnects automatically with exponential back-off when the connection
    is lost.

    Args:
        host: Bridge IP address or hostname.
        application_key: Application key for the ``hue-application-key`` header.
        client: Configured ``httpx.AsyncClient``.
        reconnect_delay_s: Initial delay between reconnect attempts in seconds.
        reconnect_max_s: Maximum reconnect delay in seconds.

    Yields:
        :class:`~huehub.models.HueEvent` for each bridge event received.
    """
    url = f"https://{host}{_SSE_PATH}"
    headers = {
        "hue-application-key": application_key,
        "Accept": "text/event-stream",
    }
    delay = reconnect_delay_s

    while True:
        try:
            log.debug("Opening SSE stream to %s", url)
            async with aconnect_sse(client, "GET", url, headers=headers) as source:
                delay = reconnect_delay_s  # reset on successful connection
                async for sse_event in source.aiter_sse():
                    if not sse_event.data:
                        continue
                    try:
                        batches = json.loads(sse_event.data)
                    except json.JSONDecodeError:
                        log.warning("Malformed SSE event data, skipping")
                        continue

                    for batch in batches:
                        event_type = batch.get("type", "update")
                        timestamp = batch.get("creationtime", "")
                        for item in batch.get("data", []):
                            yield HueEvent(
                                type=event_type,
                                resource_type=item.get("type", ""),
                                resource_id=item.get("id", ""),
                                data=item,
                                timestamp=timestamp,
                            )

        except httpx.ConnectError as exc:
            log.warning("SSE connection lost, retry in %ds: %s", delay, exc)
        except httpx.ReadTimeout as exc:
            log.debug("SSE read timeout, reconnecting: %s", exc)
        except Exception as exc:
            log.error("SSE stream error, retry in %ds: %s", delay, exc)

        await asyncio.sleep(delay)
        delay = min(delay * 2, reconnect_max_s)
