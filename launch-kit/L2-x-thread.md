# L2 — X / Twitter launch thread draft

This is a **draft** for a human to review and post to X, tweet by tweet.
Nothing here has been posted. Each block below is the exact copy-paste text
for one tweet — character counts are noted for the author's own
verification and are not part of the post itself.

## Thread (5 tweets)

### Tweet 1/5 — hook

```
1/ Built an MCP server that drives a real, licensed SOLIDWORKS seat from a JSON spec. Native .SLDPRT / .SLDASM / .SLDDRW — not a STEP dump from a throwaway kernel.
```
(163 chars)

### Tweet 2/5 — demo + the gate

```
2/ Here it is building a part end to end: propose a spec → you approve it → it executes against a live seat. Part → assembly → observe/DFM → drawing → export, human-gated the whole way.
```
(185 chars)

> attach: hero demo gif

### Tweet 3/5 — the wedge

```
3/ Why it matters: the output is a real feature tree you keep editing — change a dimension, rebuild, same as anything you built by hand. A STEP import only lets you push faces around; the design intent is gone.
```
(210 chars)

### Tweet 4/5 — honest edges

```
4/ Being straight about the walls: a class of features (lofts, ribs, wraps, combines) can't be driven out-of-process, so the bridge refuses them cleanly instead of emitting a broken part. In dimensioned mode, a few SOLIDWORKS dialogs still need a human tick.
```
(258 chars)

### Tweet 5/5 — try it with no seat (CTA)

```
5/ No SOLIDWORKS seat? You can still author + lint a real spec offline, zero license (schema, references, locals, DFM lint). Try it: https://thomas-tai.github.io/ai-sw-bridge/?utm_source=x.com&utm_medium=social&utm_campaign=launch&utm_content=launch-thread
```
(256 chars)
