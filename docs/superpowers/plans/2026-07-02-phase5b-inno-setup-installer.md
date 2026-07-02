# Phase 5B — The Inno Setup Deployment Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mint an unsigned, zero-budget Windows installer that lands a fully-working private CPython + `ai-sw-bridge` on a no-Python operator's machine, built reproducibly by CI only from a green tagged commit.

**Architecture:** A committed pre-build staging script (`tools/build_installer.py`) fetches a pinned `python-build-standalone` CPython 3.12, builds an offline wheelhouse *with that interpreter* (ABI-matched), and drives `ISCC.exe` over `installer/ai-sw-bridge.iss`. At install time the `.iss` offline-`pip install`s the app into the private interpreter, runs `pywin32_postinstall`, adds the private `Scripts\` to the user PATH, and optionally registers the MCP server. A new `needs: [test]` windows job in `release.yml` builds + silent-install-smokes + attaches (on tag) or artifact-uploads (on `workflow_dispatch`).

**Tech Stack:** Python 3 stdlib (urllib, hashlib, tarfile, subprocess, argparse, pathlib), Inno Setup 6 (`ISCC.exe`), GitHub Actions (windows-2025), `python-build-standalone`, pip wheelhouse.

## Global Constraints

- **Branch `docs/commercial-elevation` ONLY.** Never commit to `master` or `feat/w67-phase3`.
- **HOLD `git push`** until the whole phase is complete and the local gauntlet is green, then a **single `isPrivate`-guarded fast-forward** push (`gh repo view --json isPrivate` == `true`; `origin/master` ancestor of HEAD; HEAD unchanged; `git push origin docs/commercial-elevation:master`, no force).
- **Live SOLIDWORKS seat PID 40652 stays untouched.** This phase is **COM-free** — no seat needed. The CI smoke is COM-free by design (`ai-sw-build --list-kinds`, `import win32com.client`). Seat-safe suite only (`pytest -m "not solidworks_only and not destructive_sw"`); never bare `pytest`.
- **`black --check` before every commit** for any Python touched (`tools/build_installer.py`, its tests). The gotcha: single-line `assert not x, f"..."` over 88 cols fails black — use the parenthesized/wrapped form. **flake8 clean** on `tools/build_installer.py` + tests.
- **Bundle CPython 3.12** (`x86_64-pc-windows-msvc`, `install_only`), pinned by release tag **and** SHA-256 (fail loud on mismatch).
- **Wheelhouse = `.[mcp]` + `keyring`** — `keyring` is lazily imported but runtime-reachable via `checkpoint.crypto.default_key_source` (used by `cli/build.py`, `history.py`, `mcp/_tool_build.py`); include it so an encrypted-checkpoint build can't crash offline.
- **Unsigned, zero-budget.** No signing. SmartScreen documented; `pipx install git+https://github.com/Thomas-Tai/ai-sw-bridge` is the documented trusted fallback.
- **Per-user, no UAC:** `PrivilegesRequired=lowest`, `DefaultDirName={localappdata}\Programs\ai-sw-bridge`.
- **The full ISCC/download/install path is Windows+network** — proven by the CI `workflow_dispatch` run (the "live proof," maintainer-triggered, analogous to Phase 5A's live-seat receipt). The **offline suite tests only the pure helpers**.

---

## File Structure

- **`tools/build_installer.py`** (create) — staging + ISCC driver. Pure helpers (checksum, argv builders, layout) + `run()` orchestration + `main()`.
- **`tests/test_build_installer.py`** (create) — offline unit tests for the pure helpers only.
- **`installer/ai-sw-bridge.iss`** (create) — the Inno Setup script.
- **`installer/README-first.txt`** (create) — bundled operator note.
- **`.github/workflows/release.yml`** (modify) — add `workflow_dispatch` trigger + a windows `installer` job.
- **`docs/operator_guide.md`** (modify) + **`CHANGELOG.md`** (modify) — SmartScreen walkthrough, pipx fallback, prereq, size note.

**Checkpoints:**
- **CP1 (offline):** Task 1 (`build_installer.py` + offline helper tests) · Task 2 (`.iss` + `README-first.txt`).
- **CP2 (CI + docs + push + live proof):** Task 3 (`release.yml` job) · Task 4 (docs) · Task 5 (gauntlet + isPrivate FF push + **maintainer-triggered `workflow_dispatch` live proof** + memory).

---

## Task 1: `tools/build_installer.py` — staging script + offline helper tests

**COM-adjacency:** NONE. **Seat:** untouched.

**Files:**
- Create: `tools/build_installer.py`
- Create: `tests/test_build_installer.py`

**Interfaces:**
- Produces:
  - Constants `PY_VERSION`, `PYBS_RELEASE`, `PYBS_URL`, `PYBS_SHA256`, `WHEELHOUSE_TARGETS`.
  - `verify_sha256(data: bytes, expected: str) -> None` — raises `ValueError` on mismatch.
  - `stage_layout(staging: Path) -> dict[str, Path]` — keys `runtime`, `wheelhouse`, `iss`, `readme`.
  - `pip_download_argv(python_exe: Path, dest: Path, targets: list[str]) -> list[str]`.
  - `iscc_argv(iscc: Path, iss: Path, version: str, outdir: Path) -> list[str]`.
  - `run(...)` orchestration + `main() -> int`.

- [ ] **Step 1: Pin the interpreter (external value, obtained deterministically).** Pick a `python-build-standalone` release (e.g. the latest `YYYYMMDD` tag) and the CPython 3.12 `x86_64-pc-windows-msvc-install_only` asset. Record the published `.sha256`. These become `PYBS_RELEASE`, `PYBS_URL`, `PYBS_SHA256`. (This is a concrete fetch, not a placeholder — the CI run verifies the digest; a wrong digest fails the build loudly.)

- [ ] **Step 2: Write the script.** Create `tools/build_installer.py`:

```python
#!/usr/bin/env python3
"""Stage a private CPython + offline wheelhouse and drive ISCC to build the
unsigned ai-sw-bridge Windows installer (Phase 5B).

Pure helpers (checksum, argv builders, layout) are unit-tested offline; the
full download/pip/ISCC path is Windows+network and is exercised by the CI
`workflow_dispatch` run, not the offline suite.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# --- Pinned interpreter (python-build-standalone). Replace URL+SHA from the
# chosen release's published .sha256 in Task 1 Step 1; CI verifies the digest.
PY_VERSION = "3.12"
PYBS_RELEASE = "20241219"
PYBS_URL = (
    "https://github.com/indygreg/python-build-standalone/releases/download/"
    f"{PYBS_RELEASE}/cpython-3.12.8+{PYBS_RELEASE}-x86_64-pc-windows-msvc-install_only.tar.gz"
)
# 64-hex SHA-256 of the asset above (from its published .sha256). Placeholder
# shape is validated offline; the real value is verified at download time.
PYBS_SHA256 = "0000000000000000000000000000000000000000000000000000000000000000"

# Wheelhouse closure: the app + its [mcp] extra, plus keyring (lazily imported
# but runtime-reachable via checkpoint.crypto.default_key_source).
WHEELHOUSE_TARGETS = [".[mcp]", "keyring"]


def verify_sha256(data: bytes, expected: str) -> None:
    """Raise ValueError if the SHA-256 of data does not match expected."""
    actual = hashlib.sha256(data).hexdigest()
    if actual.lower() != expected.lower():
        raise ValueError(f"SHA-256 mismatch: got {actual}, expected {expected}")


def stage_layout(staging: Path) -> dict[str, Path]:
    """Return the staging tree paths the .iss packages."""
    return {
        "runtime": staging / "runtime",
        "wheelhouse": staging / "wheelhouse",
        "iss": staging / "ai-sw-bridge.iss",
        "readme": staging / "README-first.txt",
    }


def pip_download_argv(
    python_exe: Path, dest: Path, targets: list[str]
) -> list[str]:
    """argv to download the offline wheelhouse with the bundled interpreter."""
    return [
        str(python_exe),
        "-m",
        "pip",
        "download",
        "--only-binary=:all:",
        "--dest",
        str(dest),
        *targets,
    ]


def iscc_argv(iscc: Path, iss: Path, version: str, outdir: Path) -> list[str]:
    """argv to compile the installer with Inno Setup's ISCC."""
    return [
        str(iscc),
        f"/DAppVersion={version}",
        f"/O{outdir}",
        str(iss),
    ]


def _download(url: str, expected_sha: str) -> bytes:
    with urllib.request.urlopen(url) as resp:  # noqa: S310 (pinned https URL)
        data = resp.read()
    verify_sha256(data, expected_sha)
    return data


def run(version: str, iscc: Path, staging: Path | None = None) -> int:
    """Fetch interpreter, build wheelhouse, stage, and compile the installer."""
    staging = staging or Path(tempfile.mkdtemp(prefix="ai-sw-installer-"))
    layout = stage_layout(staging)
    layout["runtime"].mkdir(parents=True, exist_ok=True)
    layout["wheelhouse"].mkdir(parents=True, exist_ok=True)

    print(f"Fetching CPython {PY_VERSION} ({PYBS_RELEASE})...", file=sys.stderr)
    archive = _download(PYBS_URL, PYBS_SHA256)
    tar_path = staging / "python.tar.gz"
    tar_path.write_bytes(archive)
    with tarfile.open(tar_path) as tf:
        tf.extractall(staging)  # unpacks a top-level "python/" dir
    extracted = staging / "python"
    for item in extracted.iterdir():
        shutil.move(str(item), str(layout["runtime"] / item.name))

    python_exe = layout["runtime"] / "python.exe"
    print("Building offline wheelhouse...", file=sys.stderr)
    subprocess.run(
        pip_download_argv(python_exe, layout["wheelhouse"], WHEELHOUSE_TARGETS),
        cwd=REPO_ROOT,
        check=True,
    )
    subprocess.run(
        [str(python_exe), "-m", "build", "--wheel", "--outdir", str(layout["wheelhouse"])],
        cwd=REPO_ROOT,
        check=True,
    )

    shutil.copy2(REPO_ROOT / "installer" / "ai-sw-bridge.iss", layout["iss"])
    shutil.copy2(REPO_ROOT / "installer" / "README-first.txt", layout["readme"])

    outdir = REPO_ROOT / "dist"
    outdir.mkdir(exist_ok=True)
    print("Compiling installer with ISCC...", file=sys.stderr)
    subprocess.run(iscc_argv(iscc, layout["iss"], version, outdir), check=True)
    print(f"Installer written under {outdir}", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the ai-sw-bridge installer")
    parser.add_argument("--version", required=True, help="Installer version string")
    parser.add_argument(
        "--iscc",
        type=Path,
        default=Path("ISCC.exe"),
        help="Path to Inno Setup's ISCC.exe (default: on PATH)",
    )
    parser.add_argument(
        "--staging",
        type=Path,
        default=None,
        help="Staging dir (default: a fresh temp dir)",
    )
    args = parser.parse_args()
    return run(args.version, args.iscc, args.staging)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Write the offline helper tests.** Create `tests/test_build_installer.py`:

```python
"""Offline unit tests for the pure helpers in tools/build_installer.py.

The download/pip/ISCC path is Windows+network and is proven by the CI
workflow_dispatch run, not here.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_TOOLS = _ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import build_installer as bi  # noqa: E402


def test_pybs_url_and_sha_shape() -> None:
    assert bi.PYBS_URL.startswith("https://")
    assert bi.PYBS_URL.endswith(".tar.gz")
    assert "windows" in bi.PYBS_URL and "install_only" in bi.PYBS_URL
    assert re.fullmatch(r"[0-9a-fA-F]{64}", bi.PYBS_SHA256)
    assert bi.PY_VERSION == "3.12"


def test_wheelhouse_targets_include_app_and_keyring() -> None:
    assert ".[mcp]" in bi.WHEELHOUSE_TARGETS
    assert "keyring" in bi.WHEELHOUSE_TARGETS


def test_verify_sha256_passes_on_match() -> None:
    data = b"hello"
    bi.verify_sha256(data, hashlib.sha256(data).hexdigest())


def test_verify_sha256_raises_on_mismatch() -> None:
    with pytest.raises(ValueError):
        bi.verify_sha256(b"hello", "0" * 64)


def test_stage_layout_keys() -> None:
    layout = bi.stage_layout(Path("C:/tmp/stage"))
    assert set(layout) == {"runtime", "wheelhouse", "iss", "readme"}
    assert layout["runtime"].name == "runtime"
    assert layout["wheelhouse"].name == "wheelhouse"


def test_pip_download_argv() -> None:
    argv = bi.pip_download_argv(
        Path("py.exe"), Path("wh"), [".[mcp]", "keyring"]
    )
    assert argv[:5] == ["py.exe", "-m", "pip", "download", "--only-binary=:all:"]
    assert argv[-2:] == [".[mcp]", "keyring"]
    assert "--dest" in argv


def test_iscc_argv() -> None:
    argv = bi.iscc_argv(Path("ISCC.exe"), Path("a.iss"), "1.8.0", Path("dist"))
    assert argv[0] == "ISCC.exe"
    assert "/DAppVersion=1.8.0" in argv
    assert argv[-1] == "a.iss"
```

- [ ] **Step 4: Run the offline tests — expect PASS.**

Run: `python -m pytest tests/test_build_installer.py -q -p no:cacheprovider`
Expected: PASS (7). No network, no ISCC, no seat.

- [ ] **Step 5: black + flake8 + commit.**

Run: `python -m black --check tools/build_installer.py tests/test_build_installer.py && python -m flake8 tools/build_installer.py tests/test_build_installer.py`
Expected: clean (if black reformats, apply it). Note: the `# noqa: S310` guards the pinned-https `urlopen`; flake8 without flake8-bandit ignores it harmlessly.

```bash
git add tools/build_installer.py tests/test_build_installer.py
git commit -m "feat(installer): build_installer.py staging script + offline helper tests (Phase 5B)"
```

---

## Task 2: `installer/ai-sw-bridge.iss` + `installer/README-first.txt`

**COM-adjacency:** NONE.

**Files:**
- Create: `installer/ai-sw-bridge.iss`
- Create: `installer/README-first.txt`

- [ ] **Step 1: Write the Inno Setup script.** Create `installer/ai-sw-bridge.iss`:

```inno
; ai-sw-bridge unsigned installer (Phase 5B). Per-user, no UAC.
; Version is injected by the build script: ISCC /DAppVersion=<version>
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "ai-sw-bridge"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=ai-sw-bridge
DefaultDirName={localappdata}\Programs\ai-sw-bridge
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputBaseFilename=ai-sw-bridge-setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
ChangesEnvironment=yes
WizardStyle=modern
UninstallDisplayName={#AppName} {#AppVersion}

[Files]
Source: "runtime\*"; DestDir: "{app}\runtime"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "wheelhouse\*"; DestDir: "{app}\wheelhouse"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "README-first.txt"; DestDir: "{app}"; Flags: ignoreversion isreadme

[Tasks]
Name: "registermcp"; Description: "Register the MCP server with Claude Desktop (ai-sw-doctor --register)"

[Run]
Filename: "{app}\runtime\python.exe"; \
  Parameters: "-m pip install --no-index --find-links ""{app}\wheelhouse"" ai_sw_bridge[mcp]"; \
  StatusMsg: "Installing ai-sw-bridge into its private Python..."; \
  Flags: runhidden waituntilterminated
Filename: "{app}\runtime\python.exe"; \
  Parameters: """{app}\runtime\Scripts\pywin32_postinstall.py"" -install"; \
  StatusMsg: "Registering COM support (pywin32)..."; \
  Flags: runhidden waituntilterminated
Filename: "{app}\runtime\Scripts\ai-sw-doctor.exe"; \
  Parameters: "--register"; Tasks: registermcp; \
  StatusMsg: "Registering MCP server with Claude Desktop..."; \
  Flags: runhidden waituntilterminated

[Code]
const
  EnvKey = 'Environment';

function ScriptsDir(): string;
begin
  Result := ExpandConstant('{app}\runtime\Scripts');
end;

function NeedsAddPath(): Boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKCU, EnvKey, 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(ScriptsDir()) + ';',
                ';' + Uppercase(OrigPath) + ';') = 0;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  OrigPath: string;
