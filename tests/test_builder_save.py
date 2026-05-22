"""Tests for SaveAs3 postcondition verification (P0.1).

Exercises the failure modes that motivated the change:
  - SaveAs3 returns non-zero swFileSaveError
  - SaveAs3 returns 0 but file never lands on disk
  - SaveAs3 returns 0 but doc.GetSaveFlag stays True
  - All postconditions satisfied immediately
  - Postconditions satisfied on the second retry (OneDrive lag)

No SW required; the doc is a tiny stub. The point is to lock in the
verification contract so future edits to _save_as_with_verification
can't quietly regress the OneDrive-style silent-failure mode.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_sw_bridge.spec.builder import (
    BuildResult,
    _save_as_with_verification,
)


class _FakeDoc:
    """Minimal stand-in for IModelDoc2 covering the two surfaces the
    verifier uses: SaveAs3 (callable, returns int err code) and
    GetSaveFlag (property-like attribute, bool)."""

    def __init__(
        self,
        *,
        save_err: int = 0,
        dirty_after_save: bool = False,
        write_file: bool = True,
        dirty_clears_after: int = 0,
        file_appears_after: int = 0,
        content: bytes = b"sldprt-bytes",
    ) -> None:
        self._save_err = save_err
        self._initial_dirty = dirty_after_save
        self._dirty_clears_after = dirty_clears_after
        self._write_file = write_file
        self._file_appears_after = file_appears_after
        self._content = content
        self._path: Path | None = None
        self._save_calls = 0
        self._flag_reads = 0

    def SaveAs3(self, path: str, version: int, options: int) -> int:
        self._save_calls += 1
        self._path = Path(path)
        if self._save_err == 0 and self._write_file and self._file_appears_after == 0:
            self._path.write_bytes(self._content)
        return self._save_err

    @property
    def GetSaveFlag(self) -> bool:
        self._flag_reads += 1
        # File-appearance and dirty-clear are simulated by latency
        # measured in flag-read attempts (each attempt = one retry tick).
        if (
            self._write_file
            and self._file_appears_after > 0
            and self._flag_reads > self._file_appears_after
            and self._path is not None
            and not self._path.exists()
        ):
            self._path.write_bytes(self._content)
        if not self._initial_dirty:
            return False
        return self._flag_reads <= self._dirty_clears_after


def test_buildresult_includes_save_as_verified():
    """The dict shape MUST carry save_as_verified -- downstream tooling
    (the regression-check harness in P1.2) reads this field."""
    r = BuildResult(ok=True, features_built=["X"], bindings_added=[])
    assert "save_as_verified" in r.to_dict()
    assert r.to_dict()["save_as_verified"] is None  # default when save_as not used


def test_save_verifies_when_all_postconditions_pass(tmp_path: Path):
    out = tmp_path / "part.sldprt"
    doc = _FakeDoc()
    path, verified = _save_as_with_verification(doc, out)
    assert verified is True
    assert path == str(out)
    assert out.exists()
    assert doc._save_calls == 1


def test_save_raises_on_nonzero_swfilesaveerror(tmp_path: Path):
    out = tmp_path / "part.sldprt"
    doc = _FakeDoc(save_err=2, write_file=False)
    with pytest.raises(RuntimeError, match="swFileSaveError=2"):
        _save_as_with_verification(doc, out)


def test_save_raises_when_file_never_appears(tmp_path: Path):
    """Mimics the original OneDrive-eaten DriveRoller failure: SaveAs3
    returns NoError, but the file is never written."""
    out = tmp_path / "part.sldprt"
    doc = _FakeDoc(write_file=False)
    with pytest.raises(RuntimeError, match="postconditions unsatisfied"):
        _save_as_with_verification(doc, out)


def test_save_raises_when_dirty_flag_stays_true(tmp_path: Path):
    out = tmp_path / "part.sldprt"
    doc = _FakeDoc(dirty_after_save=True, dirty_clears_after=999)
    with pytest.raises(RuntimeError, match="dirty=True"):
        _save_as_with_verification(doc, out)


def test_save_succeeds_after_onedrive_lag(tmp_path: Path):
    """OneDrive scenario: SaveAs3 returns NoError immediately, but the
    file isn't visible until after the first retry. The verifier should
    pick it up on attempt 2 or 3."""
    out = tmp_path / "part.sldprt"
    # File appears after the FIRST GetSaveFlag read; the loop should
    # observe it on attempt 2 (after the first sleep).
    doc = _FakeDoc(file_appears_after=1)
    path, verified = _save_as_with_verification(doc, out)
    assert verified is True
    assert path == str(out)
    assert out.exists()
