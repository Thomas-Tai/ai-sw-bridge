# Project B — Distribution / Reach Design

**Date:** 2026-08-12
**Status:** Design approved (all sections); full audit folded in (findings F1–F9, 2026-08-12). Awaiting user spec-review gate → writing-plans.
**Author:** brainstorming session (Project B)
**Related:** Project A demo-suite (`docs/superpowers/specs/2026-08-12-demo-gif-suite-enhancement-design.md`) — its hero/tour/captioned clips are this project's shared proof.

---

## Goal

Make **ai-sw-bridge** the reflex answer to "how do I drive SOLIDWORKS from an AI
agent?" — win **mindshare**, not vanity stars. Build one owned home that is the
canonical reference, let both audiences discover it through their own channels,
and fire a single coordinated launch once the proof is deep.

## Strategy in one line

Build a single *owned* home that is the answer to "AI + SOLIDWORKS," and let both
tribes discover it through their own channels — so when someone asks the question,
your name is the reflex.

---

## Locked cornerstones (decided via brainstorming)

1. **Success metric = Mindshare** — "be THE name for AI + SOLIDWORKS," measured by
   inbound mentions, citations, and word-of-mouth. NOT raw stars.
   *Rationale:* the repo is **proprietary**, requires a **paid SOLIDWORKS seat**,
   and is **Windows-only** — raw-star mechanics fight a structural headwind, but
   mindshare sidesteps it (no seat is needed to cite or amplify).
   *Whose mindshare:* it accrues to the **project** (ai-sw-bridge, and by extension
   its author); the landing page and every asset are **project-branded**.
2. **Audience = BOTH tribes, two-track:** (a) AI-agent / MCP builders,
   (b) SOLIDWORKS practitioners. Guard: **shared spine, fork only at the edges**
   (framing + entry channel), never 2× the content work.
3. **Execution shape = Evergreen spine + ONE coordinated launch + light drumbeat.**
4. **Deliverable scope = Evergreen assets + a complete, ready-to-fire launch kit.**
   Division of labor: I build assets, draft all copy, prepare registry-listing PRs,
   and write the timing checklist; **the user** reviews, presses send, and does the
   live engagement.

## Approved synthesis (authority × ubiquity)

- **Spine** = a canonical reference (authority) living on a lean **landing page**
  (proof-first) = one owned home.
- **Ignition** = MCP-ecosystem listings (ubiquity) + one coordinated launch.
- **Proof** = the Project A demo suite (hero / tour / captioned clips), shared by
  both tribes.
