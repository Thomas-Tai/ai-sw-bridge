"""Batch O2 orchestrator gate — active-doc verbs via SolidWorksClient on the seat.

Verifies the worker-ported O2 batch on the live seat, focusing on the two the
directive named (feature_statistics + equations):

  A feature_stats_clean : ai-sw-observe `feature_statistics` runner
                          (SolidWorksClient().observe.feature_statistics) returns
                          ok=True with a real feature_count on a built part, and
                          emits NO PendingDeprecationWarning internally.
  B equations_clean     : ai-sw-observe `equations` runner (…observe.equations)
                          returns ok=True with NO internal PendingDeprecationWarning.
  C baseline_identity   : the legacy free function sw_get_feature_statistics STILL
                          warns AND its payload is byte-identical to the class-routed
                          result (proves the v0.17 data baseline is preserved).

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_o2_gate_pae.py
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
sys.path.insert(0, str(_HERE.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import pythoncom  # noqa: E402
import win32com.client as w32  # noqa: E402

from ai_sw_bridge.cli import observe as cli_observe  # noqa: E402
from ai_sw_bridge.observe import sw_get_feature_statistics  # noqa: E402

import spike_advanced_mates_probe as P  # noqa: E402

_OUT = _HERE.parent / "_results" / "o2_gate_pae.json"
results: dict[str, Any] = {"pae": "o2_active_doc_verbs_gate", "gates": {}}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _under_warnings_as_errors(fn) -> tuple[dict[str, Any], bool, str]:
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        try:
            return fn(), True, ""
        except PendingDeprecationWarning as exc:  # noqa: BLE001
            return {"ok": False}, False, f"internal PendingDeprecationWarning leaked: {exc}"


def _finish() -> int:
    all_pass = bool(results["gates"]) and all(g["ok"] for g in results["gates"].values())
    results["verdict"] = "GREEN" if all_pass else "PARTIAL"
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nVerdict: {results['verdict']}  (wrote {_OUT})")
    return 0 if all_pass else 1


def main() -> int:
    pythoncom.CoInitialize()
    sw = w32.Dispatch("SldWorks.Application")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    try:
        cube = P._build("o2_cube", P._cube("o2_cube", 20.0))
        if "error" in cube:
            gate("fixture", False, cube["error"])
            raise SystemExit(_finish())
        gate("fixture", True, f"cube={cube.get('path')}")

        # ── A: feature_statistics via the client ──────────────────────────
        rep, clean, why = _under_warnings_as_errors(
            lambda: cli_observe._run_feature_statistics(argparse.Namespace()))
        results["feature_stats_report"] = rep
        fcount = rep.get("feature_count")
        gate("feature_stats_clean",
             clean and bool(rep.get("ok")) and isinstance(fcount, int) and fcount > 0,
             why or f"ok={rep.get('ok')} feature_count={fcount} (class-routed, no warning)")

        # ── B: equations via the client ───────────────────────────────────
        rep2, clean2, why2 = _under_warnings_as_errors(
            lambda: cli_observe._run_equations(argparse.Namespace()))
        results["equations_report"] = rep2
        gate("equations_clean", clean2 and bool(rep2.get("ok")),
             why2 or f"ok={rep2.get('ok')} count={len(rep2.get('equations', []))} "
             f"(class-routed, no warning)")

        # ── C: legacy shim STILL warns AND payload identical to baseline ──
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            legacy = sw_get_feature_statistics()
        warned = any(issubclass(w.category, PendingDeprecationWarning) for w in caught)
        identical = legacy == rep
        gate("baseline_identity",
             warned and identical,
             f"legacy warned={warned}, payload_identical_to_class_route={identical}")
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
