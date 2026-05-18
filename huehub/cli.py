"""Command-line interface for huehub.

Provides the ``hue`` entry point with sub-commands for discovering,
setting up, and controlling a Philips Hue Bridge.

All diagnostic output goes to stderr; stdout is reserved for data output.
Use ``--json`` for machine-readable JSON on stdout.

Exit codes:
    0  – success
    2  – usage / validation error (Typer default)
    10 – bridge not reachable
    11 – TLS error
    12 – authentication error (invalid app key)
    13 – resource not found
    14 – resource name is ambiguous
    15 – link button not pressed during setup
"""

import asyncio
import json as _json
import logging
import sys
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from huehub.config import load_config, save_config
from huehub.exceptions import (
    AmbiguousNameError,
    AuthError,
    BridgeUnavailableError,
    LinkButtonNotPressedError,
    ResourceNotFoundError,
    TlsError,
)

app = typer.Typer(
    name="hue",
    help="Control your Philips Hue Bridge from the command line.",
    no_args_is_help=True,
    add_completion=True,
)
lights_app = typer.Typer(
    help="Manage individual lights.", no_args_is_help=True, add_completion=True
)
rooms_app = typer.Typer(help="Manage rooms.", no_args_is_help=True, add_completion=True)
zones_app = typer.Typer(help="Manage zones.", no_args_is_help=True, add_completion=True)
scenes_app = typer.Typer(
    help="Manage scenes.", no_args_is_help=True, add_completion=True
)
devices_app = typer.Typer(
    help="List devices.", no_args_is_help=True, add_completion=True
)
sensors_app = typer.Typer(
    help="Read sensor values.", no_args_is_help=True, add_completion=True
)
api_app = typer.Typer(
    help="Raw API access for debugging.", no_args_is_help=True, add_completion=True
)

app.add_typer(lights_app, name="lights")
app.add_typer(rooms_app, name="rooms")
app.add_typer(zones_app, name="zones")
app.add_typer(scenes_app, name="scenes")
app.add_typer(devices_app, name="devices")
app.add_typer(sensors_app, name="sensors")
app.add_typer(api_app, name="api")

_err = Console(stderr=True)
_out = Console()

# Module-level state populated by the global callback
_host: str | None = None
_app_key: str | None = None
_json_output: bool = False

logging.basicConfig(
    level=logging.WARNING,
    stream=sys.stderr,
    format="%(levelname)s %(name)s: %(message)s",
)


# ---------------------------------------------------------------------------
# Global callback
# ---------------------------------------------------------------------------


@app.callback()
def _global(
    host: Annotated[
        str | None, typer.Option("--host", help="Bridge IP/hostname.")
    ] = None,
    key: Annotated[
        str | None,
        typer.Option("--key", help="Application key.", envvar="HUE_APPLICATION_KEY"),
    ] = None,
    json_out: Annotated[
        bool, typer.Option("--json", help="Output JSON instead of tables.")
    ] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable debug logging.")
    ] = False,
) -> None:
    """Philips Hue Bridge CLI."""
    global _host, _app_key, _json_output
    _host = host
    _app_key = key
    _json_output = json_out
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _get_client():  # type: ignore[return]
    """Build a connected HueBridgeClient from the global options."""
    from huehub.client import HueBridgeClient

    cfg = load_config(host=_host, application_key=_app_key)
    return HueBridgeClient(cfg)


def _run(coro: object) -> None:  # type: ignore[return]
    """Run an async coroutine, converting exceptions to exit codes."""
    try:
        return asyncio.run(coro)
    except BridgeUnavailableError as exc:
        _err.print(f"[red]Bridge unreachable:[/red] {exc}")
        raise typer.Exit(code=10) from exc
    except TlsError as exc:
        _err.print(f"[red]TLS error:[/red] {exc}")
        raise typer.Exit(code=11) from exc
    except AuthError as exc:
        _err.print(f"[red]Auth error:[/red] {exc}")
        raise typer.Exit(code=12) from exc
    except ResourceNotFoundError as exc:
        _err.print(f"[red]Not found:[/red] {exc}")
        raise typer.Exit(code=13) from exc
    except AmbiguousNameError as exc:
        _err.print(f"[red]Ambiguous name:[/red] {exc}")
        _err.print("[yellow]Candidates:[/yellow]")
        for c in exc.candidates:
            _err.print(f"  • {c}")
        raise typer.Exit(code=14) from exc
    except LinkButtonNotPressedError as exc:
        _err.print(f"[red]Link button:[/red] {exc}")
        raise typer.Exit(code=15) from exc


