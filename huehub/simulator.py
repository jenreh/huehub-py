"""Fake Hue Bridge for testing – no real bridge required.

Provides :class:`FakeBridge` which stores a configurable set of lights,
rooms, zones, scenes, and sensors and registers all corresponding HTTP
mock responses via ``pytest-httpx``'s ``HTTPXMock`` fixture.

Usage in a pytest test::

    def test_list_lights(httpx_mock: HTTPXMock):
        bridge = FakeBridge()
        bridge.setup_mocks(httpx_mock)
        # now use the client against the fake bridge
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

_DEFAULT_HOST = "192.168.1.1"

# ---------------------------------------------------------------------------
# Default fixture data
# ---------------------------------------------------------------------------

_LIGHT_1: dict[str, Any] = {
    "id": "aaaa0000-0000-0000-0000-000000000001",
    "type": "light",
    "metadata": {"name": "Desk Lamp", "archetype": "sultan_bulb"},
    "on": {"on": True},
    "dimming": {"brightness": 75.0},
    "color": {"xy": {"x": 0.3127, "y": 0.3290}},
    "color_temperature": {"mirek": 370},
    "owner": {"rid": "dddd0000-0000-0000-0000-000000000001", "rtype": "device"},
    "status": {"reachability": "connected"},
    "effects": {"effect_values": ["candle", "fire"]},
}

_LIGHT_2: dict[str, Any] = {
    "id": "aaaa0000-0000-0000-0000-000000000002",
    "type": "light",
    "metadata": {"name": "Floor Lamp", "archetype": "floor_shade"},
    "on": {"on": False},
    "dimming": {"brightness": 0.0},
    "color_temperature": {"mirek": 300},
    "owner": {"rid": "dddd0000-0000-0000-0000-000000000002", "rtype": "device"},
    "status": {"reachability": "connected"},
    "effects": {"effect_values": []},
}

_DEVICE_1: dict[str, Any] = {
    "id": "dddd0000-0000-0000-0000-000000000001",
    "type": "device",
    "metadata": {"name": "Desk Lamp", "archetype": "sultan_bulb"},
    "product_data": {
        "model_id": "LCA001",
        "manufacturer_name": "Signify Netherlands B.V.",
        "product_name": "Hue color lamp",
    },
    "services": [{"rid": "aaaa0000-0000-0000-0000-000000000001", "rtype": "light"}],
}

_DEVICE_2: dict[str, Any] = {
    "id": "dddd0000-0000-0000-0000-000000000002",
    "type": "device",
    "metadata": {"name": "Floor Lamp", "archetype": "floor_shade"},
    "product_data": {
        "model_id": "LCT015",
        "manufacturer_name": "Signify Netherlands B.V.",
        "product_name": "Hue White and color ambiance",
    },
    "services": [{"rid": "aaaa0000-0000-0000-0000-000000000002", "rtype": "light"}],
}

_GROUPED_LIGHT: dict[str, Any] = {
    "id": "gggg0000-0000-0000-0000-000000000001",
    "type": "grouped_light",
    "on": {"on": True},
    "dimming": {"brightness": 75.0},
}

_BRIDGE_HOME_GL: dict[str, Any] = {
    "id": "gggg0000-0000-0000-0000-000000000099",
    "type": "grouped_light",
    "on": {"on": True},
    "dimming": {"brightness": 75.0},
}

_ROOM: dict[str, Any] = {
    "id": "rrrr0000-0000-0000-0000-000000000001",
    "type": "room",
    "metadata": {"name": "Living Room"},
    "children": [
        {"rid": "dddd0000-0000-0000-0000-000000000001", "rtype": "device"},
        {"rid": "dddd0000-0000-0000-0000-000000000002", "rtype": "device"},
    ],
    "services": [
        {"rid": "gggg0000-0000-0000-0000-000000000001", "rtype": "grouped_light"}
    ],
}

_ZONE: dict[str, Any] = {
    "id": "zzzz0000-0000-0000-0000-000000000001",
    "type": "zone",
    "metadata": {"name": "Downstairs"},
    "children": [
        {"rid": "aaaa0000-0000-0000-0000-000000000001", "rtype": "light"},
        {"rid": "aaaa0000-0000-0000-0000-000000000002", "rtype": "light"},
    ],
    "services": [
        {"rid": "gggg0000-0000-0000-0000-000000000002", "rtype": "grouped_light"}
    ],
}

_ZONE_GL: dict[str, Any] = {
    "id": "gggg0000-0000-0000-0000-000000000002",
    "type": "grouped_light",
    "on": {"on": True},
    "dimming": {"brightness": 60.0},
}

_SCENE: dict[str, Any] = {
    "id": "ssss0000-0000-0000-0000-000000000001",
    "type": "scene",
    "metadata": {"name": "Relax"},
    "group": {"rid": "rrrr0000-0000-0000-0000-000000000001", "rtype": "room"},
    "status": {"active": "inactive"},
}

_BRIDGE: dict[str, Any] = {
    "id": "bbbb0000-0000-0000-0000-000000000001",
    "type": "bridge",
    "bridge_id": "ecb5fa1234ab",
    "metadata": {"name": "My Hue Bridge"},
    "software_update": {"version": "1.59.1959097030"},
}

_MOTION: dict[str, Any] = {
    "id": "mmmm0000-0000-0000-0000-000000000001",
    "type": "motion",
    "owner": {"rid": "dddd0000-0000-0000-0000-000000000001", "rtype": "device"},
    "motion": {"motion": False, "motion_valid": True},
    "enabled": True,
}

_TEMPERATURE: dict[str, Any] = {
    "id": "tttt0000-0000-0000-0000-000000000001",
    "type": "temperature",
    "owner": {"rid": "dddd0000-0000-0000-0000-000000000001", "rtype": "device"},
    "temperature": {"temperature": 21.5, "temperature_valid": True},
    "enabled": True,
}

_LIGHT_LEVEL: dict[str, Any] = {
    "id": "llll0000-0000-0000-0000-000000000001",
    "type": "light_level",
    "owner": {"rid": "dddd0000-0000-0000-0000-000000000001", "rtype": "device"},
    "light": {"light_level": 1500, "light_level_valid": True},
    "enabled": True,
}

_CONTACT: dict[str, Any] = {
    "id": "cccc0000-0000-0000-0000-000000000001",
    "type": "contact",
    "owner": {"rid": "dddd0000-0000-0000-0000-000000000001", "rtype": "device"},
    "contact_report": {"state": "no_contact"},
    "enabled": True,
}

_BRIDGE_HOME: dict[str, Any] = {
    "id": "hhhh0000-0000-0000-0000-000000000001",
    "type": "bridge_home",
    "services": [
        {"rid": "gggg0000-0000-0000-0000-000000000099", "rtype": "grouped_light"}
    ],
}


class FakeBridge:
    """In-memory fake Hue Bridge for use with pytest-httpx.

    All ``data`` lists are mutable copies of the defaults, so tests can modify
    them freely before calling :meth:`setup_mocks`.

    Args:
        host: Bridge hostname used for URL matching.
    """

    def __init__(self, host: str = _DEFAULT_HOST) -> None:
        self.host = host
        self.lights: list[dict] = [deepcopy(_LIGHT_1), deepcopy(_LIGHT_2)]
        self.devices: list[dict] = [deepcopy(_DEVICE_1), deepcopy(_DEVICE_2)]
        self.rooms: list[dict] = [deepcopy(_ROOM)]
        self.zones: list[dict] = [deepcopy(_ZONE)]
        self.grouped_lights: list[dict] = [
            deepcopy(_GROUPED_LIGHT),
            deepcopy(_ZONE_GL),
            deepcopy(_BRIDGE_HOME_GL),
        ]
        self.scenes: list[dict] = [deepcopy(_SCENE)]
        self.bridges: list[dict] = [deepcopy(_BRIDGE)]
        self.bridge_homes: list[dict] = [deepcopy(_BRIDGE_HOME)]
        self.motions: list[dict] = [deepcopy(_MOTION)]
        self.temperatures: list[dict] = [deepcopy(_TEMPERATURE)]
        self.light_levels: list[dict] = [deepcopy(_LIGHT_LEVEL)]
        self.contacts: list[dict] = [deepcopy(_CONTACT)]

    # ------------------------------------------------------------------
    # Mock setup
    # ------------------------------------------------------------------

    def all_resources(self) -> list[dict]:
        """Return the combined flat resource list for ``GET /clip/v2/resource``."""
        return (
            self.lights
            + self.devices
            + self.rooms
            + self.zones
            + self.grouped_lights
            + self.scenes
            + self.bridges
            + self.bridge_homes
            + self.motions
            + self.temperatures
            + self.light_levels
            + self.contacts
        )

    def _ok(self, data: list[dict]) -> dict:
        return {"data": data, "errors": []}

    def setup_mocks(self, httpx_mock: Any) -> None:
        """Register all necessary HTTP mock responses.

        Must be called after modifying fixture data and before running the
        code under test.

        Args:
            httpx_mock: The ``HTTPXMock`` fixture from ``pytest-httpx``.
        """
        base = f"https://{self.host}"

        # GET /clip/v2/resource  – all resources (reusable: refresh=True may call it again)
        for _ in range(5):
            httpx_mock.add_response(
                method="GET",
                url=f"{base}/clip/v2/resource",
                json=self._ok(self.all_resources()),
            )

        # Per-type GET endpoints
        for rtype, items in [
            ("light", self.lights),
            ("room", self.rooms),
            ("zone", self.zones),
            ("grouped_light", self.grouped_lights),
            ("scene", self.scenes),
            ("device", self.devices),
            ("bridge", self.bridges),
        ]:
            httpx_mock.add_response(
                method="GET",
                url=f"{base}/clip/v2/resource/{rtype}",
                json=self._ok(items),
            )

        # PUT on individual lights/rooms/zones/scenes – return first item
        for rtype in ("light", "grouped_light", "scene"):
            httpx_mock.add_response(
                method="PUT",
                url=re.compile(
                    rf"https://{re.escape(self.host)}/clip/v2/resource/{rtype}/.+"
                ),
                json=self._ok([{"rid": "updated", "rtype": rtype}]),
            )

        # POST /api – authentication
        httpx_mock.add_response(
            method="POST",
            url=f"{base}/api",
            json=[
                {
                    "success": {
                        "username": "test-app-key-1234",
                        "clientkey": "test-client-key-5678",
                    }
                }
            ],
        )
