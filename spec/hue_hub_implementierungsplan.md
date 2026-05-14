# Philips Hue Bridge – Lokale Python Library – Konzept & Implementierungsplan

> **Projektname:** `huehub-py`
> **Paketname:** `huehub`
> **Stand:** Mai 2026
> **Ziel:** Lokale Steuerung des Philips Hue Bridge via Python (CLIP API v2) – nutzbar als Library, CLI und MCP-Server

---

## 1. Konzept & Protokoll-Grundlagen

### 1.1 Vergleich mit Harmony Hub

| Aspekt | Harmony Hub | Hue Bridge |
|--------|------------|------------|
| Protokoll | WebSocket (custom JSON) | HTTPS REST + SSE |
| Standard | Undokumentiert, inoffiziell | Offiziell dokumentiert (CLIP API v2) |
| Authentifizierung | Remote-ID im URL-Parameter | `hue-application-key` HTTP-Header |
| Push-Events | WebSocket-Events | Server-Sent Events (SSE) |
| TLS | Kein TLS | HTTPS zwingend, selbst-signiertes Zertifikat |
| Ressourcenmodell | Aktivitäten + Geräte | Hierarchische Ressourcen mit UUIDs |
| Statuszuverlässigkeit | Harmony-Zustand (driftet) | Bridge kennt echten Lichtstatus |

### 1.2 Transport: HTTPS / REST

Die Hue Bridge v2 ist ausschließlich über HTTPS auf **Port 443** erreichbar. HTTP ist nicht unterstützt.

**TLS-Zertifikat-Problem:**
Die Bridge verwendet ein selbst-signiertes Zertifikat (CN = Bridge-Seriennummer). Neuere Bridges haben ein von Signify's CA signiertes Zertifikat. Zwei Strategien:

```
Strategie A (einfach, weniger sicher):
  httpx.AsyncClient(verify=False)
  → TLS-Verifikation deaktiviert
  → Warnung in Logs

Strategie B (empfohlen):
  Zertifikat einmalig extrahieren und als CA verwenden:
  openssl s_client -showcerts -connect <bridge-ip>:443 < /dev/null 2>/dev/null \
    | openssl x509 -outform PEM > bridge.pem
  httpx.AsyncClient(verify="bridge.pem")
```

Die Library unterstützt beide Modi. `hue setup` extrahiert automatisch das Zertifikat.

### 1.3 Authentifizierung: Application Key

Der Application Key (früher "username") wird **einmalig** registriert. Danach wird er bei jedem Request als HTTP-Header mitgeschickt:

```
hue-application-key: KyBPfHmVUGSJNBr0Je5GwJzeRc6PXpsYfZki1IRl
```

**Registrierung (einmalig, link button drücken erforderlich):**

```
POST https://<bridge-ip>/api
Body: {"devicetype": "hue_local#meinrechner", "generateclientkey": true}

Response (Erfolg):
  [{"success": {"username": "KyBPfH...", "clientkey": "936C90..."}}]

Response (Link-Button nicht gedrückt):
  [{"error": {"type": 101, "description": "link button not pressed"}}]
```

`username` = Application Key für REST-Requests
`clientkey` = nur für Entertainment API (UDP-Streaming), nicht im MVP

### 1.4 REST-API-Struktur (CLIP v2)

**Base URL:** `https://<bridge-ip>/clip/v2/resource/`

Alle Endpunkte folgen demselben Schema:

| Operation | HTTP | Pfad |
|-----------|------|------|
| Alle Ressourcen abrufen | `GET` | `/clip/v2/resource` |
| Alle eines Typs | `GET` | `/clip/v2/resource/{rtype}` |
| Eine einzelne | `GET` | `/clip/v2/resource/{rtype}/{id}` |
| Aktualisieren | `PUT` | `/clip/v2/resource/{rtype}/{id}` |
| Erstellen | `POST` | `/clip/v2/resource/{rtype}` |
| Löschen | `DELETE` | `/clip/v2/resource/{rtype}/{id}` |

**Response-Format (immer gleich):**
```json
{
  "data": [ { ... } ],
  "errors": []
}
```

### 1.5 Ressourcen-Typen

| Ressource | Zweck |
|-----------|-------|
| `light` | Einzelne Leuchte (An/Aus, Helligkeit, Farbe, Farbtemperatur) |
| `grouped_light` | Gruppe von Lichtern gemeinsam steuern (Raum/Zone) |
| `room` | Physischer Raum mit Geräten und `grouped_light` |
| `zone` | Logische Gruppe (kann raumübergreifend sein) |
| `scene` | Gespeicherte Lichtstimmung, abrufbar |
| `smart_scene` | Dynamische Szene (Tageszeit-abhängig) |
| `device` | Physisches Gerät (Leuchte, Schalter, Sensor) |
| `bridge` | Bridge-Informationen |
| `bridge_home` | Alle Ressourcen der Bridge |
| `button` | Schalter-Events (PRESS, HOLD, RELEASE) |
| `motion` | Bewegungssensor |
| `temperature` | Temperatursensor |
| `light_level` | Lichtstärkesensor |
| `contact` | Tür-/Fenstersensor |
| `geofence_client` | Geofencing |
| `motion` | Bewegungssensor (präsent/abwesend) |
| `temperature` | Temperatursensor (°C) |
| `light_level` | Lichtstärkesensor (Lux) |
| `contact` | Tür-/Fenstersensor (offen/geschlossen) |
| `entertainment` | Entertainment-Zonen |

