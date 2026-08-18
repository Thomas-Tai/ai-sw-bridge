# Geometric Pre-flight + Convention Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a seat-free geometric pre-flight that catches coordinate-mapping and geometry-impossibility errors at author-time (via `ai-sw-build --lint`) instead of via a silent `FeatureCut4`-returns-`None` mid-build.

**Architecture:** A new pure module `spec/preflight.py` with two independent analyzers — an *exact* coordinate-mapping resolver (INFO echoes) and a *conservative* axis-aligned material-envelope tracker (WARNING/ERROR/SKIP). Both reuse the existing `LintFinding` type, take a spec dict, return findings, and touch no SOLIDWORKS. They are wired into the existing seat-free `--lint` path in `cli/build.py`, whose exit gating changes from "any finding" to "ERROR only." A convention-capture rider adds `docs/coordinate_conventions.md`, an `AGENTS.md` pointer, and a `hints.py` cross-reference.

**Tech Stack:** Python 3.10–3.14, stdlib only (no new deps), pytest, black/flake8/mypy, the existing `ai_sw_bridge.spec` package.

## Global Constraints

- **Seat-free.** `spec/preflight.py` and ALL its tests must run without SOLIDWORKS (no `win32com`, no COM). They run in CI on Linux.
- **Stdlib only.** No new dependencies. Match the style of `spec/lint.py`.
- **Never emit a false ERROR.** ERROR severity is reserved for the one provable case (empty-air cut, region ∩ material = ∅, fully modeled). Everything uncertain is WARNING or SKIP.
- **Keep `spec/lint.py` behavior unchanged.** `lint()` stays pure; `test_lint.py` passes unchanged. The pre-flight is a *separate* function, not folded into `lint()`.
- **No-false-positive invariant (CI-locked):** every buildable example spec (`examples/*/spec.json`, `examples/*/spec_parametric.json`) must pre-flight with ZERO warning/error findings (INFO echoes allowed).
- **Honesty gate (L6):** `docs/coordinate_conventions.md` lives under `docs/**` and IS scanned by `tools/honesty_gate.py`. It must never contain a bare `ai-sw-export` — the only real export CLI is `ai-sw-export-dxf-flat`; `ai-sw-import` is the import CLI. No placeholders.
- **New modules ≤ 800 LOC** (`tools/module_size_gate.py --strict`). `preflight.py` is one focused module.
- **doc_coverage_gate:** every new public function in `preflight.py` needs a docstring.
- **black / flake8 / mypy clean; every check ships with tests.**
- **No `Co-Authored-By: Claude` trailer on any commit.**
- **Windows dev paths contain `[` (a glob metachar) — quote all shell paths.** CI runs POSIX.

## File Structure

- Create `src/ai_sw_bridge/spec/preflight.py` — the two analyzers + `preflight()` aggregator. One responsibility: seat-free geometric analysis of a spec.
- Modify `src/ai_sw_bridge/spec/lint.py` — extend the `LintFinding.severity` docstring to include `"info"` (no behavior change).
- Modify `src/ai_sw_bridge/cli/build.py` — call `preflight()` in the `--lint` path, add `--no-preflight`, change exit gating to ERROR-only.
- Modify `src/ai_sw_bridge/errors/hints.py` — add the `empty_air_cut` hint + cross-refs.
- Create `docs/coordinate_conventions.md` — the convention reference.
- Modify `docs/AGENTS.md` — a short "run `--lint` first" pointer + link.
- Create `tests/test_preflight.py` — unit tests for both analyzers and the check catalog.
- Create `tests/test_preflight_examples.py` — the no-false-positive invariant over the example corpus.
- Modify (if present) any CLI test asserting the old "any-finding → exit 6" gating.

## Reference: data shapes (from the live codebase)

`LintFinding(severity: str, path: str, message: str)` with `.to_dict()` → `{"severity","path","message"}` and `.severity` in `{"info","warning","error"}` (this plan adds `"info"`).

Feature dicts (real, from `examples/drilled_plate/spec.json`):

```json
{"type":"sketch_rectangle_on_plane","name":"SK_Plate","plane":"Front","width":40.0,"height":30.0}
{"type":"boss_extrude_blind","name":"EX_Plate","sketch":"SK_Plate","depth":10.0}
{"type":"simple_hole","name":"Hole_Blind","of_feature":"EX_Plate","face":"+z","center":{"u":10.0,"v":0.0},"diameter":5.0,"end_condition":"blind","depth":6.0}
```

Feature-type sets (from `spec/schema.py`): `SKETCH_TYPES` (incl. `sketch_rectangle_on_plane`, `sketch_circle_on_plane`, `sketch_polyline_on_plane`, `sketch_3d_sketch`, …), `EXTRUDE_TYPES` (`boss_extrude_blind/midplane/through_all/two_direction/up_to_surface`, `cut_extrude_through_all/blind/midplane/two_direction`, `revolve_boss`, `revolve_cut`), `MODIFY_TYPES` (`fillet_constant_radius`, `chamfer_edge`, `simple_hole`).

**Plane→part mapping (authoritative; sketch-local `(u,v)`, plane offset `o` along the normal):**

| Plane | `X` | `Y` | `Z` |
|-------|-----|-----|-----|
| Front | `u` | `v` | `o` |
| Top   | `u` | `o` | `-v` |
| Right | `o` | `v` | `-u` |

**Box-face local mapping (for on-face sketches / holes), modeled faces only:**

| Face | `u` → | `v` → | face lies at |
|------|-------|-------|--------------|
| `+z` / `-z` | `X` | `Y` | `Z = zmax` / `zmin` |

Other faces (`±x`, `±y`) honest-skip in v0.11.

---

### Task 1: Coordinate-mapping resolver (Component 1, exact — INFO echoes)

