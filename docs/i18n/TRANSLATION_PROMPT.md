# Translation prompt for ai-sw-bridge docs

Use this prompt with Claude Sonnet, GLM-4.6, GPT-5, or any other capable LLM to translate the bridge's user-facing documentation into a target natural language. The English source remains canonical; translations are siblings under `docs/i18n/<locale>/`.

## How to use

1. Copy the prompt block below.
2. Replace the four `{{...}}` placeholders at the top of the prompt with your target language details. For the two currently planned languages, use:
   - **Traditional Chinese**: `{{LANGUAGE_NAME}} = Traditional Chinese (繁體中文)`, `{{LOCALE}} = zh-TW`, `{{REGION_NOTE}} = Use Traditional Chinese characters as written in Taiwan. Prefer Taiwanese technical vocabulary (e.g. 軟體 not 软件, 程式 not 程序).`, `{{TARGET_DIR}} = docs/i18n/zh-TW/`
   - **Simplified Chinese**: `{{LANGUAGE_NAME}} = Simplified Chinese (简体中文)`, `{{LOCALE}} = zh-CN`, `{{REGION_NOTE}} = Use Simplified Chinese characters as written in mainland China. Prefer mainland technical vocabulary (e.g. 软件 not 軟體, 程序 not 程式).`, `{{TARGET_DIR}} = docs/i18n/zh-CN/`
3. Paste the source files as attachments or inline below the prompt. The
   minimum translation surface is `README.md` and `docs/known_limitations.md`;
   `docs/why_no_addim2.md` is recommended because the new README links to it
   from the build-modes line. Other docs (`spec_reference.md`, `known_gotchas.md`,
   `architecture.md`) can be added as the project's translation appetite grows.
4. Run. The model should produce one output file per source file at the paths
   specified.
5. Review the **DO-NOT-TRANSLATE list** output (the model is asked to emit this
   as a checkpoint) against the actual translation to catch any leaked
   technical terms.

## The prompt

