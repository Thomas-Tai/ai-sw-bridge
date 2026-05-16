# Known Gotchas

A catalog of the things we hit while building this and chose to document rather than hide. Read these before extending the package.

## pywin32 late-binding

We cannot use `win32com.client.gencache.EnsureDispatch("SldWorks.Application")` — it fails on most installs with *"This COM object can not automate the makepy process."* Without a typelib, every call goes through `IDispatch::Invoke` and certain argument types are unreachable.

### Symptoms

- **Zero-arg methods auto-invoke as properties.** `doc.GetPathName` returns the string, not a method. `doc.FeatureManager` returns the sub-Dispatch directly. `callable()` reports True for every CDispatch but calling the result throws `com_error(-2147352573, "Member not found.")`. Rule: never call CDispatch results.

- **Methods with COM-interface args fail "Type mismatch" or "Parameter not optional"**:
  - `SelectByID2(name, type, x, y, z, append, mark, **Callout**, options)` — the Callout arg is an interface; pywin32 can't marshal it. Use the legacy `SelectByID(name, type, x, y, z)` (5 args, replaces selection each call).
  - `GetErrorCode2(...)` — has an OUT parameter pywin32 can't unmarshal. Use legacy `GetErrorCode` (auto-invoked property, returns int).
  - `Save3(options, **ref errors**, **ref warnings**)` — OUT params. Use `doc.Save()` instead.
  - `RunMacro2(path, module, sub, options)` — silently rejects late-bound calls in some SW builds. We fall back to `RunMacro(path, module, sub)` (3 args).

### Mitigations in this codebase

- `sw_com.resolve(obj, name)` is just `getattr` — left in place as a marker so reviewers know we touched a CDispatch via late-binding.
- Every COM call is wrapped in `try/except` and returns a structured error dict; nothing leaks raw `com_error`.

## SOLIDWORKS API quirks

### `EquationMgr` exposes only manager-wide `Status`, not per-equation status

`Status` returns one int (0=ok, 1=syntax_error, 2=circular, 3=eval_error, 4=unknown, 5=dim_not_found). To attribute blame for a broken equation, snapshot the equation list before/after and diff.

### `EditRebuild3` does NOT re-import the linked locals file

Plain rebuild only re-solves what SW already has loaded. To pick up changes to `*_locals.txt`, call `EquationMgr.UpdateValuesFromExternalEquationFile` FIRST (it returns bool and auto-invokes as a property on attribute access). Then `EditRebuild3`. This package does both in `_force_rebuild` for you.

### `doc.Save()` returns False when nothing is dirty

If your `commit` operation changed a variable that the *active part* doesn't consume, the part isn't dirty and `Save()` returns False. This is NOT an error. The `*_locals.txt` file IS updated (the bridge writes it directly). Other parts that link the same file will pick up the change on their next reload.

### `EquationMgr.Add3` silently fails on some SW builds

`Add3(-1, formula, suppress, solveOrder)` — 4 args — returns -1 with no error on SW 2024 (rev 32.1.0). Use `Add2(-1, formula, solveOrder)` — 3 args. Source: [CodeStack add-equation example](https://www.codestack.net/solidworks-api/document/dimensions/add-equation/). This package's `parameterize.py` uses `Add2`.

### `RunMacro` rejects plain-text `.swp` / `.bas`

SW only consumes BINARY `.swp` files produced by its own VBA editor. The format is an OLE Compound Document (D0CF11E0 magic) with an embedded VBA project. We can READ this (via `oletools.olevba`) but we cannot reliably WRITE it. The Path C workflow accepts a 5-second manual paste in lieu of full automation.

If you figure out how to write back a valid binary `.swp` from a `.bas` file, the `run_macro` CLI is ready to invoke it. PRs welcome.

## File I/O gotchas (Windows)

### `msvcrt.locking` unlocks at the CURRENT file position

`LK_UNLCK` operates from wherever the file pointer is now. If you read the file (which advances position) and then unlock without seeking back to 0, Windows returns `EACCES` ("Permission denied") because you're trying to unlock a region that was never locked. Symptom: spurious permission errors on every second proposal.

Fix in this codebase: `os.lseek(fd, 0, os.SEEK_SET)` before BOTH lock and unlock.

### Cloud-sync tools (OneDrive, Dropbox) transiently hold exclusive handles

After an `os.replace`, the sync client may take 100-300ms to release its handle on the new file. The first `os.open(..., O_RDWR)` afterwards can fail with `EACCES`. This package retries with exponential backoff (10 attempts, 100-1000ms apart).

### Atomic write via `tmp + os.replace` is safe on Windows since 3.3

`os.replace` is atomic on NTFS within the same volume. We write to `<path>.tmp` then replace. SW's file watcher (when `LinkToFile=True`) picks up the change on the next solve trigger.

## Path C gotchas

### Recorded macros embed runtime-generated feature names

If your SW doc already had `Sketch1` before you started recording, your new sketch becomes `Sketch2` and the recording calls `Part.Parameter("D1@Sketch2")`. Replaying against a fresh doc (no prior sketches) makes the first sketch `Sketch1`, and the parameter lookup returns Nothing → runtime error 91.

**Always record from a fresh-doc state** (File > New > Part, then immediately start recording).

### "Modify dimension" popup interrupts replay

`AddDimension2` triggers SW's value-edit dialog. The recording captured your click-through but at replay time the dialog appears again. Workaround: press Enter to dismiss; the next line overwrites the value anyway.

Future fix: inject `swApp.SetUserPreferenceToggle swInputDimValOnCreate, False` at the macro start.

### VBA reserves leading-underscore variable names

`Dim _bridgeReload As Boolean` is a compile error. Use `bridgeReload`. (We did this once, then renamed.)

### `Part.Parameter("D1@X").Equation = "..."` doesn't exist in SW 2024

Throws error 438 ("object doesn't support this property or method"). Use `EquationMgr.Add2` instead — see above.

### Recordings include mouse-zoom telemetry

Every wheel-scroll during recording emits `Scale2`/`Translation3` calls. Harmless at replay but verbose. A future release of the parameterizer will strip these.

## Encoding / line-ending gotchas

- **`*_locals.txt` files**: SW reads them as ANSI on most builds. We write UTF-8 (no BOM) because it's a strict superset for ASCII variable names. If you need MBCS for non-Latin variable names, you'll need to revisit `locals_io.atomic_write`.

- **Generated `.bas`**: UTF-8, LF line endings. VBE accepts both LF and CRLF on paste; we picked LF for cross-platform diffing.

- **U+200B (zero-width-space) contamination**: We've seen this character (invisible in SW UI, present in equation expressions copy-pasted from PDFs or documentation) corrupt feature names. Symptom: parameter lookup returns Nothing even though the name looks right. Detect with a hex dump; fix by renaming the feature in SW.

## Where to extend this list

When you hit something new and weird:

1. Add a section here with the symptom, root cause, and mitigation
2. If there's a mechanical workaround, add a `try/except` + structured error message in the relevant module
3. If the mitigation needs a global change (e.g. always set some user-pref before doing X), update `architecture.md` too
