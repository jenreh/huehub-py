"""High-level client for the Philips Hue Bridge CLIP API v2.

Usage example::

    import asyncio
    from huehub import HueBridgeClient


    async def main():
        async with HueBridgeClient("192.168.1.1") as hue:
            lights = await hue.list_lights()
            await hue.turn_on("Desk lamp", brightness=80, color="3000K")


    asyncio.run(main())
"""

import asyncio
import logging
import re
import time
from collections.abc import AsyncIterator

import httpx

from huehub._parsers import (
    build_lights_by_device,
    parse_contact,
    parse_device,
    parse_entertainment,
    parse_grouped_light,
    parse_light,
    parse_light_level,
    parse_motion,
    parse_room,
    parse_scene,
    parse_temperature,
    parse_zone,
)
from huehub.cache import ResourceCache
from huehub.color import parse_color_input
from huehub.config import HueConfig, load_config
from huehub.exceptions import (
    AmbiguousNameError,
    AuthError,
    BridgeUnavailableError,
    LinkButtonNotPressedError,
    ResourceNotFoundError,
)
from huehub.models import (
    AllResources,
    BridgeInfo,
    ContactSensor,
    Device,
    EntertainmentZone,
    HueEvent,
    Light,
    LightLevelSensor,
    MotionSensor,
    Room,
    Scene,
    TemperatureSensor,
    Zone,
)
from huehub.protocol.rest import HueRestClient
from huehub.tls import TlsMode, make_httpx_client

log = logging.getLogger(__name__)

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _looks_like_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value))


