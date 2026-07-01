# Phase 1 — Operator Product & README Front Door · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A non-coder SOLIDWORKS operator installs via one path (`pipx install ai-sw-bridge[mcp]`), runs `ai-sw-doctor` to get a pass/fail verdict, optionally auto-registers the MCP server with `ai-sw-doctor --register`, and reaches their first part from inside an AI chat — with the README rewritten as a persona-router whose spine is operator content.

**Architecture:** Additive only — no engine/COM behavior change. One new leaf CLI (`cli/doctor.py`) wraps the existing `probe()` plus static environment checks (all COM-inert at import); one new pure module (`mcp/registration.py`) does table-driven, idempotent, backed-up registration of the MCP server into an AI-client config file. Docs (README, ONBOARDING→Operator Guide) are restructured. A CI smoke stage installs the *built wheel* (not `-e`) and asserts the packaged product surface. Everything binds to the Phase-0-frozen contracts (script names, exit codes, MCP tool set).

**Tech Stack:** Python 3.10+ (stdlib `argparse`/`json`/`shutil`/`pathlib`/`datetime`/`struct`), pywin32 (already a dep), `mcp>=1.0` (via `[mcp]` extra), pytest, GitHub Actions (`windows-2025`).

## Global Constraints

Every task's requirements implicitly include this section. Values are copied verbatim from the governing spec (`docs/superpowers/specs/2026-07-01-commercial-google-standard-elevation-design.md`, §8) and the Phase-0 guardrails now on `master`.

- **Branch:** all work on `docs/commercial-elevation` (current tip after the Phase 0 FF). Never commit to `feat/w67-phase3`. Do NOT push; the controller performs the single `isPrivate`-guarded FF push at phase end.
- **Distribution decision (settled):** `pipx install ai-sw-bridge[mcp]`. Windows installer is **deferred to Phase 4** — do not build an `.exe`/`.msi`/PyInstaller/Inno artifact here.
- **`ai-sw-doctor` scope (settled — Option C):** read-only diagnostic **by default** (§8.2); `ai-sw-doctor --register` is the **opt-in** automated path (§8.3).
- **`--register` client scope (settled):** **Claude Desktop only** for Phase 1, but implemented **table-driven** so adding a client later is a new table row (a config path + a servers key), not a rewrite.
- **`--register` safety contract (settled, mandatory):** (1) **Idempotent** — running it twice must not duplicate or corrupt the entry; (2) **Backup** — a timestamped backup of the target config is written before any mutation; (3) **Transparent** — it prints the exact file path being modified and the injected entry/diff.
- **No autonomous SOLIDWORKS write** invariant is preserved (§8.4). `--register` writes only to the *AI-client config file*, never to a SW model, and only when the operator passes `--register`.
- **COM-inert at import:** every new module must perform zero COM dispatch at import time (no `Dispatch`/`get_sw_app`/`gencache` at module scope). COM happens only inside called functions. This is load-bearing — the doc-truth and conformance tests import every `cli.*` module, and a live operator seat must never be disturbed by a test import. Mirror `cli/probe.py`.
- **Two-stream contract (UIUX §2.1):** stdout carries the JSON envelope; human/log text goes to stderr. `tools/two_stream_lint.py src/` runs in CI. Reuse `cli/streams.py` (`add_quiet_flag`/`apply_quiet`).
- **Exit codes:** the shared convention is `0` = ok, `1` = `ok:false`. `ai-sw-doctor` uses **`0` (all checks pass) / `1` (one or more checks failed)**, consistent with `ai-sw-probe`. Bad CLI args → argparse's default `2`. Do NOT invent build-style codes (3–7 are `ai-sw-build`-specific).
- **Stability tier:** `ai-sw-doctor` is **`experimental`** (new, may change) — consistent with `ai-sw-probe`.
- **Import style:** match the surrounding `cli/` package (relative intra-package imports, e.g. `from ..sw_com import`, `from .stability import`). The "absolute-for-new-modules" rubric item (spec §7.1 / A.1) shipped **no flake8 gate** in Phase 0, so matching siblings is the consistent, green choice; note it in the task.
- **Formatting/typing:** `black==25.12.0` (`target-version = ["py310"]`); `flake8 src/` zero; `mypy --config-file mypy.ini src/ai_sw_bridge` zero. Fully type-annotate all new functions (`-> int`, `-> dict[str, Any]`, etc.) even though the mypy strict override currently scopes only `features.*`.
- **Doc-truth is a forcing function:** `tests/test_doc_truth.py` derives `cli_commands` from `pyproject.toml`. The moment `ai-sw-doctor` is added to `[project.scripts]`, the derived count becomes **22** and every pinned doc substring must state 22 or the suite goes red. Update them in the same task.
- **Conventional commits**, no co-author trailers, no `--no-verify`.
- **Live-seat safety:** SOLIDWORKS may be running on the dev machine. Never run `tests/e2e_sw/` or `tests/mcp_lane/` bodies. Run the seat-safe suite: `pytest -m "not solidworks_only and not destructive_sw"`. Before any task that imports MCP/COM-adjacent surfaces for counting, the controller runs the `seat-prefire-review` tripwire.

---

## File Structure

**New files**
- `src/ai_sw_bridge/cli/doctor.py` — the `ai-sw-doctor` leaf CLI. `run_doctor() -> dict` (static checks + `probe()` + `registration.detect()`), `main() -> int` (`@cli_stability("experimental")`, `--register`, `--client`, `--quiet`).
- `src/ai_sw_bridge/mcp/registration.py` — pure, table-driven MCP-client registrar. `detect(...)`, `register(...)`, `CLIENTS` table, `SERVER_NAME`. Stdlib-only; COM-inert.
- `tests/cli/test_doctor.py` — unit tests for `run_doctor()` + `main()` (COM seams mocked; no live seat).
- `tests/mcp_lane/test_registration.py` — unit tests for the registrar (tmp_path config files; idempotency/backup/malformed-JSON). *Marker note:* this is a **pure** unit test (no `ComExecutor`, no server) — it must NOT carry `mcp_lane_live`/`destructive_sw`; it runs in the normal seat-safe suite. Placed under `tests/mcp_lane/` only for locality; confirm it has no live marker.
- `docs/operator_guide.md` — the canonical Operator Guide (merges fixed ONBOARDING + limitations + capabilities framing for a non-coding SW veteran).

