"""N / N-1 SW version test matrix helpers.

Feed ``SW_VERSION_MATRIX`` to ``@pytest.mark.parametrize("sw_version", ...)``
to parametrise a test across the current seat (N) and the adjacent SW major
version (N-1).  The N-1 parameter carries the ``sw_version_n1`` marker; the
conftest in this package skips it when ``AI_SW_BRIDGE_N1_REVISION`` is absent.

Revision constants (from ``spec._version_resolver``)::

    SW 2024  major 32  (proven build; N in the standard dev environment)
    SW 2025  major 33  (N-1 target; requires a separate SW installation)

See docs/sw_version_matrix_runner.md for how W0 enables the N-1 run.
"""
from __future__ import annotations

import os

import pytest

# W0 sets this to the N-1 major revision integer string (e.g. "33" for SW 2025)
# before running the version-matrix suite on a versioned seat.
N1_REVISION_ENV = "AI_SW_BRIDGE_N1_REVISION"

N1_SKIP_REASON = (
    f"N-1 SW seat not configured — "
    f"set {N1_REVISION_ENV}=<major> and point sw_com at the N-1 process; "
    "see docs/sw_version_matrix_runner.md"
)

# Parametrize list for @pytest.mark.parametrize("sw_version", SW_VERSION_MATRIX).
# N runs unconditionally; N-1 is skipped unless AI_SW_BRIDGE_N1_REVISION is set.
SW_VERSION_MATRIX: list = [
    "N",
    pytest.param("N-1", marks=pytest.mark.sw_version_n1),
]


def n1_revision() -> str | None:
    """Return the configured N-1 major revision string, or None when absent."""
    return os.environ.get(N1_REVISION_ENV)
