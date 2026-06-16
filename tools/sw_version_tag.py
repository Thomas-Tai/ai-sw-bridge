#!/usr/bin/env python3
"""SW version tagging helper for the N/N-1 test matrix (D-4).

Reads a recorded SOLIDWORKS ``RevisionNumber`` string (e.g. ``"32.1.0"``)
and produces a human-readable version tag (``"SW2024"``) suitable for
labelling test-result records in the multi-version matrix.

This is pure Python — no COM, no seat, no ``pywin32``.  The seat supplies
``sw.RevisionNumber`` at runtime; this helper only consumes the string
after the fact, so it is fully unit-testable offline.

Revision model (mirrors ``spec._version_resolver``)::

    major 32  ->  SW 2024  (proven build, N)
    major 33  ->  SW 2025  (N-1 target)
    major 34  ->  SW 2026  (future)

The tag format is ``SW<year>`` where ``year = 1992 + major`` (SW's own
epoch: major 1 shipped in 1993, so major 32 == 2024).

Usage (in a test runner or CI harness)::

    from tools.sw_version_tag import tag_revision, tag_record

    tag = tag_revision("32.1.0")       # -> "SW2024"
    rec = tag_record({"ok": True}, "32.1.0")
    # rec == {"ok": True, "sw_version": "SW2024", "sw_major": 32}
"""

from __future__ import annotations

import sys
from typing import Any

# ---------------------------------------------------------------------------
# Revision -> year mapping
# ---------------------------------------------------------------------------

# SW epoch offset: major 1 == SW 1993, so year = 1992 + major.
_SW_EPOCH_OFFSET = 1992

# Explicitly named majors (documentation + guard-rail).
KNOWN_MAJORS: dict[int, str] = {
    32: "SW2024",
    33: "SW2025",
    34: "SW2026",
}

# Versions the matrix currently exercises.  Add here when a new seat arrives.
SUPPORTED_VERSIONS: tuple[str, ...] = ("SW2024", "SW2025")

# Features whose version behaviour is known to differ across N / N-1.
# ``True`` = supported on that version; ``False`` = expected to skip.
# Extend per-feature as the matrix grows (each seat run fills a cell).
FEATURE_VERSION_SUPPORT: dict[str, dict[str, bool]] = {
    "FeatureCut4": {"SW2024": True, "SW2025": False},
    "FeatureRevolve2": {"SW2024": True, "SW2025": False},
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_UNKNOWN_PREFIX = "SW_UNKNOWN"


def _major_from_revision(revision: str) -> int | None:
    """Parse the integer major from a dotted revision string.

    Accepts ``"32.1.0"``, ``"33"``, ``"33.0"``, or bare ``32``.  Returns
    ``None`` on anything unparseable (empty, non-numeric, ``None``).
    """
    if revision is None:
        return None
    if isinstance(revision, bool):
        return None
    if isinstance(revision, int):
        return revision
    try:
        return int(str(revision).split(".")[0])
    except (ValueError, IndexError):
        return None


def tag_revision(revision: str) -> str:
    """Return the human-readable tag for a ``RevisionNumber`` string.

    >>> tag_revision("32.1.0")
    'SW2024'
    >>> tag_revision("33")
    'SW2025'
    >>> tag_revision("garbage")
    'SW_UNKNOWN'
    """
    major = _major_from_revision(revision)
    if major is None:
        return _UNKNOWN_PREFIX
    if major in KNOWN_MAJORS:
        return KNOWN_MAJORS[major]
    return f"SW{_SW_EPOCH_OFFSET + major}"


def tag_record(record: dict[str, Any], revision: str) -> dict[str, Any]:
    """Annotate *record* (shallow copy) with ``sw_version`` + ``sw_major``.

    Returns a new dict — the input is never mutated.  Unknown revisions get
    ``sw_version="SW_UNKNOWN"`` and ``sw_major=None``.
    """
    major = _major_from_revision(revision)
    tagged = dict(record)
    tagged["sw_version"] = tag_revision(revision)
    tagged["sw_major"] = major
    return tagged


def should_skip(version_tag: str, feature: str) -> bool:
    """``True`` when *feature* is expected to be unsupported on *version_tag*.

    Returns ``False`` (do not skip) when the feature is not in the
    ``FEATURE_VERSION_SUPPORT`` table — absence means "no known gap, run it."
    """
    feature_map = FEATURE_VERSION_SUPPORT.get(feature)
    if feature_map is None:
        return False
    supported = feature_map.get(version_tag)
    if supported is None:
        return False
    return not supported


# ---------------------------------------------------------------------------
# CLI smoke (exit 0 if the helper imports + runs clean)
# ---------------------------------------------------------------------------


def _cli_main(argv: list[str] | None = None) -> int:
    import json

    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: sw_version_tag <revision> [<revision> ...]", file=sys.stderr)
        return 2
    for rev in args:
        rec = tag_record({"revision": rev}, rev)
        print(json.dumps(rec))
    return 0


if __name__ == "__main__":
    sys.exit(_cli_main())
