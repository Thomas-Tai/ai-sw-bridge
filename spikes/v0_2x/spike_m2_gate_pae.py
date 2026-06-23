"""Batch M2 orchestrator gate — assembly transaction round-trip via SolidWorksClient.

Proves the v0.18 class boundary carries the assembly family (propose/dry_run/commit
+ edit) without severing the disk-keyed proposal_id link, and that commit_assembly's
extra args (out, part_paths) flow through the facade. The round-trip is driven through
the cli/assembly.py runners, which after the M2 port route cli -> SolidWorksClient()
.mutate -> _impl. Built on the shipped-GREEN assembly_p1 recipe (two boxes + one
coincident mate) so the lifecycle itself is known-good and only the boundary is on trial.

  A propose_clean      : cli_asm._run_propose(spec=<file>) returns ok=True with a
                         12-hex proposal_id and emits NO PendingDeprecationWarning
                         internally (cli->client->_impl is warning-clean).
  B dryrun_disklink    : cli_asm._run_dry_run(<that pid>) returns ok=True — the
                         client's dry_run LOADED the proposal the client's propose
                         SAVED (disk link survives the class boundary). No leak.
  C commit_out_partpaths: cli_asm._run_commit(proposal_id, out=<.sldasm>,
                         part_paths='{}') returns ok=True, the .sldasm exists on disk,
                         and the manifest round-trips (2 components, 1 mate) — proving
                         out AND part_paths threaded through the facade kwargs. No leak.
  D shim_still_warns   : the legacy free function sw_propose_assembly STILL emits
                         PendingDeprecationWarning AND still reaches the engine
                         (ok=True) — back-compat preserved across the shim.

Scope note: assembly has NO legacy facade class (unlike ProposalStore for local/
feature), so there is no "facade quiet" witness — cli/assembly.py called the bare
verbs directly and now calls the client. Mates/B-rep correctness ride on the shipped
assembly_p1 tests; M2's seat witness is the boundary + the produced file + disk link.

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_m2_gate_pae.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import warnings
from argparse import Namespace
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[2] / "src"
_V19 = _HERE.parents[1] / "v0_19"
_V15 = _HERE.parents[1] / "v0_15"
for _p in (str(_SRC), str(_V19), str(_V15), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Hermetic store BEFORE any mutate call (mutate reads AI_SW_BRIDGE_PROPOSALS lazily).
_PROPOSALS = _HERE.parent / "_results" / "m2_proposals"
if _PROPOSALS.exists():
    shutil.rmtree(_PROPOSALS, ignore_errors=True)
_PROPOSALS.mkdir(parents=True, exist_ok=True)
os.environ["AI_SW_BRIDGE_PROPOSALS"] = str(_PROPOSALS)

import pythoncom  # noqa: E402
import win32com.client as w32  # noqa: E402

from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.cli import assembly as cli_asm  # noqa: E402
from ai_sw_bridge.mutate import sw_propose_assembly  # noqa: E402

from assembly_p1_pae import _build_box_and_save, _capture_planar_face  # noqa: E402

_OUT = _HERE.parent / "_results" / "m2_gate_pae.json"
_WORK = _HERE.parent / "_results" / "m2_work"
results: dict[str, Any] = {"pae": "m2_assembly_transaction_gate", "gates": {}}


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
    mod = wrapper_module()
    sw = w32.Dispatch("SldWorks.Application")
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    if _WORK.exists():
        shutil.rmtree(_WORK, ignore_errors=True)
    _WORK.mkdir(parents=True, exist_ok=True)
    base_path = str(_WORK / "m2_base.SLDPRT")
    lid_path = str(_WORK / "m2_lid.SLDPRT")
    asm_path = str(_WORK / "m2_asm.SLDASM")
    spec_path = _WORK / "m2_spec.json"
    try:
        # ── Fixture: two saved boxes + a coincident mate (shipped-GREEN recipe) ──
        if not _build_box_and_save(sw, base_path, mod).get("saved"):
            gate("propose_clean", False, "base build/save failed")
            raise SystemExit(_finish())
        if not _build_box_and_save(sw, lid_path, mod).get("saved"):
            gate("propose_clean", False, "lid build/save failed")
            raise SystemExit(_finish())
        base_face = _capture_planar_face(sw, base_path, (0.0, 0.0, 1.0), mod)
        lid_face = _capture_planar_face(sw, lid_path, (0.0, 0.0, -1.0), mod)
        if not (base_face.get("ok") and lid_face.get("ok")):
            gate("propose_clean", False,
                 f"face capture failed base={base_face.get('error')} lid={lid_face.get('error')}")
            raise SystemExit(_finish())

        spec = {
            "kind": "assembly",
            "name": "m2_gate_asm",
            "components": [
                {"id": "base", "part": base_path, "transform": {"xyz_mm": [0, 0, 0]}},
                {"id": "lid", "part": lid_path, "transform": {"xyz_mm": [0, 0, 50]}},
            ],
            "mates": [
                {"type": "coincident", "alignment": "anti_aligned",
                 "a": {"component": "base", "face_ref": base_face["face_ref"]},
                 "b": {"component": "lid", "face_ref": lid_face["face_ref"]}},
            ],
        }
        spec_path.write_text(json.dumps(spec), encoding="utf-8")

        # ── A: propose via the CLI runner (cli -> client -> _impl, no leak) ──
        prop, cleanA, whyA = _under_warnings_as_errors(
            lambda: cli_asm._run_propose(Namespace(spec=str(spec_path))))
        results["propose_report"] = prop
        pid = prop.get("proposal_id")
        gate("propose_clean",
             cleanA and bool(prop.get("ok")) and isinstance(pid, str) and len(pid) == 12,
             whyA or f"ok={prop.get('ok')} pid={pid} (cli->client->_impl, no warning)")
        if not pid:
            raise SystemExit(_finish())

        # ── B: dry_run via the CLI runner — disk link crossed the boundary ──
        dry, cleanB, whyB = _under_warnings_as_errors(
            lambda: cli_asm._run_dry_run(Namespace(proposal_id=pid)))
        results["dry_run_report"] = dry
        gate("dryrun_disklink",
             cleanB and bool(dry.get("ok")),
             whyB or f"ok={dry.get('ok')} (client dry_run loaded client propose's pid "
             f"across the boundary)")

        # ── C: commit via the CLI runner — out + part_paths flow through the facade ──
        com, cleanC, whyC = _under_warnings_as_errors(
            lambda: cli_asm._run_commit(
                Namespace(proposal_id=pid, out=asm_path, part_paths="{}")))
        results["commit_report"] = com
        saved = os.path.isfile(asm_path)
        # Authoritative witness: the commit report's own counters (manifest nests
        # components/mates under manifest["spec"]).
        built_ok = com.get("component_count") == 2 and com.get("mate_count") == 1
        gate("commit_out_partpaths",
             cleanC and bool(com.get("ok")) and saved and built_ok,
             whyC or f"ok={com.get('ok')} sldasm_saved={saved} "
             f"components={com.get('component_count')} mates={com.get('mate_count')} "
             f"(out + part_paths threaded through the facade)")

        # ── D: legacy shim STILL warns AND still reaches the engine ──
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            legacy = sw_propose_assembly(spec)
        warned = any(issubclass(w.category, PendingDeprecationWarning) for w in caught)
        gate("shim_still_warns",
             warned and bool(legacy.get("ok")),
             f"legacy warned={warned}, still_functions(ok={legacy.get('ok')})")
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
