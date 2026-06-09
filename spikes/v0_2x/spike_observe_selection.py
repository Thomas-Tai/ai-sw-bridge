"""Spike W43 — observe selection (perception axis) — go/no-go probe.

Tests whether the SelectionManager + GetSelectedObject6 + GetPersistReference3
pipeline correctly discriminates what was selected.

Pipeline under test:
  1. Create a 20mm box part.
  2. Programmatically SelectByID2 a known face → observe_selection reads it back.
  3. Assert count==1, type==face (swSelectType_e == 2).
  4. Clear selection → count==0.
  5. Select 2 distinct entities (face + edge) → count==2, types correct.
  6. Persist-ref round-trip: capture GetPersistReference3 → verify non-null.
  7. No-active-doc fail-closed test.

DISCRIMINATION GATE:
  - 1 face → count==1, type==2 ("face"), durable_ref is non-null base64 string
  - 0 entities → count==0
  - 2 mixed → count==2, types correct
  - no doc → ok==False, error=="no_active_doc"

Usage:
    .venv-py310/Scripts/python.exe spikes/v0_2x/spike_observe_selection.py
"""

from __future__ import annotations

import base64
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

WORKTREE = Path(__file__).resolve().parents[2]
RESULTS_PATH = WORKTREE / "_results" / "observe_selection.json"

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed, typed_extension  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app, get_active_doc  # noqa: E402
from ai_sw_bridge.observe_selection import read_selection, sw_get_selection  # noqa: E402

BOX_SIZE_M = 0.020  # 20 mm cube


def _find_part_template() -> str | None:
    import glob
    for pat in [
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\Part.PRTDOT",
        r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2024\templates\part.prtdot",
    ]:
        for m in glob.glob(pat):
            return m
    return None


def _retry(fn, *args, retries=3, delay=5, label=""):
    for attempt in range(retries):
        try:
            return fn(*args)
        except Exception as exc:
            if attempt < retries - 1:
                print(f"  [{label}] Attempt {attempt+1} failed: {exc!r}, retrying in {delay}s ...")
                time.sleep(delay)
            else:
                raise


def _make_box_part(sw_typed: Any, mod: Any, path: str) -> tuple[Any | None, str | None]:
    """Create a 20mm cube part. Returns (doc, error)."""
    try:
        doc = _retry(
            sw_typed.NewDocument,
            _find_part_template(),
            0, 0, 0,
            retries=3, delay=5, label="part_new",
        )
        if doc is None:
            return None, "NewDocument(part) returned None"
        dt = typed(doc, "IModelDoc2", module=mod)

        half = BOX_SIZE_M / 2.0
        dt.SketchManager.InsertSketch(True)
        dt.SketchManager.CreateCenterRectangle(0, 0, 0, half, half, 0)
        dt.SketchManager.InsertSketch(True)

        dt.ClearSelection2(True)
        dt.SelectByID("Sketch1", "SKETCH", 0, 0, 0)
        feat = dt.FeatureManager.FeatureExtrusion2(
            True, False, False, 0, 0,
            BOX_SIZE_M, 0.0,
            False, False, False, False,
            0.0, 0.0,
            False, False, False, False,
            True, True, True,
            0, 0,
            False,
        )
        if feat is None:
            return None, "FeatureExtrusion2 returned None"

        dt.ForceRebuild3(True)
        time.sleep(1)

        _retry(dt.SaveAs3, path, 0, 2, retries=2, delay=3, label="part_save")
        return doc, None
    except Exception as exc:
        return None, f"exception: {exc!r}"


def _select_face_by_id(doc: Any, mod: Any) -> tuple[bool, str]:
    """Select the +Z face of a 20mm centered box via SelectByID2.

    The +Z face is at z = +10mm = 0.01m.
    Uses the typed IModelDocExtension.SelectByID2 with Callout=None (the
    known marshing limitation — 5-arg legacy SelectByID is on IModelDoc2,
    SelectByID2 is on Extension).
    """
    try:
        ext = typed(doc.Extension, "IModelDocExtension", module=mod)
        # SelectByID2(Name, Type, X, Y, Z, Append, Mark, Callout, SelectOption)
        # For face selection by coordinate, Name="" and Type="FACE"
        ok = ext.SelectByID2("", "FACE", 0.0, 0.0, 0.01, False, 0, None, 0)
        return bool(ok), ""
    except Exception as exc:
        return False, f"SelectByID2: {exc!r}"


def _select_edge_by_id(doc: Any, mod: Any) -> tuple[bool, str]:
    """Select an edge of a 20mm centered box via SelectByID2.

    Pick a vertical edge at (+10mm, +10mm, 0).
    """
    try:
        ext = typed(doc.Extension, "IModelDocExtension", module=mod)
        ok = ext.SelectByID2("", "EDGE", 0.01, 0.01, 0.0, True, 0, None, 0)
        return bool(ok), ""
    except Exception as exc:
        return False, f"SelectByID2: {exc!r}"


def _close_all(sw_typed: Any) -> None:
    try:
        sw_typed.CloseAllDocuments(True)
    except Exception:
        pass
    time.sleep(1)


