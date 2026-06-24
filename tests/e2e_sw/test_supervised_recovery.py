"""Live destructive PAE — SupervisedSession catches a real SLDWORKS death.

Case 7 of docs/supervised_session_test_spec.md: an ``__assassin__`` handler at
proposal index 1 shells ``taskkill /F /PID <bound_pid>`` mid-apply-loop; the
envelope must transparently respawn, replay the FULL list onto the pristine file,
and reconstruct geometry BIT-FOR-GEOMETRY identical to a non-interrupted golden run.

Isolation: ``destructive_sw`` marker (SEH-isolation; auto-skipped unless
``-m destructive_sw``). Kills by PID only — never ``/IM`` — against the captured
bound seat, asserting it is the bound instance before pulling the trigger. Operates
on temp copies; never touches tracked files.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from ai_sw_bridge.checkpoint.rollback import _read_current_tree_hash
from ai_sw_bridge.mutate import (
    HANDLER_REGISTRY,
    _doc_title,
    _open_doc_typed,
    _sw_batch_feature_add_impl,
)
from ai_sw_bridge.resilience.session import (
    ExecutorSeatController,
    SupervisedSession,
    _find_sw_pid,
)
from ai_sw_bridge.sw_com import get_sw_app

pytestmark = pytest.mark.destructive_sw

_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "captures"
    / "refactor_smoke"
    / "mmp_master_default.SLDPRT"
)

# --- assassin state (module-level so the registered handler can reach it) ---
_KILLED = {"done": False}
_BOUND_PID = {"pid": None}


def _assassin(doc, feature, target):
    """Fire ONCE: kill the bound seat. On replay: behave as the ref_plane it
    replaced (so the recovered geometry equals the golden run)."""
    if not _KILLED["done"]:
        _KILLED["done"] = True
        pid = _find_sw_pid()
        assert pid is not None, "assassin: no bound SW pid — refusing to kill"
        assert pid == _BOUND_PID["pid"], (
            f"assassin: live pid {pid} != bound {_BOUND_PID['pid']} — "
            "refusing to kill an unbound/developer instance"
        )
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=20
        )
        return False, "assassin fired — seat assassinated"
    # replay: delegate to the real plane handler with the same distance.
    real = HANDLER_REGISTRY["ref_plane"]
    return real(
        doc, {"type": "ref_plane", "distance_mm": feature["distance_mm"]}, target
    )


def _proposals(assassin_at=None):
    out = []
    for i, dist in enumerate((10.0, 20.0, 30.0)):
        ftype = "__assassin__" if i == assassin_at else "ref_plane"
        out.append(
            {
                "feature": {"type": ftype, "distance_mm": dist},
                "target": {"plane": "Front Plane"},
            }
        )
    return out


def _witness(doc_path: str) -> dict:
    """Open the part, read the geometric witnesses, close. Tree-hash + node-count
    carry geometric identity (volume is constant for ref planes — sanity only)."""
    sw = get_sw_app()
    doc = _open_doc_typed(doc_path)  # proven typed-open (raw OpenDoc6 byref-faults)
    try:
        node_count = int(doc.GetFeatureCount())
        tree_hash = _read_current_tree_hash(doc)
        try:
            mp = doc.Extension.CreateMassProperty()
            volume = float(mp.Volume)
        except Exception:  # noqa: BLE001
            volume = None
        return {"node_count": node_count, "tree_hash": tree_hash, "volume": volume}
    finally:
        try:
            sw.CloseDoc(_doc_title(doc))
        except Exception:  # noqa: BLE001
            pass


def test_supervised_session_catches_real_seat_death():
    assert _FIXTURE.is_file(), f"fixture missing: {_FIXTURE}"
    tmp = Path(tempfile.mkdtemp(prefix="supervised_pae_"))
    golden_path = str(tmp / "golden.SLDPRT")
    assassin_path = str(tmp / "assassin.SLDPRT")
    shutil.copy2(_FIXTURE, golden_path)
    shutil.copy2(_FIXTURE, assassin_path)

    _KILLED["done"] = False
    HANDLER_REGISTRY["__assassin__"] = _assassin
    try:
        # --- GOLDEN RUN: clean 3-plane batch, no assassin ---
        golden_manifest = _sw_batch_feature_add_impl(
            golden_path, _proposals(), strict=False
        )
        assert golden_manifest["ok"] is True, golden_manifest
        golden = _witness(golden_path)
        assert golden["tree_hash"] is not None

        # --- ASSASSIN RUN: same batch, index 1 assassinates the seat mid-flight ---
        _BOUND_PID["pid"] = _find_sw_pid()
        session = SupervisedSession(
            batch_runner=_sw_batch_feature_add_impl,
            seat=ExecutorSeatController(),
        )
        out = session.execute(assassin_path, _proposals(assassin_at=1))
    finally:
        HANDLER_REGISTRY.pop("__assassin__", None)

    # --- the assertion contract (spec §3.2) ---
    rec = out["recovery"]
    assert out["ok"] is True, out  # the agent sees SUCCESS — the death was caught
    assert rec["recovered"] is True
    assert rec["replays"] == 1
    assert rec["tier"] == 1  # mid-apply death -> pristine disk -> Tier 1
    assert len(rec["deaths"]) == 1
    assert "0x800706ba" in str(rec["deaths"][0]["fault"]).lower() or rec["deaths"][0][
        "phase"
    ] in ("apply", "raised")

    # geometric equivalence to the golden run
    recovered = _witness(assassin_path)
    assert recovered["node_count"] == golden["node_count"]
    assert recovered["tree_hash"] == golden["tree_hash"]
    if recovered["volume"] is not None and golden["volume"] is not None:
        assert recovered["volume"] == pytest.approx(golden["volume"], rel=1e-6)

    shutil.rmtree(tmp, ignore_errors=True)
