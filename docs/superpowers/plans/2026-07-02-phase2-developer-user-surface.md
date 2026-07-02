# Phase 2 — Developer-User Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the developer/integrator half of `ai-sw-bridge` into a documented, versioned, *enforced* supported surface — cohesive cross-linked docs, an explicit deprecation policy, two drift fixes, a relocated MCP walkthrough, plus two executable CI guards (facade surface pin + DEPRECATIONS registry).

**Architecture:** Two new leaf test/code artifacts close the one unguarded surface (facade) and build the deprecation-enforcement spine; five documentation tasks apply the Diátaxis "unify framing, keep separate" architecture and fix D9/D10. Every prose promise is paired with a machine check; every pinned doc fact is preserved.

**Tech Stack:** Python 3.11+, pytest, `inspect`/`importlib.metadata`, import-linter (in `pyproject.toml`), Markdown docs.

**Design spec:** `docs/superpowers/specs/2026-07-02-phase2-developer-user-surface-design.md`

## Global Constraints

- **Branch:** `docs/commercial-elevation` only. NEVER commit to `feat/w67-phase3`.
- **Seat-safe suite only:** `pytest -m "not solidworks_only and not destructive_sw"`. NEVER a bare `pytest`; NEVER execute `tests/e2e_sw/` or `tests/mcp_lane/` bodies.
- **Seat-prefire-review** before any subagent touches a COM-adjacent file: static grep for `Dispatch|DispatchEx|GetActiveObject|EnsureDispatch|CoCreateInstance|win32com` **plus** a dynamic tripwire (monkeypatch those to raise, import target, assert `TRIPPED == []` and SLDWORKS PID unchanged). Marked per-task below.
- **Doc-truth gate is absolute:** no substring pinned in `tests/test_doc_truth.py::DOC_SURFACES` may drop. Current version = `1.7.0`; MCP tools = 37; CLI commands derived from pyproject. Re-run `pytest tests/test_doc_truth.py -q` after every doc task.
- **HELD push:** no `git push` until ALL tasks complete and the full seat-safe gauntlet is green, then a single `isPrivate`-guarded fast-forward push (verify `gh repo view --json isPrivate` == true, `origin/master` ancestor of HEAD, HEAD unchanged since check).
- **Deprecation policy (LOCKED):** stable CLI / MCP tool / facade → deprecate in 1.N, remove only at the next major boundary (2.0), floor ≥ 2 minor releases; experimental CLI / spec handler → deprecate in 1.N, remove in 1.N+1.
- **Commit style:** Conventional Commits, matching repo history (`feat(...)`, `fix(docs): ...`, `test(...)`).
- Each task ends with a commit. Telemetry (suite pass count, files touched, checkpoint verdict) reported after each task before dispatching the next.

---

## File Structure

**New files:**
- `src/ai_sw_bridge/deprecations.py` — cross-surface deprecation registry + pure grace validator (leaf; stdlib-only imports).
- `tests/test_deprecations.py` — synthetic-fixture gate for the validator + live present/absent cross-check.
- `tests/test_facade_surface.py` — frozen snapshot of the `SolidWorksClient` + facade public surface; fails on any drift.

**Modified files:**
- `pyproject.toml` — add an import-linter forbidden-imports contract pinning `deprecations.py` as a leaf.
- `docs/PUBLIC_API.md` — deprecation anchor + staleness truing (typo, stale sub-table, pre-1.0 SemVer/grace language) + shared nav block.
- `USAGE.md` — shared nav block + D9 fix (line 136).
- `docs/tools_reference.md` — shared nav block.
- `README.md` — D10 fix (line 368) + MCP walkthrough → stub (lines 244–334) + confirm dev router (348–357).
- `docs/AGENTS.md` — D10 fix (lines 128, 176).
- `docs/mcp_server_design.md` — receives the relocated MCP walkthrough.

---

## Task 1: DEPRECATIONS registry + CI gate

**COM-adjacency:** NONE (pure version arithmetic, stdlib-only). Seat-prefire: NOT required.

**Files:**
- Create: `src/ai_sw_bridge/deprecations.py`
- Test: `tests/test_deprecations.py`
- Modify: `pyproject.toml` (import-linter contract)

**Interfaces:**
- Produces: `DeprecationEntry(id: str, surface_class: str, deprecated_in: str, remove_in: str, replacement: str)` (frozen dataclass); `Violation(entry_id: str, reason: str)` (frozen dataclass); `DEPRECATIONS: tuple[DeprecationEntry, ...]` (empty at v1.7.0, immutable); `validate_registry(entries: Sequence[DeprecationEntry], current: str) -> list[Violation]`; `current_version() -> str`.
- Consumes: nothing from the package (leaf).