**Modified files**
- `pyproject.toml` — add `ai-sw-doctor = "ai_sw_bridge.cli.doctor:main"` to `[project.scripts]`.
- `docs/PUBLIC_API.md` — §1 tier table (+`ai-sw-doctor` under experimental); §5 script-freeze (21→22 `ai-sw-*`, add name).
- `README.md` — persona-router rewrite (§8.5); count `21`→`22 CLI commands`; keep every doc-truth-pinned substring.
- `docs/ONBOARDING.md` — count `21`→`22`; add `ai-sw-doctor` row; then fold into `operator_guide.md` (leave a stub/redirect that still satisfies the doc-truth pins, OR move the pinned substrings — see Task D).
- `src/ai_sw_bridge/cli/probe.py` — operator-legible two-branch verdict on failure (§8.4).
- `src/ai_sw_bridge/cli/build.py` — reword the seat `[y/N]` banner as reassurance (§8.4); update its guard test.
- `tests/cli/test_entrypoints_smoke.py` — docstring/assertion 22→23 total console scripts.
- `tests/cli/test_build_seat_gate.py` — update banner assertions to the reworded copy.
- `.github/workflows/ci.yml` — add a packaged-wheel operator-install smoke stage (§8.6).

**Task → deliverable map**
- **Task A:** `ai-sw-doctor` read-only diagnostic + full ripple (green everywhere).
- **Task B:** `--register` table-driven registrar + safety contract.
- **Task C:** operator error/safety UX (probe verdict + seat banner).
- **Task D:** README persona-router + Operator Guide merge.
- **Task E:** CI packaged-install smoke stage.

---

### Task A: `ai-sw-doctor` read-only diagnostic (+ doc/contract ripple)

**Files:**
- Create: `src/ai_sw_bridge/cli/doctor.py`
- Create: `tests/cli/test_doctor.py`
- Modify: `pyproject.toml` (`[project.scripts]`)
- Modify: `docs/PUBLIC_API.md` (§1 tier table, §5 script freeze)
- Modify: `README.md` (CLI-count substring 21→22)
- Modify: `docs/ONBOARDING.md` (count 21→22 + `ai-sw-doctor` table row)
- Modify: `tests/cli/test_entrypoints_smoke.py` (22→23)

**Interfaces:**
- Consumes: `cli/probe.py::probe() -> dict[str, Any]`; `cli/stability.py::cli_stability`, `add_tier`; `cli/streams.py::add_quiet_flag`, `apply_quiet`. `mcp/registration.py::detect` is consumed **only after Task B lands** — in Task A the `mcp_registration` check is implemented against a tiny local shim (see Step 3) and rewired to `registration.detect()` in Task B Step 6. (This keeps Task A independently green without a forward dependency.)
- Produces: `run_doctor(*, run_probe: bool = True) -> dict[str, Any]` returning `{"ok": bool, "checks": list[dict], "next_steps": list[str]}`; each check is `{"name": str, "ok": bool, "detail": str, "fix": str | None}`. `main() -> int` (exit 0 iff `ok`).

- [ ] **Step 1: Write the failing test for `run_doctor()` shape + bitness/pywin32 checks**

Create `tests/cli/test_doctor.py`:

```python
"""Unit tests for ai-sw-doctor: static env checks + probe/registration wrap.

All COM/probe seams are patched on the doctor module namespace so no live
SOLIDWORKS seat is ever touched (mirrors the project's monkeypatch-seam
convention). run_doctor() is a pure aggregator over check functions.
"""

from __future__ import annotations

import ai_sw_bridge.cli.doctor as doctor


def test_run_doctor_reports_all_checks_and_overall_ok(monkeypatch) -> None:
    # Force every check green.
    monkeypatch.setattr(doctor, "_check_python_bitness", lambda: _ok("python_bitness"))
    monkeypatch.setattr(doctor, "_check_pywin32", lambda: _ok("pywin32"))
    monkeypatch.setattr(doctor, "_check_scripts_on_path", lambda: _ok("scripts_on_path"))
    monkeypatch.setattr(doctor, "_check_solidworks_seat", lambda: _ok("solidworks_seat"))
    monkeypatch.setattr(doctor, "_check_mcp_registration", lambda: _ok("mcp_registration"))

    result = doctor.run_doctor()

    assert result["ok"] is True
    names = [c["name"] for c in result["checks"]]
    assert names == [
        "python_bitness",
        "pywin32",
        "scripts_on_path",
        "solidworks_seat",
        "mcp_registration",
    ]
    assert result["next_steps"] == []


def test_run_doctor_overall_false_when_any_check_fails(monkeypatch) -> None:
    monkeypatch.setattr(doctor, "_check_python_bitness", lambda: _ok("python_bitness"))
    monkeypatch.setattr(doctor, "_check_pywin32", lambda: _ok("pywin32"))
    monkeypatch.setattr(doctor, "_check_scripts_on_path", lambda: _ok("scripts_on_path"))
    monkeypatch.setattr(
        doctor,
        "_check_solidworks_seat",
        lambda: {"name": "solidworks_seat", "ok": False, "detail": "no seat",
                 "fix": "Open SOLIDWORKS, then re-run ai-sw-doctor."},
    )
    monkeypatch.setattr(doctor, "_check_mcp_registration", lambda: _ok("mcp_registration"))

    result = doctor.run_doctor()

    assert result["ok"] is False
    # The failing check's fix is surfaced in next_steps.
    assert any("Open SOLIDWORKS" in step for step in result["next_steps"])


def _ok(name: str) -> dict:
    return {"name": name, "ok": True, "detail": "fine", "fix": None}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/cli/test_doctor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ai_sw_bridge.cli.doctor'`.

- [ ] **Step 3: Write `src/ai_sw_bridge/cli/doctor.py`**

