"""Spike v0.16 / S-MATERIAL v3 — enumerate the install's real material DBs,
then find a (db, name) form that SetMaterialPropertyName2 actually honours.

v2 proved the marshaling wall is gone (typed IPartDoc.GetMaterialPropertyName2
and typed IModelDocExtension.GetMassProperties2 both return OK, volume reads
4e-6 m3 correctly). But the assignment itself did NOT stick: density stayed at
the 1000 kg/m3 water default and read-back was empty. So the (db, name) strings
are wrong for THIS install — the Hole-Wizard lesson exactly. Stop guessing;
enumerate.

SldWorks exposes the installed material databases:
    n = sw.GetMaterialDatabaseCount()
    paths = sw.GetMaterialDatabases()      # array of .sldmat file paths

The `db` arg to SetMaterialPropertyName2 is install-dependent — this spike
tries, for each enumerated database, several `db` forms (full .sldmat path,
stem, "SOLIDWORKS Materials") against a small set of likely-present names, and
records which combination makes the post-assignment density move off 1000.

Verdict: PASS if any (db, name) form moves density AND round-trips a non-empty
read-back. The winning form is what material.py will use.

Non-destructive: own blank Part, never saves, closes own doc.
Usage:  .venv-py310\Scripts\python spikes\v0_16\spike_material_v3.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
_V15 = Path(__file__).resolve().parents[1] / "v0_15"
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_V15))

import pythoncom  # noqa: E402

from ai_sw_bridge.com.earlybind import typed  # noqa: E402
from spike_earlybind_persist import connect_running_sw  # noqa: E402

BOX_W_M, BOX_H_M, BOX_D_M = 0.020, 0.020, 0.010
SW_DEFAULT_TEMPLATE_PART = 8

# Names worth trying — common steels/alloys in the stock SOLIDWORKS library.
CANDIDATE_NAMES = [
    "AISI 1020 Steel (SS)",
    "AISI 1020",
    "Plain Carbon Steel",
    "Alloy Steel",
    "1060 Alloy",
    "6061 Alloy",
]


def _title(doc: Any) -> Any:
    t = doc.GetTitle
    return t() if callable(t) else t


def _build_box(doc: Any) -> bool:
    if not doc.SelectByID("Front Plane", "PLANE", 0.0, 0.0, 0.0):
        return False
    sk = doc.SketchManager
    sk.InsertSketch(True)
    sk.CreateCornerRectangle(
        -BOX_W_M / 2, -BOX_H_M / 2, 0.0, BOX_W_M / 2, BOX_H_M / 2, 0.0
    )
    sk.InsertSketch(True)
    fm = doc.FeatureManager
    base = (
        True,
        False,
        False,
        0,
        0,
        BOX_D_M,
        0.0,
        False,
        False,
        False,
        False,
        0.0,
        0.0,
        False,
        False,
        False,
        False,
        True,
        True,
        True,
        0,
        0.0,
    )
    try:
        feat = fm.FeatureExtrusion2(*base, False)
    except Exception:  # noqa: BLE001
        feat = fm.FeatureExtrusion2(*base)
    return feat is not None


def _density(doc: Any) -> float | None:
    try:
        ext = typed(doc.Extension, "IModelDocExtension")
        props = ext.GetMassProperties2(0, 1, True)
        vals = list(props)
        arr = list(vals[0]) if vals and isinstance(vals[0], (tuple, list)) else vals
        if len(arr) >= 6 and arr[3] and float(arr[3]) > 0:
            return float(arr[5]) / float(arr[3])
    except Exception:  # noqa: BLE001
        return None
    return None


def _readback(doc: Any) -> tuple[str, str]:
    """(name, db) from typed IPartDoc.GetMaterialPropertyName2."""
    try:
        part = typed(doc, "IPartDoc")
        rb = part.GetMaterialPropertyName2("")
        if isinstance(rb, (tuple, list)) and len(rb) >= 2:
            return str(rb[0]), str(rb[1])
        return str(rb), ""
    except Exception as e:  # noqa: BLE001
        return f"<err {type(e).__name__}>", ""


def _enumerate_dbs(sw: Any) -> list[str]:
    paths: list[str] = []
    try:
        raw = sw.GetMaterialDatabases()
        if raw is not None:
            try:
                paths = [str(p) for p in raw]
            except TypeError:
                paths = [str(raw)]
    except Exception:  # noqa: BLE001
        pass
    return paths


def _db_forms(db_paths: list[str]) -> list[str]:
    """Candidate `db` argument strings, most-likely-first."""
    forms: list[str] = ["", "SOLIDWORKS Materials", "SolidWorks Materials"]
    for p in db_paths:
        forms.append(p)  # full .sldmat path
        forms.append(Path(p).stem)  # filename without extension
    # de-dup, preserve order
    seen: set[str] = set()
    out: list[str] = []
    for f in forms:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def run() -> dict[str, Any]:
    sw = connect_running_sw()
    result: dict[str, Any] = {}
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception:  # noqa: BLE001
        result["sw_revision"] = "<unreadable>"

    db_paths = _enumerate_dbs(sw)
    result["material_databases"] = db_paths
    db_forms = _db_forms(db_paths)
    result["db_forms_tried"] = db_forms

    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {"overall": "FAIL", "reason": "NewDocument returned None", **result}

    title = _title(doc)
    trials: list[dict[str, Any]] = []
    winner: dict[str, Any] | None = None
    try:
        if not _build_box(doc):
            return {"overall": "FAIL", "reason": "box did not build", **result}
        try:
            doc.EditRebuild3
        except Exception:  # noqa: BLE001
            pass
        baseline = _density(doc)
        result["baseline_density"] = baseline

        part_dyn = doc  # SetMaterialPropertyName2 is on IPartDoc; dynamic call OK
        for db in db_forms:
            for name in CANDIDATE_NAMES:
                try:
                    part_dyn.SetMaterialPropertyName2("", db, name)
                except Exception as e:  # noqa: BLE001
                    trials.append(
                        {"db": db, "name": name, "set_error": f"{type(e).__name__}"}
                    )
                    continue
                try:
                    doc.ForceRebuild3(False)
                except Exception:  # noqa: BLE001
                    try:
                        doc.EditRebuild3
                    except Exception:  # noqa: BLE001
                        pass
                dens = _density(doc)
                rb_name, rb_db = _readback(doc)
                moved = (
                    dens is not None
                    and baseline is not None
                    and abs(dens - baseline) > 50.0
                )
                rec = {
                    "db": db,
                    "name": name,
                    "density": dens,
                    "rb_name": rb_name,
                    "rb_db": rb_db,
                    "moved": moved,
                }
                trials.append(rec)
                if moved and winner is None:
                    winner = rec
                # Reset to no-material so each trial starts clean.
                try:
                    part_dyn.SetMaterialPropertyName2("", "", "")
                    doc.ForceRebuild3(False)
                except Exception:  # noqa: BLE001
                    pass
                if winner is not None:
                    break
            if winner is not None:
                break
    finally:
        try:
            sw.CloseDoc(title)
        except Exception:  # noqa: BLE001
            pass

    result["trials"] = trials
    result["winner"] = winner
    result["overall"] = "PASS" if winner else "PARTIAL"
    result["interpretation"] = (
        f"Honoured form: db={winner['db']!r} name={winner['name']!r} "
        f"density={winner['density']:.1f} -> wire into material.py."
        if winner
        else "No (db, name) form moved density off the 1000 default; inspect "
        "material_databases / trials to see what the install actually exposes."
    )
    return result


def main() -> int:
    pythoncom.CoInitialize()
    try:
        result = run()
    finally:
        pythoncom.CoUninitialize()
    out = Path(__file__).parent / "_results" / "material_v3.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    print(f"\nwrote {out}", file=sys.stderr)
    return {"PASS": 0, "PARTIAL": 2, "FAIL": 1}.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
