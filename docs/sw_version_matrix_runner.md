# SW Version Test Matrix — Runner Guide

## What this is

`tests/version_matrix/` provides a parametrise-based harness so seat tests can
run against two SOLIDWORKS major versions (N and N-1) in one pytest invocation.
The scaffold was introduced in W58 to address D-4 (the one open cross-cutting
recommendation in `central_idea_vs_implementation_audit.md`).

**Revision map** (from `src/ai_sw_bridge/spec/_version_resolver.py`):

| Revision string | Major | SW release |
|---|---|---|
| `32.x.x` | 32 | SW 2024 (the proven build; usual **N** in dev) |
| `33.x.x` | 33 | SW 2025 (adjacent target; usual **N-1** in the matrix) |

---

## Normal dev / CI (N only)

Nothing to configure.  Tests tagged `sw_version_n1` are auto-skipped with a
clear reason:

```
SKIPPED — N-1 SW seat not configured — set AI_SW_BRIDGE_N1_REVISION=<major> to enable;
           see docs/sw_version_matrix_runner.md
```

The N-variant of every parametrised test runs normally alongside the rest of
the suite.

---

## Enabling the N-1 run (W0 versioned seat)

### Prerequisites

1. A second SOLIDWORKS installation (e.g. SW 2025, major revision **33**) is
   present on the machine.
2. The N-1 SOLIDWORKS process is running and visible to the COM Running Object
   Table (ROT).  `sw_com.get_sw_app()` must be able to attach to it.

### Steps

```powershell
# 1. Launch the N-1 SW process (SW 2025) — COM ProgID includes the major:
#    SldWorks.Application.33 for SW 2025.
#    The process must be in the foreground before the tests run.

# 2. Set the env var so the skip wiring lifts:
$env:AI_SW_BRIDGE_N1_REVISION = "33"

# 3. Run the version matrix suite (isolated from the rest to avoid SEH risk):
pytest -m sw_version_n1 tests/version_matrix/ -v

# 4. Or run the full suite; N-1 items run alongside N items:
pytest -n auto tests/
```

### How tests select the right seat

Tests that use `SW_VERSION_MATRIX` receive `sw_version` as `"N"` or `"N-1"`.
They are responsible for wiring the appropriate COM target.  A typical pattern:

```python
@pytest.mark.parametrize("sw_version", SW_VERSION_MATRIX)
@pytest.mark.solidworks_only
def test_feature_on_both_versions(sw_version, live_runtime):
    if sw_version == "N-1":
        # Re-attach sw_com to the N-1 process before exercising the handler.
        # (Implementation detail: future fixture or helper — not yet wired.)
        pytest.skip("N-1 COM re-attachment fixture not yet implemented")
    # ... exercise the handler normally against the N seat ...
```

The fixture-level N-1 re-attachment is the next step after the scaffold lands
and is gated on the first real seat-gated N/N-1 test being authored.

---

## Marker reference

| Marker | Registered in | Effect |
|---|---|---|
| `sw_version_n1` | `tests/version_matrix/conftest.py` | Skipped unless `AI_SW_BRIDGE_N1_REVISION` is set |
| `solidworks_only` | `tests/conftest.py` | Skipped unless a live SW session is detected |

Both markers combine: an N-1 seat test should carry both `solidworks_only`
(needs any SW session) and the implicit `sw_version_n1` mark from
`pytest.param("N-1", marks=pytest.mark.sw_version_n1)`.

---

## Backlog reference

- Audit item: **D-4** (`central_idea_vs_implementation_audit.md` §5 #24)
- Burndown entry: `BACKLOG_BURNDOWN.md` §A #24 — `OFFLINE`, Gate R5
- Wave: **W58**