class HueBridgeClient:
    """High-level client for the Philips Hue Bridge.

    Can be used as an async context manager::

        async with HueBridgeClient(config) as client:
            lights = await client.list_lights()

    Args:
        config_or_host: Either a :class:`~huehub.config.HueConfig` instance
            or a bridge IP address string.
        application_key: Application key (only used when ``config_or_host``
            is a plain host string).
    """

    def __init__(
        self,
        config_or_host: HueConfig | str,
        application_key: str | None = None,
    ) -> None:
        if isinstance(config_or_host, str):
            cfg = load_config(host=config_or_host, application_key=application_key)
        else:
            cfg = config_or_host
        self._config = cfg
        self._http_client: httpx.AsyncClient | None = None
        self._rest: HueRestClient | None = None
        self._cache: ResourceCache | None = None
        self._all_resources: AllResources | None = None
        self._resources_loaded_at: float = 0.0

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "HueBridgeClient":
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Establish connection to the bridge.

        Raises:
            BridgeUnavailableError: If no host is configured.
        """
        host = self._config.bridge.host
        if not host:
            raise BridgeUnavailableError(
                "No bridge host configured. Set bridge.host in config.toml "
                "or export HUE_BRIDGE_HOST."
            )
        bridge_id = self._config.bridge.bridge_id or "default"
        tls_mode = TlsMode(self._config.tls.mode)
        timeout = self._config.connection.request_timeout_s

        self._http_client = make_httpx_client(host, bridge_id, tls_mode, timeout)
        app_key = self._config.bridge.application_key or ""
        self._rest = HueRestClient(host, app_key, self._http_client)
        self._cache = ResourceCache(bridge_id, self._config.cache.ttl_seconds)
        log.info("Connected to bridge at %s", host)

    async def close(self) -> None:
        """Close the underlying HTTP connection."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        log.debug("Connection to bridge closed")

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def authenticate(self, device_type: str = "huehub#client") -> str:
        """Register a new application key with the bridge.

        The user must press the link button on the bridge before or during
        this call.  Polls for up to 30 seconds.

        Args:
            device_type: Device type string registered with the bridge.

        Returns:
            The new application key string.

        Raises:
            BridgeUnavailableError: If the bridge cannot be reached.
            LinkButtonNotPressedError: If the link button was not pressed
                within 30 seconds.
        """
        if not self._rest:
            await self.connect()
        body = {"devicetype": device_type, "generateclientkey": True}
        deadline = time.monotonic() + 30.0

        while time.monotonic() < deadline:
            result = await self._rest.post_auth(body)  # type: ignore[union-attr]
            if "success" in result:
                app_key: str = result["success"]["username"]
                self._config.bridge.application_key = app_key
                self._rest._application_key = app_key  # noqa: SLF001
                log.info("Application key registered successfully")
                return app_key
            if "error" in result:
                err = result["error"]
                if err.get("type") == 101:
                    log.debug("Link button not pressed, retrying in 2s")
                    await asyncio.sleep(2)
                    continue
                raise AuthError(err.get("description", "Authentication error"))

        raise LinkButtonNotPressedError("Link button not pressed within 30 seconds")

    # ------------------------------------------------------------------
    # Bridge info
    # ------------------------------------------------------------------

    async def get_bridge_info(self) -> BridgeInfo:
        """Fetch basic bridge information.

        Returns:
            A :class:`~huehub.models.BridgeInfo` instance.
        """
        data = await self._rest_get("/resource/bridge")
        if not data:
            return BridgeInfo(
                host=self._config.bridge.host or "",
                bridge_id=self._config.bridge.bridge_id or "",
            )
        raw = data[0]
        return BridgeInfo(
            host=self._config.bridge.host or "",
            bridge_id=raw.get("bridge_id", ""),
            model_id=raw.get("type"),
            api_version=None,
            software_version=(raw.get("software_update") or {}).get("version"),
            name=(raw.get("metadata") or {}).get("name"),
        )

    # ------------------------------------------------------------------
    # All resources
    # ------------------------------------------------------------------

    async def get_all_resources(self, refresh: bool = False) -> AllResources:
        """Fetch and cache all bridge resources.

        Args:
            refresh: If ``True``, bypass the in-memory and on-disk caches.

        Returns:
            An :class:`~huehub.models.AllResources` snapshot.
        """
        ttl = self._config.cache.ttl_seconds
        if (
            not refresh
            and self._all_resources
            and time.monotonic() - self._resources_loaded_at < ttl
        ):
            return self._all_resources

        # Try on-disk cache
        if not refresh and self._cache:
            cached = self._cache.load()
            if cached is not None:
                self._all_resources = _parse_all_resources(cached)
                self._resources_loaded_at = time.monotonic()
                return self._all_resources

        raw = await self._rest_get("/resource")
        if self._cache:
            self._cache.save(raw)
        self._all_resources = _parse_all_resources(raw)
        self._resources_loaded_at = time.monotonic()
        return self._all_resources

    # ------------------------------------------------------------------
    # Lights
    # ------------------------------------------------------------------

    async def list_lights(self) -> list[Light]:
        """List all lights.

        Returns:
            List of :class:`~huehub.models.Light` instances.
        """
        return list((await self.get_all_resources()).lights)

    async def get_light(self, light: str) -> Light:
        """Get a single light by name or UUID.

        Args:
            light: Light name or UUID.

        Returns:
            The matching :class:`~huehub.models.Light`.

        Raises:
            ResourceNotFoundError: If no light matches.
            AmbiguousNameError: If multiple lights share the name.
        """
        light_id = await self._resolve_name("light", light)
        resources = await self.get_all_resources()
        for lig in resources.lights:
            if lig.id == light_id:
                return lig
        raise ResourceNotFoundError("light", light)

    async def set_light(
        self,
        light: str,
        *,
        on: bool | None = None,
        brightness: float | None = None,
        color: str | None = None,
        transition_ms: int | None = None,
        effect: str | None = None,
        alert: str | None = None,
    ) -> dict:
        """Control a single light.

        Args:
            light: Light name or UUID.
            on: Turn the light on (``True``) or off (``False``).
            brightness: Target brightness 0.0–100.0.
            color: Colour spec (RGB, HEX, Kelvin, named preset).
            transition_ms: Transition time in milliseconds.
            effect: Effect name (``"candle"``, ``"fire"``, etc.).
            alert: Alert action (``"breathe"``).

        Returns:
            Raw bridge response dict.

        Raises:
            ResourceNotFoundError: If no light matches.
            AmbiguousNameError: If multiple lights share the name.
        """
        light_id = await self._resolve_name("light", light)
        body = _build_light_body(
            on=on,
            brightness=brightness,
            color=color,
            transition_ms=transition_ms,
            effect=effect,
            alert=alert,
            user_presets=self._config.colors,
        )
        result = await self._rest_put(f"/resource/light/{light_id}", body)
        self._invalidate_cache()
        return result[0] if result else {}

    async def turn_on(self, light: str, **kwargs: object) -> dict:
        """Turn on a light, optionally setting brightness/colour.

        Args:
            light: Light name or UUID.
            **kwargs: Additional kwargs forwarded to :meth:`set_light`.

        Returns:
            Raw bridge response dict.
        """
        return await self.set_light(light, on=True, **kwargs)  # type: ignore[arg-type]

    async def turn_off(self, light: str, **kwargs: object) -> dict:
        """Turn off a light.

        Args:
            light: Light name or UUID.
            **kwargs: Additional kwargs forwarded to :meth:`set_light`.

        Returns:
            Raw bridge response dict.
        """
        return await self.set_light(light, on=False, **kwargs)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Rooms
    # ------------------------------------------------------------------

    async def list_rooms(self) -> list[Room]:
        """List all rooms.

        Returns:
            List of :class:`~huehub.models.Room` instances.
        """
        return list((await self.get_all_resources()).rooms)

    async def get_room(self, room: str) -> Room:
        """Get a single room by name or UUID.

        Args:
            room: Room name or UUID.

        Returns:
            The matching :class:`~huehub.models.Room`.

        Raises:
            ResourceNotFoundError: If no room matches.
        """
        room_id = await self._resolve_name("room", room)
        for r in (await self.get_all_resources()).rooms:
            if r.id == room_id:
                return r
        raise ResourceNotFoundError("room", room)

    async def set_room(self, room: str, **kwargs: object) -> dict:
        """Control a room's grouped_light.

        Args:
            room: Room name or UUID.
            **kwargs: Same keyword arguments as :meth:`set_light`.

        Returns:
            Raw bridge response dict.
        """
        room_obj = await self.get_room(room)
        return await self._set_grouped_light(room_obj.grouped_light_id, **kwargs)

    # ------------------------------------------------------------------
    # Zones
    # ------------------------------------------------------------------

    async def list_zones(self) -> list[Zone]:
        """List all zones.

        Returns:
            List of :class:`~huehub.models.Zone` instances.
        """
        return list((await self.get_all_resources()).zones)

    async def get_zone(self, zone: str) -> Zone:
        """Get a single zone by name or UUID.

        Args:
            zone: Zone name or UUID.

        Returns:
            The matching :class:`~huehub.models.Zone`.
        """
        zone_id = await self._resolve_name("zone", zone)
        for z in (await self.get_all_resources()).zones:
            if z.id == zone_id:
                return z
        raise ResourceNotFoundError("zone", zone)

    async def set_zone(self, zone: str, **kwargs: object) -> dict:
        """Control a zone's grouped_light.

        Args:
            zone: Zone name or UUID.
            **kwargs: Same keyword arguments as :meth:`set_light`.

        Returns:
            Raw bridge response dict.
        """
        zone_obj = await self.get_zone(zone)
        return await self._set_grouped_light(zone_obj.grouped_light_id, **kwargs)

    # ------------------------------------------------------------------
    # Scenes
    # ------------------------------------------------------------------

    async def list_scenes(self, group: str | None = None) -> list[Scene]:
        """List scenes, optionally filtered by room or zone.

        Args:
            group: Room or zone name/UUID to filter by.

        Returns:
            List of :class:`~huehub.models.Scene` instances.
        """
        scenes = list((await self.get_all_resources()).scenes)
        if not group:
            return scenes

        group_id: str | None = None
        try:
            group_id = await self._resolve_name("room", group)
        except ResourceNotFoundError:
            pass
        if not group_id:
            try:
                group_id = await self._resolve_name("zone", group)
            except ResourceNotFoundError:
                pass
        if not group_id:
            group_id = group  # treat as UUID directly

        return [s for s in scenes if s.group_id == group_id]

    async def activate_scene(self, scene: str, group: str | None = None) -> None:
        """Activate a scene by name or UUID.

        Args:
            scene: Scene name or UUID.
            group: Optional room/zone name for disambiguation.

        Raises:
            ResourceNotFoundError: If no scene matches.
            AmbiguousNameError: If multiple scenes share the name.
        """
        candidates = await self.list_scenes(group=group)
        scene_id = _resolve_from_list(
            "scene", scene, [(s.id, s.name) for s in candidates]
        )
        await self._rest_put(
            f"/resource/scene/{scene_id}",
            {"recall": {"action": "active"}},
        )

    # ------------------------------------------------------------------
    # Devices
    # ------------------------------------------------------------------

    async def list_devices(self) -> list[Device]:
        """List all devices.

        Returns:
            List of :class:`~huehub.models.Device` instances.
        """
        return list((await self.get_all_resources()).devices)

    async def get_device(self, device: str) -> Device:
        """Get a single device by name or UUID.

        Args:
            device: Device name or UUID.

        Returns:
            The matching :class:`~huehub.models.Device`.
        """
        device_id = await self._resolve_name("device", device)
        for d in (await self.get_all_resources()).devices:
            if d.id == device_id:
                return d
        raise ResourceNotFoundError("device", device)

    # ------------------------------------------------------------------
    # Sensors
    # ------------------------------------------------------------------

    async def list_motion_sensors(self) -> list[MotionSensor]:
        """List all motion sensors."""
        return list((await self.get_all_resources()).motion_sensors)

    async def list_temperature_sensors(self) -> list[TemperatureSensor]:
        """List all temperature sensors."""
        return list((await self.get_all_resources()).temperature_sensors)

    async def list_light_level_sensors(self) -> list[LightLevelSensor]:
        """List all light level sensors."""
        return list((await self.get_all_resources()).light_level_sensors)

    async def list_contact_sensors(self) -> list[ContactSensor]:
        """List all contact (door/window) sensors."""
        return list((await self.get_all_resources()).contact_sensors)

    # ------------------------------------------------------------------
    # Entertainment
    # ------------------------------------------------------------------

    async def list_entertainment_zones(self) -> list[EntertainmentZone]:
        """List all entertainment zones."""
        return list((await self.get_all_resources()).entertainment_zones)

    # ------------------------------------------------------------------
    # Global controls
    # ------------------------------------------------------------------

    async def all_off(self) -> None:
        """Turn off all lights on the bridge.

        Operates on the bridge_home grouped_light for a single API call.
        Falls back to turning off each room individually.
        """
        resources = await self.get_all_resources()
        # Find the bridge_home grouped_light
        for gl in resources.grouped_lights:
            if gl.owner_type == "bridge_home":
                await self._rest_put(
                    f"/resource/grouped_light/{gl.id}",
                    {"on": {"on": False}},
                )
                self._invalidate_cache()
                return

        # Fallback: turn off each room
        for room in resources.rooms:
            if room.grouped_light_id:
                await self._rest_put(
                    f"/resource/grouped_light/{room.grouped_light_id}",
                    {"on": {"on": False}},
                )
        self._invalidate_cache()

    # ------------------------------------------------------------------
    # SSE event stream
    # ------------------------------------------------------------------

    async def listen(self) -> AsyncIterator[HueEvent]:
        """Yield real-time bridge events from the SSE stream.

        Reconnects automatically on connection loss.

        Yields:
            :class:`~huehub.models.HueEvent` objects.
        """
        from huehub.protocol.sse import stream

        host = self._config.bridge.host or ""
        app_key = self._config.bridge.application_key or ""
        async for event in stream(
            host,
            app_key,
            self._http_client,  # type: ignore[arg-type]
            reconnect_delay_s=self._config.connection.sse_reconnect_delay_s,
            reconnect_max_s=self._config.connection.sse_reconnect_max_s,
        ):
            yield event

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _rest_get(self, path: str) -> list[dict]:
        if not self._rest:
            raise BridgeUnavailableError("Not connected. Call connect() first.")
        return await self._rest.get(path)

    async def _rest_put(self, path: str, body: dict) -> list[dict]:
        if not self._rest:
            raise BridgeUnavailableError("Not connected. Call connect() first.")
        return await self._rest.put(path, body)

    async def _set_grouped_light(self, grouped_light_id: str, **kwargs: object) -> dict:
        body = _build_light_body(**kwargs, user_presets=self._config.colors)  # type: ignore[arg-type]
        result = await self._rest_put(
            f"/resource/grouped_light/{grouped_light_id}", body
        )
        self._invalidate_cache()
        return result[0] if result else {}

    async def _resolve_name(self, resource_type: str, name_or_id: str) -> str:
        """Resolve a resource name or UUID to a UUID.

        Args:
            resource_type: Type of resource (``"light"``, ``"room"``, etc.).
            name_or_id: Resource name (case-insensitive) or UUID.

        Returns:
            The resource UUID string.

        Raises:
            ResourceNotFoundError: If no resource matches.
            AmbiguousNameError: If multiple resources share the name.
        """
        if _looks_like_uuid(name_or_id):
            return name_or_id

        resources = await self.get_all_resources()
        pairs = _resource_pairs(resource_type, resources)
        return _resolve_from_list(resource_type, name_or_id, pairs)

    def _invalidate_cache(self) -> None:
        self._all_resources = None
        if self._cache:
            self._cache.invalidate()


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _resource_pairs(
    resource_type: str, resources: AllResources
) -> list[tuple[str, str]]:
    """Return ``[(id, name)]`` pairs for a given resource type.

    Args:
        resource_type: Type string (``"light"``, ``"room"``, etc.).
        resources: Full resources snapshot.

    Returns:
        List of ``(id, name)`` tuples.
    """
    mapping: dict[str, list] = {
        "light": list(resources.lights),
        "room": list(resources.rooms),
        "zone": list(resources.zones),
        "scene": list(resources.scenes),
        "device": list(resources.devices),
        "grouped_light": list(resources.grouped_lights),
    }
    items = mapping.get(resource_type, [])
    return [(item.id, item.name) for item in items]


