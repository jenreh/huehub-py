"""Unit tests for HueBridgeClient using pytest-httpx."""

import pytest
from pytest_httpx import HTTPXMock

# Allow tests to register more mocks than actually consumed (e.g. connect-only tests)
pytestmark = pytest.mark.httpx_mock(assert_all_responses_were_requested=False)

from huehub.client import HueBridgeClient
from huehub.config import HueConfig
from huehub.exceptions import (
    BridgeUnavailableError,
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


class TestConnect:
    async def test_raises_without_host(self) -> None:
        cfg = HueConfig()
        c = HueBridgeClient(cfg)
        with pytest.raises(BridgeUnavailableError):
            await c.connect()

    async def test_connects_with_host(
        self, cfg: HueConfig, httpx_mock: HTTPXMock, bridge: FakeBridge
    ) -> None:
        bridge.setup_mocks(httpx_mock)
        c = HueBridgeClient(cfg)
        await c.connect()
        await c.close()


class TestGetBridgeInfo:
    async def test_returns_bridge_info(self, client: HueBridgeClient) -> None:
        info = await client.get_bridge_info()
        assert info.host == "192.168.1.1"
        assert info.bridge_id != ""


class TestListLights:
    async def test_returns_all_lights(self, client: HueBridgeClient) -> None:
        lights = await client.list_lights()
        assert len(lights) == 2
        names = {l.name for l in lights}
        assert "Desk Lamp" in names
        assert "Floor Lamp" in names

    async def test_light_fields(self, client: HueBridgeClient) -> None:
        lights = await client.list_lights()
        desk = next(l for l in lights if l.name == "Desk Lamp")
        assert desk.is_on is True
        assert desk.brightness == 75.0
        assert isinstance(desk.color_xy, tuple)


class TestGetLight:
    async def test_by_name(self, client: HueBridgeClient) -> None:
        light = await client.get_light("Desk Lamp")
        assert light.name == "Desk Lamp"

    async def test_by_uuid(self, client: HueBridgeClient) -> None:
        light = await client.get_light("aaaa0000-0000-0000-0000-000000000001")
        assert light.name == "Desk Lamp"

    async def test_not_found_raises(self, client: HueBridgeClient) -> None:
        with pytest.raises(ResourceNotFoundError):
            await client.get_light("Nonexistent Light")

    async def test_case_insensitive_name(self, client: HueBridgeClient) -> None:
        light = await client.get_light("desk lamp")
        assert light.name == "Desk Lamp"


class TestListRooms:
    async def test_returns_room(self, client: HueBridgeClient) -> None:
        rooms = await client.list_rooms()
        assert len(rooms) == 1
        assert rooms[0].name == "Living Room"


class TestGetRoom:
    async def test_by_name(self, client: HueBridgeClient) -> None:
        room = await client.get_room("Living Room")
        assert room.name == "Living Room"
        assert len(room.light_ids) > 0

    async def test_not_found_raises(self, client: HueBridgeClient) -> None:
        with pytest.raises(ResourceNotFoundError):
            await client.get_room("Kitchen")


class TestListZones:
    async def test_returns_zone(self, client: HueBridgeClient) -> None:
        zones = await client.list_zones()
        assert len(zones) == 1
        assert zones[0].name == "Downstairs"


class TestListScenes:
    async def test_returns_all_scenes(self, client: HueBridgeClient) -> None:
        scenes = await client.list_scenes()
        assert len(scenes) == 1
        assert scenes[0].name == "Relax"

    async def test_filter_by_group(self, client: HueBridgeClient) -> None:
        scenes = await client.list_scenes(group="Living Room")
        assert len(scenes) == 1

    async def test_filter_no_match(self, client: HueBridgeClient) -> None:
        scenes = await client.list_scenes(group="Kitchen")
        assert len(scenes) == 0


class TestListDevices:
    async def test_returns_devices(self, client: HueBridgeClient) -> None:
        devices = await client.list_devices()
        assert len(devices) == 2


class TestSetLight:
    async def test_turn_on(
        self, cfg: HueConfig, httpx_mock: HTTPXMock, bridge: FakeBridge
    ) -> None:
        bridge.setup_mocks(httpx_mock)
        c = HueBridgeClient(cfg)
        await c.connect()
        # Should not raise
        await c.set_light("Desk Lamp", on=True)
        await c.close()

    async def test_set_brightness(
        self, cfg: HueConfig, httpx_mock: HTTPXMock, bridge: FakeBridge
    ) -> None:
        bridge.setup_mocks(httpx_mock)
        c = HueBridgeClient(cfg)
        await c.connect()
        await c.set_light("Floor Lamp", brightness=50.0)
        await c.close()


class TestSensors:
    async def test_list_motion_sensors(self, client: HueBridgeClient) -> None:
        sensors = await client.list_motion_sensors()
        assert len(sensors) == 1
        assert sensors[0].motion_detected is False

    async def test_list_temperature_sensors(self, client: HueBridgeClient) -> None:
        sensors = await client.list_temperature_sensors()
        assert len(sensors) == 1
        assert sensors[0].temperature_celsius == 21.5

    async def test_list_light_level_sensors(self, client: HueBridgeClient) -> None:
        sensors = await client.list_light_level_sensors()
        assert len(sensors) == 1

    async def test_list_contact_sensors(self, client: HueBridgeClient) -> None:
        sensors = await client.list_contact_sensors()
        assert len(sensors) == 1


class TestAllOff:
    async def test_all_off(
        self, cfg: HueConfig, httpx_mock: HTTPXMock, bridge: FakeBridge
    ) -> None:
        bridge.setup_mocks(httpx_mock)
        c = HueBridgeClient(cfg)
        await c.connect()
        # Should not raise
        await c.all_off()
        await c.close()


class TestGetAllResourcesCache:
    async def test_returns_cached_on_second_call(self, client: HueBridgeClient) -> None:
        r1 = await client.get_all_resources()
        r2 = await client.get_all_resources()
        assert r1 is r2  # same object from in-memory cache

    async def test_refresh_bypasses_cache(
        self, cfg: HueConfig, httpx_mock: HTTPXMock, bridge: FakeBridge
    ) -> None:
        bridge.setup_mocks(httpx_mock)
        c = HueBridgeClient(cfg)
        await c.connect()
        r1 = await c.get_all_resources()
        r2 = await c.get_all_resources(refresh=True)
        # refresh returns new object
        assert r1 is not r2
        await c.close()
