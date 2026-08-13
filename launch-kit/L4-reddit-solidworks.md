# L4 — r/SolidWorks post draft

This is a **draft** for a human to review and post to r/SolidWorks. Nothing
here has been submitted. This sub expects transparent self-promotion: say
up front that you're the author, keep the marketing language out, and
invite people to poke holes in it.

## Title

```
I built an agent-driven SOLIDWORKS bridge where you approve every change before it touches your model — looking for critique from people who actually use SW daily
```

## Body

I'm the author, posting this myself, so take the "I" seriously below — no
ghost-marketing here.

**What it is, in the way that matters to you first: you're in control the
whole time.** ai-sw-bridge drives your real SOLIDWORKS seat from a JSON
spec, through a three-step gate — propose → approve → execute. Nothing runs
against your model until you've looked at the proposed spec and said yes.
It's not autonomous drafting; it's closer to handing off the typing while
you keep the pen.

**Why I didn't just export STEP.** The output is a native `.SLDPRT` /
`.SLDASM` / `.SLDDRW` feature tree — the kind you can change a dimension on
and rebuild, same as anything you built by hand. That's the whole reason
this exists instead of letting an agent spit out a mesh or STEP dump: those
are dead the moment they're exported, you can only push faces around, the
design intent is gone.

**Where it breaks — told straight, because you'll hit these fast.** A class
of features can't be driven out-of-process at all: lofts, ribs, wraps,
combines, and similar. Rather than hand you a broken part, the bridge
refuses those cleanly. And in dimensioned mode, a handful of SOLIDWORKS
dimension dialogs still need you to click through by hand — that's a
constraint of the SOLIDWORKS UI, not something I can script around. Both
are tracked in the repo's Known Limitations doc, which I keep current as
the edges shift. If you work with SW daily, I'd genuinely like to know
which of those walls you'd hit first, or whether there are others I haven't
found yet.

**Cost and platform, plainly, before you install anything.** It's
proprietary/commercial software (MIT-licensed through v1.4, commercial from
v1.5 on) and it needs a paid SOLIDWORKS 2021+ seat to actually build
geometry. Windows-only — it drives SOLIDWORKS over COM.

**If you don't want to install anything yet:** you can author and lint a
real spec offline with zero license — schema, references, locals, DFM
lint. That's Tier A. Actually building geometry against your seat is Tier B
and needs the license.

Landing page with the full writeup, the current kernel-wall list, and a
demo of the pipeline end to end:
`https://thomas-tai.github.io/ai-sw-bridge/?utm_source=reddit.com&utm_medium=social&utm_campaign=launch&utm_content=r-solidworks`

Repo: `https://github.com/Thomas-Tai/ai-sw-bridge`

Happy to answer anything, including the unflattering questions.
