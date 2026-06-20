"""W67 Phase 4 (Debt #4) — the fail-loud registration gate.

``features._register_lane`` is the SOLE sanctioned path into HANDLER_REGISTRY:
it registers iff the lane is seat-proven (``SPIKE_STATUS == "GREEN"``), lets an
explicitly-dormant sentinel through untouched, and FAILS LOUD on any other
status (a forgotten flip / typo'd "GREEN" must not silently advertise an
unproven handler).
"""

from __future__ import annotations

import pytest

from ai_sw_bridge import features
from ai_sw_bridge.features import _register_lane


# ---------------------------------------------------------------------------
# The registry reflects exactly the seat-proven lanes
# ---------------------------------------------------------------------------
_GREEN_LANES = (
    "hem", "composite", "helix", "project_curve", "bounding_box", "com_point",
    "mate_reference", "sketched_bend", "planar_surface", "offset_surface", "knit",
)
# Imported for provenance but NOT seat-proven — must stay OUT of the registry.
_DORMANT_LANES = ("thicken", "move_body", "copy_body")


@pytest.mark.parametrize("kind", _GREEN_LANES)
def test_green_lanes_registered(kind: str) -> None:
    assert kind in features.HANDLER_REGISTRY


@pytest.mark.parametrize("kind", _DORMANT_LANES)
def test_dormant_lanes_not_registered(kind: str) -> None:
    assert kind not in features.HANDLER_REGISTRY


# ---------------------------------------------------------------------------
# The gate itself
# ---------------------------------------------------------------------------
def _fake_handler(doc, feature, target):  # noqa: ANN001
    return True, None


class TestRegisterLane:
    def test_green_registers(self) -> None:
        key = "_t_green_lane"
        try:
            assert _register_lane(key, _fake_handler, "GREEN") is True
            assert features.HANDLER_REGISTRY[key] is _fake_handler
        finally:
            features.HANDLER_REGISTRY.pop(key, None)

    @pytest.mark.parametrize("status", ["UNFIRED", "UNRUN", "DEFERRED", "WALLED"])
    def test_dormant_sentinel_skips_without_registering(self, status: str) -> None:
        key = "_t_dormant_lane"
        assert _register_lane(key, _fake_handler, status) is False
        assert key not in features.HANDLER_REGISTRY

    @pytest.mark.parametrize("status", ["green", "Green", "PROVEN", "", "GREEN "])
    def test_unrecognized_status_fails_loud(self, status: str) -> None:
        key = "_t_bogus_lane"
        with pytest.raises(RuntimeError, match="seat-proven"):
            _register_lane(key, _fake_handler, status)
        assert key not in features.HANDLER_REGISTRY

    def test_forcing_a_dormant_module_without_green_cannot_register(self) -> None:
        # The dormant lanes are kept importable for provenance; forcing their
        # registration is only possible by lying about the status — and a
        # non-sentinel lie fails loud, while their true (dormant) status skips.
        from ai_sw_bridge.features import thicken, move_copy_body

        assert thicken.SPIKE_STATUS != "GREEN"
        assert move_copy_body.SPIKE_STATUS != "GREEN"
        # True status → dormant skip, never registered.
        assert _register_lane("thicken", thicken.create_thicken, thicken.SPIKE_STATUS) is False
        # A forced non-sentinel status → hard failure (no silent sneak-in).
        with pytest.raises(RuntimeError):
            _register_lane("thicken", thicken.create_thicken, "FORCE")
        assert "thicken" not in features.HANDLER_REGISTRY
