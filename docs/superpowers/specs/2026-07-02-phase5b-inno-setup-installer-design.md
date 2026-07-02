# Phase 5B — The Inno Setup Deployment Pipeline (Design Specification)

> **Status:** DRAFT for final review gate · **Date:** 2026-07-02 · **Author:** (SDD orchestrator)
> **Governing plan:** `docs/superpowers/specs/2026-07-01-commercial-google-standard-elevation-design.md` §11 (Phase "Expandability", decomposed — 5A perf gate SHIPPED, **5B installer = this spec, the final deliverable**).
> **Predecessors:** [[project_phase5a_perf_honesty_gate_shipped]], [[project_phase1_operator_product_shipped]] (the `pipx`-from-git path this falls back to; `ai-sw-doctor --register`).

---

## 1. Objective

Ship a **one-double-click Windows installer** that puts `ai-sw-bridge` on a CAD operator's machine **without requiring them to own or manage a Python environment** — the "true no-Python operator" the original spec named. The installer is **unsigned and zero-budget** (no code-signing certificate procured), so the design must make the resulting SmartScreen friction honest and navigable, and must preserve the `pipx` path as the documented trusted alternative.

The deliverable is a **build pipeline**, not a hand-built binary: a committed staging script + Inno Setup script, wired into the existing tag-triggered release workflow so the installer is minted only from a green, tagged commit.

---

## 2. Ratified anchors (locked in brainstorm — do NOT reopen)

