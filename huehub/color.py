"""Colour conversion utilities for the Philips Hue CLIP API v2.

The bridge works internally with CIE 1931 xy chromaticity coordinates and
mirek colour temperature.  This module converts between those and common
representations used in everyday tools (HEX, RGB, Kelvin).

Gamut clamping is applied to keep colours within the physically realisable
range of the lamp's LED technology.
"""

import math
import re

from huehub.models import ColorResult

# ---------------------------------------------------------------------------
# Named colour presets (expandable via [colors] in config.toml)
# ---------------------------------------------------------------------------

_NAMED_COLOURS: dict[str, str] = {
    "warm": "2700K",
    "cool": "4000K",
    "daylight": "6500K",
    "candlelight": "2200K",
    "concentrate": "4000K",
    "relax": "2237K",
    "energize": "6410K",
    "reading": "4085K",
    "white": "6500K",
}

# ---------------------------------------------------------------------------
# Gamut definitions (R, G, B corner xy coordinates)
# ---------------------------------------------------------------------------

_GAMUTS: dict[str, tuple[tuple[float, float], ...]] = {
    "A": (
        (0.704, 0.296),  # R
        (0.2151, 0.7106),  # G
        (0.138, 0.08),  # B
    ),
    "B": (
        (0.675, 0.322),
        (0.409, 0.518),
        (0.167, 0.04),
    ),
    "C": (
        (0.6915, 0.3083),
        (0.17, 0.7),
        (0.1532, 0.0475),
    ),
}

# ---------------------------------------------------------------------------
# Linear RGB / sRGB helpers
# ---------------------------------------------------------------------------


def _gamma_expand(value: float) -> float:
    """Convert sRGB component (0-1) to linear light value."""
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def _gamma_compress(value: float) -> float:
    """Convert linear light value to sRGB component (0-1)."""
    if value <= 0.0:
        return 0.0
    if value <= 0.0031308:
        return 12.92 * value
    return 1.055 * (value ** (1.0 / 2.4)) - 0.055


# ---------------------------------------------------------------------------
# RGB ↔ CIE xy
# ---------------------------------------------------------------------------


def rgb_to_xy(r: int, g: int, b: int) -> tuple[float, float]:
    """Convert sRGB (0–255 each) to CIE 1931 xy chromaticity.

    Uses the Wide RGB D65 matrix recommended by Philips for Hue lamps.

    Args:
        r: Red channel 0–255.
        g: Green channel 0–255.
        b: Blue channel 0–255.

    Returns:
        ``(x, y)`` CIE chromaticity coordinates.
    """
    # Normalise and apply gamma
    rl = _gamma_expand(r / 255.0)
    gl = _gamma_expand(g / 255.0)
    bl = _gamma_expand(b / 255.0)

    # Wide Gamut D65 matrix
    x_xyz = rl * 0.664511 + gl * 0.154324 + bl * 0.162028
    y_xyz = rl * 0.283881 + gl * 0.668433 + bl * 0.047685
    z_xyz = rl * 0.000088 + gl * 0.072310 + bl * 0.986039

    total = x_xyz + y_xyz + z_xyz
    if total == 0.0:
        return (0.0, 0.0)

    return (x_xyz / total, y_xyz / total)


def hex_to_xy(hex_color: str) -> tuple[float, float]:
    """Convert a HEX colour string to CIE 1931 xy.

    Args:
        hex_color: Colour string, e.g. ``"#FF8000"`` or ``"FF8000"``.

    Returns:
        ``(x, y)`` CIE chromaticity coordinates.

    Raises:
        ValueError: If the string is not a valid 6-digit HEX colour.
    """
    h = hex_color.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"Invalid hex colour: {hex_color!r}")
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return rgb_to_xy(r, g, b)