def _print_or_json(data: object, table_fn: object = None) -> None:  # type: ignore[return]
    """Print data as a Rich table or as JSON depending on --json flag."""
    if _json_output:
        _out.print_json(_json.dumps(data, default=str))
    elif table_fn:
        table_fn()


# ---------------------------------------------------------------------------
# Top-level commands
# ---------------------------------------------------------------------------


@app.command()
def discover(
    timeout: Annotated[float, typer.Option(help="mDNS timeout in seconds.")] = 5.0,
) -> None:
    """Discover Hue Bridges on the local network."""

    async def _do() -> None:
        from huehub.discovery import discover as _discover

        cfg = load_config(host=_host)
        bridges = await _discover(
            mdns_timeout_s=timeout,
            use_hostname=cfg.discovery.use_hostname_fallback,
            use_cloud=cfg.discovery.use_cloud_fallback,
        )
        if not bridges:
            _err.print("No bridges found.")
            raise typer.Exit(code=1)

        if _json_output:
            _out.print_json(_json.dumps(bridges))
            return

        table = Table(title="Discovered Bridges")
        table.add_column("Host")
        table.add_column("Bridge ID")
        for b in bridges:
            table.add_row(b.get("host", ""), b.get("bridge_id", ""))
        _out.print(table)

    _run(_do())


@app.command()
def setup(
    host: Annotated[str, typer.Option("--host", help="Bridge IP/hostname.")],
    port: Annotated[int, typer.Option(help="Bridge TLS port.")] = 443,
) -> None:
    """Extract and save the bridge TLS certificate.

    After running this command, press the link button on the bridge
    and then run ``hue authenticate``.
    """

    async def _do() -> None:
        from huehub.tls import save_cert

        cfg = load_config(host=host)
        cfg.bridge.host = host

        _err.print(f"[cyan]Extracting TLS certificate from {host}:{port}…[/cyan]")
        try:
            cert_path = save_cert(host, cfg.bridge.bridge_id or "default", port)
            _err.print(f"[green]Certificate saved to {cert_path}[/green]")
            cfg.tls.mode = "verify"
        except Exception as exc:
            _err.print(
                f"[yellow]TLS cert extraction failed ({exc}), using skip mode.[/yellow]"
            )
            cfg.tls.mode = "skip"

        save_config(cfg)
        _err.print("[cyan]Press the link button on your Hue Bridge NOW…[/cyan]")
        _err.print("[cyan]Then run: hue authenticate[/cyan]")

    _run(_do())


@app.command()
def authenticate(
    host: Annotated[str | None, typer.Option("--host")] = None,
) -> None:
    """Register a new application key (press link button first)."""

    async def _do() -> None:
        from huehub.client import HueBridgeClient

        cfg = load_config(host=host or _host)
        # Use skip TLS for initial auth: the saved cert is a leaf cert and
        # cannot serve as a CA for httpx verification (bootstrap problem).
        cfg.tls.mode = "skip"

        async with HueBridgeClient(cfg) as client:
            app_key = await client.authenticate()

        # Reload config to restore the TLS mode saved by `setup`.
        final_cfg = load_config(host=host or _host)
        final_cfg.bridge.application_key = app_key
        save_config(final_cfg)
        _err.print(f"[green]Application key registered: {app_key}[/green]")

    _run(_do())