- **A2.1 — Option 2: bundle a private CPython + offline wheelhouse.** Not PyInstaller (rejected — `win32com`/`gencache` freeze fragility). The installer lays down a private interpreter and offline-`pip install`s the app into it.
- **A2.2 — The private CPython is `python-build-standalone`** (the relocatable full-CPython distribution `uv` ships) — **not** the official *embeddable zip*. The embeddable is pip-less, ships a restrictive `._pth`, and does not host `pywin32`/its postinstall cleanly. `python-build-standalone` is pip-complete, full-stdlib, relocatable, redistributable, and hosts `pywin32` natively.
- **A2.3 — Assembly is a pre-build staging script**, not `.iss`-at-compile-time. Inno Setup is a *packager*, not a package manager; `pip download` + fetching the interpreter is a Python build step. `tools/build_installer.py` stages the tree; `ISCC.exe` packages it.
- **A2.4 — CI integration extends `release.yml`**, not a new workflow. A separate `build-installer.yml` would duplicate the `v*.*.*` tag trigger and lose the `needs: [test]` green-gate dependency (a workflow can't `needs:` a job in another workflow). A new windows job in `release.yml` reuses the test guard and attaches the `.exe` to the same GitHub Release.
- **A2.5 — Unsigned, zero-budget.** No signing. SmartScreen warnings are documented; the `pipx` install remains the documented trusted alternative.

---

## 3. Current state (measured 2026-07-02)

- **`release.yml`** — fires on `v*.*.*` tags: a `test` job (windows-2025, re-runs format/lint/mypy/import-linter/offline suite) → a `release` job (ubuntu, `python -m build`, GPG-signs checksums, publishes a GitHub Release with the wheel + sdist). The installer job hangs off the same `test` guard.
- **`ci.yml::operator-install-smoke`** — already proves the COM-free happy path after a real install: `where.exe ai-sw-probe/ai-sw-mcp/ai-sw-doctor`, `ai-sw-build --list-kinds`, `import ai_sw_bridge.mcp.server`. This is the exact smoke the installer job reuses post-silent-install.
- **Runtime deps (the wheelhouse contents):** `pywin32>=305,<400`, `Pillow>=10,<12`, `oletools>=0.60,<1`, `jsonschema>=4,<5`, `numpy>=1.24,<3`, `sqlite-vec>=0.1,<0.2`, plus the `[mcp]` extra `mcp>=1.0.0`. `requires-python >=3.10`.
- **23 console scripts** in `[project.scripts]` (`ai-sw-probe` … `ai-sw-doctor`, `ai-sw-mcp`) — `setuptools` generates their `.exe` shims in the private `Scripts\` at pip-install time.
- **`ai-sw-doctor --register`** — writes the MCP server into the `claude_desktop` config (timestamped backup first). The installer optionally invokes it.
- **`keyring`** is imported by `src/ai_sw_bridge/checkpoint/crypto.py` but is a `[dev]` dep, not a runtime one — a wheelhouse-closure audit item (§9.2).
- **No installer artifact exists** — greenfield (`installer/`, `tools/build_installer.py` are new).

---

## 4. Scope

### 4.1 In scope
- `tools/build_installer.py` — the staging script (fetch standalone CPython, `pip download` the offline wheelhouse, assemble the payload tree, invoke `ISCC.exe`).
- `installer/ai-sw-bridge.iss` — the Inno Setup script (per-user install, offline pip-install, `pywin32_postinstall`, PATH, optional `--register`, uninstall).
- A new **windows `installer` job in `release.yml`** (`needs: [test]`) that runs the staging script, silent-install-smokes the output, and attaches the unsigned `.exe` to the GitHub Release.
- Operator documentation: SmartScreen walkthrough + the `pipx` fallback, in the operator guide and the Release notes.

### 4.2 Out of scope (non-goals — named intentionally)
- **Code signing / EV cert / SmartScreen reputation** (no budget — §2 A2.5).
- **MSI / winget / Chocolatey packaging** (Inno `.exe` only).
- **Auto-update** (re-run the installer; it's idempotent per §5.4).
- **Bundling SOLIDWORKS** (a hard prerequisite the operator already has — the bridge is a SW automation client).
- **All-users / `Program Files` install** requiring UAC elevation (§5.1 chooses per-user, no-admin).
- **Changing any runtime/engine behavior** — this phase only packages.

---

## 5. The build topology

### 5.1 Install target & privilege model
Per-user, **no UAC**: Inno `PrivilegesRequired=lowest`, `DefaultDirName={localappdata}\Programs\ai-sw-bridge`. Layout on the operator's disk:

```
%LOCALAPPDATA%\Programs\ai-sw-bridge\
  runtime\            <- python-build-standalone CPython (python.exe, Lib\, Scripts\)
  wheelhouse\         <- bundled offline wheels (removed post-install, or kept for repair)
  README-first.txt    <- SmartScreen note + pipx fallback + "SOLIDWORKS required"
```

The private interpreter *is* the isolation — no venv layer needed; `pip install` targets `runtime\`'s own `site-packages`.

### 5.2 Stage 1 — `tools/build_installer.py` (pre-build, on a Windows host / CI)
1. **Fetch the interpreter:** download a pinned `python-build-standalone` release (CPython **3.12.x**, `x86_64-pc-windows-msvc`, `install_only` archive), verify its SHA-256 against a pinned digest, unpack into `staging\runtime\`.
2. **Build the wheelhouse:** `runtime\python.exe -m pip download --dest staging\wheelhouse --only-binary=:all: .[mcp]` — resolves the full runtime closure as `win_amd64`/cp312 wheels using the *bundled* interpreter (guarantees ABI match). Then `python -m build --wheel` the project and drop its wheel in too.
3. **Stage ancillaries:** copy `installer/ai-sw-bridge.iss`, `README-first.txt`, and a post-install helper into `staging\`.
4. **Compile:** invoke `ISCC.exe staging\ai-sw-bridge.iss /DAppVersion=<tag>` → `dist/ai-sw-bridge-setup-<version>.exe`.

The script is **idempotent and locally runnable** (a maintainer can produce the same `.exe` on their Windows box for dev iteration); CI just runs it in a clean runner.

### 5.3 Stage 2 — `installer/ai-sw-bridge.iss` install-time `[Run]` sequence
Executed on the operator's machine, in order, all offline:
1. `runtime\python.exe -m pip install --no-index --find-links "{app}\wheelhouse" ai_sw_bridge[mcp]` — installs the app + deps into the private interpreter; **generates the 23 `Scripts\*.exe` shims**.
2. `runtime\python.exe runtime\Scripts\pywin32_postinstall.py -install` — places `pythoncomXX.dll`/`pywintypesXX.dll` so COM dispatch works (the step the embeddable zip could not do).
3. Add `{app}\runtime\Scripts` to the **user** `PATH` (HKCU `Environment`, `ChangesEnvironment=yes`, broadcast `WM_SETTINGCHANGE`).
4. **Optional checkbox** (default on): `runtime\Scripts\ai-sw-doctor.exe --register` — wires the MCP server into `claude_desktop` (timestamped backup, per Phase 1).

Uninstall removes `{app}\` and the PATH entry.

### 5.4 Idempotence & repair
Re-running the installer over an existing install re-runs `pip install` (a no-op or upgrade) and re-applies PATH/registration — safe to run twice. The bundled `wheelhouse\` supports offline repair.

---

## 6. Operator UX — the zero-budget realities

### 6.1 SmartScreen (unsigned)
Downloading and running an unsigned `.exe` triggers **"Windows protected your PC"** (SmartScreen) and possibly a browser download warning. This is documented verbatim in `README-first.txt`, the operator guide, and the Release notes:

> This installer is **not code-signed** (open-source, no certificate). Windows SmartScreen will warn you. To proceed: click **More info → Run anyway**. If you'd rather not run an unsigned installer, use the `pipx` method below instead.

### 6.2 The `pipx` fallback (the trusted alternative)
The Phase-1 path, documented alongside the installer as the equal-status trusted option for operators who have (or will install) Python or decline the unsigned `.exe`:

```
pipx install git+https://github.com/Thomas-Tai/ai-sw-bridge
ai-sw-doctor --register
```

### 6.3 Prerequisite honesty
`README-first.txt` and the guide state plainly: **SOLIDWORKS must already be installed** (the bridge drives it via COM); the installer bundles Python, **not** SOLIDWORKS.

---

## 7. Testing (seatless, on the CI windows runner)

No SOLIDWORKS seat exists in CI, so the installer is proven on its **COM-free happy path** — which is exactly what the existing `operator-install-smoke` job already validates:
1. **Build gate:** the staging script + `ISCC` must produce a non-empty `.exe` (compile success).
2. **Silent install:** `ai-sw-bridge-setup-*.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART`.
3. **Smoke (no seat):** assert `runtime\Scripts\ai-sw-build.exe` exists; `ai-sw-build --list-kinds` runs (COM-free); `runtime\python.exe -c "import win32com.client"` (proves `pywin32_postinstall` succeeded); `import ai_sw_bridge.mcp.server`.

This runs inside the new `installer` job after the build step — a real end-to-end install proof that needs no license.

---

## 8. Definition of Done

- [ ] `tools/build_installer.py` fetches a pinned+checksummed `python-build-standalone` CPython 3.12, builds the offline `.[mcp]` wheelhouse, and drives `ISCC`.
- [ ] `installer/ai-sw-bridge.iss` — per-user/no-UAC; offline `pip install`; `pywin32_postinstall`; user-PATH; optional `--register`; clean uninstall.
- [ ] `release.yml` gains a windows `installer` job (`needs: [test]`) that builds, **silent-install-smokes** (§7), and attaches the unsigned `.exe` to the GitHub Release.
- [ ] Local reproducibility: the staging script produces the same `.exe` on a maintainer Windows box.
- [ ] Operator docs: SmartScreen walkthrough + `pipx` fallback + SOLIDWORKS-prerequisite, in the operator guide and Release notes; `README-first.txt` bundled.
- [ ] Wheelhouse-closure audit resolved (§9.2 — `keyring`/`checkpoint.crypto`).
- [ ] Seat-safe suite still green; live seat untouched (this phase is COM-free — no seat needed).
- [ ] Branch `docs/commercial-elevation` only; isPrivate-guarded FF push to master.

---

## 9. Risks & open decisions

### 9.1 Risks & mitigations
| Risk | Mitigation |
|---|---|
| **SmartScreen scares operators off** | Documented walkthrough (§6.1) + equal-status `pipx` fallback (§6.2). Accepted cost of zero-budget. |
| **Wheelhouse ABI mismatch** (wrong py/platform wheels) | `pip download` is run *by the bundled interpreter itself* with `--only-binary=:all:`, so the wheels match the shipped ABI by construction. |
| **`python-build-standalone` URL/version drift** | Pin a specific release tag **and** SHA-256; the build fails loud on mismatch. |
| **`pywin32` COM DLLs not registered** | Explicit `pywin32_postinstall -install` step (§5.3.2) + the CI smoke imports `win32com.client` to prove it. |
| **Installer size** (~80–150 MB: numpy + pywin32 + pydantic-core + CPython) | Acceptable — the operator already runs a multi-GB SOLIDWORKS install. Note the size in Release notes. |
| **Untested CI job until a tag is cut** | §9.3 — optional `workflow_dispatch` to build+smoke without publishing. |

### 9.2 Wheelhouse closure — `keyring` (OPEN DECISION)
`checkpoint/crypto.py` imports `keyring` (a `[dev]` dep). If any installed-happy-path or MCP flow reaches that import, the offline install breaks (no `keyring` wheel). **Recommendation:** during the plan, audit the import (lazy/guarded vs eager); if runtime-reachable, add `keyring` to the wheelhouse explicitly (`pip download … keyring`) rather than promoting it to a hard runtime dep. (Ratify approach.)

### 9.3 CI test without cutting a release (OPEN DECISION)
The `installer` job only fires on a real `v*.*.*` tag. **Recommendation:** add a `workflow_dispatch` trigger that runs the build + silent-install-smoke and uploads the `.exe` as a **workflow artifact only** (no Release attach, no publish) — so the pipeline is testable before a real tag, without minting a public release. (Ratify or defer.)

### 9.4 Bundled Python version (OPEN DECISION)
**Recommendation: CPython 3.12** — the primary of the CI matrix (`3.10/3.12/3.14`), broadest wheel availability today. (Ratify or pick another within `>=3.10`.)

---

## 10. Deliverable map (informs the plan, not the plan itself)

- `tools/build_installer.py` — staging + ISCC driver (fetch standalone CPython, offline wheelhouse, compile).
- `installer/ai-sw-bridge.iss` — the Inno Setup script.
- `installer/README-first.txt` — bundled operator note (SmartScreen + pipx + SOLIDWORKS prereq).
- `.github/workflows/release.yml` — new `installer` windows job (`needs: [test]`, build + smoke + attach).
- Operator guide + `CHANGELOG.md` — SmartScreen walkthrough, `pipx` fallback, install instructions.

## 11. Success criterion (one sentence)

After Phase 5B, a CAD operator with SOLIDWORKS but no Python can install `ai-sw-bridge` by double-clicking one unsigned installer — navigating a documented SmartScreen prompt — and land a fully-working private interpreter with all 23 CLI verbs, a registered MCP server, and a `pipx` escape hatch, minted reproducibly by CI only from a green tagged commit.
