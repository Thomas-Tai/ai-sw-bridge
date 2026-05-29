"""
Spike v0.15 / S-PERSIST — durable topological reference round-trip.

THE load-bearing spike for the feature-coverage keystone (Phase 0 in
docs/central_idea/api_coverage_roadmap.md). Decides whether out-of-process
late binding can produce *edit-robust* selection — i.e. a durable token for
a face/edge that survives a rebuild and reselects the same entity.

Background
----------
The E2.1 spike (spikes/v0_12/spike_brep_marshal.py) already found
``IEntity.GetSelectByIDString`` UNREACHABLE on the IFace2 proxy returned by
``IFeature.GetFaces`` — so the bridge today identifies entities by a
session-scoped synthetic temp_id + fingerprint, NOT a durable reference,
which is why edge/face selection is by brittle literal coordinate
(known_limitations.md §4) and every build is a fresh ``NewDocument``
(§5). The remaining candidate for a durable token is the persist-reference
API on ``IModelDocExtension``:

    pid  = ext.GetPersistReference3(entity)          # read  -> byte array
    obj  = ext.GetObjectByPersistReference3(pid, err) # write -> entity back

The crux is the *write-back*: ``GetObjectByPersistReference3`` has a
``[out] long`` Error parameter, and OUT params are exactly the late-binding
failure class that has bitten this project before (Callout in SelectByID2,
GetErrorCode2, etc.). This spike probes both directions and the OUT-param
marshaling explicitly.

Verdict
-------
PASS    : read + write-back + identity-match + selectable, AND the token
          survives a ForceRebuild3. The keystone lane is out-of-process
          viable; build it.
PARTIAL : read works but write-back cannot be marshaled (the OUT-param
          wall). THIS IS THE ROUTE-C SIGNAL — durable selection is not
          reachable out-of-process; escalate the in-process (PythonNET/C#)
          conversation per roadmap §3.3 / §4.4. Run --mode vba to confirm
          the same round-trip succeeds in early binding (proving the
          marshaler, not the API, is the culprit).
FAIL    : read itself fails (API absent, or persist refs need a saved doc
          — retry with --save-first).

Prereq: SOLIDWORKS running with a blank Part active (same as the other
spikes). Pass --skip-build to probe the first solid body already present.

Usage
-----
    python spikes/v0_15/spike_persist_reference.py
    python spikes/v0_15/spike_persist_reference.py --save-first --out report.json
    python spikes/v0_15/spike_persist_reference.py --mode vba   # emit .bas oracle

NOTE: this spike tests durability across a *rebuild* (the in-session proof).
The ultimate test is save -> close -> reopen -> resolve; that is left as a
documented follow-up (--reopen) because it needs file-lifecycle handling
the keystone lane will own. A rebuild-survival PASS here is necessary but
not sufficient for the reopen case; flag any RED on reopen separately.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

import pythoncom  # noqa: E402
import pywintypes  # noqa: E402

from ai_sw_bridge.sw_com import get_sw_app, get_active_doc, SW_DOC_PART  # noqa: E402


BOX_W_M = 0.020
BOX_H_M = 0.020
BOX_D_M = 0.010

# swPersistReferencedObjectStatus_e (subset; report raw code regardless).
PERSIST_STATUS_NAMES = {
    0: "Ok",
    1: "Deleted",
    2: "Suppressed",
    3: "AmbiguousReference",
    4: "InvalidReference",
}


def _type_tag(v: Any) -> str:
    if v is None:
        return "NoneType"
    return type(v).__name__


def _ensure_part_doc(sw: Any) -> Any:
    doc = get_active_doc(sw)
    if doc is None:
        raise RuntimeError("no active document; open a blank Part first")
    if doc.GetType != SW_DOC_PART:
        raise RuntimeError(
            f"active doc is not a Part (GetType={doc.GetType!r}); open a blank Part"
        )
    return doc


def build_single_box(doc: Any) -> dict[str, Any]:
    """Insert one Boss-Extrude box on the Front Plane (faces + edges to probe).

    Mirrors spikes/v0_12/spike_brep_marshal.py conventions: legacy 5-arg
    SelectByID, 23/22-arg FeatureExtrusion2 fallback.
    """
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        return {"built": False, "error": "could not select Front Plane"}

    sk = doc.SketchManager
    sk.InsertSketch(True)
    seg = sk.CreateCornerRectangle(
        -BOX_W_M / 2, -BOX_H_M / 2, 0.0, BOX_W_M / 2, BOX_H_M / 2, 0.0
    )
    if seg is None:
        sk.InsertSketch(True)
        return {"built": False, "error": "CreateCornerRectangle returned None"}
    sk.InsertSketch(True)

    fm = doc.FeatureManager
    base_args = (
        True, False, False, 0, 0, BOX_D_M, 0.0, False, False, False, False,
        0.0, 0.0, False, False, False, False, True, True, True, 0, 0.0,
    )
    try:
        feat = fm.FeatureExtrusion2(*base_args, False)  # 23-arg
    except Exception:
        feat = fm.FeatureExtrusion2(*base_args)  # 22-arg fallback
    if feat is None:
        return {"built": False, "error": "FeatureExtrusion2 returned None"}
    return {"built": True, "feature_name": getattr(feat, "Name", None)}


def _first_body(doc: Any) -> Any:
    bodies = doc.GetBodies2(0, True)  # swSolidBody=0
    if not bodies:
        return None
    return bodies[0]


def _pid_to_bytes(pid: Any) -> bytes | None:
    """Normalize a persist-ID variant to bytes for identity comparison.

    Under pywin32 a SAFEARRAY(VT_UI1) may surface as bytes, bytearray, a
    tuple/list of ints, or (less likely) a str. Returns None if it can't be
    coerced -- which is itself a finding the caller records.
    """
    if pid is None:
        return None
    if isinstance(pid, (bytes, bytearray)):
        return bytes(pid)
    if isinstance(pid, (tuple, list)):
        try:
            return bytes(int(x) & 0xFF for x in pid)
        except (TypeError, ValueError):
            return None
    if isinstance(pid, str):
        return pid.encode("latin-1", errors="replace")
    return None


def _pid_shape(pid: Any) -> dict[str, Any]:
    b = _pid_to_bytes(pid)
    shape: dict[str, Any] = {
        "python_type": _type_tag(pid),
        "coercible_to_bytes": b is not None,
        "byte_len": len(b) if b is not None else None,
    }
    if b is not None and len(b) > 0:
        shape["first8_hex"] = b[:8].hex()
        shape["last8_hex"] = b[-8:].hex()
    return shape


def _read_persist_id(ext: Any, entity: Any) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        pid = ext.GetPersistReference3(entity)
    except pywintypes.com_error as e:
        return {"status": "COM_ERROR", "hresult": getattr(e, "hresult", None),
                "description": getattr(e, "strerror", str(e)),
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0}
    except Exception as e:  # AttributeError = method unreachable via late binding
        return {"status": "PY_EXCEPTION", "exception_type": type(e).__name__,
                "message": str(e), "elapsed_ms": (time.perf_counter() - t0) * 1000.0}
    if pid is None:
        return {"status": "NONE_RETURNED",
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0}
    out = {"status": "OK", "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
           "_pid": pid}
    out.update(_pid_shape(pid))
    return out


def _resolve_persist_id(ext: Any, pid: Any) -> dict[str, Any]:
    """Probe GetObjectByPersistReference3 across invocation forms.

    The method's [out] long Error is the marshaling risk. pywin32 dynamic
    dispatch usually appends an [out] param to the return tuple, but it may
    instead demand the arg, or fail entirely. Try, in order:
      1. result = call(pid)                      -> maybe (obj, err) or obj
      2. result = call(pid, 0)                   -> explicit placeholder
      3. result = call(pid, pythoncom.Missing)   -> Missing sentinel
    Capture which form (if any) returns a usable object.
    """
    attempts: list[dict[str, Any]] = []

    def _interpret(result: Any) -> tuple[Any, Any]:
        """Split a return into (obj, errorCode) for the (obj, out-err) shape."""
        if isinstance(result, (tuple, list)) and len(result) == 2:
            return result[0], result[1]
        return result, None

    forms = [
        ("call(pid)", lambda: ext.GetObjectByPersistReference3(pid)),
        ("call(pid, 0)", lambda: ext.GetObjectByPersistReference3(pid, 0)),
        ("call(pid, Missing)",
         lambda: ext.GetObjectByPersistReference3(pid, pythoncom.Missing)),
    ]
    for label, fn in forms:
        t0 = time.perf_counter()
        try:
            result = fn()
        except pywintypes.com_error as e:
            attempts.append({"form": label, "status": "COM_ERROR",
                             "hresult": getattr(e, "hresult", None),
                             "description": getattr(e, "strerror", str(e)),
                             "elapsed_ms": (time.perf_counter() - t0) * 1000.0})
            continue
        except Exception as e:
            attempts.append({"form": label, "status": "PY_EXCEPTION",
                             "exception_type": type(e).__name__, "message": str(e),
                             "elapsed_ms": (time.perf_counter() - t0) * 1000.0})
            continue
        obj, err = _interpret(result)
        attempts.append({
            "form": label,
            "status": "OK" if obj is not None else "NONE_RETURNED",
            "returned_type": _type_tag(result),
            "obj_type": _type_tag(obj),
            "error_code": (int(err) if isinstance(err, int) else None),
            "error_status": PERSIST_STATUS_NAMES.get(err, None) if isinstance(err, int) else None,
            "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
            "_obj": obj,
        })
        if obj is not None:
            break  # first working form wins
    working = next((a for a in attempts if a.get("_obj") is not None), None)
    return {"working_form": working["form"] if working else None,
            "_obj": working.get("_obj") if working else None,
            "attempts": [{k: v for k, v in a.items() if k != "_obj"} for a in attempts]}


def _verify_identity(ext: Any, original_pid: Any, roundtripped: Any,
                     kind: str) -> dict[str, Any]:
    """Confirm the round-tripped entity IS the original.

    Primary check (kind-agnostic): re-read its persist ID and compare bytes
    with the original. Secondary (faces): compare Normal + area.
    Also test that it is selectable -- the lane needs Select2 to work.
    """
    out: dict[str, Any] = {}

    # Primary: persist-ID byte equality.
    try:
        pid2 = ext.GetPersistReference3(roundtripped)
        b0, b1 = _pid_to_bytes(original_pid), _pid_to_bytes(pid2)
        out["pid_byte_match"] = (b0 is not None and b0 == b1)
    except Exception as e:
        out["pid_byte_match"] = None
        out["pid_reread_error"] = f"{type(e).__name__}: {e}"

    # Secondary (faces only): normal/area sanity.
    if kind == "FACE":
        try:
            n = roundtripped.Normal
            out["roundtripped_normal"] = [round(float(x), 4) for x in n] if n else None
        except Exception as e:
            out["roundtripped_normal_error"] = f"{type(e).__name__}: {e}"

    # Selectable? (IEntity.Select2(Append, Mark) -- the no-Callout form that
    # marshals cleanly per builder._select_edges_by_points.)
    try:
        out["selectable"] = bool(roundtripped.Select2(False, 0))
    except Exception as e:
        out["selectable"] = None
        out["select_error"] = f"{type(e).__name__}: {e}"

    return out


def probe_entity(ext: Any, doc: Any, entity: Any, kind: str, idx: int,
                 rebuild_between: bool) -> dict[str, Any]:
    rec: dict[str, Any] = {"kind": kind, "index": idx}

    read = _read_persist_id(ext, entity)
    rec["read"] = {k: v for k, v in read.items() if k != "_pid"}
    if read["status"] != "OK":
        rec["verdict"] = "FAIL"
        rec["reason"] = f"GetPersistReference3 {read['status']}"
        return rec
    pid = read["_pid"]

    if rebuild_between:
        t0 = time.perf_counter()
        try:
            doc.ForceRebuild3(False)
            rec["rebuild_between"] = {"status": "OK",
                                      "elapsed_ms": (time.perf_counter() - t0) * 1000.0}
        except Exception as e:
            rec["rebuild_between"] = {"status": "ERROR",
                                      "message": f"{type(e).__name__}: {e}"}

    resolve = _resolve_persist_id(ext, pid)
    rec["resolve"] = {k: v for k, v in resolve.items() if k != "_obj"}
    obj = resolve["_obj"]
    if obj is None:
        rec["verdict"] = "PARTIAL"  # read OK, write-back unreachable -> Route-C signal
        rec["reason"] = "GetObjectByPersistReference3 returned no object in any form"
        return rec

    verify = _verify_identity(ext, pid, obj, kind)
    rec["verify"] = verify

    ok = (verify.get("pid_byte_match") is True
          and verify.get("selectable") is True)
    rec["verdict"] = "GREEN" if ok else "PARTIAL"
    if not ok:
        rec["reason"] = ("round-tripped but identity/selectability unconfirmed "
                         f"(pid_match={verify.get('pid_byte_match')}, "
                         f"selectable={verify.get('selectable')})")
    return rec


def run_com(skip_build: bool, save_first: bool, rebuild_between: bool) -> dict[str, Any]:
    sw = get_sw_app()
    doc = _ensure_part_doc(sw)

    build = {"skipped": skip_build}
    if not skip_build:
        build.update(build_single_box(doc))
        if not build.get("built"):
            return {"overall": "FAIL", "reason": "box did not build", "build": build}
        try:
            doc.EditRebuild3
        except Exception:
            pass

    if save_first:
        tmp = Path(tempfile.gettempdir()) / "ai-sw-bridge" / "spike_persist.sldprt"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        try:
            # SaveAs3(name, version=0 current, options=0 default)
            doc.SaveAs3(str(tmp), 0, 0)
            build["saved_to"] = str(tmp)
        except Exception as e:
            build["save_error"] = f"{type(e).__name__}: {e}"

    body = _first_body(doc)
    if body is None:
        return {"overall": "FAIL", "reason": "no solid body", "build": build}

    faces = list(body.GetFaces() or [])
    edges = list(body.GetEdges() or [])
    if not faces:
        return {"overall": "FAIL", "reason": "no faces on body", "build": build}

    ext = doc.Extension
    probes: list[dict[str, Any]] = []
    probes.append(probe_entity(ext, doc, faces[0], "FACE", 0, rebuild_between))
    if edges:
        probes.append(probe_entity(ext, doc, edges[0], "EDGE", 0, rebuild_between))

    # Corroborate the E2.1 finding on this path: is GetSelectByIDString still
    # dead on a face obtained via GetFaces? (Informational; not part of verdict.)
    selbyid: dict[str, Any] = {}
    try:
        s = faces[0].GetSelectByIDString
        selbyid = {"status": "OK", "python_type": _type_tag(s), "value": str(s)[:80]}
    except Exception as e:
        selbyid = {"status": "UNREACHABLE", "exception_type": type(e).__name__,
                   "message": str(e)[:120]}

    verdicts = [p["verdict"] for p in probes]
    if all(v == "GREEN" for v in verdicts):
        overall = "PASS"
    elif any(v == "PARTIAL" for v in verdicts):
        overall = "PARTIAL"
    else:
        overall = "FAIL"

    return {
        "overall": overall,
        "sw_revision": sw.RevisionNumber,
        "rebuild_between": rebuild_between,
        "saved_first": save_first,
        "interpretation": {
            "PASS": "persist-ref round-trips out-of-process AND survives rebuild -> build Phase 0 keystone",
            "PARTIAL": "read works, write-back OUT-param unreachable -> ROUTE-C signal (run --mode vba to confirm marshaler is the culprit)",
            "FAIL": "GetPersistReference3 read failed -> try --save-first; if still RED the API is unreachable late-bound",
        }[overall],
        "build": build,
        "GetSelectByIDString_on_GetFaces_path": selbyid,
        "probes": probes,
    }


def emit_vba() -> str:
    """Early-binding oracle. If Python is PARTIAL but this PASSes, the
    out-of-process marshaler (not the SW API) is the blocker -> Route-C."""
    return r"""' Spike v0.15 S-PERSIST VBA oracle.