```
You are translating user-facing documentation for ai-sw-bridge, an open-source
tool that lets AI assistants drive SOLIDWORKS through the COM API. The source
is in English; translate it into {{LANGUAGE_NAME}}.

Target language: {{LANGUAGE_NAME}}
Locale code: {{LOCALE}}
Region/dialect note: {{REGION_NOTE}}

Write the translated files to these paths (relative to the repo root):
  {{TARGET_DIR}}README.md
  {{TARGET_DIR}}known_limitations.md
  (and one output file per additional source file pasted below, mirroring
  the source's filename under {{TARGET_DIR}})

# Your goals, in order of priority

1. **Preserve every technical identifier verbatim.** This is the most important
   rule. Translating a method name or flag will silently break the docs for
   any reader who tries to copy-paste the example. The DO-NOT-TRANSLATE list
   below is non-negotiable.
2. **Translate prose, not code.** Sentences in body text get translated.
   Anything inside backticks, code fences, JSON snippets, file paths, URLs,
   commit hashes, and CLI invocations stays in English exactly as written.
3. **Match register.** The source is direct and technical — no marketing
   fluff. Keep that voice. If the English says "the bridge", don't translate
   it as "this wonderful tool". If the English warns the reader, the
   translation warns the reader too.
4. **Localize examples that contain natural-language strings.** A JSON spec
   with a `_comment` field containing English prose: the JSON keys stay
   English, but the prose inside the comment string gets translated. Same
   for stderr WARNING messages quoted inside prose explanations (translate
   only when they appear as illustrative text, never when they document the
   actual byte-for-byte output of the tool).

# DO-NOT-TRANSLATE list

These are technical identifiers. They MUST appear verbatim in your output.
If you find yourself "naturalizing" any of these (e.g. transliterating
"SOLIDWORKS" into a phonetic form), revert immediately.

## Tool, file, and library names
- ai-sw-bridge, ai-sw-build, ai-sw-observe, ai-sw-mutate, ai-sw-codegen, ai-sw-probe
- SOLIDWORKS, SldWorks.Application, COM, pywin32, win32com, EnsureDispatch
- Python, JSON, VBA, VBE, SLDPRT, .swp, .bas, .chm
- Claude, ChatGPT, Codex, MCP

## SW API surface (interfaces, methods, enums)
- ISldWorks, IModelDoc2, IModelDocExtension, IFeatureManager, ISketchManager,
  IEquationMgr, IFeature, ISimpleFilletFeatureData2, ISketch, ISketchSegment,
  ISketchRelation, IRelationManager, IFace2, IEntity, IBody2
- NewDocument, GetUserPreferenceStringValue, GetUserPreferenceToggle,
  SetUserPreferenceToggle, SendKeys, SelectByID, SelectByID2, ClearSelection2,
  AddDimension2, AddSpecificDimension, FeatureByPositionReverse, EditRebuild3,
  EditUndo2, Parameter, GetFeatureCount, SaveBMP, GetPartBox, FeatureExtrusion2,
  FeatureExtrusion3, FeatureCut4, FeatureCut5, FeatureFillet3, CreateDefinition,
  CreateFeature, InsertSketch, CreateCornerRectangle, CreateCenterRectangle,
  CreateCircle, CreateCircleByRadius, CreateCenterLine, Add2, GetTypeName,
  GetTypeName2, GetNextFeature, RunMacro, RunMacro2, SaveAs3, GetEquationMgr,
  FilePath, LinkToFile, AutomaticRebuild, UpdateValuesFromExternalEquationFile,
  Initialize, DefaultRadius, GetTitle, GetFirstDocument, GetNext, ActiveDoc,
  FirstFeature, ShowNamedView2, ActivateDoc2, ActivateDoc3, ViewZoomtofit2,
  ActiveView, Scale2, GetPartBox, Extension, RunCommand, GetActiveSketch2,
  RelationManager, GetRelations, DeleteRelation, GetRelationType, Suppressed,
  Select2, Select4, Normal, GetClosestPointOn, GetBodies2, GetFaces, EditSketch,
  GetStartPoint2, GetEndPoint2, ConstructionGeometry, FeatureManager,
  GetPathName, OpenDoc6, GetCount, Equation, Value
- swEndConditions_e, swStartConditions_e, swDocumentTypes_e, swDimensionType_e,
  swSelectType_e, swSimpleFilletType_e, swFeatureNameID_e,
  swFeatureFilletOptions_e, swFeatureFilletType_e, swFilletOverFlowType_e,
  swFeatureFilletProfileType_e, swConstraintType_e, swFileSaveError_e
- swEndCondBlind, swEndCondThroughAll, swEndCondThroughNext, swEndCondMidPlane,
  swEndCondThroughAllBoth, swEndCondUpToSurface, swStartSketchPlane,
  swConstRadiusFillet, swFaceFillet, swFullRoundFillet, swFmFillet,
  swInputDimValOnCreate, swSketchEnableOnScreenNumericInput,
  swDefaultTemplatePart, swDocPART, swDocASSEMBLY, swDocDRAWING,
  swFileSaveError_NoError, swSolidBody

## Bridge-internal Python identifiers (post-2026-05 class refactor)

The class hierarchy under `src/ai_sw_bridge/spec/sketches/` and its
supporting modules are part of the public layout shown in the README.
Never localize:

- SketchHandler, SketchFrame
- RectangleOnPlaneHandler, RectangleOnFaceHandler, CircleOnPlaneHandler,
  CircleOnFaceHandler, CirclesOnFaceHandler
- BuildContext, BuiltFeature, DeferredDim, FeatureType, FaceFrame
- Module paths: `src/ai_sw_bridge/spec/_build_context.py`,
  `src/ai_sw_bridge/spec/_face_geometry.py`,
  `src/ai_sw_bridge/spec/_sketch_primitives.py`,
  `src/ai_sw_bridge/spec/sketches/base.py`,
  `src/ai_sw_bridge/spec/sketches/rectangle_on_plane.py` (and the four
  siblings under `sketches/`)
- Method names on these classes: `build`, `_enter_sketch`, `_draw_geometry`,
  `_add_dimensions_inline`, `_record_deferred_dimensions`,
  `_strip_relations`, `_finalize`
- Tool script names: `tools/feature_tree_diff.py`, `tools/chm_extract.py`,
  `tools/gen_api_markdown.py`, `tools/gen_sw_types.py`

## Spec schema and CLI flags (NEVER translate)
- schema_version, name, locals, features, type, plane, sketch, of_feature,
  face, width, height, depth, diameter, radius, distance, angle, count,
  spacing, center, edges, circles, centerline, start, end, axis, mode, seed,
  spec_path, flip, rhs, u, v, x, y, z
- sketch_rectangle_on_plane, sketch_rectangle_on_face, sketch_circle_on_plane,
  sketch_circle_on_face, sketch_circles_on_face, boss_extrude_blind,
  cut_extrude_through_all, cut_extrude_blind, fillet_constant_radius,
  chamfer_edge, linear_pattern, circular_pattern, mirror_feature,
  revolve_boss, simple_hole
- equal_distance, distance_angle (chamfer modes)
- Front, Top, Right (when used as plane names in spec context)
- +x, -x, +y, -y, +z, -z (face direction codes)
- --no-dim, --deferred-dim, --save-as, --validate-only, --use-active-doc,
  --width, --height, --fit-view, --filename
- Propose-Approve-Execute, propose, dry_run, commit, undo_last_commit,
  proposal_id, var, new_value

## File and code references (NEVER translate)
- Paths like src/ai_sw_bridge/spec/builder.py, docs/known_limitations.md,
  spikes/phase0/spike_p_fillet_pipeline.py, examples/tension_bracket/spec.json
- File extensions: .py, .json, .md, .swp, .bas, .sldprt, .txt, .chm
- Commit hashes: any 7-character hex token following a word like "commit",
  appearing in parens like "(see 83256d5)", or formatted as a markdown link
  to a GitHub commit URL. Examples currently appearing in the docs:
  83256d5, c560e97, e44aaa6, 66822a5, c3b5af4, 437ffe5, bd3b5a9, 67bda48,
  45dce1e, 8320a60, 778e300, c760600, d80182e, 4b7477e. (When adding a new
  hash to the docs, list it here so future re-translations preserve it.)
- URLs (github.com/..., codestack.net/..., etc.)
- Code snippets inside ``` fences, regardless of language
- JSON object keys (translate prose VALUES inside string fields where they
  are illustrative; never translate keys)

