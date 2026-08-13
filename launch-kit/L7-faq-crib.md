# L7 — FAQ crib for objection handling

A crib sheet for the author to pull from when an objection lands in a
comment thread, a DM, or a call. Every answer here is meant to be used
close to verbatim — honest and non-defensive, no spin, no dodge. Lead
with the true free path wherever one exists.

## Core objections

### "It's proprietary."

Yes. Own it plainly: ai-sw-bridge is MIT-licensed through v1.4, and
commercial from v1.5 onward. That's not a bait-and-switch to apologize
for — it's the model. Ongoing development (the seat-proven feature-add
kinds, the fixes, the support) is funded by the commercial license, and
that's what keeps the bridge working against a real, moving target
(SOLIDWORKS's own COM surface) instead of going stale after the initial
release. If proprietary/commercial is a hard no for your use case, the
frozen MIT v1.4 snapshot is still sitting there — see the fork question
below for exactly what that does and doesn't get you.

### "It needs a seat."

Start with what doesn't need one: you can author and lint a real spec
entirely offline, zero license — schema validation, reference
resolution, locals, DFM lint. That's Tier A, and it's most of what
there is to evaluate about whether the spec format and the tool surface
fit how you work. You don't need Windows or SOLIDWORKS installed to do
any of that.

Building actual geometry is Tier B, and that part is honest about its
requirement: a running, licensed, paid SOLIDWORKS 2021+ seat, on
Windows, because the bridge drives SOLIDWORKS over COM. There's no way
around that for Tier B — it's not a licensing upsell trick, it's what
driving a real CAD kernel's feature tree actually takes.

### "I'll just fork the last MIT v1.4."

That's a legitimate move, and it's worth saying plainly what you get and
don't get from it. v1.4 is a real, valid, frozen snapshot — MIT-licensed,
yours to fork, modify, and run with no strings attached.

What it doesn't get you is anything that shipped after it: none of the
seat-proven `feature_add` kinds added since, none of the fixes, none of
the support. Every wall documented in the repo's Known Limitations doc
as of v1.4 stays a wall in your fork forever, because nobody's pushing
on it upstream on your behalf anymore. If that trade is fine for your
use case — you need exactly what v1.4 does and nothing more — fork away.
If you'll eventually want the parts built since, that's what the
commercial license is for.

## More objections

### "Why not just export STEP?"

You can, if that's what you need — the spec export block and the
`ai-sw-export-dxf-flat` CLI cover flat/downstream export formats. But
that's a different job from what the bridge is actually for. STEP (or
any mesh dump) has no feature history — once you have it, you can only
push faces around, not change a dimension and rebuild. The bridge's
whole point is producing native `.SLDPRT` / `.SLDASM` / `.SLDDRW` with a
real, editable feature tree, the same kind you'd get building it by
hand. If all you ever need is a shape to hand downstream, plain export
is the right tool and you don't need the rest of this. If you need to
keep editing the thing, that's the case the bridge is built for.

### "Is my model sent anywhere?"

No. The bridge drives your own local, licensed SOLIDWORKS seat over
COM — the same interprocess mechanism any local automation macro uses.
Your model geometry stays on your machine, in your own SOLIDWORKS
session; nothing about building a part or assembly ships it to a
server. Treat this the same as any other local automation tool talking
to software already installed on your machine.

### "Windows-only?"

Yes, and there's no near-term way around it: the bridge drives
SOLIDWORKS itself over COM, and SOLIDWORKS only runs on Windows. That's
a constraint of the CAD system being driven, not a platform choice made
for its own sake. Tier A (spec authoring, schema, references, locals,
DFM lint) has no such constraint and runs anywhere Python does — it's
only Tier B, actually building geometry, that requires Windows plus the
seat.

### "Does this work with CAD tools other than SOLIDWORKS?"

Not today. The bridge is built specifically against SOLIDWORKS's COM
automation surface, and that surface is what every part of Tier B leans
on — the feature tree shape, the dimension model, the mate types, the
drawing/BOM generation. Supporting another CAD system would mean
rebuilding that integration layer from scratch against a different
API, not a thin adapter on top of what exists. There's no other CAD
system supported right now.