@app.command(name="clear-cache")
def clear_cache() -> None:
    """Clear the cached bridge resources."""
    import json

    from huehub.cache import ResourceCache
    from huehub.config import load_config

    # Needs to match how other commands load config
    cfg = load_config(host=_host, application_key=_app_key)
    bridge_id = cfg.bridge.bridge_id or "default"
    cache = ResourceCache(bridge_id)
    cache.invalidate()

    if _json_output:
        _out.print_json(json.dumps({"success": True, "message": "Cache cleared"}))
    else:
        _err.print(f"[green]Cache for bridge '{bridge_id}' cleared.[/green]")


@app.command()
def info() -> None:
    """Show Hue Bridge information."""

    async def _do() -> None:
        async with _get_client() as client:
            bridge = await client.get_bridge_info()

        data = {
            "host": bridge.host,
            "bridge_id": bridge.bridge_id,
            "name": bridge.name,
            "model_id": bridge.model_id,
            "api_version": bridge.api_version,
            "software_version": bridge.software_version,
        }
        if _json_output:
            _out.print_json(_json.dumps(data))
            return

        table = Table(title="Bridge Info")
        table.add_column("Field")
        table.add_column("Value")
        for k, v in data.items():
            table.add_row(k, str(v or ""))
        _out.print(table)

    _run(_do())


@app.command()
def doctor() -> None:
    """Run diagnostics on the bridge connection."""

    async def _do() -> None:
        cfg = load_config(host=_host, application_key=_app_key)
        host = cfg.bridge.host
        if not host:
            _err.print("[red]FAIL[/red] No bridge host configured.")
            raise typer.Exit(code=1)

        results: list[tuple[str, str, str]] = []

        # TLS
        try:
            import ssl

            ssl.get_server_certificate((host, 443))
            results.append(("TLS", "PASS", "Certificate reachable"))
        except Exception as exc:
            results.append(("TLS", "FAIL", str(exc)))

        # REST
        from huehub.client import HueBridgeClient

        try:
            async with HueBridgeClient(cfg) as client:
                await client.get_bridge_info()
            results.append(("REST API", "PASS", "Bridge responded"))
        except AuthError as exc:
            results.append(("REST API", "WARN", str(exc)))
        except Exception as exc:
            results.append(("REST API", "FAIL", str(exc)))

        # SSE (quick connection test only)
        try:
            from huehub.tls import TlsMode, make_httpx_client

            bridge_id = cfg.bridge.bridge_id or "default"
            http = make_httpx_client(host, bridge_id, TlsMode(cfg.tls.mode), timeout=5)
            async with http:
                resp = await http.get(
                    f"https://{host}/eventstream/clip/v2",
                    headers={
                        "hue-application-key": cfg.bridge.application_key or "",
                        "Accept": "text/event-stream",
                    },
                    timeout=3,
                )
                results.append(("SSE", "PASS", f"HTTP {resp.status_code}"))
        except Exception as exc:
            results.append(("SSE", "WARN", str(exc)))

        if _json_output:
            _out.print_json(
                _json.dumps([
                    {"check": r[0], "status": r[1], "detail": r[2]} for r in results
                ])
            )
            return

        table = Table(title="Bridge Diagnostics")
        table.add_column("Check")
        table.add_column("Status")
        table.add_column("Detail")
        for check, status, detail in results:
            colour = (
                "green" if status == "PASS" else "yellow" if status == "WARN" else "red"
            )
            table.add_row(check, f"[{colour}]{status}[/{colour}]", detail)
        _out.print(table)

    _run(_do())


@app.command(name="all-off")
def all_off() -> None:
    """Turn off all lights on the bridge."""

    async def _do() -> None:
        async with _get_client() as client:
            await client.all_off()
        _err.print("[green]All lights turned off.[/green]")

    _run(_do())


