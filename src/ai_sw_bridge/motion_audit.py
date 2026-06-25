"""Motion Audit (W49) — drive a mate through its DOF, report collision-in-motion.

The Dynamic Kinematic Verification capability: given an assembly with a NAMED
driving mate (distance or angle), sweep the driver across a range and, at each
position, read interference (global) + minimum clearance (between a tracked
component pair). Answers the question static interference cannot: *does this
mechanism clear through its whole range of motion, and with how much margin?*

Drive mechanism (seat-proven exact, spikes/v0_2x/kinematic_motion_derisk +
kinematic_angle_confirm): the mate's driving DIMENSION via
``IModelDoc2.Parameter("D1@<mate>").SystemValue`` (SI: metres for distance,
radians for angle) + ``EditRebuild3``. The interference VOLUME tracked the
analytic kinematic overlap to the mm^3; the component rotation tracked the driven
angle to the degree.

§6.5: this DRIVES the model (a transient mutation), so it is CLI-only, NEVER MCP.
``motion_sweep`` RESTORES the original driver value at the end (net
non-destructive) and never saves the document.
"""

from __future__ import annotations

from typing import Any

from .com.earlybind import typed
from .com.sw_type_info import wrapper_module
from .observe_clearance import _find_component_by_name, read_clearance
from .observe_interference import read_interference

# swSelectType is irrelevant here; the driving dimension is named "D1@<mate>".
_DIM_PREFIX = "D1@"

_VALID_KINDS = ("distance", "angle")


def _to_si(kind: str, value: float) -> float:
    """Spec units (mm / deg) -> SI (m / rad) for the Parameter SystemValue."""
    if kind == "distance":
        return float(value) / 1000.0
    # angle
    import math

    return math.radians(float(value))


def _from_si(kind: str, value_si: float) -> float:
    if kind == "distance":
        return float(value_si) * 1000.0
    import math

    return math.degrees(float(value_si))


def read_mate_value_si(asm_doc: Any, mate_name: str) -> float | None:
    """Read the driving dimension's current SystemValue (SI), or None."""
    try:
        dim = asm_doc.Parameter(f"{_DIM_PREFIX}{mate_name}")
        if dim is None:
            return None
        sv = dim.SystemValue
        return float(sv() if callable(sv) else sv)
    except Exception:  # noqa: BLE001
        return None


def drive_mate_value_si(asm_doc: Any, mate_name: str, value_si: float, mod: Any) -> str:
    """Set the driving dimension to ``value_si`` (SI) and rebuild.

    Returns ``"parameter"`` on success or ``"FAIL:<reason>"``. The Parameter
    route is the seat-proven driver; no fallback is attempted in production (a
    miss is a real error the caller must surface, not paper over).
    """
    try:
        dim = asm_doc.Parameter(f"{_DIM_PREFIX}{mate_name}")
        if dim is None:
            return f"FAIL:no driving dimension {_DIM_PREFIX}{mate_name}"
        dim.SystemValue = value_si
        typed(asm_doc, "IModelDoc2", module=mod).EditRebuild3()
        return "parameter"
    except Exception as exc:  # noqa: BLE001
        return f"FAIL:{exc!r}"


def _positions(start: float, stop: float, steps: int) -> list[float]:
    if steps < 2:
        return [float(start)]
    return [start + (stop - start) * i / (steps - 1) for i in range(steps)]


def _interference_volume(inter: dict[str, Any]) -> float:
    vol = 0.0
    for it in inter.get("interferences", []) or []:
        vol += float(it.get("interference_volume_mm3", 0.0) or 0.0)
    return vol