```python
"""ai-sw-doctor: operator preflight diagnostic for ai-sw-bridge.

The *entire* terminal vocabulary a chat-first operator needs. Runs a
handful of environment checks and prints operator-legible next steps. It
is COM/engine-inert at import: the only COM touch is the reused probe(),
called at runtime inside _check_solidworks_seat().

Read-only by default (spec §8.2). `--register` (spec §8.3) is the opt-in
automated MCP-client registration path, wired in Task B.
"""

from __future__ import annotations

import argparse
import json
import shutil
import struct
import sys
from typing import Any

from .probe import probe
from .stability import add_tier, cli_stability
from .streams import add_quiet_flag, apply_quiet

Check = dict[str, Any]


def _check(name: str, ok: bool, detail: str, fix: str | None = None) -> Check:
    return {"name": name, "ok": ok, "detail": detail, "fix": fix}


def _check_python_bitness() -> Check:
    bits = struct.calcsize("P") * 8
    if bits == 64:
        return _check("python_bitness", True, "Python is 64-bit.")
    return _check(
        "python_bitness",
        False,
        f"Python is {bits}-bit; SOLIDWORKS is 64-bit.",
        "Uninstall this Python and install 64-bit Python 3.x "
        "(python.org, tick 'Add to PATH'), then reinstall ai-sw-bridge.",
    )


def _check_pywin32() -> Check:
    # Importing win32com/pythoncom is COM-inert (no Dispatch). A failure
    # here is the classic 'pywin32 post-install never ran' footgun.
    try:
        import pythoncom  # noqa: F401
        import win32com.client  # noqa: F401
    except Exception as exc:  # noqa: BLE001 — report, don't crash
        return _check(
            "pywin32",
            False,
            f"pywin32 did not import: {exc!r}",
            "Run: python -m pywin32_postinstall -install  "
            "(inside the environment ai-sw-bridge is installed in).",
        )
    return _check("pywin32", True, "pywin32 imports cleanly.")


def _check_scripts_on_path() -> Check:
    if shutil.which("ai-sw-probe"):
        return _check("scripts_on_path", True, "ai-sw-* scripts are on PATH.")
    return _check(
        "scripts_on_path",
        False,
        "ai-sw-* scripts are not on PATH.",
        "Run: pipx ensurepath  then close and reopen your terminal.",
    )


def _check_solidworks_seat() -> Check:
    result = probe()
    if result.get("ok"):
        rev = result.get("sw_revision")
        return _check("solidworks_seat", True, f"Connected to SOLIDWORKS {rev}.")
    return _check(
        "solidworks_seat",
        False,
        str(result.get("error") or "probe failed"),
        "Is SOLIDWORKS open? Open it and re-run ai-sw-doctor. If it is "
        "already open, your Python may be 32-bit — see the python_bitness fix.",
    )


def _check_mcp_registration() -> Check:
    # Task A local shim: report 'unknown' as a benign pass so the read-only
    # doctor is green pre-Task-B. Task B Step 6 replaces this body with a call
    # to mcp.registration.detect('claude_desktop').
    return _check(
        "mcp_registration",
        True,
        "MCP registration check not yet wired (see `ai-sw-doctor --register`).",
    )


_CHECKS = (
    _check_python_bitness,
    _check_pywin32,
    _check_scripts_on_path,
    _check_solidworks_seat,
    _check_mcp_registration,
)


def run_doctor(*, run_probe: bool = True) -> dict[str, Any]:
    """Run every environment check and aggregate an operator verdict.

    ``run_probe=False`` skips the live-seat check (used by the packaged
    no-SW CI smoke, which asserts graceful failure, and by unit tests).
    """
    checks: list[Check] = []
    for fn in _CHECKS:
        if fn is _check_solidworks_seat and not run_probe:
            checks.append(
                _check("solidworks_seat", False, "skipped (--no-seat)", None)
            )
            continue
        checks.append(fn())
    ok = all(c["ok"] for c in checks)
    next_steps = [c["fix"] for c in checks if not c["ok"] and c["fix"]]
    return {"ok": ok, "checks": checks, "next_steps": next_steps}


@cli_stability("experimental")
def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ai-sw-doctor",
        description=(
            "Preflight check for ai-sw-bridge: verifies 64-bit Python, "
            "pywin32, PATH, the SOLIDWORKS seat, and (optionally) registers "
            "the MCP server with your AI client. Run this first if anything "
            "misbehaves."
        ),
    )
    add_tier(parser, "experimental")
    add_quiet_flag(parser)
    parser.add_argument(
        "--no-seat",
        action="store_true",
        help="Skip the live-SOLIDWORKS check (env-only diagnosis).",
    )
    # --register / --client are declared here but only wired in Task B.
    parser.add_argument(
        "--register",
        action="store_true",
        help="Register the ai-sw-bridge MCP server with your AI client "
        "(Claude Desktop). Writes a timestamped backup first.",
    )
    parser.add_argument(
        "--client",
        default="claude_desktop",
        help="AI client to target for --register (default: claude_desktop).",
    )
    args = parser.parse_args()
    apply_quiet(args)

    if args.register:
        return _do_register(args.client)

    result = run_doctor(run_probe=not args.no_seat)
    print(json.dumps(result, indent=2, default=str))
    _print_human_summary(result)
    return 0 if result["ok"] else 1


def _print_human_summary(result: dict[str, Any]) -> None:
    for c in result["checks"]:
        mark = "OK " if c["ok"] else "FAIL"
        print(f"[{mark}] {c['name']}: {c['detail']}", file=sys.stderr)
    for step in result["next_steps"]:
        print(f"  -> {step}", file=sys.stderr)


def _do_register(client: str) -> int:
    # Task A placeholder — replaced wholesale in Task B Step 5.
    print(json.dumps({"ok": False, "error": "not yet implemented"}, indent=2))
    print("--register is not available yet.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the doctor unit test to verify it passes**

Run: `pytest tests/cli/test_doctor.py -v`
Expected: PASS (2 tests). `_check_mcp_registration` shim returns ok, so a fully-green `run_doctor` is green.

- [ ] **Step 5: Register the console script and fix every pinned doc surface**

In `pyproject.toml` `[project.scripts]`, add after the `ai-sw-urdf` line and before `ai-sw-mcp`:

```toml
ai-sw-doctor     = "ai_sw_bridge.cli.doctor:main"
```

In `docs/PUBLIC_API.md` §1 tier table, append `ai-sw-doctor` to the **experimental** row's command list. In §5 "Console-script names", change "The 21 `ai-sw-*` entry points" to "The 22 `ai-sw-*` entry points" and add `` `ai-sw-doctor` `` to the parenthesized list.

In `README.md`, find the doc-truth-pinned substring `**21 CLI commands` and change `21`→`22` (the derived count is now 22). *Do not touch any other pinned substring.*

In `docs/ONBOARDING.md`: change `All 21 CLI commands` → `All 22 CLI commands` (line ~142 heading) and add a table row so `test_onboarding_lists_every_cli_command` passes:

```markdown
| `ai-sw-doctor` | Operator preflight: Python/pywin32/PATH/seat + MCP registration | Optional |
```

In `tests/cli/test_entrypoints_smoke.py`: update the docstring "22 `[project.scripts]`" → "23", and the assertion `>= 22` → `>= 23` (21 cli + doctor + mcp = 23 total console scripts). Doctor is auto-discovered by that test, so it will also get a `--help`-exits-0 check for free.

- [ ] **Step 6: Run the full ripple-affected test set to verify green**

Run: `pytest tests/cli/test_doctor.py tests/test_doc_truth.py tests/test_extension_conformance.py tests/cli/test_entrypoints_smoke.py tests/cli/test_quiet_flag.py -v`
Expected: PASS. Specifically `test_doc_states_derived_value[README.md-cli_commands-...]` and the ONBOARDING rows now derive 22 and find it; `test_every_cli_script_has_a_stability_tier` imports `ai_sw_bridge.cli.doctor` and finds its tier; `test_onboarding_lists_every_cli_command` finds the new row; the smoke test `--help`-checks `ai-sw-doctor` at exit 0.

- [ ] **Step 7: Lint/format/type + commit**

Run: `black --check src/ai_sw_bridge/cli/doctor.py tests/cli/test_doctor.py && flake8 src/ai_sw_bridge/cli/doctor.py && python -m mypy --config-file mypy.ini src/ai_sw_bridge && python tools/two_stream_lint.py src/`
Expected: all clean (two-stream: doctor prints JSON to stdout, human text to stderr).

```bash
git add src/ai_sw_bridge/cli/doctor.py tests/cli/test_doctor.py pyproject.toml docs/PUBLIC_API.md README.md docs/ONBOARDING.md tests/cli/test_entrypoints_smoke.py
git commit -m "feat(cli): add ai-sw-doctor operator preflight diagnostic"
```

---

### Task B: `ai-sw-doctor --register` — table-driven MCP registrar

**Files:**
- Create: `src/ai_sw_bridge/mcp/registration.py`
- Create: `tests/mcp_lane/test_registration.py`
- Modify: `src/ai_sw_bridge/cli/doctor.py` (`_do_register`, `_check_mcp_registration`)
- Modify: `tests/cli/test_doctor.py` (register-path test)

**Interfaces:**
- Consumes: nothing beyond stdlib (`json`, `os`, `shutil`, `pathlib`, `datetime`, `copy`).
- Produces:
  - `SERVER_NAME = "ai-sw-bridge"`
  - `resolve_command() -> str` — absolute path to the `ai-sw-mcp` shim via `shutil.which`, falling back to the bare name.
  - `desired_entry(command: str | None = None) -> dict` — `{"command": <cmd>, "args": []}`.
  - `client_config_path(client: str) -> Path` — from the `CLIENTS` table.
  - `detect(client: str = "claude_desktop", *, config_path: Path | None = None) -> dict` — read-only; `{"client", "config_path", "present": bool, "matches": bool, "current": dict | None}`.
  - `register(client: str = "claude_desktop", *, config_path: Path | None = None, command: str | None = None) -> dict` — idempotent merge; `{"ok", "client", "config_path", "changed": bool, "backup_path": str | None, "entry": dict, "servers_before": dict, "servers_after": dict}`.

- [ ] **Step 1: Write the failing registrar tests**

Create `tests/mcp_lane/test_registration.py`:

```python
"""Unit tests for the table-driven MCP-client registrar.

Pure JSON/file logic against tmp_path — no ComExecutor, no server, no COM.
Runs in the normal seat-safe suite (NOT an mcp_lane_live/destructive test).
"""

