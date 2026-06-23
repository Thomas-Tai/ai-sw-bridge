"""Recipe-B gate — .export + .features facades on SolidWorksClient.

Completes the v0.18 commercial boundary: the two facade-only domains (no sw_*
free functions, no shims) wired onto the client.

  A export_file_drop      : client.export.run(doc, [ExportRequest(format="stl",
                            output_dir=...)], "m_recipeb") returns an ExportResult
                            with ok=True and the .stl actually on disk — proving the
                            export orchestrator (export_all) is reachable through the
                            client and the file drops correctly.
  B features_introspection : client.features.list_kinds() returns a non-empty sorted
                            list of registered (seat-proven GREEN) feature kinds that
                            matches HANDLER_REGISTRY; supports() is correct membership
                            (a known kind True, a nonsense kind False). The WRITE path
                            stays on .mutate.propose_feature_add (not duplicated here).
  C facades_cached         : client.export is client.export and client.features is
                            client.features (cached-property identity), matching the
                            .observe/.mutate/.urdf taxonomy.

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_recipeb_gate_pae.py
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[2] / "src"
for _p in (str(_SRC), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import pythoncom  # noqa: E402
import win32com.client as w32  # noqa: E402

from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.client import SolidWorksClient  # noqa: E402
from ai_sw_bridge.export import ExportRequest  # noqa: E402
from ai_sw_bridge.features import HANDLER_REGISTRY  # noqa: E402
from ai_sw_bridge.sw_com import get_active_doc, get_sw_app  # noqa: E402

import spike_advanced_mates_probe as P  # noqa: E402

_OUT = _HERE.parent / "_results" / "recipeb_gate_pae.json"
_WORK = _HERE.parent / "_results" / "recipeb_work"
results: dict[str, Any] = {"pae": "recipeb_export_features_gate", "gates": {}}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _finish() -> int:
    all_pass = bool(results["gates"]) and all(g["ok"] for g in results["gates"].values())
    results["verdict"] = "GREEN" if all_pass else "PARTIAL"
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nVerdict: {results['verdict']}  (wrote {_OUT})")
    return 0 if all_pass else 1


def main() -> int:
    pythoncom.CoInitialize()
    _ = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    if _WORK.exists():
        shutil.rmtree(_WORK, ignore_errors=True)
    _WORK.mkdir(parents=True, exist_ok=True)
    try:
        client = SolidWorksClient()

        # ── A: export a built cube through client.export.run -> file on disk ──
        cube = P._build("recipeb_cube", P._cube("recipeb_cube", 25.0))
        if "error" in cube:
            gate("export_file_drop", False, cube["error"])
            raise SystemExit(_finish())
        doc = get_active_doc(get_sw_app())
        req = ExportRequest(format="stl", output_dir=_WORK)
        export_results = client.export.run(doc, [req], "m_recipeb")
        r0 = export_results[0] if export_results else None
        path = getattr(r0, "path", None)
        ok = bool(getattr(r0, "ok", False))
        on_disk = bool(path) and Path(path).is_file()
        results["export_result"] = {
            "format": getattr(r0, "format", None), "ok": ok, "path": path,
            "error": getattr(r0, "error", None)}
        gate("export_file_drop",
             ok and on_disk,
             f"ok={ok} stl_on_disk={on_disk} path={path} "
             f"(export_all reached through client.export.run)")

        # ── B: features registry introspection ──
        kinds = client.features.list_kinds()
        expected = sorted(HANDLER_REGISTRY)
        known = "composite"  # shipped GREEN (W62) — must be advertised
        bogus = "__not_a_real_feature_kind__"
        results["features"] = {"count": len(kinds), "has_composite": known in kinds}
        gate("features_introspection",
             isinstance(kinds, list) and kinds == expected and len(kinds) > 0
             and client.features.supports(known) is True
             and client.features.supports(bogus) is False,
             f"list_kinds()=={len(kinds)} kinds, matches_registry={kinds == expected}, "
             f"supports('{known}')={client.features.supports(known)}, "
             f"supports(bogus)={client.features.supports(bogus)}")

        # ── C: facades are cached (taxonomy parity with .observe/.mutate/.urdf) ──
        gate("facades_cached",
             client.export is client.export and client.features is client.features,
             "client.export and client.features each return a cached singleton")
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