def _resolve_from_list(
    resource_type: str,
    name_or_id: str,
    pairs: list[tuple[str, str]],
) -> str:
    """Find a UUID from a list of ``(id, name)`` pairs.

    Matching is case-insensitive exact name match first, then falls back to
    a case-insensitive substring (startswith) match.

    Args:
        resource_type: Type name used in error messages.
        name_or_id: Name to search for.
        pairs: ``[(id, name)]`` pairs from the resource snapshot.

    Returns:
        The matching UUID.

    Raises:
        ResourceNotFoundError: If no match is found.
        AmbiguousNameError: If multiple resources match.
    """
    needle = name_or_id.lower()

    # Exact match (case-insensitive)
    exact = [(rid, name) for rid, name in pairs if name.lower() == needle]
    if len(exact) == 1:
        return exact[0][0]
    if len(exact) > 1:
        raise AmbiguousNameError(
            resource_type,
            name_or_id,
            [f"{name} ({rid})" for rid, name in exact],
        )

    # Prefix match
    prefix = [(rid, name) for rid, name in pairs if name.lower().startswith(needle)]
    if len(prefix) == 1:
        return prefix[0][0]
    if len(prefix) > 1:
        raise AmbiguousNameError(
            resource_type,
            name_or_id,
            [f"{name} ({rid})" for rid, name in prefix],
        )

    raise ResourceNotFoundError(resource_type, name_or_id)


