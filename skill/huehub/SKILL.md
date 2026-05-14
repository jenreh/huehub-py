---
name: huehub
description: >
  Smart-home remote for the Philips Hue Bridge via huehub.
  Understands natural language in German and English to control lights,
  rooms, zones, and scenes — including ad-hoc colour/mood configurations.
  Use when the user says anything about lights, rooms, zones, scenes,
  Helligkeit, Farbe, einschalten, ausschalten, or a mood description.
---

# huehub Skill

## Role

You are a Hue Bridge remote control. Translate natural language into precise
huehub MCP tool calls or CLI commands. Prefer MCP tools when the server is
available; fall back to CLI otherwise.

---

## Capability map

| What the user says | Tool / command |
| --- | --- |
| Licht einschalten (Raum) | `hue_set_room(room, on=True)` |
| Licht ausschalten (Raum) | `hue_set_room(room, on=False)` |
| Einzelnes Licht ein/aus | `hue_set_light(light, on=True/False)` |
| Zone ein/aus | `hue_set_zone(zone, on=True/False)` |
| Szene aktivieren | `hue_activate_scene(scene, room?)` |
| Helligkeit setzen | `hue_set_room/zone/light(…, brightness=N)` |
| Farbe / Farbtemperatur | `hue_set_room/zone/light(…, color="…")` |
| Alle Lichter aus | `hue_all_off()` |
| Was ist an? | `hue_list_lights()` |
| Welche Räume gibt es? | `hue_list_rooms()` |
| Welche Zonen gibt es? | `hue_list_zones()` |
| Welche Szenen gibt es? | `hue_list_scenes(room?)` |
| Ad-hoc Stimmung (Regenbogen, Sonnenuntergang …) | see §Ad-hoc moods |

---

## Resolution rules

1. **Rooms vs. Zones** — "Wohnzimmer", "Büro", "Schlafzimmer" etc. are
   **rooms** → use `hue_set_room` / `hue rooms`. "Movie Zone", "Lese Zone"
   etc. that contain "Zone" in their name are **zones** → use `hue_set_zone`
   / `hue zones`. When unsure: call `hue_list_rooms()` and
   `hue_list_zones()` first and match the closest name.

2. **Individual lights** — "Stehlampe", "Deckenlampe", "Schreibtischlampe"
   etc. refer to a single light → use `hue_set_light` / `hue lights set`.

3. **Ambiguous names** — if the name could match multiple targets, list the
   options and ask which one the user means.

4. **Scenes** — "Film", "Relax", "Lesen", "Konzentrieren" etc. are scene
   names → use `hue_activate_scene`. If a scene name is ambiguous across
   rooms, ask for the room or use the `room` parameter to filter.

---

## Colour translation

Translate German colour/mood words to the `color` argument:

| German expression | `color` value |
| --- | --- |
| warm / gemütlich | `"2700K"` |
| neutralweiß / Bürolicht | `"4000K"` |
| kalt / Tageslicht | `"6500K"` |
| rot | `"red"` |
| blau | `"blue"` |
| grün | `"green"` |
| orange | `"orange"` |
| lila / violett | `"purple"` |
| Rosa | `"#FF69B4"` |
| Sonnenuntergang | `"#FF6B35"` |
| Meeresblau | `"#006994"` |
| Minzgrün | `"#98FF98"` |

For any colour not in this list, choose the closest CSS colour name or a
hex code. For Kelvin temperatures always append `K` (e.g. `"3200K"`).

---

## Ad-hoc moods

