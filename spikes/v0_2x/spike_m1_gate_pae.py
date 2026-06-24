"""Batch M1 orchestrator gate — mutate transaction round-trip via SolidWorksClient.

Proves the v0.18 class-API boundary does NOT sever the disk-keyed proposal_id
transaction link, and that the Option-1 refactor (CLI now consumes the NEW
SolidWorksMutatorFacade, legacy ProposalStore repointed to the _impl cores) holds.
The whole Local-change triad (+undo) is driven through the CLI runners
(cli/mutate.py _run_*), which after the port route cli -> SolidWorksClient().mutate
-> _impl, end-to-end on the live seat:

  A propose_clean       : cli_mutate._run_propose(var=BOX_W, new_value=30) returns
                          ok=True with a 12-hex proposal_id, old_expression "20", and
                          emits NO PendingDeprecationWarning internally (proves the
                          cli->client->_impl chain is warning-clean).
  B dryrun_disklink     : cli_mutate._run_dry_run(<that pid>) returns ok=True — i.e.
                          the client's dry_run LOADED the proposal the client's
                          propose SAVED (the disk link survives the class boundary).
                          The live rebuild sees var 20 -> 30 in dry.after, then rolls
                          back. No internal warning leak.
  C commit_geometry     : cli_mutate._run_commit(<pid>) returns ok=True and the linked
                          locals file on disk now carries the new expression (30) —
                          the change propagated through a real rebuild. No leak.
  D undo_restores       : cli_mutate._run_undo_last_commit() returns ok=True and the
                          locals file is restored to its pre-commit expression (20).
  E shim_still_warns    : the legacy free function sw_propose_local_change STILL emits
                          PendingDeprecationWarning AND still reaches the engine
                          (ok=True, fresh pid) — back-compat preserved across the shim.
                          (Byte-identity is N/A: propose mints a fresh uuid + timestamp
                          per call, so the witness is "warns AND functions".)
  F proposalstore_quiet : the legacy v0.14 facade ProposalStore().propose(...) runs
                          ok=True under warnings-as-errors with NO leak — proving its
                          7 method bodies were repointed shims -> _impl (Option 1).

Scope note: the fixture binds NO dimension to BOX_W on purpose. M1 proves the FACADE
TRANSACTION BOUNDARY (disk link intact, no warning leak, CLI on the new client,
legacy facade quiet) — it does NOT re-prove the mutate engine's geometry effect,
which shipped tests already cover. The var_value 20->30 transition through the live
rebuild + the committed-file delta are the propagation witness. The feature_add triad
is ported in M1 but its correctness rides on its shipped tests + new offline facade
tests; the seat witness is the local-change round-trip the directive named.

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_m1_gate_pae.py
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
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
sys.path.insert(0, str(_HERE.parent))

# Hermetic store: isolate this gate's proposals dir so stale/foreign-family
# records in the shared ./proposals cruft can't poison the round-trip. Set
# BEFORE importing/calling mutate (which reads AI_SW_BRIDGE_PROPOSALS lazily
# at call time via _proposals_dir()).
_PROPOSALS = _HERE.parent / "_results" / "m1_proposals"
if _PROPOSALS.exists():
    shutil.rmtree(_PROPOSALS, ignore_errors=True)
_PROPOSALS.mkdir(parents=True, exist_ok=True)
os.environ["AI_SW_BRIDGE_PROPOSALS"] = str(_PROPOSALS)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import pythoncom  # noqa: E402
import win32com.client as w32  # noqa: E402

from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.cli import mutate as cli_mutate  # noqa: E402
from ai_sw_bridge.mutate import ProposalStore, sw_propose_local_change  # noqa: E402
from ai_sw_bridge.spec.builder import link_locals  # noqa: E402
from ai_sw_bridge.sw_com import get_active_doc, get_sw_app  # noqa: E402

import spike_advanced_mates_probe as P  # noqa: E402

_OUT = _HERE.parent / "_results" / "m1_gate_pae.json"
_LOCALS = _HERE.parent / "_results" / "m1_locals.txt"
results: dict[str, Any] = {"pae": "m1_mutate_local_triad_gate", "gates": {}}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _under_warnings_as_errors(fn) -> tuple[dict[str, Any], bool, str]:
    """Run *fn*; PendingDeprecationWarning becomes an exception (leak detector)."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", PendingDeprecationWarning)
        try:
            return fn(), True, ""
        except PendingDeprecationWarning as exc:  # noqa: BLE001
            return (
                {"ok": False},
                False,
                f"internal PendingDeprecationWarning leaked: {exc}",
            )


def _locals_has(token: str) -> bool:
    try:
        return token in _LOCALS.read_text(encoding="utf-8")
    except Exception:
        return False