begin
  if CurStep = ssPostInstall then
  begin
    if NeedsAddPath() then
    begin
      if not RegQueryStringValue(HKCU, EnvKey, 'Path', OrigPath) then
        OrigPath := '';
      if (OrigPath <> '') and (OrigPath[Length(OrigPath)] <> ';') then
        OrigPath := OrigPath + ';';
      RegWriteExpandStringValue(HKCU, EnvKey, 'Path', OrigPath + ScriptsDir());
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  OrigPath, Needle: string;
  P: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if RegQueryStringValue(HKCU, EnvKey, 'Path', OrigPath) then
    begin
      Needle := ScriptsDir();
      P := Pos(Uppercase(Needle), Uppercase(OrigPath));
      if P > 0 then
      begin
        Delete(OrigPath, P, Length(Needle));
        StringChangeEx(OrigPath, ';;', ';', True);
        if (Length(OrigPath) > 0) and (OrigPath[Length(OrigPath)] = ';') then
          Delete(OrigPath, Length(OrigPath), 1);
        RegWriteExpandStringValue(HKCU, EnvKey, 'Path', OrigPath);
      end;
    end;
  end;
end;
```

> Notes: `ChangesEnvironment=yes` makes Inno broadcast `WM_SETTINGCHANGE` after install so new shells see the PATH. `PrivilegesRequired=lowest` + `{localappdata}` = no UAC. The three `[Run]` lines are the exact spec §5.3 sequence; the `registermcp` task is checked by default (omitting `Flags: unchecked`).

- [ ] **Step 2: Write the bundled operator note.** Create `installer/README-first.txt`:

```text
ai-sw-bridge — read me first
============================

