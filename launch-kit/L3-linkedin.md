# L3 — LinkedIn article draft

This is a **draft** for a human to review and publish as a LinkedIn article.
Nothing here has been posted. Copy the headline and body below into
LinkedIn's article editor; the "Publish settings" note at the end is
guidance for the author's own publishing step, not text meant to appear in
the visible article.

## Headline

```
Your SOLIDWORKS seat, driven by an agent you approve at every step
```

## Article body

I didn't build ai-sw-bridge so an AI agent could replace your drafting
judgment. I built it so an agent could act *inside* your judgment — propose
a change, wait for you to say yes, then execute against your real, licensed
SOLIDWORKS seat. If you do CAD for a living, that distinction is the whole
pitch.

**The gate, not the autopilot.** Every change goes through the same
three-step gate: propose → approve → execute. The agent drafts a spec — the
dimensions, the features, the mates — you review it, and only after you
approve does anything touch your model. Nothing runs silently. If you've
ever watched an "AI does CAD" demo and wondered who's supervising it, the
answer here is: you are, every time.

**Why the output is a feature tree, not a shape.** The result is native
`.SLDPRT` / `.SLDASM` / `.SLDDRW` — the same kind of feature tree you'd get
building it by hand. Change a dimension later, hit rebuild, and it updates
the way your own work does. That's a different thing from a STEP or mesh
dump out of a throwaway kernel, where you can only push faces around after
the fact — the design intent that made the shape is gone. The landing page
has the full "which fits your job?" comparison if you want the two laid out
side by side.

**Where it actually breaks, plainly.** I'd rather you find out here than
mid-project: a class of features — lofts, ribs, wraps, combines and the
like — can't be driven out-of-process, so the bridge refuses them cleanly
instead of handing you a broken part. And in dimensioned mode, a handful of
SOLIDWORKS dimension dialogs still need a human tick before they'll proceed
— that's a SOLIDWORKS UI constraint, not something the bridge can route
around. Both are current in the repo's Known Limitations doc, and I keep
that list honest as the edges move.

**What it costs you, and what it doesn't.** ai-sw-bridge is
proprietary/commercial software — MIT-licensed through v1.4, commercial
from v1.5 onward — and it requires a paid SOLIDWORKS 2021+ seat. It's
Windows-only, because it drives SOLIDWORKS over COM. None of that is hidden
in fine print; it's on the front page.

You don't need a seat to see whether this is worth your time, either. You
can author and lint a real spec entirely offline, zero license — schema
validation, reference resolution, locals, DFM lint. That's Tier A, covered
in the 5-minute Quickstart. Building actual geometry against a live seat is
Tier B, and that's where the licensed SOLIDWORKS requirement kicks in.

If you spend your day in SOLIDWORKS and you've been skeptical of "AI does
your CAD" claims — you should be — this is built around the assumption that
your approval is what makes it safe to use, not an inconvenience to route
around.

Full argument, the current kernel-wall list, and a demo of the whole
pipeline (part → assembly → observe/DFM → drawing → export) on a live seat:
`https://thomas-tai.github.io/ai-sw-bridge/?utm_source=linkedin.com&utm_medium=social&utm_campaign=launch&utm_content=launch-article`

Canonical: https://thomas-tai.github.io/ai-sw-bridge/

## Publish settings note (for the author, not part of the visible article)

LinkedIn's own article editor doesn't expose a `rel=canonical` control. If
this piece is ever mirrored to a platform that does honor one (a personal
blog, a syndication target), set it explicitly so search engines credit the
landing page as the source of the argument:

```
<link rel="canonical" href="https://thomas-tai.github.io/ai-sw-bridge/">
```
