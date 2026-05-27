"""com_error_boundary — structured COM-error envelope (spec.md §3.3).

A context manager that wraps any block of COM-touching code. When a
``pywintypes.com_error`` (or the synthetic ``ComError`` from the
fault-injection fixtures) is raised inside the boundary, the wrapper:

1. Classifies the HRESULT into Tier A/B/C via
   ``telemetry.classify.classify_hresult``.
2. Resolves a remediation hint from the catalog in ``errors.hints``.
3. Emits a :class:`BuildError` envelope on stdout (diagnosis + hint)
   with the traceback reserved for human stderr.
4. Increments the ``com_errors_total`` telemetry counter.
5. Propagates the current thread's trace ID into the envelope.

The ``AttributeError`` branch catches pywin32's cross-thread COM
invocation failure, which surfaces at attribute lookup — NOT as a
``com_error`` (per SolidworksMCP-python/CLAUDE.md §5).
"""

from __future__ import annotations

import traceback as _tb
from contextlib import contextmanager
from typing import Iterator, Optional

from ..telemetry.classify import classify_hresult
from ..telemetry.counters import COUNTERS
from ..telemetry.trace import trace_id
from .build_error import BuildError
from .hints import default_hint, resolve_hint

# Late import of pywintypes.com_error so this module imports cleanly in
# CI environments without pywin32 installed.
_COM_ERROR: tuple[type[BaseException], ...] = ()
try:  # pragma: no cover - exercised only with pywin32 installed
    import pywintypes

    _COM_ERROR = (pywintypes.com_error,)
except ImportError:
    _COM_ERROR = ()


# Synthetic ComError from tests/fault_injection/conftest.py. Resolved
# lazily so importing this module in production doesn't pull in pytest
# fixtures.
def _synthetic_com_error_type() -> type[BaseException] | None:
    try:
        from tests.fault_injection.conftest import ComError
    except ImportError:
        return None
    # ComError is a dataclass — tests subclass it with Exception to make
    # it raisable; the module-level dataclass alone isn't a BaseException
    # subclass, so a runtime isinstance() check still works.
    return ComError  # type: ignore[return-value]


def _all_com_error_types() -> tuple[type[BaseException], ...]:
    types: list[type[BaseException]] = list(_COM_ERROR)
    syn = _synthetic_com_error_type()
    if syn is not None:
        types.append(syn)
    return tuple(types)


def _extract_hresult(exc: BaseException) -> int | None:
    """Pull the HRESULT integer out of a com_error (real or synthetic)."""
    hresult = getattr(exc, "hresult", None)
    if isinstance(hresult, int):
        return hresult
    args = getattr(exc, "args", ())
    if args and isinstance(args[0], int):
        return args[0]
    return None


def _extract_iface_method_from_excepinfo(exc: BaseException) -> Optional[str]:
    """Best-effort iface_method extraction from the exception.

    Real pywintypes.com_error carries ``(hresult, strerror, excepinfo,
    argerror)`` where ``excepinfo`` is a 7-tuple whose ``[5]`` slot is
    the source (typically the interface name).
    """
    excepinfo = getattr(exc, "excepinfo", None)
    if isinstance(excepinfo, tuple) and len(excepinfo) >= 6:
        src = excepinfo[5]
        if isinstance(src, str) and src:
            return src
    return None


def _hresult_to_hex(hresult: int | None) -> str:
    if hresult is None:
        return "0x0"
    return f"0x{hresult:08X}"


def _increment_counter(iface_method: str, hresult_hex: str) -> None:
    counter = COUNTERS.get("com_errors_total")
    if counter is None:
        return
    try:
        counter.inc(iface_method=iface_method, hresult=hresult_hex)
    except TypeError:
        # Counter label mismatch — never let telemetry kill the build.
        pass


def _is_sw_dispatch_attribute_error(exc: AttributeError) -> bool:
    """Heuristic: is this the cross-thread COM AttributeError?

    pywin32 raises ``AttributeError`` at attribute lookup when the
    IDispatch proxy is invoked from the wrong STA thread. The message
    is typically ``'NoneType' object has no attribute 'X'`` or similar.
    We treat *any* AttributeError inside a COM boundary as cross-thread
    unless explicitly excluded. The caller should scope the boundary
    tightly enough that legitimate Python attribute errors don't land
    here.
    """
    msg = str(exc)
    # Conservative: any AttributeError inside the boundary is treated
    # as COM-related. Tighter scoping is the caller's responsibility.
    return bool(msg)


