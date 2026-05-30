"""Tests for brep/manifest.py (spec.md §2.5)."""

from __future__ import annotations

import json

import pytest

from ai_sw_bridge.brep.fingerprint import fingerprint
from ai_sw_bridge.brep.manifest import Manifest


def _interrogation(
    name: str = "Extrude_Plate",
    n_faces: int = 1,
    *,
    include_temp_id: bool = True,
    error: str | None = None,
) -> dict:
    """Build a stub interrogation result matching interrogator.interrogate shape."""
    faces = []
    for i in range(n_faces):
        face = {
            "face_idx": i,
            "body_id": 0,
            "normal": [0.0, 0.0, 1.0],
            "centroid": [0.0, 0.0, 0.0025 + 0.001 * i],
            "bbox": [[-0.01, -0.01, 0.0], [0.01, 0.01, 0.005]],
            "area_mm2": 400.0,
            "role_hint": "+z_outboard",
            "is_surface": False,
        }
        if include_temp_id:
            face["temp_id"] = f"body0_face{i}"
        faces.append(face)
    out = {"feature": name, "faces": faces}
    if error is not None:
        out["error"] = error
    return out


# ---------------------------------------------------------------------------
# Basic append + lookup
# ---------------------------------------------------------------------------


def test_manifest_starts_empty() -> None:
    m = Manifest()
    assert len(m) == 0
    assert list(m) == []


def test_add_feature_assigns_fingerprint() -> None:
    m = Manifest()
    m.add_feature(_interrogation())
    block = m.lookup("Extrude_Plate")
    assert block is not None
    assert len(block["faces"]) == 1
    fp = block["faces"][0]["fingerprint"]
    assert isinstance(fp, str) and len(fp) == 16
    # Fingerprint matches the standalone fingerprint() call on the same face.
    raw_face = _interrogation()["faces"][0]
    assert fp == fingerprint(raw_face)


def test_add_feature_carries_edges_block() -> None:
    """Phase-0 edge capture: an 'edges' list survives into the feature block."""
    m = Manifest()
    res = _interrogation()
    res["edges"] = [
        {
            "edge_idx": 0,
            "body_id": 0,
            "start": [0.0, 0.0, 0.0],
            "end": [0.0, 0.0, 0.01],
            "length": 0.01,
            "midpoint": [0.0, 0.0, 0.005],
            "persist_id": "AQIDBA",
        }
    ]
    m.add_feature(res)
    block = m.lookup("Extrude_Plate")
    assert "edges" in block and len(block["edges"]) == 1
    edge = block["edges"][0]
    assert edge["edge_idx"] == 0
    assert edge["start"] == [0.0, 0.0, 0.0]
    assert edge["persist_id"] == "AQIDBA"


def test_add_feature_no_edges_block_when_absent() -> None:
    """No 'edges' key when interrogation captured none (manifest stays lean)."""
    m = Manifest()
    m.add_feature(_interrogation())
    assert "edges" not in m.lookup("Extrude_Plate")


def test_add_feature_strips_temp_id() -> None:
    """temp_id is session-scoped; must not appear in the serialized form."""
    m = Manifest()
    m.add_feature(_interrogation(include_temp_id=True))
    face = m.lookup("Extrude_Plate")["faces"][0]
    assert "temp_id" not in face


def test_add_feature_preserves_all_other_fields() -> None:
    m = Manifest()
    m.add_feature(_interrogation())
    face = m.lookup("Extrude_Plate")["faces"][0]
    for key in (
        "face_idx",
        "body_id",
        "normal",
        "centroid",
        "bbox",
        "area_mm2",
        "role_hint",
        "is_surface",
        "fingerprint",
    ):
        assert key in face, f"missing key: {key}"


def test_add_feature_rejects_none() -> None:
    m = Manifest()
    with pytest.raises(ValueError):
        m.add_feature(None)  # type: ignore[arg-type]


def test_add_feature_rejects_missing_feature_key() -> None:
    m = Manifest()
    with pytest.raises(ValueError, match="missing 'feature'"):
        m.add_feature({"faces": []})


