"""Design verbalizer — turn a design proposal/transaction into embeddable text.

Embedding raw JSON makes every design look alike: the ``{"feature":{"type":...
,"target":...}}`` skeleton, braces and quotes dominate the token stream, so the
vectors cluster on *JSON-ness* instead of engineering intent. This module
translates a design into a structured, syntax-free **recipe** — a header line
(what kind of design, on what doc, with which operations) followed by one
human-readable phrase per operation — mirroring the proven
``rag.corpus._progguide_embedding_text`` pattern.

Kind-dispatched because the real corpus is heterogeneous: feature-add batches
(the forward-looking ``TransactionStore`` payload), drawings, and assemblies.
Each kind has its own phrase family; unknown kinds degrade to a humanized
fallback (snake_case -> words + scalar params) rather than raising.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Recipe record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DesignRecipe:
    """One embeddable design unit (the per-transaction chunk)."""

    source: str  # "proposals" | "checkpoints" | "transactions"
    ref: str  # stable id within the source (txn id, proposal id, part name)
    kind: str  # "feature_add" | "drawing" | "assembly" | "part_build"
    doc: str  # the model/part/drawing this design targets
    recipe_kinds: tuple[str, ...]  # operation kinds present (metadata filter)
    state: str  # lifecycle (committed/proposed/...) where known
    recipe_text: str  # the verbalized, embeddable text block

    @property
    def spec_hash(self) -> str:
        return hashlib.sha256(self.recipe_text.encode("utf-8")).hexdigest()

    def retrieval_key(self) -> str:
        return f"{self.source}:{self.kind}:{self.ref}"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _humanize(token: str) -> str:
    """snake_case / kebab -> spaced words."""
    return token.replace("_", " ").replace("-", " ").strip()


def _num(v: Any) -> str:
    """Render a number without a trailing .0 so phrases read naturally."""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        f = float(v)
        return str(int(f)) if f.is_integer() else f"{f:g}"
    return str(v)


def _doc_stem(path: str) -> str:
    if not path:
        return "?"
    base = str(path).replace("\\", "/").rsplit("/", 1)[-1]
    return base.rsplit(".", 1)[0] if "." in base else base


# Human labels for the 36 live feature-add registry kinds (+ common checkpoint
# kinds). Missing kinds fall back to _humanize(kind).
_KIND_LABELS: dict[str, str] = {
    "ref_plane": "reference plane",
    "ref_axis": "reference axis",
    "ref_point": "reference point",
    "coordinate_system": "coordinate system",
    "com_point": "center-of-mass point",
    "bounding_box": "bounding box",
    "fillet_constant_radius": "constant-radius fillet",
    "variable_radius_fillet": "variable-radius fillet",
    "fillet_face": "face fillet",
    "chamfer": "chamfer",
    "shell": "shell",
    "draft": "draft",
    "dome": "dome",
    "scale": "scale",
    "delete_body": "delete body",
    "linear_pattern": "linear pattern",
    "circular_pattern": "circular pattern",
    "mirror_feature": "mirror",
    "sketch_driven_pattern": "sketch-driven pattern",
    "sweep": "sweep",
    "sweep_cut": "sweep cut",
    "helix": "helix",
    "spiral": "spiral",
    "composite": "composite curve",
    "project_curve": "projected curve",
    "curve_through_xyz": "curve through XYZ points",
    "intersect": "intersect",
    "knit": "knit surface",
    "planar_surface": "planar surface",
    "offset_surface": "offset surface",
    "mate_reference": "mate reference",
    "structural_weldment": "structural weldment",
    "base_flange": "sheet-metal base flange",
    "hem": "sheet-metal hem",
    "sketched_bend": "sheet-metal sketched bend",
    "wizard_hole": "hole-wizard hole",
}

# (param key -> phrase template) rendered when present on a feature dict.
_PARAM_PHRASES: list[tuple[str, str]] = [
    ("distance_mm", "{} mm offset"),
    ("depth_mm", "{} mm deep"),
    ("radius_mm", "radius {} mm"),
    ("angle_deg", "{}°"),
    ("thickness_mm", "{} mm thick"),
    ("count", "{} instances"),
    ("spacing_mm", "spaced {} mm"),
    ("pitch_mm", "pitch {} mm"),
    ("height_mm", "{} mm high"),
    ("revolutions", "{} revolutions"),
]


def _salient_params(feature: dict) -> str:
    parts = [tpl.format(_num(feature[k])) for k, tpl in _PARAM_PHRASES if k in feature]
    return ", ".join(parts)


def _target_phrase(target: dict) -> str:
    if not isinstance(target, dict) or not target:
        return ""
    if "plane" in target:
        return f"from {target['plane']}"
    for sel in ("edge", "face", "vertex", "seed", "body", "sketch"):
        if sel in target:
            return f"on {_humanize(sel)}"
    return ""


# ---------------------------------------------------------------------------
# Per-feature / per-kind verbalizers
# ---------------------------------------------------------------------------


def verbalize_feature(feature: dict, target: dict | None = None) -> str:
    """One feature dict -> one natural-language phrase (no JSON syntax)."""
    kind = (feature or {}).get("type", "unknown")
    label = _KIND_LABELS.get(kind, _humanize(kind))
    bits = [label]
    params = _salient_params(feature or {})
    if params:
        bits.append(params)
    tgt = _target_phrase(target or {})
    if tgt:
        bits.append(tgt)
    return " ".join(bits)


def verbalize_feature_add(proposals: list, *, doc: str = "") -> tuple[str, list[str]]:
    """A feature-add proposal LIST -> (recipe_text, operation kinds)."""
    kinds = [str((p.get("feature") or {}).get("type", "?")) for p in proposals]
    header = (
        f"Part build: {_doc_stem(doc)}  |  {len(proposals)} features: "
        + ", ".join(dict.fromkeys(kinds))
    )
    lines = [
        "- " + verbalize_feature(p.get("feature") or {}, p.get("target") or {})
        for p in proposals
    ]
    return "\n".join([header, *lines]), kinds


def verbalize_drawing(spec: dict) -> tuple[str, list[str]]:
    """A drawing proposal spec -> (recipe_text, table/view kinds)."""
    model = _doc_stem(spec.get("model", ""))
    name = spec.get("name", "drawing")
    views = spec.get("views") or []
    tables = [
        t.replace("_table", "")
        for t in ("revision_table", "general_table", "weldment_table", "hole_table")
        if spec.get(t)
    ]
    header = f"Drawing: {name} of {model}"
    lines = []
    if views:
        lines.append(f"- views: {', '.join(views)}")
    if tables:
        lines.append(f"- tables: {', '.join(tables)}")
    kinds = ["drawing"] + [f"view:{v}" for v in views] + [f"table:{t}" for t in tables]
    return "\n".join([header, *lines]) if lines else header, kinds


def verbalize_assembly(spec: dict) -> tuple[str, list[str]]:
    """An assembly proposal spec -> (recipe_text, mate/component kinds)."""
    name = spec.get("name", "assembly")
    components = spec.get("components") or []
    mates = spec.get("mates") or []
    header = f"Assembly: {name}  |  {len(components)} components, {len(mates)} mates"
    lines = []
    for c in components:
        part = _doc_stem(c.get("part", "")) if isinstance(c, dict) else str(c)
        lines.append(f"- component {c.get('id', '?')}: {part}")
    mate_kinds = []
    for m in mates:
        mk = m.get("type") or m.get("kind") or "mate" if isinstance(m, dict) else "mate"
        mate_kinds.append(str(mk))
        lines.append(f"- {_humanize(str(mk))} mate")
    kinds = ["assembly"] + [f"mate:{k}" for k in dict.fromkeys(mate_kinds)]
    return "\n".join([header, *lines]) if lines else header, kinds


def verbalize_part_build(part_name: str, feature_rows: list[tuple]) -> tuple[str, list]:
    """Checkpoint per-part rows -> a coarse part-build recipe.

    Each row is ``(feature_index, feature_name, feature_type)`` ordered by
    feature_index. Params aren't stored per-row, so this is a sequence recipe.
    """
    ordered = sorted(feature_rows, key=lambda r: r[0])
    kinds = [str(r[2]) for r in ordered]
    header = f"Part build: {part_name}  |  {len(ordered)} features: " + ", ".join(
        dict.fromkeys(kinds)
    )
    lines = [
        f"- {_KIND_LABELS.get(r[2], _humanize(str(r[2])))} ({r[1]})" for r in ordered
    ]
    return "\n".join([header, *lines]), kinds


# ---------------------------------------------------------------------------
# Top-level dispatch
# ---------------------------------------------------------------------------


def verbalize_proposal_record(record: dict, ref: str) -> DesignRecipe | None:
    """Dispatch a ProposalStore record (kind/state/spec) to its verbalizer.

    Returns None for empty/unverbalizable specs (e.g. the empty feature_add
    stubs) so the caller can skip them without polluting the index.
    """
    kind = record.get("kind")
    spec = record.get("spec") or {}
    state = str(record.get("state", "unknown"))
    if not isinstance(spec, dict) or not spec:
        return None

    if kind == "drawing":
        text, kinds = verbalize_drawing(spec)
        doc = _doc_stem(spec.get("model", ""))
    elif kind == "assembly":
        text, kinds = verbalize_assembly(spec)
        doc = spec.get("name", "assembly")
    elif kind == "feature_add":
        proposals = spec.get("proposals") or (
            [{"feature": spec.get("feature"), "target": spec.get("target")}]
            if spec.get("feature")
            else []
        )
        if not proposals:
            return None
        text, kinds = verbalize_feature_add(proposals, doc=spec.get("doc_path", ""))
        doc = _doc_stem(spec.get("doc_path", ""))
    else:
        return None

    return DesignRecipe(
        source="proposals",
        ref=ref,
        kind=str(kind),
        doc=doc,
        recipe_kinds=tuple(kinds),
        state=state,
        recipe_text=text,
    )


def verbalize_transaction(
    doc_path: str, intent_payload: str, ref: str, *, state: str = "committed"
) -> DesignRecipe | None:
    """A TransactionStore row (intent_payload = JSON proposal list) -> recipe."""
    try:
        proposals = json.loads(intent_payload)
    except (ValueError, TypeError):
        return None
    if not isinstance(proposals, list) or not proposals:
        return None
    text, kinds = verbalize_feature_add(proposals, doc=doc_path)
    return DesignRecipe(
        source="transactions",
        ref=ref,
        kind="feature_add",
        doc=_doc_stem(doc_path),
        recipe_kinds=tuple(kinds),
        state=state,
        recipe_text=text,
    )


__all__ = [
    "DesignRecipe",
    "verbalize_feature",
    "verbalize_feature_add",
    "verbalize_drawing",
    "verbalize_assembly",
    "verbalize_part_build",
    "verbalize_proposal_record",
    "verbalize_transaction",
]
