"""Reachability comes from the device's zigbee_connectivity resource."""

import pytest
from pytest_httpx import HTTPXMock

from huehub._parsers import (
    build_connectivity_by_device,
    is_reachable_status,
    parse_contact,
    parse_light,
    parse_light_level,
    parse_motion,
    parse_temperature,
)
from huehub.client import HueBridgeClient
from huehub.config import HueConfig
from huehub.simulator import FakeBridge

pytestmark = pytest.mark.httpx_mock(assert_all_responses_were_requested=False)

_DEV = "dev-1"


def _zigbee(device_id: str, status: str) -> dict:
    return {
        "id": f"zb-{device_id}",
        "type": "zigbee_connectivity",
        "owner": {"rid": device_id, "rtype": "device"},
        "status": status,
    }


def _light() -> dict:
    return {"id": "l-1", "type": "light", "owner": {"rid": _DEV, "rtype": "device"}}


class TestIsReachableStatus:
    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            ("connected", True),
            (None, True),
            ("connectivity_issue", False),
            ("disconnected", False),
            ("pending_discovery", False),
            ("unidirectional_incoming", False),
        ],
    )
    def test_status(self, status: str | None, expected: bool) -> None:
        assert is_reachable_status(status) is expected


class TestBuildConnectivityByDevice:
    def test_maps_owner_to_status(self) -> None:
        raw = [_zigbee("a", "connected"), _zigbee("b", "connectivity_issue")]
        assert build_connectivity_by_device(raw) == {
            "a": "connected",
            "b": "connectivity_issue",
        }

    def test_skips_items_without_owner(self) -> None:
        assert build_connectivity_by_device([{"status": "connected"}]) == {}


class TestParsersUseConnectivity:
    def test_light_unreachable_on_issue(self) -> None:
        conn = {_DEV: "connectivity_issue"}
        assert parse_light(_light(), conn).is_reachable is False

    def test_light_reachable_when_connected(self) -> None:
        assert parse_light(_light(), {_DEV: "connected"}).is_reachable is True

    def test_light_reachable_when_unknown(self) -> None:
        assert parse_light(_light()).is_reachable is True

    def test_sensors_unreachable_on_issue(self) -> None:
        raw = {"id": "s", "owner": {"rid": _DEV, "rtype": "device"}, "enabled": True}
        conn = {_DEV: "disconnected"}
        for parse in (parse_motion, parse_temperature, parse_light_level):
            assert parse(raw, [], conn).is_reachable is False
        assert parse_contact(raw, [], conn).is_reachable is False

    def test_disabled_sensor_still_reachable(self) -> None:
        raw = {"id": "s", "owner": {"rid": _DEV, "rtype": "device"}, "enabled": False}
        assert parse_motion(raw, [], {_DEV: "connected"}).is_reachable is True


class TestClientReachability:
    async def test_list_lights_reports_connectivity_issue(
        self, hue_config: HueConfig, httpx_mock: HTTPXMock, fake_bridge: FakeBridge
    ) -> None:
        fake_bridge.zigbee_connectivity[1]["status"] = "connectivity_issue"
        fake_bridge.setup_mocks(httpx_mock)
        async with HueBridgeClient(hue_config) as hue:
            lights = {lig.name: lig for lig in await hue.list_lights()}
        assert lights["Desk Lamp"].is_reachable is True
        assert lights["Floor Lamp"].is_reachable is False
