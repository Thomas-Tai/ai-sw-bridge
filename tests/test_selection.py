"""Unit tests for the ``selection`` package (P0.1, spec.md §5.1).

Two surfaces under test:

* :class:`ai_sw_bridge.selection.BrepFingerprint` — hash stability,
  round-trip (de)serialization, and the invariant that a hash must
  match its source geometry.
* :class:`ai_sw_bridge.selection.DurableRef` — base64url round-trip
  of ``persist_id`` bytes, first-class ``persist_id=None`` path (the
  S-PERSIST RED / unrun state), and role_hint / fingerprint plumbing.

All tests are SW-free: the selection types are pure-Python value
objects. No mock-adapter hookup is needed here; the resolver that
*uses* these types against a brep manifest is P0.2.
"""

from __future__ import annotations

import base64

import pytest

from ai_sw_bridge.brep.fingerprint import fingerprint as compute_hash
from ai_sw_bridge.selection import BrepFingerprint, DurableRef


# ---------------------------------------------------------------------------
# Fixtures: a canonical face dict in the shape ``brep.interrogator``
# produces. Numbers chosen to exercise quantization edge cases (zeros,
# small centroid, modest area).
# ---------------------------------------------------------------------------


def _face_dict(
    *,
    normal=(0.0, 0.0, 1.0),
    centroid=(0.01, 0.02, 0.005),
    area_mm2=2500.0,
) -> dict:
    return {
        "normal": list(normal),
        "centroid": list(centroid),
        "area_mm2": area_mm2,
    }


# ===========================================================================
# BrepFingerprint
# ===========================================================================


class TestBrepFingerprint:
    def test_hash_matches_canonical_function(self):
        face = _face_dict()
        fp = BrepFingerprint.from_face_dict(face)

        assert fp.hash_hex == compute_hash(face)
        assert len(fp.hash_hex) == 16
        # Hash is lowercase hex.
        assert all(c in "0123456789abcdef" for c in fp.hash_hex)

    def test_hash_stability_across_calls(self):
        face = _face_dict()
        a = BrepFingerprint.from_face_dict(face)
        b = BrepFingerprint.from_face_dict(face)
        assert a.hash_hex == b.hash_hex
        assert a == b  # dataclass frozen equality

    def test_hash_changes_when_geometry_changes(self):
        a = BrepFingerprint.from_face_dict(_face_dict(area_mm2=2500.0))
        b = BrepFingerprint.from_face_dict(_face_dict(area_mm2=2501.0))
        assert a.hash_hex != b.hash_hex

    def test_to_dict_round_trip(self):
        face = _face_dict()
        fp = BrepFingerprint.from_face_dict(face)
        wire = fp.to_dict()

        assert wire == {
            "hash": fp.hash_hex,
            "normal": [0.0, 0.0, 1.0],
            "centroid": [0.01, 0.02, 0.005],
            "area_mm2": 2500.0,
        }

        back = BrepFingerprint.from_dict(wire)
        assert back == fp

    def test_from_dict_rejects_hash_geometry_mismatch(self):
        face = _face_dict()
        fp = BrepFingerprint.from_face_dict(face)
        wire = fp.to_dict()
        wire["area_mm2"] = 9999.0  # geometry no longer matches the hash

        with pytest.raises(ValueError, match="does not match geometry"):
            BrepFingerprint.from_dict(wire)

    def test_from_dict_rejects_missing_keys(self):
        with pytest.raises(ValueError):
            BrepFingerprint.from_dict({"hash": "0" * 16})
        with pytest.raises(ValueError):
            BrepFingerprint.from_dict(
                {"hash": "0" * 16, "normal": [0, 0, 1], "centroid": [0, 0, 0]}
                # area_mm2 missing
            )

    def test_from_dict_rejects_wrong_type(self):
        with pytest.raises(TypeError):
            BrepFingerprint.from_dict("not a dict")  # type: ignore[arg-type]

    def test_post_init_rejects_bad_hash_shape(self):
        with pytest.raises(ValueError, match="16-char hex"):
            BrepFingerprint(
                hash_hex="tooshort",
                normal=(0.0, 0.0, 1.0),
                centroid=(0.0, 0.0, 0.0),
                area_mm2=1.0,
            )

    def test_post_init_rejects_short_vectors(self):
        with pytest.raises(ValueError, match="3-tuples"):
            BrepFingerprint(
                hash_hex="0" * 16,
                normal=(0.0, 1.0),  # too short
                centroid=(0.0, 0.0, 0.0),
                area_mm2=1.0,
            )

    def test_to_face_dict_feeds_canonical_hash(self):
        fp = BrepFingerprint.from_face_dict(_face_dict())
        # Re-running the hash on to_face_dict() reproduces hash_hex.
        assert compute_hash(fp.to_face_dict()) == fp.hash_hex

    def test_from_dict_accepts_list_or_tuple(self):
        fp = BrepFingerprint.from_face_dict(_face_dict())
        wire = fp.to_dict()
        # Caller hands back tuples instead of lists — still accepted.
        wire_tuple = {
            "hash": wire["hash"],
            "normal": tuple(wire["normal"]),
            "centroid": tuple(wire["centroid"]),
            "area_mm2": wire["area_mm2"],
        }
        assert BrepFingerprint.from_dict(wire_tuple) == fp


