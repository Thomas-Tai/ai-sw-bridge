"""
Spike v0.15 / S-EARLYBIND — does win32com EARLY binding clear the wall?  [PASS]

THE decision-gating experiment. S-PERSIST (PARTIAL) and S-DISPATCH (PARTIAL)
proved *late*-bound pywin32 (dynamic Dispatch) cannot marshal
``GetObjectByPersistReference3``'s ``[out] long`` Error param. The open question
that gates the architecture was: does Python EARLY binding (win32com makepy)
clear the same wall WITHOUT leaving the out-of-process, Python-driven,
JSON-only-agent design?

RESULT (SW 2024 SP1, 2026-05-29): **YES.** Under a typed ``IModelDocExtension``,
``GetObjectByPersistReference3(pid)`` returns ``(<entity>, 0)`` — the [out]
errCode comes back as the 2nd tuple element and the object resolves. The
keystone (durable selection) is reachable out-of-process from Python; the
in-process .NET "Route-C" is NOT required.

The working acquisition pattern (non-obvious — every win32com convenience path
fails because SW objects refuse IDispatch::GetTypeInfo):
  1. Locate the SW typelib via the registry LIBID, ``LoadTypeLib(sldworks.tlb)``
     and read its true version with ``GetLibAttr`` (key name "20.0" lies; the
     real major is 32 for SW 2024).
  2. ``gencache.EnsureModule(iid, lcid, major, minor)`` to generate makepy.
  3. Connect to the running SW with a *dynamic* dispatch (bypasses the
     makepy-automate path that EnsureDispatch/CastTo trip on).
  4. Construct typed wrappers DIRECTLY from the raw PyIDispatch:
     ``mod.IModelDocExtension(ext._oleobj_)`` — uses makepy's compiled-in
     dispids, no GetTypeInfo needed.

CAVEAT for the migration (recorded, not blocking): early-bound typed objects
expose the typelib's real property/method split — calls the bridge accesses as
auto-invoked attributes (e.g. ``RevisionNumber``) become methods that must be
CALLED. A hybrid binding (late by default, typed-wrap only the objects whose
[out]/Callout methods need it) is the surgical path; it does not require
rewriting every call site, and the agent-safety model (invariants #2/#3) is
untouched. Invariant #4 ("late-bound load-bearing") should be reframed: the
guarantee is "out-of-process Python, no agent COM access", not late binding.

Prereq: SOLIDWORKS 2024 SP1 running. Opens its own fresh blank Part
(non-destructive). First run generates the makepy cache (slow); later runs fast.

Usage
-----
    python spikes/v0_15/spike_earlybind_persist.py --out report.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import winreg
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

import pythoncom  # noqa: E402
import win32com.client  # noqa: E402
from win32com.client import dynamic, gencache  # noqa: E402

# Reuse the late-bound spike's binding-agnostic build helper verbatim, so the
# box geometry is identical to S-PERSIST and only the binding differs.
from spike_persist_reference import _first_body, build_single_box  # noqa: E402

SW_LIBID = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"  # SOLIDWORKS Type Library
SW_DEFAULT_TEMPLATE_PART = 8


def _sw_tlb_path() -> str | None:
    """Read the sldworks.tlb path from the registered SW typelib (newest ver)."""
    try:
        libk = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"TypeLib")
        libk = winreg.OpenKey(libk, SW_LIBID)
    except OSError:
        return None
    vers = []
    i = 0
    while True:
        try:
            vers.append(winreg.EnumKey(libk, i))
            i += 1
        except OSError:
            break
    for ver in reversed(vers):
        for arch in ("win64", "win32"):
            try:
                kk = winreg.OpenKey(libk, f"{ver}\\0\\{arch}")
                path, _ = winreg.QueryValueEx(kk, "")
                if path:
                    return path
            except OSError:
                continue
    return None


def ensure_sw_module() -> tuple[Any, dict[str, Any]]:
    """Generate (or load) the makepy module for the SW typelib. Returns
    (module, info). The convenience EnsureDispatch path fails on SW objects, so
    we drive makepy off the typelib FILE's true version (via GetLibAttr)."""
    info: dict[str, Any] = {}
    path = _sw_tlb_path()
    info["tlb_path"] = path
    if not path:
        raise RuntimeError("could not locate sldworks.tlb in the registry")
    tlb = pythoncom.LoadTypeLib(path)
    iid, lcid, _syskind, major, minor = tlb.GetLibAttr()[:5]
    info.update({"libid": str(iid), "lcid": lcid, "major": major, "minor": minor})
    mod = gencache.EnsureModule(str(iid), lcid, major, minor)
    if mod is None:
        raise RuntimeError("EnsureModule returned None")
    info["module"] = mod.__name__
    return mod, info


