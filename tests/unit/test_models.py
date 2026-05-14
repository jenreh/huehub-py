"""Unit tests for huehub dataclasses."""

import pytest

from huehub.models import (
    AllResources,
    ColorResult,
    ContactSensor,
    HueEvent,
    Light,
    MotionSensor,
    Room,
    Scene,
    TemperatureSensor,
)


class TestLight:
    def test_minimal_creation(self) -> None:
        light = Light(
            id="abc-123",
            name="Test Light",
            is_on=True,
            is_reachable=True,
        )
        assert light.id == "abc-123"
        assert light.brightness is None
        assert light.color_xy is None
        assert light.effects_available == ()

    def test_full_creation(self) -> None:
        light = Light(
            id="abc-123",
            name="Desk Lamp",
            is_on=True,
            is_reachable=True,
            brightness=75.0,
            color_xy=(0.31, 0.33),
            color_temp_mirek=370,
            color_mode="color",
            effects_available=("candle", "fire"),
            device_id="dev-001",
            archetype="sultan_bulb",
        )
        assert light.brightness == 75.0
        assert light.effects_available == ("candle", "fire")

    def test_frozen_immutability(self) -> None:
        light = Light(id="x", name="y", is_on=False, is_reachable=True)
        with pytest.raises(Exception):
            light.name = "new"  # type: ignore[misc]


class TestRoom:
    def test_creation(self) -> None:
        room = Room(
            id="room-1",
            name="Living Room",
            grouped_light_id="gl-1",
            device_ids=("dev-1", "dev-2"),
            light_ids=("light-1", "light-2"),
        )
        assert room.name == "Living Room"
        assert len(room.light_ids) == 2


class TestScene:
    def test_defaults(self) -> None:
        scene = Scene(
            id="scene-1",
            name="Relax",
            group_id="room-1",
            group_type="room",
        )
        assert scene.is_active is False
        assert scene.speed is None


class TestMotionSensor:
    def test_creation(self) -> None:
        sensor = MotionSensor(
            id="mot-1",
            name="Hallway Sensor",
            is_reachable=True,
            motion_detected=False,
            motion_valid=True,
            sensitivity=3,
            device_id="dev-1",
        )
        assert sensor.sensitivity == 3


class TestTemperatureSensor:
    def test_with_reading(self) -> None:
        sensor = TemperatureSensor(
            id="temp-1",
            name="Kitchen Sensor",
            is_reachable=True,
            temperature_celsius=22.5,
            temperature_valid=True,
        )
        assert sensor.temperature_celsius == 22.5

    def test_no_reading(self) -> None:
        sensor = TemperatureSensor(
            id="temp-1",
            name="Kitchen Sensor",
            is_reachable=False,
            temperature_celsius=None,
            temperature_valid=False,
        )
        assert sensor.temperature_celsius is None


class TestContactSensor:
    def test_open(self) -> None:
        sensor = ContactSensor(id="c-1", name="Door", is_reachable=True, contact=False)
        assert sensor.contact is False

    def test_closed(self) -> None:
        sensor = ContactSensor(id="c-1", name="Door", is_reachable=True, contact=True)
        assert sensor.contact is True

    def test_unknown(self) -> None:
        sensor = ContactSensor(id="c-1", name="Door", is_reachable=False, contact=None)
        assert sensor.contact is None


class TestColorResult:
    def test_xy_only(self) -> None:
        cr = ColorResult(xy=(0.3, 0.3))
        assert cr.mirek is None
        assert cr.rgb is None

    def test_full(self) -> None:
        cr = ColorResult(
            xy=(0.31, 0.33), mirek=370, rgb=(255, 200, 100), hex_str="#FFC864"
        )
        assert cr.hex_str == "#FFC864"


class TestHueEvent:
    def test_creation(self) -> None:
        event = HueEvent(
            type="update",
            resource_type="light",
            resource_id="abc-123",
            data={"on": {"on": True}},
            timestamp="2026-05-14T10:00:00Z",
        )
        assert event.type == "update"
        assert event.data["on"]["on"] is True


class TestAllResources:
    def test_empty(self) -> None:
        resources = AllResources()
        assert resources.lights == ()
        assert resources.rooms == ()

    def test_with_data(self) -> None:
        light = Light(id="l1", name="L", is_on=True, is_reachable=True)
        resources = AllResources(lights=(light,))
        assert len(resources.lights) == 1
