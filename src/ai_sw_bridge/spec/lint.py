"""Semantic lint checks that go beyond schema validation.

These are advisory checks that catch likely authoring mistakes but don't
make the spec invalid. The ``--lint`` flag runs these after ``--dry-run``
and reports all findings as warnings (non-zero exit if any found).

Each check returns a list of LintFinding dicts. An empty list means pass.
"""

from __future__ import annotations

from typing import Any

from .schema import SKETCH_TYPES, EXTRUDE_TYPES


class LintFinding:
    """One lint warning. Not fatal — the spec may still build correctly."""

    def __init__(self, severity: str, path: str, message: str) -> None:
        self.severity = severity  # "warning" or "error"
        self.path = path
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "path": self.path,
            "message": self.message,
        }

    def __str__(self) -> str:
        return f"[{self.severity}] {self.path}: {self.message}"


def _check_unconsumed_sketches(spec: dict[str, Any]) -> list[LintFinding]:
    """Warn if a sketch is never referenced by a downstream feature.

    This usually means the author forgot to add an extrude/cut, or
    misspelled the sketch name in the extrude's `sketch` field (which
    the validator would catch as a reference error).
    """
    features = spec.get("features", [])
    sketch_names = set()
    consumed_by = set()
    for feat in features:
        ftype = feat.get("type", "")
        name = feat.get("name", "")
        if ftype in SKETCH_TYPES:
            sketch_names.add(name)
        if ftype in EXTRUDE_TYPES:
            target = feat.get("sketch", "")
            consumed_by.add(target)

    findings: list[LintFinding] = []
    for i, feat in enumerate(features):
        name = feat.get("name", "")
        ftype = feat.get("type", "")
        if ftype in SKETCH_TYPES and name not in consumed_by:
            findings.append(
                LintFinding(
                    severity="warning",
                    path=f"features/{i}/{name}",
                    message=(
                        f"sketch '{name}' is not referenced by any downstream "
                        f"extrude/cut feature"
                    ),
                )
            )
    return findings


# Face-bound features (sketch_*_on_face, simple_hole) address the parent by a
# +/-x/y/z normal and assume box-like geometry. Boss/cut extrudes have those
# clean orthogonal faces; revolves produce curved side faces and annular end
# faces where the face-selection heuristic is unreliable.
_ORTHO_FACE_PARENTS = frozenset(
    {"boss_extrude_blind", "cut_extrude_through_all", "cut_extrude_blind"}
)


def _check_face_references(spec: dict[str, Any]) -> list[LintFinding]:
    """Warn if a face-bound feature takes a face of a parent that has no
    clean orthogonal faces.

    `sketch_*_on_face` and `simple_hole` select the parent face by a
    +/-x/y/z normal and assume box-like geometry. The validator already
    rejects a missing or non-extrude parent; this advisory catches the
    subtler case of a *revolve* parent, whose faces are curved/annular and
    do not map cleanly to a +/-x/y/z direction.
    """
    features = spec.get("features", [])
    seen: dict[str, str] = {}  # name -> type, of features declared so far
    findings: list[LintFinding] = []

    for i, feat in enumerate(features):
        if "of_feature" in feat:
            parent = feat["of_feature"]
            parent_type = seen.get(parent)
            # Missing parent / forward reference is the validator's job.
            if parent_type is not None and parent_type not in _ORTHO_FACE_PARENTS:
                findings.append(
                    LintFinding(
                        severity="warning",
                        path=f"features/{i}/of_feature",
                        message=(
                            f"feature '{feat.get('name', '')}' takes face "
                            f"'{feat.get('face', '')}' of '{parent}' "
                            f"({parent_type}), which has no clean orthogonal "
                            f"faces -- face selection may pick the wrong surface"
                        ),
                    )
                )
        seen[feat.get("name", "")] = feat.get("type", "")

    return findings


def _check_top_plane_centerline_center_z(
    spec: dict[str, Any],
) -> list[LintFinding]:
    """Warn if a Top Plane sketch has a centerline but no center.z.

    On Top Plane (XZ), a centerline along sketch_Y is the part Z axis.
    Revolve features need the centerline's part-Z position to be correct,
    which requires `center.z`. Without it, the centerline endpoints
    default to z=0 in the part frame, which is almost never what the
    author wants for a revolved feature on Top Plane.
    """
    features = spec.get("features", [])
    findings: list[LintFinding] = []

    for i, feat in enumerate(features):
        plane = feat.get("plane", "")
        if plane != "Top":
            continue
        if "centerline" not in feat:
            continue
        center = feat.get("center", {})
        has_center_z = "z" in center if isinstance(center, dict) else False
        if not has_center_z:
            findings.append(
                LintFinding(
                    severity="warning",
                    path=f"features/{i}/center.z",
                    message=(
                        f"sketch '{feat.get('name', '')}' on Top Plane has a "
                        f"centerline but no center.z — the centerline will "
                        f"default to part Z=0, which is usually wrong for "
                        f"revolved features"
                    ),
                )
            )
    return findings


def _check_center_z_thread_through(
    spec: dict[str, Any],
) -> list[LintFinding]:
    """Warn if a Top Plane sketch with center.z is consumed by boss_extrude.

    When a Top Plane sketch has non-zero center.z and is consumed by
    boss_extrude (not revolve), the extrude_origin remap currently
    ignores center.z — it derives part-Z from the sketch-local-Y
    projection instead. This produces incorrect extrude_origin for
    downstream face-selection. The builder comment at builder.py:405-414
    documents this known gap.
    """
    features = spec.get("features", [])
    findings: list[LintFinding] = []
    sketch_info: dict[str, dict[str, Any]] = {}

    for i, feat in enumerate(features):
        ftype = feat.get("type", "")
        name = feat.get("name", "")
        if ftype in SKETCH_TYPES:
            plane = feat.get("plane", "")
            center = feat.get("center", {})
            has_center_z = (
                isinstance(center, dict) and "z" in center and center["z"] != 0
            )
            if plane == "Top" and has_center_z:
                sketch_info[name] = feat

        if ftype == "boss_extrude_blind":
            sketch_name = feat.get("sketch", "")
            if sketch_name in sketch_info:
                findings.append(
                    LintFinding(
                        severity="warning",
                        path=f"features/{i}/sketch",
                        message=(
                            f"boss_extrude consumes Top Plane sketch "
                            f"'{sketch_name}' with non-zero center.z — "
                            f"extrude_origin may be incorrect (known gap, "
                            f"see builder.py:405-414)"
                        ),
                    )
                )

    return findings


def lint(spec: dict[str, Any]) -> list[LintFinding]:
    """Run all semantic lint checks. Returns a (possibly empty) list of findings.

    Unlike validate(), lint() does not raise on failure. It collects all
    findings so the author can see everything at once.
    """
    findings: list[LintFinding] = []
    findings.extend(_check_unconsumed_sketches(spec))
    findings.extend(_check_face_references(spec))
    findings.extend(_check_top_plane_centerline_center_z(spec))
    findings.extend(_check_center_z_thread_through(spec))
    return findings
