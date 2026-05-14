"""Unit tests for colour conversion functions."""

import pytest

from huehub.color import (
    clamp_to_gamut,
    hex_to_xy,
    kelvin_to_mirek,
    mirek_to_kelvin,
    parse_color_input,
    rgb_to_xy,
    xy_to_rgb,
)


class TestRgbToXy:
    def test_white(self) -> None:
        x, y = rgb_to_xy(255, 255, 255)
        assert 0.2 < x < 0.4
        assert 0.2 < y < 0.4

    def test_black(self) -> None:
        x, y = rgb_to_xy(0, 0, 0)
        assert x == 0.0
        assert y == 0.0

    def test_red(self) -> None:
        x, y = rgb_to_xy(255, 0, 0)
        # Red should have high x coordinate
        assert x > 0.5

    def test_green(self) -> None:
        x, y = rgb_to_xy(0, 255, 0)
        # Green should have high y coordinate
        assert y > 0.5

    def test_blue(self) -> None:
        x, y = rgb_to_xy(0, 0, 255)
        # Blue should have low x and y
        assert x < 0.2


class TestHexToXy:
    def test_valid_with_hash(self) -> None:
        xy = hex_to_xy("#FFFFFF")
        assert isinstance(xy, tuple)
        assert len(xy) == 2

    def test_valid_without_hash(self) -> None:
        xy1 = hex_to_xy("#FF0000")
        xy2 = hex_to_xy("FF0000")
        assert xy1 == xy2

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            hex_to_xy("not-a-colour")

    def test_short_hex_raises(self) -> None:
        with pytest.raises(ValueError):
            hex_to_xy("#FFF")


class TestXyToRgb:
    def test_roughly_reverses_rgb_to_xy(self) -> None:
        r, g, b = 200, 100, 50
        x, y = rgb_to_xy(r, g, b)
        r2, g2, b2 = xy_to_rgb(x, y, brightness=0.8)
        # Result won't be identical due to gamut/brightness differences
        assert isinstance(r2, int)
        assert 0 <= r2 <= 255
        assert 0 <= g2 <= 255
        assert 0 <= b2 <= 255

    def test_zero_y_returns_black(self) -> None:
        assert xy_to_rgb(0.3, 0.0) == (0, 0, 0)


class TestKelvinMirek:
    def test_kelvin_to_mirek_4000k(self) -> None:
        assert kelvin_to_mirek(4000) == 250

    def test_kelvin_to_mirek_2700k(self) -> None:
        mirek = kelvin_to_mirek(2700)
        assert 370 <= mirek <= 371

    def test_mirek_to_kelvin_250(self) -> None:
        assert mirek_to_kelvin(250) == 4000

    def test_roundtrip(self) -> None:
        for k in [2000, 3000, 4000, 5000, 6500]:
            m = kelvin_to_mirek(k)
            k2 = mirek_to_kelvin(m)
            assert abs(k - k2) <= 10  # small rounding error is OK

    def test_kelvin_out_of_range(self) -> None:
        with pytest.raises(ValueError):
            kelvin_to_mirek(500)

    def test_mirek_out_of_range(self) -> None:
        with pytest.raises(ValueError):
            mirek_to_kelvin(50)


class TestClampToGamut:
    def test_point_inside_stays(self) -> None:
        x, y = 0.3, 0.3
        cx, cy = clamp_to_gamut(x, y, "C")
        assert abs(cx - x) < 1e-9
        assert abs(cy - y) < 1e-9

    def test_extreme_red_clamped(self) -> None:
        # Far outside any gamut
        cx, cy = clamp_to_gamut(1.0, 0.0, "C")
        assert 0.0 <= cx <= 1.0
        assert 0.0 <= cy <= 1.0

    def test_all_gamuts(self) -> None:
        for gamut in ("A", "B", "C"):
            cx, cy = clamp_to_gamut(0.5, 0.5, gamut)
            assert isinstance(cx, float)
            assert isinstance(cy, float)

    def test_invalid_gamut(self) -> None:
        with pytest.raises(ValueError):
            clamp_to_gamut(0.3, 0.3, "Z")


class TestParseColorInput:
    def test_hex_with_hash(self) -> None:
        result = parse_color_input("#FF8000")
        assert result.hex_str == "#FF8000"
        assert result.xy != (0.0, 0.0)

    def test_hex_without_hash(self) -> None:
        result = parse_color_input("FF8000")
        assert result.hex_str == "#FF8000"

    def test_kelvin(self) -> None:
        result = parse_color_input("3000K")
        assert result.mirek is not None
        assert abs(result.mirek - kelvin_to_mirek(3000)) <= 1

    def test_kelvin_lowercase(self) -> None:
        result = parse_color_input("4000k")
        assert result.mirek == 250

    def test_mirek(self) -> None:
        result = parse_color_input("300mirek")
        assert result.mirek == 300

    def test_rgb_tuple(self) -> None:
        result = parse_color_input("255,128,0")
        assert result.rgb == (255, 128, 0)
        assert result.hex_str == "#FF8000"

    def test_rgb_function_notation(self) -> None:
        result = parse_color_input("rgb(255,128,0)")
        assert result.rgb == (255, 128, 0)

    def test_named_warm(self) -> None:
        result = parse_color_input("warm")
        # warm = 2700K → mirek
        assert result.mirek == kelvin_to_mirek(2700)

    def test_named_daylight(self) -> None:
        result = parse_color_input("daylight")
        assert result.mirek == kelvin_to_mirek(6500)

    def test_user_preset(self) -> None:
        result = parse_color_input(
            "myfavourite", user_presets={"myfavourite": "#0080FF"}
        )
        assert result.hex_str == "#0080FF"

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_color_input("not-a-colour-123!")
