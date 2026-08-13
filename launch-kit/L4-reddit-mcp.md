# L4 — r/mcp post draft

This is a **draft** for a human to review and post to r/mcp. Nothing here
has been submitted. Transparent authorship up front, technical framing over
marketing, inviting critique — matching how this sub expects self-promotion
posts to read.

## Title

```
ai-sw-bridge: an MCP server that drives a real SOLIDWORKS seat via propose/approve/execute — Tier A (spec authoring, zero license) works without a seat at all
```

## Body

I'm the author. Sharing this because it's a slightly unusual MCP server
shape and I'd like feedback from people building tool surfaces, not just
CAD people.

**Try the tool surface with nothing installed.** Most of the server is
usable with zero license and no SOLIDWORKS seat at all — that's Tier A:
author and lint a real spec against the schema, resolve references,
evaluate locals, run the DFM lint. If you just want to see the spec format
and the tool calls without standing up Windows plus a paid seat, start
there.

**The tool surface: propose → approve → execute.** Every mutating call
follows the same gate. The agent proposes a spec (a part, an assembly, a
mutation), a human approves it, and only then does execution happen against
the live SOLIDWORKS instance. It's a deliberate design constraint, not a
missing feature — I didn't want a tool surface where an agent could
silently touch a paid, licensed CAD seat.

**What execution actually needs (Tier B), honestly.** Building real
geometry requires a running, licensed SOLIDWORKS 2021+ seat. The server is
Windows-only — it drives SOLIDWORKS over COM, and there's no hosted or
sandboxed way to run Tier B. If you don't have Windows plus a seat, you're
capped at Tier A, and I'd rather say that plainly than let anyone find out
after installing.

**License, also plainly.** ai-sw-bridge is proprietary/commercial software
— MIT-licensed through v1.4, commercial from v1.5 onward.

**Where the tool surface currently refuses work, on purpose.** A class of
CAD features (lofts, ribs, wraps, combines, and similar) can't be driven
out-of-process through SOLIDWORKS's automation surface at all, so those
calls are refused cleanly rather than returning a broken part. In
dimensioned mode, a handful of SOLIDWORKS dialogs still need a human tick
before they'll proceed — that one's a SOLIDWORKS UI limitation, not
something the MCP layer can route around. The current list is in the
repo's Known Limitations doc.

If you're the kind of person who reads an MCP server's tool schema before
its README, I'd rather you start there and tell me what's wrong with the
surface than take the pitch at face value.

Landing page and a demo of the full pipeline (part → assembly →
observe/DFM → drawing → export) on a live seat:
`https://thomas-tai.github.io/ai-sw-bridge/?utm_source=reddit.com&utm_medium=social&utm_campaign=launch&utm_content=r-mcp`

Repo: `https://github.com/Thomas-Tai/ai-sw-bridge`
