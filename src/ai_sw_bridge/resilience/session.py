"""SupervisedSession — crash-recovery envelope over the batch transaction.

Implements ``docs/supervised_session_spec.md``. The envelope wraps the existing
fail-soft batch runner (``mutate._sw_batch_feature_add_impl``, injected — this
module never imports ``mutate``, preserving the layer boundary) and adds:

  detect (liveness oracle) → respawn (~8-9s) → idempotent replay (Tier 1 pristine /
  Tier 2 snapshot-restore) → poison-proposal / retry caps.

All collaborators are injected so the state machine is unit-tested offline with
fakes (no seat, no real sleep). See ``docs/supervised_session_test_spec.md``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid
from typing import Any, Callable, Protocol

# --- caps / budgets (overridable via the constructor for testing) ---
MAX_RESPAWN_REPLAYS = 2  # 1 original + 2 replays = 3 attempts
RESPAWN_BUDGET_S = 30.0  # per-respawn deadline (measured ~8-9s; ~3.5x headroom)
RECOVERY_BUDGET_S = 120.0  # whole-recovery wall-clock backstop


class SeatRespawnTimeout(RuntimeError):
    """The seat did not answer ``RevisionNumber`` within the respawn budget."""


# ---------------------------------------------------------------------------
# Injected collaborator protocols (duck-typed; fakes satisfy these in tests)
# ---------------------------------------------------------------------------


class Clock(Protocol):
    def now(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


class SeatController(Protocol):
    @property
    def pid(self) -> int | None: ...
    def is_alive(self) -> bool: ...
    def respawn(self) -> None: ...  # raises SeatRespawnTimeout on failure


class Journal(Protocol):
    def insert_pending(self, doc_path: str, proposals: list) -> int: ...
    def commit(self, row_id: int) -> None: ...


class Snapshotter(Protocol):
    def snapshot(self, doc_path: str) -> Any: ...  # returns an opaque token
    def restore(self, token: Any) -> None: ...
    def discard(self, token: Any) -> None: ...


# ---------------------------------------------------------------------------
# Thin production collaborators (the live ones; offline tests inject fakes)
# ---------------------------------------------------------------------------


class SystemClock:
    """Real wall clock."""

    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class FileSnapshotter:
    """Tier-2 pristine backup: copy the .sldprt before the (corruptible) save.

    Token is ``(doc_path, backup_path)``; ``restore`` copies the backup back over
    the live file. A pure file op — no COM — so it is fully unit-testable.
    """

    def __init__(self, scratch_dir: str | None = None) -> None:
        self._scratch = scratch_dir or os.environ.get("TEMP", ".")

    def snapshot(self, doc_path: str) -> tuple[str, str]:
        backup = os.path.join(self._scratch, f"supervised_{uuid.uuid4().hex}.pristine")
        shutil.copy2(doc_path, backup)
        return (doc_path, backup)

    def restore(self, token: tuple[str, str]) -> None:
        doc_path, backup = token
        shutil.copy2(backup, doc_path)

    def discard(self, token: tuple[str, str]) -> None:
        _doc_path, backup = token
        try:
            os.remove(backup)
        except OSError:
            pass


class InMemoryJournal:
    """Default journal — the PENDING|COMMITTED commit marker, in process memory.

    The durable cross-PROCESS variant binds to ``checkpoint.CheckpointStore``
    (status flag), per the locked spec; this in-memory default covers the
    within-process recovery the envelope needs and keeps the skeleton seat-free.
    """

    def __init__(self) -> None:
        self._rows: dict[int, str] = {}
        self._next = 1

    def insert_pending(self, doc_path: str, proposals: list) -> int:
        row_id = self._next
        self._next += 1
        self._rows[row_id] = "PENDING"
        return row_id

    def commit(self, row_id: int) -> None:
        self._rows[row_id] = "COMMITTED"

    def status(self, row_id: int) -> str | None:
        return self._rows.get(row_id)


# ---------------------------------------------------------------------------
# The envelope
# ---------------------------------------------------------------------------

BatchRunner = Callable[..., dict]


class SupervisedSession:
    """Detect → respawn → idempotent-replay envelope over a batch transaction."""

    def __init__(
        self,
        *,
        batch_runner: BatchRunner,
        seat: SeatController,
        journal: Journal | None = None,
        snapshotter: Snapshotter | None = None,
        clock: Clock | None = None,
        max_replays: int = MAX_RESPAWN_REPLAYS,
        recovery_budget_s: float = RECOVERY_BUDGET_S,
    ) -> None:
        self._run = batch_runner
        self._seat = seat
        self._journal = journal or InMemoryJournal()
        self._snap = snapshotter or FileSnapshotter()
        self._clock = clock or SystemClock()
        self._max_replays = max_replays
        self._recovery_budget_s = recovery_budget_s

    # -- public API --------------------------------------------------------

    def execute(
        self, doc_path: str, proposals: list[dict], *, strict: bool = False
    ) -> dict[str, Any]:
        """Run the batch under supervision; return the (recovery-annotated) manifest.

        Fail-soft: never raises. A seat death is caught transparently and replayed;
        a genuine geometric fault is propagated unchanged; an unrecoverable case
        (cap / poison / respawn-timeout) returns a fatal manifest naming the cause.
        """
        recovery: dict[str, Any] = {
            "deaths": [],
            "replays": 0,
            "tier": None,
            "recovered": None,
            "poison_proposal": None,
            "fatal_reason": None,
        }
        token = self._snap.snapshot(doc_path)
        row_id = self._journal.insert_pending(doc_path, proposals)
        deaths_by_index: dict[Any, int] = {}
        deadline = self._clock.now() + self._recovery_budget_s
        attempt = 0

        try:
            while True:
                attempt += 1
                manifest, death = self._attempt(doc_path, proposals, strict, attempt)

                if death is None:
                    # clean success OR a genuine (seat-alive) fault — terminal.
                    self._journal.commit(row_id)
                    recovery["recovered"] = True
                    return self._annotate(manifest, recovery)

                # --- a seat death was detected ---
                recovery["deaths"].append(death)
                idx = death.get("proposal_index")
                deaths_by_index[idx] = deaths_by_index.get(idx, 0) + 1

                # poison: the SAME proposal reproducibly kills the kernel.
                if idx is not None and deaths_by_index[idx] >= 2:
                    recovery["poison_proposal"] = idx
                    recovery["fatal_reason"] = (
                        f"poison proposal {idx}: reproducible seat death "
                        f"({death.get('fault')}) on 2 attempts"
                    )
                    recovery["recovered"] = False
                    return self._fatal(manifest, recovery, doc_path)

                # global replay cap.
                if recovery["replays"] >= self._max_replays:
                    recovery["fatal_reason"] = (
                        f"exceeded max respawn-replays ({self._max_replays})"
                    )
                    recovery["recovered"] = False
                    return self._fatal(manifest, recovery, doc_path)

                # wall-clock backstop.
                if self._clock.now() >= deadline:
                    recovery["fatal_reason"] = (
                        f"recovery wall-clock budget ({self._recovery_budget_s}s) "
                        "exceeded"
                    )
                    recovery["recovered"] = False
                    return self._fatal(manifest, recovery, doc_path)

                # respawn the seat (~8-9s live; instant with a fake).
                try:
                    self._seat.respawn()
                except SeatRespawnTimeout as exc:
                    recovery["fatal_reason"] = f"seat respawn failed: {exc}"
                    recovery["recovered"] = False
                    return self._fatal(manifest, recovery, doc_path)

                # Tier select: a save-stage death may have corrupted the file ->
                # restore the pristine snapshot. Tier 1 (open/apply) left disk
                # untouched -> replay onto it directly.
                tier = 2 if death.get("phase") == "save" else 1
                recovery["tier"] = tier
                if tier == 2:
                    self._snap.restore(token)
                recovery["replays"] += 1
                # loop -> replay the FULL declarative proposal list.
        finally:
            self._snap.discard(token)

    # -- internals ---------------------------------------------------------

    def _attempt(
        self, doc_path: str, proposals: list, strict: bool, attempt: int
    ) -> tuple[dict, dict | None]:
        """Run one batch attempt; return (manifest, death|None).

        The batch runner is fail-soft (never raises) — a death surfaces as a
        ``fault{stage}`` manifest. We still guard against an escaped exception.
        """
        try:
            manifest = self._run(doc_path, proposals, strict=strict)
        except BaseException as exc:  # noqa: BLE001 — escaped death/edge
            if self._seat.is_alive():
                # genuine unexpected error, seat healthy -> wrap, do NOT respawn.
                return (
                    {
                        "ok": False,
                        "doc_path": doc_path,
                        "error": f"unexpected (seat alive): {exc!r}",
                        "committed": [],
                    },
                    None,
                )
            return (
                {
                    "ok": False,
                    "doc_path": doc_path,
                    "error": repr(exc),
                    "committed": [],
                },
                {
                    "attempt": attempt,
                    "phase": "raised",
                    "proposal_index": None,
                    "fault": _signature(exc),
                },
            )

        if manifest.get("ok") is True:
            return manifest, None  # clean success
        fault = manifest.get("fault")
        if not fault:
            return manifest, None  # validation/other terminal non-death
        # there is a fault: death only if the seat is actually dead.
        if self._seat.is_alive():
            return manifest, None  # genuine geometric fault -> propagate
        return manifest, {
            "attempt": attempt,
            "phase": fault.get("stage", "apply"),
            "proposal_index": fault.get("index"),
            "fault": f"seat_dead@{fault.get('stage')}",
        }

    @staticmethod
    def _annotate(manifest: dict, recovery: dict) -> dict:
        manifest = dict(manifest)
        manifest["recovery"] = recovery
        return manifest

    def _fatal(self, manifest: dict | None, recovery: dict, doc_path: str) -> dict:
        base = dict(manifest) if manifest else {"ok": False, "doc_path": doc_path}
        base["ok"] = False
        if not base.get("error"):
            base["error"] = recovery.get("fatal_reason")
        base["recovery"] = recovery
        return base


def _signature(exc: BaseException) -> str:
    """Stable fault signature: HRESULT hex for com_error, else type name."""
    try:
        import pywintypes  # noqa: WPS433

        if isinstance(exc, pywintypes.com_error):
            hr = int(exc.args[0])
            return f"com_error {hex(hr & 0xFFFFFFFF)}"
    except Exception:  # noqa: BLE001
        pass
    return type(exc).__name__


# ---------------------------------------------------------------------------
# Live seat controller (production; exercised by the destructive_sw lane, not
# offline). The liveness oracle + respawn sequence from spec §2.2 / §3.
# ---------------------------------------------------------------------------


def _find_sw_pid() -> int | None:
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq SLDWORKS.exe", "/NH", "/FO", "CSV"],
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout
    except Exception:  # noqa: BLE001
        return None
    for line in out.splitlines():
        if "SLDWORKS.EXE" in line.upper():
            parts = [p.strip('" ') for p in line.split(",")]
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1])
    return None


def _pid_alive(pid: int) -> bool:
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout
    except Exception:  # noqa: BLE001
        return True  # fail-open: let the COM ping be the arbiter
    return str(pid) in out


def _rev(sw: Any) -> Any:
    v = sw.RevisionNumber
    return v() if callable(v) else v


class ExecutorSeatController:
    """Live SeatController: PID + COM-ping liveness oracle and the respawn loop.

    Binding-mode trap (measured, spike_seat_death_recovery): a dead seat faults
    early-bound calls with ``com_error 0x800706BA`` and dynamic calls with
    ``AttributeError`` — ``is_alive`` catches BOTH via the ``_rev`` ping. Not
    exercised offline (no seat); the destructive_sw lane proves it.
    """

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()
        self._pid = _find_sw_pid()

    @property
    def pid(self) -> int | None:
        return self._pid

    def is_alive(self) -> bool:
        from ..sw_com import get_sw_app

        if self._pid is None or not _pid_alive(self._pid):
            return False
        try:
            _rev(get_sw_app())
            return True
        except Exception:  # noqa: BLE001 — 0x800706BA or dead-dispatch AttributeError
            return False

    def respawn(self) -> None:
        import pythoncom

        from ..sw_com import get_sw_app, release_sw_app

        dead_pid = self._pid
        release_sw_app()
        try:
            pythoncom.CoUninitialize()
            pythoncom.CoInitialize()
        except Exception:  # noqa: BLE001
            pass
        deadline = self._clock.now() + RESPAWN_BUDGET_S
        while self._clock.now() < deadline:
            try:
                sw = get_sw_app()
                _rev(sw)  # the authoritative "accepts commands" gate
                new_pid = _find_sw_pid()
                if new_pid is not None and new_pid != dead_pid:
                    self._pid = new_pid
                    return
                self._pid = new_pid
                return
            except Exception:  # noqa: BLE001
                self._clock.sleep(2.0)
        raise SeatRespawnTimeout(f"no RevisionNumber within {RESPAWN_BUDGET_S}s")
