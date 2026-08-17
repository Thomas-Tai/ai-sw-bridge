#!/usr/bin/env python3
"""Build the GitHub Pages publish artifact from site/index.html.

Deterministic transform of the repo-local landing page into a self-contained
gh-pages root:

  * every image asset referenced by the page (the hero GIF, the workflow
    stills, and the Block-1 anchor stills/GIF under ../docs/img/) is copied
    into the artifact's assets/ dir and its src="" rewritten to the local
    copy, so the page resolves when only this artifact is served;
  * the four internal doc links (../QUICKSTART.md, ../docs/operator_guide.md,
    ../docs/known_limitations.md, ../docs/CAPABILITIES.md) -> their rendered
    GitHub blob URLs on the default branch (they are Markdown; GitHub renders
    them, Pages would not);
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
    "../docs/CAPABILITIES.md": f"{BLOB}/docs/CAPABILITIES.md",
}

# (src relative to site/index.html) -> (out relative in the gh-pages artifact)
IMAGE_ASSETS = [
    ("../docs/img/demo_hero.gif", "assets/demo_hero.gif"),
    ("../docs/img/still_part.png", "assets/still_part.png"),
    ("../docs/img/still_assembly.png", "assets/still_assembly.png"),
    ("../docs/img/still_observe.png", "assets/still_observe.png"),
    ("../docs/img/still_drawing.png", "assets/still_drawing.png"),
    ("../docs/img/still_export.png", "assets/still_export.png"),
    ("../docs/img/anchor_dead_step.png", "assets/anchor_dead_step.png"),
    ("../docs/img/anchor_alive_tree.png", "assets/anchor_alive_tree.png"),
    ("../docs/img/anchor_live_edit.gif", "assets/anchor_live_edit.gif"),
]


def build(repo_root: Path, out_dir: Path) -> int:
    html = (repo_root / "site" / "index.html").read_text(encoding="utf-8")

    staged: list[tuple[Path, str]] = []
    for src_rel, out_rel in IMAGE_ASSETS:
        src_path = (repo_root / "site" / src_rel).resolve()
        if not src_path.exists():
            print(f"ERROR: image asset not found: {src_path}", file=sys.stderr)
            return 1
        html = html.replace(f'src="{src_rel}"', f'src="{out_rel}"')
        staged.append((src_path, out_rel))

    for old, new in LINK_REWRITES.items():
        html = html.replace(f'href="{old}"', f'href="{new}"')

    leftover = [tok for tok in ('href="../', 'src="../') if tok in html]
    if leftover:
        print(f"ERROR: unrewritten relative refs remain: {leftover}", file=sys.stderr)
        return 1

    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "assets").mkdir(parents=True)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    for src_path, out_rel in staged:
        shutil.copy2(src_path, out_dir / out_rel)
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    print(f"OK: built Pages artifact at {out_dir} ({len(staged)} image assets)")
    return 0


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: build_pages.py <repo_root> <out_dir>", file=sys.stderr)
        return 2
    return build(Path(sys.argv[1]), Path(sys.argv[2]))


if __name__ == "__main__":
    sys.exit(main())
