# SupervisedSession — Crash-Recovery Envelope Spec (Resilience Epoch)

> **Status:** DRAFT for architecture lock · **Authored:** 2026-06-24 ·
> **Grounded in:** `spikes/spike_seat_death_recovery.py` telemetry +
> `mutate.py` transaction model + `checkpoint/` + `sw_com` cache.
> **Scope:** the single-seat, mid-hold crash — the 99% commercial path.
> Dual-instance ghost-PID and mid-`OpenDoc6` deaths are explicitly out of scope.

## 0. Premise (measured, not assumed)

From the murder-spike telemetry (`_results/seat_death_recovery.json`):

| Fact | Value | Source |
|---|---|---|
| Early-bound (`typed`) post-death fault | `com_error` HRESULT **`0x800706BA`** RPC_S_SERVER_UNAVAILABLE | spike Phase 3 |
| Dynamic (`Dispatch`) post-death fault | **`AttributeError`** (`GetIDsOfNames` on dead server) | spike Phase 3 |
| Fault latency | **immediate, 0.0s** — never hangs (property reads AND method calls) | spike Phase 3 |
| Re-bind | **~8–9s**, first `Dispatch`, **new PID**, ROT self-clears | spike Phase 4 (×3) |
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

## 2. Fault Detection Boundary  *(directive §1)*

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

## 3. Respawn Orchestration  *(directive §2)*

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
  SLDWORKS.exe" /NH /FO CSV` (proven in the spike; robust to display formatting).
- **No manual ROT surgery** — the dead entry self-clears; `release_sw_app()` +
  fresh `Dispatch` is sufficient (measured ×3).

### 3.1 UI-blocker suppression  *(resolved by `spike_seat_recovery_ui.py`, 2026-06-24)*

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

## 4. Replay Engine — Tier 1 & Tier 2  *(directive §3)*

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

Full dual-tier gauntlet specified in **`docs/supervised_session_test_spec.md`**
(locked before any session code). In brief:

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

## 8. Open questions for the lock

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
   gauntlet. (Note: §6.2's pseudo-code above still shows the original
   `CheckpointStore`-reuse sketch — superseded by this dedicated-table decision.)
4. **CoUninitialize necessity** — the spike recovered first-attempt *with* the
   apartment reset; we did not isolate whether the cache-drop alone suffices. Cheap
   to keep; flag for a follow-up micro-probe if respawn latency matters.