from __future__ import annotations

import json

from ai_sw_bridge.mcp import registration as reg


def test_register_creates_file_and_entry_no_backup(tmp_path) -> None:
    cfg = tmp_path / "claude_desktop_config.json"  # does not exist yet
    out = reg.register(config_path=cfg, command="C:/pipx/ai-sw-mcp.exe")

    assert out["ok"] is True
    assert out["changed"] is True
    assert out["backup_path"] is None  # nothing to back up
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["mcpServers"][reg.SERVER_NAME] == {
        "command": "C:/pipx/ai-sw-mcp.exe",
        "args": [],
    }


def test_register_is_idempotent(tmp_path) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    reg.register(config_path=cfg, command="X")
    backups_after_first = list(tmp_path.glob("*.bak-*"))

    out2 = reg.register(config_path=cfg, command="X")

    assert out2["changed"] is False
    assert out2["backup_path"] is None
    # No second backup created; entry not duplicated.
    assert list(tmp_path.glob("*.bak-*")) == backups_after_first


def test_register_preserves_other_servers_and_backs_up(tmp_path) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(
        json.dumps({"mcpServers": {"other": {"command": "keep"}}}),
        encoding="utf-8",
    )

    out = reg.register(config_path=cfg, command="Y")

    assert out["changed"] is True
    assert out["backup_path"] is not None  # existing file backed up
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["mcpServers"]["other"] == {"command": "keep"}
    assert data["mcpServers"][reg.SERVER_NAME]["command"] == "Y"
    backup = json.loads((tmp_path / out["backup_path"].split("/")[-1]).read_text())
    assert "ai-sw-bridge" not in backup["mcpServers"]  # backup is pre-mutation