def xy_to_rgb(x: float, y: float, brightness: float = 1.0) -> tuple[int, int, int]:
    """Convert CIE 1931 xy + brightness to sRGB (0–255 each).

    Uses the Wide Gamut D65 inverse matrix.

    Args:
        x: CIE x chromaticity (0.0–1.0).
        y: CIE y chromaticity (0.0–1.0).
        brightness: Relative brightness scalar 0.0–1.0.

    Returns:
        ``(r, g, b)`` sRGB tuple with values 0–255.
    """
    if y == 0.0:
        return (0, 0, 0)

    z = 1.0 - x - y
    y_s = brightness
    x_s = (y_s / y) * x
    z_s = (y_s / y) * z

    # Wide Gamut D65 inverse
    r_l = x_s * 1.656492 - y_s * 0.354851 - z_s * 0.255038
    g_l = -x_s * 0.707196 + y_s * 1.655397 + z_s * 0.036152
    b_l = x_s * 0.051713 - y_s * 0.121364 + z_s * 1.011530

    # Clip negative values
    r_l = max(0.0, r_l)
    g_l = max(0.0, g_l)
    b_l = max(0.0, b_l)

    # Scale to brightest channel = 1.0
    scale = max(r_l, g_l, b_l, 1.0)

    r = round(_gamma_compress(r_l / scale) * 255)
    g = round(_gamma_compress(g_l / scale) * 255)
    b = round(_gamma_compress(b_l / scale) * 255)

    return (
        max(0, min(255, r)),
        max(0, min(255, g)),
        max(0, min(255, b)),
    )


# ---------------------------------------------------------------------------
# Kelvin ↔ mirek
# ---------------------------------------------------------------------------


def kelvin_to_mirek(kelvin: int) -> int:
    """Convert colour temperature in Kelvin to mirek.

    Args:
        kelvin: Colour temperature 1000–10000 K.

    Returns:
        Mirek value (1 000 000 / kelvin), clamped to 100–1000.

    Raises:
        ValueError: If ``kelvin`` is outside 1000–10000.
    """
    if not (1000 <= kelvin <= 10000):
        raise ValueError(f"Kelvin must be 1000–10000, got {kelvin}")
    return max(100, min(1000, round(1_000_000 / kelvin)))


def mirek_to_kelvin(mirek: int) -> int:
    """Convert mirek to colour temperature in Kelvin.

    Args:
        mirek: Mirek value 100–1000.

    Returns:
        Colour temperature in Kelvin.

    Raises:
        ValueError: If ``mirek`` is outside 100–1000.
    """
    if not (100 <= mirek <= 1000):
        raise ValueError(f"Mirek must be 100–1000, got {mirek}")
    return round(1_000_000 / mirek)


# ---------------------------------------------------------------------------
# Gamut clamping
# ---------------------------------------------------------------------------


def _closest_point_on_segment(
    ax: float,
    ay: float,
    bx: float,
    by: float,
    px: float,
    py: float,
) -> tuple[float, float]:
    """Project point P onto segment AB, clamped to [A, B]."""
    ab_x = bx - ax
    ab_y = by - ay
    ap_x = px - ax
    ap_y = py - ay
    ab2 = ab_x * ab_x + ab_y * ab_y
    if ab2 == 0.0:
        return (ax, ay)
    t = max(0.0, min(1.0, (ap_x * ab_x + ap_y * ab_y) / ab2))
    return (ax + t * ab_x, ay + t * ab_y)


def _cross_product_2d(ax: float, ay: float, bx: float, by: float) -> float:
    """2-D cross product of vectors A and B."""
    return ax * by - ay * bx


def _point_in_triangle(
    px: float,
    py: float,
    vertices: tuple[tuple[float, float], ...],
) -> bool:
    """Return True if point (px, py) is inside the gamut triangle."""
    rx, ry = vertices[0]
    gx, gy = vertices[1]
    bx, by = vertices[2]
    c1 = _cross_product_2d(gx - rx, gy - ry, px - rx, py - ry)
    c2 = _cross_product_2d(bx - gx, by - gy, px - gx, py - gy)
    c3 = _cross_product_2d(rx - bx, ry - by, px - bx, py - by)
    return (c1 >= 0 and c2 >= 0 and c3 >= 0) or (c1 <= 0 and c2 <= 0 and c3 <= 0)


