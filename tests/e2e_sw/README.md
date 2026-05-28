# End-to-End SW Test Suite

Unified end-to-end tests exercising the full v0.13 stack against a live
SOLIDWORKS session: spec → CLI/MCP → COM → SW → manifest → checkpoint.

## When to run

- **Before every release.** Wave 5-style audit; gates the release.
- **After any change that touches** `spec/`, `mcp/`, `observe.py`,
  `com/`, `checkpoint/`, or `errors/`.
- **Not in CI** (no SW available there). All tests are gated with
  `@pytest.mark.solidworks_only`; CI auto-skips them.

## Prerequisites

1. **SOLIDWORKS running.** Any version 2024 SP1 or newer (per
   `sw_com.py` `SW_VERSION_VERIFIED`). No specific document needs to
   be open — tests create their own documents.
2. **pywin32 installed.** `pip install -e ".[dev,mcp]"` from the
   repo root.
3. **Sample part for read-only observe tests.** Tests that need a
   pre-existing part open it themselves from `examples/` if absent.
4. **Empty `.checkpoints/` directory.** Tests that exercise the
   checkpoint store create + clean their own DBs.

## How to run

```powershell
# Full E2E suite
pytest -m solidworks_only tests/e2e_sw/ -v

# One area at a time
pytest -m solidworks_only tests/e2e_sw/test_e2e_build.py -v
pytest -m solidworks_only tests/e2e_sw/test_e2e_mcp_lifecycle.py -v
pytest -m solidworks_only tests/e2e_sw/test_e2e_observe.py -v
```

If SW is not running, tests skip with `"live SOLIDWORKS session not
available"` (auto-skip wired in `tests/conftest.py`).

## What the suite covers

| File | Stack coverage |
|---|---|
| `test_e2e_build.py` | spec → validator → builder → COM → SW → manifest. Verifies a known-good spec creates the expected geometry and the BuildResult payload matches the golden shape. |
| `test_e2e_observe.py` | Each `observe.sw_*` function called against a real part. Verifies the JSON payload shape AND value ranges (bbox dimensions, feature count, etc.). |
| `test_e2e_mcp_lifecycle.py` | `ai-sw-mcp` subprocess + JSON-RPC. `initialize` → `tools/list` → `tools/call` for several representative tools. End-to-end wire format verification against live SW. |
| `test_e2e_checkpoint.py` | Build with `--checkpoint`, query via `sw_history_part`, diff via `sw_history_diff`, info via `sw_checkpoint_info`. |
| `test_e2e_encryption.py` | Encrypted checkpoint round-trip: `sw_build --checkpoint-encrypt` → `sw_checkpoint_info` reports encrypted; `sw_history_part` returns `fernet_v1:`-wrapped ciphertext. |
| `test_e2e_death_recovery.py` | Kill SW mid-session → next call surfaces `dispatch failed` error → `sw_reconnect` clears cache → next call recovers against fresh SW. |

## Design principles

- **One canonical part per test** — tests create their own document so
  prior runs don't poison state. After-test cleanup is opportunistic
  (SW typically prompts to save on close; tests close without saving).
- **No fixtures with side effects** — each test owns its setup. Fixtures
  only carry pure helpers (paths, runtime builders).
- **JSON-shape assertions over JSON-value assertions** where SW state
  is non-deterministic (timestamps, dispatch IDs). Shape walker
  matches W5.5 fixtures' format.
- **Live-SW state is non-deterministic.** Tests tolerate any active
  document state on entry; they DO NOT assume a clean SW.
- **The audit is the test.** If a Wave-5-style audit finds an
  uncaught bug in a future release, the right action is to add a
  test here that would have caught it.

## What this suite does NOT cover

- **Headless / CI SOLIDWORKS.** SW does not run headless reliably;
  the suite is operator-driven.
- **Long soak / load tests.** A single E2E run is ~30-60 seconds;
  longer reliability tests would live in a separate directory.
- **Cross-version compatibility.** Tests run against whatever SW
  version is installed; `sw_com.py` enforces the verified-minimum
  via `_check_sw_version`.
- **GUI client integration (Claude Desktop, Cursor).** Those need
  the actual GUI client and a human; tracked separately.

## Failure triage

When a test fails:

1. **Check SW is responsive.** Click in the SW window; if frozen,
   the test's COM call may have triggered a modal dialog. Close
   the dialog and retry.
2. **Read the assertion message.** Live-SW failures are typically
   either (a) wrong shape (real bug, file an issue) or (b) wrong
   value range (canonical part state drifted, update the fixture).
3. **Capture state.** If the failure is reproducible, save the
   active SW part to `tests/e2e_sw/fixtures/<test-name>.SLDPRT` and
   commit alongside the test fix.
4. **Compare to Wave 5 audit reports** in commit messages
   (`f9dde03`, `4a5f849`, `d91676e`, `5069866`) for prior issue
   patterns.
