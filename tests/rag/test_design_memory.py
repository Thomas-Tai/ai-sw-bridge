"""DesignMemoryIndex gauntlet — ingest→search round-trip, metadata filter, backfill.

Deterministic HashEmbedder so retrieval is reproducible without a model download.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from ai_sw_bridge.rag.design_memory import (
    DesignMemoryIndex,
    backfill_all,
    ingest_checkpoints,
    ingest_proposals_dir,
)
from ai_sw_bridge.rag.design_verbalizer import DesignRecipe
from ai_sw_bridge.rag.embed import HashEmbedder


@pytest.fixture
def embedder():
    return HashEmbedder()


@pytest.fixture
def index(tmp_path, embedder):
    idx = DesignMemoryIndex.create(tmp_path / "design_memory.sqlite", embedder.dim)
    yield idx
    idx.close()


def _recipe(ref, kind, text, recipe_kinds, state="committed"):
    return DesignRecipe(
        source="proposals",
        ref=ref,
        kind=kind,
        doc="d",
        recipe_kinds=tuple(recipe_kinds),
        state=state,
        recipe_text=text,
    )


def test_create_add_stats(index, embedder):
    n = index.add(
        [
            _recipe(
                "a", "drawing", "Drawing: gearbox front isometric views", ["drawing"]
            ),
            _recipe("b", "feature_add", "Part build shell fillet chamfer", ["shell"]),
        ],
        embedder,
    )
    assert n == 2
    s = index.stats()
    assert s["recipes"] == 2
    assert s["by_kind"] == {"drawing": 1, "feature_add": 1}


def test_ingest_search_round_trip_returns_seeded_recipe(index, embedder):
    index.add(
        [
            _recipe(
                "draw1",
                "drawing",
                "Drawing of gearbox with revision weldment tables",
                ["drawing"],
            ),
            _recipe(
                "part1",
                "feature_add",
                "Part build bracket linear pattern fillet shell",
                ["linear_pattern"],
            ),
        ],
        embedder,
    )
    # query words overlap the bracket recipe -> it should rank first.
    hits = index.search("bracket linear pattern fillet", embedder=embedder, k=2)
    assert hits, "expected at least one hit"
    assert hits[0][0].ref == "part1"
    assert hits[0][1] > 0.0  # similarity score present


def test_metadata_filter_by_kind(index, embedder):
    index.add(
        [
            _recipe("d1", "drawing", "alpha beta gamma views tables", ["drawing"]),
            _recipe("f1", "feature_add", "alpha beta gamma shell fillet", ["shell"]),
        ],
        embedder,
    )
    only_draw = index.search("alpha beta gamma", embedder=embedder, k=5, kind="drawing")
    assert only_draw and all(r.kind == "drawing" for r, _ in only_draw)
    assert {r.ref for r, _ in only_draw} == {"d1"}


def test_metadata_filter_by_recipe_kind_like(index, embedder):
    index.add(
        [
            _recipe("p1", "feature_add", "build one shell", ["shell", "fillet_face"]),
            _recipe("p2", "feature_add", "build two sweep", ["sweep", "loft"]),
        ],
        embedder,
    )
    sweeps = index.search("build", embedder=embedder, k=5, recipe_kind="sweep")
    assert {r.ref for r, _ in sweeps} == {"p2"}


def test_idempotent_add_skips_duplicate_keys(index, embedder):
    r = _recipe("dup", "drawing", "same recipe text", ["drawing"])
    assert index.add([r], embedder) == 1
    assert index.add([r], embedder) == 0  # same retrieval_key -> skipped
    assert index.stats()["recipes"] == 1


def test_empty_index_search_returns_empty(index, embedder):
    assert index.search("anything", embedder=embedder, k=5) == []


# --- backfill adapters against synthetic fixtures mirroring real shapes ------


def test_ingest_proposals_dir(tmp_path, index, embedder):
    pdir = tmp_path / "proposals"
    pdir.mkdir()
    (pdir / "a.json").write_text(
        json.dumps(
            {
                "kind": "drawing",
                "state": "committed",
                "spec": {
                    "name": "d",
                    "model": "m.sldprt",
                    "views": ["front", "top"],
                    "revision_table": True,
                },
            }
        ),
        encoding="utf-8",
    )
    (pdir / "b.json").write_text(
        json.dumps(
            {
                "kind": "assembly",
                "state": "proposed",
                "spec": {
                    "name": "asm",
                    "components": [{"id": "a", "part": "p.SLDPRT"}],
                    "mates": [{"type": "coincident"}],
                },
            }
        ),
        encoding="utf-8",
    )
    (pdir / "c.json").write_text(
        json.dumps(
            {"kind": "feature_add", "state": "proposed", "spec": {}}
        ),  # empty -> skip
        encoding="utf-8",
    )
    report = ingest_proposals_dir(index, embedder, pdir)
    assert report["files"] == 3
    assert report["indexed"] == 2  # drawing + assembly
    assert report["skipped"] == 1  # the empty feature_add
    assert index.stats()["by_kind"] == {"drawing": 1, "assembly": 1}


def test_ingest_checkpoints(tmp_path, index, embedder):
    db = tmp_path / "MinimalCylinder.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE checkpoints (part_name TEXT, feature_index INTEGER, "
        "feature_name TEXT, feature_type TEXT, status TEXT)"
    )
    conn.executemany(
        "INSERT INTO checkpoints VALUES (?,?,?,?,?)",
        [
            ("MinimalCylinder", 0, "SK_Body", "sketch_circle_on_plane", "committed"),
            ("MinimalCylinder", 1, "Extrude_Body", "boss_extrude_blind", "committed"),
            ("MinimalCylinder", 2, "Pending_X", "fillet", "pending"),  # excluded
        ],
    )
    conn.commit()
    conn.close()

    report = ingest_checkpoints(index, embedder, tmp_path)
    assert report["parts_indexed"] == 1
    rec = index.get("checkpoints:part_build:MinimalCylinder")
    assert rec is not None
    assert "sketch circle on plane" in rec.recipe_text
    assert (
        "boss_extrude_blind" not in rec.recipe_text.split("|")[0]
    )  # humanized in body


def test_backfill_all_reports_and_excludes_spikes(tmp_path, index, embedder):
    (tmp_path / "proposals").mkdir()
    (tmp_path / "proposals" / "a.json").write_text(
        json.dumps(
            {
                "kind": "drawing",
                "state": "committed",
                "spec": {"name": "d", "model": "m.sldprt", "views": ["front"]},
            }
        ),
        encoding="utf-8",
    )
    report = backfill_all(index, embedder, root=tmp_path)
    assert report["proposals"]["indexed"] == 1
    assert report["total_indexed"] == 1
    assert "spikes_excluded" in report  # honest, not silent
    assert "telemetry" in report["spikes_excluded"]["reason"]
