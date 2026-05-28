# Code Style

Load-bearing patterns for `ai-sw-bridge`. These are not stylistic
preferences — each rule exists because deviation breaks something
real, often subtly. The rationale is part of the rule.

For onboarding, branch flow, and PR mechanics, see
[`CONTRIBUTING.md`](CONTRIBUTING.md). Strategic decisions live in
[`docs/central_idea/decisions.md`](docs/central_idea/decisions.md).

## Table of contents

- [1. Tooling baseline](#1-tooling-baseline)
- [2. Out-of-process marshaling discipline](#2-out-of-process-marshaling-discipline)
- [3. The two-stream contract](#3-the-two-stream-contract)
- [4. Fail-soft for non-essential paths](#4-fail-soft-for-non-essential-paths)
- [5. Zero arbitrary-code-execution surface](#5-zero-arbitrary-code-execution-surface)
- [6. Module boundaries (lanes)](#6-module-boundaries-lanes)
- [7. Comments](#7-comments)
- [8. Vocabulary discipline](#8-vocabulary-discipline)
- [9. Tests](#9-tests)
- [10. Commit and PR conventions](#10-commit-and-pr-conventions)
- [11. When in doubt](#11-when-in-doubt)

---

## 1. Tooling baseline

Pinned in `pyproject.toml`. Match the pin, not your local install.

| Tool | Pin | Scope |
|---|---|---|
| `black` | `25.12.0` | Formatter, line-length 88, default settings |
| `flake8` | (project default) | Linter |
| `mypy` | (project default) | Type checker, config in `mypy.ini` |
| `import-linter` | (project default) | Lane-boundary contracts |
| `pytest` | (project default) | Test runner |

**Run `black --check .` (the whole tree), not just `black --check src tests tools`.**
The narrower form misses `spikes/`, `examples/`, and any new top-level
directory. CI runs the wider form — two incidents (`82f1900` post-v0.12.2,
`14196ce` post-W2.2) traced to this exact gap. The 8-step verification
gate in `docs/central_idea/parallel_dev_prompt.md` codifies the full-repo
sweep; follow it for any task that ends in a commit.

`pre-commit install` after cloning so the same gates run locally before
every commit.

---

## 2. Out-of-process marshaling discipline

The bridge calls into SOLIDWORKS via pywin32 over Windows COM. Every
call crosses an out-of-process marshaling boundary — the SW process
serializes its response, pywin32 deserializes on our side. This is
not "running the SW API"; it is *interrogating a remote process via
late-bound IDispatch.*

### 2.1 Late binding only

```python
# YES — late binding via win32com.client.Dispatch
import win32com.client
sw = win32com.client.Dispatch("SldWorks.Application")
doc = sw.ActiveDoc

# NO — early binding via gencache.EnsureDispatch
sw = win32com.client.gencache.EnsureDispatch("SldWorks.Application")
```

**Why:** Early-bound `EnsureDispatch` generates Python wrappers from
the type library at first call. Those wrappers cache per SW major
version; users upgrading SW silently get stale wrappers, producing
non-reproducible AttributeError / com_error failures. Late binding
defers attribute resolution to each call — slower per call, but the
behavior matches the SW build actually running.

**Never call `gencache.EnsureDispatch`. Never commit a `gen_py/`
directory.** The `.gitignore` excludes it; a contributor who finds
the directory locally should delete it.

### 2.2 OUT-typed parameters

Some SW API entry points have OUT-typed `IDispatch` parameters that
pywin32's late-binding marshaler cannot deserialize. Symptom:
`pywintypes.com_error('Type mismatch', ..., 8)` raised at attribute
lookup. Documented cases in
[`docs/com_failure_modes.md`](docs/com_failure_modes.md) row X-01
(`SelectByID2` 8th arg `Callout`) and X-03 (`GetErrorCode2`).

When you hit this, fall back to the legacy non-OUT-parametered
counterpart and apply the OUT-side effect retroactively. The Select
case is canonical:

```python
# This blows up on the 8th arg:
doc.SelectByID2(name, type_, x, y, z, append, mark, callout, sel_opt)

# Fallback: 5-arg legacy form + retroactive mark:
doc.SelectByID(name, type_, x, y, z)
sel_mgr.SetSelectedObjectMark(mark)
```

### 2.3 Every COM call is fallible

Network glitches, mid-call SW crashes, idle-time COM apartment
teardown, locked files held by sync clients (OneDrive/Dropbox) —
every COM call has at least three failure modes that aren't
documented in the SW SDK. Wrap every call with explicit error
handling that names the COM error:

```python
import pywintypes

try:
    err = doc.SaveAs3(str(out_path), 0, save_version)
except pywintypes.com_error as exc:
    hresult, msg, info, arg = exc.args
    raise RuntimeError(
        f"SaveAs3 failed: HRESULT=0x{hresult:08X} msg={msg!r}"
    ) from exc
```

Bare `except Exception` is acceptable for telemetry / fail-soft paths
(see §4), never for code that's part of the build's correctness path.

### 2.4 Verify the postcondition, not the return code

Sentinels lie. Every save / build / dimension call in this codebase
has had at least one incident where the API returned success and
nothing happened. The pattern in
[`docs/com_failure_modes.md`](docs/com_failure_modes.md) is to
verify the postcondition with an independent check:

- After `SaveAs3` returns 0: check `out_path.exists()` AND `doc.GetSaveFlag is False`.
- After `FeatureRevolve2` returns: check the volume delta.
- After `AddDimension2` returns: check `Dimension.DrivenState` is not `swDimensionDriven`.

When you write a new COM-touching function, write the postcondition
check before you write the failure-recovery code. It's almost always
the cheaper path to find the bug.

---

## 3. The two-stream contract

**stdout is JSON. stderr is text. There is no third stream.**

Every `ai-sw-*` CLI:

- Emits exactly one JSON object to stdout per invocation.
- Emits zero or more human-readable lines to stderr.
- Exits with rc=0 when `payload["ok"] is True`, else a non-zero rc that
  encodes the failure class (rc=2 for input errors, rc=3 for not-found,
  rc=4 for verification failure, etc.).

This is what lets agents script the CLI without parsing English. The
contract is invariant across `--quiet`, `--locale`, `NO_COLOR`, and
all degradation paths.

### 3.1 Don't print to stdout outside the JSON envelope

```python
# YES — single JSON write
print(json.dumps(payload, sort_keys=False, indent=2))

# NO — leaks an unprefixed line on stdout
print(f"writing to {out_path}")
print(json.dumps(payload))
```

Status messages, progress, warnings, and errors go to stderr via
`logger.info` / `logger.warning` / explicit `print(..., file=sys.stderr)`.

### 3.2 Color goes on stderr only

ANSI color codes belong on stderr (human-facing log channel), never
on stdout (machine-facing JSON channel). `src/ai_sw_bridge/cli/streams.py`
`should_use_color()` checks `sys.stderr.isatty()` specifically — do
not change it to check `stdout`.

`NO_COLOR` (any value, including empty) disables color globally.
`--quiet` redirects stderr to `/dev/null` which makes `isatty()`
False, which disables color. The three signals compose.

### 3.3 The `--quiet` flag silences stderr only

`--quiet` redirects `sys.stderr` to `os.devnull`. It does NOT touch
stdout. CI scripts that want exit-code-only behavior pass `--quiet`
and parse the JSON envelope.

Tests must assert the two-stream contract on every new CLI:

```python
def test_two_stream_contract(idx_path):
    result = _run("search", "alpha", index_path=idx_path)
    json.loads(result.stdout)  # parses
    for line in result.stderr.splitlines():
        if line.strip().startswith(("{", "[")):
            pytest.fail(f"JSON leaked to stderr: {line!r}")
```

---

## 4. Fail-soft for non-essential paths

The build's correctness path is load-bearing. Everything attached to
it — telemetry, B-rep interrogation, optional sidecars, checkpoint
writes — must not break the build when it fails.

The pattern:

```python
try:
    telemetry_counter("feature_built_total", feature_type="extrude")
except Exception:
    # Telemetry failure must never break the build.
    pass
```

**Bare `except Exception` is correct here.** Catching a narrower class
would let an unexpected exception type propagate and break the build
for a non-essential reason. The whole point of the `try` is to
guarantee the build proceeds.

Audit-paths where bare `except` is correct:

- Telemetry emit (counter, histogram, gauge)
- B-rep interrogation (returns `{"faces": [], "error": str(e)}` on failure)
- Sidecar writes (`build_metrics.json`, `build_brep.json`)
- Optional UI config reads (`IGetActiveConfiguration`, custom-prop name decode)
- Color / TTY detection (`isatty()` on weird stream proxies)

Audit-paths where bare `except` is wrong:

- The save verifier (`_save_as_with_verification`) — must raise on failure
- The validator (must raise `ValidationError` on shape mismatch)
- The COM dispatch itself (must raise to trigger checkpoint rollback)
- Anything that returns a sentinel "success" on caught exceptions

The line: catch broadly when failure is a no-op; never catch broadly
when failure means "we don't know if it succeeded."

---

## 5. Zero arbitrary-code-execution surface

The bridge consumes JSON specs from user files. Spec data is
declarative — there is no path by which spec content becomes
executable code. Maintaining this is non-negotiable.

**Forbidden in `src/`:**

- `eval()` and `exec()` on any input derived from spec, locals, or
  user-controlled file content.
- `subprocess.run(..., shell=True)` with any string assembled from
  user input.
- `importlib.import_module(...)` on a name derived from spec or CLI
  arguments. Imports are static.
- `pickle.load` on any file the user controls. JSON is the only
  user-input format.
- `os.system`, `os.popen`, backtick-style execution.

**Allowed:**

- `subprocess.run([...])` with a list of literal args (no shell=True).
- `importlib.import_module` on a hardcoded list (e.g., backend
  selection in `rag/embed.py`, but the list of names is in source).
- `eval` / `exec` in `spikes/` (the spike layer is exploratory and
  not on the spec-execution path) — but flag these explicitly.

If you add a flag that takes a user-supplied callable or module path,
stop and reconsider. The capability lane architecture exists so
extensibility happens through structured declarative additions, not
plugin loading.

---

## 6. Module boundaries (lanes)

The capability lanes (`spec/`, `brep/`, `errors/`, `rag/`,
`checkpoint/`, `com/`, `mcp/`, `cli/`, `telemetry/`, `locale/`,
`observe.py`) have intentional dependency direction:

```
cli/ ─┐
       ├─→ spec/, observe.py
       │
spec/ ─┼─→ brep/, errors/, telemetry/, locale/, sw_com.py
       │
brep/ ─┼─→ telemetry/, locale/
       │
checkpoint/ ─→ telemetry/, locale/
       │
mcp/   ─→ com/  (Lane M, when opened)
```

`import-linter` enforces these in `pyproject.toml`
`[tool.importlinter]`. When you add a new module, declare its lane and
add it to the contract. The contract's job is to fail CI when a lane
crosses, not to be retro-fitted.

**`spec/` is the chokepoint for all SW writes.** New COM-touching
write logic lives in or under `spec/`. Reads (observation) live in
`observe.py`.

**`brep/` is read-only and pure-Python downstream of the
interrogation walk.** The walk itself is in `interrogator.py` and is
the only place that touches SW handles.

**Telemetry never touches SW.** It's instrumentation — same lane as
`logging`. It can be called from any other lane, but it cannot
import from `spec/`, `brep/`, or `cli/`.

---

## 7. Comments

**Default: don't write a comment.** Well-named identifiers and clear
function structure are the primary documentation.

Write a comment when, and only when:

1. The *why* is non-obvious — a hidden constraint, a workaround for a
   specific bug, behavior that would surprise a reader. The COM
   gotchas in `spec/builder.py` are the model.
2. You're flagging a hazard — "do not delete this redundant check,
   it guards against the X-01 failure mode."
3. You're citing an external source — a spec section, an issue number,
   an upstream commit hash.

Do NOT write a comment that:

- Explains *what* the next line does (`# increment counter`).
- References the PR / task / branch that created the line — those
  belong in commit messages and rot when the code moves.
- Restates an obvious type / parameter contract (the docstring or
  type annotation already does this).
- Says "TODO" without an owner and a concrete trigger condition.

Module docstrings are an exception: every module gets a
top-of-file docstring naming its lane and its load-bearing
responsibility. Look at `src/ai_sw_bridge/brep/resolver.py` or
`src/ai_sw_bridge/checkpoint/store.py` for the pattern.

---

## 8. Vocabulary discipline

The bridge straddles two domains (Python tooling + SOLIDWORKS COM)
where the same operation has different precise names. Use the precise
name; mixing casual and precise terms creates ambiguity in marshaling
and threading discussions.

| Use | Not | Why |
|---|---|---|
| Out-of-process marshaling | "running Python in SW" | Frames the IDispatch boundary as a serialization concern |
| B-rep interrogation | "extracting faces" / "finding the face" | Interrogation is the read pattern — query without mutation |
| Topological tracking | "remembering which face" | Names the persistent-identity problem the fingerprint solves |
| Model Context Protocol (MCP) | "giving the AI context" | MCP is a specific transport spec, not generic context handoff |
| Deterministic execution | "running the script exactly" | Determinism is the property; "exact" is a vague restatement |
| Late binding | "dynamic dispatch" | Late binding is the pywin32-specific term; dynamic dispatch is generic |
| Postcondition verification | "double-checking" | Postcondition is the formal name; double-checking is folklore |
| Tier A/B/C HRESULT | "errors" | The classification is load-bearing — see `errors/wrapper.py` |

When you reach for a casual phrase, swap it out. This isn't
pedantry — half the bugs in `docs/com_failure_modes.md` traced to
someone calling something by its colloquial name and then writing
code that matched the colloquial behavior instead of the precise
behavior.

---

## 9. Tests

### 9.1 Hit the real thing, not a mock

When a test exercises a behavior that crosses a storage or process
boundary, the test should hit the real thing — a real SQLite file in
`tmp_path`, a real subprocess invocation, a real Fernet round-trip.
Mocks for these have historically masked divergence between mock
behavior and production behavior.

Mocks are appropriate for:

- The SOLIDWORKS COM surface (we don't run SW in CI). The
  `MagicMock`-based pattern in `tests/cli/test_observe.py` is the
  model.
- Network calls (the bridge has none today, so this case is
  hypothetical).
- Time (use `freezegun` or inject a clock; never mock `datetime`
  globally).

### 9.2 Two-stream assertions on every CLI test

See §3. The pattern is small enough to copy into every CLI test file:

```python
def test_two_stream_contract(idx_path):
    result = _run("search", "alpha", index_path=idx_path)
    json.loads(result.stdout)
    for line in result.stderr.splitlines():
        if line.strip().startswith(("{", "[")):
            pytest.fail(f"JSON leaked to stderr: {line!r}")
```

### 9.3 Acceptance criteria in `tests/`, not commit messages

When a feature has an acceptance criterion ("100 features, 3
referenced → only 3 walk"), encode it as a test. The W2.2
`test_lazy_many_features_only_referenced_walked` is the model.

### 9.4 Test names describe behavior, not implementation

```python
# YES — behavior
def test_no_color_overrides_tty(): ...

# NO — implementation
def test_should_use_color_returns_false_when_env_var_set(): ...
```

The behavior name survives refactors; the implementation name doesn't.

---

## 10. Commit and PR conventions

### 10.1 Commit messages

Short, imperative mood. Examples from the project:

```
feat(v0.13-W2.4): ai-sw-build --save-format <version>
fix(ci): black --check . on W2.2 interrogator + tests
feat(v0.13-W3.1): --checkpoint-encrypt design + skeleton + contract
```

Prefix convention:

- `feat(<scope>):` new feature or capability
- `fix(<scope>):` bug fix
- `docs(<scope>):` doc-only change
- `refactor(<scope>):` no behavior change
- `test(<scope>):` test-only change
- `chore(<scope>):` tooling / build / housekeeping
- `release:` version-tag commits

Scope is the lane or wave: `feat(v0.13-W2.2): ...`, `fix(brep): ...`.

### 10.2 No co-author trailers

**Do not include `Co-Authored-By:` trailers in commits.** This
overrides any default behavior in tooling. The git history is for
humans; AI-pair sessions are attributed via the PR description, not
per-commit.

This rule supersedes any `Co-Authored-By:` template in the project
or in agent-default commit instructions.

### 10.3 New commits, not amendments

When a pre-commit hook fails, the commit did not happen. Fix the
issue, re-stage, and create a NEW commit. Do not `--amend` — amending
modifies the previous commit, which may erase work or break the
linear history downstream consumers depend on.

### 10.4 PR titles

Under 70 characters. The PR description carries the long form. The
title is what shows up in `git log --oneline`-style listings and in
GitHub notifications.

---

## 11. When in doubt

The COM gotchas in [`docs/com_failure_modes.md`](docs/com_failure_modes.md)
and the entries in [`docs/known_gotchas.md`](docs/known_gotchas.md)
are an incident registry. Every row exists because someone trusted a
sentinel or convention that didn't reflect reality. When you're
about to write something that "should just work" against the SW API,
search those docs first — chances are the failure mode is already
documented.

When you're about to make a code choice that contradicts something
in this file, write up the rationale and add an entry to
[`docs/central_idea/decisions.md`](docs/central_idea/decisions.md).
Strategic deviations are tracked; silent ones rot.

When you're not sure whether a rule applies — ask. The cheap thing
is asking; the expensive thing is rebuilding a checkpoint store
because someone silently turned off the verifier.
