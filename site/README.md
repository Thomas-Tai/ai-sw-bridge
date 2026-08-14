# site/ — the ai-sw-bridge landing page

`index.html` is the canonical landing page (the "Spine") every launch asset
links back to. It is a single self-contained HTML file — inline CSS, no
external CDN/font/script — and it is buildable and previewable right now:
open `site/index.html` directly in a browser, no build step required.

## Publish mechanism — RESOLVED (Task 10, 2026-08-14)

The page is served by **GitHub Pages from a dedicated `gh-pages` branch**
(branch root), at the canonical URL
**`https://thomas-tai.github.io/ai-sw-bridge/`** — the default `github.io`
subdomain, no custom domain. This keeps published output off `master`
entirely, and keeps the public surface intentional: a single standalone
page, never a whole-`docs/` Jekyll build (which would have leaked internal
engineering docs — operator notes, specs, i18n mirrors).

### How the published copy is produced

`site/index.html` is the **source**; the `gh-pages` root is a **generated
artifact** built deterministically by
[`../tools/build_pages.py`](../tools/build_pages.py):

- the hero `../docs/img/demo_hero.gif` is copied to `assets/demo_hero.gif`
  and the `<img src>` repointed there, so it resolves when only the
  artifact is served;
- the three internal Markdown links (`../QUICKSTART.md`,
  `../docs/operator_guide.md`, `../docs/known_limitations.md`) are
  rewritten to their rendered GitHub blob URLs on `master` (GitHub renders
  Markdown; Pages would serve it raw);
- same-page anchors (`#hero`, `#essay`) are left untouched;
- a `.nojekyll` marker is written so Pages serves the raw HTML with no
  Jekyll build.

The script fails loudly if any escaping `../` reference survives the
rewrite. Rebuild + redeploy with:

    python tools/build_pages.py . _site
    # then publish _site/ to the gh-pages branch root

### Why the source keeps `../`-relative links

`site/index.html` deliberately uses the `../`-relative-to-`site/`
convention (`../docs/img/demo_hero.gif`, `../QUICKSTART.md`, …) so those
paths resolve **on disk**, which is what lets
`python tools/check_launch_kit.py` verify them in the repo. The publish
rewrite above lives only in the generated artifact — the committed source
is never hand-edited for publish.