def _build_light_body(
    *,
    on: bool | None = None,
    brightness: float | None = None,
    color: str | None = None,
    transition_ms: int | None = None,
    effect: str | None = None,
    alert: str | None = None,
    user_presets: dict[str, str] | None = None,
) -> dict:
    """Build the JSON body for a light or grouped_light PUT request.

    Args:
        on: Turn on/off.
        brightness: Brightness 0.0–100.0.
        color: Colour spec string.
        transition_ms: Transition duration in ms.
        effect: Effect name.
        alert: Alert action.
        user_presets: Custom colour name presets from config.

    Returns:
        Dict suitable for the bridge PUT payload.
    """
    body: dict = {}

    if on is not None:
        body["on"] = {"on": on}

    if brightness is not None:
        body["dimming"] = {"brightness": float(brightness)}

    if color is not None:
        result = parse_color_input(color, user_presets=user_presets)
        if result.mirek is not None and result.xy == (0.0, 0.0):
            body["color_temperature"] = {"mirek": result.mirek}
        elif result.xy != (0.0, 0.0):
            body["color"] = {"xy": {"x": result.xy[0], "y": result.xy[1]}}
            if result.mirek is not None:
                body["color_temperature"] = {"mirek": result.mirek}

    if transition_ms is not None:
        body.setdefault("dynamics", {})["duration"] = transition_ms

    if effect is not None:
        body["effects"] = {"effect": effect}

    if alert is not None:
        body["alert"] = {"action": alert}

    return body


