"""Vector index backed by sqlite-vec (spec.md §4.4).

Schema
------
One SQLite database with three objects:

    chunks(id INTEGER PRIMARY KEY,
           retrieval_key TEXT UNIQUE,
           corpus        TEXT,
           chunk_type    TEXT,
           interface     TEXT,
           name          TEXT,
           description   TEXT,
           example_code  TEXT,
           chm_anchor    TEXT,
           keywords      TEXT,        -- JSON list
           text_for_embedding TEXT)

    vec_chunks(rowid INTEGER PRIMARY KEY,
               embedding FLOAT32[<dim>])    -- virtual table (sqlite-vec)

The two tables are joined by rowid == chunks.id so KNN results
carry the full chunk payload back without a second lookup.

Public surface
--------------
* :class:`VectorIndex` — context-manager wrapper around a SQLite
  connection. Methods:

  - :meth:`build` — populate from a list of ApiChunks + an embedder.
    Deterministic: given the same inputs, writes the same bytes.
  - :meth:`add` — incrementally insert one or more chunks (used by
    the E5.5 CLI's ingest subcommand).
  - :meth:`search` — KNN query. Returns a list of
    ``(ApiChunk, score)`` pairs sorted by cosine similarity desc.
  - :meth:`stats` — chunk count + dim for diagnostics.

The index file is the artifact committed by E5.4. CI runs a
determinism gate that rebuilds from the corpus + embedder and
asserts byte-equal to the committed file (risk register: *index
build determinism*).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .corpus import ApiChunk
from .embed import Embedder


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS chunks (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    retrieval_key      TEXT    UNIQUE NOT NULL,
    corpus             TEXT    NOT NULL,
    chunk_type         TEXT    NOT NULL,
    interface          TEXT    NOT NULL,
    name               TEXT    NOT NULL,
    description        TEXT    NOT NULL,
    example_code       TEXT,
    chm_anchor         TEXT    NOT NULL,
    keywords           TEXT    NOT NULL,
    text_for_embedding TEXT    NOT NULL
);
"""


def _register_vec(conn: sqlite3.Connection) -> None:
    """Load the sqlite-vec extension on a fresh connection."""
    try:
        import sqlite_vec  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "sqlite-vec is not installed; install with `pip install sqlite-vec`."
        ) from e
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)


def _chunk_to_row(c: ApiChunk) -> dict[str, Any]:
    return {
        "retrieval_key": c.retrieval_key(),
        "corpus": c.corpus,
        "chunk_type": c.chunk_type,
        "interface": c.interface,
        "name": c.name,
        "description": c.description,
        "example_code": c.example_code,
        "chm_anchor": c.chm_anchor,
        "keywords": json.dumps(list(c.keywords)),
        "text_for_embedding": c.text_for_embedding,
    }


def _row_to_chunk(row: sqlite3.Row) -> ApiChunk:
    kw_raw = row["keywords"]
    keywords = tuple(json.loads(kw_raw)) if kw_raw else ()
    return ApiChunk(
        chunk_type=row["chunk_type"],
        corpus=row["corpus"],
        interface=row["interface"],
        name=row["name"],
        signature=None,  # not persisted; rebuild from source if needed
        description=row["description"],
        example_code=row["example_code"],
        chm_anchor=row["chm_anchor"],
        text_for_embedding=row["text_for_embedding"],
        chunk_index=_extract_chunk_index(row["retrieval_key"]),
        keywords=keywords,
    )


def _extract_chunk_index(key: str) -> int:
    """Recover the trailing `:<idx>` from a retrieval key."""
    try:
        return int(key.rsplit(":", 1)[-1])
    except ValueError:
        return 0


