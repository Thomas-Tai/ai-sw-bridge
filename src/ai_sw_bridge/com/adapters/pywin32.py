"""Pywin32 adapter for real SOLIDWORKS COM dispatch (W5.2).

Ported from SolidworksMCP-python (MIT, ESPO Corporation 2025).
SPDX-Port-Source: https://github.com/andrewbartels1/SolidworksMCP-python
SPDX-Port-Commit: 82e505d88da07fd81acd66b3cd85f6da65323ee4
SPDX-License-Identifier: MIT

Wraps pywin32's late-binding COM dispatch to implement the
SolidWorksAdapter interface. The original lives at
``src/solidworks_mcp/adapters/pywin32_adapter.py`` in the upstream.
This is the production adapter used when SOLIDWORKS is available.
"""

from __future__ import annotations

from typing import Any

from ..adapter import SolidWorksAdapter


class PyWin32Adapter(SolidWorksAdapter):
    """Pywin32-based adapter for real SOLIDWORKS COM dispatch.

    Uses win32com.client.Dispatch for late-binding COM dispatch.
    This is the default adapter on Windows when SOLIDWORKS is installed.

    Example:
        >>> adapter = PyWin32Adapter()
        >>> adapter.connect()
        >>> sw = adapter.get_sw_app()
        >>> doc = adapter.get_active_doc()
        >>> adapter.disconnect()
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._sw_app: Any = None

    def connect(self) -> None:
        """Connect to SOLIDWORKS via pywin32 COM dispatch.

        Raises:
            ConnectionError: If pywin32 is not available or COM dispatch fails.
        """
        try:
            import win32com.client
        except ImportError as exc:
            raise ConnectionError(
                "pywin32 not installed. Install with: pip install pywin32"
            ) from exc

        try:
            # Late binding only — no gencache.EnsureDispatch
            self._sw_app = win32com.client.Dispatch("SldWorks.Application")
            self._connected = True
        except Exception as exc:
            raise ConnectionError(
                f"Failed to connect to SOLIDWORKS via COM: {exc}"
            ) from exc

    def disconnect(self) -> None:
        """Disconnect from SOLIDWORKS (release COM reference)."""
        self._sw_app = None
        self._connected = False

    def get_sw_app(self) -> Any:
        """Return the ISldWorks COM dispatch object.

        Returns:
            win32com CDispatch object for ISldWorks.

        Raises:
            ConnectionError: If not connected.
        """
        if not self._connected or self._sw_app is None:
            raise ConnectionError("PyWin32Adapter not connected")
        self._operations_count += 1
        return self._sw_app

    def get_active_doc(self) -> Any:
        """Return the active IModelDoc2 COM dispatch object.

        Returns:
            win32com CDispatch for IModelDoc2, or None if no document is open.

        Raises:
            ConnectionError: If not connected.
        """
        if not self._connected or self._sw_app is None:
            raise ConnectionError("PyWin32Adapter not connected")
        self._operations_count += 1
        try:
            doc = self._sw_app.GetActiveDoc()
            return doc
        except Exception:
            return None