def clamp_to_gamut(x: float, y: float, gamut: str = "C") -> tuple[float, float]:
    """Clamp (x, y) to the nearest point inside the lamp gamut triangle.

    Args:
        x: CIE x coordinate.
        y: CIE y coordinate.
        gamut: Gamut letter ``"A"``, ``"B"``, or ``"C"``.

    Returns:
        A ``(x, y)`` tuple guaranteed to lie inside the gamut.

    Raises:
        ValueError: If the gamut letter is not recognised.
    """
    if gamut not in _GAMUTS:
        raise ValueError(f"Unknown gamut {gamut!r}; choose A, B or C")

    vertices = _GAMUTS[gamut]
    if _point_in_triangle(x, y, vertices):
        return (x, y)

    # Find closest point on any edge of the gamut triangle
    candidates: list[tuple[float, float]] = []
    n = len(vertices)
    for i in range(n):
        ax, ay = vertices[i]
        bx, by = vertices[(i + 1) % n]
        candidates.append(_closest_point_on_segment(ax, ay, bx, by, x, y))

    def dist(p: tuple[float, float]) -> float:
        return math.hypot(p[0] - x, p[1] - y)

    return min(candidates, key=dist)


# ---------------------------------------------------------------------------
# Colour input parser
# ---------------------------------------------------------------------------


def parse_color_input(
    color_str: str,
    user_presets: dict[str, str] | None = None,
    gamut: str = "C",
) -> ColorResult:
    """Parse a colour string into a :class:`~huehub.models.ColorResult`.

    Supported formats:
    - HEX: ``"#FF8000"`` or ``"FF8000"``
    - RGB: ``"255,128,0"`` or ``"rgb(255,128,0)"``
    - Kelvin: ``"3000K"`` or ``"3000k"``
    - Mirek: ``"333mirek"`` or ``"333m"``
    - Named: ``"warm"``, ``"cool"``, ``"daylight"``, ``"candlelight"``
    - User presets: any name registered in the ``[colors]`` config section.

    Args:
        color_str: Input colour specification.
        user_presets: Optional dict of ``{name: colour_spec}`` that overrides
            or extends the built-in named colours.
        gamut: Gamut letter used for xy clamping.

    Returns:
        A :class:`~huehub.models.ColorResult` with all available fields.

    Raises:
        ValueError: If the input cannot be parsed.
    """
    s = color_str.strip()

    # Merge presets (user overrides built-ins)
    presets = dict(_NAMED_COLOURS)
    if user_presets:
        presets.update(user_presets)

    # Resolve named colours recursively (one level of indirection)
    lower = s.lower()
    if lower in presets:
        return parse_color_input(presets[lower], gamut=gamut)

    # Mirek  e.g. "333mirek" or "333m"
    m = re.fullmatch(r"(\d+)\s*(?:mirek|m)", s, re.IGNORECASE)
    if m:
        mirek = int(m.group(1))
        kelvin = mirek_to_kelvin(mirek)
        return ColorResult(xy=(0.0, 0.0), mirek=mirek)  # no xy for temp-only

    # Kelvin  e.g. "3000K"
    m = re.fullmatch(r"(\d+)\s*k", s, re.IGNORECASE)
    if m:
        kelvin = int(m.group(1))
        mirek = kelvin_to_mirek(kelvin)
        return ColorResult(xy=(0.0, 0.0), mirek=mirek)

    # HEX  e.g. "#FF8000" or "FF8000"
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", s)
    if m:
        h = m.group(1)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        xy = clamp_to_gamut(*rgb_to_xy(r, g, b), gamut=gamut)
        return ColorResult(
            xy=xy,
            rgb=(r, g, b),
            hex_str=f"#{h.upper()}",
        )

    # RGB  e.g. "255,128,0" or "rgb(255,128,0)"
    m = re.fullmatch(r"(?:rgb\s*\(\s*)?(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)?", s)
    if m:
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        xy = clamp_to_gamut(*rgb_to_xy(r, g, b), gamut=gamut)
        return ColorResult(
            xy=xy,
            rgb=(r, g, b),
            hex_str=f"#{r:02X}{g:02X}{b:02X}",
        )

    raise ValueError(f"Cannot parse colour: {color_str!r}")