def summarize_motion(profile: list[dict[str, Any]]) -> dict[str, Any]:
    """Reduce a per-position profile to a collision envelope. PURE (no COM).

    A position is COLLIDING iff ``interference_count > 0``. ``clear_ranges`` are
    the contiguous position spans with no collision; ``first_collision_position``
    is the first colliding position (or None). ``tightest_clearance_mm`` is the
    smallest positive min-clearance over the COLLISION-FREE positions (the worst
    margin before contact); None if no clearance was tracked.
    """
    if not profile:
        return {
            "collision_free": True,
            "first_collision_position": None,
            "colliding_positions": [],
            "clear_ranges": [],
            "max_interference_volume_mm3": 0.0,
            "tightest_clearance_mm": None,
        }

    colliding = [p for p in profile if (p.get("interference_count") or 0) > 0]
    first_collision = colliding[0]["position"] if colliding else None
    max_vol = max((p.get("interference_volume_mm3") or 0.0) for p in profile)

    # Contiguous clear ranges (over the ordered profile).
    clear_ranges: list[list[float]] = []
    run_start: float | None = None
    prev_pos: float | None = None
    for p in profile:
        clear = (p.get("interference_count") or 0) == 0
        pos = p["position"]
        if clear:
            if run_start is None:
                run_start = pos
            prev_pos = pos
        else:
            if run_start is not None:
                assert prev_pos is not None
                clear_ranges.append([run_start, prev_pos])
                run_start = None
    if run_start is not None:
        assert prev_pos is not None
        clear_ranges.append([run_start, prev_pos])

    # Tightest positive clearance among collision-free positions.
    gaps = [
        p["min_clearance_mm"]
        for p in profile
        if (p.get("interference_count") or 0) == 0
        and isinstance(p.get("min_clearance_mm"), (int, float))
        and p["min_clearance_mm"] > 0
    ]
    tightest = min(gaps) if gaps else None

    return {
        "collision_free": not colliding,
        "first_collision_position": first_collision,
        "colliding_positions": [p["position"] for p in colliding],
        "clear_ranges": clear_ranges,
        "max_interference_volume_mm3": round(max_vol, 3),
        "tightest_clearance_mm": (round(tightest, 4) if tightest is not None else None),
    }


def choose_clearance_pair(
    component_names: list[str],
    pair_distances: dict[tuple[str, str], float | None],
) -> tuple[str, str] | None:
    """Select the component pair with the smallest non-negative clearance. PURE.

    ``pair_distances`` maps ``(name_a, name_b)`` to min-distance in mm, or
    ``None`` when unmeasured or in error. Negative values are skipped (invalid
    measurement). Returns the nearest pair (0.0 = touching, >0 = gap), or
    ``None`` if no pair has a non-negative distance.
    """
    best_pair: tuple[str, str] | None = None
    best_dist: float = float("inf")
    for pair, dist in pair_distances.items():
        if dist is None:
            continue
        if dist < 0:
            continue
        if dist < best_dist:
            best_dist = dist
            best_pair = pair
    return best_pair


def list_component_names(asm_doc: Any, mod: Any | None = None) -> list[str]:
    """Return the display names of all components in the assembly. Seat-bound."""
    if mod is None:
        mod = wrapper_module()
    try:
        asm_typed = typed(asm_doc, "IAssemblyDoc", module=mod)
        comps = asm_typed.GetComponents(True)
    except Exception:  # noqa: BLE001
        return []
    if comps is None:
        return []
    if not isinstance(comps, (list, tuple)):
        comps = (comps,)
    names: list[str] = []
    for comp in comps:
        try:
            nm = comp.Name2
            if callable(nm):
                nm = nm()
            names.append(str(nm))
        except Exception:  # noqa: BLE001
            continue
    return names


def read_all_clearances(
    asm_doc: Any,
    component_names: list[str],
    mod: Any | None = None,
) -> dict[tuple[str, str], float | None]:
    """Measure pairwise clearance between all named components. Seat-bound.

    Returns ``{(name_a, name_b): min_distance_mm | None}`` for every unordered
    pair. ``None`` when touching/overlapping (Distance == -1.0).
    """
    if mod is None:
        mod = wrapper_module()
    distances: dict[tuple[str, str], float | None] = {}
    for i, a in enumerate(component_names):
        for b in component_names[i + 1 :]:
            clr = read_clearance(asm_doc, a, b, mod)
            if clr.get("touching"):
                distances[(a, b)] = 0.0
            elif not clr.get("errors") and clr.get("min_distance_mm") is not None:
                distances[(a, b)] = clr["min_distance_mm"]
            else:
                distances[(a, b)] = None
    return distances