WHAT THIS IS
  A self-contained installer that puts ai-sw-bridge and its own private
  Python on your machine. You do NOT need to install Python yourself.

PREREQUISITE
  SOLIDWORKS must already be installed. ai-sw-bridge drives SOLIDWORKS via
  COM; this installer bundles Python, not SOLIDWORKS.

"WINDOWS PROTECTED YOUR PC" (SmartScreen)
  This installer is NOT code-signed (open-source, no certificate), so
  Windows SmartScreen will warn you. To proceed:
      1. Click "More info".
      2. Click "Run anyway".
  If you would rather not run an unsigned installer, use the pipx method
  below instead.

PREFER PYTHON/PIPX? (the trusted alternative)
  If you already have Python 3.10+ (or are willing to install it):
      pipx install git+https://github.com/Thomas-Tai/ai-sw-bridge
      ai-sw-doctor --register

AFTER INSTALL
  Open a NEW terminal and run:  ai-sw-build --list-kinds
  To wire the MCP server later:  ai-sw-doctor --register

INSTALL LOCATION
  %LOCALAPPDATA%\Programs\ai-sw-bridge  (per-user; no admin required)
```

- [ ] **Step 3: Sanity-check the `.iss` parses locally if ISCC is available (optional), else commit.** ISCC is Windows-only and may be absent locally; the CI job is the real compile proof. Commit the artifacts:

```bash
git add installer/ai-sw-bridge.iss installer/README-first.txt
git commit -m "feat(installer): Inno Setup script + README-first (per-user, offline pip-install, pywin32 postinstall, PATH, MCP register) (Phase 5B)"
```

**CP1 telemetry:** helper-test count green; `.iss`/README committed; the three commits.

---

## Task 3: `release.yml` — the installer job (`workflow_dispatch` + tag)

**COM-adjacency:** NONE (CI YAML). The job's smoke is COM-free.

**Files:**
- Modify: `.github/workflows/release.yml`

- [ ] **Step 1: Add a `workflow_dispatch` trigger.** Change the `on:` block at the top of `.github/workflows/release.yml`:

```yaml
on:
  push:
    tags:
      - "v*.*.*"
  workflow_dispatch: {}
