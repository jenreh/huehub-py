"""Integration tests for the CLI commands."""

import json
from typing import Any

import pytest
from pytest_httpx import HTTPXMock
from typer.testing import CliRunner

from huehub.cli import app
from huehub.simulator import FakeBridge

# Allow tests to register more mocks than consumed (CLI only calls relevant endpoints)
pytestmark = pytest.mark.httpx_mock(assert_all_responses_were_requested=False)

runner = CliRunner()

_BRIDGE_HOST = "192.168.1.1"


@pytest.fixture(autouse=True)
def _mock_bridge(httpx_mock: HTTPXMock) -> None:
    """Register fake bridge mocks for all CLI tests."""
    bridge = FakeBridge(host=_BRIDGE_HOST)
    bridge.setup_mocks(httpx_mock)


def _invoke(*args: str, json_out: bool = False) -> Any:
    """Invoke the CLI with common options pre-filled."""
    base = [
        "--host",
        _BRIDGE_HOST,
        "--key",
        "test-key",
    ]
    if json_out:
        base.append("--json")
    return runner.invoke(app, base + list(args))


class TestLightsCommands:
    def test_lights_list(self) -> None:
        result = _invoke("lights", "list")
        assert result.exit_code == 0
        assert "Desk Lamp" in result.output

    def test_lights_list_json(self) -> None:
        result = _invoke("lights", "list", json_out=True)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert any(l["name"] == "Desk Lamp" for l in data)

    def test_lights_show(self) -> None:
        result = _invoke("lights", "show", "Desk Lamp")
        assert result.exit_code == 0

    def test_lights_on(self) -> None:
        result = _invoke("lights", "on", "Desk Lamp")
        assert result.exit_code == 0

    def test_lights_off(self) -> None:
        result = _invoke("lights", "off", "Floor Lamp")
        assert result.exit_code == 0

    def test_lights_set_brightness(self) -> None:
        result = _invoke("lights", "set", "Desk Lamp", "--brightness", "50")
        assert result.exit_code == 0

    def test_lights_not_found(self) -> None:
        result = _invoke("lights", "show", "Ghost Light")
        assert result.exit_code == 13  # ResourceNotFoundError exit code


class TestRoomsCommands:
    def test_rooms_list(self) -> None:
        result = _invoke("rooms", "list")
        assert result.exit_code == 0
        assert "Living Room" in result.output

    def test_rooms_show(self) -> None:
        result = _invoke("rooms", "show", "Living Room")
        assert result.exit_code == 0

    def test_rooms_on(self) -> None:
        result = _invoke("rooms", "on", "Living Room")
        assert result.exit_code == 0

    def test_rooms_off(self) -> None:
        result = _invoke("rooms", "off", "Living Room")
        assert result.exit_code == 0


class TestScenesCommands:
    def test_scenes_list(self) -> None:
        result = _invoke("scenes", "list")
        assert result.exit_code == 0
        assert "Relax" in result.output

    def test_scenes_activate(self) -> None:
        result = _invoke("scenes", "activate", "Relax", "--room", "Living Room")
        assert result.exit_code == 0

    def test_scenes_deactivate(self) -> None:
        result = _invoke("scenes", "deactivate", "Relax", "--room", "Living Room")
        assert result.exit_code == 0


class TestSensorsCommands:
    def test_sensors_list(self) -> None:
        result = _invoke("sensors", "list")
        assert result.exit_code == 0

    def test_sensors_motion(self) -> None:
        result = _invoke("sensors", "motion")
        assert result.exit_code == 0

    def test_sensors_temperature(self) -> None:
        result = _invoke("sensors", "temperature")
        assert result.exit_code == 0

    def test_sensors_light_level(self) -> None:
        result = _invoke("sensors", "light-level")
        assert result.exit_code == 0

    def test_sensors_contact(self) -> None:
        result = _invoke("sensors", "contact")
        assert result.exit_code == 0


class TestGlobalCommands:
    def test_all_off(self) -> None:
        result = _invoke("all-off")
        assert result.exit_code == 0

    def test_info(self) -> None:
        result = _invoke("info")
        assert result.exit_code == 0


class TestApiCommands:
    def test_api_get(self) -> None:
        result = _invoke("api", "get", "/clip/v2/resource/light")
        assert result.exit_code == 0

    def test_api_get_json(self) -> None:
        result = _invoke("api", "get", "/clip/v2/resource/light", json_out=True)
        assert result.exit_code == 0
