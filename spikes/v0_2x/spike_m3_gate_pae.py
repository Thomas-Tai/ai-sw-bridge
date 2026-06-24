"""Batch M3 orchestrator gate — drawing + properties round-trips via SolidWorksClient.

The FINAL mutate batch. Proves the v0.18 class boundary carries the last two
transaction families (drawing, properties) without severing the disk-keyed
proposal_id link, driven through their CLI runners (cli/drawing.py, cli/properties.py)
which after the M3 port route cli -> SolidWorksClient().mutate -> _impl.

  DRAWING (model -> views -> .slddrw):
  A drw_propose_clean  : cli_drw._run_propose(spec=<file>) -> ok, 12-hex pid, no leak.
  B drw_dryrun_disklink: cli_drw._run_dry_run(<pid>) -> ok (client dry_run loaded
                         client propose's pid across the boundary), no leak.
  C drw_commit_file    : cli_drw._run_commit(pid, out=<.slddrw>) -> ok, .slddrw on
                         disk, view_count > 0 (out threaded through the facade), no leak.

  PROPERTIES (model -> set custom prop -> verified read-back):
  D prop_propose_clean : cli_props._run_propose(spec=<file>) -> ok, pid, no leak.
  E prop_commit_verified: dry_run then cli_props._run_commit(pid) -> ok, and props_set
                         carries M3_Tag with immediate_read_back.match True (the custom
                         property landed AND verified on the doc). No leak.

  F shims_still_warn   : legacy sw_propose_drawing AND sw_propose_properties STILL emit
                         PendingDeprecationWarning and still reach the engine.

Scope note: drawing/properties have NO legacy facade class (their CLIs called bare
verbs), so no "facade quiet" witness. View placement / property semantics ride on the
shipped W16/W29 tests; M3's seat witness is the boundary + produced .slddrw + verified
property + disk link. On GREEN the ENTIRE mutate sw_* family is sealed behind .mutate.

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_m3_gate_pae.py
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
for _p in (str(_SRC), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Hermetic store BEFORE any mutate call.
_PROPOSALS = _HERE.parent / "_results" / "m3_proposals"
if _PROPOSALS.exists():
    shutil.rmtree(_PROPOSALS, ignore_errors=True)
_PROPOSALS.mkdir(parents=True, exist_ok=True)
os.environ["AI_SW_BRIDGE_PROPOSALS"] = str(_PROPOSALS)

import pythoncom  # noqa: E402
import win32com.client as w32  # noqa: E402

from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.cli import drawing as cli_drw  # noqa: E402
from ai_sw_bridge.cli import properties as cli_props  # noqa: E402
from ai_sw_bridge.mutate import sw_propose_drawing, sw_propose_properties  # noqa: E402

import spike_advanced_mates_probe as P  # noqa: E402

_OUT = _HERE.parent / "_results" / "m3_gate_pae.json"
_WORK = _HERE.parent / "_results" / "m3_work"
results: dict[str, Any] = {"pae": "m3_drawing_properties_gate", "gates": {}}


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
            return (
                {"ok": False},
                False,
                f"internal PendingDeprecationWarning leaked: {exc}",
            )


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
    if _WORK.exists():
        shutil.rmtree(_WORK, ignore_errors=True)
    _WORK.mkdir(parents=True, exist_ok=True)
    try:
        # ── Fixtures: two saved cube parts (drawing model + properties model) ──
        drw_model = P._build("m3_drw_model", P._cube("m3_drw_model", 30.0))
        prop_model = P._build("m3_prop_model", P._cube("m3_prop_model", 20.0))
        for m in (drw_model, prop_model):
            if "error" in m:
                gate("drw_propose_clean", False, m["error"])
                raise SystemExit(_finish())
        sw.CloseAllDocuments(True)

        drw_path = str(_WORK / "m3_drawing.SLDDRW")
        drw_spec_path = _WORK / "m3_drw_spec.json"
        drw_spec_path.write_text(
            json.dumps(
                {
                    "kind": "drawing",
                    "name": "m3_gate_drw",
                    "model": drw_model["path"],
                    "views": ["front", "top", "isometric"],
                    "sheet": {"template_size": "A3"},
                }
            ),
            encoding="utf-8",
        )
        prop_spec_path = _WORK / "m3_prop_spec.json"
        prop_spec_path.write_text(
            json.dumps(
                {
                    "kind": "properties",
                    "model": prop_model["path"],
                    "properties": {"M3_Tag": "GREEN"},
                }
            ),
            encoding="utf-8",
        )

        # ── A: drawing propose via the CLI runner (cli->client->_impl, no leak) ──
        dp, cleanA, whyA = _under_warnings_as_errors(
            lambda: cli_drw._run_propose(Namespace(spec=str(drw_spec_path)))
        )
        results["drw_propose_report"] = dp
        dpid = dp.get("proposal_id")
        gate(
            "drw_propose_clean",
            cleanA and bool(dp.get("ok")) and isinstance(dpid, str) and len(dpid) == 12,
            whyA or f"ok={dp.get('ok')} pid={dpid} (cli->client->_impl, no warning)",
        )
        if not dpid:
            raise SystemExit(_finish())

        # ── B: drawing dry_run via the CLI runner — disk link crossed the boundary ──
        dd, cleanB, whyB = _under_warnings_as_errors(
            lambda: cli_drw._run_dry_run(Namespace(proposal_id=dpid))
        )
        results["drw_dry_run_report"] = dd
        gate(
            "drw_dryrun_disklink",
            cleanB and bool(dd.get("ok")),
            whyB or f"ok={dd.get('ok')} (client dry_run loaded client propose's pid)",
        )

        # ── C: drawing commit via the CLI runner — out threaded through facade ──
        dc, cleanC, whyC = _under_warnings_as_errors(
            lambda: cli_drw._run_commit(Namespace(proposal_id=dpid, out=drw_path))
        )
        results["drw_commit_report"] = dc
        drw_saved = os.path.isfile(drw_path)
        vc = dc.get("view_count") or dc.get("views_placed") or 0
        gate(
            "drw_commit_file",
            cleanC
            and bool(dc.get("ok"))
            and drw_saved
            and isinstance(vc, int)
            and vc > 0,
            whyC
            or f"ok={dc.get('ok')} slddrw_saved={drw_saved} view_count={vc} "
            f"(out threaded through the facade)",
        )

        # ── D: properties propose via the CLI runner ──
        pp, cleanD, whyD = _under_warnings_as_errors(
            lambda: cli_props._run_propose(Namespace(spec=str(prop_spec_path)))
        )
        results["prop_propose_report"] = pp
        ppid = pp.get("proposal_id")
        gate(
            "prop_propose_clean",
            cleanD and bool(pp.get("ok")) and isinstance(ppid, str) and len(ppid) == 12,
            whyD or f"ok={pp.get('ok')} pid={ppid} (cli->client->_impl, no warning)",
        )
        if not ppid:
            raise SystemExit(_finish())

        # ── E: properties dry_run + commit — custom prop landed + verified read-back ──
        pd, cleanE1, whyE1 = _under_warnings_as_errors(
            lambda: cli_props._run_dry_run(Namespace(proposal_id=ppid))
        )
        results["prop_dry_run_report"] = pd
        pc, cleanE2, whyE2 = _under_warnings_as_errors(
            lambda: cli_props._run_commit(Namespace(proposal_id=ppid))
        )
        results["prop_commit_report"] = pc
        props_set = pc.get("props_set") or []
        verified = any(
            p.get("name") == "M3_Tag"
            and (p.get("immediate_read_back") or {}).get("match") is True
            for p in props_set
        )
        gate(
            "prop_commit_verified",
            cleanE1
            and cleanE2
            and bool(pd.get("ok"))
            and bool(pc.get("ok"))
            and verified,
            (whyE1 or whyE2)
            or f"dry_run_ok={pd.get('ok')} commit_ok={pc.get('ok')} "
            f"M3_Tag_verified_readback={verified} (custom property landed on the doc)",
        )

        # ── F: legacy shims STILL warn AND still reach the engine ──
        drw_spec = json.loads(drw_spec_path.read_text(encoding="utf-8"))
        prop_spec = json.loads(prop_spec_path.read_text(encoding="utf-8"))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            l_drw = sw_propose_drawing(drw_spec)
            l_prop = sw_propose_properties(prop_spec)
        warned = (
            sum(1 for w in caught if issubclass(w.category, PendingDeprecationWarning))
            >= 2
        )
        gate(
            "shims_still_warn",
            warned and bool(l_drw.get("ok")) and bool(l_prop.get("ok")),
            f"both warned>={warned}, drawing_ok={l_drw.get('ok')} "
            f"properties_ok={l_prop.get('ok')}",
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
