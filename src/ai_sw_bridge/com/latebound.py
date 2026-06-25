"""Late-bound re-wrap for the typed-transaction ICallout / InsertHelix trap.

The disk-transaction path opens documents TYPED (``mutate._open_doc_typed``,
via ``com.earlybind``). On a makepy-TYPED ``IModelDocExtension`` proxy two
classes of call refuse to marshal:

  * ``SelectByID2``'s arg-8 ICallout ``VARIANT(VT_DISPATCH, None)`` raises
    ``TypeError('The Python instance can not be converted to a COM object')``.
  * ``IModelDoc2.InsertHelix`` is likewise late-bound-only.

Re-wrapping the proxy as LATE-BOUND (``win32com.client.dynamic.Dispatch``)
marshals both regardless of how the doc was opened. This is the exact inverse
of :mod:`ai_sw_bridge.com.earlybind`: that module climbs UP to early binding to
reach ``[out]``-param methods; this one drops back DOWN to late binding to reach
the ICallout/InsertHelix methods that early binding refuses.

Proven through the typed transaction by ``probe_curve_lanes_typed_txn``
(2026-06-24, helix/spiral dry_run reproduced the exact ``TypeError``) and first
fixed for ref_axis (commit ``794a7c4``). Previously duplicated byte-identically
in ``features/helix.py``, ``features/spiral.py`` and ``features/ref_geometry.py``;
consolidated here 2026-06-25.

Call sites import this as the module-private name they already monkeypatch in
offline tests::

    from ..com.latebound import latebound as _latebound

so each feature module keeps its own ``_latebound`` attribute (the seam the
``test_uses_latebound_seam`` tests patch to identity) while sharing one
implementation.
"""

from __future__ import annotations

from typing import Any

import win32com.client.dynamic as _w32dyn


def latebound(com_obj: Any) -> Any:
    """Re-wrap *com_obj* as a LATE-BOUND ``win32com.client.dynamic`` proxy.

    Use before any ``SelectByID2`` ICallout or ``InsertHelix`` invocation on a
    doc that may have been opened TYPED — those calls raise ``TypeError`` on a
    makepy-typed proxy but marshal cleanly late-bound. A no-op-shaped seam:
    offline tests monkeypatch the importing module's ``_latebound`` to identity.
    """
    return _w32dyn.Dispatch(com_obj)