# ===========================================================================
# DurableRef
# ===========================================================================


class TestDurableRef:
    @pytest.fixture
    def fp(self) -> BrepFingerprint:
        return BrepFingerprint.from_face_dict(_face_dict())

    # ---- persist_id=None path (S-PERSIST RED / unrun) ------------------

    def test_persist_id_none_is_first_class(self, fp):
        ref = DurableRef(persist_id=None, fingerprint=fp, role_hint="+z_outboard")
        wire = ref.to_dict()

        assert "persist_id" not in wire  # omitted, not null
        assert wire["role_hint"] == "+z_outboard"
        assert wire["fingerprint"]["hash"] == fp.hash_hex

        back = DurableRef.from_dict(wire)
        assert back.persist_id is None
        assert back.fingerprint == fp
        assert back.role_hint == "+z_outboard"
        assert back == ref

    def test_persist_id_none_round_trip_via_json(self, fp):
        """Wire format survives a JSON round trip (via dict)."""
        import json

        ref = DurableRef(persist_id=None, fingerprint=fp, role_hint="top")
        wire = ref.to_dict()
        text = json.dumps(wire)
        back = DurableRef.from_dict(json.loads(text))
        assert back == ref

    # ---- persist_id present (S-PERSIST GREEN path) ---------------------

    def test_persist_id_bytes_round_trip(self, fp):
        raw = bytes(range(32))  # 32-byte token with every byte value
        ref = DurableRef(persist_id=raw, fingerprint=fp, role_hint="top")
        wire = ref.to_dict()

        # base64url, no padding, ASCII-safe.
        encoded = wire["persist_id"]
        assert isinstance(encoded, str)
        assert encoded.isascii()
        assert "=" not in encoded
        assert "+" not in encoded and "/" not in encoded  # url-safe alphabet

        # Decode matches the original bytes.
        pad = "=" * (-len(encoded) % 4)
        assert base64.urlsafe_b64decode(encoded + pad) == raw

        # Round-trip through from_dict preserves bytes.
        back = DurableRef.from_dict(wire)
        assert back.persist_id == raw
        assert back == ref

    def test_persist_id_accepts_padded_b64(self, fp):
        """Older writers may keep the padding; reader must accept both."""
        raw = b"\xff"  # 1 byte → 2 base64 chars + 2 padding '='
        padded = base64.urlsafe_b64encode(raw).decode("ascii")
        assert padded.endswith("=")
        wire = {
            "persist_id": padded,
            "fingerprint": fp.to_dict(),
            "role_hint": "+x",
        }
        back = DurableRef.from_dict(wire)
        assert back.persist_id == raw

    def test_persist_id_empty_bytes_round_trip(self, fp):
        """Empty byte string is a valid (if degenerate) token; survives."""
        ref = DurableRef(persist_id=b"", fingerprint=fp, role_hint="r")
        wire = ref.to_dict()
        assert wire["persist_id"] == ""  # empty base64
        back = DurableRef.from_dict(wire)
        assert back.persist_id == b""

    # ---- Validation ----------------------------------------------------

    def test_rejects_non_bytes_persist_id(self, fp):
        with pytest.raises(TypeError, match="bytes or None"):
            DurableRef(
                persist_id="not-bytes",  # type: ignore[arg-type]
                fingerprint=fp,
                role_hint="top",
            )

    def test_rejects_empty_role_hint(self, fp):
        with pytest.raises(ValueError, match="role_hint"):
            DurableRef(persist_id=None, fingerprint=fp, role_hint="")

    def test_rejects_non_string_role_hint(self, fp):
        with pytest.raises(ValueError, match="role_hint"):
            DurableRef(persist_id=None, fingerprint=fp, role_hint=42)  # type: ignore[arg-type]

    def test_from_dict_rejects_missing_fingerprint(self):
        with pytest.raises(ValueError, match="fingerprint"):
            DurableRef.from_dict({"role_hint": "top"})

    def test_from_dict_rejects_missing_role_hint(self, fp):
        with pytest.raises(ValueError, match="role_hint"):
            DurableRef.from_dict({"fingerprint": fp.to_dict()})

    def test_from_dict_rejects_wrong_type(self):
        with pytest.raises(TypeError):
            DurableRef.from_dict(["not", "a", "dict"])  # type: ignore[arg-type]

    def test_from_dict_rejects_persist_id_wrong_type(self, fp):
        with pytest.raises(TypeError, match="base64url string"):
            DurableRef.from_dict(
                {
                    "persist_id": 12345,  # type: ignore[dict-item]
                    "fingerprint": fp.to_dict(),
                    "role_hint": "top",
                }
            )

    # ---- Frozen / value semantics --------------------------------------

    def test_frozen(self, fp):
        ref = DurableRef(persist_id=None, fingerprint=fp, role_hint="top")
        with pytest.raises(AttributeError):
            ref.role_hint = "other"  # type: ignore[misc]

    def test_equality_and_hash(self, fp):
        a = DurableRef(persist_id=b"\x01", fingerprint=fp, role_hint="top")
        b = DurableRef(persist_id=b"\x01", fingerprint=fp, role_hint="top")
        c = DurableRef(persist_id=b"\x02", fingerprint=fp, role_hint="top")
        assert a == b
        assert a != c
        # frozen dataclass is hashable → usable as a dict key / set member.
        assert hash(a) == hash(b)
        assert {a, b, c} == {a, c}

    # ---- from_manifest_face (brep-manifest adapter) --------------------

    @staticmethod
    def _manifest_face(*, persist_id=None, role_hint="+z_outboard") -> dict:
        """A face dict in the flat brep-manifest serialized shape."""
        face = {
            "normal": [0.0, 0.0, 1.0],
            "centroid": [0.01, 0.02, 0.005],
            "area_mm2": 2500.0,
        }
        out = {
            "fingerprint": compute_hash(face),
            "face_idx": 3,
            "body_id": 0,
            "role_hint": role_hint,
            "normal": face["normal"],
            "centroid": face["centroid"],
            "bbox": [[0.0, 0.0, 0.0], [0.02, 0.04, 0.005]],
            "area_mm2": face["area_mm2"],
            "is_surface": False,
        }
        if persist_id is not None:
            out["persist_id"] = persist_id
        return out

    def test_from_manifest_face_no_persist(self, fp):
        """Flat manifest face without a token -> persist_id None, fp matches."""
        ref = DurableRef.from_manifest_face(self._manifest_face())
        assert ref.persist_id is None
        assert ref.role_hint == "+z_outboard"
        assert ref.fingerprint == fp

    def test_from_manifest_face_with_persist(self, fp):
        raw = bytes(range(16))
        b64 = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        ref = DurableRef.from_manifest_face(self._manifest_face(persist_id=b64))
        assert ref.persist_id == raw
        assert ref.fingerprint == fp

    def test_from_manifest_face_empty_role_defaults(self):
        ref = DurableRef.from_manifest_face(self._manifest_face(role_hint=""))
        assert ref.role_hint == "unknown"

    def test_from_manifest_face_rejects_missing_geometry(self):
        with pytest.raises(ValueError, match="normal, centroid, area_mm2"):
            DurableRef.from_manifest_face({"role_hint": "top"})

    def test_from_manifest_face_rejects_non_dict(self):
        with pytest.raises(TypeError):
            DurableRef.from_manifest_face(["not", "a", "dict"])  # type: ignore[arg-type]
