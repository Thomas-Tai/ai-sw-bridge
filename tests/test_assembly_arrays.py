"""Tests for assembly component-array expansion math (Wave-26).

Pure geometry — no SOLIDWORKS required. Covers:
  - Linear array position + orientation
  - Circular array position + orientation
  - Edge cases (zero vector, id collision)
  - Full expand_component_arrays pipeline
"""

from __future__ import annotations

import math

import pytest

from ai_sw_bridge.assembly.arrays import (
    expand_circular_array,
    expand_component_arrays,
    expand_linear_array,
    _cross,
    _matrix_to_rpy,
    _normalize,
    _rotation_matrix_about_axis,
    _rpy_to_matrix,
)


# ---- Helpers ---------------------------------------------------------------

def _approx(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) < tol


def _vec_approx(a: list[float], b: list[float], tol: float = 1e-6) -> bool:
    return all(abs(ai - bi) < tol for ai, bi in zip(a, b))


# ---- Linear array ----------------------------------------------------------


class TestLinearArray:
    def test_instance_count(self) -> None:
        result = expand_linear_array(
            "rail", {"part": "r.sldprt"}, 5, 40.0, [1, 0, 0], [0, 0, 0], [0, 0, 0]
        )
        assert len(result) == 5

    def test_instance_ids(self) -> None:
        result = expand_linear_array(
            "rail", {"part": "r.sldprt"}, 3, 10.0, [1, 0, 0], [0, 0, 0], [0, 0, 0]
        )
        assert [c["id"] for c in result] == ["rail_0", "rail_1", "rail_2"]

    def test_positions_along_x(self) -> None:
        result = expand_linear_array(
            "rail", {"part": "r.sldprt"}, 3, 40.0, [1, 0, 0], [0, 0, 0], [0, 0, 0]
        )
        # Instance 0: origin
        assert _vec_approx(result[0]["transform"]["xyz_mm"], [0, 0, 0])
        # Instance 1: 40mm along +X
        assert _vec_approx(result[1]["transform"]["xyz_mm"], [40, 0, 0])
        # Instance 2: 80mm along +X
        assert _vec_approx(result[2]["transform"]["xyz_mm"], [80, 0, 0])

    def test_positions_along_diagonal(self) -> None:
        d = [1, 1, 0]
        result = expand_linear_array(
            "d", {"part": "d.sldprt"}, 2, 100.0, d, [10, 20, 30], [0, 0, 0]
        )
        # Normalized direction: [1/√2, 1/√2, 0]
        inv_sqrt2 = 1.0 / math.sqrt(2)
        assert _vec_approx(result[0]["transform"]["xyz_mm"], [10, 20, 30])
        assert _vec_approx(
            result[1]["transform"]["xyz_mm"],
            [10 + 100 * inv_sqrt2, 20 + 100 * inv_sqrt2, 30],
        )

    def test_orientation_unchanged(self) -> None:
        result = expand_linear_array(
            "r", {"part": "r.sldprt"}, 3, 10.0, [1, 0, 0], [0, 0, 0], [45, 30, 60]
        )
        for c in result:
            assert _vec_approx(c["transform"]["rpy_deg"], [45, 30, 60])

    def test_part_field_propagated(self) -> None:
        result = expand_linear_array(
            "r", {"part_spec": "r.json"}, 2, 10.0, [1, 0, 0], [0, 0, 0], [0, 0, 0]
        )
        assert result[0]["part_spec"] == "r.json"
        assert "part" not in result[0]

    def test_zero_direction_raises(self) -> None:
        with pytest.raises(ValueError, match="zero-length"):
            expand_linear_array(
                "r", {"part": "r.sldprt"}, 2, 10.0, [0, 0, 0], [0, 0, 0], [0, 0, 0]
            )


# ---- Circular array --------------------------------------------------------


