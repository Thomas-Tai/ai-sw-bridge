"""Mock adapter for testing without SOLIDWORKS (W5.2).

Ported from SolidworksMCP-python (MIT, ESPO Corporation 2025).
SPDX-Port-Source: https://github.com/andrewbartels1/SolidworksMCP-python
SPDX-Port-Commit: 82e505d88da07fd81acd66b3cd85f6da65323ee4
SPDX-License-Identifier: MIT

Provides a mock implementation of SolidWorksAdapter that simulates
COM dispatch without requiring a live SOLIDWORKS session. The original
lives at ``src/solidworks_mcp/adapters/mock_adapter.py`` in the upstream.
This port simplifies the mock dispatch for ai-sw-bridge's testing needs.
"""

from __future__ import annotations

from typing import Any

from ..adapter import SolidWorksAdapter


class MockSolidWorksApp:
    """Mock ISldWorks COM dispatch object."""

    def __init__(self) -> None:
        self._active_doc: MockModelDoc | None = None

    def GetActiveDoc(self) -> MockModelDoc | None:
        """Return the active mock document."""
        return self._active_doc

    def NewDocument(
        self, template: str, doc_type: int, width: float, height: float
    ) -> MockModelDoc:
        """Create a new mock document."""
        doc = MockModelDoc(template=template, doc_type=doc_type)
        self._active_doc = doc
        return doc


class MockModelDoc:
    """Mock IModelDoc2 COM dispatch object."""

    def __init__(
        self,
        template: str = "",
        doc_type: int = 1,
        path: str = "",
    ) -> None:
        self._template = template
        self._doc_type = doc_type
        self._path = path
        self._title = "MockPart"
        self._custom_props: dict[str, str] = {}

    def GetPathName(self) -> str:
        """Return the mock document path."""
        return self._path

    def GetTitle(self) -> str:
        """Return the mock document title."""
        return self._title

    def GetType(self) -> int:
        """Return the mock document type (1=part, 2=assembly, 3=drawing)."""
        return self._doc_type


class MockAdapter(SolidWorksAdapter):
    """Mock adapter for testing without SOLIDWORKS.

    Simulates COM dispatch with mock objects. No actual SOLIDWORKS
    connection is established. Useful for unit tests and CI.

    Example:
        >>> adapter = MockAdapter()
        >>> adapter.connect()
        >>> sw = adapter.get_sw_app()
        >>> doc = adapter.get_active_doc()  # Returns None (no doc open)
        >>> adapter.disconnect()
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._sw_app: MockSolidWorksApp | None = None

    def connect(self) -> None:
        """Simulate connection to SOLIDWORKS (no-op)."""
        self._sw_app = MockSolidWorksApp()
        self._connected = True

    def disconnect(self) -> None:
        """Simulate disconnection (no-op)."""
        self._sw_app = None
        self._connected = False

    def get_sw_app(self) -> MockSolidWorksApp:
        """Return the mock ISldWorks dispatch.

        Returns:
            MockSolidWorksApp instance.

        Raises:
            ConnectionError: If not connected.
        """
        if not self._connected or self._sw_app is None:
            raise ConnectionError("MockAdapter not connected")
        self._operations_count += 1
        return self._sw_app

    def get_active_doc(self) -> MockModelDoc | None:
        """Return the mock active document.

        Returns:
            MockModelDoc if a document is open, None otherwise.

        Raises:
            ConnectionError: If not connected.
        """
        if not self._connected or self._sw_app is None:
            raise ConnectionError("MockAdapter not connected")
        self._operations_count += 1
        return self._sw_app.GetActiveDoc()
