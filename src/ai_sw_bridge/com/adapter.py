"""Abstract base class for SOLIDWORKS adapters (W5.2).

Ported from SolidworksMCP-python (MIT, ESPO Corporation 2025).
SPDX-Port-Source: https://github.com/andrewbartels1/SolidworksMCP-python
SPDX-Port-Commit: 82e505d88da07fd81acd66b3cd85f6da65323ee4
SPDX-License-Identifier: MIT

Defines the common interface that all SOLIDWORKS adapters must implement.
The original lives at ``src/solidworks_mcp/adapters/base.py`` in the upstream.
This port simplifies to a sync interface and removes the pydantic dependency
to match ai-sw-bridge's stdlib-only style.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AdapterStatus(Enum):
    """Adapter health status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    DISCONNECTED = "disconnected"


@dataclass
class AdapterHealth:
    """Health status information for an adapter."""

    status: AdapterStatus
    connected: bool
    operations_count: int = 0
    errors_count: int = 0
    average_response_time: float = 0.0
    last_error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SolidWorksAdapter(ABC):
    """Base adapter interface for SOLIDWORKS integration.

    All adapters (pywin32, mock, future edge-dotnet) must implement this
    interface. The adapter wraps the underlying COM dispatch and provides
    a consistent API for the bridge's spec builder and observe tools.

    Lifecycle:
        1. Create adapter via factory (see com/factory.py)
        2. Call connect() to establish COM connection
        3. Use get_sw_app() / get_active_doc() for operations
        4. Call disconnect() when done (or use as context manager)
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize adapter with optional configuration.

        Args:
            config: Adapter-specific configuration dict. Keys vary by
                implementation (e.g., "timeout", "retry_attempts").
        """
        self.config = config or {}
        self._connected = False
        self._operations_count = 0
        self._errors_count = 0

    @abstractmethod
    def connect(self) -> None:
        """Connect to SOLIDWORKS application.

        Raises:
            ConnectionError: If connection fails.
        """

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from SOLIDWORKS application."""

    @abstractmethod
    def get_sw_app(self) -> Any:
        """Return the ISldWorks COM dispatch object.

        Returns:
            The ISldWorks dispatch (pywin32 CDispatch or mock equivalent).

        Raises:
            ConnectionError: If not connected.
        """

    @abstractmethod
    def get_active_doc(self) -> Any:
        """Return the active IModelDoc2 COM dispatch object.

        Returns:
            The IModelDoc2 dispatch, or None if no document is open.

        Raises:
            ConnectionError: If not connected.
        """

    def is_connected(self) -> bool:
        """Check if adapter is currently connected.

        Returns:
            True if connected, False otherwise.
        """
        return self._connected

    def get_health(self) -> AdapterHealth:
        """Return current health status of the adapter.

        Returns:
            AdapterHealth with status, connection state, and metrics.
        """
        status = (
            AdapterStatus.HEALTHY if self._connected else AdapterStatus.DISCONNECTED
        )
        return AdapterHealth(
            status=status,
            connected=self._connected,
            operations_count=self._operations_count,
            errors_count=self._errors_count,
        )

    def __enter__(self) -> "SolidWorksAdapter":
        """Context manager entry: connect."""
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit: disconnect."""
        self.disconnect()