def test_register_on_existing_matching_entry_is_noop(tmp_path) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    reg.register(config_path=cfg, command="Z")
    out = reg.register(config_path=cfg, command="Z")
    assert out["changed"] is False


def test_register_malformed_json_backs_up_and_errors(tmp_path) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text("{ this is not json", encoding="utf-8")

    out = reg.register(config_path=cfg, command="Q")

    assert out["ok"] is False
    assert out["backup_path"] is not None  # corrupt file preserved before touch
    assert "error" in out
    # Original bytes untouched (we did not clobber the operator's file).
    assert cfg.read_text(encoding="utf-8") == "{ this is not json"


def test_detect_absent_then_present(tmp_path) -> None:
    cfg = tmp_path / "claude_desktop_config.json"
    d0 = reg.detect(config_path=cfg)
    assert d0["present"] is False and d0["matches"] is False

    reg.register(config_path=cfg, command="C")
    d1 = reg.detect(config_path=cfg, command="C")
    assert d1["present"] is True and d1["matches"] is True
```

*Note on the `command` kwarg in `detect`:* `matches` compares the stored entry against `desired_entry(command)`; tests pass an explicit `command` so the comparison is deterministic without resolving PATH.

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/mcp_lane/test_registration.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ai_sw_bridge.mcp.registration'`.

- [ ] **Step 3: Write `src/ai_sw_bridge/mcp/registration.py`**

```python
"""Table-driven, idempotent registration of the ai-sw-bridge MCP server
into an AI client's config file.

Phase 1 targets Claude Desktop only, but every client is a row in CLIENTS
(config path + servers key), so adding Cursor/Codex later is a new row —
not a rewrite (spec §8.3, settled).

Safety contract (settled, mandatory):
  1. Idempotent  — re-running never duplicates or corrupts the entry.
  2. Backup      — a timestamped copy is written before any mutation.
  3. Transparent — caller receives the config path + the injected entry
                   and the before/after server maps to print.

Pure stdlib; COM-inert; no SOLIDWORKS write ever.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

SERVER_NAME = "ai-sw-bridge"
MCP_LAUNCH_SCRIPT = "ai-sw-mcp"


@dataclass(frozen=True)
class ClientSpec:
    label: str
    servers_key: str
    path_factory: Callable[[], Path]


def _claude_desktop_path() -> Path:
    appdata = os.environ.get("APPDATA", "")
    return Path(appdata) / "Claude" / "claude_desktop_config.json"


CLIENTS: dict[str, ClientSpec] = {
    "claude_desktop": ClientSpec(
        label="Claude Desktop",
        servers_key="mcpServers",
        path_factory=_claude_desktop_path,
    ),
}


def client_config_path(client: str) -> Path:
    try:
        return CLIENTS[client].path_factory()
    except KeyError:
        raise ValueError(
            f"unknown client {client!r}; known: {sorted(CLIENTS)}"
        ) from None


def resolve_command() -> str:
    """Absolute path to the ai-sw-mcp shim (Claude Desktop does not inherit
    the full user PATH, so a bare name can fail to launch)."""
    return shutil.which(MCP_LAUNCH_SCRIPT) or MCP_LAUNCH_SCRIPT


def desired_entry(command: str | None = None) -> dict[str, Any]:
    return {"command": command or resolve_command(), "args": []}


def _servers_key(client: str) -> str:
    return CLIENTS[client].servers_key


def _load(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    return json.loads(config_path.read_text(encoding="utf-8"))


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _backup(config_path: Path) -> str | None:
    if not config_path.exists():
        return None
    backup = config_path.with_name(f"{config_path.name}.bak-{_timestamp()}")
    shutil.copy2(config_path, backup)
    return str(backup)


def detect(
    client: str = "claude_desktop",
    *,
    config_path: Path | None = None,
    command: str | None = None,
) -> dict[str, Any]:
    """Read-only: is our server present, and does it match the desired entry?"""
    path = config_path or client_config_path(client)
    key = _servers_key(client)
    try:
        data = _load(path)
    except (json.JSONDecodeError, OSError):
        return {
            "client": client,
            "config_path": str(path),
            "present": False,
            "matches": False,
            "current": None,
            "error": "config file unreadable / not valid JSON",
        }
    current = (data.get(key) or {}).get(SERVER_NAME)
    return {
        "client": client,
        "config_path": str(path),
        "present": current is not None,
        "matches": current == desired_entry(command),
        "current": current,
    }


def register(
    client: str = "claude_desktop",
    *,
    config_path: Path | None = None,
    command: str | None = None,
) -> dict[str, Any]:
    """Idempotently merge our MCP server into the client config.

    Backs up an existing file before any write. A no-op when the entry
    already matches. Never clobbers a malformed file — it is backed up
    and left byte-for-byte intact, and an error is returned.
    """
    path = config_path or client_config_path(client)
    key = _servers_key(client)
    entry = desired_entry(command)

    try:
        data = _load(path)
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "ok": False,
            "client": client,
            "config_path": str(path),
            "changed": False,
            "backup_path": _backup(path),
            "entry": entry,
            "error": f"existing config is not valid JSON: {exc!r}. "
            "Backed it up and made no change; fix or delete it, then retry.",
        }

    servers = data.get(key)
    if not isinstance(servers, dict):
        servers = {}
    servers_before = copy.deepcopy(servers)

    if servers.get(SERVER_NAME) == entry:
        return {
            "ok": True,
            "client": client,
            "config_path": str(path),
            "changed": False,
            "backup_path": None,
            "entry": entry,
            "servers_before": servers_before,
            "servers_after": servers_before,
        }

    backup_path = _backup(path)
    servers[SERVER_NAME] = entry
    data[key] = servers
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    return {
        "ok": True,
        "client": client,
        "config_path": str(path),
        "changed": True,
        "backup_path": backup_path,
        "entry": entry,
        "servers_before": servers_before,
        "servers_after": servers,
    }
```

