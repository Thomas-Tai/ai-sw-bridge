# SupervisedSession — crash-recovery envelope (design + test spec)

> **Status:** Implemented in `src/ai_sw_bridge/resilience/session.py` (shipped). This
> document is the design rationale and test specification behind it.
> **Grounded in:** the seat-death recovery experiment
> (`spikes/spike_seat_death_recovery.py`) + the `mutate.py` transaction model +
> `checkpoint/` + the `sw_com` cache.
> **Scope:** the single-seat, mid-hold crash — the dominant commercial path.
> Dual-instance orphaned-PID and mid-`OpenDoc6` deaths are explicitly out of scope.

## 0. Premise (measured, not assumed)

From the seat-death recovery experiment (`_results/seat_death_recovery.json`, untracked local receipt):

| Fact | Value | Source |
|---|---|---|
| Early-bound (`typed`) post-death fault | `com_error` HRESULT **`0x800706BA`** RPC_S_SERVER_UNAVAILABLE | experiment Phase 3 |
| Dynamic (`Dispatch`) post-death fault | **`AttributeError`** (`GetIDsOfNames` on dead server) | experiment Phase 3 |
| Fault latency | **immediate, 0.0s** — never hangs (property reads AND method calls) | experiment Phase 3 |
| Re-bind | **~8–9s**, first `Dispatch`, **new PID**, running-object table self-clears | experiment Phase 4 (×3) |
| Batch persistence | **single terminal `_save_doc`** — disk untouched until the end | `mutate.py:2038–2081` |

The terminal-save model means the on-disk file is a **naturally pristine rollback
state for the entire mid-apply window** (Tier 1); only a crash *during* the atomic
save can corrupt it (Tier 2). The wrapper is a reverse-proxy: catch the upstream
death, hold the declarative payload, respawn a fresh worker, replay the intent —
the LLM agent never learns the primary node failed.

## 1. Architecture & placement

New package `src/ai_sw_bridge/resilience/session.py` exposing:

```python
class SupervisedSession:
    def run_batch(
        self, doc_path: str, proposals: list[dict], *, strict: bool = False
    ) -> dict:  # returns the batch manifest, extended with a `recovery` block
        ...
```

- **Layer:** above `mutate` (it *calls* `_sw_batch_feature_add_impl`), below
  `cli`/`mcp`. import-linter contract: insert `ai_sw_bridge.resilience` directly
  above `ai_sw_bridge.mutate` in the layers list.
- **Thread affinity:** all COM — including the respawn — runs on the **ComExecutor
  STA thread**. The MCP surface invokes `SupervisedSession.run_batch` via the
  existing `run_on_executor` primitive; the CLI invokes it on its own STA. The
  respawn MUST happen on the same apartment that holds the dead dispatch.
- **Composition, not rewrite:** the supervised loop drives the *existing*
  `_sw_batch_feature_add_impl` unchanged. Recovery is an outer envelope; the batch
  engine stays a pure, fail-soft transaction. This keeps the atomic-save guarantee
  (the whole idempotency argument) intact.

---

## 2. Fault detection boundary

### 2.1 Where the `try/except` sits

**Around the whole batch transaction, never inside `_apply_feature`.** A seat can
die at *any* COM call — `_open_doc_typed`, a handler mid-`_apply_feature`,
`_save_doc`, or the `finally` `CloseDoc`. The recovery action (tear down the entire
doc context + respawn) is **whole-transaction-granular**, so detection must be too.
Per-handler `try/except` would fragment the manifest and could not orchestrate a
respawn (which invalidates every open dispatch at once).

The batch engine is already **fail-soft — it never raises** (handler errors are
caught at `mutate.py:2043` and recorded as `fault{stage:"apply"}`). So the envelope
observes exactly two terminal outcomes:

- **(a) Batch RETURNS a manifest** — success, or a recorded `fault`.
- **(b) Batch RAISES** — a COM call at the open/save/close stage faulted
  (`com_error 0x800706BA` or dead-dispatch `AttributeError`) and escaped the
  engine's internal handling.

### 2.2 Benign vs fatal `AttributeError` — the liveness oracle