### 1.6 Licht steuern – Wichtigste PUT-Felder

```json
// Ein-/Ausschalten
{"on": {"on": true}}

// Helligkeit (0.0–100.0)
{"dimming": {"brightness": 75.0}}

// Ein + Helligkeit in einem Schritt
{"on": {"on": true}, "dimming": {"brightness": 75.0}}

// Farbtemperatur (mirek: 153 = 6500K kalt, 500 = 2000K warm)
{"color_temperature": {"mirek": 300}}

// Farbe (CIE xy-Farbraum, 0.0–1.0)
{"color": {"xy": {"x": 0.3, "y": 0.4}}}

// Übergangszeit (milliseconds, nur bei dynamics)
{"on": {"on": true}, "dimming": {"brightness": 50.0},
 "dynamics": {"duration": 1000}}

// Alert (Blink-Effekt)
{"alert": {"action": "breathe"}}

// Effekt
{"effects": {"effect": "candle"}}
// Werte: no_effect, candle, fire, prism, sparkle, opal, glisten
```

Für `grouped_light` (Raum/Zone) identische Felder.

### 1.7 Szene aktivieren

```
PUT /clip/v2/resource/scene/{scene-id}
Body: {"recall": {"action": "active"}}
      oder: {"recall": {"action": "dynamic_palette"}}
```

### 1.8 SSE Event-Stream

Der Hue Bridge sendet **proaktive Push-Notifications** via Server-Sent Events:

```
GET https://<bridge-ip>/eventstream/clip/v2
Headers:
  hue-application-key: <app-key>
  Accept: text/event-stream
```

**Event-Format:**
```
id: 1716714000:0
data: [{"creationtime":"2026-05-14T10:00:00Z","data":[{"id":"...","type":"light","on":{"on":true},"dimming":{"brightness":75.0}}],"id":"...","type":"update"}]
```

Events haben immer `type`: `update`, `add`, `delete`, `error`.

**Wichtig:** SSE-Verbindung zählt als eine der ~3 gleichzeitigen Bridge-Verbindungen. Rate-Limit: 1 Event-Batch pro Sekunde. HTTP/2 empfohlen für Multiplexing.

### 1.9 Discovery

**Methode 1 – mDNS (empfohlen, lokal):**
```
Service: _hue._tcp.local
TXT-Record enthält: bridgeid, modelid
```
Implementierung via `zeroconf`-Library. Timeout konfigurierbar (`[discovery].mdns_timeout_s`).

**Methode 2 – Hostname-Fallback (lokal):**
```
https://Philips-hue.local/api/0/config
```
Funktioniert zuverlässig wenn mDNS im Netzwerk blockiert ist (z.B. manche Router-Konfigurationen).

**Methode 3 – Hue Discovery API (cloud-Fallback):**
```
GET https://discovery.meethue.com/
Response: [{"id": "ecb5fa...", "internalipaddress": "192.168.1.100", "port": 443}]
```

**Methode 4 – Manuell:**
IP in `config.toml` eintragen. Für stabile Heimnetzwerke empfohlen (DHCP-Reservierung im Router).

Die erkannte IP wird im Cache persistiert und bei erneutem Start direkt genutzt.

---

## 2. Architektur

### 2.1 Paketstruktur

```
huehub-py/
│
├── hue_local/
│   ├── __init__.py
│   ├── client.py              # HueBridgeClient – zentrale High-Level-API
│   ├── config.py              # Config-Laden, TOML, Env-Overrides, Pfade
│   ├── models.py              # Frozen Dataclasses: Light, Room, Scene, Sensor, ...
│   ├── exceptions.py          # BridgeUnavailableError, AuthError, ResourceNotFound, ...
│   ├── color.py               # Farbkonvertierung: RGB/HEX/HSB/Kelvin ↔ CIE xy / mirek
│   ├── discovery.py           # mDNS + discovery.meethue.com Fallback
│   ├── tls.py                 # Zertifikat-Extraktion und -Verwaltung
│   ├── cache.py               # Resource-Cache (~/.cache/huehub-local/<bridge-id>/)
│   ├── protocol/
│   │   ├── __init__.py
│   │   ├── rest.py            # HTTPS REST-Client (httpx)
│   │   └── sse.py             # SSE Event-Stream (httpx-sse oder aiohttp)
│   ├── cli.py                 # Typer/Rich CLI
│   ├── mcp_server.py          # MCP Tools und Ressourcen
│   └── simulator.py           # Fake Bridge für Tests
│
├── tests/
│   ├── unit/
│   │   ├── test_color.py
│   │   ├── test_models.py
│   │   └── test_cache.py
│   ├── integration/
│   │   └── test_real_bridge.py  # opt-in via HUE_BRIDGE_HOST env
│   └── conftest.py              # Simulator-Fixtures
│
├── docs/
│   ├── protocol.md
│   ├── color.md
│   └── troubleshooting.md
│
└── pyproject.toml
```

### 2.2 Konfigurationspfade

