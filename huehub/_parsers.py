"""Parsers that convert raw CLIP v2 JSON dicts into huehub dataclasses.

Each function accepts the ``data`` array items returned by the bridge and
produces the corresponding frozen dataclass.  Missing fields are handled
gracefully to tolerate differences between bridge firmware versions.
"""

import logging

from huehub.models import (
    ContactSensor,
    Device,
    EntertainmentZone,
    GroupedLight,
    Light,
    LightLevelSensor,
    MotionSensor,
    Room,
    Scene,
    TemperatureSensor,
    Zone,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Light
# ---------------------------------------------------------------------------


def parse_light(raw: dict) -> Light:
    """Parse a CLIP v2 ``light`` resource dict.

    Args:
        raw: Single item from the bridge ``data`` array.

    Returns:
        A :class:`~huehub.models.Light` dataclass.
    """
    on_obj = raw.get("on") or {}
    dim_obj = raw.get("dimming") or {}
    color_obj = raw.get("color") or {}
    temp_obj = raw.get("color_temperature") or {}
    meta = raw.get("metadata") or {}
    owner = raw.get("owner") or {}
    effects = (raw.get("effects") or {}).get("effect_values") or []

    is_on = on_obj.get("on", False)

    brightness = dim_obj.get("brightness")

    color_xy: tuple[float, float] | None = None
    xy_raw = color_obj.get("xy")
    if xy_raw:
        color_xy = (float(xy_raw.get("x", 0.0)), float(xy_raw.get("y", 0.0)))

    color_temp_mirek: int | None = None
    mirek_val = temp_obj.get("mirek")
    if mirek_val is not None:
        color_temp_mirek = int(mirek_val)

    color_mode: str | None = None
    if raw.get("color_mode"):
        color_mode = raw["color_mode"]
    elif color_xy and not color_temp_mirek:
        color_mode = "color"
    elif color_temp_mirek:
        color_mode = "color_temperature"
    elif brightness is not None:
        color_mode = "brightness"

    # Reachability sits on the device, not the light resource itself.
    # We use the "status" field as a proxy when available.
    status = raw.get("status") or {}
    is_reachable = status.get("reachability") != "disconnected"

    return Light(
        id=raw.get("id", ""),
        name=meta.get("name", raw.get("name", "")),
        is_on=bool(is_on),
        is_reachable=is_reachable,
        brightness=float(brightness) if brightness is not None else None,
        color_xy=color_xy,
        color_temp_mirek=color_temp_mirek,
        color_mode=color_mode,
        effects_available=tuple(effects),
        device_id=owner.get("rid", ""),
        archetype=meta.get("archetype"),
    )


# ---------------------------------------------------------------------------
# GroupedLight
# ---------------------------------------------------------------------------


def parse_grouped_light(
    raw: dict, rooms: list[dict], zones: list[dict]
) -> GroupedLight:
    """Parse a ``grouped_light`` resource dict.

    Args:
        raw: Single item from the bridge ``data`` array.
        rooms: Raw room dicts (used to find owner type/id).
        zones: Raw zone dicts (used to find owner type/id).

    Returns:
        A :class:`~huehub.models.GroupedLight` dataclass.
    """
    on_obj = raw.get("on") or {}
    dim_obj = raw.get("dimming") or {}
    gl_id = raw.get("id", "")

    owner_type = "bridge_home"
    owner_id = ""

    # Search rooms and zones for a match
    for room in rooms:
        for svc in room.get("services") or []:
            if svc.get("rid") == gl_id and svc.get("rtype") == "grouped_light":
                owner_type = "room"
                owner_id = room.get("id", "")
                break
    if not owner_id:
        for zone in zones:
            for svc in zone.get("services") or []:
                if svc.get("rid") == gl_id and svc.get("rtype") == "grouped_light":
                    owner_type = "zone"
                    owner_id = zone.get("id", "")
                    break

    is_on: bool | None = on_obj.get("on") if on_obj else None
    brightness: float | None = (
        float(dim_obj["brightness"]) if "brightness" in dim_obj else None
    )

    return GroupedLight(
        id=gl_id,
        is_on=is_on,
        brightness=brightness,
        owner_type=owner_type,
        owner_id=owner_id,
    )


# ---------------------------------------------------------------------------
# Room
# ---------------------------------------------------------------------------


def parse_room(raw: dict, lights_by_device: dict[str, str]) -> Room:
    """Parse a ``room`` resource dict.

    Args:
        raw: Single item from the bridge ``data`` array.
        lights_by_device: Mapping ``{device_id: light_id}`` for fast lookup.

    Returns:
        A :class:`~huehub.models.Room` dataclass.
    """
    meta = raw.get("metadata") or {}
    children = raw.get("children") or []
    services = raw.get("services") or []

    grouped_light_id = ""
    for svc in services:
        if svc.get("rtype") == "grouped_light":
            grouped_light_id = svc.get("rid", "")
            break

    device_ids = [
        child.get("rid", "") for child in children if child.get("rtype") == "device"
    ]

    light_ids = [lid for did in device_ids if (lid := lights_by_device.get(did))]

    return Room(
        id=raw.get("id", ""),
        name=meta.get("name", raw.get("name", "")),
        grouped_light_id=grouped_light_id,
        device_ids=tuple(device_ids),
        light_ids=tuple(light_ids),
    )


# ---------------------------------------------------------------------------
# Zone
# ---------------------------------------------------------------------------


def parse_zone(raw: dict, lights_by_id: dict[str, str]) -> Zone:
    """Parse a ``zone`` resource dict.

    Args:
        raw: Single item from the bridge ``data`` array.
        lights_by_id: Mapping ``{light_id: light_id}`` (set of known IDs).

    Returns:
        A :class:`~huehub.models.Zone` dataclass.
    """
    meta = raw.get("metadata") or {}
    children = raw.get("children") or []
    services = raw.get("services") or []

    grouped_light_id = ""
    for svc in services:
        if svc.get("rtype") == "grouped_light":
            grouped_light_id = svc.get("rid", "")
            break

    light_ids: list[str] = []
    for child in children:
        if child.get("rtype") == "light":
            lid = child.get("rid", "")
            if lid in lights_by_id:
                light_ids.append(lid)

    return Zone(
        id=raw.get("id", ""),
        name=meta.get("name", raw.get("name", "")),
        grouped_light_id=grouped_light_id,
        light_ids=tuple(light_ids),
    )


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------


def parse_scene(raw: dict) -> Scene:
    """Parse a ``scene`` resource dict.

    Args:
        raw: Single item from the bridge ``data`` array.

    Returns:
        A :class:`~huehub.models.Scene` dataclass.
    """
    meta = raw.get("metadata") or {}
    group = raw.get("group") or {}
    status = raw.get("status") or {}
    speed = (raw.get("speed") or {}).get("speed")

    return Scene(
        id=raw.get("id", ""),
        name=meta.get("name", raw.get("name", "")),
        group_id=group.get("rid", ""),
        group_type=group.get("rtype", "room"),
        is_active=status.get("active") == "active",
        speed=float(speed) if speed is not None else None,
    )


# ---------------------------------------------------------------------------
# Device
# ---------------------------------------------------------------------------


def parse_device(raw: dict) -> Device:
    """Parse a ``device`` resource dict.

    Args:
        raw: Single item from the bridge ``data`` array.

    Returns:
        A :class:`~huehub.models.Device` dataclass.
    """
    meta = raw.get("metadata") or {}
    product = raw.get("product_data") or {}
    services = raw.get("services") or []

    return Device(
        id=raw.get("id", ""),
        name=meta.get("name", raw.get("name", "")),
        model_id=product.get("model_id"),
        manufacturer=product.get("manufacturer_name"),
        product_name=product.get("product_name"),
        archetype=meta.get("archetype"),
        services=tuple(services),
    )


# ---------------------------------------------------------------------------
# Sensors
# ---------------------------------------------------------------------------


def parse_motion(raw: dict, devices: list[dict]) -> MotionSensor:
    """Parse a ``motion`` resource dict.

    Args:
        raw: Single item from the bridge ``data`` array.
        devices: Raw device dicts used to resolve the sensor name.

    Returns:
        A :class:`~huehub.models.MotionSensor` dataclass.
    """
    owner = raw.get("owner") or {}
    device_id = owner.get("rid", "")
    name = _device_name(device_id, devices) or raw.get("id", "")
    motion_obj = raw.get("motion") or {}
    sensitivity_obj = raw.get("sensitivity") or {}

    return MotionSensor(
        id=raw.get("id", ""),
        name=name,
        is_reachable=(raw.get("enabled", True)),
        motion_detected=bool(motion_obj.get("motion", False)),
        motion_valid=bool(motion_obj.get("motion_valid", False)),
        sensitivity=sensitivity_obj.get("sensitivity"),
        device_id=device_id,
    )


def parse_temperature(raw: dict, devices: list[dict]) -> TemperatureSensor:
    """Parse a ``temperature`` resource dict.

    Args:
        raw: Single item from the bridge ``data`` array.
        devices: Raw device dicts used to resolve the sensor name.

    Returns:
        A :class:`~huehub.models.TemperatureSensor` dataclass.
    """
    owner = raw.get("owner") or {}
    device_id = owner.get("rid", "")
    name = _device_name(device_id, devices) or raw.get("id", "")
    temp_obj = raw.get("temperature") or {}

    return TemperatureSensor(
        id=raw.get("id", ""),
        name=name,
        is_reachable=bool(raw.get("enabled", True)),
        temperature_celsius=temp_obj.get("temperature"),
        temperature_valid=bool(temp_obj.get("temperature_valid", False)),
        device_id=device_id,
    )


def parse_light_level(raw: dict, devices: list[dict]) -> LightLevelSensor:
    """Parse a ``light_level`` resource dict.

    Args:
        raw: Single item from the bridge ``data`` array.
        devices: Raw device dicts used to resolve the sensor name.

    Returns:
        A :class:`~huehub.models.LightLevelSensor` dataclass.
    """
    owner = raw.get("owner") or {}
    device_id = owner.get("rid", "")
    name = _device_name(device_id, devices) or raw.get("id", "")
    ll_obj = raw.get("light") or {}

    return LightLevelSensor(
        id=raw.get("id", ""),
        name=name,
        is_reachable=bool(raw.get("enabled", True)),
        light_level_lux=ll_obj.get("light_level"),
        light_level_valid=bool(ll_obj.get("light_level_valid", False)),
        device_id=device_id,
    )


def parse_contact(raw: dict, devices: list[dict]) -> ContactSensor:
    """Parse a ``contact`` resource dict.

    Args:
        raw: Single item from the bridge ``data`` array.
        devices: Raw device dicts used to resolve the sensor name.

    Returns:
        A :class:`~huehub.models.ContactSensor` dataclass.
    """
    owner = raw.get("owner") or {}
    device_id = owner.get("rid", "")
    name = _device_name(device_id, devices) or raw.get("id", "")
    contact_obj = raw.get("contact_report") or {}

    raw_contact = contact_obj.get("state")
    contact: bool | None = None
    if raw_contact == "no_contact":
        contact = False
    elif raw_contact == "contact":
        contact = True

    return ContactSensor(
        id=raw.get("id", ""),
        name=name,
        is_reachable=bool(raw.get("enabled", True)),
        contact=contact,
        device_id=device_id,
    )


# ---------------------------------------------------------------------------
# Entertainment
# ---------------------------------------------------------------------------


def parse_entertainment(raw: dict) -> EntertainmentZone:
    """Parse an ``entertainment`` resource dict.

    Args:
        raw: Single item from the bridge ``data`` array.

    Returns:
        A :class:`~huehub.models.EntertainmentZone` dataclass.
    """
    meta = raw.get("metadata") or {}
    channels = raw.get("channels") or []
    config = raw.get("configuration") or {}

    light_ids = [
        member.get("rid", "")
        for ch in channels
        for member in (ch.get("members") or [])
        if member.get("rtype") == "light"
    ]

    return EntertainmentZone(
        id=raw.get("id", ""),
        name=meta.get("name", raw.get("name", "")),
        configuration_id=config.get("rid", raw.get("id", "")),
        light_ids=tuple(dict.fromkeys(light_ids)),
        status=raw.get("status"),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _device_name(device_id: str, devices: list[dict]) -> str:
    """Look up a device name by its UUID.

    Args:
        device_id: UUID of the device.
        devices: Raw device dicts from the bridge.

    Returns:
        The device name, or an empty string if not found.
    """
    for dev in devices:
        if dev.get("id") == device_id:
            meta = dev.get("metadata") or {}
            return meta.get("name", "")
    return ""


def build_lights_by_device(raw_lights: list[dict]) -> dict[str, str]:
    """Build a ``{device_id: light_id}`` mapping for fast room construction.

    Args:
        raw_lights: Raw ``light`` resource dicts from the bridge.

    Returns:
        Mapping from device UUID to light UUID.
    """
    result: dict[str, str] = {}
    for raw in raw_lights:
        owner = raw.get("owner") or {}
        device_id = owner.get("rid", "")
        if device_id:
            result[device_id] = raw.get("id", "")
    return result
