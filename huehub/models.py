"""Immutable data models for Philips Hue Bridge resources."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BridgeInfo:
    """Basic information about a Hue Bridge.

    Args:
        host: IP address or hostname of the bridge.
        bridge_id: Unique bridge identifier (e.g. ``"ecb5fa..."``).
        model_id: Bridge model identifier.
        api_version: CLIP API version reported by the bridge.
        software_version: Firmware version of the bridge.
        name: Human-readable bridge name.
    """

    host: str
    bridge_id: str
    model_id: str | None = None
    api_version: str | None = None
    software_version: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class Light:
    """A single controllable light on the bridge.

    Args:
        id: UUID of the light resource.
        name: Human-readable name.
        is_on: Whether the light is currently on.
        is_reachable: Whether the light responds to commands.
        brightness: Brightness level 0.0–100.0, or ``None`` if unavailable.
        color_xy: CIE 1931 xy chromaticity coordinates, or ``None``.
        color_temp_mirek: Colour temperature in mirek (153–500), or ``None``.
        color_mode: Active colour mode (``"color"`` | ``"color_temperature"`` |
            ``"brightness"``), or ``None``.
        effects_available: Effects supported by this light.
        device_id: UUID of the parent device.
        archetype: Product archetype (e.g. ``"sultan_bulb"``).
    """

    id: str
    name: str
    is_on: bool
    is_reachable: bool
    brightness: float | None = None
    color_xy: tuple[float, float] | None = None
    color_temp_mirek: int | None = None
    color_mode: str | None = None
    effects_available: tuple[str, ...] = field(default_factory=tuple)
    device_id: str = ""
    archetype: str | None = None


@dataclass(frozen=True)
class Room:
    """A physical room grouping on the bridge.

    Args:
        id: UUID of the room resource.
        name: Human-readable room name.
        grouped_light_id: UUID of the ``grouped_light`` for this room.
        device_ids: UUIDs of physical devices in the room.
        light_ids: UUIDs of light resources in the room.
    """

    id: str
    name: str
    grouped_light_id: str
    device_ids: tuple[str, ...] = field(default_factory=tuple)
    light_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Zone:
    """A logical zone that may span multiple rooms.

    Args:
        id: UUID of the zone resource.
        name: Human-readable zone name.
        grouped_light_id: UUID of the ``grouped_light`` for this zone.
        light_ids: UUIDs of light resources in the zone.
    """

    id: str
    name: str
    grouped_light_id: str
    light_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class GroupedLight:
    """Represents the collective state of a group of lights.

    Args:
        id: UUID of the grouped_light resource.
        is_on: Whether any light in the group is on (``None`` if mixed).
        brightness: Average brightness 0.0–100.0 (``None`` if unavailable).
        owner_type: Type of the owning resource (``"room"`` | ``"zone"`` |
            ``"bridge_home"``).
        owner_id: UUID of the owning room or zone.
    """

    id: str
    is_on: bool | None
    brightness: float | None
    owner_type: str
    owner_id: str


@dataclass(frozen=True)
class Scene:
    """A saved lighting scene that can be recalled.

    Args:
        id: UUID of the scene resource.
        name: Human-readable scene name.
        group_id: UUID of the room or zone this scene belongs to.
        group_type: Type of the group (``"room"`` | ``"zone"``).
        is_active: Whether this scene is currently active.
        speed: Dynamic scene speed 0.0–1.0, or ``None``.
    """

    id: str
    name: str
    group_id: str
    group_type: str
    is_active: bool = False
    speed: float | None = None


@dataclass(frozen=True)
class Device:
    """A physical device (bulb, switch, sensor, etc.).

    Args:
        id: UUID of the device resource.
        name: Human-readable device name.
        model_id: Manufacturer model identifier.
        manufacturer: Manufacturer name.
        product_name: Full product name.
        archetype: Product archetype string.
        services: Service references (raw dicts from the API).
    """

    id: str
    name: str
    model_id: str | None = None
    manufacturer: str | None = None
    product_name: str | None = None
    archetype: str | None = None
    services: tuple[dict, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MotionSensor:
    """A motion/presence sensor.

    Args:
        id: UUID of the motion resource.
        name: Human-readable name.
        is_reachable: Whether the sensor is reachable.
        motion_detected: Whether motion is currently detected.
        motion_valid: Whether the motion reading is valid.
        sensitivity: Sensitivity level, or ``None``.
        device_id: UUID of the parent device.
    """

    id: str
    name: str
    is_reachable: bool
    motion_detected: bool
    motion_valid: bool
    sensitivity: int | None = None
    device_id: str = ""


@dataclass(frozen=True)
class TemperatureSensor:
    """A temperature sensor.

    Args:
        id: UUID of the temperature resource.
        name: Human-readable name.
        is_reachable: Whether the sensor is reachable.
        temperature_celsius: Current temperature in °C, or ``None``.
        temperature_valid: Whether the temperature reading is valid.
        device_id: UUID of the parent device.
    """

    id: str
    name: str
    is_reachable: bool
    temperature_celsius: float | None
    temperature_valid: bool
    device_id: str = ""


@dataclass(frozen=True)
class LightLevelSensor:
    """A light level (lux) sensor.

    Args:
        id: UUID of the light_level resource.
        name: Human-readable name.
        is_reachable: Whether the sensor is reachable.
        light_level_lux: Current illuminance in lux, or ``None``.
        light_level_valid: Whether the light level reading is valid.
        device_id: UUID of the parent device.
    """

    id: str
    name: str
    is_reachable: bool
    light_level_lux: int | None
    light_level_valid: bool
    device_id: str = ""


@dataclass(frozen=True)
class ContactSensor:
    """A contact (door/window open/close) sensor.

    Args:
        id: UUID of the contact resource.
        name: Human-readable name.
        is_reachable: Whether the sensor is reachable.
        contact: ``True`` = closed, ``False`` = open, ``None`` = unknown.
        device_id: UUID of the parent device.
    """

    id: str
    name: str
    is_reachable: bool
    contact: bool | None
    device_id: str = ""


@dataclass(frozen=True)
class EntertainmentZone:
    """An entertainment zone used for Hue Sync / streaming.

    Args:
        id: UUID of the entertainment resource.
        name: Human-readable name.
        configuration_id: UUID of the entertainment configuration.
        light_ids: UUIDs of lights in the zone.
        status: Current status (``"active"`` | ``"inactive"``), or ``None``.
    """

    id: str
    name: str
    configuration_id: str
    light_ids: tuple[str, ...] = field(default_factory=tuple)
    status: str | None = None


@dataclass(frozen=True)
class HueEvent:
    """A real-time event emitted by the bridge SSE stream.

    Args:
        type: Event type (``"update"`` | ``"add"`` | ``"delete"`` |
            ``"error"``).
        resource_type: Affected resource type (e.g. ``"light"``).
        resource_id: UUID of the affected resource.
        data: Raw event data dict.
        timestamp: ISO-8601 creation timestamp from the bridge.
    """

    type: str
    resource_type: str
    resource_id: str
    data: dict
    timestamp: str


@dataclass(frozen=True)
class ColorResult:
    """Result of a colour conversion with all available representations.

    Args:
        xy: CIE 1931 xy chromaticity coordinates.
        mirek: Colour temperature in mirek (153–500), or ``None``.
        rgb: sRGB tuple (0–255 each), or ``None``.
        hex_str: Hex colour string (e.g. ``"#FF8000"``), or ``None``.
    """

    xy: tuple[float, float]
    mirek: int | None = None
    rgb: tuple[int, int, int] | None = None
    hex_str: str | None = None


@dataclass(frozen=True)
class AllResources:
    """Complete snapshot of all resources fetched from the bridge.

    Populated by :meth:`HueBridgeClient.get_all_resources`.
    """

    lights: tuple[Light, ...] = field(default_factory=tuple)
    rooms: tuple[Room, ...] = field(default_factory=tuple)
    zones: tuple[Zone, ...] = field(default_factory=tuple)
    scenes: tuple[Scene, ...] = field(default_factory=tuple)
    devices: tuple[Device, ...] = field(default_factory=tuple)
    grouped_lights: tuple[GroupedLight, ...] = field(default_factory=tuple)
    motion_sensors: tuple[MotionSensor, ...] = field(default_factory=tuple)
    temperature_sensors: tuple[TemperatureSensor, ...] = field(default_factory=tuple)
    light_level_sensors: tuple[LightLevelSensor, ...] = field(default_factory=tuple)
    contact_sensors: tuple[ContactSensor, ...] = field(default_factory=tuple)
    entertainment_zones: tuple[EntertainmentZone, ...] = field(default_factory=tuple)