| Zweck | Pfad |
|-------|------|
| Benutzerkonfiguration | `~/.config/huehub-local/config.toml` (Linux/macOS) |
| | `%APPDATA%\huehub-local\config.toml` (Windows) |
| Resource-Cache | `~/.cache/huehub-local/<bridge-id>/resources.json` |
| TLS-Zertifikat | `~/.cache/huehub-local/<bridge-id>/bridge.pem` |

### 2.3 Konfigurationsdatei (TOML)

```toml
[bridge]
host = "192.168.178.42"
application_key = "KyBPfHmVUGSJNBr0Je5GwJzeRc6PXpsYfZki1IRl"
api_version = "2"              # Gecacht nach erstem Verbindungsaufbau
# bridge_id wird automatisch erkannt und gecacht

[tls]
mode = "auto"          # auto | verify | skip
# auto: versucht gespeichertes bridge.pem, fällt auf skip zurück
# verify: verwendet bridge.pem (extrahiert via `hue setup`)
# skip: kein TLS-Check (Warnung)

[connection]
request_timeout_s = 10
sse_reconnect_delay_s = 2
sse_reconnect_max_s = 60

[discovery]
mdns_timeout_s = 5
use_cloud_fallback = true        # discovery.meethue.com als Fallback
use_hostname_fallback = true     # Philips-hue.local als Fallback
subnet_scan = false              # Langsamer Subnetz-Scan, standardmäßig aus

[cache]
ttl_seconds = 300      # 5 Minuten Resource-Cache

[color]
default_transition_ms = 400   # Standardübergangszeit bei Farbwechseln

# Nutzerdefinierte Farbpresets (überschreiben eingebaute Benennungen)
[colors]
abendrot = "#FF4500"
büro = "5000K"
lesen = "4000K"
kino = "#1A1A2E"
```

**Konfigurationspriorität:** CLI-Argument > Umgebungsvariable > Config-Datei > Default

```bash
HUE_BRIDGE_HOST=192.168.178.42
HUE_APPLICATION_KEY=KyBPfHmVUGSJNBr0Je5GwJzeRc6PXpsYfZki1IRl
HUE_TLS_MODE=skip
HUE_CONFIG_DIR=/custom/path/to/config   # Überschreibt Standard-Konfigurationspfad
```

---

## 3. Datenmodelle

```python
@dataclass(frozen=True)
class BridgeInfo:
    host: str
    bridge_id: str                  # z.B. "ecb5fa..."
    model_id: str | None
    api_version: str | None
    software_version: str | None
    name: str | None

@dataclass(frozen=True)
class Light:
    id: str                         # UUID
    name: str
    is_on: bool
    is_reachable: bool
    brightness: float | None        # 0.0–100.0
    color_xy: tuple[float, float] | None   # CIE xy
    color_temp_mirek: int | None    # 153–500
    color_mode: str | None          # "color" | "color_temperature" | "brightness"
    effects_available: list[str]
    device_id: str                  # Parent device UUID
    archetype: str | None           # "sultan_bulb", "floor_shade", etc.

@dataclass(frozen=True)
class Room:
    id: str
    name: str
    grouped_light_id: str           # UUID der zugehörigen grouped_light
    device_ids: list[str]
    light_ids: list[str]            # Konvenience: direkt alle Light-UUIDs

@dataclass(frozen=True)
class Zone:
    id: str
    name: str
    grouped_light_id: str
    light_ids: list[str]

@dataclass(frozen=True)
class GroupedLight:
    id: str
    is_on: bool | None              # None wenn gemischt
    brightness: float | None
    # Referenz auf Room oder Zone
    owner_type: str                 # "room" | "zone" | "bridge_home"
    owner_id: str

@dataclass(frozen=True)
class Scene:
    id: str
    name: str
    group_id: str                   # Room- oder Zone-UUID
    group_type: str                 # "room" | "zone"
    is_active: bool
    speed: float | None             # Dynamik-Geschwindigkeit

@dataclass(frozen=True)
class Device:
    id: str
    name: str
    model_id: str | None
    manufacturer: str | None
    product_name: str | None
    archetype: str | None
    services: list[dict]            # Referenzen auf Light, Button, Motion, etc.

@dataclass(frozen=True)
class MotionSensor:
    id: str
    name: str
    is_reachable: bool
    motion_detected: bool
    motion_valid: bool
    sensitivity: int | None
    device_id: str

@dataclass(frozen=True)
class TemperatureSensor:
    id: str
    name: str
    is_reachable: bool
    temperature_celsius: float | None
    temperature_valid: bool
    device_id: str

@dataclass(frozen=True)
class LightLevelSensor:
    id: str
    name: str
    is_reachable: bool
    light_level_lux: int | None
    light_level_valid: bool
    device_id: str

@dataclass(frozen=True)
class ContactSensor:
    id: str
    name: str
    is_reachable: bool
    contact: bool | None            # True = geschlossen, False = offen
    device_id: str

@dataclass(frozen=True)
class EntertainmentZone:
    id: str
    name: str
    configuration_id: str
    light_ids: list[str]
    status: str | None              # "active" | "inactive"

@dataclass(frozen=True)
class HueEvent:
    type: str                       # "update" | "add" | "delete" | "error"
    resource_type: str              # "light", "grouped_light", "motion", etc.
    resource_id: str
    data: dict
    timestamp: str

@dataclass(frozen=True)
class ColorResult:
    """Ergebnis einer Farbkonvertierung mit allen Repräsentationen"""
    xy: tuple[float, float]
    mirek: int | None
    rgb: tuple[int, int, int] | None
    hex_str: str | None
```