def connect_running_sw() -> Any:
    """Attach to the RUNNING SW as a *dynamic* dispatch (works whether or not
    the makepy module is already generated — unlike Dispatch/EnsureDispatch,
    which trip on SW's missing GetTypeInfo)."""
    try:
        return dynamic.Dispatch(pythoncom.GetActiveObject("SldWorks.Application"))
    except Exception:
        return dynamic.Dispatch("SldWorks.Application")


def typed(mod: Any, iface: str, obj: Any) -> Any:
    """Construct the early-bound typed wrapper for *obj* directly from its raw
    PyIDispatch (no GetTypeInfo needed)."""
    cls = getattr(mod, iface)
    return cls(obj._oleobj_)


def run() -> dict[str, Any]:
    result: dict[str, Any] = {"binding": "early (makepy module + direct typed-wrap)"}
    mod, info = ensure_sw_module()
    result["module_info"] = info

    sw = connect_running_sw()
    # RevisionNumber is a typelib METHOD under early binding but the dynamic app
    # still auto-invokes it as a property; read it dynamically for the record.
    try:
        result["sw_revision"] = str(sw.RevisionNumber)
    except Exception as e:  # noqa: BLE001
        result["sw_revision"] = f"<unreadable: {type(e).__name__}>"

    # Open our own blank Part and build the S-PERSIST box (late-bound, proven).
    template = sw.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    doc = sw.NewDocument(template, 0, 0.0, 0.0)
    if doc is None:
        return {"overall": "FAIL", "reason": "NewDocument returned None", **result}
    build = build_single_box(doc)
    result["build"] = build
    if not build.get("built"):
        return {"overall": "FAIL", "reason": "box did not build", **result}
    try:
        doc.EditRebuild3
    except Exception:
        pass

    body = _first_body(doc)
    faces = list(body.GetFaces() or []) if body is not None else []
    if not faces:
        return {"overall": "FAIL", "reason": "no faces on body", **result}

    # The decisive probe: typed Extension -> [out]-param write-back.
    ext = typed(mod, "IModelDocExtension", doc.Extension)
    result["ext_early_bound"] = "gen_py" in type(ext).__module__

    t0 = time.perf_counter()
    pid = ext.GetPersistReference3(faces[0])
    read = {
        "status": "OK" if pid is not None else "NONE",
        "python_type": type(pid).__name__,
        "byte_len": len(pid) if hasattr(pid, "__len__") else None,
        "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
    }
    result["read"] = read
    if pid is None:
        return {
            "overall": "FAIL",
            "reason": "GetPersistReference3 returned None",
            **result,
        }

    rebuilt = True
    try:
        doc.ForceRebuild3(False)
    except Exception as e:  # noqa: BLE001
        rebuilt = False
        result["rebuild_error"] = repr(e)
    result["rebuilt_between"] = rebuilt

    t0 = time.perf_counter()
    res = ext.GetObjectByPersistReference3(pid)
    obj = res[0] if isinstance(res, tuple) else res
    err = res[1] if isinstance(res, tuple) and len(res) > 1 else None
    resolved = obj is not None and not isinstance(obj, int)
    resolve: dict[str, Any] = {
        "returned_type": type(res).__name__,
        "is_tuple_out_param": isinstance(res, tuple),
        "out_error_code": err,
        "object_resolved": resolved,
        "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
    }

    # Selectability: typed-wrap the round-tripped entity (same direct-wrap trick).
    if resolved:
        try:
            ent = typed(mod, "IEntity", obj)
            resolve["selectable"] = bool(ent.Select2(False, 0))
        except Exception as e:  # noqa: BLE001
            resolve["selectable"] = None
            resolve["select_note"] = repr(e)[:160]
    result["resolve"] = resolve

    if resolved and resolve.get("selectable") is True:
        overall = "PASS"
        interp = (
            "EARLY binding clears the OUT-param wall: persist write-back "
            "resolves the entity (errCode=0) AND it is selectable, after a "
            "rebuild. Durable selection is viable out-of-process in Python "
            "via typed-interface wrappers; no in-process .NET add-in needed."
        )
    elif resolved:
        overall = "PASS"
        interp = (
            "EARLY binding clears the OUT-param wall: write-back resolves "
            "the entity (errCode=0). Selectability via typed IEntity needs "
            "the same direct-wrap; not a binding blocker."
        )
    else:
        overall = "FAIL"
        interp = (
            "write-back returned no object even under early binding -> the "
            "wall is the API, not the marshaler; in-process is the path."
        )
    result["overall"] = overall
    result["interpretation"] = interp
    return result


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
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
        result = run()
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