@app.command()
def listen(
    type_filter: Annotated[
        list[str] | None, typer.Option("--type", help="Filter by resource type.")
    ] = None,
) -> None:
    """Stream real-time events from the bridge."""

    async def _do() -> None:
        async with _get_client() as client:
            async for event in client.listen():
                if type_filter and event.resource_type not in type_filter:
                    continue
                if _json_output:
                    _out.print_json(
                        _json.dumps({
                            "type": event.type,
                            "resource_type": event.resource_type,
                            "resource_id": event.resource_id,
                            "timestamp": event.timestamp,
                            "data": event.data,
                        })
                    )
                else:
                    _out.print(
                        f"[cyan]{event.timestamp}[/cyan] "
                        f"[bold]{event.type}[/bold] "
                        f"{event.resource_type}/{event.resource_id}"
                    )

    _run(_do())


# ---------------------------------------------------------------------------
# Lights sub-commands
# ---------------------------------------------------------------------------


@lights_app.command(name="list")
def lights_list(
    room: Annotated[
        str | None, typer.Option("--room", help="Filter by room name.")
    ] = None,
) -> None:
    """List all lights."""

    async def _do() -> None:
        async with _get_client() as client:
            lights = await client.list_lights()

        if room:
            # Filter by room (need rooms too)
            async def _filtered() -> list:
                async with _get_client() as c:
                    rooms = await c.list_rooms()
                    lts = await c.list_lights()
                    for r in rooms:
                        if r.name.lower() == room.lower() or r.id == room:
                            return [lig for lig in lts if lig.id in r.light_ids]
                return lts

            lights = _run(_filtered())  # type: ignore[assignment]

        if _json_output:
            _out.print_json(
                _json.dumps([
                    {
                        "id": lig.id,
                        "name": lig.name,
                        "on": lig.is_on,
                        "brightness": lig.brightness,
                        "reachable": lig.is_reachable,
                    }
                    for lig in lights
                ])
            )
            return

        table = Table(title="Lights")
        table.add_column("Name")
        table.add_column("On")
        table.add_column("Brightness")
        table.add_column("Mode")
        table.add_column("Reachable")
        for lig in lights:
            table.add_row(
                lig.name,
                "●" if lig.is_on else "○",
                f"{lig.brightness:.0f}%" if lig.brightness is not None else "–",
                lig.color_mode or "–",
                "✓" if lig.is_reachable else "✗",
            )
        _out.print(table)

    _run(_do())


@lights_app.command()
def show(name: Annotated[str, typer.Argument(help="Light name or UUID.")]) -> None:
    """Show current state of a light."""

    async def _do() -> None:
        async with _get_client() as client:
            lig = await client.get_light(name)

        data = {
            "id": lig.id,
            "name": lig.name,
            "on": lig.is_on,
            "brightness": lig.brightness,
            "color_xy": lig.color_xy,
            "color_temp_mirek": lig.color_temp_mirek,
            "color_mode": lig.color_mode,
            "reachable": lig.is_reachable,
            "effects": list(lig.effects_available),
        }
        if _json_output:
            _out.print_json(_json.dumps(data, default=str))
            return
        table = Table(title=f"Light: {lig.name}")
        table.add_column("Field")
        table.add_column("Value")
        for k, v in data.items():
            table.add_row(k, str(v) if v is not None else "–")
        _out.print(table)

    _run(_do())


@lights_app.command(name="on")
def light_on(name: Annotated[str, typer.Argument()]) -> None:
    """Turn on a light."""

    async def _do() -> None:
        async with _get_client() as client:
            await client.turn_on(name)
        _err.print(f"[green]{name}[/green] turned on.")

    _run(_do())


@lights_app.command(name="off")
def light_off(name: Annotated[str, typer.Argument()]) -> None:
    """Turn off a light."""

    async def _do() -> None:
        async with _get_client() as client:
            await client.turn_off(name)
        _err.print(f"[green]{name}[/green] turned off.")

    _run(_do())


@lights_app.command(name="set")
def light_set(
    name: Annotated[str, typer.Argument()],
    brightness: Annotated[float | None, typer.Option("--brightness", "-b")] = None,
    color: Annotated[str | None, typer.Option("--color", "-c")] = None,
    transition: Annotated[int | None, typer.Option("--transition", "-t")] = None,
    effect: Annotated[str | None, typer.Option("--effect")] = None,
    on: Annotated[bool | None, typer.Option("--on/--off")] = None,
) -> None:
    """Set light properties."""

    async def _do() -> None:
        async with _get_client() as client:
            await client.set_light(
                name,
                on=on,
                brightness=brightness,
                color=color,
                transition_ms=transition,
                effect=effect,
            )
        _err.print(f"[green]{name}[/green] updated.")

    _run(_do())