---

## 4. Farbkonvertierung (`color.py`)

Da der Hue Hub intern mit CIE xy-Koordinaten arbeitet, ist eine robuste Farbkonvertierung essenziell:

```python
# Alle Konvertierungen
def rgb_to_xy(r: int, g: int, b: int) -> tuple[float, float]: ...
def hex_to_xy(hex_color: str) -> tuple[float, float]: ...
def kelvin_to_mirek(kelvin: int) -> int: ...      # z.B. 4000K → 250 mirek
def mirek_to_kelvin(mirek: int) -> int: ...
def xy_to_rgb(x: float, y: float, brightness: float = 1.0) -> tuple[int, int, int]: ...

# Gamut-Korrektur (Hue-Leuchten haben eingeschränkten Farbraum)
def clamp_to_gamut(x: float, y: float, gamut: str = "C") -> tuple[float, float]: ...
# Gamut A (ältere Leuchten), B (Hue Living Colors), C (aktuell)
```

**Unterstützte Eingabeformate in CLI/MCP:**
- RGB: `255,128,0` oder `rgb(255,128,0)`
- HEX: `#FF8000` oder `FF8000`
- Kelvin: `3000K` oder `3000`
- Mirek: `333mirek`
- Benannte Farben: `warm`, `cool`, `daylight`, `candlelight`

---

## 5. Core Client API

```python
class HueBridgeClient:
    async def connect(self) -> None: ...
    async def close(self) -> None: ...

    # Bridge-Informationen
    async def get_bridge_info(self) -> BridgeInfo: ...

    # Ressourcen-Überblick
    async def get_all_resources(self, refresh: bool = False) -> AllResources: ...

    # Lichter
    async def list_lights(self) -> list[Light]: ...
    async def get_light(self, light: str) -> Light: ...           # Name oder UUID
    async def set_light(
        self,
        light: str,                           # Name oder UUID
        *,
        on: bool | None = None,
        brightness: float | None = None,      # 0.0–100.0
        color: str | None = None,             # RGB/HEX/Kelvin/Name
        transition_ms: int | None = None,
        effect: str | None = None,
        alert: str | None = None,
    ) -> LightResult: ...
    async def turn_on(self, light: str, **kwargs) -> LightResult: ...
    async def turn_off(self, light: str, **kwargs) -> LightResult: ...

    # Räume
    async def list_rooms(self) -> list[Room]: ...
    async def get_room(self, room: str) -> Room: ...
    async def set_room(self, room: str, **kwargs) -> GroupedLightResult: ...

    # Zonen
    async def list_zones(self) -> list[Zone]: ...
    async def get_zone(self, zone: str) -> Zone: ...
    async def set_zone(self, zone: str, **kwargs) -> GroupedLightResult: ...

    # Szenen
    async def list_scenes(self, group: str | None = None) -> list[Scene]: ...
    async def activate_scene(self, scene: str, group: str | None = None) -> None: ...

    # Geräte
    async def list_devices(self) -> list[Device]: ...
    async def get_device(self, device: str) -> Device: ...

    # Sensoren
    async def list_motion_sensors(self) -> list[MotionSensor]: ...
    async def list_temperature_sensors(self) -> list[TemperatureSensor]: ...
    async def list_light_level_sensors(self) -> list[LightLevelSensor]: ...
    async def list_contact_sensors(self) -> list[ContactSensor]: ...

    # Entertainment
    async def list_entertainment_zones(self) -> list[EntertainmentZone]: ...

    # Alle Lichter aus
    async def all_off(self) -> None: ...

    # Event-Stream
    async def listen(self) -> AsyncIterator[HueEvent]: ...
```

---

## 6. CLI-Interface

Technologie: **Typer** + **Rich**

```bash
# Setup und Discovery
hue discover                              # mDNS + discovery.meethue.com
hue setup --host 192.168.178.42          # TLS-Zertifikat extrahieren + App-Key registrieren
hue authenticate --host 192.168.178.42   # Nur App-Key registrieren (Link-Button drücken!)
hue info [--host <ip>]                    # Bridge-Informationen
hue doctor                               # Diagnose: TLS / Auth / API / SSE

# Lichter
hue lights list
hue lights list --room "Wohnzimmer"
hue light on "Stehlampe"
hue light off "Stehlampe"
hue light set "Stehlampe" --brightness 75
hue light set "Stehlampe" --color "#FF8000"
hue light set "Stehlampe" --color "3000K"
hue light set "Stehlampe" --color warm
hue light set "Stehlampe" --brightness 50 --transition 2000
hue light set "Stehlampe" --effect candle
hue light show "Stehlampe"              # Aktuellen State anzeigen

# Räume
hue rooms list
hue room on "Wohnzimmer"
hue room off "Wohnzimmer"
hue room set "Wohnzimmer" --brightness 80 --color "4000K"
hue room show "Wohnzimmer"

# Zonen
hue zones list
hue zone on "Erdgeschoss"
hue zone off "Erdgeschoss"
hue zone set "Erdgeschoss" --brightness 60

# Szenen
hue scenes list [--room "Wohnzimmer"]
hue scene activate "Entspannen" [--room "Wohnzimmer"]

# Geräte
hue devices list

# Sensoren
hue sensors list                          # Alle Sensoren
hue sensors motion                        # Bewegungssensoren mit aktuellem Status
hue sensors temperature                   # Temperatursensoren
hue sensors light-level                   # Lichtstärkesensoren
hue sensors contact                       # Tür-/Fenstersensoren

# Alle Lichter aus
hue all-off

# Event-Stream beobachten
hue listen [--type light] [--type grouped_light]

# Direkter API-Zugriff (Debugging)
hue api get /clip/v2/resource/light
hue api put /clip/v2/resource/light/<id> --body '{"on":{"on":true}}'
```

