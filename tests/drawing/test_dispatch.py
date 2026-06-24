"""Tests for the drawing dispatch (SW-free, mock doc)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ai_sw_bridge.drawing.dispatch import (
    DrawingRequest,
    DrawingResult,
    _place_one_view,
    generate_all,
    resolve_output_path,
)


class _MockDrawingDoc:
    """Minimal IDrawingDoc mock for drawing dispatch tests.

    Simulates ``CreateDrawViewFromModelView3`` by returning a fake view
    object when the view name is recognized.
    """

    KNOWN_VIEWS = {"*Front", "*Top", "*Right", "*Isometric", "*Dimetric", "*Trimetric"}

    def __init__(self, fail_on: str | None = None) -> None:
        self._fail_on = fail_on
        self.view_calls: list[tuple[str, str, float, float, float]] = []

    def CreateDrawViewFromModelView3(
        self,
        part_path: str,
        view_name: str,
        x: float,
        y: float,
        z: float,
    ) -> Any:
        self.view_calls.append((part_path, view_name, x, y, z))
        if self._fail_on and view_name == self._fail_on:
            return None
        if view_name in self.KNOWN_VIEWS:
            return object()  # non-None view object
        return None


class TestDrawingRequest:
    def test_frozen(self) -> None:
        req = DrawingRequest(view="front")
        with pytest.raises(AttributeError):
            req.view = "hacked"  # type: ignore[misc]

    def test_defaults_none(self) -> None:
        req = DrawingRequest(view="front")
        assert req.x is None
        assert req.y is None


class TestDrawingResult:
    def test_to_dict_success(self) -> None:
        r = DrawingResult(view="front", ok=True, position=(0.1, 0.15))
        d = r.to_dict()
        assert d == {
            "view": "front",
            "ok": True,
            "position": {"x": 0.1, "y": 0.15},
        }
        assert "error" not in d

    def test_to_dict_failure(self) -> None:
        r = DrawingResult(view="section", ok=False, error="SEAT-gated")
        d = r.to_dict()
        assert d["error"] == "SEAT-gated"
        assert d["ok"] is False
        assert "position" not in d


class TestResolveOutputPath:
    def test_uses_part_name(self, tmp_path: Path) -> None:
        p = resolve_output_path(tmp_path, "MotorPlate")
        assert p.name == "MotorPlate.slddrw"
        assert p.parent == tmp_path.resolve()

    def test_creates_missing_dir(self, tmp_path: Path) -> None:
        sub = tmp_path / "nested" / "drawings"
        p = resolve_output_path(sub, "Part")
        assert sub.exists()
        assert p.name == "Part.slddrw"


class TestPlaceOneView:
    def test_standard_view_success(self) -> None:
        doc = _MockDrawingDoc()
        req = DrawingRequest(view="front")
        result = _place_one_view(doc, req, "/path/to/part.sldprt")
        assert result.ok is True
        assert result.view == "front"
        assert result.position == (0.1, 0.15)
        assert len(doc.view_calls) == 1

    def test_standard_view_custom_position(self) -> None:
        doc = _MockDrawingDoc()
        req = DrawingRequest(view="top", x=0.5, y=0.6)
        result = _place_one_view(doc, req, "/path/to/part.sldprt")
        assert result.ok is True
        assert result.position == (0.5, 0.6)

    def test_standard_view_failure(self) -> None:
        doc = _MockDrawingDoc(fail_on="*Front")
        req = DrawingRequest(view="front")
        result = _place_one_view(doc, req, "/path/to/part.sldprt")
        assert result.ok is False
        assert "returned None" in result.error

    def test_unknown_view(self) -> None:
        doc = _MockDrawingDoc()
        req = DrawingRequest(view="nonexistent")
        result = _place_one_view(doc, req, "/path/to/part.sldprt")
        assert result.ok is False
        assert "Unknown drawing view" in result.error

    def test_exception_in_create_view(self) -> None:
        class _RaisingDoc:
            def CreateDrawViewFromModelView3(
                self, path: str, name: str, x: float, y: float, z: float
            ) -> Any:
                raise RuntimeError("COM timeout")

        doc = _RaisingDoc()
        req = DrawingRequest(view="front")
        result = _place_one_view(doc, req, "/path/to/part.sldprt")
        assert result.ok is False
        assert "COM timeout" in result.error

    @pytest.mark.parametrize(
        "view_name",
        ["front", "top", "right", "isometric", "dimetric", "trimetric"],
    )
    def test_all_standard_views_succeed(self, view_name: str) -> None:
        doc = _MockDrawingDoc()
        req = DrawingRequest(view=view_name)
        result = _place_one_view(doc, req, "/path/to/part.sldprt")
        assert result.ok is True, f"{view_name}: {result.error}"


class TestGenerateAll:
    def test_multiple_views(self) -> None:
        doc = _MockDrawingDoc()
        requests = [
            DrawingRequest(view="front"),
            DrawingRequest(view="top"),
        ]
        results = generate_all(doc, requests, "/path/to/part.sldprt")
        assert len(results) == 2
        assert all(r.ok for r in results)

    def test_partial_failure(self) -> None:
        doc = _MockDrawingDoc(fail_on="*Top")
        requests = [
            DrawingRequest(view="front"),
            DrawingRequest(view="top"),
            DrawingRequest(view="right"),
        ]
        results = generate_all(doc, requests, "/path/to/part.sldprt")
        assert len(results) == 3
        assert results[0].ok is True
        assert results[1].ok is False
        assert results[2].ok is True

    def test_empty_requests(self) -> None:
        doc = _MockDrawingDoc()
        results = generate_all(doc, [], "/path/to/part.sldprt")
        assert results == []

    def test_human_stream_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        doc = _MockDrawingDoc(fail_on="*Top")
        requests = [
            DrawingRequest(view="front"),
            DrawingRequest(view="top"),
        ]
        generate_all(doc, requests, "/path/to/part.sldprt")
        captured = capsys.readouterr()
        assert "placed front" in captured.err
        assert "FAILED top" in captured.err

    def test_order_preserved(self) -> None:
        doc = _MockDrawingDoc()
        views = ["right", "front", "isometric", "top"]
        requests = [DrawingRequest(view=v) for v in views]
        results = generate_all(doc, requests, "/path/to/part.sldprt")
        assert [r.view for r in results] == views
