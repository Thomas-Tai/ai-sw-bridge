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

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

import ai_sw_bridge.mutate as mutate
from ai_sw_bridge.checkpoint import TransactionStore
from ai_sw_bridge.checkpoint.rollback import _read_current_tree_hash
from ai_sw_bridge.mutate import (
    HANDLER_REGISTRY,
    _doc_title,
    _open_doc_typed,
    _sw_batch_feature_add_impl,
)
from ai_sw_bridge.resilience import TransactionStoreJournal
from ai_sw_bridge.resilience.session import (
    ExecutorSeatController,
    FileSnapshotter,
    SupervisedSession,
    _find_sw_pids,
)
from ai_sw_bridge.sw_com import get_sw_app, release_sw_app

pytestmark = pytest.mark.destructive_sw


# ---------------------------------------------------------------------------
# SAFETY HARNESS (2026-06-25 incident: an unguarded kill murdered the operator's
# live seat — the bridge attaches to the running SLDWORKS via the ROT). Every
# kill is now (a) SINGLETON-GUARDED — refuses if >1 SLDWORKS.exe exists, so a
# developer instance can never be the target — and (b) BIND-CHECKED against the
# captured seat PID. See memory reference_destructive_seat_kill_safety.
# ---------------------------------------------------------------------------


def _assert_single_seat() -> int:
    """Exactly one SLDWORKS.exe must exist; return its PID. Refuses on 0 or >1."""
    pids = _find_sw_pids()
    assert len(pids) == 1, (
        f"destructive guard: expected exactly 1 SLDWORKS.exe, found {len(pids)} "
        f"({pids}); refusing to run a process-killing test while another seat is "
        "open — it could be a developer instance. Close all but the bound seat."
    )
    return pids[0]


