# huehub

![Version](https://img.shields.io/badge/version-0.3.1-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE.md)
[![Python](https://img.shields.io/badge/python-3.14%2B-orange)](https://www.python.org)

**huehub** talks directly to your bridge over HTTPS — no Philips cloud, no account, no internet required.

---

## Features

- **Full CLIP API v2 coverage** — lights, rooms, zones, scenes, sensors, devices
- **Async Python library** — `async with HueBridgeClient(cfg) as client: ...`
- **Rich CLI** — human-readable tables or `--json` for scripts
- **MCP server** — expose your bridge as tools to Claude or any MCP client
- **TLS cert pinning** — extracts and pins the bridge certificate automatically
- **SSE event stream** — subscribe to real-time bridge events
- **On-disk resource cache** — fast repeated reads, configurable TTL

---

## Installation

```bash
pip install huehub-py
# or with uv
uv add huehub-py
```

Requires Python 3.14+.

---

## Quick start

### 1. Discover your bridge

```bash
hue discover
```

```text
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Host            ┃ Bridge ID        ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ 192.168.1.10    │ c42996fffec629f5 │
└─────────────────┴──────────────────┘
```

### 2. Pin the TLS certificate

```bash
hue setup --host 192.168.1.10
```

```text
Extracting TLS certificate from 192.168.1.10:443…
Certificate saved to ~/.cache/huehub/default/bridge.pem
Press the link button on your Hue Bridge NOW…
Then run: hue authenticate
```

### 3. Register an application key

Press the link button on the bridge, then:

```bash
hue authenticate
```

```text
Application key registered: yqPX7XTm…
```

Config is saved to `~/.config/huehub/config.toml`. You're done.

---

## CLI reference

```text
hue [--host IP] [--key KEY] [--json] [--verbose] <command>
```

| Command | Description |
| --- | --- |
| `hue discover` | mDNS / cloud discovery of bridges |
| `hue setup --host IP` | Extract and pin the bridge TLS certificate |
| `hue authenticate` | Register a new application key |
| `hue info` | Bridge firmware, model, API version |
| `hue lights list` | All lights with status |
| `hue lights on NAME` | Turn a light on |
| `hue lights off NAME` | Turn a light off |
| `hue lights set NAME` | Set brightness / colour / colour-temp |
| `hue rooms list` | Rooms with light count |
| `hue rooms on NAME` | Turn all lights in a room on |
| `hue rooms off NAME` | Turn all lights in a room off |
| `hue rooms set NAME` | Set brightness / colour for a room |
| `hue zones list` | Zones with light count |
| `hue scenes list` | Scenes, optionally filtered by room |
| `hue scenes activate NAME` | Activate a scene |
| `hue devices list` | All paired devices |
| `hue sensors list` | Motion, temperature, light-level, contact |
| `hue api get PATH` | Raw GET request to `/clip/v2/...` |

Use `--json` before the subcommand for machine-readable output:

```bash
hue --json rooms list | jq '.[].name'
```

---

## Python library

```python
import asyncio
from huehub import HueBridgeClient, load_config


async def main():
    async with HueBridgeClient(load_config()) as hue:
        # List all lights
        for light in await hue.list_lights():
            print(light.name, light.on, f"{light.brightness:.0%}")

        # Turn on a room at 60 % warm white
        await hue.turn_on_room("Wohnzimmer", brightness=60, color="2700K")

        # Activate a scene
        await hue.activate_scene("Relax")

        # Stream real-time events
        async for event in hue.listen():
            print(event)


asyncio.run(main())
```

### Colour input formats

`turn_on`, `set_light`, `set_room`, and `set_zone` all accept the same flexible `color` argument:

| Format | Example |
| --- | --- |
| Colour temperature (Kelvin) | `"2700K"`, `"4000k"` |
| Named white | `"warm"`, `"cool"`, `"daylight"` |
| CSS hex | `"#FF8800"` |
| CSS name | `"red"`, `"blue"`, `"coral"` |

---

## MCP server

**huehub** ships with an MCP server that exposes the bridge as tools for Claude or any MCP-compatible client.

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "hue": {
      "command": "hue-mcp"
    }
  }
}
```

### VS Code (agent mode)

```json
{
  "mcp": {
    "servers": {
      "hue": { "command": "hue-mcp", "type": "stdio" }
    }
  }
}
```

### Available MCP tools

`hue_get_bridge_info` · `hue_list_lights` · `hue_turn_on` · `hue_turn_off` · `hue_set_light` · `hue_list_rooms` · `hue_set_room` · `hue_list_zones` · `hue_set_zone` · `hue_list_scenes` · `hue_activate_scene` · `hue_list_devices` · `hue_list_sensors` · `hue_list_entertainment_zones` · `hue_get_raw`

---

## Configuration

Config file: `~/.config/huehub/config.toml`

```toml
[bridge]
host = "192.168.1.10"
application_key = "your-key-here"

[tls]
# auto (default) | verify | skip
mode = "verify"

[connection]
request_timeout_s = 10

[cache]
ttl_seconds = 300

[color]
default_transition_ms = 400
```

Environment variable overrides:

| Variable | Overrides |
| --- | --- |
| `HUE_BRIDGE_HOST` | `bridge.host` |
| `HUE_APPLICATION_KEY` | `bridge.application_key` |
| `HUE_TLS_MODE` | `tls.mode` |
| `HUE_CONFIG_DIR` | config directory path |

---

## TLS modes

| Mode | Behaviour |
| --- | --- |
| `auto` | Use pinned cert if present, fall back to skip (with warning) |
| `verify` | Require pinned cert — fail if absent |
| `skip` | Disable TLS verification (not recommended) |

Run `hue setup` to extract and pin the bridge certificate. The certificate is stored in `~/.cache/huehub/<bridge-id>/bridge.pem`. Connection by IP is supported even though the bridge certificate's SAN contains the hostname.

---

## Agent skill

`skill/huehub/SKILL.md` follows the [Agent Skills open standard](https://agentskills.io) and works across GitHub Copilot (VS Code, CLI, cloud agent), Claude Code, OpenAI Codex, and Cursor — write once, use everywhere.

### Skill installation

Each agent scans well-known directories for `SKILL.md` files automatically — no configuration required.

**Project skill** (available in one repository):

```bash
# pick whichever path matches your primary agent
cp -r skill/huehub /your-project/.agents/skills/huehub    # generic / Copilot
cp -r skill/huehub /your-project/.github/skills/huehub    # Copilot recommended
cp -r skill/huehub /your-project/.claude/skills/huehub    # Claude Code

# symlink keeps it in sync with this repo
ln -s "$(pwd)/skill/huehub" /your-project/.agents/skills/huehub
```

**Personal skill** (available in every project on your machine):

```bash
cp -r skill/huehub ~/.agents/skills/huehub      # generic / Copilot
cp -r skill/huehub ~/.claude/skills/huehub      # Claude Code
cp -r skill/huehub ~/.copilot/skills/huehub     # Copilot only

ln -s "$(pwd)/skill/huehub" ~/.agents/skills/huehub   # or symlink
```

> [!TIP]
> If you cloned huehub-py, the skill is already present as a project skill in `.agents/skills/huehub` — no extra step needed.

### What it does

The skill maps natural-language phrases to MCP tool calls or `hue` CLI commands automatically:

| Intent | Example utterance |
| --- | --- |
| Turn room on/off | "Wohnzimmer einschalten", "turn off the bedroom" |
| Set brightness | "Küche auf 40 %", "dim the office to 20" |
| Set colour / temperature | "Flur warm weiß", "living room blue" |
| Activate scene | "Relax im Büro", "activate Concentrate in the kitchen" |
| Ad-hoc mood | "Regenbogen im Flur", "sunset vibe in the lounge" |
| All lights off | "Alles aus", "turn everything off" |

MCP tools are used when the server is running; the skill falls back to the `hue` CLI automatically.

---

## Development

```bash
git clone https://github.com/jenreh/huehub-py
cd huehub-py
uv sync --extra dev
task test      # pytest with coverage
task lint      # ruff + mypy
task format    # ruff format
```

> [!NOTE]
> A `FakeBridge` simulator (`huehub.simulator`) is included for use in tests. It registers all expected CLIP v2 endpoints against `pytest-httpx` without requiring a real bridge.
