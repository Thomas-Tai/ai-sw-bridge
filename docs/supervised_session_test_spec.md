# SupervisedSession — Dual-Tier Test Spec (the Gauntlet)

> **Status:** DRAFT for lock · **Authored:** 2026-06-24 · companion to
> `docs/supervised_session_spec.md`. We write this BEFORE `resilience/session.py`:
> a recovery envelope is only as trustworthy as the assassination it survives.

## 0. The two tiers, and why both

| Tier | Runs | Proves | Pays the ~8s respawn tax? |
|---|---|---|---|
| **Offline mocks** | every CI run (no seat) | the Python state machine: detect → tier-select → respawn → replay → cap, and manifest shaping | **No** — faults & respawn are injected, clock is faked |
| **Live destructive** | `-m destructive_sw` only | the physical PAE: a real `taskkill` mid-transaction recovers to a geometrically identical model | Yes — one real respawn per case |

Offline proves the **logic** is correct in milliseconds; live proves the **physics**
hold. Neither alone is sufficient — offline can't prove COM actually faults
`0x800706BA`, live is too slow/flaky to exhaust every control-flow branch.

---

## 1. Offline mock strategy  *(directive §1)*

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

## 2. Live assassin injection — the `destructive_sw` lane  *(directive §2)*

### 2.1 The Assassin handler (deterministic timing by construction)

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
`[a, b, assassin, c, d]` to also prove the tail replays). The death lands
deterministically mid-apply-loop **after two greens are in memory and BEFORE the
terminal `_save_doc`** → Tier 1, disk pristine. No sleeps, no flakiness.

> **Why the user's "shell out at index 2" instinct is right — and sharpened:** the
> shell-out lives INSIDE the index-2 handler, so the crash point is the handler
> invocation itself. We make it precise by injection rather than approximate by
> timing, and we kill **by PID** (the spike proved `/PID` works and is safe;
> `/IM` would nuke a developer's unrelated SW instance — forbidden in the lane).

### 2.2 Tier-2 variant (save-window death)

To exercise the snapshot-restore path, a fixture monkeypatches `_save_doc` for one
test to `lambda doc: (_kill(BOUND_PID), _real_save(doc))[1]` — the seat dies at the
save seam. Assert `recovery.tier == 2` and that the pre-save `snapshotter` backup was
restored before replay.

### 2.3 Poison-proposal cap (anti-infinite-loop)

An assassin that fires on **every** invocation of index 2 (kills, and on replay kills
again). Assert: the envelope stops after the **2nd same-index death**, returns
`recovered=False, poison_proposal=2`, within the wall-clock backstop — proving a
reproducible kernel-crasher cannot wedge the agent.

### 2.4 Isolation & safety rules

- **Marker:** `@pytest.mark.destructive_sw` (SEH-crash isolation; the existing
  conftest auto-skips unless `-m destructive_sw`).
- **Kill by PID only**, captured from the bound seat (`find_sw_pid()` at setup).
  Never `/IM`. A guard asserts `BOUND_PID` is set before any assassin can fire.
- **Throwaway fixtures:** each test `shutil.copy2`s a `captures/*.SLDPRT` into a
  temp dir; never touches tracked files or the developer's documents.
- **Teardown:** restore `HANDLER_REGISTRY`, `CloseAllDocuments`, leave no orphan
  (the respawned headless seat self-closes — verified by the spike).

---

## 3. The assertion contract  *(directive §3)*

A "passed recovery" is **strict geometric equivalence to a non-interrupted run** —
not merely "it didn't throw".

### 3.1 The golden baseline

Run the SAME proposal list (assassin removed) on an **identical fresh fixture copy**,
capture the golden witnesses:

```
golden = {
  committed:  manifest["committed"],                 # ordered kind sequence
  node_count: GetFeatureCount(doc),                  # feature-tree size
  tree_hash:  checkpoint._read_current_tree_hash(doc),  # structural identity
  volume:     observe.mbd? no -> CreateMassProperty .Volume,  # geometric identity
}
```

### 3.2 The five assertions (recovery run, assassin at index 2)

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

> **On the directive's "mtime + node count":** `mtime` cannot be *equal* across two
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

| # | Lane | Case | Asserts |
|---|---|---|---|
| 1 | offline | liveness oracle (4 rows of §1.3) | dead/alive verdict; benign-AttributeError ≠ respawn |
| 2 | offline | death at apply-i → Tier-1 replay | manifest shape, full committed[], 1 replay |
| 3 | offline | death at save → Tier-2 restore | snapshotter.restore ×1, journal dichotomy |
| 4 | offline | retry cap | 3rd death → fatal, no 4th respawn |
| 5 | offline | poison proposal | same-index ×2 → fatal w/ poison_proposal, < backstop |
| 6 | offline | faked clock | respawn budget / cap timing, zero real sleep |
| 7 | **live** | assassin @ index 2 of 3 → Tier 1 | the full §3.2 contract vs golden |
| 8 | **live** | assassin @ index 2 of 5 → Tier 1 | tail (3,4) replays; equivalence vs golden |
| 9 | **live** | save-window assassin → Tier 2 | §3.3 |
| 10 | **live** | reproducible crasher → poison | recovered=False, named, bounded |

---

## 5. Harness & fixtures

- `tests/resilience/test_supervised_offline.py` — cases 1–6, no marker, every CI run.
- `tests/e2e_sw/test_supervised_recovery.py` — cases 7–10, `@destructive_sw`,
  single-threaded, PID-targeted kills, temp fixture copies.
- Shared `conftest`: `_golden_run(fixture, proposals)` helper, `BOUND_PID` capture,
  `HANDLER_REGISTRY` monkeypatch guard, tree-hash/node-count/volume witness readers.
- The murder-spike (`spike_seat_death_recovery.py`) is the provenance for the live
  kill mechanics; this suite productionizes it behind deterministic seam-injection.
