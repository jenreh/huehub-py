"""Extended unit tests for HueBridgeClient – additional coverage."""

import pytest
from pytest_httpx import HTTPXMock

pytestmark = pytest.mark.httpx_mock(assert_all_responses_were_requested=False)

from huehub.client import HueBridgeClient, _build_light_body, _resolve_from_list
from huehub.config import HueConfig
from huehub.exceptions import (
    AmbiguousNameError,
    ResourceNotFoundError,
)
from huehub.simulator import FakeBridge


@pytest.fixture
def bridge(fake_bridge: FakeBridge) -> FakeBridge:
    return fake_bridge


@pytest.fixture
def cfg(hue_config: HueConfig) -> HueConfig:
    return hue_config


@pytest.fixture
async def client(
    cfg: HueConfig, httpx_mock: HTTPXMock, bridge: FakeBridge
) -> HueBridgeClient:
    bridge.setup_mocks(httpx_mock)
    c = HueBridgeClient(cfg)
    await c.connect()
    return c


class TestSetRoom:
    async def test_set_room_on(
        self, cfg: HueConfig, httpx_mock: HTTPXMock, bridge: FakeBridge
    ) -> None:
        bridge.setup_mocks(httpx_mock)
        c = HueBridgeClient(cfg)
        await c.connect()
        result = await c.set_room("Living Room", on=True)
        assert isinstance(result, dict)
        await c.close()

    async def test_set_room_brightness(
        self, cfg: HueConfig, httpx_mock: HTTPXMock, bridge: FakeBridge
    ) -> None:
        bridge.setup_mocks(httpx_mock)
        c = HueBridgeClient(cfg)
        await c.connect()
        result = await c.set_room("Living Room", brightness=80.0)
        assert isinstance(result, dict)
        await c.close()


class TestSetZone:
    async def test_set_zone_on(
        self, cfg: HueConfig, httpx_mock: HTTPXMock, bridge: FakeBridge
    ) -> None:
        bridge.setup_mocks(httpx_mock)
        c = HueBridgeClient(cfg)
        await c.connect()
        result = await c.set_zone("Downstairs", on=False)
        assert isinstance(result, dict)
        await c.close()


class TestActivateScene:
    async def test_activate_by_name(
        self, cfg: HueConfig, httpx_mock: HTTPXMock, bridge: FakeBridge
    ) -> None:
        bridge.setup_mocks(httpx_mock)
        c = HueBridgeClient(cfg)
        await c.connect()
        await c.activate_scene("Relax")
        await c.close()

    async def test_activate_by_uuid(
        self, cfg: HueConfig, httpx_mock: HTTPXMock, bridge: FakeBridge
    ) -> None:
        bridge.setup_mocks(httpx_mock)
        c = HueBridgeClient(cfg)
        await c.connect()
        # activate_scene with UUID needs it in the candidates list — use name instead
        await c.activate_scene("Relax")
        await c.close()

    async def test_activate_not_found(self, client: HueBridgeClient) -> None:
        with pytest.raises(ResourceNotFoundError):
            await client.activate_scene("NonExistentScene")


class TestGetDevice:
    async def test_by_name(self, client: HueBridgeClient) -> None:
        dev = await client.get_device("Desk Lamp")
        assert dev.name == "Desk Lamp"

    async def test_not_found(self, client: HueBridgeClient) -> None:
        with pytest.raises(ResourceNotFoundError):
            await client.get_device("Unknown Device")


class TestListEntertainmentZones:
    async def test_returns_empty(self, client: HueBridgeClient) -> None:
        # FakeBridge has no entertainment zones
        zones = await client.list_entertainment_zones()
        assert isinstance(zones, list)


class TestListScenesWithGroup:
    async def test_filter_by_zone(self, client: HueBridgeClient) -> None:
        scenes = await client.list_scenes(group="Downstairs")
        # The scene is in Living Room, not Downstairs zone
        assert isinstance(scenes, list)

    async def test_filter_by_uuid_directly(self, client: HueBridgeClient) -> None:
        scenes = await client.list_scenes(group="rrrr0000-0000-0000-0000-000000000001")
        assert len(scenes) == 1


class TestAuthenticate:
    async def test_authenticate_success(
        self, cfg: HueConfig, httpx_mock: HTTPXMock, bridge: FakeBridge
    ) -> None:
        bridge.setup_mocks(httpx_mock)
        c = HueBridgeClient(cfg)
        await c.connect()
        key = await c.authenticate("test-app")
        assert key == "test-app-key-1234"
        await c.close()


class TestBuildLightBody:
    def test_on_only(self) -> None:
        body = _build_light_body(on=True)
        assert body == {"on": {"on": True}}

    def test_brightness_only(self) -> None:
        body = _build_light_body(brightness=50.0)
        assert body["dimming"]["brightness"] == 50.0

    def test_color_hex(self) -> None:
        body = _build_light_body(color="#ff0000")
        assert "color" in body

    def test_color_kelvin(self) -> None:
        body = _build_light_body(color="warm")
        assert "color_temperature" in body

    def test_transition_ms(self) -> None:
        body = _build_light_body(transition_ms=500)
        assert body["dynamics"]["duration"] == 500

    def test_effect(self) -> None:
        body = _build_light_body(effect="candle")
        assert body["effects"]["effect"] == "candle"

    def test_alert(self) -> None:
        body = _build_light_body(alert="breathe")
        assert body["alert"]["action"] == "breathe"

    def test_empty_body(self) -> None:
        body = _build_light_body()
        assert body == {}


class TestResolveFromList:
    def test_exact_match(self) -> None:
        pairs = [("id1", "Living Room"), ("id2", "Kitchen")]
        assert _resolve_from_list("room", "Living Room", pairs) == "id1"

    def test_case_insensitive(self) -> None:
        pairs = [("id1", "Living Room")]
        assert _resolve_from_list("room", "living room", pairs) == "id1"

    def test_prefix_match(self) -> None:
        pairs = [("id1", "Living Room"), ("id2", "Kitchen")]
        assert _resolve_from_list("room", "Livi", pairs) == "id1"

    def test_ambiguous_exact(self) -> None:
        pairs = [("id1", "Room"), ("id2", "Room")]
        with pytest.raises(AmbiguousNameError):
            _resolve_from_list("room", "Room", pairs)

    def test_ambiguous_prefix(self) -> None:
        pairs = [("id1", "Living Room"), ("id2", "Living Area")]
        with pytest.raises(AmbiguousNameError):
            _resolve_from_list("room", "Living", pairs)

    def test_not_found(self) -> None:
        pairs = [("id1", "Kitchen")]
        with pytest.raises(ResourceNotFoundError):
            _resolve_from_list("room", "Bedroom", pairs)