class TestCircularArray:
    def test_instance_count(self) -> None:
        result = expand_circular_array(
            "bolt", {"part": "b.sldprt"}, 6, 50.0, [0, 0, 1], [0, 0, 0], 360.0, [0, 0, 0]
        )
        assert len(result) == 6

    def test_full_circle_positions_z_axis(self) -> None:
        """4 instances on Z-axis circle, radius=50: at 0°, 90°, 180°, 270°."""
        result = expand_circular_array(
            "b", {"part": "b.sldprt"}, 4, 50.0, [0, 0, 1], [0, 0, 0], 360.0, [0, 0, 0]
        )
        # Instance 0 (θ=0): at (50, 0, 0) approximately (depending on u choice)
        # Instance 1 (θ=90): ~90° from instance 0
        # All instances at radius=50 from center
        for c in result:
            xyz = c["transform"]["xyz_mm"]
            r = math.sqrt(xyz[0] ** 2 + xyz[1] ** 2)
            assert _approx(r, 50.0, tol=1e-4), f"radius={r}, expected 50"

        # Instances are NOT stacked (the no-op trap)
        positions = [tuple(c["transform"]["xyz_mm"]) for c in result]
        assert len(set(positions)) == 4, "all 4 instances must have distinct positions"

    def test_angular_separation(self) -> None:
        """4 instances on Z-axis: consecutive pairs are ~90° apart."""
        result = expand_circular_array(
            "b", {"part": "b.sldprt"}, 4, 50.0, [0, 0, 1], [0, 0, 0], 360.0, [0, 0, 0]
        )
        angles = []
        for c in result:
            xyz = c["transform"]["xyz_mm"]
            angles.append(math.degrees(math.atan2(xyz[1], xyz[0])))

        # Consecutive angular differences should be ~90°
        for i in range(len(angles) - 1):
            delta = abs(angles[i + 1] - angles[i])
            # Normalize to [0, 360]
            delta = delta % 360
            assert _approx(min(delta, 360 - delta), 90.0, tol=1.0), (
                f"angular sep between {i} and {i+1}: {delta}°"
            )

    def test_instance_at_center_offset(self) -> None:
        """Circle centered at (10, 20, 30): all instances at radius from center."""
        result = expand_circular_array(
            "b", {"part": "b.sldprt"}, 3, 25.0, [0, 0, 1], [10, 20, 30], 360.0, [0, 0, 0]
        )
        for c in result:
            xyz = c["transform"]["xyz_mm"]
            dx = xyz[0] - 10
            dy = xyz[1] - 20
            r = math.sqrt(dx ** 2 + dy ** 2)
            assert _approx(r, 25.0, tol=1e-4)
            assert _approx(xyz[2], 30.0, tol=1e-4)

    def test_z_height_constant_for_z_axis(self) -> None:
        """Z-axis circular array: all instances at same Z."""
        result = expand_circular_array(
            "b", {"part": "b.sldprt"}, 6, 50.0, [0, 0, 1], [0, 0, 100], 360.0, [0, 0, 0]
        )
        for c in result:
            assert _approx(c["transform"]["xyz_mm"][2], 100.0, tol=1e-4)

    def test_orientation_varies(self) -> None:
        """Non-trivial base_rpy: orientation should differ per instance."""
        result = expand_circular_array(
            "b", {"part": "b.sldprt"}, 4, 50.0, [0, 0, 1], [0, 0, 0], 360.0, [0, 0, 0]
        )
        # At least some instances should have different orientations
        rpys = [tuple(c["transform"]["rpy_deg"]) for c in result]
        assert len(set(rpys)) > 1, "orientations must vary around the circle"

    def test_y_axis_circle(self) -> None:
        """Y-axis circle: instances in XZ plane at radius from Y axis."""
        result = expand_circular_array(
            "b", {"part": "b.sldprt"}, 4, 30.0, [0, 1, 0], [0, 50, 0], 360.0, [0, 0, 0]
        )
        for c in result:
            xyz = c["transform"]["xyz_mm"]
            r = math.sqrt(xyz[0] ** 2 + xyz[2] ** 2)
            assert _approx(r, 30.0, tol=1e-4), f"radius={r}"
            assert _approx(xyz[1], 50.0, tol=1e-4)

    def test_zero_axis_raises(self) -> None:
        with pytest.raises(ValueError, match="zero-length"):
            expand_circular_array(
                "b", {"part": "b.sldprt"}, 2, 10.0, [0, 0, 0], [0, 0, 0], 360.0, [0, 0, 0]
            )


# ---- Rotation matrix round-trip --------------------------------------------