## Hardware / domain references that should stay verbatim
- S1b_Conveyor, MMP, TensionBracket, IdlerRoller, SpringEndCap, SideGuide,
  AxleEndCap, MotorMountPlate
- Variable names from locals.txt: S1B_TB_X, S1B_TB_Y_OUTBOARD, S1B_TB_CAP_T,
  S1B_AXLE_CLEARANCE, S1B_FRAME_PLATE_T, S1B_TB_BORE, S1B_MMP_H, S1B_MMP_W,
  S1B_MMP_T, S1B_COUPLER_CLEARANCE, S1B_MOTOR_FLANGE_OD, S1B_MOTOR_HOLE_PITCH,
  S1B_MMP_FRAME_HOLE_PITCH, S1B_MMP_FRAME_HOLE_DIA, S1B_PRINT_FILLET_R
- Dim references: D1, D2, D1@SK_Body, D1@Fillet_TopRightEdge, etc.

# Things that benefit from translation (the actual prose)

- Section headings (translate the words, keep code-formatted identifiers
  verbatim — e.g. "## Why this design" -> "## 為什麼這樣設計" but
  "## Two build modes" with internal `--no-dim` references keeps the flag)
- Body paragraphs explaining what something is, why a decision was made,
  what a tester should expect
- Table column headers in plain prose ("Purpose", "Limits", "When to use")
  — but NOT the cell content that names a method/flag/file
- _comment field text inside JSON examples (this is illustrative prose
  embedded in a code block; localize it so readers in the target language
  understand the example)
- Captions, intros, transition sentences
- Error messages QUOTED inline for explanation (translate the explanation;
  keep the actual error string verbatim so readers can grep for it)

# Style guidance for {{LANGUAGE_NAME}}

- Use technical vocabulary that a working software engineer would recognize.
  When an English term has no clean translation (e.g. "sketch", "extrude",
  "fillet" in CAD context), prefer the SOLIDWORKS official localized term
  if you know it; otherwise keep the English in parentheses after a best-
  effort translation, e.g. "草圖 (sketch)" the first time it appears.
- Sentence-final emphasis: if the English uses bold or italics for emphasis,
  preserve the same markdown markers around the corresponding phrase in the
  target language.
- Numbers, units (mm, MB, °, KB/s), and timing references (~3s, ~16 ticks)
  stay in their English / numeric form.
- Markdown structure stays identical: same headers at the same levels, same
  list markers, same code-fence language tags, same link syntax. Do not
  reflow paragraphs; one source paragraph = one translated paragraph.

# Output format

Produce TWO complete files, each fully translated:

  File 1: {{TARGET_DIR}}README.md
  File 2: {{TARGET_DIR}}known_limitations.md

At the very top of each translated file, add a single-line language-switcher
comment AFTER the title heading. Use this exact format:

  # <translated title>

  > **Language**: [English](../../README.md) · {{LANGUAGE_NAME}}

