"""README is a persona router (spec §8.5): an operator-first front door with
signposted developer/contributor sections. This pins the structure so a later
edit can't silently un-route it."""

from __future__ import annotations

from pathlib import Path

_README = (Path(__file__).resolve().parents[1] / "README.md").read_text(
    encoding="utf-8"
)


def test_readme_has_persona_router_headings() -> None:
    for needle in (
        "Who are you?",  # the router
        "For operators",  # operator spine
        "For developers",  # dev teaser
        "For contributors",  # contributor teaser
    ):
        assert needle in _README, f"README persona-router section missing: {needle!r}"


def test_readme_links_operator_guide() -> None:
    assert "operator_guide.md" in _README
