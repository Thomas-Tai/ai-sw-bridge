"""W42 dxf_flat — offline proof pinned to the PHYSICAL developed boundary.

The load-bearing W42 result is that ``dxf_flat`` performs an authentic
topological UNFOLD: a verified bent L-bracket (open-profile base flange,
vol=6902.655 mm³, 14 faces, one 90° bend) exports a flat-pattern DXF whose
developed outline is **86.28 × 40.0 mm** — the *unrolled* length, distinct from
both the 60 mm largest folded face and the 90 mm naive segment sum. These tests
pin that physical span against a golden fixture captured from the live seat
(2026-06-09), NOT superficial layer names / entity counts.

Bend LINES (brake annotation) are deliberately NOT asserted: ExportFlatPatternView
(options 0–7) does not emit them — that is a deferred sub-scope routed through a
drawing flat-pattern view (W33), see docs/DEFERRED.md Wave-42.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ai_sw_bridge.cli.export_dxf_flat import (
    parse_dxf_outline_bbox,
    _parse_dxf_entities,
)
from ai_sw_bridge.export.formats import EXPORT_FORMATS

_GOLDEN = Path(__file__).parent / "fixtures" / "W42_L_bracket_flat.dxf"

# Seat-measured developed boundary of the L-bracket (60+30mm segments, t=2mm,
# bend R=3mm, depth=40mm). The long span is the UNROLLED developed length.
_DEV_LONG_MM = 86.28
_FOLDED_FACE_MM = 60.0   # the largest folded face — what a NON-unfold would emit
_NAIVE_SUM_MM = 90.0     # 60+30 with no bend deduction
_DEPTH_MM = 40.0


class TestDxfFlatDevelopedBoundary:
    """Pin the physical unrolled span — the proof dxf_flat actually unfolds."""

    def _bbox(self) -> dict:
        return parse_dxf_outline_bbox(_GOLDEN.read_text(encoding="utf-8", errors="replace"))

    def test_outline_found(self) -> None:
        assert self._bbox().get("found") is True

    def test_long_span_is_the_developed_length(self) -> None:
        bbox = self._bbox()
        # Pinned to the seat-measured developed length (86.28 mm), tight tolerance.
        assert bbox["span_long_mm"] == pytest.approx(_DEV_LONG_MM, abs=0.5)

    def test_short_span_is_the_depth(self) -> None:
        assert self._bbox()["span_short_mm"] == pytest.approx(_DEPTH_MM, abs=0.5)

    def test_unfold_is_real_not_a_folded_face(self) -> None:
        # The decisive discrimination: the developed long span must be strictly
        # GREATER than the largest folded face (60 mm) — a non-unfolding export
        # (single face) would land at ~60. It must also be < the naive 90 mm sum
        # (a real bend DEDUCTS material), proving an authentic unroll.
        span = self._bbox()["span_long_mm"]
        assert span > _FOLDED_FACE_MM + 5.0
        assert span < _NAIVE_SUM_MM


class TestDxfFlatRegistration:
    def test_dxf_flat_is_seat_confirmed(self) -> None:
        fmt = EXPORT_FORMATS["dxf_flat"]
        assert fmt.seat_confirmed is True

    def test_golden_has_outline_entities(self) -> None:
        ent = _parse_dxf_entities(_GOLDEN.read_text(encoding="utf-8", errors="replace"))
        assert ent["entities_section_found"] is True
        assert ent["entity_types"].get("LINE", 0) >= 4

    def test_bbox_parser_handles_empty(self) -> None:
        assert parse_dxf_outline_bbox("no entities here") == {"found": False}