' Paste into a Part-document module, press F5. Early binding handles the
' ByRef Error out-param natively, so this isolates whether the Python
' PARTIAL is a marshaling limitation rather than an API one.
Option Explicit
Sub ProbePersistRoundTrip()
    Dim swApp As Object, Part As Object, ext As Object
    Dim bodies As Variant, body As Object, faces As Variant, f As Object
    Dim pid As Variant, obj As Object, errCode As Long
    Set swApp = Application.SldWorks
    Set Part = swApp.ActiveDoc
    Set ext = Part.Extension
    bodies = Part.GetBodies2(0, True)
    If IsEmpty(bodies) Then MsgBox "No solid body": Exit Sub
    Set body = bodies(0)
    faces = body.GetFaces
    Set f = faces(0)
    pid = ext.GetPersistReference3(f)
    Part.ForceRebuild3 False
    Set obj = ext.GetObjectByPersistReference3(pid, errCode)
    If obj Is Nothing Then
        MsgBox "VBA round-trip FAILED, errCode=" & errCode
    Else
        MsgBox "VBA round-trip OK, errCode=" & errCode & _
               ", selectable=" & obj.Select2(False, 0)
    End If
End Sub
"""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", choices=["com", "vba"], default="com",
                   help="com = drive SW from Python; vba = emit the .bas oracle.")
    p.add_argument("--skip-build", action="store_true",
                   help="Probe the first solid body already in the active part.")
    p.add_argument("--save-first", action="store_true",
                   help="SaveAs3 to a temp path before probing (persist refs may "
                        "be more stable on a saved doc).")
    p.add_argument("--no-rebuild", action="store_true",
                   help="Skip the ForceRebuild3 between read and resolve "
                        "(disables the durability check).")
    p.add_argument("--out", type=Path, default=None,
                   help="Write JSON report to this path instead of stdout.")
    args = p.parse_args()

    if args.mode == "vba":
        out = Path(__file__).parent / "spike_persist_reference.bas"
        out.write_text(emit_vba(), encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
        return 0

    pythoncom.CoInitialize()
    try:
        result = run_com(args.skip_build, args.save_first, not args.no_rebuild)
    finally:
        pythoncom.CoUninitialize()

    payload = json.dumps(result, indent=2, default=str)
    if args.out is not None:
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)
    # PARTIAL exits 2 to distinguish the Route-C signal from a clean FAIL.
    return {"PASS": 0, "PARTIAL": 2, "FAIL": 1}.get(result["overall"], 1)


if __name__ == "__main__":
    sys.exit(main())