def _parse_all_resources(raw_list: list[dict]) -> AllResources:
    """Parse a flat list of bridge resource dicts into an AllResources snapshot.

    Args:
        raw_list: Items from ``GET /clip/v2/resource`` response.

    Returns:
        A fully populated :class:`~huehub.models.AllResources`.
    """
    by_type: dict[str, list[dict]] = {}
    for item in raw_list:
        rtype = item.get("type", "")
        by_type.setdefault(rtype, []).append(item)

    raw_lights = by_type.get("light", [])
    raw_rooms = by_type.get("room", [])
    raw_zones = by_type.get("zone", [])
    raw_grouped = by_type.get("grouped_light", [])
    raw_scenes = by_type.get("scene", [])
    raw_devices = by_type.get("device", [])
    raw_motion = by_type.get("motion", [])
    raw_temp = by_type.get("temperature", [])
    raw_ll = by_type.get("light_level", [])
    raw_contact = by_type.get("contact", [])
    raw_entertainment = by_type.get("entertainment", [])

    lights = tuple(parse_light(r) for r in raw_lights)
    lights_by_device = build_lights_by_device(raw_lights)
    lights_by_id = {lid: lid for lid in lights_by_device.values()}

    rooms = tuple(parse_room(r, lights_by_device) for r in raw_rooms)
    zones = tuple(parse_zone(r, lights_by_id) for r in raw_zones)
    grouped_lights = tuple(
        parse_grouped_light(r, raw_rooms, raw_zones) for r in raw_grouped
    )

    return AllResources(
        lights=lights,
        rooms=rooms,
        zones=zones,
        scenes=tuple(parse_scene(r) for r in raw_scenes),
        devices=tuple(parse_device(r) for r in raw_devices),
        grouped_lights=grouped_lights,
        motion_sensors=tuple(parse_motion(r, raw_devices) for r in raw_motion),
        temperature_sensors=tuple(parse_temperature(r, raw_devices) for r in raw_temp),
        light_level_sensors=tuple(parse_light_level(r, raw_devices) for r in raw_ll),
        contact_sensors=tuple(parse_contact(r, raw_devices) for r in raw_contact),
        entertainment_zones=tuple(parse_entertainment(r) for r in raw_entertainment),
    )