### CLI-Designregeln

- `--host` und `--key` überschreiben Config-Datei.
- `--json` für maschinenlesbare Ausgabe.
- **Alle Logs auf `stderr`** – stdout nur für Ausgaben.
- Licht/Raum/Zone per **Name oder UUID** adressierbar (fuzzy match bei Namen).
- Fehler bei Mehrdeutigkeit: Kandidatenliste ausgeben.

### CLI Exit-Codes

| Code | Bedeutung |
|------|-----------|
| `0` | Erfolg |
| `2` | Usage-/Validierungsfehler |
| `10` | Bridge nicht erreichbar |
| `11` | TLS-Fehler |
| `12` | Authentifizierungsfehler (ungültiger App-Key) |
| `13` | Ressource nicht gefunden |
| `14` | Ressource mehrdeutig (Name-Match) |
| `15` | Link-Button nicht gedrückt (bei Setup) |

---

## 7. MCP-Server

Technologie: **Offizielles MCP Python SDK** (`mcp`).
Default-Transport: **stdio**.

### 7.1 MCP Tools

| Tool | Beschreibung |
|------|-------------|
| `hue_get_bridge_info` | Bridge-Informationen |
| `hue_list_lights` | Alle Lichter (optional gefiltert nach Raum) |
| `hue_get_light` | Einzelne Leuchte mit vollständigem Status (per Name oder UUID) |
| `hue_set_light` | Licht steuern (an/aus, Helligkeit, Farbe, Effekt) |
| `hue_set_light_color_temp` | Farbtemperatur gezielt setzen (Kelvin oder Mirek) |
| `hue_list_rooms` | Alle Räume |
| `hue_set_room_on` | Raum ein-/ausschalten |
| `hue_set_room` | Raum steuern (Helligkeit, Farbe) |
| `hue_list_zones` | Alle Zonen |
| `hue_set_zone` | Zone steuern |
| `hue_list_scenes` | Szenen (optional nach Raum gefiltert) |
| `hue_activate_scene` | Szene aktivieren |
| `hue_list_devices` | Alle Geräte |
| `hue_list_motion_sensors` | Bewegungssensoren mit aktuellem Status |
| `hue_list_temperature_sensors` | Temperatursensoren mit Messwerten |
| `hue_list_light_level_sensors` | Lichtstärkesensoren mit Lux-Werten |
| `hue_list_contact_sensors` | Tür-/Fenstersensoren mit aktuellem Zustand |
| `hue_all_off` | Alle Lichter ausschalten |
| `hue_refresh_resources` | Cache neu laden |

```python
@mcp.tool()
async def hue_set_light(
    light: str,                  # Name oder UUID
    on: bool | None = None,
    brightness: float | None = None,   # 0.0–100.0
    color: str | None = None,          # "#FF8000" | "3000K" | "warm"
    transition_ms: int | None = None,
    effect: str | None = None,         # "candle" | "fire" | etc.
) -> dict: ...

@mcp.tool()
async def hue_set_light_color_temp(
    light: str,                  # Name oder UUID
    color_temp: str | int,       # z.B. "3000K", "4000K", 300 (mirek)
    brightness: float | None = None,
    transition_ms: int | None = None,
) -> dict: ...

@mcp.tool()
async def hue_set_room_on(
    room: str,                   # Name oder UUID
    on: bool,
) -> dict: ...

@mcp.tool()
async def hue_activate_scene(
    scene: str,                  # Name oder UUID
    room: str | None = None,     # Zur Disambiguierung bei gleichnamigen Szenen
) -> dict: ...
```

### 7.2 MCP Resources

| Resource URI | Inhalt |
|---|---|
| `hue://bridge` | Bridge-Info |
| `hue://lights` | Alle Lichter mit aktuellem Status |
| `hue://rooms` | Alle Räume mit Lichtern |
| `hue://zones` | Alle Zonen |
| `hue://scenes` | Alle Szenen |
| `hue://devices` | Alle Geräte |
| `hue://sensors` | Alle Sensoren (Motion, Temperature, LightLevel, Contact) |

### 7.3 Claude Desktop Integration

```json
// ~/.claude/claude_desktop_config.json
{
  "mcpServers": {
    "hue": {
      "command": "hue-mcp",
      "args": [],
      "env": {
        "HUE_BRIDGE_HOST": "192.168.178.42",
        "HUE_APPLICATION_KEY": "KyBPfHmVUGSJNBr0Je5GwJzeRc6PXpsYfZki1IRl",
        "HUE_TLS_MODE": "skip"
      }
    }
  }
}
```

### 7.4 MCP-Sicherheitsregeln

- Kein Logging auf stdout.
- Application Key nicht in Tool-Antworten ausgeben.
- Kein `0.0.0.0`-Binding im stdio-Modus.