def main() -> None:
    pythoncom.CoInitialize()
    sw = get_sw_app()
    mod = wrapper_module()
    sw_typed = typed(sw, "ISldWorks", module=mod)

    print("[S1] Closing all documents for clean slate ...")
    _close_all(sw_typed)
    time.sleep(2)

    result: dict[str, Any] = {
        "verdict": "PENDING",
        "test_1_face": {"ok": False, "count": None, "type": None, "type_name": None, "has_durable_ref": False, "error": None},
        "test_0_empty": {"ok": False, "count": None, "error": None},
        "test_2_mixed": {"ok": False, "count": None, "types": [], "type_names": [], "durable_refs": [], "error": None},
        "test_no_doc": {"ok": None, "error": None},
        "test_persist_roundtrip": {"captured": False, "resolved": False, "error": None},
        "errors": [],
    }

    tmpdir = tempfile.mkdtemp(prefix="aisw_W43_")
    part_path = str(Path(tmpdir) / "box_20mm.sldprt")

    try:
        # ── Step 1: Create box part ──────────────────────────────────────
        print("[S1] Creating 20mm box part ...")
        part_doc, err = _make_box_part(sw_typed, mod, part_path)
        if err:
            result["errors"].append(f"make_part: {err}")
            result["verdict"] = "NO-GO"
            _write_result(result)
            return
        print(f"[S1] Part saved: {part_path}")
        time.sleep(2)

        doc = get_active_doc(sw)
        if doc is None:
            result["errors"].append("no active doc after part creation")
            result["verdict"] = "NO-GO"
            _write_result(result)
            return

        doc_typed = typed(doc, "IModelDoc2", module=mod)

        # ── Test 1: Select one face, read back ──────────────────────────
        print("[S1] TEST 1: Select one face via SelectByID2 ...")
        doc_typed.ClearSelection2(True)
        time.sleep(0.5)

        ok, sel_err = _select_face_by_id(doc, mod)
        if not ok:
            result["test_1_face"]["error"] = f"face select failed: {sel_err}"
            result["errors"].append(f"test_1: {sel_err}")
            print(f"[S1]   FACE select FAILED: {sel_err}")
        else:
            print("[S1]   Face selected OK, reading back ...")
            time.sleep(0.5)
            sel_result = sw_get_selection(doc)
            t1 = result["test_1_face"]
            t1["ok"] = sel_result.get("ok", False)
            if sel_result.get("selection"):
                t1["count"] = sel_result["selection"]["count"]
                if sel_result["selection"]["selections"]:
                    s0 = sel_result["selection"]["selections"][0]
                    t1["type"] = s0.get("type")
                    t1["type_name"] = s0.get("type_name")
                    t1["has_durable_ref"] = s0.get("durable_ref") is not None
                    print(f"[S1]   count={t1['count']}, type={t1['type']} ({t1['type_name']}), durable_ref={'YES' if t1['has_durable_ref'] else 'NO'}")

            if not t1["ok"]:
                t1["error"] = sel_result.get("error")
                result["errors"].append(f"test_1: selection not ok: {sel_result.get('error')}")

        # ── Test 2: Clear selection, read back (should be count==0) ─────
        print("[S1] TEST 2: Clear selection ...")
        doc_typed.ClearSelection2(True)
        time.sleep(0.5)

        sel_result_0 = sw_get_selection(doc)
        t0 = result["test_0_empty"]
        t0["ok"] = sel_result_0.get("ok", False)
        if sel_result_0.get("selection"):
            t0["count"] = sel_result_0["selection"]["count"]
        print(f"[S1]   count={t0['count']}, ok={t0['ok']}")
        if not t0["ok"]:
            t0["error"] = sel_result_0.get("error")

        # ── Test 3: Select face + edge (2 mixed entities) ───────────────
        print("[S1] TEST 3: Select face + edge (2 mixed) ...")
        doc_typed.ClearSelection2(True)
        time.sleep(0.5)

        ok_face, face_err = _select_face_by_id(doc, mod)
        if ok_face:
            ok_edge, edge_err = _select_edge_by_id(doc, mod)
            if not ok_edge:
                result["test_2_mixed"]["error"] = f"edge select failed: {edge_err}"
                result["errors"].append(f"test_3: {edge_err}")
                print(f"[S1]   EDGE select FAILED: {edge_err}")
            else:
                time.sleep(0.5)
                sel_result_2 = sw_get_selection(doc)
                t2 = result["test_2_mixed"]
                t2["ok"] = sel_result_2.get("ok", False)
                if sel_result_2.get("selection"):
                    t2["count"] = sel_result_2["selection"]["count"]
                    for s in sel_result_2["selection"]["selections"]:
                        t2["types"].append(s.get("type"))
                        t2["type_names"].append(s.get("type_name"))
                        t2["durable_refs"].append(s.get("durable_ref") is not None)
                print(f"[S1]   count={t2['count']}, types={t2['types']}, names={t2['type_names']}, durable_refs={t2['durable_refs']}")
                if not t2["ok"]:
                    t2["error"] = sel_result_2.get("error")
        else:
            result["test_2_mixed"]["error"] = f"face select failed: {face_err}"
            result["errors"].append(f"test_3: {face_err}")

        # ── Test 4: Persist-ref round-trip ──────────────────────────────
        print("[S1] TEST 4: Persist-ref round-trip ...")
        doc_typed.ClearSelection2(True)
        time.sleep(0.5)
        ok_face2, _ = _select_face_by_id(doc, mod)
        if ok_face2:
            time.sleep(0.5)
            sel_rt = sw_get_selection(doc)
            if sel_rt.get("selection") and sel_rt["selection"]["selections"]:
                dref = sel_rt["selection"]["selections"][0].get("durable_ref")
                if dref:
                    result["test_persist_roundtrip"]["captured"] = True
                    # Decode and attempt resolve
                    try:
                        padding = 4 - len(dref) % 4
                        if padding < 4:
                            dref_padded = dref + "=" * padding
                        else:
                            dref_padded = dref
                        pid_bytes = base64.urlsafe_b64decode(dref_padded)
                        ext = typed_extension(doc)
                        entity, err_code = ext.GetObjectByPersistReference3(pid_bytes)
                        result["test_persist_roundtrip"]["resolved"] = (
                            entity is not None and (err_code is None or err_code == 0)
                        )
                        print(f"[S1]   persist-ref: captured=True, resolved={result['test_persist_roundtrip']['resolved']}, err_code={err_code}")
                    except Exception as exc:
                        result["test_persist_roundtrip"]["error"] = f"resolve: {exc!r}"
                        print(f"[S1]   persist-ref resolve error: {exc!r}")
                else:
                    result["test_persist_roundtrip"]["error"] = "no durable_ref captured"
                    print("[S1]   persist-ref: no durable_ref captured")
        else:
            result["test_persist_roundtrip"]["error"] = "face select failed"

        # ── Test 5: No-active-doc fail-closed ───────────────────────────
        print("[S1] TEST 5: No-active-doc fail-closed ...")
        _close_all(sw_typed)
        time.sleep(1)

        from ai_sw_bridge.observe import SolidWorksObserver
        no_doc_result = SolidWorksObserver().selection()
        tnd = result["test_no_doc"]
        tnd["ok"] = no_doc_result.get("ok")
        tnd["error"] = no_doc_result.get("error")
        print(f"[S1]   no-doc: ok={tnd['ok']}, error={tnd['error']}")

        # ── VERDICT ─────────────────────────────────────────────────────
        checks = []

        # Check 1: single face — assert BOTH the int type AND the type_name
        # (the name table was the W43 bug; assert it so a wrong label fails).
        t1 = result["test_1_face"]
        c1 = (
            t1["ok"] is True
            and t1["count"] == 1
            and t1["type"] == 2  # swSelFACES
            and t1["type_name"] == "face"  # table correctness
            and t1["has_durable_ref"] is True
        )
        checks.append(("1_face", c1))

        # Check 2: empty
        t0 = result["test_0_empty"]
        c2 = t0["ok"] is True and t0["count"] == 0
        checks.append(("0_empty", c2))

        # Check 3: mixed — the EDGE in this set must read type 1 AND name
        # "edge" (NOT "everything" — the original mislabel). face must read
        # "face". This is the discrimination the first cut got wrong.
        t2 = result["test_2_mixed"]
        c3 = (
            t2["ok"] is True
            and t2["count"] == 2
            and 2 in t2["types"]  # face int
            and "face" in t2["type_names"]
            and "edge" in t2["type_names"]  # edge=1 → "edge", NOT "everything"
        )
        checks.append(("2_mixed", c3))

        # Check 4: no doc
        tnd = result["test_no_doc"]
        c4 = tnd["ok"] is False and tnd["error"] == "no_active_doc"
        checks.append(("no_doc", c4))

        # Check 5: persist round-trip
        c5 = result["test_persist_roundtrip"]["captured"] and result["test_persist_roundtrip"]["resolved"]
        checks.append(("persist_rt", c5))

        all_pass = all(c for _, c in checks)
        result["verdict"] = "GREEN" if all_pass else "PARTIAL"
        result["checks"] = {name: "PASS" if ok else "FAIL" for name, ok in checks}

        if not all_pass:
            failed = [name for name, ok in checks if not ok]
            result["errors"].append(f"failed checks: {failed}")

    except Exception as exc:
        result["errors"].append(f"top-level: {exc!r}")
        result["verdict"] = "NO-GO"
        import traceback
        traceback.print_exc()
    finally:
        try:
            sw_typed.CloseAllDocuments(True)
        except Exception:
            pass
        _write_result(result)
        print(f"\n[S1] VERDICT: {result['verdict']}")
        if result.get("checks"):
            for name, status in result["checks"].items():
                print(f"  {name}: {status}")
        if result["errors"]:
            print(f"[S1] Errors: {result['errors']}")


def _write_result(result: dict[str, Any]) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"[S1] Results written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
