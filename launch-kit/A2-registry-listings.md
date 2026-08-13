# A2 — MCP-ecosystem registry listings

This doc is two things in one: a **submit/skip decision log** for the MCP
ecosystem's directories, and the **ready-to-submit listing copy** for the
targets where a listing makes sense. The author drafts the copy and the
decisions below; a human still has to actually submit each one — nothing in
this file has been submitted anywhere yet. The point of getting listed is
**mindshare** — being citable and discoverable when someone searches "MCP
server" + "SOLIDWORKS" or browses a registry — not to imply a one-click
hosted install anywhere a directory happens to also run servers.

### Honest prerequisites

ai-sw-bridge is **proprietary/commercial software** (MIT-licensed through
v1.4; commercial license from v1.5 onward). It requires a **paid SOLIDWORKS
2021+ seat**, and it is **Windows-only**. This same one-line reminder is
reused verbatim in every listing below so no builder finds out the hard way
after they've already tried to install it.

## Classification (finding F4)

Not every registry means the same thing by "listing." Some are pure
directories — a catalog entry with a link, nothing runs on their
infrastructure. Others are **runnable hosts** — they expect to build,
host, or proxy the server themselves. A Windows-only server that needs a
paid, locally-installed SOLIDWORKS seat cannot run on a hosted runner, so
those two categories get different treatment below.

| Target | Type | Action | Why |
|---|---|---|---|
| Official MCP registry | Directory-only | Submit listing | A catalog entry is always appropriate — it's metadata, not a hosting commitment. |
| awesome-mcp-servers (punkpeye) | Directory-only | Submit PR | Curated list; a one-line entry + link, no hosting involved. |
| mcp.so | Directory-only | Submit listing | Directory/discovery site — links out, doesn't run anything. |
| PulseMCP | Directory-only | Submit listing | Directory/discovery site — same, links out. |
| Smithery | Runnable-host | Listing/reference only (or skip) | Expects an installable/hostable server; Windows + a paid seat won't run on their hosted runner, so a normal submission would be rejected or misleading. |
| Glama | Runnable-host | Listing/reference only (or skip) | Same runnable-host expectation as Smithery. |

---

## Official MCP registry

- **Name:** ai-sw-bridge
- **One-line description:** An MCP server that drives a real, licensed SOLIDWORKS seat from a JSON spec — native, editable `.SLDPRT`/`.SLDASM`, human-gated (propose → approve → execute).
- **Repo:** `https://github.com/Thomas-Tai/ai-sw-bridge`
- **Website:** `https://thomas-tai.github.io/ai-sw-bridge/?utm_source=mcp-registry&utm_medium=referral&utm_campaign=launch&utm_content=listing`
- **Category / tags:** `mcp-server`, `cad`, `solidworks`, `engineering`, `automation`, `windows`
- **Prerequisites note:** Proprietary/commercial (MIT through v1.4, commercial from v1.5); requires a paid SOLIDWORKS 2021+ seat; Windows-only.

## awesome-mcp-servers (punkpeye)

- **Name:** ai-sw-bridge
- **One-line description:** Drives a real, licensed SOLIDWORKS seat from a JSON spec — native, editable `.SLDPRT`/`.SLDASM` feature trees, not a foreign STEP dump.
- **Repo:** `https://github.com/Thomas-Tai/ai-sw-bridge`
- **Website:** n/a — repo only (this list carries one link per entry; the repo README is the front door)
- **Category / tags:** `mcp-server`, `cad`, `solidworks`, `engineering`, `automation`, `windows`
- **Prerequisites note:** Proprietary/commercial (MIT through v1.4, commercial from v1.5); requires a paid SOLIDWORKS 2021+ seat; Windows-only.
- **Literal list-item text, as it would appear in that README:**
  ```
  - [ai-sw-bridge](https://github.com/Thomas-Tai/ai-sw-bridge) — Drives a real, licensed SOLIDWORKS seat from a JSON spec, with a native editable feature tree. Windows, requires a paid SOLIDWORKS 2021+ seat.
  ```

## mcp.so

- **Name:** ai-sw-bridge
- **One-line description:** An MCP server for real SOLIDWORKS CAD: build parts and assemblies from a JSON spec with a native, editable feature tree, human-gated end to end.
- **Repo:** `https://github.com/Thomas-Tai/ai-sw-bridge`
- **Website:** `https://thomas-tai.github.io/ai-sw-bridge/?utm_source=mcp-registry&utm_medium=referral&utm_campaign=launch&utm_content=listing`
- **Category / tags:** `mcp-server`, `cad`, `solidworks`, `engineering`, `automation`, `windows`
- **Prerequisites note:** Proprietary/commercial (MIT through v1.4, commercial from v1.5); requires a paid SOLIDWORKS 2021+ seat; Windows-only.

## PulseMCP

- **Name:** ai-sw-bridge
- **One-line description:** Drive a real, licensed SOLIDWORKS seat from a JSON spec — native `.SLDPRT`/`.SLDASM`/`.SLDDRW`, propose → approve → execute.
- **Repo:** `https://github.com/Thomas-Tai/ai-sw-bridge`
- **Website:** `https://thomas-tai.github.io/ai-sw-bridge/?utm_source=mcp-registry&utm_medium=referral&utm_campaign=launch&utm_content=listing`
- **Category / tags:** `mcp-server`, `cad`, `solidworks`, `engineering`, `automation`, `windows`
- **Prerequisites note:** Proprietary/commercial (MIT through v1.4, commercial from v1.5); requires a paid SOLIDWORKS 2021+ seat; Windows-only.

---

## Runnable-host targets — listing-only / skip

**Smithery.** Smithery's model expects a server it can install and host for
a user, typically from a manifest that describes how to run it in their
infrastructure. ai-sw-bridge cannot satisfy that: it is Windows-only and
requires driving a real, paid, locally-installed SOLIDWORKS 2021+ seat over
COM — there is no container or hosted runner that can stand one up. Submitting
a normal "runnable server" entry would either be rejected by their vetting
or, worse, imply a hosted/one-click experience that doesn't exist. If
Smithery's submission flow supports a non-runnable reference entry (repo
link + description, no "run" action), submit that; otherwise, skip Smithery
for now rather than publish a misleading listing.

**Glama.** Same reasoning as Smithery: Glama's directory is built around
servers it can index and often run/verify against a live connection. A
Windows + paid-SOLIDWORKS-seat server fails that assumption the same way.
If Glama offers a listing-only or "unverified/reference" tier that doesn't
claim the server was run on their infrastructure, submit under that tier
with the honest-prerequisites note attached; otherwise, skip it. No entry
on either platform should imply a one-click hosted install of ai-sw-bridge.
