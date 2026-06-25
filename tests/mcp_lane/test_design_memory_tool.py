"""sw_retrieve_design_memory MCP tool — not-found + with-index retrieval."""

from __future__ import annotations

from ai_sw_bridge.mcp import _tool_design_memory as T
from ai_sw_bridge.rag.design_memory import DesignMemoryIndex
from ai_sw_bridge.rag.design_verbalizer import DesignRecipe
from ai_sw_bridge.rag.embed import HashEmbedder


class _FakeMCP:
    """Captures @mcp.tool()-decorated functions by name."""

    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


def _register() -> dict:
    m = _FakeMCP()
    T.register(m)
    return m.tools


def test_index_absent_returns_actionable_not_found(monkeypatch, tmp_path):
    monkeypatch.setattr(T, "_DEFAULT_INDEX", tmp_path / "absent.sqlite")
    tool = _register()["sw_retrieve_design_memory"]
    out = tool(query="bracket linear pattern")
    assert out["ok"] is False
    assert out["count"] == 0 and out["hits"] == []
    assert "not found" in out["error"]
    assert "ai-sw-memory build" in out["hint"]


def test_with_index_returns_hits(monkeypatch, tmp_path):
    emb = HashEmbedder()
    p = tmp_path / "dm.sqlite"
    idx = DesignMemoryIndex.create(p, emb.dim)
    idx.add(
        [
            DesignRecipe(
                "proposals",
                "r1",
                "feature_add",
                "bracket",
                ("linear_pattern", "fillet_constant_radius"),
                "committed",
                "Part build bracket linear pattern fillet shell",
            ),
            DesignRecipe(
                "proposals",
                "d1",
                "drawing",
                "gearbox",
                ("drawing", "table:revision"),
                "committed",
                "Drawing of gearbox with revision table",
            ),
        ],
        emb,
    )
    idx.close()
    monkeypatch.setattr(T, "_DEFAULT_INDEX", p)
    tool = _register()["sw_retrieve_design_memory"]

    out = tool(query="bracket linear pattern", k=2, backend="hash")
    assert out["ok"] is True and out["count"] >= 1
    top = out["hits"][0]["recipe"]
    assert top["kind"] == "feature_add"
    assert top["retrieval_key"] == "proposals:feature_add:r1"
    assert "linear pattern" in top["recipe_text"]
    assert isinstance(out["hits"][0]["score"], float)

    # metadata filter: kind=drawing returns only the drawing recipe
    only_draw = tool(query="gearbox", k=5, kind="drawing", backend="hash")
    assert only_draw["ok"] is True
    assert all(h["recipe"]["kind"] == "drawing" for h in only_draw["hits"])
