"""Tests for NO_COLOR / isatty color degradation (W2.3).

Parametrized over NO_COLOR env var, stderr.isatty(), and --quiet
(stderr redirected to devnull). Verifies that should_use_color(),
strip_ansi(), PlainFormatter, and progress_cr() all behave correctly
across the matrix.
"""

from __future__ import annotations

import io
import logging
import os
import sys
from unittest.mock import patch

import pytest

from ai_sw_bridge.cli.streams import (
    PlainFormatter,
    progress_cr,
    should_use_color,
    strip_ansi,
)


class _FakeStderr(io.StringIO):
    """StringIO subclass with a controllable isatty() return value.

    Instance-attribute monkey-patching of isatty doesn't reliably
    override the C-level method on _io.StringIO, so we override it
    at the class level.
    """

    def __init__(self, tty: bool = False) -> None:
        super().__init__()
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


@pytest.fixture(autouse=True)
def _reset_color_cache():
    """Reset the should_use_color cache before every test."""
    should_use_color(_reset=True)
    yield
    should_use_color(_reset=True)


# ---------------------------------------------------------------------------
# strip_ansi
# ---------------------------------------------------------------------------


class TestStripAnsi:
    def test_removes_sgr_codes(self) -> None:
        assert strip_ansi("\x1b[31mhello\x1b[0m") == "hello"

    def test_removes_multi_param_sgr(self) -> None:
        assert strip_ansi("\x1b[1;32;40mbold green on black\x1b[0m") == (
            "bold green on black"
        )

    def test_noop_on_plain_text(self) -> None:
        assert strip_ansi("no codes here") == "no codes here"

    def test_empty_string(self) -> None:
        assert strip_ansi("") == ""

    def test_mixed_content(self) -> None:
        text = "prefix \x1b[33mwarning\x1b[0m suffix"
        assert strip_ansi(text) == "prefix warning suffix"

    def test_multiple_sgr_sequences(self) -> None:
        text = "\x1b[1m\x1b[31mERROR\x1b[0m \x1b[33mmsg\x1b[0m"
        assert strip_ansi(text) == "ERROR msg"


# ---------------------------------------------------------------------------
# should_use_color
# ---------------------------------------------------------------------------


class TestShouldUseColor:
    def test_no_color_set_returns_false(self) -> None:
        with patch.dict(os.environ, {"NO_COLOR": "1"}, clear=False):
            assert should_use_color() is False

    def test_no_color_empty_string_returns_false(self) -> None:
        """NO_COLOR="" still counts as 'set' per no-color.org."""
        with patch.dict(os.environ, {"NO_COLOR": ""}, clear=False):
            assert should_use_color() is False

    def test_no_color_absent_tty_returns_true(self) -> None:
        fake_stderr = _FakeStderr(tty=True)
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(sys, "stderr", fake_stderr):
                assert should_use_color() is True

    def test_no_color_absent_not_tty_returns_false(self) -> None:
        fake_stderr = _FakeStderr(tty=False)
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(sys, "stderr", fake_stderr):
                assert should_use_color() is False

    def test_no_color_overrides_tty(self) -> None:
        """NO_COLOR wins even when stderr is a TTY."""
        fake_stderr = _FakeStderr(tty=True)
        with patch.dict(os.environ, {"NO_COLOR": "1"}, clear=False):
            with patch.object(sys, "stderr", fake_stderr):
                assert should_use_color() is False

    def test_quiet_redirects_stderr_to_devnull(self) -> None:
        """--quiet -> stderr is devnull -> isatty() False -> no color."""
        devnull = _FakeStderr(tty=False)
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(sys, "stderr", devnull):
                assert should_use_color() is False

    def test_caching(self) -> None:
        """Result is cached after first call."""
        fake_stderr = _FakeStderr(tty=True)
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(sys, "stderr", fake_stderr):
                first = should_use_color()
                assert first is True
                # Change env after caching — should still return cached value
                os.environ["NO_COLOR"] = "1"
                assert should_use_color() is True

    def test_reset_clears_cache(self) -> None:
        """_reset=True invalidates the cache."""
        fake_stderr = _FakeStderr(tty=True)
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(sys, "stderr", fake_stderr):
                assert should_use_color() is True
        # Now change the environment and reset
        with patch.dict(os.environ, {"NO_COLOR": "1"}, clear=False):
            should_use_color(_reset=True)
            assert should_use_color() is False

    @pytest.mark.parametrize(
        "no_color,isatty,expected",
        [
            (None, True, True),
            (None, False, False),
            ("", True, False),
            ("1", True, False),
            ("1", False, False),
        ],
        ids=[
            "unset+tty",
            "unset+pipe",
            "empty+tty",
            "set+tty",
            "set+pipe",
        ],
    )
    def test_parametrized_matrix(
        self,
        no_color: str | None,
        isatty: bool,
        expected: bool,
    ) -> None:
        fake_stderr = _FakeStderr(tty=isatty)
        env = {} if no_color is None else {"NO_COLOR": no_color}
        with patch.dict(os.environ, env, clear=True):
            with patch.object(sys, "stderr", fake_stderr):
                assert should_use_color() is expected