def _finish() -> int:
    all_pass = bool(results["gates"]) and all(
        g["ok"] for g in results["gates"].values()
    )
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
    try:
        # ── Fixture: a saved 20mm cube part with a linked single-var locals file ──
        cube = P._build("m1_box", P._cube("m1_box", 20.0))
        if "error" in cube:
            gate("propose_clean", False, cube["error"])
            raise SystemExit(_finish())
        doc = get_active_doc(get_sw_app())
        _OUT.parent.mkdir(parents=True, exist_ok=True)
        _LOCALS.write_text('"BOX_W" = 20\n', encoding="utf-8")
        link_locals(doc, str(_LOCALS))  # 4-call LinkToFile sequence (builder.py)

        # ── A: propose via the CLI runner (cli -> client -> _impl, no leak) ──
        prop, cleanA, whyA = _under_warnings_as_errors(
            lambda: cli_mutate._run_propose(Namespace(var="BOX_W", new_value="30"))
        )
        results["propose_report"] = prop
        pid = prop.get("proposal_id")
        gate(
            "propose_clean",
            cleanA
            and bool(prop.get("ok"))
            and isinstance(pid, str)
            and len(pid) == 12
            and str(prop.get("old_expression")).strip() == "20",
            whyA
            or f"ok={prop.get('ok')} pid={pid} old={prop.get('old_expression')!r} "
            f"(cli->client->_impl, no warning)",
        )
        if not pid:
            raise SystemExit(_finish())

        # ── B: dry_run via the CLI runner — proves the disk link crossed the boundary ─
        dry, cleanB, whyB = _under_warnings_as_errors(
            lambda: cli_mutate._run_dry_run(Namespace(proposal_id=pid))
        )
        results["dry_run_report"] = dry
        before = (dry.get("before") or {}).get("var_value")
        after = (dry.get("after") or {}).get("var_value")

        def _near(v, target):
            return isinstance(v, (int, float)) and abs(float(v) - target) < 1e-6

        gate(
            "dryrun_disklink",
            cleanB
            and bool(dry.get("ok"))
            and bool(dry.get("rebuild_ok"))
            and bool(dry.get("rolled_back"))
            and _near(before, 20.0)
            and _near(after, 30.0),
            whyB
            or f"ok={dry.get('ok')} rebuild_ok={dry.get('rebuild_ok')} "
            f"rolled_back={dry.get('rolled_back')} var {before}->{after} "
            f"(client dry_run loaded client propose's pid across the boundary)",
        )

        # ── C: commit via the CLI runner — the locals file on disk gains "30" ──
        com, cleanC, whyC = _under_warnings_as_errors(
            lambda: cli_mutate._run_commit(Namespace(proposal_id=pid))
        )
        results["commit_report"] = com
        gate(
            "commit_geometry",
            cleanC and bool(com.get("ok")) and _locals_has("30"),
            whyC
            or f"ok={com.get('ok')} locals_file_has_30={_locals_has('30')} "
            f"(committed change propagated to disk through a live rebuild)",
        )

        # ── D: undo via the CLI runner — the locals file is restored to "20" ──
        undo, cleanD, whyD = _under_warnings_as_errors(
            lambda: cli_mutate._run_undo_last_commit(Namespace())
        )
        results["undo_report"] = undo
        gate(
            "undo_restores",
            cleanD
            and bool(undo.get("ok"))
            and _locals_has("20")
            and not _locals_has("30"),
            whyD
            or f"ok={undo.get('ok')} locals_restored_to_20="
            f"{_locals_has('20') and not _locals_has('30')}",
        )

        # ── E: legacy free-fn shim STILL warns AND still reaches the engine ──
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            legacy = sw_propose_local_change("BOX_W", "30")
        warned = any(issubclass(w.category, PendingDeprecationWarning) for w in caught)
        gate(
            "shim_still_warns",
            warned and bool(legacy.get("ok")) and bool(legacy.get("proposal_id")),
            f"legacy warned={warned}, still_functions(ok={legacy.get('ok')}, "
            f"fresh pid={legacy.get('proposal_id')})",
        )

        # ── F: legacy v0.14 ProposalStore facade quiet (repointed to _impl) ──
        ps, cleanF, whyF = _under_warnings_as_errors(
            lambda: ProposalStore().propose(var="BOX_W", new_value="30")
        )
        results["proposalstore_report"] = ps
        gate(
            "proposalstore_quiet",
            cleanF and bool(ps.get("ok")) and bool(ps.get("proposal_id")),
            whyF
            or f"ProposalStore().propose ok={ps.get('ok')} "
            f"pid={ps.get('proposal_id')} (no warning leak — bodies on _impl)",
        )
    finally:
        try:
            sw.CloseAllDocuments(True)
        except Exception:
            pass
        pythoncom.CoUninitialize()
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
