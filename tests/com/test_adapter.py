"""Tests for com/adapter pattern (W5.2)."""

from __future__ import annotations

import platform

import pytest

from ai_sw_bridge.com.adapter import AdapterStatus, SolidWorksAdapter
from ai_sw_bridge.com.adapters.mock import MockAdapter
from ai_sw_bridge.com.adapters.pywin32 import PyWin32Adapter
from ai_sw_bridge.com.factory import AdapterFactory, create_adapter


class TestAdapterABC:
    """Tests for the SolidWorksAdapter abstract base class."""

    def test_mock_adapter_implements_abc(self) -> None:
        """MockAdapter must implement SolidWorksAdapter interface."""
        adapter = MockAdapter()
        assert isinstance(adapter, SolidWorksAdapter)

    def test_pywin32_adapter_implements_abc(self) -> None:
        """PyWin32Adapter must implement SolidWorksAdapter interface."""
        adapter = PyWin32Adapter()
        assert isinstance(adapter, SolidWorksAdapter)

    def test_initial_state_not_connected(self) -> None:
        """Adapters start disconnected."""
        adapter = MockAdapter()
        assert not adapter.is_connected()
        health = adapter.get_health()
        assert health.status == AdapterStatus.DISCONNECTED
        assert not health.connected

    def test_context_manager(self) -> None:
        """Adapter works as context manager."""
        with MockAdapter() as adapter:
            assert adapter.is_connected()
            sw = adapter.get_sw_app()
            assert sw is not None
        # After exit, should be disconnected
        assert not adapter.is_connected()


class TestMockAdapter:
    """Tests for the MockAdapter."""

    def test_connect_disconnect(self) -> None:
        """MockAdapter connect/disconnect lifecycle."""
        adapter = MockAdapter()
        adapter.connect()
        assert adapter.is_connected()
        adapter.disconnect()
        assert not adapter.is_connected()

    def test_get_sw_app_when_connected(self) -> None:
        """get_sw_app() returns mock app when connected."""
        adapter = MockAdapter()
        adapter.connect()
        sw = adapter.get_sw_app()
        assert sw is not None

    def test_get_sw_app_when_not_connected_raises(self) -> None:
        """get_sw_app() raises ConnectionError when not connected."""
        adapter = MockAdapter()
        with pytest.raises(ConnectionError, match="not connected"):
            adapter.get_sw_app()

    def test_get_active_doc_returns_none_initially(self) -> None:
        """get_active_doc() returns None when no document is open."""
        adapter = MockAdapter()
        adapter.connect()
        doc = adapter.get_active_doc()
        assert doc is None

    def test_operations_count_increments(self) -> None:
        """Operations counter increments on each call."""
        adapter = MockAdapter()
        adapter.connect()
        assert adapter._operations_count == 0
        adapter.get_sw_app()
        assert adapter._operations_count == 1
        adapter.get_active_doc()
        assert adapter._operations_count == 2


class TestAdapterFactory:
    """Tests for the AdapterFactory."""

    def test_create_mock_adapter(self) -> None:
        """Factory creates MockAdapter when requested."""
        adapter = AdapterFactory.create_adapter("mock")
        assert isinstance(adapter, MockAdapter)

    def test_create_pywin32_adapter(self) -> None:
        """Factory creates PyWin32Adapter when requested."""
        adapter = AdapterFactory.create_adapter("pywin32")
        assert isinstance(adapter, PyWin32Adapter)

    def test_auto_select_on_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Factory auto-selects pywin32 on Windows."""
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        adapter = AdapterFactory.create_adapter()
        assert isinstance(adapter, PyWin32Adapter)

    def test_auto_select_on_non_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Factory auto-selects mock on non-Windows."""
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        adapter = AdapterFactory.create_adapter()
        assert isinstance(adapter, MockAdapter)

    def test_unknown_adapter_type_raises(self) -> None:
        """Factory raises ValueError for unknown adapter type."""
        with pytest.raises(ValueError, match="Unknown adapter type"):
            AdapterFactory.create_adapter("nonexistent")

    def test_register_custom_adapter(self) -> None:
        """Factory allows registering custom adapters."""

        class CustomAdapter(SolidWorksAdapter):
            def connect(self) -> None:
                pass

            def disconnect(self) -> None:
                pass

            def get_sw_app(self) -> None:
                pass

            def get_active_doc(self) -> None:
                pass

        AdapterFactory.register_adapter("custom", CustomAdapter)
        adapter = AdapterFactory.create_adapter("custom")
        assert isinstance(adapter, CustomAdapter)

    def test_convenience_function(self) -> None:
        """create_adapter() convenience function works."""
        adapter = create_adapter("mock")
        assert isinstance(adapter, MockAdapter)


class TestAdapterHealth:
    """Tests for adapter health reporting."""

    def test_health_when_disconnected(self) -> None:
        """Health status is DISCONNECTED when not connected."""
        adapter = MockAdapter()
        health = adapter.get_health()
        assert health.status == AdapterStatus.DISCONNECTED
        assert not health.connected
        assert health.operations_count == 0
        assert health.errors_count == 0

    def test_health_when_connected(self) -> None:
        """Health status is HEALTHY when connected."""
        adapter = MockAdapter()
        adapter.connect()
        health = adapter.get_health()
        assert health.status == AdapterStatus.HEALTHY
        assert health.connected