# ---------------------------------------------------------------------------
# PlainFormatter
# ---------------------------------------------------------------------------


class TestPlainFormatter:
    def _make_record(self, msg: str = "test message") -> logging.LogRecord:
        return logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )

    def test_strips_ansi_when_no_color(self) -> None:
        with patch.dict(os.environ, {"NO_COLOR": "1"}, clear=False):
            fmt = PlainFormatter(fmt="%(message)s")
            record = self._make_record("\x1b[31mred\x1b[0m")
            assert fmt.format(record) == "red"

    def test_preserves_ansi_when_color_available(self) -> None:
        fake_stderr = _FakeStderr(tty=True)
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(sys, "stderr", fake_stderr):
                fmt = PlainFormatter(fmt="%(message)s")
                record = self._make_record("\x1b[31mred\x1b[0m")
                assert fmt.format(record) == "\x1b[31mred\x1b[0m"

    def test_force_plain_always_strips(self) -> None:
        """force_plain=True strips even when color is available."""
        fake_stderr = _FakeStderr(tty=True)
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(sys, "stderr", fake_stderr):
                fmt = PlainFormatter(fmt="%(message)s", force_plain=True)
                record = self._make_record("\x1b[31mred\x1b[0m")
                assert fmt.format(record) == "red"

    def test_force_plain_false_preserves(self) -> None:
        """force_plain=False preserves ANSI even with NO_COLOR."""
        with patch.dict(os.environ, {"NO_COLOR": "1"}, clear=False):
            fmt = PlainFormatter(fmt="%(message)s", force_plain=False)
            record = self._make_record("\x1b[31mred\x1b[0m")
            assert fmt.format(record) == "\x1b[31mred\x1b[0m"

    def test_plain_text_unchanged(self) -> None:
        fmt = PlainFormatter(fmt="%(levelname)s %(message)s")
        record = self._make_record("hello")
        assert fmt.format(record) == "INFO hello"


# ---------------------------------------------------------------------------
# progress_cr
# ---------------------------------------------------------------------------


class TestProgressCr:
    def test_cr_on_tty(self) -> None:
        fake_stderr = _FakeStderr(tty=True)
        with patch.object(sys, "stderr", fake_stderr):
            assert progress_cr() == "\r"

    def test_newline_on_pipe(self) -> None:
        fake_stderr = _FakeStderr(tty=False)
        with patch.object(sys, "stderr", fake_stderr):
            assert progress_cr() == "\n"

    def test_newline_on_devnull(self) -> None:
        fake_stderr = _FakeStderr(tty=False)
        with patch.object(sys, "stderr", fake_stderr):
            assert progress_cr() == "\n"
