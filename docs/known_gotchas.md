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

If you figure out how to write back a valid binary `.swp` from a `.bas` file, `SldWorks.RunMacro` / `RunMacro2` will execute it. PRs welcome.

### B-rep: multi-body features duplicate role hints across bodies

A feature that produces two or more solid bodies (e.g. a multi-body
boss extrude, or a pattern whose instances don't merge) yields one
face set **per body**. Each body's `+z_outboard` face carries the
same `role_hint`, so a downstream `face_role="+z_outboard"` lookup
will hit :class:`FaceAmbiguityError` unless you disambiguate.

**How to recognize**
- `brep_interrogation` manifest shows `body_id` values `0` and `1`
  (or higher) on faces of the same feature.
- :class:`brep.resolver.FaceAmbiguityError` at build time, with
  the candidate fingerprints listed in the error message.

**Workaround**
- Resolve by body: prefer `body_id=0` for the "main" body when you
  know the feature's intent. The resolver will grow a
  `body_id_hint` tiebreaker in a follow-up.
- Or split the feature in the spec so each body has its own
  feature name — the manifest then keys by feature, and the
  ambiguity goes away.

See *(retired v0.13.0; see decisions.md 2026-05-28 entry)* §2.10 row 1
(multi-body part).

### B-rep: surface bodies have no volume — `inboard`/`outboard` is meaningless

A sheet / surface body (the result of a surface-extrude or an
imported STL) is interrogated the same way as a solid, but the
`role_hint` heuristic deliberately skips the
`{+/-}{axis}_{inboard|outboard}` disambiguation: a surface has no
inside, so "inboard" would be a fabrication.

**How to recognize**
- `brep.faces[*].is_surface == true` in the manifest.
- `role_hint == "oblique"` even when the normal is axis-aligned
  (the heuristic falls back to oblique because the inboard/outboard
  comparison requires a signed volume).

**Workaround**
- Target surface faces by `fingerprint` (stable across rebuilds)
  or by `normal` directly. `face_role` matching still works for the
  axis-aligned case when the surface is on the part boundary.

See *(retired v0.13.0; see decisions.md 2026-05-28 entry)* §2.10 row 2
(surface body).

### B-rep: suppressed features emit an empty brep block with `status: "suppressed"`

If a feature is suppressed in the feature tree, `IFeature.IsSuppressed()`
returns True and the interrogator skips face walking entirely. The
manifest still contains the brep block for the feature, but its
`faces` list is empty and the block carries `status: "suppressed"` so
downstream resolvers can distinguish "intentionally absent" from "bug
in interrogation."

**How to recognize**
- `brep_manifest.features["<name>"]["status"] == "suppressed"`
- `brep_manifest.features["<name>"]["faces"] == []`
- `FaceResolutionError` with `available_roles=[]` from any child
  feature targeting the suppressed parent.

**Workaround**
- Unsuppress the feature in SW before running the build, OR
- Use a different parent feature as the `of_feature` reference, OR
- Move the suppressed feature later in the tree so child features
  don't reference it as a `face_role` source.

See *(retired v0.13.0; see decisions.md 2026-05-28 entry)* §2.10 row 4
(suppressed feature).

### B-rep: hidden faces are included but flagged `is_hidden: true`

A face hidden via `Hide` in the feature manager still exists in the
SW model — `IFeature.GetFaces()` returns it and `IFace2.GetBox` /
`Normal` / `GetArea` all read normally. The interrogator includes
the face in the manifest but sets `is_hidden: true` so the resolver
can deprioritize it when scoring `face_role` candidates.

Order of fallback on older SW builds: `IFace2.IsHidden` is preferred;
if that read fails, the interrogator falls back to `IFace2.Visible`
(the inverse).

**How to recognize**
- `manifest["features"][i]["faces"][j]["is_hidden"] == true`

**Workaround (only if needed)**
- Make the face visible in the SW feature manager before the build.
- Hidden faces don't break interrogation — this gotcha is informational.

### B-rep: ImportFeature falls back to body-level walk

An `IFeature` returned by an imported body (STEP / IGES / Parasolid)
has `GetTypeName2() == "ImportFeature"`. These features do NOT expose
native face topology through the feature handle — `IFeature.GetFaces`
returns nothing useful on the dispatch proxy. The interrogator
detects the case and walks `IFeature.GetBody()` directly.

If body-level walk also can't reach geometry (rare — happens when the
import is corrupt or `GetBody` returns null), the manifest entry's
`faces` is `[]` and `status == "imported"`.

**How to recognize**
- `manifest["features"][i]["status"] == "imported"` AND `faces == []`
  → SW returned no body chain for the import.
- The same feature works as a `face_role` parent if `faces` is
  non-empty — body-level walk produced real topology.

**Workaround**
- Re-import the source file (STEP/IGES) with a different option set
  (heal solids, knit surfaces) so SW exposes the body topology.
- Or use the imported feature's downstream child features as
  `face_role` parents instead.

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

For incident-registry entries (API said "OK" but wasn't), add a row in
[`com_failure_modes.md`](com_failure_modes.md) instead. That doc is the
canonical taxonomy of silent-failure modes with stable IDs (S-*, G-*,
X-*, E-*, U-*). This file is for gotchas and workarounds; that file is
for "the return code lied" incidents.

When you hit something new and weird:

1. If it's a silent-failure incident (misleading sentinel), add a row in
   [`com_failure_modes.md`](com_failure_modes.md) following its ID
   convention
2. If it's a gotcha or workaround, add a section here with the symptom,
   root cause, and mitigation
3. If there's a mechanical workaround, add a `try/except` + structured
   error message in the relevant module
4. If the mitigation needs a global change (e.g. always set some
   user-pref before doing X), update `CLASS_RELATION_MAP.md` too
