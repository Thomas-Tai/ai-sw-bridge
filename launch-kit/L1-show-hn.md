# L1 — Show HN draft

This is a **draft** for a human to review and post to Hacker News. Nothing
here has been submitted. Copy the pieces below into the HN submission form
(title, URL) and post the first comment yourself right after.

## Title

```
Show HN: ai-sw-bridge – drive a real SOLIDWORKS seat from a JSON spec (MCP)
```

## URL

```
https://thomas-tai.github.io/ai-sw-bridge/?utm_source=news.ycombinator.com&utm_medium=referral&utm_campaign=launch&utm_content=show-hn
```

## Body (the post text)

ai-sw-bridge is an MCP server that drives a real, licensed SOLIDWORKS seat
from a JSON spec — native `.SLDPRT` / `.SLDASM` / `.SLDDRW` with a real,
editable feature tree, not a foreign STEP dump from a throwaway kernel. It's
not friction-free, and I'd rather say so up front than have you find out the
hard way: a whole class of features (lofts, ribs, wraps, combines and the
like) can't be driven out-of-process, so the bridge refuses them cleanly
instead of emitting a broken part, and in dimensioned mode a handful of
SOLIDWORKS dimension dialogs still need a human tick before they proceed.

Every change goes through the same three-step gate — propose, approve,
execute. The agent proposes a spec, you review and approve it, and only then
does it execute against your live seat. Nothing runs silently against your
model.

You don't need a SOLIDWORKS seat to try something today. You can author and
lint a real spec entirely offline with zero license — schema validation,
reference resolution, locals, DFM lint. That's Tier A. Building actual
geometry is Tier B, and that's where a running, licensed SOLIDWORKS 2021+
seat becomes required.

The landing page linked above has the full argument, the current list of
kernel walls, and a demo of the whole pipeline (part → assembly →
observe/DFM → drawing → export) on a live seat.

## First comment (post this yourself, right after submitting)

I'm the author — a few things worth saying plainly before anyone installs
this:

**Why it exists.** Every AI-CAD demo I'd seen produced a dead STEP or mesh
dump — geometry with no history, nothing you can keep editing in the tool
you actually design in. I wanted the agent to drive the CAD system I already
run and keep the feature tree native, so I built this instead.

**License and cost.** It's proprietary/commercial software — MIT-licensed
through v1.4, commercial from v1.5 onward. It also requires a paid
SOLIDWORKS 2021+ seat, and it's Windows-only (it drives SOLIDWORKS over
COM).

**No seat? Start with Tier A.** You can author and lint a real spec offline
with zero license — schema, references, locals, DFM lint. Building actual
geometry (Tier B) is what needs the licensed seat.

**The real kernel walls.** A class of features — lofts, ribs, wraps,
combines and the like — can't be driven out-of-process, so the bridge
refuses them cleanly rather than emit a broken part. In dimensioned mode, a
handful of SOLIDWORKS dimension dialogs still need a human tick before
they'll proceed. Both are listed, and kept current, in the repo's Known
Limitations doc.

Code and docs: `https://github.com/Thomas-Tai/ai-sw-bridge`. Happy to answer
anything.
