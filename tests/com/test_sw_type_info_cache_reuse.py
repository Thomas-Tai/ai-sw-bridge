"""The flag cache must not mistake a recycled address for an already-flagged object.

``flag_methods`` records which interfaces it has flagged, keyed by ``id(obj)``.
An id is unique only among *live* objects, and CPython hands a freed block
straight back to the next allocation of the same size. A fresh COM dispatch can
therefore land on a dead one's address, be judged "already flagged", and never
be flagged at all — after which its methods resolve as properties and
SolidWorks answers "Member not found".

Ported alongside the fix from SolidworksMCP-python (MIT), upstream commit
``7695ae8956ee4a9cfe430eb837f5308ce7f36610``.
"""

from __future__ import annotations

import weakref

import pytest

from ai_sw_bridge.com import sw_type_info

_INTERFACE = "IModelDoc2"
_MEMBERS = frozenset({"SketchMirror", "ClearSelection2", "GetActiveSketch2"})


class _FakeDispatch:
    """Stand-in for a pywin32 ``CDispatch``.

    ``__slots__`` keeps every instance the same size, which is what makes
    CPython reuse a freed instance's address for the next one. ``__weakref__``
    is declared because real ``CDispatch`` objects are weak-referenceable and
    the cache relies on that to detect staleness.
    """

    __slots__ = ("flagged", "__weakref__")

    def __init__(self) -> None:
        self.flagged: list[str] = []

    def _FlagAsMethod(self, name: str) -> None:  # noqa: N802 — pywin32 spelling
        """Record what pywin32 was asked to treat as a method."""
        self.flagged.append(name)


@pytest.fixture
def loaded_type_info(monkeypatch: pytest.MonkeyPatch) -> object:
    """Pretend the SolidWorks type library is loaded with one interface."""
    monkeypatch.setattr(sw_type_info, "_wrapper_module", object())
    monkeypatch.setattr(sw_type_info, "_interface_methods", {_INTERFACE: _MEMBERS})
    monkeypatch.setattr(sw_type_info, "_flag_cache", {})
    return sw_type_info


def _flag_then_reuse_address() -> tuple[bool, int, list[str]]:
    """Flag one object, free it, then flag a new one at the same address.

    Done in a plain helper on purpose: pytest rewrites assertions and can keep
    references to a test function's locals, which would prevent the first
    object from being freed and make address reuse impossible. Nothing here
    outlives the call.

    Returns:
        ``(reused, flagged_count, names_flagged)`` for the second object.
    """
    first = _FakeDispatch()
    sw_type_info.flag_methods(first, _INTERFACE)
    target_id = id(first)
    del first

    for _ in range(50000):
        candidate = _FakeDispatch()
        if id(candidate) == target_id:
            count = sw_type_info.flag_methods(candidate, _INTERFACE)
            return True, count, list(candidate.flagged)
        del candidate
    return False, 0, []


def test_recycled_address_does_not_suppress_flagging(loaded_type_info: object) -> None:
    """A new object at a dead object's address must still be flagged.

    Against the id-only cache this returned 0 with an empty ``names``: the new
    object was silently left unflagged and its members then resolved as
    properties.
    """
    reused, flagged, names = _flag_then_reuse_address()
    if not reused:
        pytest.skip("could not force address reuse in this interpreter run")

    assert flagged == len(_MEMBERS)
    assert set(names) == set(_MEMBERS)


def test_repeat_calls_on_the_same_object_are_still_cached(
    loaded_type_info: object,
) -> None:
    """The cache must keep working; this is a correctness fix, not a removal."""
    obj = _FakeDispatch()

    assert sw_type_info.flag_methods(obj, _INTERFACE) == len(_MEMBERS)
    # Second call is a no-op because this same object was already flagged.
    assert sw_type_info.flag_methods(obj, _INTERFACE) == 0
    assert len(obj.flagged) == len(_MEMBERS)


def test_object_without_weakref_support_is_flagged_every_time(
    loaded_type_info: object,
) -> None:
    """Un-weak-referenceable objects are not cached, so they cannot go stale."""

    class _NoWeakref:
        __slots__ = ("flagged",)

        def __init__(self) -> None:
            self.flagged: list[str] = []

        def _FlagAsMethod(self, name: str) -> None:  # noqa: N802
            self.flagged.append(name)

    obj = _NoWeakref()
    assert sw_type_info.flag_methods(obj, _INTERFACE) == len(_MEMBERS)
    # Not cached, so flagged again rather than risking a stale entry.
    assert sw_type_info.flag_methods(obj, _INTERFACE) == len(_MEMBERS)


def test_cache_entry_does_not_keep_the_dispatch_alive(
    loaded_type_info: object,
) -> None:
    """Caching must not retain COM objects; entries die with their object."""
    obj = _FakeDispatch()
    sw_type_info.flag_methods(obj, _INTERFACE)
    ref = weakref.ref(obj)

    del obj
    assert ref() is None, "flag cache retained the dispatch"


def test_incremental_flagging_across_interfaces_still_works(
    loaded_type_info: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two interfaces on one object flag incrementally, not as a no-op."""
    second = frozenset({"AddComponent5"})
    monkeypatch.setattr(
        sw_type_info,
        "_interface_methods",
        {_INTERFACE: _MEMBERS, "IAssemblyDoc": second},
    )
    obj = _FakeDispatch()

    assert sw_type_info.flag_methods(obj, _INTERFACE) == len(_MEMBERS)
    assert sw_type_info.flag_methods(obj, "IAssemblyDoc") == len(second)
    assert set(obj.flagged) == set(_MEMBERS) | set(second)