def motion_sweep(
    asm_doc: Any,
    *,
    mate_name: str,
    kind: str,
    start: float,
    stop: float,
    steps: int,
    clearance_pair: tuple[str, str] | None = None,
    mod: Any | None = None,
) -> dict[str, Any]:
    """Drive ``mate_name`` from ``start`` to ``stop`` over ``steps`` and report.

    ``kind`` is ``"distance"`` (start/stop in mm) or ``"angle"`` (deg). At each
    position: drive + rebuild + interference + optional clearance between the two
    ``clearance_pair`` component names. The original driver value is RESTORED at
    the end (net non-destructive); the document is not saved.

    Returns ``{ok, profile, summary, driver, restored, errors}``.
    """
    result: dict[str, Any] = {
        "ok": False,
        "driver": {
            "mate": mate_name,
            "kind": kind,
            "from": start,
            "to": stop,
            "steps": steps,
        },
        "profile": [],
        "summary": {},
        "restored": False,
        "errors": [],
    }
    if mod is None:
        mod = wrapper_module()
    if kind not in _VALID_KINDS:
        result["errors"].append(f"kind must be one of {_VALID_KINDS}, got {kind!r}")
        return result
    if steps < 2:
        result["errors"].append("steps must be >= 2")
        return result

    original_si = read_mate_value_si(asm_doc, mate_name)
    if original_si is None:
        result["errors"].append(
            f"no driving dimension {_DIM_PREFIX}{mate_name} — the mate must be "
            f"named and carry a driving dimension (distance/angle)"
        )
        return result

    # Validate the clearance pair up front (fail loud, not per-step).
    if clearance_pair is not None:
        for nm in clearance_pair:
            if _find_component_by_name(asm_doc, nm, mod=mod) is None:
                result["errors"].append(f"clearance component not found: {nm!r}")
                clearance_pair = None
                break

    profile: list[dict[str, Any]] = []
    try:
        for pos in _positions(start, stop, steps):
            route = drive_mate_value_si(asm_doc, mate_name, _to_si(kind, pos), mod)
            entry: dict[str, Any] = {"position": round(pos, 4), "drive_route": route}
            if route.startswith("FAIL"):
                entry["interference_count"] = None
                entry["interference_volume_mm3"] = None
                entry["min_clearance_mm"] = None
                profile.append(entry)
                result["errors"].append(f"drive failed at {pos}: {route}")
                continue
            inter = read_interference(asm_doc, mod)
            entry["interference_count"] = inter.get("interference_count", 0)
            entry["interference_volume_mm3"] = round(_interference_volume(inter), 3)
            entry["min_clearance_mm"] = None
            if clearance_pair is not None:
                # read_clearance is the LOW-LEVEL reader: it returns
                # {min_distance_mm, touching, errors} directly (NOT the
                # sw_get_clearance {ok, clearance} wrapper shape).
                clr = read_clearance(asm_doc, clearance_pair[0], clearance_pair[1], mod)
                if clr.get("touching"):
                    entry["min_clearance_mm"] = 0.0
                elif not clr.get("errors") and clr.get("min_distance_mm") is not None:
                    entry["min_clearance_mm"] = clr.get("min_distance_mm")
            profile.append(entry)
    finally:
        # Restore the original driver value (net non-destructive).
        restore = drive_mate_value_si(asm_doc, mate_name, original_si, mod)
        result["restored"] = restore == "parameter"
        if not result["restored"]:
            result["errors"].append(f"restore failed: {restore}")

    result["profile"] = profile
    result["summary"] = summarize_motion(profile)
    result["ok"] = len(profile) == steps and all(
        not p["drive_route"].startswith("FAIL") for p in profile
    )
    return result
