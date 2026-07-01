"""Unit tests for ai-sw-build's Issue #7 seat-identification gate.

``_seat_gate(assume_yes)`` prints which SOLIDWORKS seat the build is about to
drive (PID + active doc) and, on an interactive TTY, pauses for ``[y/N]``. It
returns ``None`` to proceed or an exit code to abort. These tests pin the whole
decision table WITHOUT a live seat: ``_find_sw_pids`` and the ``sw_com`` readers
are patched, so ``get_sw_app`` never attaches to (or launches) real SOLIDWORKS.

Crux: ``--yes`` and a non-TTY stdin PROCEED (return None) after the banner; an
interactive ``y`` proceeds; ``n`` / bare-Enter abort cleanly (exit 0, not an
error); EOF on a pseudo-TTY PROCEEDS (agent harnesses run under a PTY). The
banner write is encoding-hardened so a CJK doc title can never crash the gate.
"""

from __future__ import annotations

import json
import sys
from unittest.mock import patch

from ai_sw_bridge.cli.build import _eprint, _seat_gate

_PIDS = "ai_sw_bridge.resilience.session._find_sw_pids"
_GET_APP = "ai_sw_bridge.sw_com.get_sw_app"
_GET_DOC = "ai_sw_bridge.sw_com.get_active_doc"
_RESOLVE = "ai_sw_bridge.sw_com.resolve"


class _FakeStdin:
    """Minimal stdin stand-in: only ``isatty`` matters to the gate."""

    def __init__(self, tty: bool) -> None:
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def test_yes_prints_banner_and_proceeds_without_prompting(capsys):
    # --yes short-circuits before isatty/input: banner still prints, no prompt.
    def _no_prompt(*_a, **_k):
        raise AssertionError("input() must not be called under --yes")

    with (
        patch(_PIDS, return_value=[1234]),
        patch(_GET_APP, return_value=object()),
        patch(_GET_DOC, return_value=None),
        patch("builtins.input", _no_prompt),
    ):
        rc = _seat_gate(assume_yes=True)
    assert rc is None
    err = capsys.readouterr().err
    assert "[PID: 1234]" in err
    assert "will not overwrite" in err


def test_no_running_sw_proceeds_and_warns(capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdin", _FakeStdin(tty=False))
    with patch(_PIDS, return_value=[]):
        rc = _seat_gate(assume_yes=False)
    assert rc is None
    err = capsys.readouterr().err
    assert "no running SOLIDWORKS" in err
    assert "will not overwrite" in err


def test_banner_reports_active_doc_title(capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdin", _FakeStdin(tty=False))
    with (
        patch(_PIDS, return_value=[42]),
        patch(_GET_APP, return_value=object()),
        patch(_GET_DOC, return_value=object()),
        patch(_RESOLVE, return_value="bracket.SLDPRT"),
    ):
        rc = _seat_gate(assume_yes=False)
    assert rc is None
    err = capsys.readouterr().err
    assert "[PID: 42]" in err and "bracket.SLDPRT" in err
    assert "will not overwrite" in err


def test_multiple_pids_listed_with_active_doc_disambiguator(capsys, monkeypatch):
    # Several seats: list ALL pids and lean on the active-doc title as the real
    # disambiguator (get_sw_app attaches to the ROT instance, not pids[0]).
    monkeypatch.setattr(sys, "stdin", _FakeStdin(tty=False))
    with (
        patch(_PIDS, return_value=[30, 10, 20]),
        patch(_GET_APP, return_value=object()),
        patch(_GET_DOC, return_value=None),
    ):
        rc = _seat_gate(assume_yes=False)
    assert rc is None
    err = capsys.readouterr().err
    assert "[PID: 10, 20, 30]" in err and "3 seats running" in err


def test_active_doc_read_failure_degrades_to_unknown(capsys, monkeypatch):
    # A COM hiccup reading the title must not abort the gate; show "unknown".
    monkeypatch.setattr(sys, "stdin", _FakeStdin(tty=False))
    with (
        patch(_PIDS, return_value=[9]),
        patch(_GET_APP, side_effect=RuntimeError("com boom")),
    ):
        rc = _seat_gate(assume_yes=False)
    assert rc is None
    assert "unknown" in capsys.readouterr().err


def test_interactive_yes_proceeds(monkeypatch):
    monkeypatch.setattr(sys, "stdin", _FakeStdin(tty=True))
    with (
        patch(_PIDS, return_value=[7]),
        patch(_GET_APP, return_value=object()),
        patch(_GET_DOC, return_value=None),
        patch("builtins.input", return_value="y"),
    ):
        rc = _seat_gate(assume_yes=False)
    assert rc is None


def test_interactive_no_aborts_clean_exit_zero(capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdin", _FakeStdin(tty=True))
    with (
        patch(_PIDS, return_value=[7]),
        patch(_GET_APP, return_value=object()),
        patch(_GET_DOC, return_value=None),
        patch("builtins.input", return_value="n"),
    ):
        rc = _seat_gate(assume_yes=False)
    assert rc == 0  # a clean decline is not an error
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False and payload["aborted"] is True


def test_interactive_bare_enter_defaults_to_abort(capsys, monkeypatch):
    # [y/N] -> empty input is the default "no".
    monkeypatch.setattr(sys, "stdin", _FakeStdin(tty=True))
    with (
        patch(_PIDS, return_value=[7]),
        patch(_GET_APP, return_value=object()),
        patch(_GET_DOC, return_value=None),
        patch("builtins.input", return_value=""),
    ):
        rc = _seat_gate(assume_yes=False)
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["aborted"] is True


def test_pseudo_tty_eof_proceeds(monkeypatch):
    # isatty()==True but input() EOFs (agent/CI PTY): proceed, don't abort.
    monkeypatch.setattr(sys, "stdin", _FakeStdin(tty=True))
    with (
        patch(_PIDS, return_value=[7]),
        patch(_GET_APP, return_value=object()),
        patch(_GET_DOC, return_value=None),
        patch("builtins.input", side_effect=EOFError),
    ):
        rc = _seat_gate(assume_yes=False)
    assert rc is None


def test_eprint_degrades_on_cp1252_console(monkeypatch):
    # A console that can't encode CJK must not crash the banner: _eprint
    # replaces the offending glyphs instead of propagating UnicodeEncodeError.
    class _Cp1252Stderr:
        encoding = "cp1252"

        def __init__(self) -> None:
            self.buf: list[str] = []

        def write(self, s: str) -> int:
            s.encode("cp1252")  # raises UnicodeEncodeError on CJK
            self.buf.append(s)
            return len(s)

        def flush(self) -> None:
            pass

    fake = _Cp1252Stderr()
    monkeypatch.setattr(sys, "stderr", fake)
    _eprint("ai-sw-build: attached (active doc: 壁報.SLDPRT).")  # must not raise
    joined = "".join(fake.buf)
    assert "active doc:" in joined and "?" in joined