This is the crux. A benign `AttributeError` ("extrude a non-existent face") means
the **seat is alive**; a fatal one means **dynamic dispatch died**. They are
indistinguishable *at the exception object*. We disambiguate with a **post-hoc
liveness probe**, applied to BOTH a raised exception AND a returned `fault` manifest
(because a death mid-handler is caught by the engine and mislabeled `stage:"apply"`):

```
def _seat_is_dead(sw, pid) -> bool:
    if pid is None or not _pid_alive(pid):     # gate 1: cheap — is the PROCESS gone?
        return True
    try:
        _ = _rev(sw)        # gate 2: authoritative — does a known-good COM call fault?
        return False        # seat answered -> ALIVE -> original error was genuine
    except Exception:
        return True          # 0x800706BA or dead-dispatch AttributeError -> DEAD
```

The probe is a **reliable oracle** because we measured that *every* COM call faults
immediately post-death — a live seat cannot produce a false "dead", and a dead seat
cannot produce a false "alive".

**Decision table** (applied to every non-clean batch outcome):

| Batch outcome | `_seat_is_dead`? | Action |
|---|---|---|
| clean success | — | return manifest (happy path) |
| `fault{stage:"apply"}` | **alive** | genuine geometric fault → **propagate to agent unchanged** |
| `fault{stage:"apply"}` | **dead** | death mislabeled as apply-fault → **respawn + replay** |
| raised `com_error`/`AttributeError` | **alive** | unexpected app error → propagate (do NOT respawn) |
| raised `com_error`/`AttributeError` | **dead** | seat death → **respawn + replay** |

Net: the agent only ever sees a death as a transparent retry; a real geometric
fault is never masked by a spurious respawn, and a benign `AttributeError` never
triggers one.

---

## 3. Respawn orchestration

Executed on the STA executor thread, after `_seat_is_dead` returns True:

```
1. dead_pid := the PID captured at session entry (find_sw_pid()).
2. TEARDOWN (best-effort, swallow all):
     - drop every held dispatch ref (del sw, doc, ext, …)
     - release_sw_app()            # clears _CACHED_SW_APP — the load-bearing step
     - pythoncom.CoUninitialize(); pythoncom.CoInitialize()   # apartment reset (belt)
3. RESPAWN LOOP (deadline = RESPAWN_BUDGET_S = 30s ≈ 3.5× measured 8–9s):
     repeat:
       try:
         sw := get_sw_app()        # re-Dispatch + repopulate _CACHED_SW_APP
         rev := _rev(sw)           # READINESS GATE — the authoritative liveness signal
         new_pid := find_sw_pid()
         assert new_pid != dead_pid   # corroboration: a genuinely fresh process
         return sw                 # RECOVERED
       except Exception:
         sleep(2s); continue
     on deadline exceeded -> raise SeatRespawnTimeout
```

- **Liveness = the readiness COM ping (`_rev`) succeeds**, not PID-alive. During a
  cold start the PID can exist before COM accepts commands; `RevisionNumber`
  returning a string is the true "accepts commands" gate. `new_pid != dead_pid` is
  *corroboration* (guards against a stale ROT entry pointing at the corpse), not the
  primary signal.
- **PID acquisition:** `find_sw_pid()` parses `tasklist /FI "IMAGENAME eq
  SLDWORKS.exe" /NH /FO CSV` (proven in the experiment; robust to display formatting).
- **No manual ROT surgery** — the dead entry self-clears; `release_sw_app()` +
  fresh `Dispatch` is sufficient (measured ×3).

### 3.1 UI-blocker suppression  *(verified by `spike_seat_recovery_ui.py`)*

**Measured finding: an unsaved-work crash does NOT block the respawn on the
agent-batch timescale.** Two dirty-doc crash→respawn cycles (a real unsaved 3D-sketch
edit, `GetSaveFlag=True`, then `taskkill /F`): the respawned seat came up **clean —
readiness in 1.4–1.6s, `ActiveDoc = None` (no Document-Recovery doc auto-loaded), no
modal, the watchdog never fired**. Root cause: SW writes recovery snapshots to
`%APPDATA%\SOLIDWORKS\SOLIDWORKS 2024\swxauto` only on the auto-recover *interval*
(minutes); a seconds-long batch crash never reaches it, so **no recovery file is
written → no Document-Recovery pane appears**. `taskkill /F` is an external hard-kill,
so SW's own "encountered a problem" crash dialog never runs either (the process is
gone before it can paint UI). On this seat `swxauto` never even came into existence.