# ---------------------------------------------------------------------------
# Rooms sub-commands
# ---------------------------------------------------------------------------


@rooms_app.command(name="list")
def rooms_list() -> None:
    """List all rooms."""

    async def _do() -> None:
        async with _get_client() as client:
            all_res = await client.get_all_resources()
            rooms = sorted(all_res.rooms, key=lambda r: r.name)
            gl_map = {gl.id: gl for gl in all_res.grouped_lights}

        if _json_output:
            _out.print_json(
                _json.dumps([
                    {
                        "id": r.id,
                        "name": r.name,
                        "lights": len(r.light_ids),
                        "is_on": gl_map[r.grouped_light_id].is_on
                        if r.grouped_light_id in gl_map
                        else None,
                    }
                    for r in rooms
                ])
            )
            return

        table = Table(title="Rooms")
        table.add_column("Name")
        table.add_column("State")
        table.add_column("Lights")
        for r in rooms:
            gl = gl_map.get(r.grouped_light_id)
            is_on = getattr(gl, "is_on", None)

            if is_on is None:
                state_str = "Unknown"
                color = "dim"
            elif is_on:
                state_str = "On"
                color = "green"
            else:
                state_str = "Off"
                color = "dim"

            table.add_row(
                r.name,
                f"[{color}]{state_str}[/{color}]",
                str(len(r.light_ids)),
            )
        _out.print(table)

    _run(_do())


@rooms_app.command()
def show(name: Annotated[str, typer.Argument()]) -> None:  # noqa: F811
    """Show room details."""

    async def _do() -> None:
        async with _get_client() as client:
            room = await client.get_room(name)

        data = {
            "id": room.id,
            "name": room.name,
            "grouped_light_id": room.grouped_light_id,
            "light_ids": list(room.light_ids),
        }
        if _json_output:
            _out.print_json(_json.dumps(data))
            return
        table = Table(title=f"Room: {room.name}")
        table.add_column("Field")
        table.add_column("Value")
        for k, v in data.items():
            table.add_row(k, str(v))
        _out.print(table)

    _run(_do())


@rooms_app.command(name="on")
def room_on(name: Annotated[str, typer.Argument()]) -> None:
    """Turn on all lights in a room."""

    async def _do() -> None:
        async with _get_client() as client:
            await client.set_room(name, on=True)
        _err.print(f"[green]{name}[/green] turned on.")

    _run(_do())


@rooms_app.command(name="off")
def room_off(name: Annotated[str, typer.Argument()]) -> None:
    """Turn off all lights in a room."""

    async def _do() -> None:
        async with _get_client() as client:
            await client.set_room(name, on=False)
        _err.print(f"[green]{name}[/green] turned off.")

    _run(_do())


@rooms_app.command(name="set")
def room_set(
    name: Annotated[str, typer.Argument()],
    brightness: Annotated[float | None, typer.Option("--brightness", "-b")] = None,
    color: Annotated[str | None, typer.Option("--color", "-c")] = None,
    transition: Annotated[int | None, typer.Option("--transition", "-t")] = None,
    on: Annotated[bool | None, typer.Option("--on/--off")] = None,
) -> None:
    """Set room light properties."""

    async def _do() -> None:
        async with _get_client() as client:
            await client.set_room(
                name,
                on=on,
                brightness=brightness,
                color=color,
                transition_ms=transition,
            )
        _err.print(f"[green]{name}[/green] updated.")

    _run(_do())


# ---------------------------------------------------------------------------
# Zones sub-commands
# ---------------------------------------------------------------------------


