"""Tests for com.connection: stale-handle detection and reconnect logic.

Uses a synthetic ComError (no pywin32 dependency) matching the pattern
from connection.py's is_stale_handle_error() which reads exc.hresult or
exc.args[0] for the HRESULT value.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ai_sw_bridge.com.connection import (
    STALE_HANDLE_HRESULTS,
    is_stale_handle_error,
    reconnect_sw_app,
    with_reconnect,
)


# ---------------------------------------------------------------------------
# Stand-in for pywintypes.com_error (avoids pywin32 import in test env)
# ---------------------------------------------------------------------------


class ComError(Exception):
    """Mimics pywintypes.com_error for testing.

    pywintypes.com_error stores the HRESULT as args[0] and also exposes
    an .hresult attribute in some versions. Both paths are tested.
    """

    def __init__(self, hresult: int, description: str = "COM error"):
        self.hresult = hresult
        super().__init__(hresult, description)


# ---------------------------------------------------------------------------
# is_stale_handle_error
# ---------------------------------------------------------------------------


class TestIsStaleHandleError:
    """Stale-handle HRESULT detection."""

    def test_rpc_server_unavailable_via_hresult_attr(self):
        exc = ComError(0x800706BA, "RPC_S_SERVER_UNAVAILABLE")
        assert is_stale_handle_error(exc) is True

    def test_rpc_e_disconnected_via_hresult_attr(self):
        exc = ComError(0x80010108, "RPC_E_DISCONNECTED")
        assert is_stale_handle_error(exc) is True

    def test_non_stale_hresult(self):
        exc = ComError(0x80020003, "DISP_E_MEMBERNOTFOUND")
        assert is_stale_handle_error(exc) is False

    def test_generic_exception(self):
        assert is_stale_handle_error(RuntimeError("boom")) is False

    def test_args0_fallback_no_hresult_attr(self):
        """When .hresult is absent, is_stale_handle_error reads args[0]."""

        class ArgsOnlyError(Exception):
            pass

        exc = ArgsOnlyError(0x800706BA, "server gone")
        assert is_stale_handle_error(exc) is True

    def test_args0_non_int(self):
        exc = Exception("not an hresult")
        assert is_stale_handle_error(exc) is False

    def test_all_stale_hresults_detected(self):
        for hresult in STALE_HANDLE_HRESULTS:
            assert is_stale_handle_error(ComError(hresult)) is True


# ---------------------------------------------------------------------------
# reconnect_sw_app
# ---------------------------------------------------------------------------


class TestReconnectSwApp:
    """reconnect_sw_app() tears down the cached proxy and re-acquires."""

    @patch("ai_sw_bridge.sw_com.get_sw_app")
    @patch("ai_sw_bridge.sw_com.release_sw_app")
    def test_calls_release_then_get(self, mock_release, mock_get):
        mock_sw = MagicMock()
        mock_get.return_value = mock_sw
        result = reconnect_sw_app()
        mock_release.assert_called_once()
        mock_get.assert_called_once()
        assert result is mock_sw

    @patch("ai_sw_bridge.sw_com.get_sw_app")
    @patch("ai_sw_bridge.sw_com.release_sw_app")
    def test_emits_tier_c_hint_to_stderr(self, mock_release, mock_get, capsys):
        mock_get.return_value = MagicMock()
        reconnect_sw_app()
        captured = capsys.readouterr()
        assert "COM handle re-acquired mid-build" in captured.err


# ---------------------------------------------------------------------------
# with_reconnect
# ---------------------------------------------------------------------------


class TestWithReconnect:
    """with_reconnect() wrapper: retry-on-stale-handle semantics."""

    def test_success_path_no_reconnect(self):
        fn = MagicMock(return_value="ok")
        result = with_reconnect(fn, reconnect=False)
        assert result == "ok"
        assert fn.call_count == 1

    def test_success_path_with_reconnect(self):
        fn = MagicMock(return_value="ok")
        result = with_reconnect(fn, reconnect=True)
        assert result == "ok"
        assert fn.call_count == 1

    def test_non_stale_error_propagates_without_retry(self):
        fn = MagicMock(side_effect=RuntimeError("not COM"))
        with pytest.raises(RuntimeError, match="not COM"):
            with_reconnect(fn, reconnect=True)
        assert fn.call_count == 1

    def test_stale_error_without_reconnect_propagates(self):
        fn = MagicMock(side_effect=ComError(0x800706BA))
        with pytest.raises(ComError):
            with_reconnect(fn, reconnect=False)
        assert fn.call_count == 1

    @patch("ai_sw_bridge.com.connection.reconnect_sw_app")
    def test_stale_error_with_reconnect_retries_once(self, mock_reconnect):
        mock_reconnect.return_value = MagicMock()
        fn = MagicMock(side_effect=[ComError(0x800706BA), "recovered"])
        result = with_reconnect(fn, reconnect=True)
        assert result == "recovered"
        assert fn.call_count == 2
        mock_reconnect.assert_called_once()

    @patch("ai_sw_bridge.com.connection.reconnect_sw_app")
    def test_stale_error_with_reconnect_reraises_on_second_failure(
        self, mock_reconnect
    ):
        mock_reconnect.return_value = MagicMock()
        fn = MagicMock(side_effect=ComError(0x80010108))
        with pytest.raises(ComError):
            with_reconnect(fn, reconnect=True)
        assert fn.call_count == 2
        mock_reconnect.assert_called_once()

    @patch("ai_sw_bridge.com.connection.reconnect_sw_app")
    def test_args_kwargs_forwarded(self, mock_reconnect):
        mock_reconnect.return_value = MagicMock()
        fn = MagicMock(return_value="ok")
        result = with_reconnect(fn, "a", "b", reconnect=True, extra="c")
        fn.assert_called_once_with("a", "b", extra="c")
        assert result == "ok"


# ---------------------------------------------------------------------------
# Acceptance test: mock harness with injected RPC_S_SERVER_UNAVAILABLE
# passes with --reconnect; fails cleanly without it.
# ---------------------------------------------------------------------------


class TestAcceptance:
    """Task 1.12 acceptance criterion: mock harness with injected
    RPC_S_SERVER_UNAVAILABLE passes the build with --reconnect; fails
    cleanly without it.
    """

    def test_stale_handle_fails_without_reconnect(self):
        """Without --reconnect, a stale-handle error surfaces as a normal failure."""
        fn = MagicMock(side_effect=ComError(0x800706BA))
        with pytest.raises(ComError):
            with_reconnect(fn, reconnect=False)

    @patch("ai_sw_bridge.com.connection.reconnect_sw_app")
    def test_stale_handle_recovers_with_reconnect(self, mock_reconnect):
        """With --reconnect, a stale-handle error triggers one reconnect
        and retry, allowing the operation to succeed."""
        mock_reconnect.return_value = MagicMock()
        fn = MagicMock(side_effect=[ComError(0x800706BA), "success"])
        result = with_reconnect(fn, reconnect=True)
        assert result == "success"
        mock_reconnect.assert_called_once()

    @patch("ai_sw_bridge.com.connection.reconnect_sw_app")
    def test_stale_handle_double_failure_still_raises(self, mock_reconnect):
        """Even with --reconnect, if the retry ALSO fails, the error propagates."""
        mock_reconnect.return_value = MagicMock()
        fn = MagicMock(side_effect=ComError(0x800706BA))
        with pytest.raises(ComError):
            with_reconnect(fn, reconnect=True)
        assert fn.call_count == 2