---

## 8. Implementierungsphasen

### Phase 0 – Projekt-Setup

| # | Aufgabe | Details |
|---|---------|---------|
| 0.1 | Repository + `pyproject.toml` | Python ≥ 3.11, Entry Points |
| 0.2 | Paketstruktur anlegen | Alle Module als leere Dateien mit Docstrings |
| 0.3 | Tooling konfigurieren | `ruff`, `mypy`, `pytest`, `pytest-asyncio` |
| 0.4 | Config-Pfade implementieren | XDG-konform, plattformübergreifend |
| 0.5 | Entry Points prüfen | `hue --help`, `hue-mcp --help` |

**Akzeptanzkriterium:** `pip install -e .` funktioniert, `pytest` läuft fehlerfrei.

### Phase 1 – TLS und Zertifikat-Verwaltung

| # | Aufgabe | Details |
|---|---------|---------|
| 1.1 | `tls.py` – Zertifikat extrahieren | `openssl s_client` via subprocess oder `ssl`-Modul |
| 1.2 | Zertifikat persistieren | In `~/.cache/huehub-local/<bridge-id>/bridge.pem` |
| 1.3 | TLS-Modi implementieren | `auto`, `verify`, `skip` |
| 1.4 | `httpx.AsyncClient` konfigurieren | Mit custom CA oder `verify=False` |
| 1.5 | TLS-Fehlerklassen | `TlsError`, `CertificateError` |

**Akzeptanzkriterium:** `hue setup --host <ip>` extrahiert das Zertifikat und speichert es. `hue doctor` meldet TLS-Status.

### Phase 2 – Registrierung und Authentifizierung

| # | Aufgabe | Details |
|---|---------|---------|
| 2.1 | `POST /api` implementieren | Link-Button-Flow mit Retry-Schleife |
| 2.2 | Link-Button-Prompt | CLI wartet 30s, prüft alle 2s |
| 2.3 | App-Key in Config speichern | Automatisch in `config.toml` schreiben |
| 2.4 | Auth-Header | `hue-application-key` bei allen Requests |
| 2.5 | `hue authenticate` CLI-Command | Separater Command (ohne TLS-Setup), für Re-Auth |
| 2.6 | Fehlerklassen | `AuthError`, `LinkButtonNotPressedError` |

**Akzeptanzkriterium:** `hue setup --host <ip>` führt vollständig durch: TLS → Link-Button → App-Key → gespeichert.

### Phase 3 – REST-Client und Resource-Abruf

| # | Aufgabe | Details |
|---|---------|---------|
| 3.1 | `protocol/rest.py` | `get()`, `put()`, `post()`, `delete()` mit Auth-Header |
| 3.2 | Response-Parsing | `data`-Array extrahieren, `errors` prüfen |
| 3.3 | `GET /clip/v2/resource` | Alle Ressourcen in einem Aufruf |
| 3.4 | Einzelne Typen | `list_lights()`, `list_rooms()`, `list_zones()`, `list_scenes()`, `list_devices()` |
| 3.5 | `cache.py` | Resource-Cache mit TTL, invalidierbar |
| 3.6 | Name-zu-UUID-Resolver | Fuzzy-Match auf `name`-Felder, `AmbiguousNameError` |

**Akzeptanzkriterium:** `hue lights list`, `hue rooms list`, `hue scenes list` zeigen korrekte Daten.

### Phase 4 – Licht- und Gruppensteuerung

| # | Aufgabe | Details |
|---|---------|---------|
| 4.1 | `set_light()` | PUT auf `/clip/v2/resource/light/{id}` |
| 4.2 | `set_room()` / `set_zone()` | PUT auf `/clip/v2/resource/grouped_light/{id}` |
| 4.3 | `turn_on()` / `turn_off()` | `{"on": {"on": true/false}}` |
| 4.4 | Helligkeit | `{"dimming": {"brightness": n}}` |
| 4.5 | Dynamik / Übergangszeit | `{"dynamics": {"duration": ms}}` |
| 4.6 | Effekte | `{"effects": {"effect": "candle"}}` |
| 4.7 | Alert | `{"alert": {"action": "breathe"}}` |
| 4.8 | `all_off()` | Bridge-Home `grouped_light` steuern |

**Akzeptanzkriterium:** `hue light on "Stehlampe"`, `hue room set "Wohnzimmer" --brightness 80` funktionieren.

### Phase 5 – Farbkonvertierung

| # | Aufgabe | Details |
|---|---------|---------|
| 5.1 | `color.py` – RGB → CIE xy | Mit Gamut-Korrektur |
| 5.2 | HEX-Parser | `#RRGGBB` und `RRGGBB` |
| 5.3 | Kelvin → mirek | Validierung: 1000–10000K → 100–1000 mirek |
| 5.4 | Benannte Farben | `warm` (2700K), `cool` (4000K), `daylight` (6500K), etc. |
| 5.5 | CIE xy → RGB | Für Statusanzeige |
| 5.6 | Gamut-Clamping | Gamut A/B/C je nach Leuchtmittel |

**Akzeptanzkriterium:** `hue light set "Lampe" --color "#FF8000"`, `--color "3000K"`, `--color warm` funktionieren korrekt.

### Phase 6 – Szenen

