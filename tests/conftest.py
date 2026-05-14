"""Shared pytest fixtures for huehub tests."""

import pytest

from huehub.config import HueConfig
from huehub.simulator import FakeBridge


@pytest.fixture
def fake_bridge() -> FakeBridge:
    """Return a default FakeBridge instance."""
    return FakeBridge(host="192.168.1.1")


@pytest.fixture
def hue_config(fake_bridge: FakeBridge) -> HueConfig:
    """Return a HueConfig pointing at the fake bridge."""
    cfg = HueConfig()
    cfg.bridge.host = fake_bridge.host
    cfg.bridge.application_key = "test-app-key"
    cfg.tls.mode = "skip"
    cfg.cache.ttl_seconds = 300  # use in-memory cache within a single test
    return cfg