def test_multiple_features_append() -> None:
    m = Manifest()
    m.add_feature(_interrogation("A"))
    m.add_feature(_interrogation("B"))
    assert len(m) == 2
    assert m.lookup("A") is not None
    assert m.lookup("B") is not None


# ---------------------------------------------------------------------------
# feature_type + error passthrough
# ---------------------------------------------------------------------------


def test_add_feature_records_feature_type() -> None:
    m = Manifest()
    m.add_feature(_interrogation(), feature_type="boss_extrude_blind")
    block = m.lookup("Extrude_Plate")
    assert block["type"] == "boss_extrude_blind"


def test_add_feature_preserves_error_marker() -> None:
    m = Manifest()
    m.add_feature(_interrogation(error="COM failure"))
    block = m.lookup("Extrude_Plate")
    assert block["error"] == "COM failure"


# ---------------------------------------------------------------------------
# Serialization + round-trip
# ---------------------------------------------------------------------------


def test_to_dict_schema() -> None:
    m = Manifest()
    m.add_feature(_interrogation())
    data = m.to_dict()
    assert data["schema_version"] == 1
    assert isinstance(data["features"], list)
    assert len(data["features"]) == 1
    assert data["features"][0]["feature"] == "Extrude_Plate"


def test_to_json_produces_valid_json() -> None:
    m = Manifest()
    m.add_feature(_interrogation(n_faces=3))
    text = m.to_json()
    parsed = json.loads(text)
    assert parsed["schema_version"] == 1
    assert len(parsed["features"][0]["faces"]) == 3


def test_round_trip_dict() -> None:
    m = Manifest()
    m.add_feature(_interrogation("A", n_faces=2))
    m.add_feature(_interrogation("B"))
    data = m.to_dict()
    restored = Manifest.from_dict(data)
    assert len(restored) == 2
    assert restored.lookup("A") == m.lookup("A")
    assert restored.lookup("B") == m.lookup("B")


def test_round_trip_json() -> None:
    m = Manifest()
    m.add_feature(_interrogation("Plate", n_faces=6))
    text = m.to_json()
    restored = Manifest.from_json(text)
    assert restored.to_dict() == m.to_dict()


def test_from_dict_rejects_bad_schema_version() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        Manifest.from_dict({"schema_version": 99, "features": []})


def test_from_dict_rejects_missing_features_list() -> None:
    with pytest.raises(TypeError):
        Manifest.from_dict({"schema_version": 1, "features": {}})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# active_configuration (audit §6.2)
# ---------------------------------------------------------------------------


def test_manifest_active_configuration_defaults_none() -> None:
    m = Manifest()
    assert m.active_configuration is None
    # Field is omitted from to_dict when None to keep the existing
    # shape stable for v0.11 consumers that don't know about configs.
    assert "active_configuration" not in m.to_dict()


def test_manifest_active_configuration_serializes_when_set() -> None:
    m = Manifest(active_configuration="HighSpeedVariant")
    out = m.to_dict()
    assert out["active_configuration"] == "HighSpeedVariant"


def test_manifest_active_configuration_round_trip() -> None:
    m = Manifest(active_configuration="Default")
    restored = Manifest.from_dict(m.to_dict())
    assert restored.active_configuration == "Default"


def test_manifest_from_dict_back_compat_without_active_config() -> None:
    """v0.11-era manifests without active_configuration still parse."""
    restored = Manifest.from_dict({"schema_version": 1, "features": []})
    assert restored.active_configuration is None


# ---------------------------------------------------------------------------
# Fingerprint stability
# ---------------------------------------------------------------------------


def test_fingerprints_deterministic_across_adds() -> None:
    """Two manifests built from the same interrogation result agree on fingerprints."""
    a = Manifest()
    b = Manifest()
    a.add_feature(_interrogation(n_faces=3))
    b.add_feature(_interrogation(n_faces=3))
    a_fps = [f["fingerprint"] for f in a.lookup("Extrude_Plate")["faces"]]
    b_fps = [f["fingerprint"] for f in b.lookup("Extrude_Plate")["faces"]]
    assert a_fps == b_fps
