"""Scaffold tests demonstrating the N / N-1 version matrix mechanism.

OFFLINE — no seat, no COM calls.  Verifies:
  1. SW_VERSION_MATRIX has the expected shape (N + marked N-1).
  2. n1_revision() reflects the env var state.
  3. A parametrised test: N runs; N-1 is skipped by the conftest hook with a
     non-silent reason when AI_SW_BRIDGE_N1_REVISION is absent.
  4. The skip reason text is informative (names the env var and the doc).
"""

from __future__ import annotations

import pytest

from version_matrix._matrix import (
    N1_REVISION_ENV,
    N1_SKIP_REASON,
    SW_VERSION_MATRIX,
    n1_revision,
)


def test_sw_version_matrix_shape():
    """Matrix must have exactly two entries: plain 'N' and a marked 'N-1'."""
    assert len(SW_VERSION_MATRIX) == 2
    assert SW_VERSION_MATRIX[0] == "N"
    n1_param = SW_VERSION_MATRIX[1]
    assert hasattr(n1_param, "values"), "N-1 entry must be a pytest.param"
    assert n1_param.values == ("N-1",)


def test_n1_revision_absent_by_default(monkeypatch):
    """n1_revision() returns None when the env var is not set."""
    monkeypatch.delenv(N1_REVISION_ENV, raising=False)
    assert n1_revision() is None


def test_n1_revision_present(monkeypatch):
    """n1_revision() returns the env value when set."""
    monkeypatch.setenv(N1_REVISION_ENV, "33")
    assert n1_revision() == "33"


def test_n1_skip_reason_is_informative():
    """The skip reason must name the env var and the runner doc."""
    assert N1_REVISION_ENV in N1_SKIP_REASON
    assert "sw_version_matrix_runner" in N1_SKIP_REASON


@pytest.mark.parametrize("sw_version", SW_VERSION_MATRIX)
def test_version_matrix_parametrize(sw_version):
    """N variant runs; N-1 variant is skipped by the conftest hook.

    When AI_SW_BRIDGE_N1_REVISION is absent, only the N param executes.
    When the env var is set, both params run and both values are accepted.
    """
    assert sw_version in ("N", "N-1")