- [ ] **Step 4: Run registrar tests to verify they pass**

Run: `pytest tests/mcp_lane/test_registration.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Wire `--register` into doctor** — replace `_do_register` in `cli/doctor.py`:

```python
def _do_register(client: str) -> int:
    from ..mcp import registration as reg  # function-local: keep import light

    try:
        out = reg.register(client)
    except ValueError as exc:  # unknown client
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(out, indent=2, default=str))
    # Transparency: name the file and show what we injected.
    print(f"config file: {out['config_path']}", file=sys.stderr)
    if out.get("backup_path"):
        print(f"backup:      {out['backup_path']}", file=sys.stderr)
    if out.get("changed"):
        print("registered the ai-sw-bridge MCP server:", file=sys.stderr)
        print(json.dumps(out["entry"], indent=2), file=sys.stderr)
    elif out.get("ok"):
        print("already registered — no change.", file=sys.stderr)
    return 0 if out.get("ok") else 1
```

- [ ] **Step 6: Rewire the read-only `_check_mcp_registration`** in `cli/doctor.py` to use real detection:

```python
def _check_mcp_registration() -> Check:
    from ..mcp import registration as reg

    try:
        d = reg.detect("claude_desktop")
    except Exception as exc:  # noqa: BLE001
        return _check("mcp_registration", False, f"detect failed: {exc!r}",
                      "Run: ai-sw-doctor --register")
    if d.get("present"):
        return _check("mcp_registration", True,
                      f"MCP server registered in {d['config_path']}.")
    return _check(
        "mcp_registration",
        False,
        f"ai-sw-bridge not found in {d['config_path']}.",
        "Run: ai-sw-doctor --register  (writes a timestamped backup first).",
    )
```

Because a fresh dev/CI machine has no Claude config, this check now reports `False`. Update `tests/cli/test_doctor.py` Step-1 tests: they already `monkeypatch.setattr(doctor, "_check_mcp_registration", ...)`, so they stay green. Add one register-path test:

```python
def test_main_register_invokes_registrar(monkeypatch, capsys) -> None:
    calls = {}

    def fake_register(client):
        calls["client"] = client
        return {"ok": True, "client": client, "config_path": "X",
                "changed": True, "backup_path": None,
                "entry": {"command": "ai-sw-mcp", "args": []}}

    monkeypatch.setattr("ai_sw_bridge.mcp.registration.register", fake_register)
    monkeypatch.setattr("sys.argv", ["ai-sw-doctor", "--register"])

    rc = doctor.main()

    assert rc == 0
    assert calls["client"] == "claude_desktop"
    assert '"command": "ai-sw-mcp"' in capsys.readouterr().out
```

- [ ] **Step 7: Run the doctor + registrar suite; lint/type; commit**

Run: `pytest tests/cli/test_doctor.py tests/mcp_lane/test_registration.py -v && black --check src/ai_sw_bridge/mcp/registration.py src/ai_sw_bridge/cli/doctor.py tests/mcp_lane/test_registration.py && flake8 src/ai_sw_bridge/mcp/registration.py src/ai_sw_bridge/cli/doctor.py && python -m mypy --config-file mypy.ini src/ai_sw_bridge && python tools/two_stream_lint.py src/`
Expected: all pass/clean.

```bash
git add src/ai_sw_bridge/mcp/registration.py tests/mcp_lane/test_registration.py src/ai_sw_bridge/cli/doctor.py tests/cli/test_doctor.py
git commit -m "feat(cli): ai-sw-doctor --register (idempotent, backed-up Claude Desktop MCP registration)"
```

---

### Task C: Operator error & safety UX (probe verdict + seat banner)

**Files:**
- Modify: `src/ai_sw_bridge/cli/probe.py` (two-branch failure verdict)
- Modify: `src/ai_sw_bridge/cli/build.py` (reassuring seat banner)
- Modify: `tests/cli/test_build_seat_gate.py` (banner assertions)
- Create/Modify: `tests/cli/test_probe_verdict.py` (probe verdict message)

**Interfaces:** no signature changes — `probe()` keeps its dict shape; only the `error` string content is enriched. `build.py`'s seat-gate keeps its exit-code contract; only the banner prose changes.

- [ ] **Step 1: Write the failing probe-verdict test**

Create `tests/cli/test_probe_verdict.py`:

```python
"""probe()'s failure message must be operator-legible (spec §8.4): it names
both likely causes — SW not open, and 32-bit/64-bit mismatch."""

from __future__ import annotations

import ai_sw_bridge.cli.probe as probe_mod


def test_probe_dispatch_failure_names_both_causes(monkeypatch) -> None:
    def boom():
        raise OSError("Class not registered")

    monkeypatch.setattr(probe_mod, "get_sw_app", boom)
    result = probe_mod.probe()

    assert result["ok"] is False
    msg = result["error"].lower()
    assert "solidworks" in msg and "running" in msg  # (a) is it open?
    assert "64-bit" in msg or "32-bit" in msg          # (b) bitness mismatch
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/cli/test_probe_verdict.py -v`
Expected: FAIL — current message mentions "Is SOLIDWORKS running?" but not the bitness branch.

- [ ] **Step 3: Enrich `probe.py`'s dispatch-failure message**

In `cli/probe.py`, replace the `except Exception as exc:` block after `sw = get_sw_app()` with:

```python
    except Exception as exc:
        result["error"] = (
            f"could not dispatch SldWorks.Application: {exc!r}. "
            "Two common causes: (a) SOLIDWORKS is not running — open it and "
            "retry; (b) if it IS open, your Python is 32-bit but SOLIDWORKS "
            "is 64-bit — reinstall 64-bit Python and ai-sw-bridge."
        )
        return result