| # | Aufgabe | Details |
|---|---------|---------|
| 6.1 | `list_scenes()` | Optional nach Raum/Zone filtern |
| 6.2 | `activate_scene()` | `PUT` mit `{"recall": {"action": "active"}}` |
| 6.3 | Name-Disambiguation | Gleiche Szenenname in verschiedenen Räumen → Fehler mit Kandidaten |

**Akzeptanzkriterium:** `hue scene activate "Entspannen" --room "Wohnzimmer"` funktioniert.

### Phase 7 – SSE Event-Stream

| # | Aufgabe | Details |
|---|---------|---------|
| 7.1 | `protocol/sse.py` | `GET /eventstream/clip/v2` via `httpx-sse` |
| 7.2 | Event-Parsing | JSON-Payload → `HueEvent`-Objekte |
| 7.3 | `listen()` | `AsyncIterator[HueEvent]` |
| 7.4 | Auto-Reconnect | Exponential Backoff bei Verbindungsabbruch |
| 7.5 | Rate-Limit beachten | 1 Event-Batch/Sekunde, nicht pollen |

**Akzeptanzkriterium:** `hue listen` zeigt Live-Events. Lichtstatus-Änderungen über die App erscheinen in Echtzeit.

### Phase 8 – CLI

| # | Aufgabe | Details |
|---|---------|---------|
| 8.1 | Typer-App strukturieren | Subcommands, Global-Options |
| 8.2 | `hue setup` / `hue discover` | TLS + Auth-Flow, mDNS |
| 8.3 | `hue doctor` | TLS → Auth → REST → SSE → Cache |
| 8.4 | Alle Light/Room/Zone/Scene-Commands | Siehe CLI-Interface-Abschnitt |
| 8.5 | `hue api` | Direkter API-Zugriff für Debugging |
| 8.6 | `hue listen` | Event-Stream-Ausgabe |
| 8.7 | Exit-Codes | 0 / 2 / 10–15 |
| 8.8 | Rich-Output | Tabellen, Farb-Vorschau (ANSI), JSON-Flag |

**Akzeptanzkriterium:** Alle Funktionen per CLI, `--json` funktioniert überall, `hue doctor` gibt Pass/Fail-Diagnose.

### Phase 9 – MCP-Server

| # | Aufgabe | Details |
|---|---------|---------|
| 9.1 | `mcp_server.py` | Offizielles MCP Python SDK, `HueBridgeClient`-Singleton |
| 9.2 | STDIO-Transport | Default |
| 9.3 | Alle Tools implementieren | Siehe Abschnitt 7.1 |
| 9.4 | Alle Resources implementieren | `hue://lights`, `hue://rooms`, etc. |
| 9.5 | Kein stdout-Logging | `logging` → stderr |

**Akzeptanzkriterium:** MCP Inspector listet und ruft alle Tools auf. Claude Desktop kann Lichter schalten.

### Phase 10 – Tests

**Ziel:** 80%+ Testabdeckung ohne echten Hub, opt-in Integrationstests.

| # | Aufgabe | Details |
|---|---------|---------|
| 10.1 | `simulator.py` | Fake Bridge: HTTPS-Server (Test-Cert) + SSE-Endpoint |
| 10.2 | Simulator-Fixtures | Konfigurierbare Lights/Rooms/Scenes/Sensors, Event-Emitter |
| 10.3 | `test_color.py` | RGB-xy, Kelvin-mirek, Gamut-Clamping, Benannte Farben |
| 10.4 | `test_models.py` | Dataclass-Validierung, Sensor-Parsing, ColorResult |
| 10.5 | `test_client.py` | Client-Logik mit gemocktem HTTP, Name-Resolver, Sensor-Methoden |
| 10.6 | `test_config.py` | TOML-Laden, Env-Overrides, HUE_CONFIG_DIR, Plattformpfade |
| 10.7 | `test_discovery.py` | mDNS (gemocktes zeroconf), Hostname-Fallback, Cloud-Fallback |
| 10.8 | `test_cli_commands.py` | Typer-Testclient, Ausgabe-Snapshots, Exit-Codes |
| 10.9 | `test_mcp_tools.py` | Alle 19 MCP-Tools mit SDK-Testclient |
| 10.10 | `test_real_bridge.py` | HUE_BRIDGE_HOST=... pytest -m integration (opt-in) |

**Akzeptanzkriterium:** 80%+ Coverage. Kein echter Hub fuer CI. Integration opt-in und zerstoerungsarm.

### Phase 11 – Dokumentation

| # | Aufgabe | Details |
|---|---------|---------|
| 11.1 | `README.md` | Installation, Setup-Flow, CLI-Beispiele, MCP-Einrichtung |
| 11.2 | `docs/protocol.md` | CLIP v2 Endpoints, Request/Response-Beispiele |
| 11.3 | `docs/color.md` | Farbräume, Gamut-Erklärung, Konvertierungstabellen |
| 11.4 | `docs/troubleshooting.md` | TLS-Fehler, Link-Button, App-Key ungültig, SSE-Verbindung |

---

## 9. Abhängigkeiten

