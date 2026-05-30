"""Tests for the drawing format registry (SW-free, pure data)."""

from __future__ import annotations

import pytest

from ai_sw_bridge.drawing.formats import (
    DRAWING_FORMAT_NAMES,
    DRAWING_FORMATS,
    DrawingFormat,
    DrawingMethod,
    resolve_format,
)


class TestDrawingFormats:
    """DRAWING_FORMATS table integrity."""

    def test_all_formats_registered(self) -> None:
        expected = {
            "front",
            "top",
            "right",
            "isometric",
            "dimetric",
            "trimetric",
        }
        assert DRAWING_FORMAT_NAMES == expected

    def test_format_names_frozenset_matches_dict(self) -> None:
        assert DRAWING_FORMAT_NAMES == frozenset(DRAWING_FORMATS)

    def test_every_format_has_view_name(self) -> None:
        for name, fmt in DRAWING_FORMATS.items():
            assert fmt.view_name.startswith("*"), (
                f"{name} view_name should start with * (SW standard view prefix)"
            )

    def test_every_format_has_description(self) -> None:
        for name, fmt in DRAWING_FORMATS.items():
            assert fmt.description, f"{name} has no description"

    def test_formats_are_frozen(self) -> None:
        fmt = DRAWING_FORMATS["front"]
        with pytest.raises(AttributeError):
            fmt.name = "hacked"  # type: ignore[misc]

    @pytest.mark.parametrize(
        "name",
        ["front", "top", "right", "isometric", "dimetric", "trimetric"],
    )
    def test_standard_view_formats(self, name: str) -> None:
        assert DRAWING_FORMATS[name].draw_method == DrawingMethod.STANDARD_VIEW

    def test_no_format_confirmed_yet(self) -> None:
        """All formats ship unconfirmed — seat confirmation is a SEAT task."""
        for name, fmt in DRAWING_FORMATS.items():
            assert not fmt.seat_confirmed, (
                f"{name} is marked confirmed but no seat session has run"
            )

    def test_default_positions_are_positive(self) -> None:
        for name, fmt in DRAWING_FORMATS.items():
            assert fmt.default_x >= 0, f"{name} default_x is negative"
            assert fmt.default_y >= 0, f"{name} default_y is negative"


class TestResolveDrawingFormat:
    """resolve_format() lookup."""

    def test_known_format(self) -> None:
        fmt = resolve_format("front")
        assert isinstance(fmt, DrawingFormat)
        assert fmt.name == "front"
        assert fmt.view_name == "*Front"

    def test_unknown_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown drawing view"):
            resolve_format("nonexistent")

    def test_unknown_format_lists_known(self) -> None:
        with pytest.raises(ValueError, match="front"):
            resolve_format("nonexistent")
