"""W59 offline tests — ``cosmetic_thread`` + ``cut_thread`` handler stubs.

Both handlers are SEAT-PENDING behind spike W59_thread — they must fail
closed for every input until W0 runs the spike and adjudicates GREEN.

The module is **DORMANT** while ``SPIKE_STATUS == "UNRUN"``: handler
functions exist and are testable, but they are NOT registered in
``HANDLER_REGISTRY`` (W0 controls wiring in ``__init__.py``).

What is tested
--------------
* Stub fail-closed: both handlers return ``(False, <reason>)`` for any
  valid-looking input — never ``(True, None)`` or an exception.
* Stub reason mentions "SEAT-PENDING" and the spike id.
* Dormant gate: SPIKE_STATUS="UNRUN" → kinds absent from registry.
* Kind-name disjointness from built-in types (always valid).

COM seams are NOT patched — the stubs never touch COM.
"""

from __future__ import annotations

from ai_sw_bridge.features import HANDLER_REGISTRY
from ai_sw_bridge.features.thread import (
    SPIKE_STATUS,
    create_cosmetic_thread,
    create_cut_thread,
)


# ---------------------------------------------------------------------------
# Cosmetic thread — SEAT-PENDING stub
# ---------------------------------------------------------------------------


class TestCosmeticThreadStub:
    def test_returns_false_with_seat_pending(self) -> None:
        ok, err = create_cosmetic_thread(
            object(),
            {"type": "cosmetic_thread", "thread_standard": "Metric"},
            {"face_ref": {"persist_id": "abc"}},
        )
        assert ok is False
        assert err is not None
        assert "SEAT-PENDING" in err
        assert "W59_thread" in err

    def test_returns_false_with_empty_feature(self) -> None:
        ok, err = create_cosmetic_thread(object(), {}, {})
        assert ok is False
        assert "SEAT-PENDING" in err

    def test_returns_false_with_full_params(self) -> None:
        ok, err = create_cosmetic_thread(
            object(),
            {
                "type": "cosmetic_thread",
                "thread_standard": "UNC",
                "thread_size": "1/4-20",
                "thread_pitch_mm": 1.27,
                "thread_depth_mm": 10.0,
            },
            {"face_ref": {"persist_id": "xyz", "fingerprint": "123"}},
        )
        assert ok is False
        assert "SEAT-PENDING" in err

    def test_never_raises(self) -> None:
        for _ in range(5):
            ok, err = create_cosmetic_thread(None, None, None)  # type: ignore[arg-type]
            assert ok is False


# ---------------------------------------------------------------------------
# Cut thread — SEAT-PENDING stub
# ---------------------------------------------------------------------------


class TestCutThreadStub:
    def test_returns_false_with_seat_pending(self) -> None:
        ok, err = create_cut_thread(
            object(),
            {"type": "cut_thread", "thread_standard": "Metric"},
            {"face_ref": {"persist_id": "abc"}},
        )
        assert ok is False
        assert err is not None
        assert "SEAT-PENDING" in err
        assert "W59_thread" in err

    def test_returns_false_with_empty_feature(self) -> None:
        ok, err = create_cut_thread(object(), {}, {})
        assert ok is False
        assert "SEAT-PENDING" in err

    def test_returns_false_with_full_params(self) -> None:
        ok, err = create_cut_thread(
            object(),
            {
                "type": "cut_thread",
                "thread_standard": "Metric",
                "thread_size": "M10",
                "thread_pitch_mm": 1.5,
                "thread_depth_mm": 15.0,
                "direction": "right_hand",
            },
            {"face_ref": {"persist_id": "xyz"}},
        )
        assert ok is False
        assert "SEAT-PENDING" in err

    def test_never_raises(self) -> None:
        for _ in range(5):
            ok, err = create_cut_thread(None, None, None)  # type: ignore[arg-type]
            assert ok is False


# ---------------------------------------------------------------------------
# Dormant gate + kind disjointness
# ---------------------------------------------------------------------------


class TestDormantGate:
    """While SPIKE_STATUS is UNRUN, handlers are NOT in the registry."""

    def test_spike_status_is_unrun(self) -> None:
        assert SPIKE_STATUS == "UNRUN"

    def test_cosmetic_thread_not_in_registry_when_dormant(self) -> None:
        assert "cosmetic_thread" not in HANDLER_REGISTRY

    def test_cut_thread_not_in_registry_when_dormant(self) -> None:
        assert "cut_thread" not in HANDLER_REGISTRY


class TestKindNames:
    """Kind names must be disjoint from built-in types (always valid)."""

    def test_keys_disjoint_from_builtin_types(self) -> None:
        builtin_kinds = {
            "fillet_constant_radius",
            "base_flange",
            "variable_radius_fillet",
            "wizard_hole",
            "shell",
            "draft",
            "sweep",
            "ref_plane",
            "ref_axis",
            "coordinate_system",
            "ref_point",
            "dome",
            "sweep_cut",
        }
        assert "cosmetic_thread" not in builtin_kinds
        assert "cut_thread" not in builtin_kinds