```

- [ ] **Step 4: Run probe test to verify pass**

Run: `pytest tests/cli/test_probe_verdict.py tests/cli/test_doctor.py -v`
Expected: PASS. (`_check_solidworks_seat` surfaces the same richer message.)

- [ ] **Step 5: Reword the build seat banner (measure-first)**

Read the current banner in `src/ai_sw_bridge/cli/build.py` (grep `PID` / `Approve` / the `[y/N]` prompt) and read `tests/cli/test_build_seat_gate.py` to see the pinned substrings. Reword the banner to the reassurance framing (spec §8.4), preserving the active-doc name and PID and the no-overwrite promise:

> `I'm about to build in the SOLIDWORKS window showing '{active_doc}' (PID {pid}). This adds a new part; it will not overwrite your open work. Approve? [y/N]`

Keep the banner on **stderr** (the exit-codes contract test asserts stderr is used) and keep the exit-code behavior identical. Update the pinned substrings in `tests/cli/test_build_seat_gate.py` to match the new copy (e.g. assert `"will not overwrite"` and the `PID` interpolation remain).

- [ ] **Step 6: Run the seat-gate + exit-code guard tests**

Run: `pytest tests/cli/test_build_seat_gate.py tests/cli/test_exit_codes_documented.py -v`
Expected: PASS (banner still on stderr, exit codes unchanged).

- [ ] **Step 7: Lint/type + commit**

Run: `black --check src/ai_sw_bridge/cli/probe.py src/ai_sw_bridge/cli/build.py tests/cli/test_probe_verdict.py tests/cli/test_build_seat_gate.py && flake8 src/ai_sw_bridge/cli/probe.py src/ai_sw_bridge/cli/build.py && python tools/two_stream_lint.py src/`
Expected: clean.

```bash
git add src/ai_sw_bridge/cli/probe.py src/ai_sw_bridge/cli/build.py tests/cli/test_probe_verdict.py tests/cli/test_build_seat_gate.py
git commit -m "feat(cli): operator-legible probe verdict + reassuring seat-gate banner"
```

---

### Task D: README persona-router + Operator Guide merge

**Files:**
- Modify: `README.md` (persona-router rewrite, §8.5 skeleton)
- Create: `docs/operator_guide.md` (canonical Operator Guide)
- Modify: `docs/ONBOARDING.md` (fold content into a redirect that keeps its doc-truth pins)
- Create: `tests/test_readme_persona_router.py` (structural assertion)

**Interfaces:** none (docs). **Hard constraint:** every substring in `tests/test_doc_truth.py::DOC_SURFACES` and every `` `<kind>` `` in `tests/test_extension_conformance.py::test_every_feature_kind_named_in_readme_kind_table` must still be present after the rewrite. The doc-truth rows that live in `README.md` and `docs/ONBOARDING.md` are load-bearing — preserve them verbatim (with the count now = 22).

- [ ] **Step 1: Write the failing structural test for the persona router**

Create `tests/test_readme_persona_router.py`:

```python
"""README is a persona router (spec §8.5): an operator-first front door with
signposted developer/contributor sections. This pins the structure so a later
edit can't silently un-route it."""

from __future__ import annotations

from pathlib import Path

_README = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")


def test_readme_has_persona_router_headings() -> None:
    for needle in (
        "Who are you?",          # the router
        "For operators",         # operator spine
        "For developers",        # dev teaser
        "For contributors",      # contributor teaser
    ):
        assert needle in _README, f"README persona-router section missing: {needle!r}"


def test_readme_links_operator_guide() -> None:
    assert "operator_guide.md" in _README
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_readme_persona_router.py -v`
Expected: FAIL (headings not present yet).

- [ ] **Step 3: Rewrite `README.md` to the §8.5 skeleton**

Restructure `README.md` into, in order: title + badges + language links + one-line pitch; **"Who are you? → start here"** router (Operator / Developer-integrator / Contributor); What this is + inline `spec.json`; **"For operators — 5-minute quickstart"** (prerequisites incl. Git+Python 64-bit; `pipx install ai-sw-bridge[mcp]`; `ai-sw-doctor`; smoke test with probe output + seat-gate forewarning; hand keys to the AI; first-run troubleshooting table) — this is the spine (~70% of length); What ships in the box (short command table); Feature kinds (short — must keep every `` `<kind>` ``); Limitations (inline); **"For developers & integrators"** (~10–15 lines → `PUBLIC_API.md`, `tools_reference.md`, `AGENTS.md`, `USAGE.md`); **"For contributors"** (~8–10 lines → `CONTRIBUTING.md`, `CLASS_RELATION_MAP.md`); Project status (version pinned); Layout; License; Acknowledgments.

**Preserve verbatim** (doc-truth + conformance pins): `**{22} CLI commands`, `Current release: \`v1.7.0\``, `**{30} part-modelling feature types**`, `Feature kinds you can add ({36})`, `**36 seat-proven**`, `{37}-tool MCP server`, `{36}-kind \`feature_add\` registry`, and every feature-kind name in backticks. (The `{n}` are the current derived values; state them literally.)

- [ ] **Step 4: Create `docs/operator_guide.md` and redirect ONBOARDING**

