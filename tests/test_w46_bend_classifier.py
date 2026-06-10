"""W46 geometric bend-line classifier — offline proof on the golden flat pattern.

SOLIDWORKS collapses every flat-pattern DXF entity onto layer ``"0"``, so a
layer-NAME parser cannot distinguish a bend (fold) line from the part outline
(W46 wall). ``classify_bend_lines_geometric`` instead reads the topology: the
developed outline is the bounding-rectangle PERIMETER, and bend lines are the
INTERIOR LINE entities that do not lie on a bbox side.

These tests pin that classifier against the golden L-bracket flat pattern
captured from the live seat (``W42_L_bracket_flat_bends.dxf``): 5 LINE entities
+ 1 MTEXT, bbox 40.0 × 86.283 mm, where exactly ONE line — (130,165)→(170,165),
spanning the full 40 mm width strictly between ymin and ymax — is the single
90° bend. The proof is the EXTRACTED interior segment, not a layer-name string.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ai_sw_bridge.cli.export_dxf_flat import classify_bend_lines_geometric

_GOLDEN = Path(__file__).parent / "fixtures" / "W42_L_bracket_flat_bends.dxf"

# The single seat-captured interior fold line (endpoints, order-insensitive).
_BEND_ENDPOINTS = {(130.0, 165.0), (170.0, 165.0)}


class TestGeometricBendClassifier:
    """Pin the interior-vs-perimeter split on the golden flat pattern."""

    def _classify(self) -> dict:
        return classify_bend_lines_geometric(
            _GOLDEN.read_text(encoding="utf-8", errors="replace")
        )

    def test_exactly_one_bend_line(self) -> None:
        # The single 90° bend ⇒ exactly one interior LINE survives.
        assert self._classify()["bend_line_count"] == 1

    def test_four_perimeter_outline_lines(self) -> None:
        # The four bbox-rectangle edges classify as outline, not bend.
        assert self._classify()["outline_line_count"] == 4

    def test_bend_line_endpoints_match_seat(self) -> None:
        bends = self._classify()["bend_lines"]
        assert len(bends) == 1
        bl = bends[0]
        endpoints = {tuple(bl["start"]), tuple(bl["end"])}
        # Order-insensitive within epsilon — compare each captured endpoint to
        # its nearest expected datum.
        for got in endpoints:
            assert any(
                abs(got[0] - exp[0]) <= 1e-3 and abs(got[1] - exp[1]) <= 1e-3
                for exp in _BEND_ENDPOINTS
            ), f"unexpected bend endpoint {got}"

    def test_bbox_spans_the_developed_boundary(self) -> None:
        bbox = self._classify()["bbox"]
        assert bbox is not None
        assert bbox["x_max"] - bbox["x_min"] == pytest.approx(40.0, abs=1e-3)
        assert bbox["y_max"] - bbox["y_min"] == pytest.approx(86.283, abs=1e-3)


class TestGeometricBendClassifierDegenerate:
    """The classifier never crashes on empty / no-LINE input."""

    def test_empty_string(self) -> None:
        res = classify_bend_lines_geometric("")
        assert res["bend_line_count"] == 0
        assert res["bend_lines"] == []
        assert res["outline_line_count"] == 0
        assert res["bbox"] is None

    def test_no_line_entities(self) -> None:
        # A DXF-shaped blob with no LINE entity must not divide-by-zero on the
        # empty bbox.
        res = classify_bend_lines_geometric("0\nSECTION\n2\nENTITIES\n0\nENDSEC\n")
        assert res["bend_line_count"] == 0
        assert res["bbox"] is None
