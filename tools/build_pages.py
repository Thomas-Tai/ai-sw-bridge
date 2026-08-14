#!/usr/bin/env python3
"""Build the GitHub Pages publish artifact from site/index.html.

Deterministic transform of the repo-local landing page into a self-contained
gh-pages root:

  * hero  ../docs/img/demo_hero.gif  -> assets/demo_hero.gif  (copied in, so it
    resolves when only this artifact is served);
  * the three internal doc links (../QUICKSTART.md, ../docs/operator_guide.md,
    ../docs/known_limitations.md) -> their rendered GitHub blob URLs on the
    default branch (they are Markdown; GitHub renders them, Pages would not);
  * same-page anchors (#hero, #essay) are left untouched;
  * a .nojekyll marker so Pages serves the raw HTML without a Jekyll build.

Run:  python build_pages.py <repo_root> <out_dir>
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

BLOB = "https://github.com/Thomas-Tai/ai-sw-bridge/blob/master"

# (repo-relative link in site/index.html) -> (published URL)
LINK_REWRITES = {
    "../QUICKSTART.md": f"{BLOB}/QUICKSTART.md",
    "../docs/operator_guide.md": f"{BLOB}/docs/operator_guide.md",
    "../docs/known_limitations.md": f"{BLOB}/docs/known_limitations.md",
}
HERO_SRC_REL = "../docs/img/demo_hero.gif"
HERO_OUT_REL = "assets/demo_hero.gif"


def build(repo_root: Path, out_dir: Path) -> int:
    src_html = (repo_root / "site" / "index.html").read_text(encoding="utf-8")
    hero = repo_root / "docs" / "img" / "demo_hero.gif"
    if not hero.exists():
        print(f"ERROR: hero not found: {hero}", file=sys.stderr)
        return 1

    html = src_html.replace(f'src="{HERO_SRC_REL}"', f'src="{HERO_OUT_REL}"')
    for old, new in LINK_REWRITES.items():
        html = html.replace(f'href="{old}"', f'href="{new}"')

    # Fail loudly if any escaping ../ link survived the rewrite.
    leftover = [tok for tok in ('href="../', 'src="../') if tok in html]
    if leftover:
        print(f"ERROR: unrewritten relative refs remain: {leftover}", file=sys.stderr)
        return 1

    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "assets").mkdir(parents=True)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    shutil.copy2(hero, out_dir / HERO_OUT_REL)
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    print(f"OK: built Pages artifact at {out_dir}")
    print(f"  index.html    ({len(html)} bytes)")
    print(f"  {HERO_OUT_REL} ({hero.stat().st_size} bytes)")
    print("  .nojekyll")
    return 0


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: build_pages.py <repo_root> <out_dir>", file=sys.stderr)
        return 2
    return build(Path(sys.argv[1]), Path(sys.argv[2]))


if __name__ == "__main__":
    sys.exit(main())
