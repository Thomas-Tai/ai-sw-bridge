# site/ — the ai-sw-bridge landing page

`index.html` is the canonical landing page (the "Spine") every launch asset
links back to. It is a single self-contained HTML file — inline CSS, no
external CDN/font/script — and it is buildable and previewable right now:
open `site/index.html` directly in a browser, no build step required.

## Publish mechanism — deferred decision

How this page actually gets served on the public web is **not decided
here**. That call is Task 10, and it stays open until the git hold on this
work lifts. The live options on the table:

- **GitHub Pages from `/docs`** — repurpose the existing `docs/` folder as
  the Pages root.
- **A dedicated `gh-pages` branch** — keep published output out of `main`
  entirely.
- **`site/` as the Pages root** — point Pages straight at this directory.

Also undecided: the default `github.io` subdomain vs. a custom domain.
None of that affects how this page is written today — it only affects how
it gets deployed later.

### Recommendation

Publish `site/` as a **standalone page**, not by turning the whole `docs/`
folder into a Jekyll build. `docs/` holds internal engineering
documentation (operator guide, known limitations, architecture notes,
i18n mirrors, superpowers specs) that was never meant to be a public
website — a whole-`docs/` Jekyll build would publish all of it by
accident. `site/` (or an equivalent narrowly-scoped Pages root) keeps the
public surface intentional.

## Why the links still work today

`index.html` uses the `../`-relative-to-`site/` convention for every
internal link and asset (`../docs/img/demo_hero.gif`, `../QUICKSTART.md`,
`../docs/operator_guide.md`, `../docs/known_limitations.md`). That's
deliberate: those paths resolve on disk right now, which is what lets
`python tools/check_launch_kit.py` verify them before a publish mechanism
even exists.

At actual publish time, two things happen that this file does not attempt
to pre-solve:

- The **hero asset** (`docs/img/demo_hero.gif`) is finalized and copied
  into whatever the chosen publish layout expects.
- The **internal `../`-relative links** are rewritten to their published
  URLs (e.g. an absolute path, a different relative depth, or a full
  `https://` URL depending on which of the three options above is chosen).

Neither rewrite changes anything in this document now — they're deferred
to Task 10, alongside the publish-mechanism decision itself.
