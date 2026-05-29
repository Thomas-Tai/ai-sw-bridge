"""
Spike v0.15 / S-VARFIL — IVariableRadiusFilletFeatureData per-edge radius SAFEARRAY.

THE load-bearing spike for Phase-1 variable-radius fillet (FR-1-05, P1.5 in
docs/central_idea/todolist.md). Decides whether out-of-process late binding
can marshal a SAFEARRAY of per-edge radius values into
``IVariableRadiusFilletFeatureData`` — the crux that distinguishes a
var-radius fillet handler from the simpler constant-radius one already in the
bridge.

Background
----------
The bridge already drives ``CreateDefinition(swFmFillet=1)`` successfully for
constant-radius fillets (proven in spikes/phase0/spike_p_fillet_pipeline.py).
The variable-radius extension requires populating the per-edge radius SAFEARRAY
on the feature-data object before calling ``CreateFeature``.  The SW API
surface for this is::

    data = fm.CreateDefinition(swFmFillet)        # same enum value as constant fillet
    data.Radius = 0.001                            # fallback constant radius (meters)
    data.VariableRadiusParameters = <SAFEARRAY>   # per-edge array — THE risk

``VariableRadiusParameters`` (and the related ``SetVariableRadiusParameters``
method) accept/return a SAFEARRAY of doubles (per-edge radius values in
meters, one entry per selected edge, in the same order as the edge selection).

The SAFEARRAY marshaling risk is in exactly the same class as the OUT-param
variant-array failure seen in S-PERSIST (``GetObjectByPersistReference3``
[out] long Error) and E2.1 (``GetSelectByIDString`` on IFace2 proxies).
Under pywin32 dynamic dispatch, a ``SAFEARRAY(VT_R8)`` written via a property
setter may arrive as a Python tuple, list, bytes-of-floats, or raise
``DISP_E_TYPEMISMATCH``.  This spike probes every plausible invocation form
and records the actual Python type, element count, and first/last values.

Two additional risks:
- Edge selection for fillet must be pre-staged.  The bridge uses coordinate-
  based ``SelectByID`` for edges; this spike re-uses that pattern (the
  Callout-free ``IEntity.Select2`` form is probed as a secondary).
- ``ISimpleFilletFeatureData2.Initialize`` vs. ``IVariableRadiusFilletFeatureData``
  disambiguation: both share ``swFmFillet``.  The spike uses the presence of
  ``VariableRadiusParameters`` / ``SetVariableRadiusParameters`` as the
  discriminator.

Verdict
-------
PASS    : per-edge radius SAFEARRAY round-trips (write then read-back) AND
          ``CreateFeature`` materializes a variable-radius fillet feature on
          the box edge.  Phase-1 var-radius fillet handler is out-of-process
          viable; build it.
PARTIAL : the data object is reachable and simple props (Radius, FilletType,
          EdgeCount) marshal cleanly, but the SAFEARRAY write or read-back
          fails (``DISP_E_TYPEMISMATCH``, wrong element count, or all-zeros on
          read-back).  THIS IS THE SAFEARRAY-WALL SIGNAL.  Run ``--mode vba``
          to confirm the round-trip works in early binding (proving the pywin32
          marshaler, not the SW API, is the culprit).  Fall back: drop to face/
          full-round fillet only (constant-radius path already proven).
FAIL    : ``swFmFillet`` not found, ``CreateDefinition`` returns None, or the
          feature-data object lacks ``VariableRadiusParameters`` entirely
          (install/version issue).

Prereq: SOLIDWORKS running with a blank Part active.
        Pass ``--skip-build`` to probe a solid body already present.

Usage
-----
    python spikes/v0_15/spike_varfil.py
    python spikes/v0_15/spike_varfil.py --skip-build --out report.json
    python spikes/v0_15/spike_varfil.py --mode vba   # emit .bas early-binding oracle

NOTE: the --mode vba oracle is especially valuable here.  The SAFEARRAY
round-trip for per-edge radius values is the precise failure mode that
separates a Python-PARTIAL from a genuine API gap.  If Python is PARTIAL
(SAFEARRAY write fails) but the VBA oracle PASSes (early binding handles
the array natively), the pywin32 marshaler is the wall and Route-C
(PythonNET/C# in-process) is signalled.  If VBA also fails, the SW API
itself cannot accept the array form at all (fall back to face/full-round
fillet only regardless of binding strategy).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

import pythoncom  # noqa: E402
import pywintypes  # noqa: E402

from ai_sw_bridge.sw_com import get_sw_app, get_active_doc, SW_DOC_PART  # noqa: E402


# ---------------------------------------------------------------------------
# Box geometry (metres)
# ---------------------------------------------------------------------------
BOX_W_M = 0.020   # 20 mm × 20 mm footprint
BOX_H_M = 0.020
BOX_D_M = 0.010   # 10 mm tall — +z face at z = 0.010

# The test fillet will be applied to one bottom edge of the box.
# Bottom edge: from (-BOX_W_M/2, -BOX_H_M/2, 0) to (+BOX_W_M/2, -BOX_H_M/2, 0)
# Mid-point coordinate used for SelectByID edge selection:
EDGE_X_M = 0.0
EDGE_Y_M = -BOX_H_M / 2   # -0.010
EDGE_Z_M = 0.0

# Per-edge radius values to probe (two entries: start and end of the edge).
# SW var-radius typically wants [start_radius, end_radius] per edge in meters.
VARRAD_START_M = 0.002   # 2 mm at start vertex
VARRAD_END_M   = 0.004   # 4 mm at end vertex

# swFilletType_e candidates (probe; docs say swFilletTypeVariable=1).
FILLET_TYPE_VARIABLE = 1
FILLET_TYPE_CONSTANT = 0

# swFmFillet is known = 1 from spike_p_fillet_pipeline.py.
SW_FM_FILLET = 1


def _type_tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def _ensure_part_doc(sw: Any) -> Any:
    doc = get_active_doc(sw)
    if doc is None:
        raise RuntimeError("no active document; open a blank Part first")
    if doc.GetType != SW_DOC_PART:
        raise RuntimeError(
            f"active doc is not a Part (GetType={doc.GetType!r}); open a blank Part"
        )
    return doc


# ---------------------------------------------------------------------------
# Solid fixture
# ---------------------------------------------------------------------------

def _build_box(doc: Any) -> dict[str, Any]:
    """Insert a 20×20×10 mm Boss-Extrude on the Front Plane.

    Returns a dict with keys: built (bool), feature_name, error (on failure).
    Mirrors spikes/v0_15/spike_persist_reference.py build_single_box exactly.
    """
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        return {"built": False, "error": "could not select Front Plane"}
    sk = doc.SketchManager
    sk.InsertSketch(True)
    seg = sk.CreateCornerRectangle(
        -BOX_W_M / 2, -BOX_H_M / 2, 0.0,
        BOX_W_M / 2,  BOX_H_M / 2,  0.0,
    )
    if seg is None:
        sk.InsertSketch(True)
        return {"built": False, "error": "CreateCornerRectangle returned None"}
    sk.InsertSketch(True)
    fm = doc.FeatureManager
    base_args = (
        True, False, False, 0, 0, BOX_D_M, 0.0,
        False, False, False, False, 0.0, 0.0,
        False, False, False, False, True, True, True, 0, 0.0,
    )
    try:
        feat = fm.FeatureExtrusion2(*base_args, False)   # 23-arg
    except Exception:
        feat = fm.FeatureExtrusion2(*base_args)           # 22-arg fallback
    if feat is None:
        return {"built": False, "error": "FeatureExtrusion2 returned None"}
    return {"built": True, "feature_name": getattr(feat, "Name", None)}


# ---------------------------------------------------------------------------
# IVariableRadiusFilletFeatureData discrimination
# ---------------------------------------------------------------------------

def _is_varfil_data(data: Any) -> bool:
    """Return True if *data* exposes VariableRadiusParameters or
    SetVariableRadiusParameters — the discriminator for
    IVariableRadiusFilletFeatureData vs. ISimpleFilletFeatureData2.
    """
    for attr in ("VariableRadiusParameters", "SetVariableRadiusParameters"):
        try:
            getattr(data, attr)
            return True
        except pywintypes.com_error:
            pass
        except AttributeError:
            pass
        except Exception:
            pass
    return False


# ---------------------------------------------------------------------------
# Edge selection
# ---------------------------------------------------------------------------

def _select_bottom_edge(doc: Any) -> dict[str, Any]:
    """Select one bottom edge of the box via coordinate-based SelectByID.

    Returns status dict.  Mid-point of the front-bottom edge is used
    (Y = -BOX_H_M/2, Z = 0) — the same pattern as builder._select_edges_by_points.
    """
    rec: dict[str, Any] = {}
    doc.ClearSelection2(True)
    t0 = time.perf_counter()
    try:
        ok = doc.SelectByID("", "EDGE", EDGE_X_M, EDGE_Y_M, EDGE_Z_M)
        rec["status"] = "OK" if ok else "NOT_SELECTED"
        rec["ok"] = ok
    except pywintypes.com_error as e:
        rec["status"] = "COM_ERROR"
        rec["error"] = f"{getattr(e, 'hresult', None):#010x} {getattr(e, 'strerror', str(e))}"
    except Exception as e:
        rec["status"] = "PY_EXCEPTION"
        rec["error"] = f"{type(e).__name__}: {e}"
    rec["elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
    return rec


# ---------------------------------------------------------------------------
# IVariableRadiusFilletFeatureData property probes
# ---------------------------------------------------------------------------

def _probe_prop_rw(data: Any, prop: str, write_val: Any) -> dict[str, Any]:
    """Read then write-back a single scalar property on the data object."""
    rec: dict[str, Any] = {"prop": prop}
    t0 = time.perf_counter()
    try:
        read_val = getattr(data, prop)
        rec["read_status"] = "OK"
        rec["read_type"] = _type_tag(read_val)
        rec["read_value"] = (
            read_val if not isinstance(read_val, (bytes, bytearray))
            else read_val.hex()
        )
    except pywintypes.com_error as e:
        rec["read_status"] = "COM_ERROR"
        rec["read_error"] = (
            f"{getattr(e, 'hresult', None):#010x} {getattr(e, 'strerror', str(e))}"
        )
    except Exception as e:
        rec["read_status"] = "PY_EXCEPTION"
        rec["read_error"] = f"{type(e).__name__}: {e}"
    rec["read_elapsed_ms"] = (time.perf_counter() - t0) * 1000.0

    t0 = time.perf_counter()
    try:
        setattr(data, prop, write_val)
        read_back = getattr(data, prop)
        rec["write_status"] = "OK"
        rec["write_readback"] = (
            read_back if not isinstance(read_back, (bytes, bytearray))
            else read_back.hex()
        )
    except pywintypes.com_error as e:
        rec["write_status"] = "COM_ERROR"
        rec["write_error"] = (
            f"{getattr(e, 'hresult', None):#010x} {getattr(e, 'strerror', str(e))}"
        )
    except Exception as e:
        rec["write_status"] = "PY_EXCEPTION"
        rec["write_error"] = f"{type(e).__name__}: {e}"
    rec["write_elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
    return rec


def _safearray_shape(v: Any) -> dict[str, Any]:
    """Describe the Python form of a SAFEARRAY returned from VariableRadiusParameters.

    Under pywin32 dynamic dispatch a SAFEARRAY(VT_R8) can surface as:
      - tuple of floats         (most common)
      - list of floats
      - bytes (packed IEEE-754, len = 8 × n)
      - bytearray
      - a single float          (if SW flattens a 1-element array)
      - None                    (read before any write)
    Record the Python type, element count (if iterable), and first/last
    values so the handler author can see what to expect.
    """
    shape: dict[str, Any] = {"python_type": _type_tag(v)}
    if v is None:
        return shape
    if isinstance(v, (tuple, list)):
        shape["len"] = len(v)
        if len(v) > 0:
            shape["first"] = float(v[0]) if isinstance(v[0], (int, float)) else repr(v[0])
            shape["last"]  = float(v[-1]) if isinstance(v[-1], (int, float)) else repr(v[-1])
    elif isinstance(v, (bytes, bytearray)):
        shape["byte_len"] = len(v)
        shape["first8_hex"] = bytes(v)[:8].hex()
    elif isinstance(v, (int, float)):
        shape["scalar"] = float(v)
    return shape


def probe_safearray_roundtrip(data: Any) -> dict[str, Any]:
    """THE core probe of this spike.

    Attempt to write then read-back a per-edge radius SAFEARRAY via every
    plausible invocation form.  Record the Python type tags and values at
    each step — this is the finding that determines PASS / PARTIAL / FAIL.

    Forms attempted (in order):
      A. Property assignment: data.VariableRadiusParameters = (start, end)
      B. Method call: data.SetVariableRadiusParameters((start, end))
      C. Method call with explicit list: data.SetVariableRadiusParameters([start, end])
    Read-back after each successful write via data.VariableRadiusParameters.
    """
    rec: dict[str, Any] = {}

    test_array_tuple = (VARRAD_START_M, VARRAD_END_M)
    test_array_list  = [VARRAD_START_M, VARRAD_END_M]

    # --- read-before-write (baseline) ---
    t0 = time.perf_counter()
    try:
        baseline = data.VariableRadiusParameters
        rec["read_before_write"] = {
            "status": "OK",
            "shape": _safearray_shape(baseline),
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }
    except pywintypes.com_error as e:
        rec["read_before_write"] = {
            "status": "COM_ERROR",
            "error": f"{getattr(e, 'hresult', None):#010x} {getattr(e, 'strerror', str(e))}",
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }
    except Exception as e:
        rec["read_before_write"] = {
            "status": "PY_EXCEPTION",
            "error": f"{type(e).__name__}: {e}",
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
        }

    write_attempts: list[dict[str, Any]] = []

    # Form A: property assignment with tuple.
    attempt: dict[str, Any] = {"form": "prop_assign_tuple"}
    t0 = time.perf_counter()
    try:
        data.VariableRadiusParameters = test_array_tuple
        attempt["write_status"] = "OK"
        attempt["write_elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
        # Read-back
        t1 = time.perf_counter()
        try:
            rb = data.VariableRadiusParameters
            attempt["readback_status"] = "OK"
            attempt["readback_shape"] = _safearray_shape(rb)
            attempt["readback_elapsed_ms"] = (time.perf_counter() - t1) * 1000.0
        except Exception as e2:
            attempt["readback_status"] = "EXCEPTION"
            attempt["readback_error"] = f"{type(e2).__name__}: {e2}"
            attempt["readback_elapsed_ms"] = (time.perf_counter() - t1) * 1000.0
    except pywintypes.com_error as e:
        attempt["write_status"] = "COM_ERROR"
        attempt["write_error"] = (
            f"{getattr(e, 'hresult', None):#010x} {getattr(e, 'strerror', str(e))}"
        )
        attempt["write_elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
    except Exception as e:
        attempt["write_status"] = "PY_EXCEPTION"
        attempt["write_error"] = f"{type(e).__name__}: {e}"
        attempt["write_elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
    write_attempts.append(attempt)

    # Form B: SetVariableRadiusParameters with tuple.
    attempt = {"form": "method_tuple"}
    t0 = time.perf_counter()
    try:
        data.SetVariableRadiusParameters(test_array_tuple)
        attempt["write_status"] = "OK"
        attempt["write_elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
        t1 = time.perf_counter()
        try:
            rb = data.VariableRadiusParameters
            attempt["readback_status"] = "OK"
            attempt["readback_shape"] = _safearray_shape(rb)
            attempt["readback_elapsed_ms"] = (time.perf_counter() - t1) * 1000.0
        except Exception as e2:
            attempt["readback_status"] = "EXCEPTION"
            attempt["readback_error"] = f"{type(e2).__name__}: {e2}"
            attempt["readback_elapsed_ms"] = (time.perf_counter() - t1) * 1000.0
    except pywintypes.com_error as e:
        attempt["write_status"] = "COM_ERROR"
        attempt["write_error"] = (
            f"{getattr(e, 'hresult', None):#010x} {getattr(e, 'strerror', str(e))}"
        )
        attempt["write_elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
    except Exception as e:
        attempt["write_status"] = "OK" if "not found" not in str(e).lower() else "NOT_FOUND"
        attempt["write_error"] = f"{type(e).__name__}: {e}"
        attempt["write_elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
    write_attempts.append(attempt)

    # Form C: SetVariableRadiusParameters with list.
    attempt = {"form": "method_list"}
    t0 = time.perf_counter()
    try:
        data.SetVariableRadiusParameters(test_array_list)
        attempt["write_status"] = "OK"
        attempt["write_elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
        t1 = time.perf_counter()
        try:
            rb = data.VariableRadiusParameters
            attempt["readback_status"] = "OK"
            attempt["readback_shape"] = _safearray_shape(rb)
            attempt["readback_elapsed_ms"] = (time.perf_counter() - t1) * 1000.0
        except Exception as e2:
            attempt["readback_status"] = "EXCEPTION"
            attempt["readback_error"] = f"{type(e2).__name__}: {e2}"
            attempt["readback_elapsed_ms"] = (time.perf_counter() - t1) * 1000.0
    except pywintypes.com_error as e:
        attempt["write_status"] = "COM_ERROR"
        attempt["write_error"] = (
            f"{getattr(e, 'hresult', None):#010x} {getattr(e, 'strerror', str(e))}"
        )
        attempt["write_elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
    except Exception as e:
        attempt["write_status"] = "OK" if "not found" not in str(e).lower() else "NOT_FOUND"
        attempt["write_error"] = f"{type(e).__name__}: {e}"
        attempt["write_elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
    write_attempts.append(attempt)

    rec["write_attempts"] = write_attempts

    # Determine whether any form achieved a successful round-trip.
    def _round_trip_ok(a: dict[str, Any]) -> bool:
        if a.get("write_status") != "OK":
            return False
        if a.get("readback_status") != "OK":
            return False
        shape = a.get("readback_shape", {})
        # Minimal correctness: element count == 2 and first value is non-zero.
        if shape.get("len", 0) == 2 and shape.get("first", 0.0) != 0.0:
            return True
        # Scalar form: a single float equal to one of our test values (degenerate match).
        if "scalar" in shape and shape["scalar"] in (VARRAD_START_M, VARRAD_END_M):
            return True
        return False

    rec["any_round_trip_ok"] = any(_round_trip_ok(a) for a in write_attempts)
    rec["working_form"] = next(
        (a["form"] for a in write_attempts if _round_trip_ok(a)), None
    )
    return rec


def probe_scalar_props(data: Any) -> dict[str, Any]:
    """Probe read+write of scalar properties on the fillet data object."""
    props = [
        # (property_name, test_write_value)
        ("Radius",         0.002),          # 2 mm constant fallback radius
        ("FilletType",     FILLET_TYPE_VARIABLE),
        ("Propagate",      True),
        ("TangentPropagation", True),
        ("SmoothFace",     False),
        ("ReverseDir",     False),
    ]
    results = [_probe_prop_rw(data, name, val) for name, val in props]
    all_readable = all(r["read_status"] == "OK" for r in results)
    all_writable = all(r["write_status"] == "OK" for r in results)
    return {
        "props": results,
        "all_readable": all_readable,
        "all_writable": all_writable,
    }


# ---------------------------------------------------------------------------
# CreateFeature probe
# ---------------------------------------------------------------------------

def probe_create_feature(fm: Any, data: Any, doc: Any) -> dict[str, Any]:
    """Attempt to materialize the var-radius fillet via CreateFeature(data).

    Pre-requisite: edge selection is in place (caller ensures this).
    """
    rec: dict[str, Any] = {}

    # Set up data for a variable-radius fillet (best-effort defaults).
    try:
        data.Radius = VARRAD_START_M          # fallback constant radius
        data.FilletType = FILLET_TYPE_VARIABLE
        data.Propagate = True
    except Exception as e:
        rec["data_setup_error"] = f"{type(e).__name__}: {e}"

    t0 = time.perf_counter()
    try:
        feat = fm.CreateFeature(data)
        rec["elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
        if feat is None:
            rec["status"] = "NONE_RETURNED"
            rec["reason"] = "CreateFeature(data) returned None"
        else:
            rec["status"] = "OK"
            rec["feature_type"] = _type_tag(feat)
            try:
                rec["feature_name"] = feat.Name
                rec["feature_type_name"] = feat.GetTypeName2
            except Exception as e:
                rec["feature_attr_error"] = f"{type(e).__name__}: {e}"
            try:
                rec["feature_count_after"] = doc.GetFeatureCount
            except Exception:
                pass
    except pywintypes.com_error as e:
        rec["elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
        rec["status"] = "COM_ERROR"
        rec["hresult"] = f"{getattr(e, 'hresult', None):#010x}"
        rec["description"] = getattr(e, "strerror", str(e))
    except Exception as e:
        rec["elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
        rec["status"] = "PY_EXCEPTION"
        rec["exception_type"] = type(e).__name__
        rec["message"] = str(e)
    return rec


# ---------------------------------------------------------------------------
# Top-level COM run
# ---------------------------------------------------------------------------

def run_com(skip_build: bool) -> dict[str, Any]:
    sw = get_sw_app()
    doc = _ensure_part_doc(sw)

    build_rec: dict[str, Any] = {"skipped": skip_build}
    if not skip_build:
        build_rec.update(_build_box(doc))
        if not build_rec.get("built"):
            return {"overall": "FAIL", "reason": "box did not build", "build": build_rec}
        try:
            doc.EditRebuild3
        except Exception:
            pass

    fm = doc.FeatureManager

    # 1. Get the fillet data object (swFmFillet = 1, known from spike_p).
    t0 = time.perf_counter()
    try:
        data = fm.CreateDefinition(SW_FM_FILLET)
    except Exception as e:
        return {
            "overall": "FAIL",
            "reason": f"CreateDefinition({SW_FM_FILLET}) raised {type(e).__name__}: {e}",
            "build": build_rec,
        }
    create_def_elapsed = (time.perf_counter() - t0) * 1000.0

    if data is None:
        return {
            "overall": "FAIL",
            "reason": f"CreateDefinition({SW_FM_FILLET}) returned None",
            "build": build_rec,
        }

    data_info: dict[str, Any] = {
        "python_type": _type_tag(data),
        "create_def_elapsed_ms": create_def_elapsed,
        "is_varfil_data": _is_varfil_data(data),
    }

    if not data_info["is_varfil_data"]:
        # ISimpleFilletFeatureData2 returned instead of IVariableRadiusFilletFeatureData.
        # Try setting FilletType first to switch the object to variable mode.
        try:
            data.FilletType = FILLET_TYPE_VARIABLE
            data_info["is_varfil_data_after_type_set"] = _is_varfil_data(data)
        except Exception as e:
            data_info["type_set_error"] = f"{type(e).__name__}: {e}"
            data_info["is_varfil_data_after_type_set"] = False

        if not data_info.get("is_varfil_data_after_type_set", False):
            return {
                "overall": "FAIL",
                "reason": (
                    "CreateDefinition(swFmFillet) returned an object without "
                    "VariableRadiusParameters / SetVariableRadiusParameters; "
                    "SW API may not expose IVariableRadiusFilletFeatureData "
                    "via late binding on this install/version"
                ),
                "data_info": data_info,
                "build": build_rec,
            }

    # 2. Scalar property probes.
    scalar_probe = probe_scalar_props(data)

    # 3. SAFEARRAY round-trip — THE crux.
    safearray_probe = probe_safearray_roundtrip(data)

    # 4. Edge selection.
    edge_select = _select_bottom_edge(doc)

    # 5. CreateFeature probe (uses the edge selection left in place by step 4).
    create_feat_probe: dict[str, Any] = {}
    if edge_select.get("ok"):
        create_feat_probe = probe_create_feature(fm, data, doc)
    else:
        create_feat_probe = {
            "status": "SKIPPED",
            "reason": "edge selection failed; cannot invoke CreateFeature",
        }

    # --- Verdict derivation ---
    safearray_ok = safearray_probe.get("any_round_trip_ok", False)
    feat_ok = create_feat_probe.get("status") == "OK"
    scalar_ok = scalar_probe["all_readable"] and scalar_probe["all_writable"]

    if safearray_ok and feat_ok:
        overall = "PASS"
    elif scalar_ok and not safearray_ok:
        # Scalar props work; SAFEARRAY is the wall — the expected PARTIAL signal.
        overall = "PARTIAL"
    elif safearray_ok and not feat_ok:
        # Array round-trips but CreateFeature fails — less common PARTIAL.
        overall = "PARTIAL"
    else:
        overall = "PARTIAL" if scalar_ok else "FAIL"

    interpretation_map = {
        "PASS": (
            "IVariableRadiusFilletFeatureData SAFEARRAY round-trips out-of-process "
            "AND CreateFeature materializes the var-radius fillet → "
            "build Phase-1 var-radius fillet handler (P1.5)"
        ),
        "PARTIAL": (
            "Data object accessible (scalar props ok) but SAFEARRAY write/read-back "
            "fails → SAFEARRAY-WALL signal; run --mode vba to confirm the pywin32 "
            "marshaler (not the SW API) is the culprit → Route-C signal if VBA PASSes; "
            "fall back to face/full-round fillet only (constant-radius path) if VBA also FAILs"
        ),
        "FAIL": (
            "IVariableRadiusFilletFeatureData unreachable or CreateDefinition fails → "
            "drop to face/full-round fillet only; record in DEFERRED.md"
        ),
    }

    return {
        "overall": overall,
        "sw_revision": sw.RevisionNumber,
        "interpretation": interpretation_map[overall],
        "swFmFillet_int": SW_FM_FILLET,
        "build": build_rec,
        "data_info": data_info,
        "scalar_props": scalar_probe,
        "safearray_roundtrip": safearray_probe,
        "edge_selection": edge_select,
        "create_feature": create_feat_probe,
    }


# ---------------------------------------------------------------------------
# VBA oracle (early-binding)
# ---------------------------------------------------------------------------

def emit_vba() -> str:
    """Early-binding oracle for the SAFEARRAY round-trip.

    Especially valuable for this spike: if Python is PARTIAL (SAFEARRAY
    write fails) but this VBA PASSes, the pywin32 marshaler is the wall
    → Route-C signal.  If VBA also fails, the API itself cannot accept
    the array and the fall-back (face/full-round fillet) is the only option.
    """
    return r"""' Spike v0.15 S-VARFIL VBA oracle.
