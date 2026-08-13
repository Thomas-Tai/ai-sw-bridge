> OPTIONAL — decide at Task 10 whether to include (spec open question #3).

# L5 — Product Hunt draft

This is a **draft** for a human to review and, if Task 10 decides to launch
on Product Hunt, post there. Nothing here has been submitted.

## Tagline

```
Drive your real SOLIDWORKS seat from a JSON spec — human-approved, every step
```

## Description

ai-sw-bridge drives a real, licensed SOLIDWORKS seat from a JSON spec —
native `.SLDPRT` / `.SLDASM` / `.SLDDRW` with an editable feature tree, not
a STEP dump from a throwaway kernel. Every change goes through the same
gate: propose → approve → execute. The agent proposes a spec, you approve
it, and only then does it execute against your live seat — nothing runs
silently.

It's not friction-free: a class of features (lofts, ribs, wraps, combines
and the like) can't be driven out-of-process, so the bridge refuses them
cleanly instead of handing you a broken part, and dimensioned mode still
needs a human tick on a handful of SOLIDWORKS dialogs. Full list in the
repo's Known Limitations doc.

**Before you try it:** ai-sw-bridge is proprietary/commercial software
(MIT-licensed through v1.4, commercial from v1.5 on), it requires a paid
SOLIDWORKS 2021+ seat to build geometry, and it's Windows-only. No
SOLIDWORKS seat? You can still author and lint a real spec offline with
zero license (schema, references, locals, DFM lint) — that's Tier A,
covered in the 5-minute Quickstart.

## First comment (post this yourself, right after launching)

I'm the maker. A few things worth saying before you upvote or install:

**Why it exists.** I wanted an agent to drive the CAD tool I actually
design in, and keep the output a real, editable feature tree — not a dead
STEP or mesh dump with the design intent stripped out.

**Cost and platform.** Proprietary/commercial (MIT through v1.4, commercial
from v1.5), a paid SOLIDWORKS 2021+ seat is required to build geometry, and
it's Windows-only (drives SOLIDWORKS over COM).

**No seat? Start with Tier A.** Author and lint a real spec entirely
offline, zero license — schema, references, locals, DFM lint. Building
actual geometry (Tier B) is what needs the licensed seat.

**The honest edges.** A class of features — lofts, ribs, wraps, combines
and the like — can't be driven out-of-process, so the bridge refuses them
cleanly rather than emit a broken part. In dimensioned mode, a handful of
SOLIDWORKS dimension dialogs still need a human tick. Both are tracked in
the repo's Known Limitations doc.

Try it / read the full argument:
`https://thomas-tai.github.io/ai-sw-bridge/?utm_source=producthunt.com&utm_medium=referral&utm_campaign=launch&utm_content=launch`

Code: `https://github.com/Thomas-Tai/ai-sw-bridge`

Happy to answer anything.