@zones_app.command(name="list")
def zones_list() -> None:
    """List all zones."""

    async def _do() -> None:
        async with _get_client() as client:
            all_res = await client.get_all_resources()
            zones = sorted(all_res.zones, key=lambda z: z.name)
            gl_map = {gl.id: gl for gl in all_res.grouped_lights}

        if _json_output:
            _out.print_json(
                _json.dumps([
                    {
                        "id": z.id,
                        "name": z.name,
                        "lights": len(z.light_ids),
                        "is_on": gl_map[z.grouped_light_id].is_on
                        if z.grouped_light_id in gl_map
                        else None,
                    }
                    for z in zones
                ])
            )
            return

        table = Table(title="Zones")
        table.add_column("Name")
        table.add_column("State")
        table.add_column("Lights")
        for z in zones:
            gl = gl_map.get(z.grouped_light_id)
            is_on = getattr(gl, "is_on", None)

            if is_on is None:
                state_str = "Unknown"
                color = "dim"
            elif is_on:
                state_str = "On"
                color = "green"
            else:
                state_str = "Off"
                color = "dim"

            table.add_row(
                z.name,
                f"[{color}]{state_str}[/{color}]",
                str(len(z.light_ids)),
            )
        _out.print(table)

    _run(_do())


@zones_app.command(name="on")
def zone_on(name: Annotated[str, typer.Argument()]) -> None:
    """Turn on all lights in a zone."""

    async def _do() -> None:
        async with _get_client() as client:
            await client.set_zone(name, on=True)
        _err.print(f"[green]{name}[/green] turned on.")

    _run(_do())


@zones_app.command(name="off")
def zone_off(name: Annotated[str, typer.Argument()]) -> None:
    """Turn off all lights in a zone."""

    async def _do() -> None:
        async with _get_client() as client:
            await client.set_zone(name, on=False)
        _err.print(f"[green]{name}[/green] turned off.")

    _run(_do())


@zones_app.command(name="set")
def zone_set(
    name: Annotated[str, typer.Argument()],
    brightness: Annotated[float | None, typer.Option("--brightness", "-b")] = None,
    color: Annotated[str | None, typer.Option("--color", "-c")] = None,
    transition: Annotated[int | None, typer.Option("--transition", "-t")] = None,
    on: Annotated[bool | None, typer.Option("--on/--off")] = None,
) -> None:
    """Set zone light properties."""

    async def _do() -> None:
        async with _get_client() as client:
            await client.set_zone(
                name,
                on=on,
                brightness=brightness,
                color=color,
                transition_ms=transition,
            )
        _err.print(f"[green]{name}[/green] updated.")

    _run(_do())


# ---------------------------------------------------------------------------
# Scenes sub-commands
# ---------------------------------------------------------------------------


@scenes_app.command(name="list")
def scenes_list(
    room: Annotated[str | None, typer.Option("--room")] = None,
) -> None:
    """List scenes."""

    async def _do() -> None:
        async with _get_client() as client:
            scenes = await client.list_scenes(group=room)
            all_res = await client.get_all_resources()

            group_map = {}
            for r in all_res.rooms:
                group_map[r.id] = r.name
            for z in all_res.zones:
                group_map[z.id] = z.name

            # Sort scenes conceptually by Room, then Scene name
            scenes = sorted(
                scenes, key=lambda s: (group_map.get(s.group_id, ""), s.name)
            )

        if _json_output:
            _out.print_json(
                _json.dumps([
                    {
                        "id": s.id,
                        "name": s.name,
                        "group": group_map.get(s.group_id, s.group_id),
                        "active": s.is_active,
                    }
                    for s in scenes
                ])
            )
            return

        table = Table(title="Scenes")
        table.add_column("Name")
        table.add_column("Room/Zone")
        table.add_column("State")
        for s in scenes:
            group_name = group_map.get(s.group_id, "Unknown")

            if s.is_active:
                state_str = "Active"
                color = "green"
            else:
                state_str = "Inactive"
                color = "dim"

            table.add_row(
                s.name,
                group_name,
                f"[{color}]{state_str}[/{color}]",
            )
        _out.print(table)

    _run(_do())