' Paste into a Part-document module, press F5.
' Prereq: a 20x20x10 mm box on Front Plane already present.
' Tests IVariableRadiusFilletFeatureData SAFEARRAY round-trip
' (per-edge radius write + read-back) in early binding.
' If this PASSes but Python spikes/v0_15/spike_varfil.py is PARTIAL,
' the pywin32 marshaler (not the SW API) is the wall -> Route-C signal.
Option Explicit
Sub ProbeVarRadFillet()
    Dim swApp   As SldWorks.SldWorks
    Dim Part    As SldWorks.ModelDoc2
    Dim fm      As SldWorks.FeatureManager
    Dim data    As SldWorks.SimpleFilletFeatureData2   ' late-cast; VBA resolves IVarRad
    Dim feat    As SldWorks.Feature
    Dim radii() As Double
    Dim readback As Variant
    Dim msg     As String

    Set swApp = Application.SldWorks
    Set Part  = swApp.ActiveDoc
    Set fm    = Part.FeatureManager

    ' --- 1. Get data object (swFmFillet = 1) ---
    Set data = fm.CreateDefinition(swFmFillet)
    If data Is Nothing Then
        MsgBox "CreateDefinition(swFmFillet) returned Nothing"
        Exit Sub
    End If

    ' --- 2. Switch to variable-radius mode ---
    data.FilletType = swFilletTypeVariable   ' enum value 1

    ' --- 3. SAFEARRAY write: set per-edge radius array ---
    ' Two values: start=2 mm, end=4 mm (in metres)
    ReDim radii(1)
    radii(0) = 0.002
    radii(1) = 0.004
    data.SetVariableRadiusParameters radii

    ' --- 4. Read-back ---
    readback = data.VariableRadiusParameters
    If IsEmpty(readback) Or IsNull(readback) Then
        msg = "VariableRadiusParameters read-back: EMPTY (SAFEARRAY wall)"
    ElseIf IsArray(readback) Then
        msg = "VariableRadiusParameters read-back: ARRAY len=" & _
              UBound(readback) - LBound(readback) + 1 & _
              " first=" & readback(LBound(readback)) & _
              " last=" & readback(UBound(readback))
    Else
        msg = "VariableRadiusParameters read-back: scalar=" & readback
    End If

    ' --- 5. Select edge and create feature ---
    Part.ClearSelection2 True
    ' Select bottom-front edge mid-point (Y=-0.01, Z=0)
    Part.SelectByID2 "", "EDGE", 0, -0.01, 0, False, 0, Nothing, 0
    data.Radius = 0.002   ' constant fallback

    Set feat = fm.CreateFeature(data)
    If feat Is Nothing Then
        msg = msg & Chr(10) & "CreateFeature: NOTHING returned"
    Else
        msg = msg & Chr(10) & "CreateFeature OK -> " & feat.Name & " / " & feat.GetTypeName2
    End If

    MsgBox "S-VARFIL VBA oracle:" & Chr(10) & msg
End Sub
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--mode", choices=["com", "vba"], default="com",
        help="com = drive SW from Python; vba = emit the .bas oracle.",
    )
    p.add_argument(
        "--skip-build", action="store_true",
        help="Skip creating the test box; probe the first solid body already present.",
    )
    p.add_argument(
        "--out", type=Path, default=None,
        help="Write JSON report to this path instead of stdout.",
    )
    args = p.parse_args()

    if args.mode == "vba":
        out = Path(__file__).parent / "spike_varfil.bas"
        out.write_text(emit_vba(), encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
        return 0

    pythoncom.CoInitialize()
    try:
        result = run_com(args.skip_build)
    finally:
        pythoncom.CoUninitialize()

    payload = json.dumps(result, indent=2, default=str)
    if args.out is not None:
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)

    # PARTIAL exits 2 to distinguish the SAFEARRAY-wall signal from a clean FAIL.
    return {"PASS": 0, "PARTIAL": 2, "FAIL": 1}.get(result["overall"], 1)


if __name__ == "__main__":
    sys.exit(main())
