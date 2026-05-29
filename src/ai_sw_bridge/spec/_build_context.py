"""Per-build state containers shared by the spec builder and its handlers.

Extracted from ``builder.py`` so handler modules can import ``BuildContext``,
``BuiltFeature``, ``DeferredDim``, and ``FeatureType`` without pulling in the
full handler-registry module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BuiltFeature:
    name: str
    type: str
    sw_object: Any = None  # the IFeature CDispatch
    # For sketches: the outward normal of the parent (reference plane OR
    # face) in part coordinates. Used by the subsequent extrusion to set its
    # axis. Set for plane-based sketches by build() after the handler runs;
    # set for face-based sketches inside the handler (so the chain of stacked
    # extrudes correctly inherits direction).
    parent_plane_normal: tuple[float, float, float] | None = None
    # For face-based sketches only: world-coord origin of the parent face
    # (the point _select_extrude_face succeeded at). The child extrude that
    # consumes this sketch uses it as its extrude_origin so downstream face-
    # selects find faces in the right place along stacked-extrude chains.
    parent_face_origin: tuple[float, float, float] | None = None
    # For plane-based sketches with a `center` offset: the sketch's center
    # in part coords (meters), with the axis-aligned component zeroed.
    # The downstream extrude uses this as its extrude_origin so the +/-z
    # face center for a child face-sketch lands at the actual face centroid,
    # not at (0, 0, depth). Was the root cause of the original TensionBracket
    # bug -- plane sketches with `center` offsets recorded extrude_origin
    # as world-origin and the downstream face math went wrong.
    sketch_center_part: tuple[float, float, float] | None = None
    # For extrusions: the actual extrude axis (outward normal of the boss/cut),
    # origin of the base face in part coords, blind depth in meters, and the
    # `flip` flag (True = extrude in -axis direction). Used by child sketches
    # on this extrusion's faces to compute world coords.
    extrude_axis: tuple[float, float, float] | None = None
    extrude_origin: tuple[float, float, float] | None = None
    extrude_depth_m: float | None = None
    extrude_flip: bool = False
    # For sketches built on a rectangular profile: half-extents along the
    # sketch's local u-axis and v-axis (in meters). Set by the rectangle
    # sketch handlers. Used by side-face frames (+/-x, +/-y) to compute
    # the side-face plane equations on the parent extrusion. None means
    # "profile has no flat side faces" (e.g., a circle sketch produces a
    # cylinder whose side is curved and not accessible via this builder).
    sketch_extent_uv: tuple[float, float] | None = None


@dataclass
class DeferredDim:
    """One AddDimension2 call deferred to the batch phase at the end of build().

    Populated by per-feature handlers when ctx.deferred_dim is True. Replayed
    by _apply_deferred_dims() AFTER all geometry has been built, so the user
    sees a contiguous burst of Modify-Dimension popups at the end instead of
    popups interleaved through a ~60-second build.

    The dim-placement coords (select_xyz + leader_xyz) are computed by the
    handler using its existing logic (sketch_uv_to_part, etc.) -- the handler
    knows where the dim goes; the deferred pass just replays the COM calls.
    """

    sketch_name: str  # name of the parent sketch (re-opened via EditSketch)
    select_type: str  # "SKETCHSEGMENT" for edges/perimeters
    select_xyz: tuple[float, float, float]  # part-coord point for SelectByID
    leader_xyz: tuple[float, float, float]  # AddDimension2 leader position
    expected_dim_name: str  # e.g. "D1@SK_Box" -- for error reporting
    field_label: str  # human-readable for errors, e.g. "width of SK_Box"


@dataclass
class BuildContext:
    """Per-build state. Holds the SW app/doc handle and feature lookup."""

    sw: Any
    doc: Any
    features_by_name: dict[str, BuiltFeature] = field(default_factory=dict)
    rebuild_count: int = 0
    # no_dim mode: skip all AddDimension2 calls and Add2 bindings. Geometry
    # is built at literal target sizes (rhs's resolved at the spec level
    # before any handler runs). The resulting part has no equation links to
    # locals.txt -- editing locals requires re-running ai-sw-build.
    no_dim: bool = False
    # deferred_dim mode: build all geometry without AddDimension2 calls
    # (popup-free Phase 1), then replay the dim calls in a contiguous batch
    # at the end (Phase 3). The resulting part HAS the live equation link
    # to locals.txt -- same as the legacy parametric mode but with N popups
    # batched at the end instead of interleaved through a ~60-second build.
    # See _apply_deferred_dims() for the replay logic.
    deferred_dim: bool = False
    # Populated by handlers when deferred_dim is True. One entry per dim that
    # would have been created by AddDimension2 in inline mode.
    deferred_dims: list[DeferredDim] = field(default_factory=list)
    # Lazy B-rep interrogation (spec.md §2.11): set of (parent_name, face_role)
    # tuples from the validator. When non-None, the interrogator skips face
    # walking for features not in this set and filters faces to matching
    # roles when the set is present. None = eager mode (default).
    referenced_face_roles: set[tuple[str, str]] | None = None


@dataclass(frozen=True)
class FieldSpec:
    """One spec field of a feature primitive (X3, FR-X-03).

    Carries the field's JSON-Schema property dict plus whether it is required.
    The single source from which ``schema.py`` *assembles* a primitive's
    fragment, replacing the hand-written per-primitive dict literals (so a new
    primitive is one descriptor edit, not five hand-synced files).

    ``schema`` is the exact JSON-Schema for this one property (e.g.
    ``LENGTH_SCHEMA`` for a parametric length, or ``{"type": "number",
    "maximum": 360}`` for an angle). The assembler wraps these in the common
    object envelope (``type``/``additionalProperties``/``required`` and the
    shared ``type`` const + ``name`` pattern).
    """

    name: str
    schema: dict[str, Any]
    required: bool = False


@dataclass
class FeatureDescriptor:
    """Per-feature-type metadata. One entry per supported feature.

    X3 (FR-X-03) grows the legacy ``FeatureType`` (name/handler/dim_fields/
    rhs_walker) into the single source of truth for a primitive: it also
    carries the declarative ``fields`` (for schema assembly) and the
    doc/coverage metadata. The added attributes are all optional so existing
    construction keeps working and primitives migrate incrementally.
    """

    name: str
    handler: Any  # Callable[[BuildContext, dict], BuiltFeature]
    # {spec_field_name: dim_suffix} for fixed dims. dim_suffix is the SW
    # auto-name (D1, D2, ...) created by AddDimension2 in selection order.
    dim_fields: dict[str, str]
    # Override for non-default rhs walking (e.g. arrays of dims).
    # Default None means "use the dim_fields-based walker."
    rhs_walker: Any | None = None  # Callable[[dict], list[(field_path, suffix, rhs)]]
    # --- X3 (FR-X-03) declarative + coverage metadata (all optional) ---
    # Declarative field list; schema.py assembles the JSON-Schema fragment
    # from these instead of a hand-written dict. Empty until migrated.
    fields: list[FieldSpec] = field(default_factory=list)
    # Risk tier per the spike-first law ("safe" | "spike" | "seat") and the
    # spike that GREEN-gated this primitive's COM signature, if any.
    risk_tier: str | None = None
    spike_id: str | None = None
    # Minimum proven SW version (e.g. "2024 SP1"). None = unversioned.
    sw_min: str | None = None
    # One-line human description + the canonical examples/<dir> that exercises
    # this primitive. Read by the doc-coverage test so docs can't drift.
    doc: str | None = None
    example_ref: str | None = None

    def collect_rhs_bindings(self, feat: dict[str, Any]) -> list[tuple[str, str]]:
        """Return [(dim_name, rhs)] for every parametric ({rhs}) length in
        this feature. dim_name is the SW-fq form 'Dn@FeatureName'."""
        # Imported lazily to avoid a circular dependency: _default_rhs_walker
        # is a thin closure factory that lives in builder.py with the rest of
        # the rhs-walking logic.
        from .builder import _default_rhs_walker

        walker = self.rhs_walker or _default_rhs_walker(self.dim_fields)
        return [
            (f"{suffix}@{feat['name']}", rhs)
            for _field_path, suffix, rhs in walker(feat)
        ]


# Back-compat alias: builder.py and tests import ``FeatureType``. The class was
# renamed to ``FeatureDescriptor`` in X3; the old name stays as an alias so the
# rename is non-breaking.
FeatureType = FeatureDescriptor
