"""Resource cache for Hue Bridge responses.

Caches the full resource payload from ``GET /clip/v2/resource`` in a JSON
file under ``~/.cache/huehub/<bridge-id>/resources.json``.

TTL is based on file modification time, so the cache survives process
restarts.  Call :meth:`ResourceCache.invalidate` to force a refresh.
"""

import json
import logging
import time
from pathlib import Path

from huehub.config import cache_dir as _base_cache_dir

log = logging.getLogger(__name__)


class ResourceCache:
    """On-disk resource cache with TTL.

    Args:
        bridge_id: Bridge identifier used as the cache sub-directory.
        ttl_seconds: How many seconds cached data is considered fresh.
    """

    def __init__(self, bridge_id: str, ttl_seconds: int = 300) -> None:
        self._ttl = ttl_seconds
        cache_path = _base_cache_dir(bridge_id)
        cache_path.mkdir(parents=True, exist_ok=True)
        self._path: Path = cache_path / "resources.json"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> list[dict] | None:
        """Return cached resource data if it exists and is still fresh.

        Returns:
            The cached resource list, or ``None`` if absent or expired.
        """
        if not self._path.exists():
            return None
        age = time.time() - self._path.stat().st_mtime
        if age > self._ttl:
            log.debug("Cache expired (age=%.0fs > ttl=%ds)", age, self._ttl)
            return None
        try:
            data: list[dict] = json.loads(self._path.read_text())
            log.debug("Cache hit (%d resources, age=%.0fs)", len(data), age)
            return data
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Failed to read cache: %s", exc)
            return None

    def save(self, data: list[dict]) -> None:
        """Persist resource data to disk.

        Args:
            data: List of raw resource dicts from ``GET /clip/v2/resource``.
        """
        try:
            self._path.write_text(json.dumps(data))
            log.debug("Cache saved (%d resources)", len(data))
        except OSError as exc:
            log.warning("Failed to write cache: %s", exc)

    def invalidate(self) -> None:
        """Delete the cache file, forcing a fresh fetch on next access."""
        if self._path.exists():
            self._path.unlink()
            log.debug("Cache invalidated")