**Files:**
- Create: `src/ai_sw_bridge/spec/preflight.py`
- Test: `tests/test_preflight.py`

**Interfaces:**
- Consumes: `LintFinding` from `ai_sw_bridge.spec.lint`.
- Produces:
  - `PLANE_AXES: dict[str, tuple[str, str, str]]` — plane name → (X-expr, Y-expr, Z-expr) using tokens `"u"`, `"v"`, `"-v"`, `"-u"`, `"o"`.
  - `map_plane_point(plane: str, u: float, v: float, offset: float) -> tuple[float, float, float]` — sketch-local point → part-frame `(x, y, z)`; raises `KeyError` on unknown plane (caller guards).
  - `coordinate_mapping_report(spec: dict) -> list[LintFinding]` — one `severity="info"` finding per plane-sketch with a rectangle/circle profile, naming the part-frame spans.
  - `_plane_center_uvo(plane: str, center: dict) -> tuple[float, float, float]` — project a part-frame sketch `center` `{x,y,z}` (mm) to sketch-local `(u, v)` plus the plane's out-of-plane offset `o`, consistent with `PLANE_AXES`: Front→`(x, y, z)`, Top→`(x, −z, y)`, Right→`(−z, y, x)`. The real schema's plane-sketch `center` is part-frame (`descriptors.py` `_SKETCH_PLANE_CENTER`, `additionalProperties:False`, keys `x/y/z`); the builder projects it per-plane (`sketches/rectangle_on_plane.py`). Reused by Task 2's `_plane_rect_box`. `_rect_uv_extent(feat, cu, cv)` now takes the projected center.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_preflight.py
from __future__ import annotations

import pytest

from ai_sw_bridge.spec.preflight import (
    map_plane_point,
    coordinate_mapping_report,
)


def test_map_front_is_identity_xy():
    assert map_plane_point("Front", 10.0, 5.0, 0.0) == (10.0, 5.0, 0.0)


def test_map_top_v_maps_to_negative_z():
    # Top (XZ, normal +Y): u->X, v->-Z, offset->Y
    assert map_plane_point("Top", 10.0, 5.0, 40.0) == (10.0, 40.0, -5.0)


def test_map_right_u_maps_to_negative_z():
    # Right (YZ, normal +X): u->-Z, v->Y, offset->X
    assert map_plane_point("Right", 10.0, 5.0, 0.0) == (0.0, 5.0, -10.0)


def test_coordinate_echo_reports_part_spans_for_top_rect():
    spec = {
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Groove",
                "plane": "Top",
                "width": 40.0,
                "height": 30.0,
            }
        ]
    }
    findings = coordinate_mapping_report(spec)
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == "info"
    # width(u)->X spans [-20,20]; height(v)->-Z spans [-15,15]
    assert "X[-20.0, 20.0]" in f.message
    assert "Z[-15.0, 15.0]" in f.message


def test_coordinate_echo_ignores_on_face_sketches():
    # on-face sketches have no plane; they are Component-2 territory
    spec = {"features": [{"type": "simple_hole", "name": "H", "face": "+z"}]}
    assert coordinate_mapping_report(spec) == []


def test_top_rect_with_offset_center_shifts_z_span():
    # O-ring groove at mid-length of a +Z shaft: Top plane, center z=40.
    # center.z must map through v->-Z so the span centers on Z=40, not 0.
    spec = {
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Groove",
                "plane": "Top",
                "width": 40.0,
                "height": 30.0,
                "center": {"x": 0.0, "z": 40.0},
            }
        ]
    }
    f = coordinate_mapping_report(spec)[0]
    assert "Z[25.0, 55.0]" in f.message  # 40 +/- 15, not [-15, 15]