```toml
[project]
name = "huehub-py"
requires-python = ">=3.11"

dependencies = [
    "httpx>=0.27",           # Async HTTPS REST-Client
    "httpx-sse>=0.4",        # SSE über httpx
    "mcp>=1.0",              # Offizielles MCP Python SDK
    "typer[all]>=0.12",      # CLI mit Rich-Output
    "pydantic>=2.0",         # Datenmodelle & Validierung
    "zeroconf>=0.131",       # mDNS-Discovery (_hue._tcp.local)
    "platformdirs>=4.0",     # Plattformübergreifende Config-/Cache-Pfade
    # tomllib in stdlib ab Python 3.11
]

[tool.pytest.ini_options]
asyncio_mode = "auto"

[project.scripts]
hue = "hue_local.cli:app"
hue-mcp = "hue_local.mcp_server:main"
```

**Dokumentations-Konvention:** Alle öffentlichen Methoden und Klassen verwenden **Google-Style Docstrings**.

```python
async def set_light(self, light: str, *, brightness: float | None = None) -> LightResult:
    """Steuert eine einzelne Leuchte.

    Args:
        light: Name oder UUID der Leuchte.
        brightness: Helligkeit in Prozent (0.0–100.0).

    Returns:
        LightResult mit dem neuen Zustand der Leuchte.

    Raises:
        ResourceNotFoundError: Wenn keine Leuchte mit diesem Namen/UUID existiert.
        AmbiguousNameError: Wenn mehrere Leuchten den Namen tragen.
    """
```

---

## 10. Risiken und Gegenmaßnahmen

| Risiko | Auswirkung | Gegenmaßnahme |
|--------|------------|---------------|
| TLS-Zertifikat-Mismatch | Verbindung schlägt fehl | `tls.mode = skip` als Fallback; klare Fehlermeldung |
| App-Key ungültig (Bridge-Reset) | 401 Unauthorized | Klare Fehlermeldung: `hue setup` erneut ausführen |
| Ressourcen-Name mehrdeutig | Falsches Gerät gesteuert | `AmbiguousNameError` mit Kandidatenliste; UUID als sichere Alternative |
| Farbgamut überschritten | Farbe wird verfälscht | Gamut-Clamping + Hinweis in Ausgabe |
| SSE-Verbindung fällt ab | Verpasste Events | Auto-Reconnect mit Exponential Backoff + Resync per REST |
| Bridge-Verbindungslimit (~3) | SSE belegt einen Slot | Dokumentieren, SSE optional halten |
| API-Versionierung | Neue Bridge-Firmware ändert Response-Felder | Pydantic-Validierung mit optionalen Feldern, robustes Parsing |
| App-Key in Logs | Datenschutzproblem | Key nur aus Config laden, nie in Logs oder MCP-Antworten |

---

## 11. MVP-Scope

**Im MVP enthalten:**

1. Manuelle Bridge-IP + App-Key in Config
2. TLS-Zertifikat-Extraktion und -Verwaltung (`hue setup`)
3. App-Key-Registrierung via Link-Button-Flow (`hue authenticate`)
4. Lichter: listen, an/aus, Helligkeit, Farbe (RGB/HEX/Kelvin/Preset), Effekte
5. Räume: listen, steuern (Helligkeit, Farbe, an/aus)
6. Zonen: listen, steuern
7. Szenen: listen, aktivieren
8. Geräte: listen
9. Sensoren: Motion, Temperature, LightLevel, Contact (nur lesen)
10. `all_off()`
11. CLI für alle MVP-Funktionen inkl. `hue doctor` und `hue authenticate`
12. MCP STDIO Server mit allen 19 Kern-Tools + Resources inkl. `hue://sensors`
13. Simulator für Tests ohne Bridge

**Nicht im MVP:**

- mDNS-Discovery (manuelle IP reicht)
- SSE Event-Stream (REST-Polling als Alternative)
- Entertainment API (UDP-Streaming für Sync)
- Sensoren (Motion, Temperature, Contact)
- Szenen erstellen/bearbeiten
- Räume/Zonen erstellen/bearbeiten
- Smart Scenes (dynamisch)
- HTTP/2 Multiplexing

---

## 12. Beispiel-Nutzung (Library)

```python
import asyncio
from hue_local import HueBridgeClient

async def main():
    async with HueBridgeClient("192.168.178.42") as hue:
        # Bridge-Info
        info = await hue.get_bridge_info()
        print(f"Bridge: {info.name} (ID: {info.bridge_id})")

        # Lichter auflisten
        lights = await hue.list_lights()
        for light in lights:
            status = "an" if light.is_on else "aus"
            print(f"  - {light.name}: {status}, {light.brightness:.0f}%")

        # Einzelne Leuchte steuern
        await hue.turn_on("Stehlampe", brightness=60, color="3000K")
        await asyncio.sleep(1)

        # Farbe wechseln
        await hue.set_light("Stehlampe", color="#FF4500", transition_ms=1000)
        await asyncio.sleep(2)

        # Raum steuern
        await hue.set_room("Wohnzimmer", brightness=80, color="daylight")

        # Szene aktivieren
        await hue.activate_scene("Entspannen", room="Wohnzimmer")

        # Event-Stream kurz beobachten
        async with asyncio.timeout(10):
            async for event in hue.listen():
                print(f"Event: {event.resource_type}/{event.resource_id} → {event.type}")

        # Alles aus
        await hue.all_off()

asyncio.run(main())
```
---

*Erstellt: Mai 2026 | Protokoll-Grundlage: Philips Hue CLIP API v2 (Port 443, HTTPS)*
