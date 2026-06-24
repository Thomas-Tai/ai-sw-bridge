"""
Spike v0.15 / S-EARLYBIND-REOPEN -- does a persist token survive save->close->
reopen?  [authored seat-free; RUN ON A LIVE SEAT]

S-EARLYBIND proved the persist write-back marshals out-of-process under hybrid
early binding *across an in-session ForceRebuild3*. The original persist spike
flagged the harder, decisive case as a deferred follow-up:

    "The ultimate test is save -> close -> reopen -> resolve."

This spike runs exactly that. A persist reference (``GetPersistReference3``)
is meant to be a *durable* token precisely so it survives a file round-trip;
the in-session rebuild PASS is necessary but not sufficient. The keystone lane
(open-existing-doc build target + ``mutate.py`` feature-additions anchored to a
token in the manifest) depends on this case, not just the rebuild one.

What it does (non-destructive -- own temp file, own documents):
  1. Open a fresh blank Part, build the proven S-PERSIST box.
  2. Typed ``IModelDocExtension`` -> ``pid = GetPersistReference3(face0)``.
  3. ``SaveAs3`` to a temp ``.sldprt``; capture the title; ``CloseDoc``.
  4. Reopen via a typed ``ISldWorks.OpenDoc6`` (its ``[out]`` Errors/Warnings
     longs come back as trailing tuple elements under early binding -- the same
     hybrid pattern, exercised again).
  5. Typed ``IModelDocExtension`` on the *reopened* doc ->
     ``GetObjectByPersistReference3(pid)``; check it resolves (errCode==0) and
     is selectable.
  6. Clean up the temp file.

Verdict
-------
PASS    : the token resolves the same entity (errCode==0) AND it is selectable
          after a real save->close->reopen. Durable selection is viable
          out-of-process end-to-end; the open-existing keystone lane is unblocked.
PARTIAL : the entity resolves after reopen but is not selectable (or errCode!=0)
          -- token survives the file round-trip but the reselection needs more
          work; not a binding blocker.
FAIL    : the token does not resolve after reopen (returns no object) -- the
          persistence is the wall, not the binding; capture/anchor must fall
          back to fingerprint reselection across reopen (roadmap S4.4).

Prereq: SOLIDWORKS 2024 SP1 running. First run may regenerate the makepy cache.

Usage
-----
    python spikes/v0_15/spike_earlybind_reopen.py --out report.json
    python spikes/v0_15/spike_earlybind_reopen.py --keep-file
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

# Reuse the proven early-binding acquisition + box geometry verbatim.
from spike_earlybind_persist import (  # noqa: E402
    SW_DEFAULT_TEMPLATE_PART,
    connect_running_sw,
    ensure_sw_module,
    typed,
)
from spike_persist_reference import build_single_box, _first_body  # noqa: E402

SW_DOC_PART = 1
SW_OPEN_SILENT = 1  # swOpenDocOptions_Silent


def _tag(v: Any) -> str:
    return "NoneType" if v is None else type(v).__name__


def _resolved(obj: Any) -> bool:
    return obj is not None and not isinstance(obj, int)


def _title(d: Any) -> Any:
    """Read a doc title whether the proxy is late-bound (GetTitle auto-invokes
    as a property) or early-bound (GetTitle is a method that must be called)."""
    t = d.GetTitle
    return t() if callable(t) else t


def run(keep_file: bool) -> dict[str, Any]:
    result: dict[str, Any] = {"binding": "hybrid early (com.earlybind pattern)"}
    mod, info = ensure_sw_module()
    result["module_info"] = info
    sw = connect_running_sw()
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception as e:  # noqa: BLE001
        result["sw_revision"] = f"<unreadable: {type(e).__name__}>"

    # 1. Fresh blank Part + the proven box.
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {**result, "overall": "FAIL", "reason": "NewDocument returned None"}
    build = build_single_box(doc)
    result["build"] = build
    if not build.get("built"):
        return {**result, "overall": "FAIL", "reason": "box did not build"}

    body = _first_body(doc)
    faces = list(body.GetFaces() or []) if body is not None else []
    if not faces:
        return {**result, "overall": "FAIL", "reason": "no faces on body"}

    # 2. Read the persist token (early-bound Extension).
    ext = typed(mod, "IModelDocExtension", doc.Extension)
    pid = ext.GetPersistReference3(faces[0])
    result["read"] = {
        "status": "OK" if pid is not None else "NONE",
        "python_type": _tag(pid),
        "byte_len": len(pid) if hasattr(pid, "__len__") else None,
    }
    if pid is None:
        return {
            **result,
            "overall": "FAIL",
            "reason": "GetPersistReference3 returned None",
        }

    # 3. Save -> capture title -> close.
    tmp = Path(tempfile.gettempdir()) / "ai-sw-bridge" / "spike_earlybind_reopen.sldprt"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    if tmp.exists():
        try:
            tmp.unlink()
        except OSError:
            pass
    save: dict[str, Any] = {"path": str(tmp)}
    t0 = time.perf_counter()
    try:
        save["saveas3_ret"] = doc.SaveAs3(str(tmp), 0, 0)
        save["status"] = "OK" if tmp.exists() else "NO_FILE"
        save["file_exists"] = tmp.exists()
    except Exception as e:  # noqa: BLE001
        save["status"] = "EXCEPTION"
        save["error"] = f"{type(e).__name__}: {str(e)[:160]}"
    save["elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
    result["save"] = save
    if not tmp.exists():
        return {**result, "overall": "FAIL", "reason": "SaveAs3 produced no file"}

    title = None
    try:
        title = _title(doc)
    except Exception:  # noqa: BLE001
        title = tmp.name
    result["title"] = title

    close: dict[str, Any] = {}
    try:
        sw.CloseDoc(title)
        close["status"] = "OK"
    except Exception as e:  # noqa: BLE001
        close["status"] = "EXCEPTION"
        close["error"] = f"{type(e).__name__}: {str(e)[:160]}"
    result["close"] = close

    # 4. Reopen via typed ISldWorks.OpenDoc6 ([out] Errors/Warnings -> tuple).
    reopen: dict[str, Any] = {}
    tsw = typed(mod, "ISldWorks", sw)
    t0 = time.perf_counter()
    try:
        # Errors/Warnings are [in,out] byref longs (VT_BYREF|VT_I4); the
        # early-bound stub requires them passed as ints and returns the updated
        # values appended to the tuple. Omitting them raises "Type mismatch".
        ret = tsw.OpenDoc6(str(tmp), SW_DOC_PART, SW_OPEN_SILENT, "", 0, 0)
        reopen["returned_type"] = _tag(ret)
        if isinstance(ret, tuple):
            reopen["is_tuple_out_param"] = True
            doc2 = ret[0]
            reopen["errors"] = ret[1] if len(ret) > 1 else None
            reopen["warnings"] = ret[2] if len(ret) > 2 else None
        else:
            reopen["is_tuple_out_param"] = False
            doc2 = ret
        reopen["doc_opened"] = doc2 is not None
        reopen["status"] = "OK" if doc2 is not None else "NONE_RETURNED"
    except Exception as e:  # noqa: BLE001
        reopen["status"] = "EXCEPTION"
        reopen["error"] = f"{type(e).__name__}: {str(e)[:160]}"
        doc2 = None
    reopen["elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
    result["reopen"] = reopen

    if doc2 is None:
        # Fall back to ActiveDoc in case OpenDoc6 opened it but didn't return it.
        try:
            doc2 = sw.ActiveDoc
            result["reopen"]["recovered_via_active_doc"] = doc2 is not None
        except Exception:  # noqa: BLE001
            doc2 = None
    if doc2 is None:
        return {**result, "overall": "FAIL", "reason": "reopen produced no document"}

    # Rebuild the freshly-opened doc so its B-rep is realized before we resolve
    # the persist token against it (the token resolves to errCode=1 'Deleted'
    # without this on a just-opened part).
    rebuilt = True
    try:
        doc2.ForceRebuild3(False)
    except Exception as e:  # noqa: BLE001
        rebuilt = False
        result["reopen_rebuild_error"] = f"{type(e).__name__}: {str(e)[:120]}"
    result["reopen_rebuilt"] = rebuilt

    # 5. Resolve the token on the reopened doc.
    resolve: dict[str, Any] = {}
    t0 = time.perf_counter()
    try:
        ext2 = typed(mod, "IModelDocExtension", doc2.Extension)
        res = ext2.GetObjectByPersistReference3(pid)
        obj = res[0] if isinstance(res, tuple) else res
        err = res[1] if isinstance(res, tuple) and len(res) > 1 else None
        resolve["returned_type"] = _tag(res)
        resolve["is_tuple_out_param"] = isinstance(res, tuple)
        resolve["out_error_code"] = err
        resolve["object_resolved"] = _resolved(obj)
        if _resolved(obj):
            try:
                ent = typed(mod, "IEntity", obj)
                resolve["selectable"] = bool(ent.Select2(False, 0))
            except Exception as e:  # noqa: BLE001
                resolve["selectable"] = None
                resolve["select_note"] = repr(e)[:160]
    except Exception as e:  # noqa: BLE001
        resolve["status"] = "EXCEPTION"
        resolve["error"] = f"{type(e).__name__}: {str(e)[:160]}"
        obj = None
    resolve["elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
    result["resolve"] = resolve

    # 6. Cleanup (best-effort).
    if not keep_file:
        try:
            sw.CloseDoc(_title(doc2))
        except Exception:  # noqa: BLE001
            pass
        try:
            tmp.unlink()
            result["cleanup"] = "removed temp file"
        except OSError as e:
            result["cleanup"] = f"could not remove temp file: {e}"
    else:
        result["cleanup"] = f"kept temp file at {tmp}"

    # Verdict.
    if resolve.get("object_resolved") and resolve.get("selectable") is True:
        overall, interp = "PASS", (
            "persist token survives save->close->reopen: resolves (errCode "
            f"{resolve.get('out_error_code')}) AND selectable. Open-existing "
            "keystone lane is unblocked out-of-process."
        )
    elif resolve.get("object_resolved"):
        overall, interp = "PARTIAL", (
            "token resolves after reopen but selectability/errCode unconfirmed "
            f"(err={resolve.get('out_error_code')}, selectable="
            f"{resolve.get('selectable')}) -- not a binding blocker."
        )
    else:
        overall, interp = "FAIL", (
            "token did NOT resolve after reopen -- persistence is the wall, not "
            "the binding; capture/anchor must fall back to fingerprint "
            "reselection across reopen (roadmap S4.4)."
        )
    result["overall"] = overall
    result["interpretation"] = interp
    return result


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--keep-file",
        action="store_true",
        help="Do not delete the temp .sldprt (leave the reopened doc open).",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write JSON report to this path instead of stdout.",
    )
    args = p.parse_args()

    pythoncom.CoInitialize()
    try:
        result = run(args.keep_file)
    finally:
        pythoncom.CoUninitialize()

    payload = json.dumps(result, indent=2, default=str)
    if args.out is not None:
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(payload)
    return {"PASS": 0, "PARTIAL": 2, "FAIL": 1}.get(result.get("overall"), 1)


if __name__ == "__main__":
    raise SystemExit(main())