Create `docs/operator_guide.md` = the fixed ONBOARDING quickstart + `known_limitations.md` framing + a cross-link to `docs/AGENTS.md` ("if you pair with an AI assistant, hand it this file"), written for a non-coding SW veteran. In `docs/ONBOARDING.md`, keep the two doc-truth-pinned lines (`All 22 CLI commands`, `exposes 37 read-only + build tools`) and the full command table (so `test_onboarding_lists_every_cli_command` still passes), and add a top banner: `> This guide has moved to [docs/operator_guide.md](operator_guide.md).` Do **not** delete the pinned content — moving it would require also moving the `DOC_SURFACES` rows, which is out of scope for Phase 1 (a Phase-2 doc-IA task owns ONBOARDING's retirement).

- [ ] **Step 5: Run the doc gates to verify nothing drifted**

Run: `pytest tests/test_readme_persona_router.py tests/test_doc_truth.py tests/test_extension_conformance.py -v`
Expected: PASS — persona headings present, every derived count still found in README/ONBOARDING, every feature kind still named in the README kind table.

- [ ] **Step 6: Commit**

```bash
git add README.md docs/operator_guide.md docs/ONBOARDING.md tests/test_readme_persona_router.py
git commit -m "docs: persona-router README + canonical Operator Guide"
```

---

### Task E: CI packaged-install smoke stage (§8.6)

**Files:**
- Modify: `.github/workflows/ci.yml` (add a job that installs the built wheel)

**Interfaces:** none. Asserts the *packaged* product surface (wheel, not `-e`): scripts on PATH, no-SW commands work, probe/doctor fail gracefully, the MCP server imports.

- [ ] **Step 1: Add the `operator-install-smoke` job**

Append to `.github/workflows/ci.yml` a new job (sibling of `onboarding`):

```yaml
  operator-install-smoke:
    runs-on: windows-2025
    steps:
      - uses: actions/checkout@v5
      - name: Set up Python
        uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - name: Build wheel
        run: |
          python -m pip install --upgrade pip build
          python -m build --wheel
      - name: Install the built artifact (not -e)
        shell: pwsh
        run: |
          $whl = Get-ChildItem dist/*.whl | Select-Object -First 1
          pip install "$($whl.FullName)[mcp]"
      - name: Scripts are on PATH
        shell: pwsh
        run: |
          where.exe ai-sw-probe
          where.exe ai-sw-mcp
          where.exe ai-sw-doctor
      - name: No-SW command works (list kinds)
        run: ai-sw-build --list-kinds
      - name: probe/doctor fail gracefully with no SW (exit 1, no traceback)
        shell: pwsh
        run: |
          ai-sw-doctor --no-seat
          if ($LASTEXITCODE -ne 1 -and $LASTEXITCODE -ne 0) {
            throw "ai-sw-doctor --no-seat exited $LASTEXITCODE (want 0/1)"
          }
          $out = ai-sw-probe 2>&1
          if ($LASTEXITCODE -ne 1) { throw "ai-sw-probe exited $LASTEXITCODE (want 1 with no seat)" }
          if ($out -match "Traceback") { throw "ai-sw-probe leaked a traceback" }
      - name: MCP server module imports
        run: python -c "import ai_sw_bridge.mcp.server; print('mcp ok')"
```

- [ ] **Step 2: Validate the workflow YAML locally**

Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('yaml ok')"`
Expected: `yaml ok`. (Full job execution is validated by CI on push; the controller does not push mid-phase — note this as the one step whose live proof defers to the phase-end CI run.)

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: packaged-wheel operator-install smoke (scripts on PATH, graceful no-SW failure)"
```

---

## Self-Review

**1. Spec coverage (§8):**
- §8.1 Distribution (pipx) — the install path is documented in the README operator quickstart (Task D) and the scripted pywin32 post-install is surfaced as `ai-sw-doctor`'s `pywin32` check fix (Task A). No installer artifact (deferred to Phase 4). ✅
- §8.2 `ai-sw-doctor` read-only — Task A. ✅
- §8.3 `--register` automated, table-driven, Claude Desktop only — Task B. ✅
- §8.4 Error/safety UX (probe two-branch, seat banner, scripts-on-PATH, `--no-dim` default) — Task C covers probe + seat banner + PATH; `--no-dim` packaged default is an existing `ai-sw-build` behavior surfaced in the README quickstart (Task D), not a code change. ✅
- §8.5 README IA + Operator Guide merge — Task D. ✅
- §8.6 Guardrail (packaged-install smoke) — Task E. ✅
- §8.7 DoD — all clauses map to A–E (see below).

**2. Placeholder scan:** `_do_register`/`_check_mcp_registration` are explicitly labelled Task-A shims and are **replaced with real code in Task B** (Steps 5–6) — not left as TODOs. Every code step shows complete code. ✅

**3. Type/name consistency:** `run_doctor` / check-function names match between the Task-A test (Step 1) and implementation (Step 3). `register`/`detect`/`SERVER_NAME`/`desired_entry` names match between the Task-B test and module. `_do_register` calls `reg.register(client)` (positional client) — matches the signature. ✅

**4. Guardrail-ripple completeness:** adding `ai-sw-doctor` bumps `_cli_command_count` → 22; Task A Step 5 updates README + ONBOARDING counts, the ONBOARDING table row, PUBLIC_API §1+§5, and the entrypoints-smoke assertion. `test_every_cli_script_has_a_stability_tier` and `test_entrypoint_imports_and_help_exits_zero` auto-discover doctor and are satisfied by the `@cli_stability` tier and the argparse `--help`. ✅

**Phase-1 DoD (§8.7) trace:** one pipx path (README/Task D) ✅ · `ai-sw-doctor` on PATH with pass/fail verdicts (Task A) ✅ · chat-first defaults to `--no-dim` (existing behavior, surfaced Task D) ✅ · seat banner reads reassuringly (Task C) ✅ · three first-run failures → plain-English guidance (probe bitness/seat, scripts-on-PATH, pywin32 — Tasks A+C) ✅ · README persona-router with operator content >2/3 (Task D) ✅ · ONBOARDING counts fixed (Task A) ✅ · operator-install smoke green on windows-2025 (Task E, proof at phase-end CI) ✅.

**Residual risk (named, not hidden):** Task E's *live* proof runs only when the branch is pushed (the controller holds the push to phase-end, per Global Constraints). Every other task is fully offline-verifiable on `windows-2025`/dev. The `mcp_lane/test_registration.py` file must carry **no** live marker — the reviewer confirms it runs inside `pytest -m "not solidworks_only and not destructive_sw"`.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-01-phase1-operator-product.md`. Recommended execution: **Subagent-Driven Development** — fresh implementer per task (A→B→C→D→E; B depends on A, D after A–C, E after A), a task review after each, and a whole-branch review at the end. Suggested checkpoints mirroring Phase 0: **Checkpoint 1 = A & B** (the doctor + registrar core), **Checkpoint 2 = C & D** (UX + docs), **Checkpoint 3 = E** (CI). Run `seat-prefire-review` before Task A (doctor imports probe/sw_com) and before Task E (packaged import of the MCP server).
