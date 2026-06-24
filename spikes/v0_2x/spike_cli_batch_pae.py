"""ai-sw-batch CLI — end-to-end seat PAE (the plan→approve→EXECUTE loop closed).

Drives the REAL CLI as a SUBPROCESS with 'y' piped to stdin — exercising the
human approval ceremony exactly as an operator would — and proves the irreversible
commit lands on the live seat:

  A approve_commits : `python -m ai_sw_bridge.cli.batch <part> <props.json>` with
                      stdin='y' → manifest on stdout shows ok=True, committed=3,
                      doc_saved=True, exit 0.
  B disk_updated    : the .sldprt mtime ADVANCES (the commit persisted) AND a
                      reopen shows the feature count grew by >=3 (features really
                      materialized on disk) — the INVERSE of the dry-run PAE.
  C decline_noops   : a second run with stdin='n' → aborted, exit 0, and the disk
                      is unchanged (the human gate truly blocks the write).

Run: PYTHONPATH=<repo>/src python spikes/v0_2x/spike_cli_batch_pae.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_REPO = _HERE.parents[2]
_SRC = _REPO / "src"
for _p in (str(_SRC), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import pythoncom  # noqa: E402
import win32com.client as w32  # noqa: E402
from win32com.client import VARIANT  # noqa: E402

from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.features import verify  # noqa: E402
import _feature_spike_fixtures as fx  # noqa: E402

_RESULTS = _HERE.parent / "_results"
_OUT = _RESULTS / "cli_batch_pae.json"
results: dict[str, Any] = {"pae": "cli_batch", "gates": {}}


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _finish() -> int:
    all_pass = bool(results["gates"]) and all(
        g["ok"] for g in results["gates"].values()
    )
    results["verdict"] = "GREEN" if all_pass else "PARTIAL"
    _RESULTS.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nVerdict: {results['verdict']}  (wrote {_OUT})")
    return 0 if all_pass else 1


def _close_all(sw: Any) -> None:
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass


def _build_block_to_disk(sw: Any, path: Path) -> None:
    _close_all(sw)
    doc = fx.build_block(sw)
    if path.exists():
        try:
            path.unlink()
        except Exception:
            pass
    doc.SaveAs3(str(path), 0, 0)
    _close_all(sw)


def _reopen_node_count(sw: Any, path: Path) -> int:
    errs = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warns = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    doc = sw.OpenDoc6(str(path), 1, 1, "", errs, warns)
    n = verify.feature_node_count(doc)
    _close_all(sw)
    return n


def _run_cli(part: Path, props: Path, answer: str) -> tuple[int, dict | None, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_SRC)
    proc = subprocess.run(
        [sys.executable, "-m", "ai_sw_bridge.cli.batch", str(part), str(props)],
        input=answer + "\n",
        capture_output=True,
        text=True,
        env=env,
        cwd=str(_REPO),
        timeout=240,
    )
    manifest = None
    out = proc.stdout.strip()
    if out:
        try:
            manifest = json.loads(out[out.index("{") :])
        except Exception:
            manifest = None
    return proc.returncode, manifest, proc.stderr


def main() -> int:
    pythoncom.CoInitialize()
    _ = wrapper_module()
    _RESULTS.mkdir(parents=True, exist_ok=True)
    sw = w32.Dispatch("SldWorks.Application")

    part = _RESULTS / "cli_batch_pae.sldprt"
    props = _RESULTS / "cli_batch_pae_proposals.json"
    props.write_text(
        json.dumps(
            [
                {
                    "feature": {"type": "ref_plane", "distance_mm": 25.0},
                    "target": {"plane": "Front Plane"},
                },
                {"feature": {"type": "scale", "scale_factor": 1.5}, "target": {}},
                {"feature": {"type": "com_point"}, "target": {}},
            ]
        ),
        encoding="utf-8",
    )

    try:
        # --- C first (decline) on a fresh block: the gate must block the write ---
        _build_block_to_disk(sw, part)
        nodes0 = _reopen_node_count(sw, part)
        mtime0 = part.stat().st_mtime_ns
        rc_n, man_n, _err_n = _run_cli(part, props, "n")
        nodes_n = _reopen_node_count(sw, part)
        mtime_n = part.stat().st_mtime_ns
        gate(
            "decline_noops",
            rc_n == 0
            and bool(man_n)
            and man_n.get("aborted") is True
            and mtime_n == mtime0
            and nodes_n == nodes0,
            f"rc={rc_n} aborted={man_n.get('aborted') if man_n else None} "
            f"mtime_unchanged={mtime_n == mtime0} nodes {nodes0}->{nodes_n}",
        )

        # --- A + B (approve) on a fresh block: the commit must PERSIST ---
        _build_block_to_disk(sw, part)
        nodes_before = _reopen_node_count(sw, part)
        mtime_before = part.stat().st_mtime_ns
        rc_y, man_y, err_y = _run_cli(part, props, "y")
        results["commit_manifest"] = man_y
        gate(
            "approve_commits",
            rc_y == 0
            and bool(man_y)
            and man_y.get("ok") is True
            and man_y.get("committed_count") == 3
            and man_y.get("doc_saved") is True,
            f"rc={rc_y} ok={man_y.get('ok') if man_y else None} "
            f"committed={man_y.get('committed_count') if man_y else None} "
            f"kinds={[c.get('kind') for c in (man_y or {}).get('committed', [])]}",
        )

        nodes_after = _reopen_node_count(sw, part)
        mtime_after = part.stat().st_mtime_ns
        gate(
            "disk_updated",
            mtime_after > mtime_before and nodes_after >= nodes_before + 3,
            f"mtime_advanced={mtime_after > mtime_before} "
            f"nodes {nodes_before}->{nodes_after} (expect +3 materialized)",
        )
    finally:
        _close_all(sw)
        pythoncom.CoUninitialize()
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
