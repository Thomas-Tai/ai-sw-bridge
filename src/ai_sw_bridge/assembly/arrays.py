"""Assembly component-array expansion (Wave-26).

Declarative expansion of ``component_arrays`` entries into synthetic
``components`` entries with computed transforms. Pure math — zero COM.

**Convention (circular, PRE-LOCKED):**
  ``θk = k · angle_deg / count`` for k = 0..count-1.
  A full-circle array (angle_deg=360, count=4) places instances at
  0°, 90°, 180°, 270° — evenly spaced with no overlap.

**Linear array:**
  Instance k at ``base_xyz_mm + k · spacing_mm · normalize(direction)``,
  orientation = ``base_rpy_deg`` (translation only).

**Circular array:**
  Instance k positioned on the circle of ``radius_mm`` about ``axis``
  through ``center_xyz_mm`` at angle ``θk``. Orientation: component is
  rotated about ``axis`` by ``θk`` (so instances "go around"), composed
  with ``base_rpy_deg``.

Both reuse the W13 rpy→transform convention (intrinsic ZYX ``Rz·Ry·Rx``).
"""

from __future__ import annotations

import math
from typing import Any


def _normalize(v: list[float]) -> list[float]:
    """Normalize a 3-vector; raises ValueError on zero-length."""
    length = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    if length < 1e-12:
        raise ValueError(f"zero-length vector: {v}")
    return [v[0] / length, v[1] / length, v[2] / length]


def _rotation_matrix_about_axis(axis: list[float], angle_rad: float) -> list[list[float]]:
    """Rodrigues' rotation formula: R(axis, θ) as 3×3 matrix.

    axis must be a unit vector.
    """
    ax, ay, az = axis
    c = math.cos(angle_rad)
    s = math.sin(angle_rad)
    t = 1.0 - c

    return [
        [t * ax * ax + c,     t * ax * ay - s * az, t * ax * az + s * ay],
        [t * ax * ay + s * az, t * ay * ay + c,     t * ay * az - s * ax],
        [t * ax * az - s * ay, t * ay * az + s * ax, t * az * az + c],
    ]


def _mat_mul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    """3×3 matrix multiply: a · b."""
    return [
        [sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)]
        for i in range(3)
    ]


def _rpy_to_matrix(roll_deg: float, pitch_deg: float, yaw_deg: float) -> list[list[float]]:
    """Build rotation matrix R = Rz(yaw) · Ry(pitch) · Rx(roll).

    Matches the W13 convention in handlers._rpy_to_transform.
    """
    rx = math.radians(roll_deg)
    ry = math.radians(pitch_deg)
    rz = math.radians(yaw_deg)

    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)

    return [
        [cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx],
        [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx],
        [-sy,     cy * sx,               cy * cx],
    ]


def _matrix_to_rpy(m: list[list[float]]) -> list[float]:
    """Extract (roll_deg, pitch_deg, yaw_deg) from R = Rz·Ry·Rx.

    Inverse of _rpy_to_matrix. Uses the standard ZYX Euler decomposition:
      pitch = asin(-R[2][0])
      roll  = atan2(R[2][1], R[2][2])
      yaw   = atan2(R[1][0], R[0][0])
    """
    r20 = max(-1.0, min(1.0, m[2][0]))
    pitch = math.asin(-r20)

    if abs(math.cos(pitch)) > 1e-10:
        roll = math.atan2(m[2][1], m[2][2])
        yaw = math.atan2(m[1][0], m[0][0])
    else:
        roll = 0.0
        yaw = math.atan2(-m[0][1], m[1][1])

    return [math.degrees(roll), math.degrees(pitch), math.degrees(yaw)]


def expand_linear_array(
    array_id: str,
    part: dict[str, str],
    count: int,
    spacing_mm: float,
    direction: list[float],
    base_xyz_mm: list[float],
    base_rpy_deg: list[float],
) -> list[dict[str, Any]]:
    """Expand a linear array into synthetic component entries.

    Returns a list of ``count`` component dicts with ids ``{array_id}_0``
    through ``{array_id}_{count-1}``.

    Args:
        array_id: the array's ``id`` (used as prefix for instance ids).
        part: ``{"part": path}`` or ``{"part_spec": path}``.
        count: number of instances (≥2).
        spacing_mm: spacing between consecutive instances in mm.
        direction: 3-vector (will be normalized).
        base_xyz_mm: position of instance 0.
        base_rpy_deg: orientation for all instances (translation only).

    Returns:
        List of component dicts ready for ``place_components``.
    """
    d = _normalize(direction)
    bx, by, bz = base_xyz_mm
    components: list[dict[str, Any]] = []

    for k in range(count):
        xyz = [
            bx + k * spacing_mm * d[0],
            by + k * spacing_mm * d[1],
            bz + k * spacing_mm * d[2],
        ]
        comp: dict[str, Any] = {
            "id": f"{array_id}_{k}",
            "transform": {
                "xyz_mm": xyz,
                "rpy_deg": list(base_rpy_deg),
            },
        }
        comp.update(part)
        components.append(comp)

    return components