class VectorIndex:
    """Sqlite-vec-backed KNN index over ApiChunks.

    Use as a context manager so the SQLite connection is closed on
    exit:

        with VectorIndex.open(path) as idx:
            results = idx.search("how to add a dimension", k=5)
    """

    def __init__(self, conn: sqlite3.Connection, path: Path | None) -> None:
        self._conn = conn
        self._path = path
        self._vec_ready = False

    # -- lifecycle ----------------------------------------------------------

    @classmethod
    def open(cls, path: Path) -> "VectorIndex":
        """Open an existing index file read-only."""
        if not path.exists():
            raise FileNotFoundError(f"index not found: {path}")
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        _register_vec(conn)
        return cls(conn, path)

    @classmethod
    def create(cls, path: Path, dim: int) -> "VectorIndex":
        """Create a fresh index file (overwrites any existing file)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        _register_vec(conn)
        conn.executescript(_SCHEMA_SQL)
        conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks "
            f"USING vec0(embedding float[{dim}])"
        )
        conn.commit()
        return cls(conn, path)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "VectorIndex":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # -- inspection ---------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        cur = self._conn.execute("SELECT COUNT(*) FROM chunks")
        count = cur.fetchone()[0]
        dim_cur = self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='vec_chunks'"
        ).fetchone()
        dim: int | None = None
        if dim_cur and dim_cur[0]:
            # sql looks like "... vec0(embedding float[256])"
            try:
                dim = int(dim_cur[0].rsplit("[", 1)[1].rstrip("])"))
            except (IndexError, ValueError):
                dim = None
        return {
            "path": str(self._path) if self._path else None,
            "chunks": count,
            "dim": dim,
        }

    # -- write path ---------------------------------------------------------

    def add(self, chunks: Sequence[ApiChunk], embedder: Embedder) -> int:
        """Insert chunks + their embeddings. Returns rows added.

        Duplicates (same ``retrieval_key``) are skipped silently so
        re-running the build is idempotent.
        """
        if not chunks:
            return 0
        texts = [c.text_for_embedding for c in chunks]
        vectors = embedder.embed_many(texts)
        added = 0
        for chunk, vec in zip(chunks, vectors):
            row = _chunk_to_row(chunk)
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO chunks "
                "(retrieval_key, corpus, chunk_type, interface, name, "
                "description, example_code, chm_anchor, keywords, "
                "text_for_embedding) VALUES "
                "(:retrieval_key, :corpus, :chunk_type, :interface, :name, "
                ":description, :example_code, :chm_anchor, :keywords, "
                ":text_for_embedding)",
                row,
            )
            if cur.rowcount == 0:
                continue
            row_id = cur.lastrowid
            self._conn.execute(
                "INSERT INTO vec_chunks(rowid, embedding) VALUES (?, ?)",
                (row_id, vec.astype(np.float32).tobytes()),
            )
            added += 1
        self._conn.commit()
        return added

    def build(self, chunks: Sequence[ApiChunk], embedder: Embedder) -> dict[str, Any]:
        """(Re)build the index from scratch.

        Drops existing rows and re-inserts. Returns a small summary
        dict (useful for E5.4's CI determinism gate log line).
        """
        self._conn.execute("DELETE FROM chunks")
        self._conn.execute("DELETE FROM vec_chunks")
        self._conn.commit()
        added = self.add(chunks, embedder)
        return {"chunks": added, "dim": embedder.dim}

    # -- read path ----------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        embedder: Embedder,
        k: int = 5,
        corpus_filter: str | None = None,
    ) -> list[tuple[ApiChunk, float]]:
        """KNN search. Returns up to ``k`` ``(ApiChunk, score)`` pairs.

        Score is converted from sqlite-vec's L2 distance to a
        "higher-is-better" similarity via ``1 / (1 + distance)`` so
        the CLI and eval harness can sort naturally descending.

        ``corpus_filter`` narrows to one corpus (e.g.
        ``"sldworksapiprogguide"``) for callers that want to keep
        API-ref and narrative results separate.
        """
        q_vec = embedder.embed(query).astype(np.float32).tobytes()
        if corpus_filter is not None:
            sql = (
                "SELECT c.*, v.distance "
                "FROM vec_chunks v "
                "JOIN chunks c ON c.id = v.rowid "
                "WHERE v.embedding MATCH ? AND v.k = ? AND c.corpus = ? "
                "ORDER BY v.distance"
            )
            params: tuple[Any, ...] = (q_vec, k, corpus_filter)
        else:
            sql = (
                "SELECT c.*, v.distance "
                "FROM vec_chunks v "
                "JOIN chunks c ON c.id = v.rowid "
                "WHERE v.embedding MATCH ? AND v.k = ? "
                "ORDER BY v.distance"
            )
            params = (q_vec, k)
        rows = self._conn.execute(sql, params).fetchall()
        out: list[tuple[ApiChunk, float]] = []
        for r in rows:
            distance = float(r["distance"])
            similarity = 1.0 / (1.0 + distance)
            out.append((_row_to_chunk(r), similarity))
        return out


__all__ = ["VectorIndex"]
