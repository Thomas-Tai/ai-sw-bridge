"""Shape-contract tests for sw_get_bbox / sw_get_volume (P0.2).

These run WITHOUT a running SOLIDWORKS session: get_sw_app() will raise
com_error, the functions catch it, and return their typed error dict.
What we verify here is the SHAPE of that dict -- every key the wire
contract promises is present, error is populated, ok is False.

The point isn't to test SW behavior (we can't from CI). The point is
to lock the wire contract so the regression-check harness (P1.2) can
rely on `out["volume_mm3"]` existing even on error paths -- it'll be
None, but the key is there.
"""

from __future__ import annotations

from ai_sw_bridge.observe import sw_get_bbox, sw_get_volume


BBOX_KEYS = frozenset(
    {
        "ok",
        "doc_path",
        "error",
        "x_min_mm",
        "x_max_mm",
        "x_span_mm",
        "y_min_mm",
        "y_max_mm",
        "y_span_mm",
        "z_min_mm",
        "z_max_mm",
        "z_span_mm",
        "x_min_m",
        "x_max_m",
        "y_min_m",
        "y_max_m",
        "z_min_m",
        "z_max_m",
    }
)


VOLUME_KEYS = frozenset(
    {
        "ok",
        "doc_path",
        "error",
        "volume_mm3",
        "volume_m3",
        "surface_area_mm2",
        "surface_area_m2",
        "mass_kg",
        "density_kg_m3",
        "center_of_mass_mm",
        "body_count",
    }
)


def test_sw_get_bbox_shape_when_sw_unavailable():
    result = sw_get_bbox()
    # The exact error text depends on whether SW is running or not; the
    # contract is that we ALWAYS get a dict back with the right keys, and
    # `ok` is False (with a non-empty error) when SW can't be reached.
    assert isinstance(result, dict)
    assert set(result.keys()) == BBOX_KEYS
    if not result["ok"]:
        assert result["error"] is not None


def test_sw_get_volume_shape_when_sw_unavailable():
    result = sw_get_volume()
    assert isinstance(result, dict)
    assert set(result.keys()) == VOLUME_KEYS
    if not result["ok"]:
        assert result["error"] is not None
