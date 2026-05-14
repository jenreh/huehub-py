"""Unit tests for the resource cache."""

import time
from pathlib import Path

import pytest

from huehub.cache import ResourceCache


@pytest.fixture
def cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ResourceCache:
    """Return a ResourceCache backed by a temporary directory."""
    monkeypatch.setattr(
        "huehub.cache._base_cache_dir",
        lambda bridge_id: tmp_path / bridge_id,
    )
    return ResourceCache("test-bridge", ttl_seconds=60)


class TestResourceCache:
    def test_miss_when_empty(self, cache: ResourceCache) -> None:
        assert cache.load() is None

    def test_save_and_load(self, cache: ResourceCache) -> None:
        data = [{"id": "a", "type": "light"}]
        cache.save(data)
        loaded = cache.load()
        assert loaded is not None
        assert loaded[0]["id"] == "a"

    def test_expired_returns_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "huehub.cache._base_cache_dir",
            lambda bridge_id: tmp_path / bridge_id,
        )
        short_cache = ResourceCache("short-bridge", ttl_seconds=0)
        short_cache.save([{"id": "x"}])

        # Sleep briefly to ensure mtime is in the past
        time.sleep(0.01)
        assert short_cache.load() is None

    def test_invalidate(self, cache: ResourceCache) -> None:
        cache.save([{"id": "b"}])
        cache.invalidate()
        assert cache.load() is None

    def test_invalidate_noop_when_empty(self, cache: ResourceCache) -> None:
        # Should not raise
        cache.invalidate()

    def test_save_overwrites(self, cache: ResourceCache) -> None:
        cache.save([{"id": "old"}])
        cache.save([{"id": "new"}])
        loaded = cache.load()
        assert loaded is not None
        assert loaded[0]["id"] == "new"