class TestRotationMath:
    def test_identity(self) -> None:
        m = _rpy_to_matrix(0, 0, 0)
        assert _vec_approx([m[i][j] for i in range(3) for j in range(3)],
                           [1, 0, 0, 0, 1, 0, 0, 0, 1])

    def test_rpy_roundtrip(self) -> None:
        for rpy in [(30, 45, 60), (0, 0, 90), (-10, 20, -30), (90, 0, 0)]:
            m = _rpy_to_matrix(*rpy)
            recovered = _matrix_to_rpy(m)
            assert _vec_approx(recovered, list(rpy), tol=1e-4), (
                f"rpy={rpy}, recovered={recovered}"
            )

    def test_axis_rotation_z90(self) -> None:
        """R(z, 90°) should rotate +X to +Y."""
        R = _rotation_matrix_about_axis([0, 0, 1], math.pi / 2)
        # R · [1,0,0] should be ~[0,1,0]
        rx = R[0][0] * 1 + R[0][1] * 0 + R[0][2] * 0
        ry = R[1][0] * 1 + R[1][1] * 0 + R[1][2] * 0
        rz = R[2][0] * 1 + R[2][1] * 0 + R[2][2] * 0
        assert _approx(rx, 0.0, tol=1e-6)
        assert _approx(ry, 1.0, tol=1e-6)
        assert _approx(rz, 0.0, tol=1e-6)


# ---- Full expansion pipeline -----------------------------------------------


class TestExpandArrays:
    def test_linear_expansion(self) -> None:
        arrays = [{
            "id": "rail", "type": "linear", "part": "r.sldprt",
            "count": 3, "spacing_mm": 40.0, "direction": [1, 0, 0],
            "base_xyz_mm": [0, 0, 0], "base_rpy_deg": [0, 0, 0],
        }]
        expanded, err = expand_component_arrays(arrays, set())
        assert err is None
        assert len(expanded) == 3
        assert expanded[0]["id"] == "rail_0"
        assert expanded[2]["id"] == "rail_2"

    def test_circular_expansion(self) -> None:
        arrays = [{
            "id": "bolt", "type": "circular", "part": "b.sldprt",
            "count": 4, "radius_mm": 50.0, "axis": [0, 0, 1],
            "center_xyz_mm": [0, 0, 0], "angle_deg": 360.0,
        }]
        expanded, err = expand_component_arrays(arrays, set())
        assert err is None
        assert len(expanded) == 4

    def test_id_collision_rejected(self) -> None:
        arrays = [{
            "id": "rail", "type": "linear", "part": "r.sldprt",
            "count": 2, "spacing_mm": 10.0, "direction": [1, 0, 0],
        }]
        # "rail_0" already exists
        expanded, err = expand_component_arrays(arrays, {"rail_0"})
        assert err is not None
        assert "collides" in err

    def test_unknown_type_rejected(self) -> None:
        arrays = [{
            "id": "x", "type": "spiral", "part": "x.sldprt",
            "count": 2,
        }]
        expanded, err = expand_component_arrays(arrays, set())
        assert err is not None
        assert "unknown type" in err

    def test_mixed_linear_circular(self) -> None:
        arrays = [
            {
                "id": "rail", "type": "linear", "part": "r.sldprt",
                "count": 3, "spacing_mm": 40.0, "direction": [1, 0, 0],
            },
            {
                "id": "bolt", "type": "circular", "part": "b.sldprt",
                "count": 4, "radius_mm": 50.0, "axis": [0, 0, 1],
                "angle_deg": 360.0,
            },
        ]
        expanded, err = expand_component_arrays(arrays, set())
        assert err is None
        assert len(expanded) == 7
        ids = [c["id"] for c in expanded]
        assert "rail_0" in ids
        assert "bolt_3" in ids

    def test_part_spec_array(self) -> None:
        arrays = [{
            "id": "a", "type": "linear", "part_spec": "a.json",
            "count": 2, "spacing_mm": 10.0, "direction": [1, 0, 0],
        }]
        expanded, err = expand_component_arrays(arrays, set())
        assert err is None
        assert expanded[0]["part_spec"] == "a.json"
        assert "part" not in expanded[0]

    def test_no_part_raises(self) -> None:
        arrays = [{
            "id": "x", "type": "linear",
            "count": 2, "spacing_mm": 10.0, "direction": [1, 0, 0],
        }]
        expanded, err = expand_component_arrays(arrays, set())
        assert err is not None
        assert "no part" in err
