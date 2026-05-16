"""ai-sw-bridge: AI-assistant control bridge for SOLIDWORKS via COM.

Public surface:
    from ai_sw_bridge import observe, mutate, parameterize, sw_com, locals_io
"""

__version__ = "0.1.0"

from . import locals_io, mutate, observe, parameterize, sw_com

__all__ = ["locals_io", "mutate", "observe", "parameterize", "sw_com", "__version__"]