(adjust the relative path to point back to the English source from the
translated file's location: README in {{TARGET_DIR}} reaches the English
README via ../../README.md; known_limitations in {{TARGET_DIR}} reaches the
English version via ../../../docs/known_limitations.md)

After the two translated files, output ONE additional section titled
"## Translation audit" containing:

1. A bullet list of every English technical term you encountered and the
   exact form you used in the translation (e.g. "`sketch_rectangle_on_face`
   → kept verbatim", "`fillet` (CAD operation) → 圓角 (the verbatim English
   appears once in parens on first use)").
2. A list of any sentences in the source that you found ambiguous or hard
   to translate faithfully, with your interpretation noted. The maintainer
   reads this list to catch translation drift.
3. A confidence rating from 1-5 for how faithfully the translation preserves
   the source's technical content. 5 = "I'm certain a tester following this
   would not be misled". Below 4 means the maintainer should review carefully.

# Final reminders

- If you are about to translate ANY identifier from the DO-NOT-TRANSLATE
  list, stop and reconsider. That list exists because each translation of a
  technical identifier would break tests, examples, or grep workflows for
  someone.
- The English source is authoritative. If you spot what looks like a typo
  or technical inaccuracy in the source, flag it in the Translation audit
  rather than silently "correcting" it.
- Do NOT add new content (intro paragraphs, translator's notes inside body
  text, "as the original states..." framing). Translate what is there; flag
  separately what you wished was there.

Now translate. Source files follow below.

[paste README.md here]

[paste docs/known_limitations.md here]
```

## After running the prompt

1. Save the two output files to `docs/i18n/<locale>/README.md` and `docs/i18n/<locale>/known_limitations.md`.
2. Add a language-switcher line to the **English** `README.md` so readers can find translations:
   ```markdown
   > **Language**: English · [繁體中文](docs/i18n/zh-TW/README.md) · [简体中文](docs/i18n/zh-CN/README.md)
   ```
   (only list the locales that have actually been translated)
3. Read the "Translation audit" section the model emitted. Spot-check 3-5 entries from its DO-NOT-TRANSLATE confirmation list — open the translated file and grep for the English form to confirm it survived.
4. Build the filleted_box example following ONLY the translated README. If it works, the translation is field-ready. If it doesn't, the failure usually points at a specific mistranslation; file an issue.

## Maintenance

When the English docs change (e.g. a new feature primitive ships), the translations drift. Two ways to keep them in sync:

- **Manual re-run**: re-run this prompt against the updated English source. Cheap if changes are small; lossy if the translator picks different phrasings for previously-translated paragraphs.
- **Diff-based update**: paste only the `git diff` of the English doc since the last translation, plus the current translated file, and ask the model to apply the equivalent change in the target language. Preserves prior phrasings but requires more careful prompting.

Recommended: keep a `translated-from: <commit_hash>` line in the frontmatter of each translated file so future re-translation can target the diff from that commit rather than the whole file.

### Structural rewrites: do a full re-translation, not a diff

If the English source has been substantially restructured (sections deleted, moved, or rewritten — not just edited paragraph-by-paragraph), the diff-based update is the *wrong* tool. The current `docs/i18n/zh-{TW,CN}/README.md` files were translated against an older 514-line README; the current English README is 164 lines after a 2026-05-20 audience-pivot rewrite. A re-translator pointed at the diff will produce a Frankenstein file with paragraphs from both versions.

How to recognize this case:

- Source line count changed by more than ~30%
- A whole section heading was added, removed, or renamed in the source
- The README's lede paragraph changed audience or framing

When any of these is true: ignore the existing translation entirely, re-run this prompt fresh, and replace the translated file wholesale. Carry over only the `> **Language**: ...` switcher line at the top.

### New docs added since last translation

The original prompt translated only `README.md` and `docs/known_limitations.md`. The bridge has since added several user-facing docs that are linked from the new README:

- `docs/why_no_addim2.md` — build-modes deep-dive (linked from README's CLI table)
- `docs/spec_reference.md` — per-primitive schema reference
- `docs/known_gotchas.md` — pywin32 marshalling surprises
- `docs/architecture.md` — phases + design rationale
- `docs/AGENTS.md` — agent briefing (also user-facing as "what the AI reads first")

These are not yet translated. Add any of them to the source-file list when pasting the prompt; they are user-facing and benefit from translation. The DO-NOT-TRANSLATE list above already covers identifiers that appear in them.