@scenes_app.command()
def activate(
    name: Annotated[str, typer.Argument()],
    room: Annotated[str | None, typer.Option("--room")] = None,
) -> None:
    """Activate a scene."""

    async def _do() -> None:
        async with _get_client() as client:
            await client.activate_scene(name, group=room)
        _err.print(f"[green]Scene '{name}' activated.[/green]")

    _run(_do())


# ---------------------------------------------------------------------------
# Devices sub-commands
# ---------------------------------------------------------------------------


@devices_app.command(name="list")
def devices_list() -> None:
    """List all devices."""

    async def _do() -> None:
        async with _get_client() as client:
            devices = await client.list_devices()

        if _json_output:
            _out.print_json(
                _json.dumps([
                    {
                        "id": d.id,
                        "name": d.name,
                        "product": d.product_name,
                        "manufacturer": d.manufacturer,
                    }
                    for d in devices
                ])
            )
            return

        table = Table(title="Devices")
        table.add_column("Name")
        table.add_column("Product")
        table.add_column("Manufacturer")
        for d in devices:
            table.add_row(d.name, d.product_name or "–", d.manufacturer or "–")
        _out.print(table)

    _run(_do())


# ---------------------------------------------------------------------------
# Sensors sub-commands
# ---------------------------------------------------------------------------


@sensors_app.command(name="list")
def sensors_list() -> None:
    """List all sensors."""

    async def _do() -> None:
        async with _get_client() as client:
            motions = await client.list_motion_sensors()
            temps = await client.list_temperature_sensors()
            lights_lvl = await client.list_light_level_sensors()
            contacts = await client.list_contact_sensors()

        if _json_output:
            data: list[dict] = (
                [
                    {"type": "motion", "name": m.name, "value": m.motion_detected}
                    for m in motions
                ]
                + [
                    {
                        "type": "temperature",
                        "name": t.name,
                        "value": t.temperature_celsius,
                    }
                    for t in temps
                ]
                + [
                    {
                        "type": "light_level",
                        "name": ll.name,
                        "value": ll.light_level_lux,
                    }
                    for ll in lights_lvl
                ]
                + [
                    {"type": "contact", "name": c.name, "value": c.contact}
                    for c in contacts
                ]
            )
            _out.print_json(_json.dumps(data))
            return

        table = Table(title="Sensors")
        table.add_column("Type")
        table.add_column("Name")
        table.add_column("Value")
        for m in motions:
            table.add_row(
                "motion", m.name, "detected" if m.motion_detected else "clear"
            )
        for t in temps:
            val = (
                f"{t.temperature_celsius:.1f} °C"
                if t.temperature_celsius is not None
                else "–"
            )
            table.add_row("temperature", t.name, val)
        for ll in lights_lvl:
            val = f"{ll.light_level_lux} lux" if ll.light_level_lux is not None else "–"
            table.add_row("light_level", ll.name, val)
        for c in contacts:
            val = "closed" if c.contact else "open" if c.contact is False else "–"
            table.add_row("contact", c.name, val)
        _out.print(table)

    _run(_do())


@sensors_app.command()
def motion() -> None:
    """Show motion sensor readings."""

    async def _do() -> None:
        async with _get_client() as client:
            sensors = await client.list_motion_sensors()

        if _json_output:
            _out.print_json(
                _json.dumps([
                    {
                        "id": s.id,
                        "name": s.name,
                        "motion": s.motion_detected,
                        "valid": s.motion_valid,
                        "reachable": s.is_reachable,
                    }
                    for s in sensors
                ])
            )
            return

        table = Table(title="Motion Sensors")
        table.add_column("Name")
        table.add_column("Motion")
        table.add_column("Valid")
        for s in sensors:
            table.add_row(
                s.name,
                "[yellow]MOTION[/yellow]" if s.motion_detected else "clear",
                "✓" if s.motion_valid else "–",
            )
        _out.print(table)

    _run(_do())


