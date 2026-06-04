"""Tests for component-context face resolution (Wave-9 Slice 3).

Uses fake bodies/faces (no SOLIDWORKS). Tests the persist-id path and the
fingerprint fallback path.
"""

from __future__ import annotations

import base64
from typing import Any
from unittest.mock import MagicMock

import pytest

from ai_sw_bridge.assembly.face_resolver import (
    ComponentFaceResolution,
    resolve_component_face,
)


class FakeFace:
    """A fake face entity with a configurable normal."""

    def __init__(self, normal: list[float], name: str = "face") -> None:
        self.normal = normal
        self.Normal = normal  # COM-style capitalized property
        self.name = name
        self._oleobj_ = MagicMock()


class FakeBody:
    """A fake body returning configured faces."""

    def __init__(self, faces: list[FakeFace]) -> None:
        self._faces = faces

    def GetFaces(self) -> tuple[FakeFace, ...]:
        return tuple(self._faces)


class FakeComponent:
    """A fake IComponent2 returning a body with faces."""

    def __init__(self, faces: list[FakeFace]) -> None:
        self._body = FakeBody(faces)

    def GetBodies(self, body_type: int) -> tuple[FakeBody, ...]:
        return (self._body,)


class FakeExtension:
    """A fake IModelDocExtension that resolves persist_ids to entities."""

    def __init__(self, mapping: dict[bytes, Any]) -> None:
        self._map = mapping

    def GetObjectByPersistReference3(self, persist_id: bytes) -> tuple:
        entity = self._map.get(persist_id)
        if entity is not None:
            return (entity, 0)
        return (None, 3)  # PERSIST_INVALID


class FakeDoc:
    """A fake assembly doc with a controllable Extension."""

    def __init__(self, ext: FakeExtension) -> None:
        self._ext = ext

    @property
    def Extension(self) -> FakeExtension:
        return self._ext


# ---- Tests -----------------------------------------------------------------


class TestResolveComponentFace:
    def test_empty_face_ref(self) -> None:
        result = resolve_component_face(MagicMock(), MagicMock(), {})
        assert not result.ok
        assert result.method == "unresolved"
        assert "empty" in result.error

    def test_persist_path_succeeds(self, monkeypatch) -> None:
        face_entity = FakeFace([0, 0, 1])
        pid = b"\x01\x02\x03"
        pid_b64 = base64.urlsafe_b64encode(pid).decode("ascii").rstrip("=")

        ext = FakeExtension({pid: face_entity})
        doc = FakeDoc(ext)

        monkeypatch.setattr(
            "ai_sw_bridge.assembly.face_resolver.typed_extension",
            lambda doc, module=None: ext,
        )

        result = resolve_component_face(
            doc, MagicMock(), {"persist_id": pid_b64, "normal": [0, 0, 1]}
        )
        assert result.ok
        assert result.method == "persist_id"
        assert result.entity is face_entity

    def test_persist_fails_degrades_to_fingerprint(self, monkeypatch) -> None:
        target_normal = [0, 0, 1]
        face1 = FakeFace([1, 0, 0], "wrong")
        face2 = FakeFace([0, 0, 1], "match")

        ext = FakeExtension({})
        doc = FakeDoc(ext)
        comp = FakeComponent([face1, face2])

        monkeypatch.setattr(
            "ai_sw_bridge.assembly.face_resolver.typed_extension",
            lambda doc, module=None: ext,
        )
        # Fingerprint path uses typed() which we need to bypass for fakes
        monkeypatch.setattr(
            "ai_sw_bridge.assembly.face_resolver.typed",
            lambda obj, iface, module=None: obj,
        )

        pid_b64 = base64.urlsafe_b64encode(b"\xff").decode("ascii").rstrip("=")
        result = resolve_component_face(
            doc, comp,
            {"persist_id": pid_b64, "normal": target_normal},
        )
        assert result.ok
        assert result.method == "fingerprint"
        assert result.entity is face2

    def test_no_persist_no_normal_unresolved(self, monkeypatch) -> None:
        ext = FakeExtension({})
        doc = FakeDoc(ext)
        comp = FakeComponent([FakeFace([0, 0, 1])])

        monkeypatch.setattr(
            "ai_sw_bridge.assembly.face_resolver.typed_extension",
            lambda doc, module=None: ext,
        )

        result = resolve_component_face(doc, comp, {"role_hint": "top"})
        assert not result.ok
        assert result.method == "unresolved"

    def test_fingerprint_no_match(self, monkeypatch) -> None:
        target_normal = [0, 0, 1]
        face1 = FakeFace([1, 0, 0])
        face2 = FakeFace([0, 1, 0])

        ext = FakeExtension({})
        doc = FakeDoc(ext)
        comp = FakeComponent([face1, face2])

        monkeypatch.setattr(
            "ai_sw_bridge.assembly.face_resolver.typed_extension",
            lambda doc, module=None: ext,
        )
        monkeypatch.setattr(
            "ai_sw_bridge.assembly.face_resolver.typed",
            lambda obj, iface, module=None: obj,
        )

        result = resolve_component_face(
            doc, comp, {"normal": target_normal}
        )
        assert not result.ok
        assert result.method == "unresolved"
        assert "no face matched" in result.error

    def test_component_no_bodies(self, monkeypatch) -> None:
        class EmptyComp:
            def GetBodies(self, t: int) -> tuple:
                return ()

        ext = FakeExtension({})
        doc = FakeDoc(ext)

        monkeypatch.setattr(
            "ai_sw_bridge.assembly.face_resolver.typed_extension",
            lambda doc, module=None: ext,
        )

        result = resolve_component_face(
            doc, EmptyComp(), {"normal": [0, 0, 1]}
        )
        assert not result.ok
        assert "no bodies" in result.error


class TestComponentFaceResolution:
    def test_ok_property(self) -> None:
        assert ComponentFaceResolution(MagicMock(), "persist_id").ok is True
        assert ComponentFaceResolution(None, "unresolved", "err").ok is False

    def test_frozen(self) -> None:
        r = ComponentFaceResolution(None, "unresolved")
        with pytest.raises(AttributeError):
            r.method = "changed"  # type: ignore[misc]
