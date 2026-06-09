"""Offline tests for observe_draft (W37).

Tests schema/arg validation, fail-closed paths, pull-direction parsing,
and the discrimination gate (drafted vs vertical vs negative face)
WITHOUT a running SOLIDWORKS session. Uses mocks for COM objects.
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock

import pytest

from ai_sw_bridge.observe_draft import (
    PULL_DIRECTIONS,
    _classify_draft,
    _compute_draft_deg,
    parse_pull_direction,
    read_draft,
    sw_get_draft_analysis,
)


DRAFT_ANALYSIS_KEYS = frozenset(
    {
        "pull_direction",
        "pull_vector",
        "faces_total",
        "faces_positive",
        "faces_negative",
        "faces_vertical",
        "min_draft_deg",
        "faces_below_threshold",
        "errors",
    }
)

SW_DRAFT_KEYS = frozenset(
    {
        "ok",
        "error",
        "draft_analysis",
    }
)


def _make_face(normal: tuple[float, float, float]) -> MagicMock:
    """Create a mock IFace2 with a given Normal (property-get, late-bound)."""
    face = MagicMock()
    face.Normal = normal
    return face


def _make_body(faces: list[MagicMock]) -> MagicMock:
    """Create a mock IBody2 whose GetFaces returns the given faces."""
    body = MagicMock()
    body.GetFaces = faces
    return body


def _make_part_doc(bodies: list[MagicMock], doc_type: int = 1) -> MagicMock:
    """Create a mock IPartDoc with given bodies and doc type."""
    doc = MagicMock()
    doc.GetType = doc_type
    doc.GetBodies2 = MagicMock(return_value=bodies if bodies else None)
    return doc


# ── Pull-direction parsing ────────────────────────────────────────────────


def test_parse_pull_direction_valid():
    """All documented directions resolve to unit vectors."""
    assert parse_pull_direction("front") == (0.0, 0.0, 1.0)
    assert parse_pull_direction("back") == (0.0, 0.0, -1.0)
    assert parse_pull_direction("top") == (0.0, 1.0, 0.0)
    assert parse_pull_direction("bottom") == (0.0, -1.0, 0.0)
    assert parse_pull_direction("right") == (1.0, 0.0, 0.0)
    assert parse_pull_direction("left") == (-1.0, 0.0, 0.0)
    assert parse_pull_direction("+x") == (1.0, 0.0, 0.0)
    assert parse_pull_direction("-z") == (0.0, 0.0, -1.0)


def test_parse_pull_direction_case_insensitive():
    """Direction strings are case-insensitive."""
    assert parse_pull_direction("Front") == (0.0, 0.0, 1.0)
    assert parse_pull_direction("TOP") == (0.0, 1.0, 0.0)
    assert parse_pull_direction("+X") == (1.0, 0.0, 0.0)


def test_parse_pull_direction_invalid():
    """Unrecognised direction → None."""
    assert parse_pull_direction("up") is None
    assert parse_pull_direction("diagonal") is None
    assert parse_pull_direction("") is None


# ── Draft-angle computation ──────────────────────────────────────────────


def test_compute_draft_deg_vertical_wall():
    """Normal perpendicular to pull → draft = 0° (vertical wall)."""
    draft = _compute_draft_deg((1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    assert abs(draft) < 1e-9


def test_compute_draft_deg_horizontal_face():
    """Normal parallel to pull → draft = 90° (horizontal face)."""
    draft = _compute_draft_deg((0.0, 0.0, 1.0), (0.0, 0.0, 1.0))
    assert abs(draft - 90.0) < 1e-9


def test_compute_draft_deg_positive_3():
    """3° positive-draft face reads ≈ 3°."""
    normal = (math.cos(math.radians(3.0)), 0.0, math.sin(math.radians(3.0)))
    draft = _compute_draft_deg(normal, (0.0, 0.0, 1.0))
    assert abs(draft - 3.0) < 0.01


def test_compute_draft_deg_negative_3():
    """3° negative-draft (undercut) face reads ≈ -3°."""
    normal = (math.cos(math.radians(3.0)), 0.0, -math.sin(math.radians(3.0)))
    draft = _compute_draft_deg(normal, (0.0, 0.0, 1.0))
    assert abs(draft - (-3.0)) < 0.01


def test_classify_draft():
    """Classification thresholds work correctly."""
    assert _classify_draft(5.0, 1.0) == "positive"
    assert _classify_draft(-5.0, 1.0) == "negative"
    assert _classify_draft(0.5, 1.0) == "vertical"
    assert _classify_draft(-0.5, 1.0) == "vertical"
    assert _classify_draft(0.0, 1.0) == "vertical"


# ── Schema / shape tests ─────────────────────────────────────────────────


def test_read_draft_shape_invalid_pull():
    """Invalid pull direction → errors populated, faces_total = 0."""
    doc = _make_part_doc([_make_body([])])
    result = read_draft(doc, "sideways")
    assert isinstance(result, dict)
    assert set(result.keys()) == DRAFT_ANALYSIS_KEYS
    assert result["faces_total"] == 0
    assert len(result["errors"]) > 0


def test_sw_get_draft_analysis_shape_not_part():
    """Non-part doc → ok=False with typed error."""
    doc = MagicMock()
    doc.GetType = 2  # SW_DOC_ASSEMBLY

    result = sw_get_draft_analysis(doc, "top")
    assert isinstance(result, dict)
    assert set(result.keys()) == SW_DRAFT_KEYS
    assert result["ok"] is False
    assert "part document" in str(result["error"])


def test_sw_get_draft_analysis_shape_drawing():
    """Drawing doc → ok=False with typed error."""
    doc = MagicMock()
    doc.GetType = 3  # SW_DOC_DRAWING

    result = sw_get_draft_analysis(doc, "top")
    assert result["ok"] is False
    assert "part document" in str(result["error"])


def test_read_draft_no_bodies():
    """Part with no solid bodies → error."""
    doc = _make_part_doc([])
    result = read_draft(doc, "top")
    assert result["faces_total"] == 0
    assert any("no solid bodies" in e for e in result["errors"])


# ── Discrimination gate (load-bearing) ───────────────────────────────────


def test_discrimination_gate():
    """Part with known drafted face (3°), vertical wall (0°), and
    negative-draft control (-3°) — angles must discriminate correctly.

    This is the W35 clearance-discrimination doctrine applied to angles:
    numbers alone don't ship; the analyser must distinguish positive,
    zero, and negative draft.
    """
    pull = (0.0, 0.0, 1.0)

    # Vertical wall: normal = (1, 0, 0) → draft = 0°
    vertical = _make_face((1.0, 0.0, 0.0))

    # 3° positive draft: normal tilted 3° toward pull from horizontal
    pos_normal = (math.cos(math.radians(3.0)), 0.0, math.sin(math.radians(3.0)))
    positive = _make_face(pos_normal)

    # 3° negative draft (undercut): normal tilted 3° away from pull
    neg_normal = (math.cos(math.radians(3.0)), 0.0, -math.sin(math.radians(3.0)))
    negative = _make_face(neg_normal)

    # Horizontal top: normal = pull → draft = 90°
    top = _make_face((0.0, 0.0, 1.0))

    body = _make_body([vertical, positive, negative, top])
    doc = _make_part_doc([body])

    result = read_draft(doc, "front", min_angle_deg=1.0)

    assert result["errors"] == []
    assert result["faces_total"] == 4
    assert result["faces_positive"] == 2  # positive draft + horizontal top
    assert result["faces_negative"] == 1  # negative draft
    assert result["faces_vertical"] == 1  # vertical wall

    # Vertical wall should be in faces_below_threshold
    assert len(result["faces_below_threshold"]) == 1
    flagged = result["faces_below_threshold"][0]
    assert abs(flagged["draft_deg"]) < 1e-6
    assert flagged["classification"] == "vertical"

    # min_draft_deg should be ≈ 0 (the vertical wall)
    assert result["min_draft_deg"] is not None
    assert abs(result["min_draft_deg"]) < 1e-6


def test_discrimination_gate_negative_control():
    """Negative-draft face must read negative — the control that proves
    the sign convention is correct.
    """
    neg_normal = (math.cos(math.radians(5.0)), 0.0, -math.sin(math.radians(5.0)))
    negative = _make_face(neg_normal)
    body = _make_body([negative])
    doc = _make_part_doc([body])

    result = read_draft(doc, "front", min_angle_deg=1.0)

    assert result["faces_total"] == 1
    assert result["faces_negative"] == 1
    assert result["faces_positive"] == 0
    assert result["faces_vertical"] == 0
    assert result["faces_below_threshold"] == []


# ── sw_get_draft_analysis integration ────────────────────────────────────


def test_sw_get_draft_analysis_ok():
    """Successful analysis → ok=True with draft_analysis populated."""
    vertical = _make_face((1.0, 0.0, 0.0))
    top = _make_face((0.0, 0.0, 1.0))
    body = _make_body([vertical, top])
    doc = _make_part_doc([body], doc_type=1)

    result = sw_get_draft_analysis(doc, "front")

    assert result["ok"] is True
    assert result["error"] is None
    assert result["draft_analysis"] is not None
    assert result["draft_analysis"]["faces_total"] == 2


def test_sw_get_draft_analysis_no_bodies():
    """No solid bodies → ok=False with error."""
    doc = _make_part_doc([], doc_type=1)

    result = sw_get_draft_analysis(doc, "front")

    assert result["ok"] is False
    assert "no solid bodies" in str(result["error"])


# ── Multi-body part ──────────────────────────────────────────────────────


def test_multi_body_part():
    """Faces from multiple bodies are all classified."""
    face_a = _make_face((1.0, 0.0, 0.0))
    face_b = _make_face((0.0, 0.0, 1.0))
    body_a = _make_body([face_a])
    body_b = _make_body([face_b])
    doc = _make_part_doc([body_a, body_b])

    result = read_draft(doc, "front")

    assert result["faces_total"] == 2


# ── CLI subcommand parser tests ──────────────────────────────────────────


def test_draft_subcommand_in_parser():
    """The 'draft' subcommand is registered in the CLI parser."""
    from ai_sw_bridge.cli.observe import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["draft", "--pull-direction", "top"])
    assert args.tool == "draft"
    assert args.pull_direction == "top"
    assert args.min_angle == 1.0
    assert hasattr(args, "func")


def test_draft_subcommand_custom_min_angle():
    """--min-angle flag is parsed correctly."""
    from ai_sw_bridge.cli.observe import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["draft", "--pull-direction", "+z", "--min-angle", "2.5"])
    assert args.pull_direction == "+z"
    assert args.min_angle == 2.5


def test_draft_subcommand_requires_pull_direction():
    """--pull-direction is required."""
    from ai_sw_bridge.cli.observe import _build_parser

    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["draft"])
