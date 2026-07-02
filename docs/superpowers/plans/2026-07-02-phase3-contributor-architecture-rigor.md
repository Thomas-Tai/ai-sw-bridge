# Phase 3 — Contributor & Architecture Rigor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decompose `spec/builder.py` (3335 LOC) into `spec/handlers/*.py` behind a lean acyclic kernel, as byte-identical pure relocations, then lock the module-size gate to blocking, strengthen the conformance test, expand mypy, and rewrite CONTRIBUTING.

**Architecture:** A dependency-free `spec/handlers/_common.py` leaf (3 COM-transport symbols) is extracted first; then six handler families relocate in ascending-risk order (`pattern → revolve → hole → dress_up → sketch → extrude`), each re-exported into `builder`'s namespace so `_wire_handlers` and every `builder.<sym>` monkeypatch seam keep resolving unchanged. `HANDLERS`/`DESCRIPTORS` dispatch stays byte-for-byte identical; no behavior change.

**Tech Stack:** Python 3.11+, pytest, import-linter, mypy, `tools/module_size_gate.py`.

**Design spec:** `docs/superpowers/specs/2026-07-02-phase3-contributor-architecture-rigor-design.md`

## Global Constraints

- **Branch:** `docs/commercial-elevation` only. NEVER `feat/w67-phase3`.
- **Seat-safe suite only:** `pytest -m "not solidworks_only and not destructive_sw"`. NEVER bare `pytest`; NEVER run `tests/e2e_sw/` or `tests/mcp_lane/` bodies. Baseline = **3894 passed** — must stay green at EVERY commit.
- **A LIVE SOLIDWORKS seat is running (PID 40652).** Every handler move is COM-adjacent (`builder.py` imports `get_sw_app`). Run **seat-prefire-review before any subagent touches a handler/`_common` file** (procedure below). Only the extrude live-seat re-fire (Task 6) intentionally exercises the seat.
- **Byte-identical moves:** move function bodies unchanged; carry every module constant a moved function references. `HANDLERS`/`DESCRIPTORS` dispatch must not change. No walled/dormant kind promoted to GREEN.
- **Re-export rule:** after moving symbols to `spec/handlers/<F>.py`, add `from .handlers.<F> import (<moved symbols>)` to `builder.py` so `builder.<sym>` still resolves (the `client.py` `_impl` precedent). `# noqa: F401` where re-exported only for back-compat/seams.
- **HELD push:** no `git push` until the whole phase is green, then a single `isPrivate`-guarded fast-forward to **master** (`git push origin docs/commercial-elevation:master`, no force).
- **Report telemetry after each task** before dispatching the next.
- **Import-linter** must stay `kept, 0 broken` at every commit. Command: `python -c "import sys; from importlinter.cli import lint_imports_command; sys.exit(lint_imports_command())"` (the console `lint-imports` isn't on PATH in Git Bash).

### Seat-prefire procedure (run BEFORE dispatching any COM-adjacent task)

Create/run `scratchpad/seat_prefire_builder.py`:

```python
import sys
TRIPPED = []
def _blk(n):
    def _r(*a, **k):
        TRIPPED.append(n); raise RuntimeError(f"COM {n} blocked")
    return _r
import win32com.client as w
for nm in ("Dispatch", "DispatchEx", "GetActiveObject", "EnsureDispatch"):
    if hasattr(w, nm): setattr(w, nm, _blk(nm))
try:
    import win32com.client.gencache as gc
    if hasattr(gc, "EnsureDispatch"): gc.EnsureDispatch = _blk("gencache.EnsureDispatch")
except Exception: pass
import ai_sw_bridge.spec.builder  # noqa: F401 -- import must not touch COM
print("TRIPPED:", TRIPPED)
assert TRIPPED == [], f"import touched COM: {TRIPPED}"
print("OK - builder import is COM-clean")
```

Run: `python scratchpad/seat_prefire_builder.py` — require `TRIPPED: []` and (separately) SLDWORKS PID unchanged. If TRIPPED is non-empty, HALT and escalate.

### The anti-mirror seam check (run per family move, after the re-export)

A relocated monkeypatch seam that no longer intercepts is a silent regression. For each family, after the move:
1. Enumerate the family's seams: `grep -rhoE "builder\.(_[a-zA-Z0-9_]+)" tests/ | sort | uniq -c` filtered to this family's symbols.
2. For ≥1 seam symbol: temporarily edit the MOVED function in `handlers/<F>.py` to `raise AssertionError("probe")`, run the specific test that patches it. If the test still exercises the code, it FAILS (seam bites through re-export). If it PASSES unchanged, the seam is DEAD — the caller resolves the symbol from `handlers.<F>`'s namespace, not `builder`'s → **re-point that test** to patch `ai_sw_bridge.spec.handlers.<F>.<sym>`. Revert the probe.
3. Record per-seam disposition (re-export-safe | re-pointed) in the task's report.

---

## File Structure

**New files:**
- `src/ai_sw_bridge/spec/handlers/__init__.py` — package marker (empty or docstring only).
- `src/ai_sw_bridge/spec/handlers/_common.py` — the 3-symbol acyclic kernel.
- `src/ai_sw_bridge/spec/handlers/pattern.py` — linear/circular/mirror + `_mark_first_selection`.
- `src/ai_sw_bridge/spec/handlers/revolve.py` — revolve boss/cut + `_call_feature_revolve`.
- `src/ai_sw_bridge/spec/handlers/hole.py` — `_build_simple_hole`.
- `src/ai_sw_bridge/spec/handlers/dress_up.py` — fillet/chamfer + edge-selection block.
- `src/ai_sw_bridge/spec/handlers/sketch.py` — 8 sketch primitives + plane/3d/text helpers.
- `src/ai_sw_bridge/spec/handlers/extrude.py` — boss/cut families + extrusion helpers + `@versioned _cut4_args_*`.
- `tests/spec/test_versioned_import_order.py` — guards the extrude `@versioned` registry population.

**Modified files:**
- `src/ai_sw_bridge/spec/builder.py` — remove moved defs, add re-export imports; shrinks to ~800 LOC.
- `pyproject.toml` — import-linter forbidden contract for the handlers leaf.
- `tools/module_size_baseline.json` — remove `builder.py` entry after it drops under 800.
- `.github/workflows/ci.yml:76` — `python tools/module_size_gate.py` → `--strict`.
- `tests/test_extension_conformance.py` — strengthened to the self-registration contract.
- `mypy.ini` (or `pyproject.toml [tool.mypy]`) — add `spec/handlers/*` to strict set.
- `CONTRIBUTING.md` — D5 registry recipes, Extension Contract, CLASS_RELATION_MAP canonical.

---

## Task 0: Move 0 — `spec/handlers/_common.py` (the acyclic kernel)

**COM-adjacency:** YES → seat-prefire REQUIRED before dispatch.

**Files:**
- Create: `src/ai_sw_bridge/spec/handlers/__init__.py`, `src/ai_sw_bridge/spec/handlers/_common.py`
- Modify: `src/ai_sw_bridge/spec/builder.py`, `pyproject.toml`

**Interfaces:**
- Produces: `spec.handlers._common` exporting `_mm_to_m(value) -> float`, `_select_sketch(ctx: BuildContext, sketch_name: str) -> None`, `_r8_safearray(values: list[float]) -> Any`.
- Consumes: `BuildContext` from `.._build_context`; `pythoncom`/`win32com` for `_r8_safearray`.

- [ ] **Step 0: Seat-prefire** — run the procedure above. Require `TRIPPED: []` + PID unchanged.

- [ ] **Step 1: Capture the current three function bodies verbatim**

Read `builder.py` lines for `_mm_to_m` (~1679), `_r8_safearray` (~1691), `_select_sketch` (~553). Copy each body byte-identical. Note their exact current imports/deps (`_mm_to_m` is pure; `_r8_safearray` uses `win32com`/`pythoncom` — find the exact call in the current body; `_select_sketch` uses `ctx` + COM).

- [ ] **Step 2: Create the package + kernel module**

Create `src/ai_sw_bridge/spec/handlers/__init__.py`:

```python
"""Feature build handlers, relocated from builder.py (Phase 3).

Each family module imports only leaf modules (_common, _build_context,
_edge_selectors, _face_geometry, _sketch_primitives, _version_resolver,
sketches) — never builder.py. builder.py re-exports the handlers back into
its namespace so _wire_handlers and monkeypatch seams resolve unchanged.
"""
```

Create `src/ai_sw_bridge/spec/handlers/_common.py` with the three functions moved byte-identical, e.g.:

```python
"""Shared COM/transport kernel for the feature handlers (Phase 3 Move 0).

Acyclic leaf: imports only stdlib, COM, and the _build_context leaf — NEVER
builder.py or any sibling handler module (import-linter forbidden contract
pins this). Holds only genuinely cross-family primitives.
"""
from __future__ import annotations

from typing import Any

from .._build_context import BuildContext

# <paste _mm_to_m body byte-identical>
# <paste _r8_safearray body byte-identical, with its win32com/pythoncom import>
# <paste _select_sketch body byte-identical>
```

(Move the exact bodies; keep any module constant they reference. If `_r8_safearray` imports `win32com.client`/`pythoncom` at module level in builder, add the same import here.)

- [ ] **Step 3: Remove the three defs from builder.py and re-export**

Delete the three `def` blocks from `builder.py`. Add near builder's other `from .` imports:

```python
from .handlers._common import _mm_to_m, _r8_safearray, _select_sketch  # noqa: F401  -- re-exported for _wire_handlers + monkeypatch seams
```

- [ ] **Step 4: Add the import-linter forbidden contract**

In `pyproject.toml`, add (adapt `name`/format to the existing contracts):

```toml
[[tool.importlinter.contracts]]
name = "spec handlers kernel is a builder-free leaf"
type = "forbidden"
source_modules = ["ai_sw_bridge.spec.handlers._common"]
forbidden_modules = ["ai_sw_bridge.spec.builder"]
```

- [ ] **Step 5: Run import-linter**

Run: `python -c "import sys; from importlinter.cli import lint_imports_command; sys.exit(lint_imports_command())"`
Expected: all contracts `KEPT`, `0 broken`.

- [ ] **Step 6: Anti-mirror seam check for `_mm_to_m` / `_r8_safearray`**

Per the anti-mirror procedure: the 4 tests patching `builder._mm_to_m` and 1 patching `builder._r8_safearray` must still bite. Probe (raise in the moved fn), run those tests, confirm behavior, re-point any dead seam to `ai_sw_bridge.spec.handlers._common.<sym>`, revert probe.

- [ ] **Step 7: Run the affected suite subset + full seat-safe suite**

Run: `python -m pytest tests/spec/ tests/test_extension_conformance.py tests/test_doc_truth.py -q -m "not solidworks_only and not destructive_sw"`
Then: `python -m pytest -m "not solidworks_only and not destructive_sw" -q`
Expected: **3894 passed** (unchanged). Confirm SLDWORKS PID 40652 unchanged.

- [ ] **Step 8: Commit**

```bash
git add src/ai_sw_bridge/spec/handlers/__init__.py src/ai_sw_bridge/spec/handlers/_common.py src/ai_sw_bridge/spec/builder.py pyproject.toml
git commit -m "refactor(spec): extract _common.py kernel (Move 0) — _mm_to_m/_select_sketch/_r8_safearray"
```

---

## Task 1: Move 1 — `pattern.py` (proving-ground family, 0 seams)

**COM-adjacency:** YES → seat-prefire REQUIRED.

**Files:**
- Create: `src/ai_sw_bridge/spec/handlers/pattern.py`
- Modify: `src/ai_sw_bridge/spec/builder.py`

**Symbols to move (byte-identical):** `_build_linear_pattern`, `_build_circular_pattern`, `_build_mirror_feature`, `_mark_first_selection` (all callers of `_mark_first_selection` are these three handlers).

**Interfaces:**
- Consumes: `BuildContext`, `BuiltFeature` (from `.._build_context`); `_mm_to_m`/`_select_sketch` (from `._common` if used — check each body); any `_face_geometry`/`_edge_selectors` leaf helpers the bodies call.
- Produces: the four symbols, re-exported into `builder`.

- [ ] **Step 0: Seat-prefire** — run procedure; require `TRIPPED: []` + PID unchanged.

- [ ] **Step 1: Seam audit**

Run: `grep -rhoE "builder\.(_build_linear_pattern|_build_circular_pattern|_build_mirror_feature|_mark_first_selection)" tests/ | sort | uniq -c`
Expected: (design measured 0 for pattern handlers; confirm). Record the list.

- [ ] **Step 2: Create `pattern.py` and move the four defs byte-identical**

Create `src/ai_sw_bridge/spec/handlers/pattern.py` with a module docstring and the four functions moved verbatim. Import what the bodies need from leaves:

```python
from __future__ import annotations
from typing import Any
from .._build_context import BuildContext, BuiltFeature
from ._common import _mm_to_m, _select_sketch  # only those actually used — verify
# <paste _mark_first_selection, _build_linear_pattern, _build_circular_pattern, _build_mirror_feature byte-identical>
```

Verify by reading each body which leaf symbols it references; add exactly those imports (missing imports pass offline but fail at the seat — port carefully).

- [ ] **Step 3: Remove the four defs from builder.py and re-export**

Delete the four blocks from `builder.py`; add:

```python
from .handlers.pattern import (  # noqa: F401  -- re-exported for _wire_handlers + seams
    _build_circular_pattern,
    _build_linear_pattern,
    _build_mirror_feature,
    _mark_first_selection,
)
```

Confirm `_wire_handlers`'s local dict entries (`"linear_pattern": _build_linear_pattern`, etc.) still resolve via the re-export.

- [ ] **Step 4: import-linter + anti-mirror check**

Run import-linter (expect KEPT/0 broken). Run the anti-mirror probe on `_build_linear_pattern` (or whichever seam exists; if 0 seams, probe that dispatch still routes: temporarily raise in the moved fn, run a pattern build test, confirm FAIL, revert).

- [ ] **Step 5: Run pattern tests + full seat-safe suite**

Run: `python -m pytest tests/spec/ tests/test_extension_conformance.py -q -m "not solidworks_only and not destructive_sw"`
Then full: `python -m pytest -m "not solidworks_only and not destructive_sw" -q`
Expected: **3894 passed**. PID 40652 unchanged.

- [ ] **Step 6: Commit**

```bash
git add src/ai_sw_bridge/spec/handlers/pattern.py src/ai_sw_bridge/spec/builder.py
git commit -m "refactor(spec): relocate pattern family to handlers/pattern.py (Move 1)"
```

---

## Task 2: Move 2 — `revolve.py`

**COM-adjacency:** YES → seat-prefire REQUIRED.

**Files:** Create `src/ai_sw_bridge/spec/handlers/revolve.py`; Modify `builder.py`.

**Symbols (byte-identical):** `_build_revolve_boss`, `_build_revolve_cut`, `_call_feature_revolve` (revolve-only). `_call_feature_revolve` calls `_select_sketch` → import from `._common`.

- [ ] **Step 0: Seat-prefire** — require `TRIPPED: []` + PID unchanged.
- [ ] **Step 1: Seam audit** — `grep -rhoE "builder\.(_build_revolve_boss|_build_revolve_cut|_call_feature_revolve)" tests/ | sort | uniq -c`. Record.
- [ ] **Step 2: Create `revolve.py`**, move the three defs byte-identical:

```python
from __future__ import annotations
from typing import Any
from .._build_context import BuildContext, BuiltFeature
from ._common import _select_sketch  # _call_feature_revolve uses it
# <paste _call_feature_revolve, _build_revolve_boss, _build_revolve_cut byte-identical>
```
Add any other leaf import the bodies use (read them; e.g. `_version_resolver` if `@versioned`, `_face_geometry` if face refs).

- [ ] **Step 3: Remove from builder.py + re-export:**

```python
from .handlers.revolve import (  # noqa: F401
    _build_revolve_boss,
    _build_revolve_cut,
    _call_feature_revolve,
)
```
- [ ] **Step 4: import-linter + anti-mirror check** (probe `_build_revolve_boss`).
- [ ] **Step 5:** Run `python -m pytest tests/spec/ tests/test_extension_conformance.py -q -m "not solidworks_only and not destructive_sw"` then full seat-safe suite. Expected **3894 passed**, PID unchanged.
- [ ] **Step 6: Commit** — `git commit -m "refactor(spec): relocate revolve family to handlers/revolve.py (Move 2)"`

---

## Task 3: Move 3 — `hole.py`

**COM-adjacency:** YES → seat-prefire REQUIRED.

**Files:** Create `src/ai_sw_bridge/spec/handlers/hole.py`; Modify `builder.py`.

**Symbols (byte-identical):** `_build_simple_hole` (self-contained — uses `_select_extrude_face`, `_face_frame`, `_warn_face_sketch_offset` from the `_face_geometry` leaf + raw `ctx.doc` COM; no builder-local shared helper).

- [ ] **Step 0: Seat-prefire** — require `TRIPPED: []` + PID unchanged.
- [ ] **Step 1: Seam audit** — `grep -rhoE "builder\._build_simple_hole" tests/ | sort | uniq -c`. Record.
- [ ] **Step 2: Create `hole.py`**, move `_build_simple_hole` byte-identical:

```python
from __future__ import annotations
from typing import Any
from .._build_context import BuildContext, BuiltFeature
from .._face_geometry import _select_extrude_face, _face_frame, _warn_face_sketch_offset
# <paste _build_simple_hole byte-identical>
```
Verify the exact `_face_geometry` symbols the body calls; import exactly those.

- [ ] **Step 3: Remove from builder.py + re-export:** `from .handlers.hole import _build_simple_hole  # noqa: F401`
- [ ] **Step 4: import-linter + anti-mirror check** (probe `_build_simple_hole`).
- [ ] **Step 5:** Run spec tests then full seat-safe suite. Expected **3894 passed**, PID unchanged.
- [ ] **Step 6: Commit** — `git commit -m "refactor(spec): relocate hole family to handlers/hole.py (Move 3)"`

---

## Task 4: Move 4 — `dress_up.py` (7 seams — re-point audit matters)

**COM-adjacency:** YES → seat-prefire REQUIRED.

**Files:** Create `src/ai_sw_bridge/spec/handlers/dress_up.py`; Modify `builder.py`.

**Symbols (byte-identical):** handlers `_build_fillet_constant_radius`, `_build_chamfer_edge`; helpers `_edge_fingerprint`, `_all_solid_edges`, `_select_edges`, `_mark_first_selection`? (NO — that's pattern's; do not move it here); constants `_EDGE_FP_REFS`, `SW_FM_FILLET`, `SW_CONST_RADIUS_FILLET`.

**Critical seam note:** `_select_edges` has **7 test seams**. Because the fillet/chamfer handlers call `_select_edges` *intra-module* after the move, tests that patch `builder._select_edges` to intercept that call will go DEAD unless re-pointed. This task's anti-mirror check MUST classify all 7.

- [ ] **Step 0: Seat-prefire** — require `TRIPPED: []` + PID unchanged.
- [ ] **Step 1: Seam audit** — `grep -rlE "builder\.(_select_edges|_build_fillet_constant_radius|_build_chamfer_edge|_edge_fingerprint|_all_solid_edges)" tests/`. List every test file + line.
- [ ] **Step 2: Create `dress_up.py`**, move handlers + helpers + constants byte-identical:

```python
from __future__ import annotations
from typing import Any
from .._build_context import BuildContext, BuiltFeature
from .._edge_selectors import parse_edge_selectors, resolve_edge_selectors, faces_referenced  # verify exact symbols used
# constants
SW_FM_FILLET = 1
SW_CONST_RADIUS_FILLET = 0
_EDGE_FP_REFS = ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
# <paste _edge_fingerprint, _all_solid_edges, _select_edges, _build_fillet_constant_radius, _build_chamfer_edge byte-identical>
```
Read each body for exact `_edge_selectors`/`_face_geometry`/`_common` symbols used; import exactly those.

- [ ] **Step 3: Remove from builder.py + re-export:**

```python
from .handlers.dress_up import (  # noqa: F401
    SW_CONST_RADIUS_FILLET,
    SW_FM_FILLET,
    _all_solid_edges,
    _build_chamfer_edge,
    _build_fillet_constant_radius,
    _edge_fingerprint,
    _select_edges,
)
```
(Also re-export `_EDGE_FP_REFS` if any test/other code references `builder._EDGE_FP_REFS`.)

- [ ] **Step 4: Anti-mirror check on ALL 7 `_select_edges` seams**

For each of the 7 tests: probe (raise in `handlers/dress_up.py::_select_edges`), run that test. If it still fails → seam bites (the test calls `builder._select_edges` directly or patches something dispatch-reached). If it passes unchanged → the handler's intra-module call bypasses the `builder` re-export → **re-point that test** to `monkeypatch.setattr("ai_sw_bridge.spec.handlers.dress_up._select_edges", ...)`. Revert probe. Record each seam's disposition.

- [ ] **Step 5: import-linter** (KEPT/0 broken), then spec tests + full seat-safe suite. Expected **3894 passed**, PID unchanged.
- [ ] **Step 6: Commit** — `git commit -m "refactor(spec): relocate dress_up family to handlers/dress_up.py (Move 4); re-point _select_edges seams"`

---

## Task 5: Move 5 — `sketch.py` (8 handlers, ~28 seams — largest mechanical move)

**COM-adjacency:** YES → seat-prefire REQUIRED.

**Files:** Create `src/ai_sw_bridge/spec/handlers/sketch.py`; Modify `builder.py`.

**Symbols (byte-identical):** handlers `_build_sketch_line`, `_build_sketch_arc`, `_build_sketch_spline`, `_build_sketch_slot`, `_build_sketch_polygon`, `_build_sketch_ellipse`, `_build_sketch_text`, `_build_sketch_3d_sketch`; helpers `_enter_plane_sketch`, `_close_plane_sketch_and_build`, `_apply_construction`, `_segments`, `_enter_3d_sketch`, `_close_3d_sketch_and_build`, `_as_sketch_text`, `_apply_text_format`. Uses `_mm_to_m`, `_r8_safearray` from `._common`; `_literal_or_default`, `PLACEHOLDER_MM` from `_sketch_primitives` leaf.

- [ ] **Step 0: Seat-prefire** — require `TRIPPED: []` + PID unchanged.
- [ ] **Step 1: Seam audit** — `grep -rhoE "builder\.(_build_sketch_[a-z0-9_]+|_enter_plane_sketch|_close_plane_sketch_and_build|_apply_construction|_segments|_as_sketch_text|_apply_text_format|_enter_3d_sketch|_close_3d_sketch_and_build)" tests/ | sort | uniq -c`. Expect ~28. List every test file.
- [ ] **Step 2: Create `sketch.py`**, move all 8 handlers + 8 helpers byte-identical:

```python
from __future__ import annotations
from typing import Any
from .._build_context import BuildContext, BuiltFeature
from .._sketch_primitives import PLACEHOLDER_MM, _literal_or_default  # verify usage
from ._common import _mm_to_m, _r8_safearray
# <paste the 8 helpers then the 8 handlers, byte-identical>
```
Verify per-body imports (some handlers call `_face_geometry`/`sketches` leaf helpers — read and import exactly those). NOTE: `_build_sketch_*` keep their existing `NotImplementedError` sub-mode branches unchanged (byte-identical; no promotion).

- [ ] **Step 3: Remove all 16 defs from builder.py + re-export** (alphabetized import of all 16 names) `# noqa: F401`.
- [ ] **Step 4: Anti-mirror check** — classify the ~28 seams. Handler seams (`builder._build_sketch_X`) are typically direct-call/dispatch and re-export-safe; helper seams (`_enter_plane_sketch` etc.) called intra-module by handlers likely need re-pointing to `ai_sw_bridge.spec.handlers.sketch.<sym>`. Probe a representative of each class; re-point dead ones; record all dispositions.
- [ ] **Step 5: import-linter** (KEPT/0 broken); run `tests/spec/test_sketch_*.py` explicitly, then spec tests, then full seat-safe suite. Expected **3894 passed**, PID unchanged.
- [ ] **Step 6: Commit** — `git commit -m "refactor(spec): relocate sketch family to handlers/sketch.py (Move 5); re-point sketch seams"`

---

## Task 6: Move 6 — `extrude.py` (LAST — `@versioned` correctness risk + live-seat re-fire)

**COM-adjacency:** YES → seat-prefire REQUIRED. **Live-seat re-fire:** YES (the DoD gate).

**Files:** Create `src/ai_sw_bridge/spec/handlers/extrude.py`; Create `tests/spec/test_versioned_import_order.py`; Modify `builder.py`.

**Symbols (byte-identical):** handlers `_build_boss_extrude_blind/midplane/through_all/two_direction/up_to_surface`, `_build_cut_extrude_through_all/blind/midplane/two_direction`; helpers `_call_feature_extrusion`, `_call_feature_cut`, `_boss_built_feature`; `@versioned`-decorated `_cut4_args_2024`, `_cut4_args_2025`. Uses `_select_sketch`, `_mm_to_m` from `._common`; `versioned`, `resolve_op`, `DEFAULT_KEY`, `SW_2025_MAJOR` from `_version_resolver`.

- [ ] **Step 0: Seat-prefire** — require `TRIPPED: []` + PID unchanged.
- [ ] **Step 1: Seam audit** — `grep -rhoE "builder\.(_build_boss_extrude_[a-z_]+|_build_cut_extrude_[a-z_]+|_call_feature_extrusion|_call_feature_cut|_cut4_args_2024|_cut4_args_2025|_boss_built_feature)" tests/ | sort | uniq -c`. Expect ~15. List every test file.
- [ ] **Step 2: Create `extrude.py`**, move all handlers + helpers + the two `@versioned` funcs byte-identical:

```python
from __future__ import annotations
from typing import Any
from .._build_context import BuildContext, BuiltFeature
from .._version_resolver import DEFAULT_KEY, SW_2025_MAJOR, resolve_op, versioned
from ._common import _mm_to_m, _select_sketch
# <paste _call_feature_extrusion, _cut4_args_2024 (@versioned), _cut4_args_2025 (@versioned),
#  _call_feature_cut, _boss_built_feature, then the 9 handlers — byte-identical>
```
The `@versioned("FeatureCut4", DEFAULT_KEY)` / `@versioned("FeatureCut4", SW_2025_MAJOR)` decorators must be preserved exactly so both register into the version-resolver registry at import.

- [ ] **Step 3: Remove all extrude defs from builder.py + re-export** (all handlers + helpers + `_cut4_args_2024`/`_cut4_args_2025`) `# noqa: F401`. Because `_wire_handlers` runs at builder import and references these names, the re-export import line MUST precede `_wire_handlers()` execution order (it does — imports are at top).

- [ ] **Step 4: Write the `@versioned` import-order guard test**

Create `tests/spec/test_versioned_import_order.py`:

```python
"""Guard: importing builder populates the @versioned FeatureCut4 registry.

The extrude relocation (Phase 3 Move 6) risks the version-resolver registry
not being populated if handlers/extrude.py isn't imported before dispatch.
This test fails loudly if either the 2024 or 2025 variant fails to resolve.
COM-clean: import + registry lookup only; no seat, no dispatch.
"""
from __future__ import annotations


def test_featurecut4_versioned_variants_resolve_after_builder_import() -> None:
    import ai_sw_bridge.spec.builder  # noqa: F401  -- triggers handler import + registration
    from ai_sw_bridge.spec._version_resolver import DEFAULT_KEY, SW_2025_MAJOR, resolve_op

    assert resolve_op("FeatureCut4", DEFAULT_KEY) is not None
    assert resolve_op("FeatureCut4", SW_2025_MAJOR) is not None
```

Adjust the `resolve_op` call signature to match `_version_resolver.resolve_op`'s real signature (read it first).

- [ ] **Step 5: Run the guard test + anti-mirror check**

Run: `python -m pytest tests/spec/test_versioned_import_order.py -q`
Expected: PASS. Then anti-mirror the ~15 seams (esp. `_cut4_args_2024/2025` with 11 seams — classify re-export-safe vs re-point).

- [ ] **Step 6: import-linter + full offline suite**

Run import-linter (KEPT/0 broken). Run full seat-safe suite: `python -m pytest -m "not solidworks_only and not destructive_sw" -q`. Expected **3895 passed** (+1 = the new import-order test), PID 40652 unchanged.

- [ ] **Step 7: LIVE-SEAT RE-FIRE (DoD gate) — orchestrator-run, isolated**

This is the one intentional live-seat exercise. Run `seat-prefire` first (paradoxically confirms import-clean), then fire a minimal extrude build against the seat to prove the relocated `@versioned` dispatch executes the real COM call. Use an existing destructive/seat spike pattern (e.g. `tests/e2e_sw/` extrude fixture) run ISOLATED with `-m solidworks_only` on a single test, NOT the batched suite. Confirm a boss_extrude + cut_extrude build succeeds and the resolved `FeatureCut4` variant matches the seat's SW major. Record the result. If the seat is unavailable, mark the DoD item BLOCKED and escalate (do not fake it).

- [ ] **Step 8: Commit**

```bash
git add src/ai_sw_bridge/spec/handlers/extrude.py tests/spec/test_versioned_import_order.py src/ai_sw_bridge/spec/builder.py
git commit -m "refactor(spec): relocate extrude family to handlers/extrude.py (Move 6); @versioned import-order guard + live-seat re-fire"
```

---

## Task 7: Module-size gate warn→block

**COM-adjacency:** NONE.

**Files:** Modify `tools/module_size_baseline.json`, `.github/workflows/ci.yml`.

- [ ] **Step 1: Measure builder.py**

Run: `wc -l src/ai_sw_bridge/spec/builder.py` and `for f in src/ai_sw_bridge/spec/handlers/*.py; do wc -l "$f"; done`
Expected: `builder.py` ≤ 800; every `handlers/*.py` < 800. If `sketch.py` or `extrude.py` ≥ 800, STOP — split the family module further (a sub-family seam) before proceeding; do not baseline it.

- [ ] **Step 2: Remove builder.py from the baseline**

Edit `tools/module_size_baseline.json`: delete the `"src/ai_sw_bridge/spec/builder.py": 3335` line. Leave the other 8 entries (accepted debt, out of scope).

- [ ] **Step 3: Verify the gate passes in strict mode**

Run: `python tools/module_size_gate.py --strict`
Expected: exit 0, "module-size gate: OK". (builder.py now under ceiling; new handler modules under ceiling; other 8 at baseline.)

- [ ] **Step 4: Flip CI to strict**

Edit `.github/workflows/ci.yml:76`: `run: python tools/module_size_gate.py` → `run: python tools/module_size_gate.py --strict`

- [ ] **Step 5: Commit**

```bash
git add tools/module_size_baseline.json .github/workflows/ci.yml
git commit -m "ci: promote module-size gate to --strict; drop builder.py from baseline (now < 800)"
```

---

## Task 8: Strengthen `tests/test_extension_conformance.py`

**COM-adjacency:** NONE (import + registry introspection; keep COM-clean).

**Files:** Modify `tests/test_extension_conformance.py`.

- [ ] **Step 1: Write the failing strengthened test**

Add to `tests/test_extension_conformance.py`:

```python
def test_every_spec_handler_lives_in_handlers_package() -> None:
    """Post-Phase-3: every DESCRIPTORS handler resolves to a callable defined
    in a spec.handlers.* module (or the sketches handler classes), proving the
    self-registration shape holds and no handler slid back into builder.py."""
    from ai_sw_bridge.spec import builder

    strays = []
    for name, ft in builder.DESCRIPTORS.items():
        handler = ft.handler
        mod = getattr(handler, "__module__", "")
        # sketches.* handler-class .build methods are allowed; everything else
        # must live under spec.handlers.* (NOT spec.builder).
        if mod == "ai_sw_bridge.spec.builder":
            strays.append(name)
    assert not strays, f"handlers still defined in builder.py (should be in handlers/*): {strays}"


def test_handlers_never_import_builder() -> None:
    """The handler leaf layer must not import builder (acyclic guarantee)."""
    import ast
    from pathlib import Path

    hdir = Path(__file__).resolve().parents[1] / "src" / "ai_sw_bridge" / "spec" / "handlers"
    offenders = []
    for py in hdir.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and "builder" in node.module:
                offenders.append(py.name)
            if isinstance(node, ast.Import):
                for a in node.names:
                    if "builder" in a.name:
                        offenders.append(py.name)
    assert not offenders, f"handler modules import builder (breaks the leaf): {offenders}"
```

Adjust `DESCRIPTORS`/`FeatureType.handler` access to the real attribute names (read `_build_context.FeatureDescriptor`). The `sketches.*` handler-class `.build` methods have `__module__` under `ai_sw_bridge.spec.sketches` — allowed.

- [ ] **Step 2: Run to verify it passes** (all handlers already moved by Tasks 1–6)

Run: `python -m pytest tests/test_extension_conformance.py -q`
Expected: PASS. If `test_every_spec_handler_lives_in_handlers_package` fails, a family was missed — fix the relocation, not the test.

- [ ] **Step 3: Verify the guard bites**

Temporarily move one handler def back into `builder.py` (or repoint one `_wire_handlers` entry to a builder-local fn), run → confirm `strays` fails; revert.

- [ ] **Step 4: Full seat-safe suite + commit**

Run full suite (expect 3897 = +2 new conformance tests over 3895). Then:

```bash
git add tests/test_extension_conformance.py
git commit -m "test(conformance): strengthen to the self-registration + handler-leaf contract (Phase 3)"
```

---

## Task 9: mypy strict on `spec/handlers/*`

**COM-adjacency:** NONE.

**Files:** Modify `mypy.ini` (or `[tool.mypy]` in `pyproject.toml` — check which the repo uses; the config `files = src` was noted earlier, so it lives in `mypy.ini`).

- [ ] **Step 1: Locate the strict-typed set** — read `mypy.ini`. Find how per-module strictness is configured (e.g. `[mypy-ai_sw_bridge.features.*]` sections).

- [ ] **Step 2: Add the handlers modules to the strict set**

Add (matching the existing section style):

```ini
[mypy-ai_sw_bridge.spec.handlers.*]
disallow_untyped_defs = True
disallow_incomplete_defs = True
# (mirror whatever the strictest existing per-module section uses)
```

- [ ] **Step 3: Run mypy on the handlers**

Run: `python -m mypy src/ai_sw_bridge/spec/handlers/`
Expected: `Success: no issues found`. Handlers are already `(BuildContext, dict) -> BuiltFeature` typed. Fix any surfaced annotation gaps (the moved code was already strict-clean in builder; expect zero).

- [ ] **Step 4: Full mypy + commit**

Run: `python -m mypy src` (whole tree, expect no new errors). Then:

```bash
git add mypy.ini
git commit -m "types: enable strict mypy for spec/handlers/* (Phase 3)"
```

---

## Task 10: `CONTRIBUTING.md` rewrite (D5 + Extension Contract + CLASS_RELATION_MAP)

**COM-adjacency:** NONE.

**Files:** Modify `CONTRIBUTING.md`; possibly `docs/architecture.md` (mark superseded, D8).

- [ ] **Step 1: Re-grep D3/D4/D5 at execution**

Run: `grep -nE "v0\.2|early-stage|manual for now|integration tests" CONTRIBUTING.md` and read `CONTRIBUTING.md:80-89`. Record which of D3 (version), D4 (integration-tests-manual), D5 (features/ registry recipe) are still open (D3 likely fixed — doc-truth pins CONTRIBUTING to v1.7.0).

- [ ] **Step 2: Add the two-registry extension recipes (D5)**

Add a "Adding a capability" section documenting BOTH distinct paths, concretely:
- **Spec-build handler** (part-modelling feature in a spec): add a `FeatureType` to `spec/builder.py::DESCRIPTORS`, implement `_build_<kind>(ctx, feat) -> BuiltFeature` in the appropriate `spec/handlers/<family>.py`, wire it in `_wire_handlers`, add schema fields in `spec/descriptors.py`.
- **feature_add / mutate handler**: register in `features/HANDLER_REGISTRY` (the `client.mutate` path). Reference the existing registry mechanic.
State clearly these are two separate registries for two separate surfaces.

- [ ] **Step 3: Publish the five-row Extension Contract**

Insert the Extension Contract table (governing spec §6) — the five obligations every new capability must satisfy (handler + schema + doc + example + test/conformance). Copy the canonical five rows from the governing spec.

- [ ] **Step 4: Promote CLASS_RELATION_MAP.md as canonical; mark architecture.md superseded (D8)**

Point CONTRIBUTING's architecture reference at `docs/CLASS_RELATION_MAP.md`. Add a top note to `docs/architecture.md`: `> **Superseded** by [CLASS_RELATION_MAP.md](CLASS_RELATION_MAP.md) (Phase 3). Kept for history.` Fix any still-open D3/D4 wording.

- [ ] **Step 5: Doc-truth + commit**

Run: `python -m pytest tests/test_doc_truth.py -q -m "not solidworks_only and not destructive_sw"`
Expected: PASS (CONTRIBUTING version pin preserved). Then:

```bash
git add CONTRIBUTING.md docs/architecture.md
git commit -m "docs(contributing): two-registry extension recipes (D5) + Extension Contract + CLASS_RELATION_MAP canonical"
```

---

## Final Checkpoint — full gauntlet + HELD push

- [ ] **Step 1: Full seat-safe suite** — `python -m pytest -m "not solidworks_only and not destructive_sw" -q`. Expected ≥ 3897 passed (3894 baseline + import-order + 2 conformance), 0 failed. PID 40652 unchanged.
- [ ] **Step 2: import-linter + module-size strict + mypy** — `python -c "import sys; from importlinter.cli import lint_imports_command; sys.exit(lint_imports_command())"` (KEPT/0 broken); `python tools/module_size_gate.py --strict` (OK); `python -m mypy src` (clean).
- [ ] **Step 3: Verify DoD** — every §10.4 box: 6 families + `_common` relocated; builder ~800 & off baseline; dispatch byte-identical (conformance green); gate `--strict`; conformance strengthened; mypy strict handlers; CONTRIBUTING rewritten; extrude live-seat re-fire GREEN.
- [ ] **Step 4: isPrivate-guarded fast-forward push to master**

```bash
gh repo view --json isPrivate           # MUST be true
git fetch origin
git merge-base --is-ancestor origin/master HEAD && echo FF-SAFE
# confirm HEAD unchanged since the check, then:
git push origin docs/commercial-elevation:master   # no force
```
Only push after ALL boxes checked and the gauntlet is green. If isPrivate≠true or FF-safety fails, HALT and escalate.

---

## Self-Review

**1. Spec coverage:**
- Move 0 `_common` (§2.1/§3.1) → Task 0. ✓
- Six families in locked order (§2.2/§3.2) → Tasks 1–6. ✓
- Re-export discipline + anti-mirror seam check (§3.2/§3.3) → every family task Step 3–4 + the per-plan procedure. ✓
- `@versioned` import-order (§3.4) → Task 6 Step 4 guard test. ✓
- WALL-NO-AMNESTY (§3.5) → byte-identical moves; sketch keeps NotImplementedError sub-modes (Task 5 Step 2). ✓
- Module-size warn→block (§4.1) → Task 7. ✓
- Strengthen conformance (§4.2) → Task 8. ✓
- mypy strict (§4.3) → Task 9. ✓
- CONTRIBUTING rewrite (§4.4) → Task 10. ✓
- Live-seat re-fire on extrude (§5.3/DoD) → Task 6 Step 7. ✓
- Safety: seat-prefire per COM-adjacent task; seat-safe suite green each commit; HELD isPrivate FF push. ✓
- Non-goals honored: other 8 grandfathered modules untouched; descriptors.py schema untouched; features/ registry documented not refactored. ✓

**2. Placeholder scan:** every move task lists exact symbols + exact grep/test/commit commands; the re-export imports are spelled out; the guard test and conformance tests have full code. The `# <paste ... byte-identical>` markers are deliberate move-instructions (the bodies exist verbatim in builder.py and must not be rewritten), paired with exact import lines — not TBDs. No "similar to Task N": each family task is self-contained with its own symbols/commands.

**3. Type consistency:** `_build_*(ctx: BuildContext, feat: dict) -> BuiltFeature` used uniformly; `_common` exports `_mm_to_m`/`_select_sketch`/`_r8_safearray` consistently across Tasks 0/1/2/5/6; `DESCRIPTORS`/`FeatureType`/`FeatureDescriptor` names match builder.py; `resolve_op`/`versioned`/`DEFAULT_KEY`/`SW_2025_MAJOR` match `_version_resolver` imports.

**Known measure-at-execution items (not placeholders — genuine per-family measurements the implementer performs):** exact leaf-import set per moved body (read the body, import exactly what it calls); exact seam re-export-vs-re-point disposition (the anti-mirror check decides); whether sketch.py/extrude.py need sub-splitting to stay < 800 (Task 7 Step 1 gate).
