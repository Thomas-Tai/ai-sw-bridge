"""W48 bend-layer rewriter — offline proof on the golden flat pattern.

``rewrite_dxf_with_bend_layer`` is the production transform behind the
``dxf_flat_bends`` export format: it re-assigns every classified INTERIOR bend
LINE from layer ``"0"`` to ``"BEND"`` while leaving the developed-boundary
perimeter on ``"0"`` and preserving all other geometry. These tests pin it
against the golden L-bracket flat pattern captured from the live seat
(``W42_L_bracket_flat_bends.dxf``): exactly ONE interior fold line
(130,165)→(170,165) must move to ``BEND``; the four perimeter edges must stay
on ``"0"``; the geometry (re-classification) must be unchanged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_sw_bridge.export.dxf_bend_layers import (
    classify_bend_lines_geometric,
    rewrite_dxf_with_bend_layer,
)

_GOLDEN = Path(__file__).parent / "fixtures" / "W42_L_bracket_flat_bends.dxf"
_BEND_ENDPOINTS = {(130.0, 165.0), (170.0, 165.0)}


def _line_layers(dxf_text: str) -> list[tuple[tuple[float, float, float, float], str]]:
    """Return ``[((x1,y1,x2,y2), layer_name), ...]`` for every LINE entity."""
    lines = dxf_text.splitlines()
    out: list[tuple[tuple[float, float, float, float], str]] = []
    cur: str | None = None
    seg: dict[str, float] = {}
    layer = "0"

    def _flush() -> None:
        if cur == "LINE" and {"10", "20", "11", "21"} <= seg.keys():
            out.append(((seg["10"], seg["20"], seg["11"], seg["21"]), layer))

    i = 0
    while i < len(lines) - 1:
        code = lines[i].strip()
        val = lines[i + 1].strip()
        if code == "0":
            _flush()
            cur = val
            seg = {}
            layer = "0"
        elif cur == "LINE":
            if code in ("10", "20", "11", "21"):
                try:
                    seg[code] = float(val)
                except ValueError:
                    pass
            elif code == "8":
                layer = val
        i += 2
    _flush()
    return out


def _is_bend_seg(s: tuple[float, float, float, float]) -> bool:
    x1, y1, x2, y2 = s
    pts = {(round(x1, 3), round(y1, 3)), (round(x2, 3), round(y2, 3))}
    return pts == _BEND_ENDPOINTS


class TestBendLayerRewriter:
    def _golden(self) -> str:
        return _GOLDEN.read_text(encoding="utf-8", errors="replace")

    def test_rewrites_exactly_one_bend_entity(self) -> None:
        _, classified = rewrite_dxf_with_bend_layer(self._golden(), "BEND")
        assert classified["bend_line_count"] == 1
        assert classified["rewritten_bend_entities"] == 1

    def test_bend_line_moves_to_bend_layer(self) -> None:
        rewritten, _ = rewrite_dxf_with_bend_layer(self._golden(), "BEND")
        layered = _line_layers(rewritten)
        bend = [(s, lyr) for (s, lyr) in layered if _is_bend_seg(s)]
        assert len(bend) == 1
        assert bend[0][1] == "BEND"

    def test_perimeter_lines_stay_on_layer_0(self) -> None:
        rewritten, _ = rewrite_dxf_with_bend_layer(self._golden(), "BEND")
        layered = _line_layers(rewritten)
        outline = [(s, lyr) for (s, lyr) in layered if not _is_bend_seg(s)]
        assert len(outline) == 4
        assert all(lyr == "0" for (_s, lyr) in outline)

    def test_geometry_unchanged_after_rewrite(self) -> None:
        rewritten, _ = rewrite_dxf_with_bend_layer(self._golden(), "BEND")
        reclassified = classify_bend_lines_geometric(rewritten)
        assert reclassified["bend_line_count"] == 1
        assert reclassified["outline_line_count"] == 4
        assert reclassified["bbox"]["y_max"] - reclassified["bbox"][
            "y_min"
        ] == pytest.approx(86.283, abs=1e-3)

    def test_custom_layer_name(self) -> None:
        rewritten, _ = rewrite_dxf_with_bend_layer(self._golden(), "IV_BEND")
        layered = _line_layers(rewritten)
        bend = [(s, lyr) for (s, lyr) in layered if _is_bend_seg(s)]
        assert bend[0][1] == "IV_BEND"

    def test_line_count_preserved(self) -> None:
        # The rewrite must not add or drop entities — same 5 LINEs in, 5 out.
        before = len(_line_layers(self._golden()))
        rewritten, _ = rewrite_dxf_with_bend_layer(self._golden(), "BEND")
        assert len(_line_layers(rewritten)) == before == 5


class TestBendLayerRewriterDegenerate:
    def test_no_bend_returns_unchanged(self) -> None:
        text = "0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n"
        rewritten, classified = rewrite_dxf_with_bend_layer(text, "BEND")
        assert rewritten == text
        assert classified["bend_line_count"] == 0

    def test_empty_string(self) -> None:
        rewritten, classified = rewrite_dxf_with_bend_layer("", "BEND")
        assert rewritten == ""
        assert classified["bend_line_count"] == 0