def expand_circular_array(
    array_id: str,
    part: dict[str, str],
    count: int,
    radius_mm: float,
    axis: list[float],
    center_xyz_mm: list[float],
    angle_deg: float,
    base_rpy_deg: list[float],
) -> list[dict[str, Any]]:
    """Expand a circular array into synthetic component entries.

    Convention: ``θk = k · angle_deg / count`` for k = 0..count-1.

    Instance k is positioned at:
      ``center + radius · (cos(θk) · u + sin(θk) · (axis × u))``
    where u is a unit vector perpendicular to axis.

    Instance k is oriented by rotating base_rpy_deg about axis by θk.

    Args:
        array_id: the array's ``id`` (used as prefix for instance ids).
        part: ``{"part": path}`` or ``{"part_spec": path}``.
        count: number of instances (≥2).
        radius_mm: radius of the circle in mm.
        axis: 3-vector rotation axis (will be normalized).
        center_xyz_mm: center of the circle.
        angle_deg: total sweep angle (360 for full circle).
        base_rpy_deg: base orientation composed with per-instance rotation.

    Returns:
        List of component dicts ready for ``place_components``.
    """
    ax = _normalize(axis)
    cx, cy, cz = center_xyz_mm
    components: list[dict[str, Any]] = []

    # Pick a unit vector u perpendicular to axis for the circle's local X
    if abs(ax[0]) < 0.9:
        perp = [1.0, 0.0, 0.0]
    else:
        perp = [0.0, 1.0, 0.0]
    u = _normalize(_cross(perp, ax))
    v = _cross(ax, u)  # local Y = axis × u (also perpendicular, also unit)

    # Base rotation matrix
    R_base = _rpy_to_matrix(*base_rpy_deg)

    for k in range(count):
        theta_k = math.radians(k * angle_deg / count)
        ct = math.cos(theta_k)
        st = math.sin(theta_k)

        # Position on the circle: center + radius*(cos(θ)*u + sin(θ)*v)
        px = cx + radius_mm * (ct * u[0] + st * v[0])
        py = cy + radius_mm * (ct * u[1] + st * v[1])
        pz = cz + radius_mm * (ct * u[2] + st * v[2])

        # Orientation: R_axis(θk) · R_base
        R_axis_k = _rotation_matrix_about_axis(ax, theta_k)
        R_final = _mat_mul(R_axis_k, R_base)
        rpy = _matrix_to_rpy(R_final)

        comp: dict[str, Any] = {
            "id": f"{array_id}_{k}",
            "transform": {
                "xyz_mm": [px, py, pz],
                "rpy_deg": rpy,
            },
        }
        comp.update(part)
        components.append(comp)

    return components


def _cross(a: list[float], b: list[float]) -> list[float]:
    """Cross product of two 3-vectors."""
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def expand_component_arrays(
    arrays: list[dict[str, Any]],
    existing_ids: set[str],
) -> tuple[list[dict[str, Any]], str | None]:
    """Expand all component_arrays into synthetic component entries.

    Args:
        arrays: the ``component_arrays`` list from the spec.
        existing_ids: set of already-used component ids (to detect collisions).

    Returns:
        ``(expanded_components, error)`` — list of synthetic component dicts
        to append to ``spec["components"]``, or ``(None, message)`` on
        validation/expansion failure.
    """
    expanded: list[dict[str, Any]] = []
    used_ids: set[str] = set(existing_ids)

    for i, arr in enumerate(arrays):
        array_id = arr["id"]
        count = arr["count"]
        atype = arr["type"]

        # Resolve part reference
        part: dict[str, str] = {}
        if "part" in arr:
            part = {"part": arr["part"]}
        elif "part_spec" in arr:
            part = {"part_spec": arr["part_spec"]}
        else:
            return [], f"component_arrays[{i}]: no part or part_spec"

        base_rpy = arr.get("base_rpy_deg", [0.0, 0.0, 0.0])

        if atype == "linear":
            instances = expand_linear_array(
                array_id, part, count,
                spacing_mm=arr["spacing_mm"],
                direction=arr["direction"],
                base_xyz_mm=arr.get("base_xyz_mm", [0.0, 0.0, 0.0]),
                base_rpy_deg=base_rpy,
            )
        elif atype == "circular":
            instances = expand_circular_array(
                array_id, part, count,
                radius_mm=arr["radius_mm"],
                axis=arr["axis"],
                center_xyz_mm=arr.get("center_xyz_mm", [0.0, 0.0, 0.0]),
                angle_deg=arr.get("angle_deg", 360.0),
                base_rpy_deg=base_rpy,
            )
        else:
            return [], f"component_arrays[{i}]: unknown type {atype!r}"

        # Check id collisions
        for inst in instances:
            if inst["id"] in used_ids:
                return [], (
                    f"component_arrays[{i}]: expanded id {inst['id']!r} "
                    f"collides with existing component"
                )
            used_ids.add(inst["id"])

        expanded.extend(instances)

    return expanded, None
