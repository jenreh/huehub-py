"""MCP server for the Philips Hue Bridge.

Exposes all bridge controls as MCP tools and resources using ``fastmcp``.
Run as a stdio server (default) for use with Claude Desktop.

Configuration is read from the standard huehub config file / env vars.
The application key is never returned in tool responses.
"""

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastmcp import FastMCP

from huehub.client import HueBridgeClient
from huehub.config import load_config

# All logging goes to stderr – never to stdout (MCP protocol stream)
logging.basicConfig(
    level=logging.WARNING,
    stream=sys.stderr,
    format="%(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Server setup with lifespan
# ---------------------------------------------------------------------------

_client: HueBridgeClient | None = None


@asynccontextmanager
async def _lifespan(server: FastMCP) -> AsyncIterator[None]:
    global _client
    cfg = load_config()
    _client = HueBridgeClient(cfg)
    try:
        await _client.connect()
        log.info("MCP server connected to bridge at %s", cfg.bridge.host)
        yield
    finally:
        if _client:
            await _client.close()
        _client = None


mcp = FastMCP("hue", lifespan=_lifespan)


def _get_client() -> HueBridgeClient:
    if _client is None:
        raise RuntimeError("Bridge client not initialised")
    return _client


# ---------------------------------------------------------------------------
# Tools – Bridge
# ---------------------------------------------------------------------------


@mcp.tool()
async def hue_get_bridge_info() -> dict[str, Any]:
    """Get basic information about the Hue Bridge."""
    info = await _get_client().get_bridge_info()
    return {
        "host": info.host,
        "bridge_id": info.bridge_id,
        "name": info.name,
        "model_id": info.model_id,
        "api_version": info.api_version,
        "software_version": info.software_version,
    }


# ---------------------------------------------------------------------------
# Tools – Lights
# ---------------------------------------------------------------------------


@mcp.tool()
async def hue_list_lights(room: str | None = None) -> list[dict[str, Any]]:
    """List all lights, optionally filtered by room name or UUID.

    Args:
        room: Room name or UUID to filter by (optional).
    """
    client = _get_client()
    if room:
        lights = await client.list_lights()
        rooms = await client.list_rooms()
        for r in rooms:
            if r.name.lower() == room.lower() or r.id == room:
                lights = [lig for lig in lights if lig.id in r.light_ids]
                break
    else:
        lights = await client.list_lights()

    return [
        {
            "id": lig.id,
            "name": lig.name,
            "on": lig.is_on,
            "brightness": lig.brightness,
            "color_xy": lig.color_xy,
            "color_temp_mirek": lig.color_temp_mirek,
            "color_mode": lig.color_mode,
            "reachable": lig.is_reachable,
            "effects_available": list(lig.effects_available),
            "archetype": lig.archetype,
        }
        for lig in lights
    ]


@mcp.tool()
async def hue_get_light(light: str) -> dict[str, Any]:
    """Get the full current state of a single light.

    Args:
        light: Light name or UUID.
    """
    lig = await _get_client().get_light(light)
    return {
        "id": lig.id,
        "name": lig.name,
        "on": lig.is_on,
        "brightness": lig.brightness,
        "color_xy": lig.color_xy,
        "color_temp_mirek": lig.color_temp_mirek,
        "color_mode": lig.color_mode,
        "reachable": lig.is_reachable,
        "effects_available": list(lig.effects_available),
        "archetype": lig.archetype,
    }


@mcp.tool()
async def hue_set_light(
    light: str,
    on: bool | None = None,
    brightness: float | None = None,
    color: str | None = None,
    transition_ms: int | None = None,
    effect: str | None = None,
) -> dict[str, Any]:
    """Control a single light.

    Args:
        light: Light name or UUID.
        on: Turn on (True) or off (False).
        brightness: Brightness 0.0–100.0.
        color: Colour spec: "#FF8000", "3000K", "warm", "255,128,0", etc.
        transition_ms: Transition time in milliseconds.
        effect: Effect name: "candle", "fire", "prism", "sparkle", etc.
    """
    result = await _get_client().set_light(
        light,
        on=on,
        brightness=brightness,
        color=color,
        transition_ms=transition_ms,
        effect=effect,
    )
    return {"status": "ok", "result": result}


@mcp.tool()
async def hue_set_light_color_temp(
    light: str,
    color_temp: str | int,
    brightness: float | None = None,
    transition_ms: int | None = None,
) -> dict[str, Any]:
    """Set a light's colour temperature.

    Args:
        light: Light name or UUID.
        color_temp: Temperature as "3000K", "4000K", or a mirek integer.
        brightness: Optional brightness 0.0–100.0.
        transition_ms: Optional transition time in milliseconds.
    """
    color_str = str(color_temp)
    if isinstance(color_temp, int) or (
        not color_str.upper().endswith("K") and not color_str.lower().endswith("mirek")
    ):
        color_str = f"{color_temp}mirek"

    result = await _get_client().set_light(
        light, color=color_str, brightness=brightness, transition_ms=transition_ms
    )
    return {"status": "ok", "result": result}


# ---------------------------------------------------------------------------
# Tools – Rooms
# ---------------------------------------------------------------------------


@mcp.tool()
async def hue_list_rooms() -> list[dict[str, Any]]:
    """List all rooms."""
    rooms = await _get_client().list_rooms()
    return [
        {
            "id": r.id,
            "name": r.name,
            "grouped_light_id": r.grouped_light_id,
            "light_ids": list(r.light_ids),
            "device_ids": list(r.device_ids),
        }
        for r in rooms
    ]


@mcp.tool()
async def hue_set_room_on(room: str, on: bool) -> dict[str, Any]:
    """Turn a room's lights on or off.

    Args:
        room: Room name or UUID.
        on: True to turn on, False to turn off.
    """
    await _get_client().set_room(room, on=on)
    return {"status": "ok", "room": room, "on": on}


@mcp.tool()
async def hue_set_room(
    room: str,
    on: bool | None = None,
    brightness: float | None = None,
    color: str | None = None,
    transition_ms: int | None = None,
) -> dict[str, Any]:
    """Control a room's lights.

    Args:
        room: Room name or UUID.
        on: Turn on/off.
        brightness: Brightness 0.0–100.0.
        color: Colour spec string.
        transition_ms: Transition time in milliseconds.
    """
    await _get_client().set_room(
        room, on=on, brightness=brightness, color=color, transition_ms=transition_ms
    )
    return {"status": "ok", "room": room}


# ---------------------------------------------------------------------------
# Tools – Zones
# ---------------------------------------------------------------------------


@mcp.tool()
async def hue_list_zones() -> list[dict[str, Any]]:
    """List all zones."""
    zones = await _get_client().list_zones()
    return [
        {
            "id": z.id,
            "name": z.name,
            "grouped_light_id": z.grouped_light_id,
            "light_ids": list(z.light_ids),
        }
        for z in zones
    ]


@mcp.tool()
async def hue_set_zone(
    zone: str,
    on: bool | None = None,
    brightness: float | None = None,
    color: str | None = None,
    transition_ms: int | None = None,
) -> dict[str, Any]:
    """Control a zone's lights.

    Args:
        zone: Zone name or UUID.
        on: Turn on/off.
        brightness: Brightness 0.0–100.0.
        color: Colour spec string.
        transition_ms: Transition time in milliseconds.
    """
    await _get_client().set_zone(
        zone, on=on, brightness=brightness, color=color, transition_ms=transition_ms
    )
    return {"status": "ok", "zone": zone}


# ---------------------------------------------------------------------------
# Tools – Scenes
# ---------------------------------------------------------------------------


@mcp.tool()
async def hue_list_scenes(room: str | None = None) -> list[dict[str, Any]]:
    """List scenes, optionally filtered by room.

    Args:
        room: Room name or UUID to filter scenes by.
    """
    scenes = await _get_client().list_scenes(group=room)
    return [
        {
            "id": s.id,
            "name": s.name,
            "group_id": s.group_id,
            "group_type": s.group_type,
            "is_active": s.is_active,
        }
        for s in scenes
    ]


@mcp.tool()
async def hue_activate_scene(scene: str, room: str | None = None) -> dict[str, Any]:
    """Activate a scene.

    Args:
        scene: Scene name or UUID.
        room: Optional room name/UUID to disambiguate same-named scenes.
    """
    await _get_client().activate_scene(scene, group=room)
    return {"status": "ok", "scene": scene}


# ---------------------------------------------------------------------------
# Tools – Devices
# ---------------------------------------------------------------------------


@mcp.tool()
async def hue_list_devices() -> list[dict[str, Any]]:
    """List all physical devices on the bridge."""
    devices = await _get_client().list_devices()
    return [
        {
            "id": d.id,
            "name": d.name,
            "model_id": d.model_id,
            "manufacturer": d.manufacturer,
            "product_name": d.product_name,
            "archetype": d.archetype,
        }
        for d in devices
    ]


# ---------------------------------------------------------------------------
# Tools – Sensors
# ---------------------------------------------------------------------------


@mcp.tool()
async def hue_list_motion_sensors() -> list[dict[str, Any]]:
    """List motion sensors with their current readings."""
    sensors = await _get_client().list_motion_sensors()
    return [
        {
            "id": s.id,
            "name": s.name,
            "motion_detected": s.motion_detected,
            "motion_valid": s.motion_valid,
            "reachable": s.is_reachable,
        }
        for s in sensors
    ]


@mcp.tool()
async def hue_list_temperature_sensors() -> list[dict[str, Any]]:
    """List temperature sensors with current measurements."""
    sensors = await _get_client().list_temperature_sensors()
    return [
        {
            "id": s.id,
            "name": s.name,
            "temperature_celsius": s.temperature_celsius,
            "valid": s.temperature_valid,
            "reachable": s.is_reachable,
        }
        for s in sensors
    ]


@mcp.tool()
async def hue_list_light_level_sensors() -> list[dict[str, Any]]:
    """List light level sensors with current lux values."""
    sensors = await _get_client().list_light_level_sensors()
    return [
        {
            "id": s.id,
            "name": s.name,
            "light_level_lux": s.light_level_lux,
            "valid": s.light_level_valid,
            "reachable": s.is_reachable,
        }
        for s in sensors
    ]


@mcp.tool()
async def hue_list_contact_sensors() -> list[dict[str, Any]]:
    """List contact (door/window) sensors with their current state."""
    sensors = await _get_client().list_contact_sensors()
    return [
        {
            "id": s.id,
            "name": s.name,
            "contact": s.contact,
            "state": "closed"
            if s.contact
            else "open"
            if s.contact is False
            else "unknown",
            "reachable": s.is_reachable,
        }
        for s in sensors
    ]


# ---------------------------------------------------------------------------
# Tools – Global
# ---------------------------------------------------------------------------


@mcp.tool()
async def hue_all_off() -> dict[str, Any]:
    """Turn off all lights on the bridge immediately."""
    await _get_client().all_off()
    return {"status": "ok", "message": "All lights turned off"}


@mcp.tool()
async def hue_refresh_resources() -> dict[str, Any]:
    """Force a fresh fetch of all resources from the bridge, bypassing cache."""
    resources = await _get_client().get_all_resources(refresh=True)
    return {
        "status": "ok",
        "counts": {
            "lights": len(resources.lights),
            "rooms": len(resources.rooms),
            "zones": len(resources.zones),
            "scenes": len(resources.scenes),
            "devices": len(resources.devices),
        },
    }


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


@mcp.resource("hue://bridge")
async def resource_bridge() -> str:
    """Bridge information."""
    info = await _get_client().get_bridge_info()
    import json

    return json.dumps(
        {
            "host": info.host,
            "bridge_id": info.bridge_id,
            "name": info.name,
        }
    )


@mcp.resource("hue://lights")
async def resource_lights() -> str:
    """All lights with current status."""
    lights = await _get_client().list_lights()
    import json

    return json.dumps(
        [
            {
                "id": lig.id,
                "name": lig.name,
                "on": lig.is_on,
                "brightness": lig.brightness,
            }
            for lig in lights
        ]
    )


@mcp.resource("hue://rooms")
async def resource_rooms() -> str:
    """All rooms with their lights."""
    rooms = await _get_client().list_rooms()
    import json

    return json.dumps(
        [{"id": r.id, "name": r.name, "light_ids": list(r.light_ids)} for r in rooms]
    )


@mcp.resource("hue://zones")
async def resource_zones() -> str:
    """All zones."""
    zones = await _get_client().list_zones()
    import json

    return json.dumps(
        [{"id": z.id, "name": z.name, "light_ids": list(z.light_ids)} for z in zones]
    )


@mcp.resource("hue://scenes")
async def resource_scenes() -> str:
    """All scenes."""
    scenes = await _get_client().list_scenes()
    import json

    return json.dumps(
        [
            {"id": s.id, "name": s.name, "group_id": s.group_id, "active": s.is_active}
            for s in scenes
        ]
    )


@mcp.resource("hue://devices")
async def resource_devices() -> str:
    """All physical devices."""
    devices = await _get_client().list_devices()
    import json

    return json.dumps(
        [{"id": d.id, "name": d.name, "product": d.product_name} for d in devices]
    )


@mcp.resource("hue://sensors")
async def resource_sensors() -> str:
    """All sensors with current readings."""
    client = _get_client()
    motions = await client.list_motion_sensors()
    temps = await client.list_temperature_sensors()
    lights_lvl = await client.list_light_level_sensors()
    contacts = await client.list_contact_sensors()
    import json

    data: list[dict] = (
        [
            {"type": "motion", "id": m.id, "name": m.name, "motion": m.motion_detected}
            for m in motions
        ]
        + [
            {
                "type": "temperature",
                "id": t.id,
                "name": t.name,
                "temp_c": t.temperature_celsius,
            }
            for t in temps
        ]
        + [
            {
                "type": "light_level",
                "id": ll.id,
                "name": ll.name,
                "lux": ll.light_level_lux,
            }
            for ll in lights_lvl
        ]
        + [
            {"type": "contact", "id": c.id, "name": c.name, "contact": c.contact}
            for c in contacts
        ]
    )
    return json.dumps(data)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the MCP server using stdio transport."""
    mcp.run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
