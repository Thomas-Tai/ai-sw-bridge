"""Marker registration and skip wiring for the N / N-1 SW version matrix.

``pytest_configure`` registers the ``sw_version_n1`` marker so pytest never
emits an unknown-marker warning.  ``pytest_collection_modifyitems`` gates it
on ``AI_SW_BRIDGE_N1_REVISION``: when absent, every tagged item is skipped
with a human-readable reason (non-silent, mirrors the ``solidworks_only``
idiom in tests/conftest.py).

See docs/sw_version_matrix_runner.md for how W0 enables the N-1 run.
"""
from __future__ import annotations

import os

import pytest

# Keep in sync with version_matrix._matrix.N1_REVISION_ENV.
_N1_ENV = "AI_SW_BRIDGE_N1_REVISION"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        f"sw_version_n1: requires the N-1 SOLIDWORKS version seat — "
        f"skipped unless {_N1_ENV} is set "
        "(see docs/sw_version_matrix_runner.md)",
    )


def pytest_collection_modifyitems(items: list) -> None:
    if os.environ.get(_N1_ENV):
        return  # N-1 seat configured; all items may run
    reason = (
        f"N-1 SW seat not configured — "
        f"set {_N1_ENV}=<major> to enable; "
        "see docs/sw_version_matrix_runner.md"
    )
    skip = pytest.mark.skip(reason=reason)
    for item in items:
        if item.get_closest_marker("sw_version_n1"):
            item.add_marker(skip)