**Two-layer mitigation in the respawn sequence (defense-in-depth):**
1. **Hard backstop (mandatory): the readiness probe runs under the watchdog timer**
   (step 3 above). IF a future config *did* pop a blocking modal, the probe converts
   an infinite wedge into a clean `SeatRespawnTimeout` after `RESPAWN_BUDGET_S`, which
   routes to the retry/poison cap — the agent fails actionably, never hangs forever.
   This is the load-bearing guarantee; it holds regardless of UI behavior.
2. **Defensive suppression (cheap belt): clear `swxauto` on respawn.** Add a
   pre-Dispatch step that deletes the auto-recover directory contents
   (`shutil.rmtree(AUTORECOVER_DIR, ignore_errors=True)`) — binding-independent,
   guarantees no recovery file exists → no pane, even on a machine with an aggressive
   auto-recover interval or a long batch that crosses it. *Caveat: efficacy against a
   POPULATED `swxauto` was not directly exercised (auto-recover never fired in the
   probe's short window, so there was nothing to clear — `dir_cleared:False`); it is a
   well-founded inference (the pane reads from `swxauto`), not a witnessed result.* The
   toggle route (`swAutoRecoverInterval=0`) is a weaker secondary — the constant did
   not resolve via `win32com.client.constants` (swconst makepy not loaded that way), so
   the file-system clear is the robust mechanism.

---

## 4. Replay engine — Tier 1 & Tier 2

### 4.1 Phase tracking → Tier selection

The supervised loop stamps `PHASE ∈ {open, apply, save, close}` before each stage,
so on death it knows which Tier applies:

- death in **`open`/`apply`** → **Tier 1** (disk pristine — terminal save not reached).
- death in **`save`** → **Tier 2** (the atomic write may be partial/corrupt).

### 4.2 Tier 1 — pristine replay (the 99% path)

Disk is bit-identical to pre-batch. Recovery = **reopen `doc_path`, re-run the FULL
proposal list** via a fresh `_sw_batch_feature_add_impl(doc_path, proposals,
strict=strict)`. Idempotent: registry handlers are pure transforms over doc state,
and the starting tree is identical, so `committed[]` (incl. auto-incremented feature
names) reproduces exactly. **No feature-tree introspection of the survivor** — there
is nothing to resume *from*; there is only the pristine state to replay *onto*.

### 4.3 Tier 2 — pre-save snapshot + durable commit marker

The narrow hazard window is a crash *inside* the atomic `_save_doc`. Guarded by a
**file-copy snapshot** (NOT the live-model `checkpoint.rollback_to`/EditRollback,
which is useless on a dead seat) plus the existing `CheckpointStore` SQLite as the
**atomic commit boundary**:

```
# inside the supervised save phase, on the STA thread:
backup := shutil.copy2(doc_path, <scratch>/<batch_id>.pristine.sldprt)
row_id := CheckpointStore.insert_pending(batch_id, doc_path, manifest_intent)   # BEFORE save
PHASE = "save"
saved := _save_doc(doc)            # the only corruptible call
CheckpointStore.commit(row_id)     # AFTER save returns
```

**Recovery dichotomy (the clean idempotency boundary):**

| Durable state on recovery | Meaning | Action |
|---|---|---|
| `committed` row exists | save completed, batch durable | **no-op** — batch is done |
| `pending` row, no commit | save outcome AMBIGUOUS (may be corrupt/partial) | **restore `backup` over `doc_path`** → Tier-1 replay |
| no row | death before save phase | Tier-1 replay (disk already pristine) |

Because the manifest commit marker is ordered to **never claim more than disk
holds**, recovery is always either a no-op (durably saved) or a replay onto a
known-pristine file. **No partial-feature reconciliation ever occurs.**

### 4.4 Retry cap + poison-proposal quarantine  *(the infinite-loop guard)*

A proposal that *reliably* crashes the Parasolid kernel would otherwise loop
detect→respawn→replay→crash forever. Three backstops:

1. **Global cap `MAX_RESPAWN_REPLAYS = 2`** (1 original + 2 replays = 3 attempts).
2. **Poison-proposal detection (the smart cap):** record the in-flight proposal
   index (`PHASE=apply`, current `i`) at each death. If the **same index** causes a
   death on **2 separate attempts**, it is a reproducible kernel-crasher →
   **abort immediately**, do not exhaust the global cap. Return a fatal manifest
   that names it (echo `feature`/`target` verbatim, mirroring the existing `fault{}`
   contract) with `poison_proposal: <i>` — so the agent/human learns *which*
   geometric op to avoid, not just "it failed".
3. **Wall-clock backstop `RECOVERY_BUDGET_S = 120s`** caps pathological slow-respawn
   loops regardless of attempt count.

On give-up: return the manifest with `recovery.recovered = False`,
`recovery.fatal_reason`, the identified `poison_proposal` (if any), and the
`committed[]` from the last clean attempt. **The agent always gets an actionable
terminal error, never a hang.**

---

## 5. Manifest extension

The supervised wrapper adds a `recovery` block to the batch manifest (the batch
manifest itself is unchanged):

```jsonc
"recovery": {
  "deaths": [ { "attempt": 1, "phase": "apply", "proposal_index": 3,
                "fault": "com_error 0x800706BA", "dead_pid": 85928,
                "respawn_s": 8.6, "new_pid": 81112 } ],
  "replays": 1,
  "tier": 1,                       // or 2 if a save-window restore happened
  "recovered": true,
  "poison_proposal": null,         // or the index of a reproducible crasher
  "fatal_reason": null
}
```

---

## 6. State machine (one transaction)

```
        ┌─────────┐  open ok   ┌─────────┐  all ok   ┌─────────┐  saved   ┌──────┐
  START │  OPEN   ├───────────▶│  APPLY  ├──────────▶│  SAVE   ├─────────▶│ DONE │
        └────┬────┘            └────┬────┘           └────┬────┘          └──────┘
             │ death/raise          │ death OR          │ death
             ▼                      │ fault+dead        ▼
        ┌──────────────────────────────────────────────────────┐
        │  DETECT: _seat_is_dead()?  ──no──▶ propagate genuine   │
        │            │yes                     fault to agent      │
        │            ▼                                            │
        │  attempts<cap & not poison? ──no──▶ FATAL (named)      │
        │            │yes                                        │
        │            ▼                                            │
        │  RESPAWN (≤30s) ─▶ Tier2? restore backup ─▶ REPLAY ────┼──▶ back to OPEN
        └──────────────────────────────────────────────────────┘
```

---

## 7. Testing plan

Full dual-tier test plan in the **Test specification** section below (written before
any session code). In brief:

- **Offline (every CI run, no seat):** dependency-injected fakes; both measured fault
  signatures reconstructed as plain objects (`pywintypes.com_error(-2147023174, …)` /
  `AttributeError`); faked clock so respawn-budget/cap/poison logic runs in
  microseconds. Proves the state machine + the liveness oracle (benign `AttributeError`
  ≠ respawn).
- **Live (`-m destructive_sw`):** an `__assassin__` handler injected at proposal index
  2 shells `taskkill /F /PID <bound_pid>` (by PID, never `/IM`) — deterministic
  mid-transaction death by seam-injection, not timing. Plus a save-seam variant for
  Tier 2 and a reproducible-crasher for the poison cap.
- **Assertion contract = strict geometric equivalence to a non-interrupted golden
  run:** transparent catch + `recovery` block, FULL pristine replay, and
  `tree_hash == golden ∧ node_count == golden ∧ volume ≈ golden` (NOT mtime/byte —
  SW embeds timestamps; `mtime` only asserted to have *advanced*).

---

## 8. Design decisions & open questions

1. **Scope of "intent" replayed** — only `proposals` (current design), or also any
   pre-batch document mutations? Recommend: supervised batch owns the whole
   `doc_path` transaction; anything outside it is the caller's checkpoint concern.
2. **Active-doc collision / recovery UI on respawn — RESOLVED** (§3.1,
   `spike_seat_recovery_ui.py`): the fresh seat boots with `ActiveDoc=None` and no
   blocking Document-Recovery modal on the batch timescale; the watchdog-timed
   readiness probe is the hard backstop, the `swxauto` clear the defensive belt.
3. **CheckpointStore reuse — RESOLVED (2026-06-25): a dedicated table, NOT reuse.**
   Measure-first found `CheckpointStore` is a per-FEATURE geometry ledger whose
   every row carries NOT-NULL `pre_tree_hash`/`post_tree_hash`; a batch
   transaction has an intent payload + status but no geometry hash, so reusing it
   would mean injecting dummy hashes to satisfy those constraints. Shipped instead
   as a dedicated `checkpoint.TransactionStore` (id/doc_path/spec_hash/
   intent_payload/status/recovery_json) bound via `resilience.TransactionStoreJournal`
   — the schema now matches the architectural model. PENDING→COMMITTED on
   recovery; a fatal run stays PENDING (the host-crash resume anchor). The
   in-memory `InMemoryJournal` remains the seat-free default for the offline
   test suite. (Note: §6.2's pseudo-code above still shows the original
   `CheckpointStore`-reuse sketch — superseded by this dedicated-table decision.)
4. **CoUninitialize necessity** — the experiment recovered first-attempt *with* the
   apartment reset; we did not isolate whether the cache-drop alone suffices. Cheap
   to keep; flag for a follow-up micro-probe if respawn latency matters.

---

# Test specification

_Consolidated from the former `supervised_session_test_spec.md`._


> Companion to the design spec above. This was written *before*
> `resilience/session.py`: a recovery envelope is only as trustworthy as the
> crash it survives.

## 0. The two tiers, and why both

| Tier | Runs | Proves | Pays the ~8s respawn tax? |
|---|---|---|---|
| **Offline mocks** | every CI run (no seat) | the Python state machine: detect → tier-select → respawn → replay → cap, and manifest shaping | **No** — faults & respawn are injected, clock is faked |
| **Live destructive** | `-m destructive_sw` only | the live end-to-end proof: a real `taskkill` mid-transaction recovers to a geometrically identical model | Yes — one real respawn per case |

Offline proves the **logic** is correct in milliseconds; live proves the **physics**
hold. Neither alone is sufficient — offline can't prove COM actually faults
`0x800706BA`, live is too slow/flaky to exhaust every control-flow branch.

---

## 1. Offline mock strategy

### 1.1 Dependency injection at the seams

`SupervisedSession` is built to take injectable collaborators so tests substitute
fakes without touching COM:

```python
SupervisedSession(
    batch_runner = <calls _sw_batch_feature_add_impl>,   # the transaction
    seat         = <is_alive() / respawn() / pid>,        # the SeatController
    journal      = <CheckpointStore: pending()/commit()>, # the commit marker
    snapshotter  = <copy()/restore() pristine file>,      # Tier-2 backup
    clock        = <now()/sleep()>,                       # fake-able time
)
```

Production wires the real ones; tests pass fakes. The envelope's control flow is
identical either way — that is precisely what we're validating.

### 1.2 Reproducing the two measured fault signatures WITHOUT a seat

Both signatures from `spike_seat_death_recovery.py` are constructible as plain
Python objects — no process needed:

```python
import pywintypes
RPC_DEAD = pywintypes.com_error(-2147023174, "The RPC server is unavailable.", None, None)  # 0x800706BA
DYN_DEAD = AttributeError("SldWorks.Application.RevisionNumber")                              # dynamic-dispatch death
```

A fake `batch_runner.run` is programmed with a `side_effect` list to fault on the
first call and succeed on the replay:

```python
batch_runner.run.side_effect = [
    _raise_death_at(index=2, exc=RPC_DEAD),   # attempt 1: dies after 2 greens
    _green_manifest(committed=[0,1,2]),       # attempt 2 (replay): full success
]
```

For **integration-flavored** offline tests, register a test-only handler in
`mutate.HANDLER_REGISTRY` (monkeypatched, restored in teardown) keyed
`"__test_death__"` that raises `RPC_DEAD` when applied, and drive the REAL
`_sw_batch_feature_add_impl` over a fully mocked `doc` (a `MagicMock` whose
`Extension`/`SketchManager`/save are stubs). This exercises the real engine's
`fault{stage:"apply"}` path → the envelope's reclassification, end to end, offline.

### 1.3 The liveness oracle, isolated

Parametrize `_seat_is_dead(sw, pid)` against fakes:

| `_pid_alive(pid)` | `_rev(sw)` | Expected verdict |
|---|---|---|
| False | (not reached) | **dead** (process gone) |
| True | raises `RPC_DEAD` | **dead** |
| True | raises `DYN_DEAD` | **dead** (the AttributeError trap) |
| True | returns `"32.1.0"` | **alive** → propagate original error |

This is the single most important offline test: it proves a **benign
`AttributeError` with a live seat does NOT trigger a respawn**, while a death does.

### 1.4 Faked time — no real sleeps

Inject `clock`; the respawn loop calls `clock.sleep(2)` / `clock.now()`. The fake
advances a counter, so the 30s `RESPAWN_BUDGET_S` deadline, the
`MAX_RESPAWN_REPLAYS=2` cap, the poison-proposal counter, and the 120s wall-clock
backstop are all validated **deterministically in microseconds**.

### 1.5 What offline asserts (pure logic)

- Tier selection: death in `apply` → Tier 1 (no snapshot restore); death in `save`
  → Tier 2 (snapshotter.restore called exactly once).
- Commit-marker dichotomy: `journal` has `pending`-no-`commit` → restore+replay;
  `committed` → no-op.
- Retry cap: 3rd death raises fatal (recovered=False) — never a 4th respawn.
- **Poison quarantine:** same `proposal_index` dies twice → abort BEFORE the global
  cap, fatal manifest carries `poison_proposal == 2` + echoed feature/target.
- Manifest `recovery` block shape (deaths[], replays, tier, recovered, fatal_reason).

---

## 2. Live kill-injection — the `destructive_sw` suite

### 2.1 The kill-injection handler (deterministic timing by construction)

Rather than race a `taskkill` against the batch, we inject the kill **at the seam**,
so timing is exact, not timed. A test-only handler registered in
`HANDLER_REGISTRY["__assassin__"]`:

```python
def _assassin(doc, feature, target):
    # captured before the batch: the BOUND seat's PID
    subprocess.run(["taskkill", "/F", "/PID", str(BOUND_PID)], ...)  # by PID, never /IM
    # any COM call after this faults 0x800706BA — return; the loop's next op detects it
    return True, "assassin fired"
```

Place it as **proposal index 2 of 3** (`[real_a, real_b, __assassin__]` — or
`[a, b, __assassin__, c, d]` to also prove the tail replays). The death lands
deterministically mid-apply-loop **after two greens are in memory and BEFORE the
terminal `_save_doc`** → Tier 1, disk pristine. No sleeps, no flakiness.

> **Why inject the kill rather than time it:** the `taskkill` lives INSIDE the
> index-2 handler, so the crash point is the handler invocation itself — precise by
> construction, not approximate by timing. We kill **by PID** (the experiment proved
> `/PID` works and is safe; `/IM` would terminate a developer's unrelated SOLIDWORKS
> instance — forbidden in this suite).

### 2.2 Tier-2 variant (save-window death)

To exercise the snapshot-restore path, a fixture monkeypatches `_save_doc` for one
test to `lambda doc: (_kill(BOUND_PID), _real_save(doc))[1]` — the seat dies at the
save seam. Assert `recovery.tier == 2` and that the pre-save `snapshotter` backup was
restored before replay.

### 2.3 Poison-proposal cap (anti-infinite-loop)

A kill-injection that fires on **every** invocation of index 2 (kills, and on replay
kills again). Assert: the envelope stops after the **2nd same-index death**, returns
`recovered=False, poison_proposal=2`, within the wall-clock backstop — proving a
reproducible kernel-crasher cannot wedge the agent.

### 2.4 Isolation & safety rules

- **Marker:** `@pytest.mark.destructive_sw` (SEH-crash isolation; the existing
  conftest auto-skips unless `-m destructive_sw`).
- **Kill by PID only**, captured from the bound seat (`find_sw_pid()` at setup).
  Never `/IM`. A guard asserts `BOUND_PID` is set before any kill can fire.
- **Throwaway fixtures:** each test `shutil.copy2`s a `captures/*.SLDPRT` into a
  temp dir; never touches tracked files or the developer's documents.
- **Teardown:** restore `HANDLER_REGISTRY`, `CloseAllDocuments`, leave no orphan
  (the respawned headless seat self-closes — verified by the experiment).

---

## 3. The assertion contract

A "passed recovery" is **strict geometric equivalence to a non-interrupted run** —
not merely "it didn't throw".

### 3.1 The golden baseline

Run the SAME proposal list (the `__assassin__` handler removed) on an **identical fresh fixture copy**,
capture the golden witnesses:

```
golden = {
  committed:  manifest["committed"],                 # ordered kind sequence
  node_count: GetFeatureCount(doc),                  # feature-tree size
  tree_hash:  checkpoint._read_current_tree_hash(doc),  # structural identity
  volume:     observe.mbd? no -> CreateMassProperty .Volume,  # geometric identity
}
```

### 3.2 The five assertions (recovery run, kill at index 2)

1. **Transparency** — the agent-facing manifest is a SUCCESS: `ok == True`, and the
   `recovery` block records exactly the death we injected:
   `deaths == [{attempt:1, phase:"apply", proposal_index:2, fault:"0x800706ba"}]`,
   `replays == 1`, `tier == 1`, `recovered == True`. The death was caught
   transparently; the agent never saw a COM error.
2. **Full pristine replay (not partial resume)** — `recovered.committed == golden.committed`
   (same kinds, same order, same **count**). The WHOLE list re-ran from the top.
3. **Geometric equivalence** — `recovered.tree_hash == golden.tree_hash` AND
   `recovered.node_count == golden.node_count` AND
   `recovered.volume == pytest.approx(golden.volume)`. The recovered model is
   bit-for-geometry identical to the clean run.
4. **No double-apply (idempotency)** — `node_count == golden.node_count` exactly
   (NOT `>`). A replay that re-added an already-saved feature would over-count; Tier-1
   pristine disk guarantees it can't, and this assertion is the tripwire.
5. **Durable + bounded** — the file `mtime` **advanced past the pre-batch baseline**
   (a save genuinely happened) and the whole recovery completed within a time budget
   (< 30s incl. one real respawn).

> **On asserting "mtime + node count":** `mtime` cannot be *equal* across two
> runs (it's wall-clock); we assert `mtime > pre_batch_baseline` to prove a save
> occurred. **Geometric identity is carried by `tree_hash` + `node_count` + `volume`,
> not byte-equality** — SW embeds timestamps/GUIDs in the `.sldprt` binary, so two
> identical-geometry saves are never byte-equal. Tree-hash is the right equivalence.

### 3.3 Tier-2 extra assertion

For the save-window case, additionally: `recovery.tier == 2`, the snapshot-restore
fired, and §3.2 assertions 2–4 still hold (the restore→replay produced the correct
model despite the corrupt-save window).

---

## 4. Test matrix

| # | Suite | Case | Asserts |
|---|---|---|---|
| 1 | offline | liveness oracle (4 rows of §1.3) | dead/alive verdict; benign-AttributeError ≠ respawn |
| 2 | offline | death at apply-i → Tier-1 replay | manifest shape, full committed[], 1 replay |
| 3 | offline | death at save → Tier-2 restore | snapshotter.restore ×1, journal dichotomy |
| 4 | offline | retry cap | 3rd death → fatal, no 4th respawn |
| 5 | offline | poison proposal | same-index ×2 → fatal w/ poison_proposal, < backstop |
| 6 | offline | faked clock | respawn budget / cap timing, zero real sleep |
| 7 | **live** | kill @ index 2 of 3 → Tier 1 | the full §3.2 contract vs golden |
| 8 | **live** | kill @ index 2 of 5 → Tier 1 | tail (3,4) replays; equivalence vs golden |
| 9 | **live** | save-window kill → Tier 2 | §3.3 |
| 10 | **live** | reproducible crasher → poison | recovered=False, named, bounded |

---

## 5. Harness & fixtures

- `tests/resilience/test_supervised_offline.py` — cases 1–6, no marker, every CI run.
- `tests/e2e_sw/test_supervised_recovery.py` — cases 7–10, `@destructive_sw`,
  single-threaded, PID-targeted kills, temp fixture copies.
- Shared `conftest`: `_golden_run(fixture, proposals)` helper, `BOUND_PID` capture,
  `HANDLER_REGISTRY` monkeypatch guard, tree-hash/node-count/volume witness readers.
- The seat-death recovery experiment (`spike_seat_death_recovery.py`) is the
  provenance for the live kill mechanics; this suite productionizes it behind
  deterministic seam-injection.
