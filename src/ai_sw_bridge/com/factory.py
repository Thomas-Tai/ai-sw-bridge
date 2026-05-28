"""Adapter factory for creating SOLIDWORKS adapters (W5.2).

Ported from SolidworksMCP-python (MIT, ESPO Corporation 2025).
SPDX-Port-Source: https://github.com/andrewbartels1/SolidworksMCP-python
SPDX-Port-Commit: 82e505d88da07fd81acd66b3cd85f6da65323ee4
SPDX-License-Identifier: MIT

Provides centralized adapter creation with configuration-based selection
and automatic fallback strategies. The original lives at
``src/solidworks_mcp/adapters/factory.py`` in the upstream. This port
simplifies the factory for ai-sw-bridge's sync, stdlib-only style.
"""

from __future__ import annotations

import platform
from typing import Any

from .adapter import SolidWorksAdapter
from .adapters.mock import MockAdapter
from .adapters.pywin32 import PyWin32Adapter


class AdapterFactory:
    """Factory for creating SOLIDWORKS adapters.

    Selects the appropriate adapter based on platform and configuration.
    Defaults to PyWin32Adapter on Windows, MockAdapter elsewhere.

    Example:
        >>> factory = AdapterFactory()
        >>> adapter = factory.create_adapter()
        >>> adapter.connect()
        >>> sw = adapter.get_sw_app()
    """

    _registry: dict[str, type[SolidWorksAdapter]] = {
        "pywin32": PyWin32Adapter,
        "mock": MockAdapter,
    }

    @classmethod
    def register_adapter(
        cls, name: str, adapter_class: type[SolidWorksAdapter]
    ) -> None:
        """Register a custom adapter class.

        Args:
            name: Adapter name (e.g., "edge-dotnet").
            adapter_class: Adapter class to register.
        """
        cls._registry[name] = adapter_class

    @classmethod
    def create_adapter(
        cls,
        adapter_type: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> SolidWorksAdapter:
        """Create an adapter instance.

        Args:
            adapter_type: Adapter name ("pywin32", "mock", or registered custom).
                If None, auto-selects based on platform.
            config: Adapter-specific configuration.

        Returns:
            Adapter instance (not yet connected).

        Raises:
            ValueError: If adapter_type is not registered.
        """
        if adapter_type is None:
            # Auto-select: pywin32 on Windows, mock elsewhere
            adapter_type = "pywin32" if platform.system() == "Windows" else "mock"

        if adapter_type not in cls._registry:
            raise ValueError(
                f"Unknown adapter type: {adapter_type!r}. "
                f"Registered: {list(cls._registry.keys())}"
            )

        adapter_class = cls._registry[adapter_type]
        return adapter_class(config)


def create_adapter(
    adapter_type: str | None = None,
    config: dict[str, Any] | None = None,
) -> SolidWorksAdapter:
    """Convenience function for creating adapters.

    Args:
        adapter_type: Adapter name (see AdapterFactory.create_adapter).
        config: Adapter-specific configuration.

    Returns:
        Adapter instance (not yet connected).
    """
    return AdapterFactory.create_adapter(adapter_type, config)
