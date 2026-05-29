"""ai-sw-bridge: AI-assistant control bridge for SOLIDWORKS via COM.

Public surface:
    from ai_sw_bridge import observe, mutate, parameterize, sw_com, locals_io
    from ai_sw_bridge import locals_io  # works on Linux too -- doesn't pull pywin32

The pywin32-dependent modules (observe, mutate, sw_com) are loaded lazily
via PEP 562 __getattr__ so the package can be imported on non-Windows
systems for the pure-Python utilities (locals_io, parameterize, spec).
"""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("ai-sw-bridge")
except PackageNotFoundError:
    # Source checkout without ``pip install -e .`` or frozen build
    # without dist-info — fall back so ``ai_sw_bridge.__version__``
    # is always a readable string for diagnostics.
    __version__ = "0.0.0+unknown"

_LAZY_MODULES = frozenset(
    {"locals_io", "mutate", "observe", "parameterize", "sw_com", "spec"}
)


def __getattr__(name):
    if name in _LAZY_MODULES:
        import importlib

        mod = importlib.import_module(f".{name}", __name__)
        globals()[name] = mod
        return mod
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | _LAZY_MODULES)


__all__ = [
    "locals_io",
    "mutate",
    "observe",
    "parameterize",
    "sw_com",
    "spec",
    "__version__",
]