def test_map_plane_point_unknown_plane_raises():
    with pytest.raises(KeyError):
        map_plane_point("Bogus", 0.0, 0.0, 0.0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src python -m pytest tests/test_preflight.py -q`
Expected: FAIL — `ModuleNotFoundError: ai_sw_bridge.spec.preflight`.

- [ ] **Step 3: Implement the resolver**

```python
# src/ai_sw_bridge/spec/preflight.py
"""Seat-free geometric pre-flight for ai-sw-build specs.

Two independent analyzers, both pure functions over the spec dict that
return ``LintFinding`` lists and never touch SOLIDWORKS:

1. ``coordinate_mapping_report`` — exact, deterministic INFO echoes of the
   part-frame coordinates each plane-sketch maps to (Component 1).
2. ``material_envelope_scan`` — a conservative axis-aligned material model
   that flags empty-air cuts and off-material on-face sketches, and
   honestly SKIPS any feature it cannot model exactly (Component 2).

Wired into ``ai-sw-build --lint`` via ``preflight``. See
docs/superpowers/specs/2026-08-18-geometric-preflight-design.md and
docs/coordinate_conventions.md.
"""

from __future__ import annotations

from typing import Any, Optional

from .lint import LintFinding

# Plane name -> (X, Y, Z) token exprs over sketch-local u, v and offset o.
PLANE_AXES: dict[str, tuple[str, str, str]] = {
    "Front": ("u", "v", "o"),
    "Top": ("u", "o", "-v"),
    "Right": ("o", "v", "-u"),
}


def _eval_axis(token: str, u: float, v: float, o: float) -> float:
    return {"u": u, "-u": -u, "v": v, "-v": -v, "o": o}[token]


def map_plane_point(
    plane: str, u: float, v: float, offset: float
) -> tuple[float, float, float]:
    """Map a sketch-local point (u, v) on ``plane`` to part-frame (x, y, z).

    ``offset`` is the plane's position along its own normal (0 for the
    standard planes through the origin). Raises KeyError on unknown plane.
    """
    ax, ay, az = PLANE_AXES[plane]
    return (
        _eval_axis(ax, u, v, offset),
        _eval_axis(ay, u, v, offset),
        _eval_axis(az, u, v, offset),
    )


def _plane_center_uvo(
    plane: str, center: dict[str, Any]
) -> tuple[float, float, float]:
    """Project a part-frame sketch ``center`` {x, y, z} (mm) to sketch-local
    (u, v) plus the plane's out-of-plane offset o, consistent with
    ``PLANE_AXES``: Front->(x, y, z); Top->(x, -z, y); Right->(-z, y, x).

    The real schema's plane-sketch ``center`` is part-frame (see
    descriptors.py ``_SKETCH_PLANE_CENTER``); the builder projects it
    per-plane (sketches/rectangle_on_plane.py). Front is identity in x/y;
    Top and Right carry the out-of-plane component that must NOT be dropped.
    """
    x = float(center.get("x", 0.0))
    y = float(center.get("y", 0.0))
    z = float(center.get("z", 0.0))
    if plane == "Top":
        return x, -z, y
    if plane == "Right":
        return -z, y, x
    return x, y, z  # Front (and default)


def _rect_uv_extent(
    feat: dict[str, Any], cu: float, cv: float
) -> Optional[tuple[float, float, float, float]]:
    """Return (umin, umax, vmin, vmax) for a rectangle/circle plane-sketch
    centered at sketch-local (cu, cv), or None if the feature carries no
    modelable planar profile."""
    if "width" in feat and "height" in feat:
        w, h = float(feat["width"]), float(feat["height"])
        return (cu - w / 2, cu + w / 2, cv - h / 2, cv + h / 2)
    if "diameter" in feat:
        r = float(feat["diameter"]) / 2
        return (cu - r, cu + r, cv - r, cv + r)
    return None


def coordinate_mapping_report(spec: dict[str, Any]) -> list[LintFinding]:
    """Emit one INFO finding per plane-sketch naming its part-frame spans.

    Exact (a linear transform of declared coordinates) — zero
    false-positive risk. On-face sketches (no ``plane``) are skipped;
    they are handled by ``material_envelope_scan``.
    """
    findings: list[LintFinding] = []
    for i, feat in enumerate(spec.get("features", [])):
        plane = feat.get("plane", "")
        if plane not in PLANE_AXES:
            continue
        cu, cv, offset = _plane_center_uvo(plane, feat.get("center", {}) or {})
        extent = _rect_uv_extent(feat, cu, cv)
        if extent is None:
            continue
        umin, umax, vmin, vmax = extent
        xs, ys, zs = [], [], []
        for u, v in ((umin, vmin), (umax, vmax)):
            x, y, z = map_plane_point(plane, u, v, offset)
            xs.append(x)
            ys.append(y)
            zs.append(z)
        msg = (
            f"{plane} sketch '{feat.get('name', '')}': part spans "
            f"X[{min(xs)}, {max(xs)}], Y[{min(ys)}, {max(ys)}], "
            f"Z[{min(zs)}, {max(zs)}] (plane offset {offset})"
        )
        findings.append(
            LintFinding(severity="info", path=f"features/{i}/plane", message=msg)
        )
    return findings
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src python -m pytest tests/test_preflight.py -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/ai_sw_bridge/spec/preflight.py tests/test_preflight.py
git commit -m "feat(preflight): exact coordinate-mapping resolver (INFO echoes)"
```

---

### Task 2: Material-envelope tracker (Component 2 — C1 empty-air ERROR, C2 off-material WARNING, honest-skip)

**Files:**
- Modify: `src/ai_sw_bridge/spec/preflight.py`
- Test: `tests/test_preflight.py`

**Interfaces:**
- Consumes: `map_plane_point`, `PLANE_AXES` (Task 1).
- Produces:
  - `Box = tuple[float, float, float, float, float, float]` (xmin,xmax,ymin,ymax,zmin,zmax).
  - `material_envelope_scan(spec: dict) -> list[LintFinding]`.
  - Internal helpers: `_boxes_overlap(a: Box, b: Box) -> bool`, `_boss_box(feat, sketch) -> Optional[Box]`, `_hole_offface_finding(...)`.

Semantics: walk features in order maintaining `material: list[Box]`. `boss_extrude_blind` of a `sketch_rectangle_on_plane` adds a box (sketch extent × depth along the plane normal). `simple_hole` on a modeled `+z`/`-z` face checks the hole center ± radius lies within the union X/Y extent of material at that face; if fully outside → C2 WARNING. A `cut_extrude_blind` of a plane-rectangle whose swept box is disjoint from all material → C1 ERROR. Any feature not in the modeled set → append an INFO SKIP note and, for body-modifying skips, stop trusting the material model for downstream C1/C2 (set a `modeled_complete=False` flag so no false ERROR fires later).

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_preflight.py
from ai_sw_bridge.spec.preflight import material_envelope_scan

_PLATE = {
    "type": "sketch_rectangle_on_plane",
    "name": "SK_Plate",
    "plane": "Front",
    "width": 40.0,
    "height": 30.0,
}
_BOSS = {
    "type": "boss_extrude_blind",
    "name": "EX_Plate",
    "sketch": "SK_Plate",
    "depth": 10.0,
}


def _sev(findings, sev):
    return [f for f in findings if f.severity == sev]


def test_clean_plate_with_on_material_hole_has_no_warn_or_error():
    spec = {
        "features": [
            _PLATE,
            _BOSS,
            {
                "type": "simple_hole",
                "name": "H1",
                "of_feature": "EX_Plate",
                "face": "+z",
                "center": {"u": 10.0, "v": 0.0},
                "diameter": 5.0,
            },
        ]
    }
    findings = material_envelope_scan(spec)
    assert _sev(findings, "warning") == []
    assert _sev(findings, "error") == []


def test_hole_off_the_face_warns():
    spec = {
        "features": [
            _PLATE,
            _BOSS,
            {
                "type": "simple_hole",
                "name": "H_off",
                "of_feature": "EX_Plate",
                "face": "+z",
                "center": {"u": 50.0, "v": 0.0},  # face is X in [-20, 20]
                "diameter": 5.0,
            },
        ]
    }
    warns = _sev(material_envelope_scan(spec), "warning")
    assert any("H_off" in f.message and "off" in f.message.lower() for f in warns)


def test_empty_air_cut_errors():
    spec = {
        "features": [
            _PLATE,
            _BOSS,
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Air",
                "plane": "Front",
                "width": 5.0,
                "height": 5.0,
                "center": {"x": 100.0, "y": 100.0},  # far from the plate
            },
            {
                "type": "cut_extrude_blind",
                "name": "CUT_Air",
                "sketch": "SK_Air",
                "depth": 5.0,
            },
        ]
    }
    errs = _sev(material_envelope_scan(spec), "error")
    assert any("CUT_Air" in f.message for f in errs)


def test_revolve_is_skipped_not_flagged():
    spec = {
        "features": [
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_Rev",
                "plane": "Top",
                "width": 10.0,
                "height": 10.0,
                "centerline": True,
            },
            {"type": "revolve_boss", "name": "REV", "sketch": "SK_Rev"},
            {
                "type": "cut_extrude_blind",
                "name": "CUT_X",
                "sketch": "SK_Rev",
                "depth": 2.0,
            },
        ]
    }
    findings = material_envelope_scan(spec)
    assert _sev(findings, "error") == []  # no false ERROR after an unmodeled body
    assert any(f.severity == "info" and "skip" in f.message.lower() for f in findings)


def test_flipped_cut_into_material_is_not_flagged():
    # A cut sketched on the +Z top face (Front plane, center z=10) with
    # flip=True cuts INWARD into real material (Z[5, 10]); the tracker must
    # model -normal and NOT fire a false empty-air ERROR. With the old
    # +normal-only code the box was Z[10, 15] (disjoint) -> false ERROR.
    spec = {
        "features": [
            _PLATE,
            _BOSS,  # material Z in [0, 10]
            {
                "type": "sketch_rectangle_on_plane",
                "name": "SK_TopCut",
                "plane": "Front",
                "width": 10.0,
                "height": 10.0,
                "center": {"z": 10.0},  # top face of the plate
            },
            {
                "type": "cut_extrude_blind",
                "name": "CUT_In",
                "sketch": "SK_TopCut",
                "depth": 5.0,
                "flip": True,  # cut -Z, into the plate
            },
        ]
    }
    assert _sev(material_envelope_scan(spec), "error") == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONPATH=src python -m pytest tests/test_preflight.py -q`
Expected: FAIL — `material_envelope_scan` not defined.

- [ ] **Step 3: Implement the tracker**

```python
# append to src/ai_sw_bridge/spec/preflight.py

Box = tuple[float, float, float, float, float, float]

# Feature types the axis-aligned box model represents exactly.
_MODELED_ADDITIVE = frozenset({"boss_extrude_blind"})
_MODELED_SUBTRACTIVE = frozenset({"cut_extrude_blind"})


def _boxes_overlap(a: Box, b: Box) -> bool:
    return (
        a[0] < b[1] and b[0] < a[1]  # x
        and a[2] < b[3] and b[2] < a[3]  # y
        and a[4] < b[5] and b[4] < a[5]  # z
    )


def _plane_rect_box(feat: dict[str, Any]) -> Optional[Box]:
    """Part-frame box of a plane rectangle extruded ``depth`` along its
    normal, or None if not a modelable plane rectangle."""
    plane = feat.get("plane", "")
    if plane not in PLANE_AXES or "width" not in feat or "height" not in feat:
        return None
    cu, cv, offset = _plane_center_uvo(plane, feat.get("center", {}) or {})
    extent = _rect_uv_extent(feat, cu, cv)
    if extent is None:
        return None
    umin, umax, vmin, vmax = extent
    xs, ys, zs = [], [], []
    for u in (umin, umax):
        for v in (vmin, vmax):
            x, y, z = map_plane_point(plane, u, v, offset)
            xs.append(x)
            ys.append(y)
            zs.append(z)
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


def _extruded_box(
    sketch: dict[str, Any], depth: float, flip: bool = False
) -> Optional[Box]:
    """Part-frame box of a plane rectangle extruded ``depth`` along the plane
    normal, or None if ``sketch`` is not a modelable plane rectangle.

    ``flip`` honors the schema's boss/cut ``flip`` field: False sweeps
    +normal (``[lo, lo + depth]``), True sweeps -normal (``[lo - depth, lo]``)
    -- e.g. a blind cut on a top face flipped to cut inward into material.
    A sketch is zero-thickness along its own normal (``lo == hi ==`` the plane
    offset), so the swept box grows from that single offset value.
    """
    base = _plane_rect_box(sketch)
    if base is None:
        return None
    plane = sketch.get("plane", "")
    normal_axis = {"Front": 2, "Top": 1, "Right": 0}[plane]
    lo = min(base[normal_axis * 2], base[normal_axis * 2 + 1])
    box = list(base)
    if flip:
        box[normal_axis * 2] = lo - depth
        box[normal_axis * 2 + 1] = lo
    else:
        box[normal_axis * 2] = lo
        box[normal_axis * 2 + 1] = lo + depth
    return (box[0], box[1], box[2], box[3], box[4], box[5])


def material_envelope_scan(spec: dict[str, Any]) -> list[LintFinding]:
    """Conservative axis-aligned material model. Flags empty-air cuts
    (ERROR) and off-face on-face sketches (WARNING). Any feature the box
    model cannot represent honest-SKIPS (INFO) and marks the model
    incomplete so no false ERROR fires downstream."""
    features = spec.get("features", [])
    sketches = {
        f.get("name", ""): f for f in features if f.get("plane") in PLANE_AXES
    }
    material: list[Box] = []
    modeled_complete = True
    findings: list[LintFinding] = []

    for i, feat in enumerate(features):
        ftype = feat.get("type", "")
        name = feat.get("name", "")

        if ftype in _MODELED_ADDITIVE:
            box = _extruded_box(
                sketches.get(feat.get("sketch", ""), {}),
                float(feat.get("depth", 0.0)),
                bool(feat.get("flip", False)),
            )
            if box is None:
                modeled_complete = False
                findings.append(_skip(i, name, ftype))
            else:
                material.append(box)

        elif ftype in _MODELED_SUBTRACTIVE:
            box = _extruded_box(
                sketches.get(feat.get("sketch", ""), {}),
                float(feat.get("depth", 0.0)),
                bool(feat.get("flip", False)),
            )
            if box is None:
                modeled_complete = False
                findings.append(_skip(i, name, ftype))
            elif modeled_complete and material and not any(_boxes_overlap(box, m) for m in material):
                findings.append(
                    LintFinding(
                        severity="error",
                        path=f"features/{i}/{name}",
                        message=(
                            f"cut '{name}' sweeps a region disjoint from all "
                            f"modeled material -- this is an empty-air cut and "
                            f"SW will return None. Check the sketch plane, "
                            f"coordinates, and offset (see "
                            f"docs/coordinate_conventions.md)."
                        ),
                    )
                )

        elif ftype == "simple_hole":
            findings.extend(_hole_offface_finding(i, feat, material, modeled_complete))

        elif ftype in {"boss_extrude_midplane", "boss_extrude_two_direction"}:
            # additive but not yet modeled -> conservative: mark incomplete
            modeled_complete = False
            findings.append(_skip(i, name, ftype))

        else:
            # sketches carry no body; every other feature type is unmodeled.
            if ftype not in PLANE_AXES and ftype not in _SKETCH_ONLY_QUIET:
                findings.append(_skip(i, name, ftype))
                if ftype not in _NON_BODY_TYPES:
                    modeled_complete = False

    return findings


# Sketch/echo-only types that should not emit a SKIP note (they add no body).
_SKETCH_ONLY_QUIET = frozenset(
    {
        "sketch_rectangle_on_plane",
        "sketch_circle_on_plane",
        "sketch_circles_on_face",
        "sketch_rectangle_on_face",
        "sketch_circle_on_face",
    }
)
# Types that do not modify the solid body (so a SKIP does not invalidate the model).
_NON_BODY_TYPES = frozenset({"linear_pattern", "circular_pattern", "mirror_feature"})


def _skip(i: int, name: str, ftype: str) -> LintFinding:
    return LintFinding(
        severity="info",
        path=f"features/{i}/{name}",
        message=(
            f"pre-flight skip: '{name}' ({ftype}) is not modeled by the "
            f"axis-aligned envelope; downstream geometry checks are relaxed."
        ),
    )


def _hole_offface_finding(
    i: int, feat: dict[str, Any], material: list[Box], modeled_complete: bool
) -> list[LintFinding]:
    face = feat.get("face", "")
    if face not in {"+z", "-z"} or not material or not modeled_complete:
        return []
    center = feat.get("center", {}) or {}
    cu = float(center.get("u", 0.0))
    cv = float(center.get("v", 0.0))
    r = float(feat.get("diameter", 0.0)) / 2
    # +z/-z face: u->X, v->Y; check the hole footprint against material X/Y union
    xmin = min(m[0] for m in material)
    xmax = max(m[1] for m in material)
    ymin = min(m[2] for m in material)
    ymax = max(m[3] for m in material)
    on = (xmin <= cu - r and cu + r <= xmax and ymin <= cv - r and cv + r <= ymax)
    if on:
        return []
    return [
        LintFinding(
            severity="warning",
            path=f"features/{i}/center",
            message=(
                f"hole '{feat.get('name', '')}' center ({cu}, {cv}) r{r} lands "
                f"off the modeled {face} face (X[{xmin}, {xmax}], "
                f"Y[{ymin}, {ymax}]) -- it may miss material."
            ),
        )
    ]
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src python -m pytest tests/test_preflight.py -q`
Expected: PASS (all Task 1 + Task 2 tests).

- [ ] **Step 5: black/flake8/mypy the module**

Run: `PYTHONPATH=src python -m black src/ai_sw_bridge/spec/preflight.py tests/test_preflight.py && python -m flake8 src/ai_sw_bridge/spec/preflight.py && python -m mypy --config-file mypy.ini src/ai_sw_bridge/spec/preflight.py`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/ai_sw_bridge/spec/preflight.py tests/test_preflight.py
git commit -m "feat(preflight): axis-aligned material tracker (empty-air cut, off-face hole, honest-skip)"
```

---

### Task 3: Degenerate-profile (C4) checks + `preflight()` aggregator

**Files:**
- Modify: `src/ai_sw_bridge/spec/preflight.py`
- Test: `tests/test_preflight.py`

**Interfaces:**
- Produces:
  - `_degenerate_profile_checks(spec: dict) -> list[LintFinding]` — WARNING for a `sketch_polyline_on_plane` that is `closed:false` but consumed by a boss/cut, a construction-only sketch, or a self-intersecting polyline.
  - `preflight(spec: dict) -> list[LintFinding]` — concatenation of `coordinate_mapping_report` + `material_envelope_scan` + `_degenerate_profile_checks`.

(Fillet-vs-edge C5 is folded here as a WARNING only when the adjacent edge is modeled; if the fillet's owning body is unmodeled it skips. Keep it minimal: warn when `fillet_constant_radius` radius ≥ half the smallest span of the most-recent modeled box.)

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_preflight.py
from ai_sw_bridge.spec.preflight import preflight, _degenerate_profile_checks


def test_open_polyline_consumed_by_boss_warns():
    spec = {
        "features": [
            {
                "type": "sketch_polyline_on_plane",
                "name": "SK_Open",
                "plane": "Front",
                "points": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}],
                "closed": False,
            },
            {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK_Open", "depth": 5.0},
        ]
    }
    warns = [f for f in _degenerate_profile_checks(spec) if f.severity == "warning"]
    assert any("SK_Open" in f.message and "closed" in f.message.lower() for f in warns)


def test_preflight_aggregates_all_three_analyzers():
    spec = {"features": [_PLATE, _BOSS]}
    findings = preflight(spec)
    # coordinate echo (info) present, no warning/error on a clean plate
    assert any(f.severity == "info" for f in findings)
    assert [f for f in findings if f.severity in ("warning", "error")] == []
```

- [ ] **Step 2: Run to verify fail**

Run: `PYTHONPATH=src python -m pytest tests/test_preflight.py::test_open_polyline_consumed_by_boss_warns tests/test_preflight.py::test_preflight_aggregates_all_three_analyzers -q`
Expected: FAIL — names not defined.

- [ ] **Step 3: Implement**

```python
# append to src/ai_sw_bridge/spec/preflight.py

def _degenerate_profile_checks(spec: dict[str, Any]) -> list[LintFinding]:
    """WARNING for spec-detectable degenerate profiles: an open polyline
    consumed by a boss/cut, or a construction-only sketch. These map to
    the post-mortem hints (sketch_open_contour_needed_closed,
    sketch_construction_only) in errors/hints.py, promoted to pre-build."""
    features = spec.get("features", [])
    consumed = {
        f.get("sketch", "")
        for f in features
        if f.get("type", "").endswith(("_blind", "_midplane", "_two_direction", "_through_all"))
    }
    findings: list[LintFinding] = []
    for i, feat in enumerate(features):
        name = feat.get("name", "")
        if feat.get("type") == "sketch_polyline_on_plane":
            if feat.get("closed", True) is False and name in consumed:
                findings.append(
                    LintFinding(
                        severity="warning",
                        path=f"features/{i}/closed",
                        message=(
                            f"polyline sketch '{name}' is closed:false but is "
                            f"consumed by a boss/cut, which needs a closed "
                            f"profile -- SW raises 'No closed profile'. Close "
                            f"the contour (see errors/hints.py "
                            f"sketch_open_contour_needed_closed)."
                        ),
                    )
                )
            if feat.get("construction", False) is True:
                findings.append(
                    LintFinding(
                        severity="warning",
                        path=f"features/{i}/construction",
                        message=(
                            f"sketch '{name}' is construction-only; a boss/cut "
                            f"has no real entities to sweep (see errors/hints.py "
                            f"sketch_construction_only)."
                        ),
                    )
                )
    return findings


def preflight(spec: dict[str, Any]) -> list[LintFinding]:
    """Run all seat-free geometric pre-flight analyzers over ``spec``.

    Returns INFO coordinate echoes, WARNING advisories, and at most one
    ERROR per provable empty-air cut. Never raises; never touches SW.
    """
    findings: list[LintFinding] = []
    findings.extend(coordinate_mapping_report(spec))
    findings.extend(material_envelope_scan(spec))
    findings.extend(_degenerate_profile_checks(spec))
    return findings
```

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src python -m pytest tests/test_preflight.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ai_sw_bridge/spec/preflight.py tests/test_preflight.py
git commit -m "feat(preflight): degenerate-profile checks + preflight() aggregator"
```

---

### Task 4: Wire `preflight()` into `--lint` with ERROR-only exit gating + `--no-preflight`

**Files:**
- Modify: `src/ai_sw_bridge/cli/build.py:809-825` (lint-only path)
- Modify: `src/ai_sw_bridge/spec/lint.py:20-23` (LintFinding severity docstring: add `"info"`)
- Test: `tests/test_preflight_cli.py` (new)

**Interfaces:**
- Consumes: `preflight` from `ai_sw_bridge.spec.preflight`.
- The `--lint` JSON payload gains `preflight` findings merged into `findings`; `ok` and exit become ERROR-gated.

- [ ] **Step 1: Extend the LintFinding severity docstring (no behavior change)**

In `src/ai_sw_bridge/spec/lint.py`, change the comment on line 21 from
`self.severity = severity  # "warning" or "error"` to
`self.severity = severity  # "info", "warning", or "error"`.

- [ ] **Step 2: Write the failing CLI tests**

```python
# tests/test_preflight_cli.py
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(spec: dict, tmp_path: Path, *extra: str):
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec))
    env = {"PYTHONPATH": str(ROOT / "src")}
    import os

    env = {**os.environ, **env}
    r = subprocess.run(
        [sys.executable, "-m", "ai_sw_bridge.cli.build", str(p), "--lint", *extra],
        capture_output=True, text=True, env=env,
    )
    return r.returncode, json.loads(r.stdout)


_CLEAN = {
    "schema_version": 1,
    "name": "Clean",
    "features": [
        {"type": "sketch_rectangle_on_plane", "name": "SK", "plane": "Front", "width": 40, "height": 30},
        {"type": "boss_extrude_blind", "name": "EX", "sketch": "SK", "depth": 10},
    ],
}


def test_clean_spec_exits_zero_with_info_echoes(tmp_path):
    rc, payload = _run(_CLEAN, tmp_path)
    assert rc == 0
    assert payload["ok"] is True
    assert any(f["severity"] == "info" for f in payload["findings"])


def test_empty_air_cut_exits_six(tmp_path):
    spec = json.loads(json.dumps(_CLEAN))
    spec["features"] += [
        {"type": "sketch_rectangle_on_plane", "name": "SKA", "plane": "Front", "width": 5, "height": 5, "center": {"x": 100, "y": 100}},
        {"type": "cut_extrude_blind", "name": "CUTA", "sketch": "SKA", "depth": 5},
    ]
    rc, payload = _run(spec, tmp_path)
    assert rc == 6
    assert payload["ok"] is False
    assert any(f["severity"] == "error" and "CUTA" in f["message"] for f in payload["findings"])


def test_no_preflight_suppresses_geometry_findings(tmp_path):
    spec = json.loads(json.dumps(_CLEAN))
    spec["features"] += [
        {"type": "sketch_rectangle_on_plane", "name": "SKA", "plane": "Front", "width": 5, "height": 5, "center": {"x": 100, "y": 100}},
        {"type": "cut_extrude_blind", "name": "CUTA", "sketch": "SKA", "depth": 5},
    ]
    rc, payload = _run(spec, tmp_path, "--no-preflight")
    assert rc == 0  # empty-air ERROR suppressed
```

- [ ] **Step 3: Run to verify fail**

Run: `PYTHONPATH=src python -m pytest tests/test_preflight_cli.py -q`
Expected: FAIL (no `--no-preflight` flag; clean spec currently exits 0 but has no info echoes; empty-air spec currently exits 0 not 6).

- [ ] **Step 4: Add the `--no-preflight` flag**

In `build.py`'s argparse setup (near the `--lint` definition around line 399), add:

```python
    parser.add_argument(
        "--no-preflight",
        dest="no_preflight",
        action="store_true",
        help=(
            "Skip the seat-free geometric pre-flight (coordinate-mapping "
            "echoes + material-envelope checks). Semantic lint still runs."
        ),
    )
```

- [ ] **Step 5: Merge preflight findings + ERROR-only gating**

Replace the lint-only block at `build.py:811-825` with:

```python
    lint_findings = spec_lint(spec)
    if not getattr(args, "no_preflight", False):
        from ..spec.preflight import preflight

        lint_findings = lint_findings + preflight(spec)
    lint_payload = [f.to_dict() for f in lint_findings]
    has_error = any(f.severity == "error" for f in lint_findings)

    if args.lint and not (args.no_dim or args.deferred_dim):
        dry_run_payload = _dry_run(spec) if args.dry_run or args.lint else None
        payload: dict[str, Any] = {
            "ok": not has_error,
            "lint": True,
            "findings": lint_payload,
            "finding_count": len(lint_findings),
            "error_count": sum(1 for f in lint_findings if f.severity == "error"),
            "warning_count": sum(1 for f in lint_findings if f.severity == "warning"),
        }
        if dry_run_payload is not None:
            payload["dry_run"] = dry_run_payload
        return _emit(payload, 0 if not has_error else 6)
```

- [ ] **Step 6: Run the CLI tests + the existing lint/build tests**

Run: `PYTHONPATH=src python -m pytest tests/test_preflight_cli.py tests/test_lint.py -q`
Expected: PASS. If any pre-existing test in `tests/` asserted the old "any-finding → exit 6 / ok:false" gating, update it to the ERROR-only contract (search: `grep -rn "== 6" tests/ | grep -i lint`).

- [ ] **Step 7: Commit**

```bash
git add src/ai_sw_bridge/cli/build.py src/ai_sw_bridge/spec/lint.py tests/test_preflight_cli.py
git commit -m "feat(preflight): wire into --lint with ERROR-only gating and --no-preflight"
```

---

### Task 5: No-false-positive invariant over the example corpus (CI-locked)

**Files:**
- Test: `tests/test_preflight_examples.py` (new)

**Interfaces:**
- Consumes: `preflight` from `ai_sw_bridge.spec.preflight`.

- [ ] **Step 1: Write the invariant test**

```python
# tests/test_preflight_examples.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_sw_bridge.spec.preflight import preflight

ROOT = Path(__file__).resolve().parents[1]
SPECS = sorted(
    p
    for p in ROOT.glob("examples/*/*.json")
    if p.name in ("spec.json", "spec_parametric.json")
)


@pytest.mark.parametrize("spec_path", SPECS, ids=lambda p: p.parent.name + "/" + p.name)
def test_example_preflights_without_warn_or_error(spec_path: Path):
    spec = json.loads(spec_path.read_text())
    bad = [f for f in preflight(spec) if f.severity in ("warning", "error")]
    assert bad == [], (
        f"{spec_path} produced non-info pre-flight findings (false positives): "
        + "; ".join(str(f) for f in bad)
    )


def test_corpus_is_non_empty():
    assert SPECS, "expected example specs under examples/*/"
```

- [ ] **Step 2: Run it**

Run: `PYTHONPATH=src python -m pytest tests/test_preflight_examples.py -q`
Expected: PASS for every example. **If any example legitimately trips a WARNING/ERROR, that is a false positive — fix the analyzer (usually by widening honest-skip), not the test.** Turned parts (`drive_roller`, `grooved_shaft`, `minimal_cylinder`, `patterned_disc`) must land as INFO skips.

- [ ] **Step 3: Commit**

```bash
git add tests/test_preflight_examples.py
git commit -m "test(preflight): no-false-positive invariant over example corpus"
```

---

### Task 6: Convention-capture rider (docs + hint cross-refs)

**Files:**
- Create: `docs/coordinate_conventions.md`
- Modify: `docs/AGENTS.md`
- Modify: `src/ai_sw_bridge/errors/hints.py`
- Test: `tests/test_preflight_hints.py` (new)

**Interfaces:**
- Adds `empty_air_cut` to `HINT_CATALOG` and registers it in `_IFACE_FEATURE_MAP` for `("IFeatureManager.FeatureCut4", "empty_air_cut")`.

- [ ] **Step 1: Write the failing hint test**

```python
# tests/test_preflight_hints.py
from ai_sw_bridge.errors.hints import HINT_CATALOG, resolve_hint


def test_empty_air_cut_hint_exists():
    assert "empty_air_cut" in HINT_CATALOG
    h = HINT_CATALOG["empty_air_cut"]
    assert "coordinate_conventions.md" in h.remedy or "coordinate_conventions" in h.ref_doc


def test_empty_air_cut_resolves_by_feature_type():
    h = resolve_hint(None, "IFeatureManager.FeatureCut4", "empty_air_cut")
    assert h is not None and h.key == "empty_air_cut"
```

- [ ] **Step 2: Run to verify fail**

Run: `PYTHONPATH=src python -m pytest tests/test_preflight_hints.py -q`
Expected: FAIL — `empty_air_cut` not in catalog.

- [ ] **Step 3: Add the hint + registration**

In `src/ai_sw_bridge/errors/hints.py`, add to `HINT_CATALOG`:

```python
    "empty_air_cut": Hint(
        key="empty_air_cut",
        summary=(
            "A cut/hole sweeps a region that does not intersect any "
            "material -- FeatureCut4 returns None with no error."
        ),
        remedy=(
            "The pre-flight (ai-sw-build --lint) flags this before build. "
            "Check the sketch plane, sketch-local coordinates, and plane "
            "offset against docs/coordinate_conventions.md -- the usual "
            "cause is a plane->part mapping slip (Top v->-Z, Right u->-Z)."
        ),
        ref_doc="docs/coordinate_conventions.md",
    ),
```

and register in `_IFACE_FEATURE_MAP`:

```python
    ("IFeatureManager.FeatureCut4", "empty_air_cut"): "empty_air_cut",
```

- [ ] **Step 4: Create `docs/coordinate_conventions.md`**

Write the reference doc. **Honesty-gate constraint: no bare `ai-sw-export`.** Contents:
- The plane→part mapping table (Front/Top/Right) verbatim from this plan's Reference section, calling out the Top `v→−Z` and Right `u→−Z` traps.
- The box-face local mapping table (`+z`/`-z`).
- Offset-part recipes: `start_offset` always grows +normal and ignores `flip` (use `flip_start_offset`); `cut_extrude_two_direction` with symmetric blind depths to hole a body across an air gap (through-all returns `None` across a gap).
- The Front-plane-boss + `+z`-face-hole pattern for flat parts.
- Silent-`None` triage: suspect geometry-in-air first; run `ai-sw-build <spec> --lint` (pre-flight) before suspecting the API; the 1μm-slug-and-read-bbox spike is the on-seat fallback.
- A one-line pointer to the assembly placement quirk (rpy=0 → bbox-center; rpy≠0 → part-origin).

- [ ] **Step 5: Add the AGENTS.md pointer**

In `docs/AGENTS.md`, add a short line under its "before you build" guidance:
`Run `ai-sw-build <spec> --lint` first — the seat-free pre-flight catches coordinate-mapping and empty-air-cut errors before a build. Conventions: docs/coordinate_conventions.md.`

- [ ] **Step 6: Run hint tests + the honesty gate + doc-coverage gate**

Run:
```
PYTHONPATH=src python -m pytest tests/test_preflight_hints.py -q
python tools/honesty_gate.py
python tools/doc_coverage_gate.py
```
Expected: tests PASS; honesty gate exit 0 (the new doc names only real CLIs); doc-coverage clean.

- [ ] **Step 7: Commit**

```bash
git add docs/coordinate_conventions.md docs/AGENTS.md src/ai_sw_bridge/errors/hints.py tests/test_preflight_hints.py
git commit -m "docs(preflight): coordinate_conventions.md + AGENTS pointer + empty_air_cut hint"
```

---

## Final full-suite gate

- [ ] **Run the full local gate the CI mirrors:**

```
PYTHONPATH=src python -m black --check src/ tests/
python -m flake8 src/
python -m mypy --config-file mypy.ini src/ai_sw_bridge
python tools/module_size_gate.py --strict
python tools/honesty_gate.py
PYTHONPATH=src python -m pytest -q
```
Expected: all green. (No live SOLIDWORKS is needed for any of the above.)

## Self-Review (author's checklist, completed)

**Spec coverage:** Component 1 → Task 1; Component 2 (C1/C2/skip) → Task 2; C4 + aggregator → Task 3; C5 folded into Task 3 (minimal); Decision ① (fold into `--lint`) + ② (ERROR-only gating) + `--no-preflight` → Task 4; testing/no-false-positive invariant → Task 5; convention-capture rider (docs + hints) → Task 6. Out-of-scope items (CSG, revolve/loft/swept checks, part-interrogation CLI, live-seat validation) are honored by the honest-skip discipline and are not implemented.

**Placeholder scan:** no TBD/TODO; every code step carries runnable code; the one doc-writing step (Task 6 Step 4) enumerates exact contents rather than "write docs."

**Type consistency:** `LintFinding(severity, path, message)` used identically across tasks; `preflight`, `coordinate_mapping_report`, `material_envelope_scan`, `_degenerate_profile_checks`, `map_plane_point`, `PLANE_AXES`, `Box`, `_boxes_overlap`, `_extruded_box`, `_plane_rect_box`, `_rect_uv_extent`, `_hole_offface_finding`, `_skip` names are consistent between their definition and use; severities are drawn from `{"info","warning","error"}` throughout.

**Known follow-ups for the implementer (not blockers):** C5 fillet-vs-edge is intentionally minimal (warn only when the owning body is modeled); `boss_extrude_midplane`/`two_direction` honest-skip in v0.11 rather than model their offset math — widen later if an example needs it (the no-false-positive invariant will stay green because they skip).