def _kill_seat(expected_pid: int) -> None:
    """Kill ONLY the bound seat: assert the sole live PID == *expected_pid*
    (singleton-guarded) immediately before pulling the trigger."""
    pid = _assert_single_seat()
    assert pid == expected_pid, (
        f"kill guard: live pid {pid} != bound {expected_pid}; refusing to kill an "
        "unbound/developer instance"
    )
    subprocess.run(
        ["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=20
    )


def _kill_sole_seat() -> int:
    """Kill whatever the SINGLE live seat currently is (singleton-guarded), for
    multi-kill assassins whose bound PID rotates across respawns. Still refuses
    if a second (developer) instance is present."""
    pid = _assert_single_seat()
    subprocess.run(
        ["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=20
    )
    return pid


@pytest.fixture(autouse=True)
def _fresh_seat_cache():
    """Drop any stale cached SW app so a killed-seat handle from a prior test
    can't leak in (the batched-run COM-state contamination)."""
    release_sw_app()
    yield
    release_sw_app()


@pytest.fixture(scope="module", autouse=True)
def _reap_respawn_orphans():
    """Leave no headless corpses: kill any SLDWORKS that APPEARED during this
    module's run (the envelope's respawns — windowless, they don't always
    self-close), while NEVER touching a PID that pre-existed the run. The
    baseline-diff is the safety boundary — a developer's interactive seat was
    open before the tests and stays in the baseline, so it is never reaped.
    """
    baseline = set(_find_sw_pids())
    yield
    for pid in set(_find_sw_pids()) - baseline:
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=20
        )


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
        _kill_seat(_BOUND_PID["pid"])  # singleton-guarded + bind-checked
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
        _BOUND_PID["pid"] = _assert_single_seat()
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


def test_customer_batch_api_survives_seat_death():
    """Case 7b (Wave 2, RES-1): the SAME mid-apply assassination, but routed
    through the CUSTOMER API ``client.mutate.batch()`` (supervised by default) —
    not a hand-built SupervisedSession. Proves the production path a buyer
    actually calls recovers to geometry identical to the golden run."""
    from ai_sw_bridge.client import SolidWorksClient

    assert _FIXTURE.is_file(), f"fixture missing: {_FIXTURE}"
    tmp = Path(tempfile.mkdtemp(prefix="supervised_api_pae_"))
    golden_path = str(tmp / "golden.SLDPRT")
    assassin_path = str(tmp / "assassin.SLDPRT")
    shutil.copy2(_FIXTURE, golden_path)
    shutil.copy2(_FIXTURE, assassin_path)

    _KILLED["done"] = False
    HANDLER_REGISTRY["__assassin__"] = _assassin
    try:
        golden_manifest = _sw_batch_feature_add_impl(
            golden_path, _proposals(), strict=False
        )
        assert golden_manifest["ok"] is True, golden_manifest
        golden = _witness(golden_path)

        _BOUND_PID["pid"] = _assert_single_seat()
        # THE CUSTOMER PATH — supervised=True is the default; no hand-built session.
        out = SolidWorksClient().mutate.batch(assassin_path, _proposals(assassin_at=1))
    finally:
        HANDLER_REGISTRY.pop("__assassin__", None)

    rec = out["recovery"]
    assert out["ok"] is True, out  # the agent/customer sees SUCCESS
    assert rec["recovered"] is True
    assert rec["replays"] == 1
    assert rec["tier"] == 1  # mid-apply death -> pristine disk -> Tier 1
    assert len(rec["deaths"]) == 1

    recovered = _witness(assassin_path)
    assert recovered["node_count"] == golden["node_count"]
    assert recovered["tree_hash"] == golden["tree_hash"]
    if recovered["volume"] is not None and golden["volume"] is not None:
        assert recovered["volume"] == pytest.approx(golden["volume"], rel=1e-6)

    shutil.rmtree(tmp, ignore_errors=True)


# ===========================================================================
# Cases 8-10 — the edge-case gauntlet
# ===========================================================================


def _golden(path: str) -> dict:
    """Clean 3-plane batch + witness — the non-interrupted baseline."""
    m = _sw_batch_feature_add_impl(path, _proposals(), strict=False)
    assert m["ok"] is True, m
    return _witness(path)


def _two_copies(prefix: str) -> tuple[Path, str, str]:
    tmp = Path(tempfile.mkdtemp(prefix=prefix))
    g, a = str(tmp / "golden.SLDPRT"), str(tmp / "run.SLDPRT")
    shutil.copy2(_FIXTURE, g)
    shutil.copy2(_FIXTURE, a)
    return tmp, g, a


def test_case8_open_death_recovers_tier1(monkeypatch):
    """Seat dies during _open_doc_typed (before the apply loop) -> Tier-1 recover."""
    assert _FIXTURE.is_file()
    tmp, gpath, rpath = _two_copies("supervised_open_")
    golden = _golden(gpath)

    bound = _assert_single_seat()
    fired = {"done": False}
    real_open = mutate._open_doc_typed

    def _killing_open(doc_path):
        if not fired["done"]:
            fired["done"] = True
            _kill_seat(bound)  # the real open below now faults on the dead seat
        return real_open(doc_path)

    monkeypatch.setattr(mutate, "_open_doc_typed", _killing_open)
    session = SupervisedSession(
        batch_runner=_sw_batch_feature_add_impl, seat=ExecutorSeatController()
    )
    out = session.execute(rpath, _proposals())

    rec = out["recovery"]
    assert out["ok"] is True, out
    assert rec["recovered"] is True and rec["replays"] == 1
    assert rec["tier"] == 1  # open-stage death -> pristine disk
    assert rec["deaths"][0]["phase"] in ("open_doc", "raised")
    recovered = _witness(rpath)
    assert recovered["node_count"] == golden["node_count"]
    assert recovered["tree_hash"] == golden["tree_hash"]
    shutil.rmtree(tmp, ignore_errors=True)


def test_case9_save_death_restores_snapshot_tier2(monkeypatch):
    """Seat dies during the atomic _save_doc (after PENDING) -> Tier-2 snapshot
    restore -> replay. Proves the checkpoint-boundary recovery path."""
    assert _FIXTURE.is_file()
    tmp, gpath, rpath = _two_copies("supervised_save_")
    golden = _golden(gpath)

    bound = _assert_single_seat()
    fired = {"done": False}
    real_save = mutate._save_doc

    def _killing_save(doc):
        if not fired["done"]:
            fired["done"] = True
            _kill_seat(bound)  # save now faults -> fault{stage:"save"}
        return real_save(doc)

    monkeypatch.setattr(mutate, "_save_doc", _killing_save)

    class _SpySnap(FileSnapshotter):
        restores = 0

        def restore(self, token):
            _SpySnap.restores += 1
            return super().restore(token)

    _SpySnap.restores = 0
    # DURABLE journal: the SQLite ledger lives in its own file, untouched by the
    # SLDWORKS taskkill — proving the PENDING marker survives the seat death and
    # flips to COMMITTED only when the supervised recovery completes.
    store = TransactionStore(root=Path(tmp))
    session = SupervisedSession(
        batch_runner=_sw_batch_feature_add_impl,
        seat=ExecutorSeatController(),
        snapshotter=_SpySnap(),
        journal=TransactionStoreJournal(store),
    )
    out = session.execute(rpath, _proposals())

    rec = out["recovery"]
    assert out["ok"] is True, out
    assert rec["recovered"] is True and rec["replays"] == 1
    assert rec["tier"] == 2  # save-stage death
    assert _SpySnap.restores == 1  # the pristine snapshot was restored before replay
    recovered = _witness(rpath)
    assert recovered["node_count"] == golden["node_count"]
    assert recovered["tree_hash"] == golden["tree_hash"]

    # the durable ledger survived the kill and recorded exactly one COMMITTED txn.
    assert store.db_path.is_file()
    assert store.get_pending_transactions() == []  # nothing left dangling
    reopened = TransactionStore(root=Path(tmp))  # fresh handle = a 'next process'
    rows = (
        reopened._connect()
        .execute(  # noqa: SLF001 — test introspection
            "SELECT status, intent_payload FROM transactions"
        )
        .fetchall()
    )
    assert len(rows) == 1
    assert rows[0][0] == "committed"
    assert json.loads(rows[0][1]) == _proposals()
    shutil.rmtree(tmp, ignore_errors=True)


def test_case10_live_poison_cap_does_not_wedge():
    """An assassin that kills on EVERY attempt -> poison-proposal quarantine ->
    fatal ok=False, bounded (no infinite respawn loop)."""
    assert _FIXTURE.is_file()
    tmp, _gpath, rpath = _two_copies("supervised_poison_")

    def _assassin_always(doc, feature, target):
        # Kills the CURRENT sole seat every time (its PID rotates after each
        # respawn); singleton-guarded so a developer instance is never hit.
        _kill_sole_seat()
        return False, "assassin (always) fired"

    HANDLER_REGISTRY["__assassin__"] = _assassin_always
    try:
        session = SupervisedSession(
            batch_runner=_sw_batch_feature_add_impl, seat=ExecutorSeatController()
        )
        out = session.execute(rpath, _proposals(assassin_at=1))
    finally:
        HANDLER_REGISTRY.pop("__assassin__", None)

    rec = out["recovery"]
    assert out["ok"] is False, out  # the agent gets an actionable terminal error
    assert rec["recovered"] is False, out
    # same index dies twice -> poison quarantine (bounded), not the global cap
    assert rec["poison_proposal"] == 1
    assert "reproducible seat death" in rec["fatal_reason"]
    shutil.rmtree(tmp, ignore_errors=True)