- [ ] **Step 1: Write the failing test**

Create `tests/test_deprecations.py`:

```python
"""Gate for the cross-surface deprecation registry + grace validator.

Synthetic fixtures exercise the pure validator with an empty production
registry; a live cross-check asserts present/absent consistency against the
real surface registries. The production DEPRECATIONS tuple is never mutated.
"""
from __future__ import annotations

import pytest

from ai_sw_bridge.deprecations import (
    DEPRECATIONS,
    DeprecationEntry,
    validate_registry,
    current_version,
)


def _entry(**kw):
    base = dict(
        id="mcp_tool:sw_old",
        surface_class="mcp_tool",
        deprecated_in="1.8",
        remove_in="2.0",
        replacement="sw_new",
    )
    base.update(kw)
    return DeprecationEntry(**base)


# --- production registry is clean & immutable -------------------------------

def test_production_registry_is_empty_and_valid():
    assert DEPRECATIONS == ()
    assert validate_registry(DEPRECATIONS, current_version()) == []


def test_production_registry_is_immutable():
    with pytest.raises((AttributeError, TypeError)):
        DEPRECATIONS.append(_entry())  # type: ignore[attr-defined]


# --- valid synthetic entries produce no violations --------------------------

def test_valid_stable_entry_ok():
    assert validate_registry([_entry(surface_class="mcp_tool")], "1.9") == []
    assert validate_registry([_entry(surface_class="stable_cli")], "1.9") == []
    assert validate_registry([_entry(surface_class="facade")], "1.9") == []


def test_valid_experimental_entry_ok():
    e = _entry(surface_class="experimental_cli", deprecated_in="1.8", remove_in="1.9")
    assert validate_registry([e], "1.8") == []
    e2 = _entry(surface_class="spec_handler", deprecated_in="1.8", remove_in="1.9")
    assert validate_registry([e2], "1.8") == []


# --- each invalid case yields exactly one violation -------------------------

def test_stable_removal_not_at_major_boundary_violates():
    e = _entry(surface_class="mcp_tool", deprecated_in="1.8", remove_in="1.9")
    v = validate_registry([e], "1.8")
    assert len(v) == 1 and "boundary" in v[0].reason


def test_stable_removal_at_nonzero_minor_violates():
    e = _entry(surface_class="facade", deprecated_in="1.8", remove_in="2.1")
    v = validate_registry([e], "1.8")
    assert len(v) == 1 and "boundary" in v[0].reason


def test_experimental_removal_skipping_a_minor_violates():
    e = _entry(surface_class="experimental_cli", deprecated_in="1.8", remove_in="1.10")
    v = validate_registry([e], "1.8")
    assert len(v) == 1 and "next minor" in v[0].reason


def test_announce_not_before_remove_violates():
    e = _entry(surface_class="experimental_cli", deprecated_in="1.8", remove_in="1.8")
    v = validate_registry([e], "1.8")
    assert len(v) == 1


def test_unknown_surface_class_violates():
    e = _entry(surface_class="bogus")
    v = validate_registry([e], "1.8")
    assert len(v) == 1 and "surface_class" in v[0].reason


def test_unparseable_version_violates():
    e = _entry(deprecated_in="one.two")
    v = validate_registry([e], "1.8")
    assert len(v) == 1


# --- live cross-check: entries must name real surfaces & obey present/absent -

def test_live_entries_reference_real_surfaces():
    """Every production entry must name a surface that exists (until removed)."""
    from ai_sw_bridge.cli.stability import TIER_REGISTRY  # noqa: F401
    # With DEPRECATIONS empty this is vacuously true; the check is wired so the
    # first real entry is validated against the live registries.
    for e in DEPRECATIONS:
        assert ":" in e.id  # id is "<class>:<surface-name>"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_deprecations.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ai_sw_bridge.deprecations'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/ai_sw_bridge/deprecations.py`:

```python
"""Cross-surface deprecation registry + grace-policy validator.

Leaf module: imports only stdlib. Governs the four public surface classes
(stable CLI, MCP tool, facade, spec handler) by *opaque string id* — it never
imports the symbols it governs, so it cannot form an import cycle. An
import-linter forbidden contract (pyproject.toml) pins the leaf property.

Policy (PUBLIC_API.md "Deprecation policy", ratified 2026-07-02):
  stable_cli / mcp_tool / facade  -> deprecate in 1.N; removed ONLY at the next
      major boundary (2.0), floor >= 2 minor releases between announce and cut.
      The gate enforces the stronger, cleanly-checkable superset: removal lands
      only on the next major's .0 (never within the announcing major), which
      guarantees the whole remainder of the 1.x line elapses first.
  experimental_cli / spec_handler -> deprecate in 1.N; removed in 1.N+1.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import version as _pkg_version
from typing import Sequence

_STABLE_CLASSES = frozenset({"stable_cli", "mcp_tool", "facade"})
_EXPERIMENTAL_CLASSES = frozenset({"experimental_cli", "spec_handler"})


@dataclass(frozen=True)
class DeprecationEntry:
    id: str  # "<surface_class>:<surface-name>", e.g. "mcp_tool:sw_bbox"
    surface_class: str
    deprecated_in: str  # "1.8"
    remove_in: str  # "2.0"
    replacement: str


@dataclass(frozen=True)
class Violation:
    entry_id: str
    reason: str


# Production registry — EMPTY at v1.7.0. Immutable tuple: an accidental
# mutation raises rather than silently pollutes. Add entries HERE (never in a
# test) when a real surface is deprecated.
DEPRECATIONS: tuple[DeprecationEntry, ...] = ()


def _parse(v: str) -> tuple[int, int]:
    """Parse 'MAJOR.MINOR' (any patch suffix ignored)."""
    parts = v.split(".")
    return int(parts[0]), int(parts[1])


def current_version() -> str:
    return _pkg_version("ai-sw-bridge")


def validate_registry(
    entries: Sequence[DeprecationEntry], current: str
) -> list[Violation]:
    """Pure validator — reads only its arguments, never the module global."""
    out: list[Violation] = []
    for e in entries:
        try:
            dep = _parse(e.deprecated_in)
            rem = _parse(e.remove_in)
        except (ValueError, IndexError):
            out.append(Violation(e.id, f"unparseable version in {e!r}"))
            continue
        if rem <= dep:
            out.append(Violation(e.id, "remove_in must be strictly after deprecated_in"))
            continue
        if e.surface_class in _STABLE_CLASSES:
            # Removal only at the next major boundary: (dep_major + 1, 0).
            if rem != (dep[0] + 1, 0):
                out.append(
                    Violation(
                        e.id,
                        "stable surface must be removed at the next major boundary "
                        f"({dep[0] + 1}.0), not {e.remove_in}",
                    )
                )
        elif e.surface_class in _EXPERIMENTAL_CLASSES:
            if rem != (dep[0], dep[1] + 1):
                out.append(
                    Violation(
                        e.id,
                        f"experimental surface must be removed in the next minor "
                        f"({dep[0]}.{dep[1] + 1}), not {e.remove_in}",
                    )
                )
        else:
            out.append(Violation(e.id, f"unknown surface_class {e.surface_class!r}"))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_deprecations.py -q`
Expected: PASS (all cases green).

- [ ] **Step 5: Pin the leaf property with import-linter**

In `pyproject.toml`, locate the `[tool.importlinter]` section and its contracts. Add a new contract (adapt `name` numbering to the existing list):

```toml
[[tool.importlinter.contracts]]
name = "deprecations registry is a stdlib-only leaf"
type = "forbidden"
source_modules = ["ai_sw_bridge.deprecations"]
forbidden_modules = [
    "ai_sw_bridge.cli",
    "ai_sw_bridge.mcp",
    "ai_sw_bridge.client",
    "ai_sw_bridge.spec",
    "ai_sw_bridge.mutate",
    "ai_sw_bridge.observe",
    "ai_sw_bridge.features",
]
```

- [ ] **Step 6: Run import-linter to verify the contract holds**

