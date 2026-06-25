"""Design-Memory vector index — semantic memory over the operator's OWN designs.

A second, dedicated ``sqlite-vec`` index (parallel to the static API index in
:mod:`ai_sw_bridge.rag.index`, NOT crammed into its ApiChunk schema — a design
recipe is a different entity than an API doc). Each row is a per-transaction
"design recipe": the verbalized (syntax-free) text block from
:mod:`ai_sw_bridge.rag.design_verbalizer`, its embedding, and metadata columns
(``kind``, ``recipe_kinds``, ``state``) for pre-filtered retrieval.

The index is a LOCAL, MUTABLE runtime artifact (gitignored), built incrementally
as the operator models + backfilled from existing history. Fully local embeddings
(``all-MiniLM-L6-v2`` or the deterministic ``HashEmbedder``) — proprietary design
history never leaves the device.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

from .design_verbalizer import (
    DesignRecipe,
    verbalize_part_build,
    verbalize_proposal_record,
)
from .embed import Embedder

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS recipes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    retrieval_key TEXT    UNIQUE NOT NULL,
    source        TEXT    NOT NULL,
    kind          TEXT    NOT NULL,
    doc           TEXT    NOT NULL,
    recipe_kinds  TEXT    NOT NULL,   -- JSON list, for LIKE metadata filter
    state         TEXT    NOT NULL,
    spec_hash     TEXT    NOT NULL,
    recipe_text   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_recipe_kind ON recipes(kind);
"""


def _register_vec(conn: sqlite3.Connection) -> None:
    try:
        import sqlite_vec
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "sqlite-vec is not installed; install with `pip install sqlite-vec`."
        ) from e
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)


def _row_to_recipe(row: sqlite3.Row) -> DesignRecipe:
    return DesignRecipe(
        source=row["source"],
        ref=row["retrieval_key"].split(":", 2)[-1],
        kind=row["kind"],
        doc=row["doc"],
        recipe_kinds=tuple(json.loads(row["recipe_kinds"])),
        state=row["state"],
        recipe_text=row["recipe_text"],
    )


class DesignMemoryIndex:
    """sqlite-vec KNN index over verbalized design recipes."""

    def __init__(self, conn: sqlite3.Connection, path: Path | None) -> None:
        self._conn = conn
        self._path = path

    # -- lifecycle ---------------------------------------------------------

    @classmethod
    def create(cls, path: Path, dim: int) -> "DesignMemoryIndex":
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        _register_vec(conn)
        conn.executescript(_SCHEMA_SQL)
        conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_recipes "
            f"USING vec0(embedding float[{dim}])"
        )
        conn.commit()
        return cls(conn, path)

    @classmethod
    def open(cls, path: Path) -> "DesignMemoryIndex":
        if not path.exists():
            raise FileNotFoundError(f"design-memory index not found: {path}")
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        _register_vec(conn)
        return cls(conn, path)

    @classmethod
    def open_or_create(cls, path: Path, dim: int) -> "DesignMemoryIndex":
        return cls.open(path) if path.exists() else cls.create(path, dim)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None  # type: ignore[assignment]

    def __enter__(self) -> "DesignMemoryIndex":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # -- write -------------------------------------------------------------

    def add(self, recipes: Sequence[DesignRecipe], embedder: Embedder) -> int:
        """Insert recipes + embeddings. Idempotent on retrieval_key."""
        recipes = [r for r in recipes if r is not None]
        if not recipes:
            return 0
        vectors = embedder.embed_many([r.recipe_text for r in recipes])
        added = 0
        for r, vec in zip(recipes, vectors):
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO recipes "
                "(retrieval_key, source, kind, doc, recipe_kinds, state, "
                "spec_hash, recipe_text) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    r.retrieval_key(),
                    r.source,
                    r.kind,
                    r.doc,
                    json.dumps(list(r.recipe_kinds)),
                    r.state,
                    r.spec_hash,
                    r.recipe_text,
                ),
            )
            if cur.rowcount == 0:
                continue  # duplicate retrieval_key
            self._conn.execute(
                "INSERT INTO vec_recipes(rowid, embedding) VALUES (?, ?)",
                (cur.lastrowid, vec.astype(np.float32).tobytes()),
            )
            added += 1
        self._conn.commit()
        return added

    # -- read --------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        count = self._conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]
        by_kind = {
            r[0]: r[1]
            for r in self._conn.execute(
                "SELECT kind, COUNT(*) FROM recipes GROUP BY kind"
            ).fetchall()
        }
        # Recover the embedding dim from the vec0 virtual-table DDL so a reader
        # can pick a dimension-matching embedder (mirrors VectorIndex.stats).
        dim: int | None = None
        ddl = self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='vec_recipes'"
        ).fetchone()
        if ddl and ddl[0]:
            try:
                dim = int(ddl[0].rsplit("[", 1)[1].rstrip("])"))
            except (IndexError, ValueError):
                dim = None
        return {
            "path": str(self._path) if self._path else None,
            "recipes": count,
            "by_kind": by_kind,
            "dim": dim,
        }

    def search(
        self,
        query: str,
        *,
        embedder: Embedder,
        k: int = 5,
        kind: str | None = None,
        recipe_kind: str | None = None,
        k_inflate: int = 8,
    ) -> list[tuple[DesignRecipe, float]]:
        """KNN search with optional metadata pre-filtering.

        sqlite-vec applies the ``MATCH``/``k`` KNN FIRST, then the JOIN's WHERE
        clauses filter the result set — so a metadata filter can leave fewer
        than *k* rows. When a filter is active we request ``k * k_inflate``
        neighbours from the vec0 table, filter, then trim to *k* (the
        post-KNN-filter trimming the directive called for).
        """
        q_vec = embedder.embed(query).astype(np.float32).tobytes()
        filtered = bool(kind or recipe_kind)
        inner_k = k * k_inflate if filtered else k
        where = ["v.embedding MATCH ?", "v.k = ?"]
        params: list[Any] = [q_vec, inner_k]
        if kind:
            where.append("r.kind = ?")
            params.append(kind)
        if recipe_kind:
            where.append("r.recipe_kinds LIKE ?")
            params.append(f'%"{recipe_kind}"%')
        sql = (
            "SELECT r.*, v.distance FROM vec_recipes v "
            "JOIN recipes r ON r.id = v.rowid "
            f"WHERE {' AND '.join(where)} ORDER BY v.distance LIMIT ?"
        )
        params.append(k)
        rows = self._conn.execute(sql, params).fetchall()
        out: list[tuple[DesignRecipe, float]] = []
        for r in rows:
            similarity = 1.0 / (1.0 + float(r["distance"]))
            out.append((_row_to_recipe(r), similarity))
        return out

    def get(self, retrieval_key: str) -> DesignRecipe | None:
        row = self._conn.execute(
            "SELECT * FROM recipes WHERE retrieval_key = ?", (retrieval_key,)
        ).fetchone()
        return _row_to_recipe(row) if row is not None else None