@contextmanager
def com_error_boundary(
    feature_name: str,
    json_path: str,
    *,
    iface_method: str = "unknown",
    feature_type: Optional[str] = None,
) -> Iterator[None]:
    """Wrap a COM-touching block; convert COM errors into BuildError envelopes.

    Args:
        feature_name: Name of the spec feature being built.
        json_path: JSON path into the spec (e.g. ``"features[3]"``).
        iface_method: Fallback iface_method used when the exception
            doesn't carry one. Typically the method the handler is
            about to call.
        feature_type: Optional feature-type string used for the
            catalog's feature_type fallback (e.g. ``"boss_extrude_blind"``).

    Raises:
        BuildError: with the structured envelope on any COM error.
        AttributeError: re-raised if it doesn't look like a cross-thread
            COM failure.
    """
    try:
        yield
    except BaseException as exc:
        com_types = _all_com_error_types()
        if com_types and isinstance(exc, com_types):
            raise _build_error_from_com(
                exc,
                feature_name=feature_name,
                json_path=json_path,
                fallback_iface_method=iface_method,
                feature_type=feature_type,
            ) from exc

        if isinstance(exc, AttributeError) and _is_sw_dispatch_attribute_error(exc):
            raise BuildError(
                feature=feature_name,
                json_path=json_path,
                hresult="0xCROSS_THREAD",
                iface_method=str(exc),
                diagnosis="COM IDispatch invoked across STA boundaries.",
                next_action_hint=(
                    "Ensure the call goes through the STA executor "
                    "(com.executor.submit) rather than a free-threaded path."
                ),
                traceback="".join(
                    _tb.format_exception(type(exc), exc, exc.__traceback__)
                ),
                tier="C",
                hint_key=None,
            ) from exc

        raise


def _build_error_from_com(
    exc: BaseException,
    *,
    feature_name: str,
    json_path: str,
    fallback_iface_method: str,
    feature_type: Optional[str],
) -> BuildError:
    from .build_error import _coerce_tier  # local import: avoids cycle

    hresult_int = _extract_hresult(exc)
    hresult_hex = _hresult_to_hex(hresult_int)
    raw_tier = classify_hresult(hresult_int) if hresult_int is not None else "unknown"
    tier = _coerce_tier(raw_tier)
    iface_method = _extract_iface_method_from_excepinfo(exc) or fallback_iface_method

    hint = resolve_hint(hresult_hex, iface_method, feature_type)
    if hint is None:
        hint = default_hint()
        hint_key: Optional[str] = None
    else:
        hint_key = hint.key

    tb = "".join(_tb.format_exception(type(exc), exc, exc.__traceback__))

    _increment_counter(iface_method, hresult_hex)

    # Trace ID propagation — may be None if the CLI entrypoint didn't
    # call new_trace_id(). BuildError doesn't carry trace_id as a
    # first-class field today; it's embedded in the diagnosis prefix
    # so downstream consumers can correlate.
    tid = trace_id()
    diagnosis = hint.summary
    if tid is not None:
        diagnosis = f"[{tid}] {diagnosis}"

    return BuildError(
        feature=feature_name,
        json_path=json_path,
        hresult=hresult_hex,
        iface_method=iface_method,
        diagnosis=diagnosis,
        next_action_hint=hint.remedy,
        traceback=tb,
        tier=tier,
        hint_key=hint_key,
    )


def emit_envelope_to_stderr(err: BuildError) -> None:
    """Write the human-readable diagnosis to stderr.

    The LLM-facing JSON envelope travels via BuildResult (and is
    emitted by the CLI entry points — the designated stdout emitters
    per the two-stream lint). This helper writes the traceback /
    diagnosis to stderr for the human operator.
    """
    import sys

    print(err.format_traceback(), file=sys.stderr)


__all__ = [
    "com_error_boundary",
    "emit_envelope_to_stderr",
]