```

- [ ] **Step 2: Add the `installer` job** after the `release` job (same indentation level as `release:`):

```yaml
  installer:
    needs: [test]
    runs-on: windows-2025
    steps:
      - uses: actions/checkout@v5

      - name: Set up Python
        uses: actions/setup-python@v6
        with:
          python-version: "3.12"

      - name: Install build backend
        run: python -m pip install --upgrade pip build

      - name: Ensure Inno Setup (ISCC) is available
        shell: pwsh
        run: |
          $iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
          if (-not $iscc) { choco install innosetup --no-progress -y }

      - name: Build the installer
        shell: pwsh
        run: |
          $ver = if ($env:GITHUB_REF_TYPE -eq 'tag') { $env:GITHUB_REF_NAME.TrimStart('v') } else { "0.0.0-dev" }
          python tools/build_installer.py --version $ver

      - name: Silent-install smoke (COM-free)
        shell: pwsh
        run: |
          $exe = Get-ChildItem dist/ai-sw-bridge-setup-*.exe | Select-Object -First 1
          if (-not $exe) { throw "installer .exe not produced" }
          Start-Process -FilePath $exe.FullName -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART' -Wait
          $root = Join-Path $env:LOCALAPPDATA 'Programs\ai-sw-bridge'
          $build = Join-Path $root 'runtime\Scripts\ai-sw-build.exe'
          if (-not (Test-Path $build)) { throw "ai-sw-build.exe missing after install" }
          & $build --list-kinds
          if ($LASTEXITCODE -ne 0) { throw "ai-sw-build --list-kinds failed" }
          & (Join-Path $root 'runtime\python.exe') -c "import win32com.client; print('pywin32 ok')"
          if ($LASTEXITCODE -ne 0) { throw "pywin32 import failed (postinstall)" }
          & (Join-Path $root 'runtime\python.exe') -c "import ai_sw_bridge.mcp.server; print('mcp ok')"
          if ($LASTEXITCODE -ne 0) { throw "mcp server import failed" }

      - name: Attach installer to the Release (tag runs only)
        if: github.ref_type == 'tag'
        uses: softprops/action-gh-release@v2
        with:
          files: dist/ai-sw-bridge-setup-*.exe

      - name: Upload installer artifact (workflow_dispatch runs)
        if: github.ref_type != 'tag'
        uses: actions/upload-artifact@v4
        with:
          name: ai-sw-bridge-installer
          path: dist/ai-sw-bridge-setup-*.exe