@sensors_app.command()
def temperature() -> None:
    """Show temperature sensor readings."""

    async def _do() -> None:
        async with _get_client() as client:
            sensors = await client.list_temperature_sensors()

        if _json_output:
            _out.print_json(
                _json.dumps([
                    {
                        "id": s.id,
                        "name": s.name,
                        "temp_celsius": s.temperature_celsius,
                        "valid": s.temperature_valid,
                    }
                    for s in sensors
                ])
            )
            return

        table = Table(title="Temperature Sensors")
        table.add_column("Name")
        table.add_column("Temperature")
        for s in sensors:
            val = (
                f"{s.temperature_celsius:.1f} °C"
                if s.temperature_celsius is not None
                else "–"
            )
            table.add_row(s.name, val)
        _out.print(table)

    _run(_do())


@sensors_app.command(name="light-level")
def light_level() -> None:
    """Show light level sensor readings."""

    async def _do() -> None:
        async with _get_client() as client:
            sensors = await client.list_light_level_sensors()

        if _json_output:
            _out.print_json(
                _json.dumps([
                    {
                        "id": s.id,
                        "name": s.name,
                        "lux": s.light_level_lux,
                        "valid": s.light_level_valid,
                    }
                    for s in sensors
                ])
            )
            return

        table = Table(title="Light Level Sensors")
        table.add_column("Name")
        table.add_column("Level")
        for s in sensors:
            val = f"{s.light_level_lux} lux" if s.light_level_lux is not None else "–"
            table.add_row(s.name, val)
        _out.print(table)

    _run(_do())


@sensors_app.command()
def contact() -> None:
    """Show contact (door/window) sensor readings."""

    async def _do() -> None:
        async with _get_client() as client:
            sensors = await client.list_contact_sensors()

        if _json_output:
            _out.print_json(
                _json.dumps([
                    {
                        "id": s.id,
                        "name": s.name,
                        "closed": s.contact,
                        "reachable": s.is_reachable,
                    }
                    for s in sensors
                ])
            )
            return

        table = Table(title="Contact Sensors")
        table.add_column("Name")
        table.add_column("State")
        for s in sensors:
            state = "closed" if s.contact else "open" if s.contact is False else "–"
            colour = "green" if s.contact else "red" if s.contact is False else "white"
            table.add_row(s.name, f"[{colour}]{state}[/{colour}]")
        _out.print(table)

    _run(_do())


# ---------------------------------------------------------------------------
# Raw API sub-commands
# ---------------------------------------------------------------------------


@api_app.command(name="get")
def api_get(
    path: Annotated[str, typer.Argument(help="API path, e.g. /clip/v2/resource/light")],
) -> None:
    """Send a raw GET request to the bridge."""

    async def _do() -> None:
        cfg = load_config(host=_host, application_key=_app_key)
        from huehub.tls import TlsMode, make_httpx_client

        bridge_id = cfg.bridge.bridge_id or "default"
        host = cfg.bridge.host or ""
        http = make_httpx_client(host, bridge_id, TlsMode(cfg.tls.mode))
        async with http:
            resp = await http.get(
                f"https://{host}{path}",
                headers={"hue-application-key": cfg.bridge.application_key or ""},
            )
        _out.print_json(resp.text)

    _run(_do())


@api_app.command(name="put")
def api_put(
    path: Annotated[str, typer.Argument()],
    body: Annotated[str, typer.Option("--body", help="JSON body string.")],
) -> None:
    """Send a raw PUT request to the bridge."""

    async def _do() -> None:
        cfg = load_config(host=_host, application_key=_app_key)
        from huehub.tls import TlsMode, make_httpx_client

        bridge_id = cfg.bridge.bridge_id or "default"
        host = cfg.bridge.host or ""
        http = make_httpx_client(host, bridge_id, TlsMode(cfg.tls.mode))
        async with http:
            resp = await http.put(
                f"https://{host}{path}",
                content=body,
                headers={
                    "hue-application-key": cfg.bridge.application_key or "",
                    "Content-Type": "application/json",
                },
            )
        _out.print_json(resp.text)

    _run(_do())


if __name__ == "__main__":
    app()