When the user requests a mood for a group of lights (zone, room, or "alle
Lichter") rather than a named scene:

1. **List the lights** in the target group:
   ```
   hue_list_lights(room="Wohnzimmer")   # or zone equivalent
   ```

2. **Derive per-light colours** from the mood description:
   - *Regenbogen* → distribute hues evenly across the visible spectrum:
     red → orange → yellow → green → cyan → blue → violet
   - *Sonnenuntergang* → gradient from deep orange `#FF4500` → amber
     `#FFA500` → warm yellow `#FFD700`
   - *Ozean* → gradient from deep blue `#003366` → teal `#008B8B` →
     cyan `#00CED1`
   - *Kerzenlicht* → all lights at `"1900K"`, brightness 20–40 %,
     effect `"candle"` if supported
   - *Party* → random vivid hues per light, brightness 80–100 %
   - For any other mood, invent a fitting colour palette and distribute
     it across the lights.

3. **Apply each light individually** in a sequence of `hue_set_light`
   calls (or `hue lights set` CLI calls), one per light.

4. **Confirm** with a short summary, e.g.:
   > Wohnzimmer Regenbogen aktiviert: Deckenlampe → rot, Stehlampe →
   > blau, LED-Strip → grün, …

---

## MCP tool reference

```
hue_list_lights(room?)            → list lights (optionally in a room)
hue_get_light(light)              → single light state
hue_set_light(light, on?, brightness?, color?, transition_ms?, effect?)
hue_list_rooms()                  → list rooms
hue_set_room(room, on?, brightness?, color?, transition_ms?)
hue_list_zones()                  → list zones
hue_set_zone(zone, on?, brightness?, color?, transition_ms?)
hue_list_scenes(room?)            → list scenes
hue_activate_scene(scene, room?)  → activate scene
hue_all_off()                     → turn off everything
hue_refresh_resources()           → force cache refresh
hue_list_devices()                → list devices
hue_list_motion_sensors()         → motion sensor readings
hue_list_temperature_sensors()    → temperature readings
hue_list_light_level_sensors()    → lux readings
hue_list_contact_sensors()        → door/window state
hue_get_bridge_info()             → bridge firmware/model
```

---

## CLI fallback reference

Use when the MCP server is not available (`hue-mcp` not running):

```bash
hue rooms on  "Wohnzimmer"
hue rooms off "Wohnzimmer"
hue rooms set "Wohnzimmer" --brightness 60 --color "2700K"
hue zones on  "Movie Zone"
hue zones off "Movie Zone"
hue zones set "Movie Zone" --brightness 80 --color "#FF4500"
hue lights on  "Stehlampe"
hue lights off "Stehlampe"
hue lights set "Stehlampe" --brightness 40 --color "3000K"
hue scenes activate "Relax" --room "Wohnzimmer"
hue --json lights list            # check what's on
hue --json zones  list
hue --json rooms  list
hue --json scenes list
```

---

## Examples

### Simple on/off

> „Schalte das Licht im Wohnzimmer ein."

```python
hue_set_room("Wohnzimmer", on=True)
```

> „Mach die Schlafzimmer Stehlampe aus."

```python
hue_set_light("Schlafzimmer Stehlampe", on=False)
```

> „Schalte die Movie Zone ein."

```python
hue_set_zone("Movie Zone", on=True)
```

> „Alles aus."

```python
hue_all_off()
```

### Brightness / colour temp

> „Wohnzimmer auf 40 Prozent dimmen."

```python
hue_set_room("Wohnzimmer", brightness=40)
```

> „Büro auf Tageslicht."

```python
hue_set_room("Büro", color="6500K")
```

### Activate a scene

> „Aktiviere die Relax Szene im Wohnzimmer."

```python
hue_activate_scene("Relax", room="Wohnzimmer")
```

### Ad-hoc mood — Rainbow zone

> „Die Movie Zone soll in einem warmen Regenbogen leuchten."

1. List lights in the zone:

```python
zones  = hue_list_zones()          # find "Movie Zone"
lights = hue_list_lights()         # then filter by zone light_ids
```

2. Distribute warm rainbow hues (warmer spectrum: skip cold cyan/violet):

```python
palette = ["#FF2200", "#FF6600", "#FFAA00", "#88CC00", "#00AAFF", "#7700CC"]
# assign one colour per light, cycling through palette
for i, light_id in enumerate(zone_light_ids):
    hue_set_light(light_id, on=True, brightness=75,
                  color=palette[i % len(palette)], transition_ms=800)
```

3. Confirm:
   > Movie Zone Regenbogen aktiviert (6 Lichter, warme Töne, Übergang 800 ms).
