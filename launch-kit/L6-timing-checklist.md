# L6 — Launch timing / fire-order checklist

This is the launch operator's playbook: the order things fire in, the
timing notes that matter, and the measurement routine to run afterward.
It is not copy to publish — it is the runbook for the human running launch
day, cribbing from the drafts already sitting in this directory.

## BLOCKING GATE — read this before touching anything below

> **STOP. The coordinated launch does NOT fire until Project A Phase-2
> deep clips (observe / drawing / export) land and the hero recomposes
> over them.**
>
> Findings note: `docs/superpowers/notes/2026-08-12-phase2-findings.md`
>
> Nothing in the fire order below goes out — not the registry listings,
> not Show HN, not the thread, not Reddit, not LinkedIn, not Product Hunt
> — until that clip work lands and the hero on the landing page reflects
> it. Check the findings note above for current status before scheduling
> a single post. If it isn't resolved, this checklist does not run today.

## Fire order (launch day)

Work top to bottom. Each item names the launch-kit asset it fires from
and any timing note that applies. Don't skip ahead — later items assume
the earlier ones are already live so cross-links and "we're live"
framing hold up.

- [ ] **Registries live first.** Submit/verify the listings in
      `A2-registry-listings.md` (official MCP registry, awesome-mcp-servers,
      mcp.so, PulseMCP; Smithery/Glama per their listing-only-or-skip
      decision in that doc). These should be live *before* anything else
      posts, so anyone who clicks through from a later channel finds a
      real listing already up.
- [ ] **Show HN, US-morning window.** Post the title/URL/body from
      `L1-show-hn.md`, then post the first comment yourself immediately
      after submitting — don't leave the submission without an author
      comment. Time this for the US-morning window (~8–10am ET) since
      that's when HN's front page has the most traffic turnover.
- [ ] **X thread.** Post the 5-tweet thread from `L2-x-thread.md`,
      tweet by tweet, right after the HN submission is live — attach the
      hero demo gif on tweet 2/5 as noted in the draft. Fire this soon
      after HN so anyone bouncing between the two sees consistent timing.
- [ ] **Reddit, both subs.** Post `L4-reddit-mcp.md` to r/mcp and
      `L4-reddit-solidworks.md` to r/SolidWorks. These are two separate,
      independent posts — space them out rather than firing back-to-back,
      since both subs expect a genuine author present to answer comments,
      not a cross-post blast.
- [ ] **LinkedIn.** Publish the article from `L3-linkedin.md` once the
      above channels are live — this one has the longest shelf life of
      the set, so it doesn't need to race the others, but it should still
      go out same-day so it's citable from the other threads if anyone
      asks for the longer version.
- [ ] **Product Hunt — optional.** Only fire `L5-product-hunt.md` if
      Task 10 decided to launch there (spec open question #3). If yes,
      treat it as its own timing slot (PH's own day-start window matters
      more than sequencing against the channels above) — check that
      draft's own header note before scheduling.

## Measurement

After launch, on a **14-day window**, review both of the following
signals to see which doorway actually works:

- **(a) UTM referrers per channel.** Every launch link in the drafts
  above already carries UTM tags sourced from `launch-kit/utm_links.md`
  — per-channel attribution is already wired in, nothing extra to add.
  Pull referrer breakdowns by `utm_source`/`utm_content` for the window.
- **(b) GitHub repo-traffic referrers.** Check the repo's own traffic
  referrers (Insights → Traffic) over the same 14-day window — this
  catches traffic that lands on the repo directly rather than through
  the landing page, which the UTM links alone won't show.

**Stars are watched, not chased.** Under a paid-seat + proprietary
headwind, stars are a lagging proxy at best — don't treat a star count
as the success metric or optimize toward it. The real signal from this
window is which doorway (builder vs. practitioner) actually drives
qualified traffic, read from (a) and (b) above, not the star count.