# ---------------------------------------------------------------------------
# Backfill adapters — bootstrap the corpus from existing on-disk history.
# ---------------------------------------------------------------------------


def ingest_proposals_dir(
    index: DesignMemoryIndex, embedder: Embedder, proposals_dir: Path
) -> dict[str, Any]:
    """Backfill from the ProposalStore (``proposals/*.json``).

    Each record is ``{kind, state, spec, proposed_at}``; the verbalizer
    dispatches on ``kind`` (drawing/assembly/feature_add) and returns None for
    empty/unverbalizable specs (skipped, counted).
    """
    recipes: list[DesignRecipe] = []
    skipped = 0
    files = sorted(proposals_dir.glob("*.json")) if proposals_dir.exists() else []
    for f in files:
        try:
            record = json.loads(f.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            skipped += 1
            continue
        recipe = verbalize_proposal_record(record, ref=f.stem)
        if recipe is None:
            skipped += 1
            continue
        recipes.append(recipe)
    added = index.add(recipes, embedder)
    return {"files": len(files), "indexed": added, "skipped": skipped}


def ingest_checkpoints(
    index: DesignMemoryIndex, embedder: Embedder, checkpoints_dir: Path
) -> dict[str, Any]:
    """Backfill from CheckpointStore DBs (``.checkpoints/*.sqlite``).

    Committed feature rows are grouped per part into a coarse build recipe
    (params aren't stored per-row, so this is a sequence recipe). Read raw —
    these DBs are unencrypted; the per-part CheckpointStore ceremony is skipped.
    """
    recipes: list[DesignRecipe] = []
    dbs = sorted(checkpoints_dir.glob("*.sqlite")) if checkpoints_dir.exists() else []
    for db in dbs:
        try:
            conn = sqlite3.connect(str(db))
            rows = conn.execute(
                "SELECT part_name, feature_index, feature_name, feature_type "
                "FROM checkpoints WHERE status = 'committed' ORDER BY feature_index"
            ).fetchall()
            conn.close()
        except sqlite3.Error:
            continue
        by_part: dict[str, list[tuple]] = {}
        for part_name, fidx, fname, ftype in rows:
            by_part.setdefault(part_name, []).append((fidx, fname, ftype))
        for part_name, feat_rows in by_part.items():
            text, kinds = verbalize_part_build(part_name, feat_rows)
            recipes.append(
                DesignRecipe(
                    source="checkpoints",
                    ref=part_name,
                    kind="part_build",
                    doc=part_name,
                    recipe_kinds=tuple(kinds),
                    state="committed",
                    recipe_text=text,
                )
            )
    added = index.add(recipes, embedder)
    return {"dbs": len(dbs), "parts_indexed": added}


def backfill_all(
    index: DesignMemoryIndex,
    embedder: Embedder,
    *,
    root: Path = Path("."),
) -> dict[str, Any]:
    """Run every backfill adapter; return a consolidated, honest report.

    NOTE: ``spikes/_results/*.json`` are deliberately EXCLUDED — a measure-first
    audit found only ~2/277 carry any design signal (the rest are probe/PAE
    telemetry with no common proposal schema). Reported, not silently dropped.
    """
    report: dict[str, Any] = {
        "proposals": ingest_proposals_dir(index, embedder, root / "proposals"),
        "checkpoints": ingest_checkpoints(index, embedder, root / ".checkpoints"),
        "spikes_excluded": {
            "reason": "heterogeneous probe/PAE telemetry, not design recipes "
            "(~2/277 had any design signal)",
        },
    }
    report["total_indexed"] = (
        report["proposals"]["indexed"] + report["checkpoints"]["parts_indexed"]
    )
    return report


def ingest_recipes(
    index: DesignMemoryIndex, embedder: Embedder, recipes: Iterable[DesignRecipe]
) -> int:
    """Thin helper: index an iterable of pre-built recipes (e.g. live
    TransactionStore rows verbalized by the caller)."""
    return index.add(list(recipes), embedder)


__all__ = [
    "DesignMemoryIndex",
    "ingest_proposals_dir",
    "ingest_checkpoints",
    "backfill_all",
    "ingest_recipes",
]