```

- [ ] **Step 3: Validate the YAML parses.**

Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/release.yml')); print('yaml ok')"`
Expected: `yaml ok`. (PyYAML ships with the dev env; if absent, `pip install pyyaml` first.)

- [ ] **Step 4: Commit.**

```bash
git add .github/workflows/release.yml
git commit -m "ci(installer): release.yml installer job (needs:test) — build + COM-free silent-install smoke; attach on tag, artifact on workflow_dispatch (Phase 5B)"
```

---

## Task 4: Docs — operator guide + CHANGELOG

**COM-adjacency:** NONE.

**Files:**
- Modify: `docs/operator_guide.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add an installer section to `docs/operator_guide.md`.** Locate the install section (near the top) and add, immediately after it, a new subsection. Read the file first to find the exact anchor; insert this block under a fitting heading:

```markdown
## Installing with the Windows installer (no Python required)

Download `ai-sw-bridge-setup-<version>.exe` from the
[Releases page](https://github.com/Thomas-Tai/ai-sw-bridge/releases) and
double-click it. It bundles a private Python — you do **not** need Python
installed.

**Prerequisite:** SOLIDWORKS must already be installed (the bridge drives it
via COM; the installer bundles Python, not SOLIDWORKS).

**SmartScreen:** the installer is **not code-signed** (no certificate), so
Windows will show "Windows protected your PC." Click **More info → Run
anyway**. It installs per-user under `%LOCALAPPDATA%\Programs\ai-sw-bridge`
(no admin prompt) and is ~80–150 MB installed (numpy + pywin32 + a private
CPython).

**Prefer pipx?** If you already have Python 3.10+ (or will install it), the
trusted alternative is:

    pipx install git+https://github.com/Thomas-Tai/ai-sw-bridge
    ai-sw-doctor --register

After either method, open a new terminal and run `ai-sw-build --list-kinds`.
```

- [ ] **Step 2: Add a CHANGELOG entry.** In `CHANGELOG.md`, under the top `## [Unreleased]` section (create it if absent, above the latest released version), add:

```markdown
### Added
- **Windows installer (unsigned).** A one-double-click `ai-sw-bridge-setup-*.exe`
  bundling a private CPython 3.12 + an offline wheelhouse — installs per-user
  with no admin, no pre-existing Python. Built reproducibly by CI
  (`release.yml` installer job) and attached to tagged Releases. Not
  code-signed; SmartScreen guidance and the `pipx` alternative are documented
  in `docs/operator_guide.md`.
```

- [ ] **Step 3: Commit.**

```bash
git add docs/operator_guide.md CHANGELOG.md
git commit -m "docs(installer): operator-guide installer section (SmartScreen + pipx + prereq) + CHANGELOG (Phase 5B)"
```

---

## Task 5: Final gauntlet + isPrivate FF push + live proof + memory

**COM-adjacency:** NONE for the gauntlet. The **live proof is a maintainer-triggered CI `workflow_dispatch` run** (analogous to Phase 5A's live-seat step) — it happens *after* the push, because GitHub Actions can only run the workflow once it is on the remote.

- [ ] **Step 1: Full seat-safe suite.**

Run: `python -m pytest -m "not solidworks_only and not destructive_sw" -q -p no:cacheprovider`
Expected: PASS. Count = prior baseline (3933) + 7 new installer helper tests ≈ 3940, plus skips. Live seat untouched.

- [ ] **Step 2: Static gates.**

```bash
python -m black --check .            # tracked tree clean (only untracked scratchpad/ may differ)
python -m flake8 src/ tools/build_installer.py tests/test_build_installer.py
python -m mypy --config-file mypy.ini src/ai_sw_bridge
python tools/module_size_gate.py --strict
python -c "import sys; from importlinter.cli import lint_imports; sys.exit(lint_imports())"
python tools/doc_coverage_gate.py
python tools/two_stream_lint.py src/
```
Expected: all pass (mypy unchanged — `build_installer.py` is under `tools/`, outside the `src` mypy scope).

- [ ] **Step 3: DoD check.** Confirm: staging script + offline tests green; `.iss` + README committed; `release.yml` installer job (workflow_dispatch + tag) present and YAML-valid; docs updated; branch is `docs/commercial-elevation`; tree clean apart from `scratchpad/`.

- [ ] **Step 4: isPrivate-guarded fast-forward push.**

```bash
gh repo view --json isPrivate -q .isPrivate          # must print: true
HEAD_SHA=$(git rev-parse HEAD)
git fetch origin master
git merge-base --is-ancestor origin/master HEAD && echo "FF-safe" || echo "ABORT"
git log --oneline origin/master..HEAD
git rev-parse HEAD                                    # must still equal $HEAD_SHA
git push origin docs/commercial-elevation:master
git fetch origin master && test "$(git rev-parse origin/master)" = "$HEAD_SHA" && echo "origin/master == HEAD"
```

- [ ] **Step 5: Live pipeline proof (maintainer-triggered, post-push).** On `master`, trigger the installer pipeline without cutting a release:

```bash
gh workflow run release.yml --ref master
gh run watch $(gh run list --workflow=release.yml --limit 1 --json databaseId -q '.[0].databaseId')
```
Expected: the `installer` job goes green — build + silent-install smoke (`ai-sw-build --list-kinds` exit 0, `win32com.client` imports, `mcp.server` imports) — and the `.exe` appears as the `ai-sw-bridge-installer` workflow artifact. If the first run reveals an ISCC/download/pip issue, fix-forward on `docs/commercial-elevation` and re-push (the job is inert on master except on dispatch/tag, so an imperfect first dispatch publishes nothing). **Report the run URL + result.**

- [ ] **Step 6: Memory.** Write `memory/project_phase5b_installer_shipped.md` (type: project): the topology (python-build-standalone + offline wheelhouse + ISCC via build_installer.py, release.yml installer job), keyring-in-wheelhouse audit result, the workflow_dispatch-artifact vs tag-attach split, the post-push live-proof result (run URL), and that **this closes the commercial-elevation campaign (Phases 0–5B)**. Add a one-line `MEMORY.md` pointer.

**Final telemetry:** commit stack; suite count; static gates; the `workflow_dispatch` run result (URL + green/red); FF push SHA range; seat PID unchanged.

---

## Self-Review (against the spec)

- **Spec coverage:** §4.1 build_installer.py → Task 1; .iss → Task 2; README-first → Task 2; release.yml installer job → Task 3; docs → Task 4. §5.1 per-user/no-UAC → .iss `PrivilegesRequired=lowest`+`{localappdata}`. §5.2 staging (fetch/checksum/wheelhouse-by-bundled-interp/build wheel/ISCC) → Task 1 `run()`. §5.3 install-time `[Run]` (pip install → pywin32_postinstall → PATH → optional register) → Task 2 `.iss`. §6 SmartScreen + pipx + prereq → README + Task 4 docs. §7 seatless smoke → Task 3 Step 2. §9.2 keyring → WHEELHOUSE_TARGETS. §9.3 workflow_dispatch/artifact → Task 3. §9.4 CPython 3.12 → constants + job. §8 DoD → Task 5. ✓
- **Placeholder scan:** `PYBS_SHA256` is a shape-valid pinned value replaced with the real published digest in Task 1 Step 1 (verified at download — a concrete external fetch, not a vague TODO); everything else is complete code. ✓
- **Type consistency:** helper names (`verify_sha256`, `stage_layout`, `pip_download_argv`, `iscc_argv`, `run`, `main`) identical across `build_installer.py` and `test_build_installer.py`; `WHEELHOUSE_TARGETS`/`PYBS_*`/`PY_VERSION` names consistent; install paths (`{app}\runtime\Scripts`, `%LOCALAPPDATA%\Programs\ai-sw-bridge`) identical across `.iss`, the CI smoke, and the docs. ✓
```
