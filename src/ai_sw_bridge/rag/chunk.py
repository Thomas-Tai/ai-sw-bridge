"""Chunking strategies (spec.md §4.3).

Two strategies, one per corpus:

* **Narrative** (``sldworksapiprogguide``) — paragraph-based with
  ``chunk_tokens`` target and ``overlap_tokens`` overlap. Splits the
  topic prose on paragraph breaks (``\\n\\n`` emitted by the
  extractor), then greedily packs paragraphs into a window. Windows
  slide by ``chunk_tokens - overlap_tokens`` so adjacent chunks share
  context at their boundary. Table / list boundaries are honored
  insofar as the extractor preserves them as paragraph breaks --
  a ``<p>`` inside a ``<table>`` becomes a paragraph, so a table
  never straddles two chunks when it fits in one.
* **Reference** (``sldworksapi``) — identity. One method / one enum
  = one chunk. No splitting.

Token counts are word-count approximations (``len(text.split())``).
The embedding model's real tokenizer is used in E5.3
(:mod:`ai_sw_bridge.rag.embed`); the chunker stays tokenizer-free
so it has zero external deps and runs in pure Python.

Stability contract: given the same input corpus and the same
``chunk_tokens`` / ``overlap_tokens`` pair, the chunker emits the
same sequence of chunk boundaries across runs. Verified in
:mod:`tests.rag.test_chunk`.
"""

from __future__ import annotations

from dataclasses import replace

from .corpus import ApiChunk

DEFAULT_CHUNK_TOKENS = 200
DEFAULT_OVERLAP_TOKENS = 40


def _approx_tokens(text: str) -> int:
    """Word-count approximation of token count.

    Good enough for chunking (the embedder's real tokenizer
    determines vector length). Avoids pulling in a 100 MB
    tokenizer dependency just for boundary decisions.
    """
    return len(text.split())


def chunk_progguide_topic(
    chunk: ApiChunk,
    *,
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[ApiChunk]:
    """Split one narrative-topic chunk into windowed sub-chunks.

    Short topics (prose fits in ``chunk_tokens``) come back as a
    single-element list containing the original chunk unchanged --
    so callers can always iterate the return value without
    special-casing.

    Args:
        chunk: A single topic-shaped ApiChunk (``chunk_type='topic'``).
        chunk_tokens: Target tokens per window (word-count approx).
        overlap_tokens: Number of tokens shared between adjacent
            windows. Must be strictly less than ``chunk_tokens``.

    Returns:
        One or more ApiChunk instances, each with ``chunk_index``
        set to its position in the sequence. The first sub-chunk
        inherits ``chunk_index=0``.

    Raises:
        ValueError: ``overlap_tokens >= chunk_tokens``.
    """
    if overlap_tokens >= chunk_tokens:
        raise ValueError(
            f"overlap_tokens ({overlap_tokens}) must be < "
            f"chunk_tokens ({chunk_tokens})"
        )

    prose = chunk.description or ""
    if not prose:
        return [replace(chunk, chunk_index=0)]

    paragraphs = [p for p in prose.split("\n\n") if p.strip()]
    if not paragraphs:
        return [replace(chunk, chunk_index=0)]

    para_tokens = [_approx_tokens(p) for p in paragraphs]
    avg_para_tokens = sum(para_tokens) / len(para_tokens) or 1
    # Convert token-based window/overlap into paragraph-based step.
    # `step` is how many paragraphs the cursor advances per window
    # so adjacent windows share boundary context. Clamped to >=1.
    step = max(
        1,
        int((chunk_tokens - overlap_tokens) / avg_para_tokens) or 1,
    )
    # A window typically holds `chunk_tokens / avg_para_tokens` paragraphs;
    # if step >= that count, force step=1 so we don't skip content.
    typical_window = max(1, int(chunk_tokens / avg_para_tokens) or 1)
    if step >= typical_window:
        step = max(1, typical_window - 1)

    windows: list[list[str]] = []
    cursor = 0
    while cursor < len(paragraphs):
        # Greedy pack: extend from cursor until the next paragraph
        # would push us past chunk_tokens. A first paragraph that
        # alone exceeds chunk_tokens is emitted solo (graceful
        # degradation).
        window_end = cursor
        window_tokens = 0
        while window_end < len(paragraphs):
            next_tokens = window_tokens + para_tokens[window_end]
            if next_tokens > chunk_tokens:
                if window_end == cursor:
                    # First paragraph overshoots: emit it solo.
                    window_end = cursor + 1
                break
            window_tokens = next_tokens
            window_end += 1

        windows.append(paragraphs[cursor:window_end])
        # Advance by step paragraphs. `step < (typical window length)`
        # guarantees adjacent windows share paragraphs at their
        # boundary.
        cursor += step

    # Drop the final window if it's a strict suffix of the previous
    # one (happens when the last `step` advance lands near the end).
    if len(windows) >= 2 and windows[-1] == windows[-2][-len(windows[-1]) :]:
        windows.pop()

    if len(windows) == 1:
        return [replace(chunk, chunk_index=0)]

    out: list[ApiChunk] = []
    for idx, paras in enumerate(windows):
        sub_prose = "\n\n".join(paras)
        sub_text = "\n".join(
            part
            for part in [
                f"[{chunk.interface}]" if chunk.interface else "",
                chunk.name,
                sub_prose,
                chunk.example_code or "",
            ]
            if part
        )
        out.append(
            replace(
                chunk,
                description=sub_prose,
                text_for_embedding=sub_text,
                chunk_index=idx,
            )
        )
    return out


__all__ = [
    "DEFAULT_CHUNK_TOKENS",
    "DEFAULT_OVERLAP_TOKENS",
    "chunk_progguide_topic",
]