- **Two-track** = one spine, forked only at framing (builders: "an MCP server that
  drives a REAL SOLIDWORKS seat, safely"; practitioners: "let Claude do your
  drafting, human-gated").

---

## Section 1 — Architecture & the Spine

**The Spine** is one durable **GitHub Pages landing page**, three layers deep:

- **The fold** — demo hero gif + the wedge headline ("Drive your *real* SOLIDWORKS
  seat from a JSON spec — a native, editable feature tree, not a foreign STEP dump
  from a throwaway kernel"). Zero scroll to grasp what it is and why it differs.
- **The heart** — a canonical reference essay, *"Driving real SOLIDWORKS from an AI
  agent — and why it's hard."* Five honest beats:
  1. the problem;
  2. propose → approve → execute, human-gated safety;
  3. native editable feature tree vs. foreign STEP;
  4. the real kernel walls you hit (walled OOP feature types — loft/rib/wrap/combine, failed closed — and dimensioned-mode popups; stated as fact, not spin — NB: mates are NOT a wall, resolved per known_limitations.md §8);
  5. try it with no seat.
  This essay is the citable artifact; authority is what earns mindshare here.
- **The CTA** — a **per-doorway** next step, because the two tribes convert on
  different things:
  - **Builders** → the no-seat **Tier A** quickstart (author + lint spec JSON
    offline, zero license). This is genuinely compelling to them.
  - **Practitioners** → the **visual demo (hero / video) + operator guide**
    ("install & drive it from your AI — you approve every step"). A 20-year
    SOLIDWORKS user's payoff is *seeing geometry rebuild in a real seat*, which the
    offline linter does not show — so their CTA is the demo, **not** Tier A.

**Two-track, one spine:** the page forks only at the *doorway* — the README
persona-router pattern (two entry doors: "AI-agent / MCP builder" and "SOLIDWORKS
practitioner"), each with its own framing, both landing in the same reference +
demo. No 2× content.

**Syndication:** anything posted off-site (dev.to, Medium, LinkedIn article)
carries `rel=canonical` back to the owned page, concentrating link equity and
citations on the home we control.

---

## Section 2 — The Deliverable Set

### Evergreen assets

| ID | Asset | What it is | Notes |
|---|---|---|---|
| **A1** | Landing page | The Spine (§1) on GitHub Pages: fold (hero + wedge), canonical reference essay, two doorways, per-tribe CTA | The one owned home; everything points here. **Baseline build path:** render the existing README / QUICKSTART / docs via a GitHub Pages **Jekyll theme** (near-zero cost) and weigh that against a hand-built page before committing effort. |
| **A2** | MCP-ecosystem listings | Submission entries / PRs to registries builders browse | **Tag each target:** *directory-only* (mcp.so, PulseMCP, awesome-mcp-servers, official **MCP registry**) = a listing, always OK; *runnable-host* (Smithery, Glama) expects an installable/hostable server — a Windows+seat server **won't run there**, so submit as a listing/reference only or skip, to avoid a rejected PR. The "ubiquity" half. |
| **A3** | Repo README | Already wedged in Project A (hero + capability table + no-seat callout) | Done. Landing page and README share one wedge voice. |
| **A4** | "AI + SOLIDWORKS" explainer | A short, honest comparison: real-seat / native-feature-tree vs. throwaway-kernel→STEP — framed *"which fits your job,"* not a swipe | The citable artifact; lives on A1, backbone of the launch essay. |

### Launch kit (draft-and-hold folder)

| ID | Asset | Notes |
|---|---|---|
| **L1** | Show HN post | title + body + first-comment context |
| **L2** | X / Twitter thread | hook → demo gif → wedge → try-no-seat CTA |
| **L3** | LinkedIn article | practitioner-framed; `rel=canonical` → A1 |
| **L4** | Reddit posts | r/SolidWorks (practitioner voice) + r/mcp (builder voice), tuned to sub norms |
| **L5** | Product Hunt | **optional** — flagged, not assumed |
| **L6** | Timing / sequence checklist | launch-day fire order + the dependency that launch waits on Project A Phase-2 deep clips |
| **L7** | Response-FAQ crib | graceful answers to *"it's proprietary"* and *"needs a seat"*: lead with the free no-seat quickstart; state plainly it **was** MIT ≤ v1.4, now commercial. Also handle *"I'll just fork the last MIT v1.4"* honestly — a valid frozen snapshot, but it gets **none** of the ongoing seat-proven `feature_add` kinds, fixes, or support. No spin, no dodge. |

**Division of labor:** I build all assets + drafted copy + registry PRs; the user
reviews and presses send / does live engagement.

---

## Section 3 — Funnel, Measurement & Guardrails

### The two-track funnel

One shared arc — *stranger → lands on the Spine → tries it (no seat) → cites /
names you* — forked only at entry channel and framing:

| Stage | AI-agent / MCP builder track | SOLIDWORKS practitioner track |
|---|---|---|
| **Discover** | MCP registries (A2), Show HN, X, r/mcp | LinkedIn, r/SolidWorks, GrabCAD, eng-YouTube, VARs |
| **Frame** | "An MCP server that drives a *real* SOLIDWORKS seat — safely, human-gated" | "Let Claude do your drafting — you approve every step" |
| **Land** | Same Spine, "builder" doorway → reference essay + hero | Same Spine, "practitioner" doorway → reference essay + hero |
| **Convert** | No-seat **Tier A** (author + lint specs offline) → **cites / lists it as *the reference implementation*.** Most can't run a Windows+seat server, so builder conversion is *citation, not install* — consistent with the mindshare-not-stars metric. | **Visual demo** (hero / video) + operator guide → "install & drive it from your AI, you approve every step" → shares it, mentions it to team / VAR |
| **Amplify** | Cites the reference essay when "AI + CAD" comes up | Names you when a peer asks "how do I automate SOLIDWORKS?" |

The **amplify** row is the actual goal — mindshare is people repeating your name
unprompted.

### Measurement (mindshare, not vanity)

Primary signals, reviewed on a light cadence:
- **Inbound mentions & citations** — links to the reference essay; "ai-sw-bridge"
  appearing in others' threads, stack lists, comparison posts.
- **Referral traffic** — GitHub Pages / repo traffic sourced from the MCP
  registries and each launch channel (tells us which doorway works).
  *Requires instrumentation:* **UTM tags on every launch link** + GitHub
  repo-traffic referrers (14-day window). Without them, "which doorway works" is
  unmeasurable — build the tagging into the launch kit, not as an afterthought.
- **Launch reception** — HN points/comments, Reddit upvotes/tone, registry
  acceptances.
- **Secondary, watched-not-chased:** stars — a lagging proxy given the
  seat+proprietary headwind; never the headline metric.

### Risks & honesty guardrails

- **L6 honesty carries over, non-negotiable** — every claim in every asset is
  defensible. Kernel walls stated as fact; SOLIDWORKS a plain requirement, not an
  endorsement; the wedge a factual contrast, never a swipe at the competitor.
- **⚠ Launch-timing dependency** — the launch is *strongest after Project A's
  Phase-2 deep clips land* (today's observe/drawing/export clips are the
  honest-but-shallow versions). Evergreen assets can be built now; **the
  coordinated launch fires only once the proof is deep.** The one hard sequencing
  constraint.
- **"Proprietary / needs a seat" backlash** — pre-drafted in the FAQ crib (L7):
  lead with the free no-seat trial; state the MIT-≤v1.4 → commercial history
  plainly. Expected friction, managed not hidden.
- **Practitioner AI-skepticism / craft-threat backlash** — r/SolidWorks and the
  LinkedIn CAD community are protective of the craft and weary of AI hype;
  "let Claude do your drafting" can read as *slop-generator* or *job-threat*, and
  is the likeliest flamewar on the practitioner track. *Mitigation:* lead
  practitioner copy with **control and correctness** — the human-gated
  propose → approve → execute loop, framed as "a power tool you drive, not a
  replacement" — and put the approval gate **visibly** in the demo. Never frame it
  as autonomous drafting.
- **MCP-hype-fade** — the authority essay is the durable asset; if the MCP wave
  cools, the reference and the demo still stand. Registries are ignition, not
  foundation.
- **Solo bandwidth** — the user presses send and engages; I front-load all drafting
  so launch day is review-and-fire, not author-from-scratch.

---

## Sequencing & dependencies

1. **Now (buildable):** A1 landing page, A2 registry PRs, A4 explainer, and the
   full launch kit (L1–L7) as drafts-on-hold.
2. **Gate:** the coordinated launch does **not** fire until Project A Phase-2 deep
   clips (observe / drawing / export) land and the hero recomposes over them.
   The A1 landing page embeds the **same hero** as the README, so its hero embed
   inherits the same caveat: build A1's *structure* now, but **re-embed its hero**
   alongside the README when the deep clips land — don't ship a deep-proof landing
   page wrapped around shallow proof.
3. **Git hold:** Project B build work respects the standing git hold — working-tree
   assets only, no commits, until the hold lifts. (This spec file itself is written
   but **not** committed.)

## Out of scope (this spec)

- Paid ads / sponsorships.
- The Project A Phase-2 deep re-records themselves (owned by the Project A plan;
  this project only *depends* on them).
- Any commercial-pricing / sales-funnel work — this is reach, not monetization.

## Open questions (resolve during writing-plans or first build)

- Landing-page host specifics: GitHub Pages from `/docs` vs. a `gh-pages` branch;
  custom domain vs. `github.io` (custom domain strengthens the `rel=canonical`
  story but adds setup).
- Whether A4 (explainer) is a standalone page or a section within A1 at launch.
- Final channel list confirmation (e.g., include Product Hunt L5 or drop it).