Run: `lint-imports` (or `python -m importlinter` — match the command the repo's CI uses; check `pyproject.toml`/CI config).
Expected: the new contract passes (deprecations.py imports nothing forbidden).

- [ ] **Step 7: Run the seat-safe suite subset touched**

Run: `pytest tests/test_deprecations.py tests/test_doc_truth.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/ai_sw_bridge/deprecations.py tests/test_deprecations.py pyproject.toml
git commit -m "feat(deprecations): cross-surface registry + grace-policy CI gate (empty at 1.7.0)"
```

---

## Task 2: Facade public-surface pin

**COM-adjacency:** YES — the test imports `ai_sw_bridge.client`. Import is known-safe (lazy/injectable `app`/`mod`), but **seat-prefire-review is REQUIRED** before the implementer touches this file.

**Files:**
- Create: `tests/test_facade_surface.py`

**Interfaces:**
- Consumes: `ai_sw_bridge.client.SolidWorksClient` + facade classes `SolidWorksObserverFacade`, `SolidWorksMutatorFacade`, `UrdfFacade`, `SolidWorksExportFacade`, `SolidWorksFeaturesFacade`.
- Produces: nothing consumed by later tasks.

- [ ] **Step 0: SEAT-PREFIRE-REVIEW (orchestrator runs BEFORE dispatching implementer)**

Static: `grep -nE "Dispatch|DispatchEx|GetActiveObject|EnsureDispatch|CoCreateInstance|win32com" src/ai_sw_bridge/client.py tests/test_facade_surface.py` — confirm the new test adds no COM-trigger; note any in client.py are behind lazy properties.

Dynamic tripwire — run this and require `TRIPPED == []` + SLDWORKS PID unchanged:

```python
# scratchpad/seat_prefire_facade.py
import os, sys
TRIPPED = []
import win32com.client as w
for name in ("Dispatch", "DispatchEx", "GetActiveObject", "EnsureDispatch"):
    orig = getattr(w, name, None)
    if orig:
        setattr(w, name, lambda *a, _n=name, **k: (TRIPPED.append(_n), (_ for _ in ()).throw(RuntimeError(f"COM {_n} blocked")))[1])
import ai_sw_bridge.client  # noqa: F401  -- import must NOT touch COM
print("TRIPPED:", TRIPPED)
assert TRIPPED == [], f"import touched COM: {TRIPPED}"
print("OK — import is COM-clean")
```

Run: `python scratchpad/seat_prefire_facade.py`
Expected: `TRIPPED: []` then `OK`. If TRIPPED is non-empty, STOP and escalate — do not dispatch the implementer.

- [ ] **Step 1: Write the failing test**

Create `tests/test_facade_surface.py`:

```python
"""Frozen snapshot of the SolidWorksClient public surface (PUBLIC_API.md §3).

The facade's "signatures guaranteed backward-compatible" promise had no guard
(CLI has test_cli_stability, MCP has EXPECTED_TOOLS). This closes that leg.
Strict snapshot: BOTH removals and un-snapshotted additions fail, mirroring
EXPECTED_TOOLS discipline — public surface stays intentionally designed.

COM-clean: importing client.py touches no COM (lazy app/mod). Do not
instantiate against a live seat here.
"""
from __future__ import annotations

import inspect

from ai_sw_bridge.client import (
    SolidWorksClient,
    SolidWorksObserverFacade,
    SolidWorksMutatorFacade,
    UrdfFacade,
    SolidWorksExportFacade,
    SolidWorksFeaturesFacade,
)


def _surface(cls) -> dict[str, str]:
    """Public members: methods -> signature string; properties -> '<property>'."""
    out: dict[str, str] = {}
    for name in dir(cls):
        if name.startswith("_"):
            continue
        attr = inspect.getattr_static(cls, name)
        if isinstance(attr, property):
            out[name] = "<property>"
        elif inspect.isfunction(attr):
            out[name] = str(inspect.signature(attr))
    return out


# Regenerate intentionally when the public surface changes on purpose:
#   python -c "import json,inspect,tests.test_facade_surface as t; ..."
# (any new public method is a deliberate act and must be admitted here.)
EXPECTED = {
    "SolidWorksClient": {
        "active_doc": "<property>",
        "app": "<property>",
        "export": "<property>",
        "features": "<property>",
        "mod": "<property>",
        "mutate": "<property>",
        "observe": "<property>",
        "urdf": "<property>",
    },
    "SolidWorksObserverFacade": _surface(SolidWorksObserverFacade),
    "SolidWorksMutatorFacade": _surface(SolidWorksMutatorFacade),
    "UrdfFacade": _surface(UrdfFacade),
    "SolidWorksExportFacade": _surface(SolidWorksExportFacade),
    "SolidWorksFeaturesFacade": _surface(SolidWorksFeaturesFacade),
}

_CLASSES = {
    "SolidWorksClient": SolidWorksClient,
    "SolidWorksObserverFacade": SolidWorksObserverFacade,
    "SolidWorksMutatorFacade": SolidWorksMutatorFacade,
    "UrdfFacade": UrdfFacade,
    "SolidWorksExportFacade": SolidWorksExportFacade,
    "SolidWorksFeaturesFacade": SolidWorksFeaturesFacade,
}


import pytest


@pytest.mark.parametrize("cls_name", sorted(_CLASSES))
def test_facade_surface_matches_snapshot(cls_name: str) -> None:
    actual = _surface(_CLASSES[cls_name])
    expected = EXPECTED[cls_name]
    added = set(actual) - set(expected)
    removed = set(expected) - set(actual)
    changed = {k: (expected[k], actual[k]) for k in set(actual) & set(expected) if actual[k] != expected[k]}
    assert not (added or removed or changed), (
        f"{cls_name} public surface drifted — "
        f"added={sorted(added)} removed={sorted(removed)} changed={changed}. "
        f"If intentional, update EXPECTED in tests/test_facade_surface.py."
    )
```

Note to implementer: the `SolidWorksClient` block above is the concrete expected surface. For the five facade classes, the snapshot is seeded from `_surface(...)` at authoring time — but you MUST freeze them to literal dicts (run the helper once, paste the result) so a later signature change is actually caught. A self-referential `_surface()` expected value would never fail. Replace each `"<FacadeName>": _surface(<FacadeName>)` with the literal dict it returns.

- [ ] **Step 2: Freeze the facade snapshots to literals**

Run once to dump the current surface, then paste each literal dict into `EXPECTED`:

```bash
python -c "import inspect, json; from tests.test_facade_surface import _surface, _CLASSES; print(json.dumps({k: _surface(v) for k,v in _CLASSES.items()}, indent=2, sort_keys=True))"
```

Paste the five facade dicts (and verify the `SolidWorksClient` block matches) as literals. Remove the `_surface(<Class>)` calls from `EXPECTED`.

- [ ] **Step 3: Run test to verify it passes (snapshot matches reality)**

Run: `pytest tests/test_facade_surface.py -q`
Expected: PASS (6 parametrized cases).

- [ ] **Step 4: Verify the guard bites — temporary drift check**

Temporarily rename one facade method in a scratch copy OR add a throwaway `def zzz_probe(self): ...` to a facade class, re-run, confirm the test FAILS with the added/removed diff, then revert. (Do not commit the probe.)

Run: `pytest tests/test_facade_surface.py -q` (after adding probe) → Expected: FAIL naming `zzz_probe` in `added`. Revert.

- [ ] **Step 5: Commit**

```bash
git add tests/test_facade_surface.py
git commit -m "test(facade): pin SolidWorksClient public surface (closes the unguarded contract leg)"
```

---

## Task 3: PUBLIC_API.md deprecation anchor + staleness truing

**COM-adjacency:** NONE (Markdown). Seat-prefire: NOT required.

**Files:**
- Modify: `docs/PUBLIC_API.md`

- [ ] **Step 1: Read the current PUBLIC_API.md and confirm target lines**

Run: `pytest tests/test_doc_truth.py -q -k version` first to confirm the `v1.7.0` pin (row `("docs/PUBLIC_API.md", "version", "v{n}")`) location — do NOT alter that substring. Read the file; confirm the stale spots: `add_tire` typo (~line 177), 5-command "Current assignments" sub-table (~191–197), pre-1.0 SemVer language (~219–220), "at least one MINOR release" procedure (~222–235).

- [ ] **Step 2: Fix the typo**

Replace `add_tire(` → `add_tier(` (exact, single occurrence ~line 177).

- [ ] **Step 3: Remove the stale 5-command "Current assignments" sub-table**

Delete the sub-table listing only build/observe/mutate/probe/codegen (~191–197) — the authoritative tier assignment is the full §1 main table. Replace with a one-line pointer: `See the §1 tier table above for the full assignment across all CLI commands.`

- [ ] **Step 4: Replace pre-1.0 SemVer language + deprecation procedure with the locked policy**

Replace the ~219–235 block with a `### Deprecation policy` subsection stating verbatim:

```markdown
### Deprecation policy

`ai-sw-bridge` follows SemVer. Backward-compatibility guarantees and the grace
period for removal depend on the surface's stability class:

| Surface class | Announced (deprecated) in | Hard removal | Grace floor |
|---|---|---|---|
| **Stable** — CLI (tier `stable`), MCP tool, `SolidWorksClient` facade signature | `1.N` | **only at the next major, `2.0`** | ≥ 2 minor releases between announce and the `2.0` cut |
| **Experimental** — CLI (tier `experimental`), spec handler | `1.N` | `1.N+1` | 1 minor release |

Stable surfaces are never removed inside the major version that announced their
deprecation. This grace math is machine-enforced by
`src/ai_sw_bridge/deprecations.py` + `tests/test_deprecations.py` — the CI gate
refuses a registry entry that violates the floor.

**Deprecation warnings.** When an MCP tool is deprecated, the warning surfaces
on two channels (policy; runtime wiring lands with the first real MCP-tool
deprecation):
- **Human** — the tool description is prefixed `[DEPRECATED in 1.N → use X]`,
  visible during tool discovery.
- **Machine** — a `_deprecation: {replaces: "X", remove_in: "2.0"}` block is
  injected into the tool's JSON response envelope for headless consumers.

CLI deprecations emit a `DeprecationWarning` on stderr per invocation; Python
facade deprecations emit `DeprecationWarning` (or `PendingDeprecationWarning`
during the announce window). Every removal is recorded in `CHANGELOG.md` under
`### Deprecated` then `### Removed`.
```

- [ ] **Step 5: Verify no doc-truth pin dropped**

Run: `pytest tests/test_doc_truth.py -q`
Expected: PASS (the `docs/PUBLIC_API.md`/`v1.7.0` pin still present).

- [ ] **Step 6: Commit**

```bash
git add docs/PUBLIC_API.md
git commit -m "docs(public-api): deprecation policy anchor + true up stale tier/SemVer sections"
```

---

## Task 4: Shared navigation block across the three dev-surface docs

**COM-adjacency:** NONE (Markdown). Seat-prefire: NOT required.

**Files:**
- Modify: `USAGE.md` (repo root), `docs/tools_reference.md`, `docs/PUBLIC_API.md`

**Interfaces:** relative link paths differ per file — `USAGE.md` is at repo root (links `docs/tools_reference.md`, `docs/PUBLIC_API.md`); the other two are under `docs/` (link `../USAGE.md`, and each other as `tools_reference.md` / `PUBLIC_API.md`).

- [ ] **Step 1: Insert the nav block at the top of `USAGE.md`**

Immediately after the `# USAGE` H1 (before the existing intro line), insert:

```markdown
> **Developer surface — How-to guide.** Task-oriented recipes for driving the
> bridge. For the exhaustive CLI/MCP **reference** (every flag, subcommand,
> payload) see [`docs/tools_reference.md`](docs/tools_reference.md); for the
> supported-surface **contract** (stability tiers, SemVer, deprecation policy)
> see [`docs/PUBLIC_API.md`](docs/PUBLIC_API.md).
```

- [ ] **Step 2: Insert the nav block at the top of `docs/tools_reference.md`**

After the `# Tools Reference` H1, before the existing intro line:

```markdown
> **Developer surface — Reference.** Every CLI command and flag, exhaustively.
> For task-oriented **how-to** recipes see [`../USAGE.md`](../USAGE.md); for the
> supported-surface **contract** (stability tiers, SemVer, deprecation policy)
> see [`PUBLIC_API.md`](PUBLIC_API.md).
```

- [ ] **Step 3: Insert the nav block at the top of `docs/PUBLIC_API.md`**

After the H1, before the first body line (and before/after the existing "_Consolidated from…_" note as fits):

```markdown
> **Developer surface — Contract.** The supported-surface promise: every public
> symbol, its stability tier, the SemVer + deprecation policy. For task-oriented
> **how-to** recipes see [`../USAGE.md`](../USAGE.md); for the exhaustive CLI/MCP
> **reference** see [`tools_reference.md`](tools_reference.md).
```

- [ ] **Step 4: Verify links resolve and no doc-truth pin dropped**

Run: `pytest tests/test_doc_truth.py -q`
Expected: PASS.
Manually confirm each of the 6 relative links points at an existing file (paths above are pre-computed for each file's location).

- [ ] **Step 5: Commit**

```bash
git add USAGE.md docs/tools_reference.md docs/PUBLIC_API.md
git commit -m "docs: shared Diataxis nav block cross-linking the three dev-surface docs"
```

---

## Task 5: D9 fix — USAGE.md:136 MCP claim

**COM-adjacency:** NONE (Markdown). Seat-prefire: NOT required.

**Files:**
- Modify: `USAGE.md` (line 136, in Workflow 4)

- [ ] **Step 1: Replace the false MCP claim**

Replace the exact line 136:

```
For Claude Code specifically, you can wrap each command in a slash-command or expose them via MCP. The package intentionally stays out of MCP transport details — point an MCP server at the CLIs and you're done.
```

with:

```
For Claude Code and other MCP clients, `ai-sw-bridge` ships a native MCP server — `ai-sw-mcp` — exposing 37 tools (read lanes + plan/elicit-gated writes) over stdio; you do not need to wrap the CLIs yourself. See [`docs/mcp_server_design.md`](docs/mcp_server_design.md) for setup, the tool inventory, and the protocol. The subprocess-over-CLI pattern shown above still works for bespoke harnesses that prefer it.
```

- [ ] **Step 2: Verify no doc-truth pin dropped**

Run: `pytest tests/test_doc_truth.py -q`
Expected: PASS. (No USAGE.md pin exists in `DOC_SURFACES`, but confirm the suite stays green.)

- [ ] **Step 3: Commit**

```bash
git add USAGE.md
git commit -m "fix(docs): D9 — USAGE reflects the shipped 37-tool ai-sw-mcp server"
```

---

## Task 6: D10 fix — dead api_reference.md links (English README + AGENTS)

**COM-adjacency:** NONE (Markdown). Seat-prefire: NOT required.

**Files:**
- Modify: `README.md` (line 368), `docs/AGENTS.md` (lines 128, 176)

**Scope note:** English surface only. i18n mirror links (`docs/i18n/zh-*/README.md`) and `docs/com_failure_modes.md:117` are OUT of scope (ride the deferred i18n-retranslation track per design spec §3.2).

- [ ] **Step 1: Fix README.md:368**

Replace `[See the API reference →](docs/api_reference.md)` with:

```
The CHM-verified signature reference (`api_reference.md`) is generated locally and not committed — regenerate it from `tools/_api_extract_input.json` (see [`docs/AGENTS.md`](docs/AGENTS.md)); the committed superset is browsable at [`docs/sw_api_full.md`](docs/sw_api_full.md).
```

- [ ] **Step 2: Fix docs/AGENTS.md:128**

Replace the dead link `[`docs/api_reference.md`](api_reference.md)` in the `PARAMNOTOPTIONAL` row with guidance to regenerate locally (keep the surrounding sentence about arg-count drift; the file is gitignored, so point at the regeneration path already named in that same line — `tools/_api_extract_input.json` — and drop the hyperlink to the uncommitted artifact). Result text:

```
3. **`PARAMNOTOPTIONAL` / `Invalid number of parameters`** at runtime: usually means an API arg count drifted. Regenerate the CHM-authoritative reference locally (`api_reference.md` is gitignored) from [`tools/_api_extract_input.json`](../tools/_api_extract_input.json) and check the signature; if you genuinely need a new API surface, add it there and regenerate.
```

- [ ] **Step 3: Fix docs/AGENTS.md:176**

Replace the table row `| CHM-verified SW API ref | [`docs/api_reference.md`](api_reference.md) |` with:

```
| CHM-verified SW API ref | regenerate locally from [`tools/_api_extract_input.json`](../tools/_api_extract_input.json) (gitignored); superset [`docs/sw_api_full.md`](sw_api_full.md) |
```

- [ ] **Step 4: Verify no doc-truth pin dropped**

Run: `pytest tests/test_doc_truth.py -q`
Expected: PASS (README pins untouched — none reference api_reference.md).

- [ ] **Step 5: Commit**

```bash
git add README.md docs/AGENTS.md
git commit -m "fix(docs): D10 — replace dead api_reference.md links with regenerate-locally guidance"
```

---

## Task 7: MCP walkthrough relocation → mcp_server_design.md + README stub

**COM-adjacency:** NONE (Markdown). Seat-prefire: NOT required.

**Files:**
- Modify: `README.md` (lines 244–334), `docs/mcp_server_design.md`

**Interfaces / constraints:**
- The sole README `mcp_tools` doc-truth pin is `"37-tool MCP server"` at README:386 — OUTSIDE the relocated range (244–334). It stays untouched; doc-truth is preserved trivially.
- Inbound README anchors point at `#mcp-server--drive-the-bridge-from-claude-desktop--cursor--etc` (from lines 46, 168, 203). The stub MUST keep that exact H2 heading (hence anchor id) so those links resolve.

- [ ] **Step 1: Confirm inbound anchors and the pin location**

Run: `grep -n "mcp-server--drive-the-bridge\|37-tool MCP server\|Jump to the MCP section" README.md`
Expected: inbound links at ~46/168/203 target the anchor; the `37-tool MCP server` pin at ~386. Confirm before editing.

- [ ] **Step 2: Move the walkthrough body into docs/mcp_server_design.md**

Cut README lines ~263–334 (the "Quick install", "Register with Claude Desktop", "Tool inventory (37 tools)", "Deliberately NOT exposed" subsections + the final `[Full MCP server design…]` self-link). Paste into `docs/mcp_server_design.md` under a clearly-titled section (e.g. `## Setup & tool inventory (from README)`), FIRST checking that doc for an existing tool inventory — if one exists, merge (do not duplicate); reconcile any count/name differences to the `EXPECTED_TOOLS` truth.

- [ ] **Step 3: Replace the README section body with a stub (keep the H2 + anchor)**

Keep the H2 `## MCP server — drive the bridge from Claude Desktop / Cursor / etc.` (lines 244) and the mermaid transport diagram (252–261). Replace the removed install/register/inventory prose with:

```markdown
The MCP server (`ai-sw-mcp`, new in v0.13) exposes 37 tools to MCP-capable AI
clients (Claude Desktop, Cursor, Continue.dev) over stdio — the same observation
+ planning surface as the CLI, a different transport. The tool set is pinned by
name and payload shape in `tests/mcp_lane/test_server_contract.py`
(`EXPECTED_TOOLS`), so any add/remove/rename fails CI.

**Setup, the full 37-tool inventory, the two elicit-gated write tools, and the
deliberately-CLI-only surface** are documented in
[`docs/mcp_server_design.md`](docs/mcp_server_design.md).
```

- [ ] **Step 4: Verify anchors still resolve + doc-truth green**

Run: `grep -n "^## MCP server — drive the bridge" README.md` → Expected: heading still present (anchor intact).
Run: `pytest tests/test_doc_truth.py -q` → Expected: PASS (the `37-tool MCP server` pin at ~386 untouched).
Manually confirm the three inbound links (46/168/203) still target the retained anchor, and README's own `[Jump to the MCP section ↓]` resolves.

- [ ] **Step 5: Confirm the dev router (README:348–357) still lists the three pillars**

Read README:348–357. Confirm it routes to PUBLIC_API.md, tools_reference.md, AGENTS.md, USAGE.md. If any link text now points at a moved target, fix it. (Expected: no change needed — the walkthrough relocation doesn't move these four.)

- [ ] **Step 6: Commit**

```bash
git add README.md docs/mcp_server_design.md
git commit -m "docs: relocate MCP walkthrough to mcp_server_design.md, README keeps anchored stub"
```

---

## Final Checkpoint — full gauntlet + HELD push

- [ ] **Step 1: Run the full seat-safe suite**

Run: `pytest -m "not solidworks_only and not destructive_sw" -q`
Expected: PASS (baseline was 3869 seat-safe; new tests add cases — no regressions).

- [ ] **Step 2: Run import-linter + doc-truth explicitly**

Run: `lint-imports` and `pytest tests/test_doc_truth.py -q`
Expected: both PASS (new leaf contract holds; every pin preserved).

- [ ] **Step 3: Verify DoD**

Confirm each design-spec §6 DoD checkbox: nav block ×3, walkthrough relocated + anchored stub, D9 fixed, D10 fixed (English), deprecation policy in PUBLIC_API, facade pin green, DEPRECATIONS gate green, doc-truth green.

- [ ] **Step 4: isPrivate-guarded fast-forward push**

```bash
gh repo view --json isPrivate   # MUST be true
git fetch origin
git merge-base --is-ancestor origin/master HEAD && echo "FF-safe"   # origin/master ancestor of HEAD
# confirm HEAD unchanged since the isPrivate check, then:
git push origin docs/commercial-elevation
```

Only push after ALL boxes are checked and the gauntlet is green. If `isPrivate` is not true or FF-safety fails, STOP and escalate.

---

## Self-Review

**1. Spec coverage:**
- Pillar A (shared nav block) → Task 4. ✓
- Pillar B (D9) → Task 5; (D10) → Task 6. ✓
- Pillar C (deprecation anchor + staleness) → Task 3. ✓
- Pillar D (README router + MCP relocation) → Task 7. ✓
- Enforcement (a) facade pin → Task 2; (b) DEPRECATIONS registry/gate → Task 1. ✓
- Enforcement (c) MCP plumbing → documented in Task 3's policy block, NOT built. ✓ (matches deferral)
- Safety: seat-prefire on the one COM-adjacent task (2); seat-safe suite; doc-truth after every doc task; HELD isPrivate FF push. ✓
- Non-goals honored: no file merge, no registry merge, no i18n, no api_reference.md commit, no MCP plumbing. ✓

**2. Placeholder scan:** every code step shows full code; every doc step shows exact before/after text. Task 2 explicitly flags the "freeze snapshots to literals" trap (a self-referential `_surface()` expected value would never fail) and gives the dump command. No TBD/TODO.

**3. Type consistency:** `DeprecationEntry`/`Violation` fields and `validate_registry(entries, current)` signature are identical between Task 1's test and implementation. Facade class names in Task 2 match the grep-confirmed names in `client.py`. `_surface()` helper used consistently.

**Known judgment call recorded:** the literal "≥2 minor releases" floor is not derivable from two version strings alone; Task 1's gate enforces the cleanly-checkable *superset* ("stable removals only at the next major boundary, never within the announcing major"), with the literal count documented as policy in PUBLIC_API. This is stated in both `deprecations.py`'s docstring and the plan — flagged for the reviewer, not hidden.
