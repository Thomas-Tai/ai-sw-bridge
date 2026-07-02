"""Frozen snapshot of the SolidWorksClient public surface (PUBLIC_API.md §3).

The facade's "signatures guaranteed backward-compatible" promise had no guard
(CLI has test_cli_stability, MCP has EXPECTED_TOOLS). This closes that leg.
Strict snapshot: BOTH removals and un-snapshotted additions fail, mirroring
EXPECTED_TOOLS discipline — public surface stays intentionally designed.

COM-clean: importing client.py touches no COM (lazy app/mod). Do not
instantiate against a live seat here.
"""

from __future__ import annotations

import inspect

import pytest

from ai_sw_bridge.client import (
    SolidWorksClient,
    SolidWorksObserverFacade,
    SolidWorksMutatorFacade,
    UrdfFacade,
    SolidWorksExportFacade,
    SolidWorksFeaturesFacade,
)


def _surface(cls) -> dict[str, str]:
    """Public members: methods -> signature string; properties -> '<property>'."""
    out: dict[str, str] = {}
    for name in dir(cls):
        if name.startswith("_"):
            continue
        attr = inspect.getattr_static(cls, name)
        if isinstance(attr, property):
            out[name] = "<property>"
        elif inspect.isfunction(attr):
            out[name] = str(inspect.signature(attr))
    return out


# Regenerate intentionally when the public surface changes on purpose:
#   python -c "import inspect, json; from tests.test_facade_surface import _surface, _CLASSES; print(json.dumps({k: _surface(v) for k,v in _CLASSES.items()}, indent=2, sort_keys=True))"
# (any new public method is a deliberate act and must be admitted here.)
EXPECTED = {
    "SolidWorksClient": {
        "active_doc": "(self) -> 'Any'",
        "app": "<property>",
        "export": "<property>",
        "features": "<property>",
        "mod": "<property>",
        "mutate": "<property>",
        "observe": "<property>",
        "urdf": "<property>",
    },
    "SolidWorksExportFacade": {
        "run": "(self, doc: 'Any', requests: 'Any', part_name: 'str') -> 'Any'",
    },
    "SolidWorksFeaturesFacade": {
        "list_kinds": "(self) -> 'list[str]'",
        "supports": "(self, kind: 'str') -> 'bool'",
    },
    "SolidWorksMutatorFacade": {
        "batch": "(self, file_path: 'str', proposals: \"'list[dict]'\", strict: 'bool' = False, *, supervised: 'bool' = True) -> 'dict[str, Any]'",
        "commit": "(self, proposal_id: 'str') -> 'dict[str, Any]'",
        "commit_assembly": "(self, proposal_id: 'str', output_path: 'str', *, part_paths: 'dict[str, str] | None' = None) -> 'dict[str, Any]'",
        "commit_drawing": "(self, proposal_id: 'str', output_path: 'str') -> 'dict[str, Any]'",
        "commit_feature_add": "(self, proposal_id: 'str') -> 'dict[str, Any]'",
        "commit_properties": "(self, proposal_id: 'str') -> 'dict[str, Any]'",
        "dry_run": "(self, proposal_id: 'str') -> 'dict[str, Any]'",
        "dry_run_assembly": "(self, proposal_id: 'str') -> 'dict[str, Any]'",
        "dry_run_drawing": "(self, proposal_id: 'str') -> 'dict[str, Any]'",
        "dry_run_feature_add": "(self, proposal_id: 'str') -> 'dict[str, Any]'",
        "dry_run_properties": "(self, proposal_id: 'str') -> 'dict[str, Any]'",
        "edit_assembly": "(self, manifest_path: 'str', op: 'dict[str, Any]') -> 'dict[str, Any]'",
        "propose_assembly": "(self, spec: 'dict[str, Any]') -> 'dict[str, Any]'",
        "propose_drawing": "(self, spec: 'dict[str, Any]') -> 'dict[str, Any]'",
        "propose_feature_add": "(self, doc_path: 'str', feature: 'dict', target: 'dict') -> 'dict[str, Any]'",
        "propose_local_change": "(self, var: 'str', new_value: 'str') -> 'dict[str, Any]'",
        "propose_properties": "(self, spec: 'dict[str, Any]') -> 'dict[str, Any]'",
        "undo_last_commit": "(self) -> 'dict[str, Any]'",
    },
    "SolidWorksObserverFacade": {
        "active_doc": "(self) -> 'dict[str, Any]'",
        "analyze_stackup": "(self, component_names: 'Any', *, check_endpoints: 'bool' = True, doc: 'Any' = None) -> 'dict[str, Any]'",
        "assembly_bbox": "(self, *, doc: 'Any' = None) -> 'dict[str, Any]'",
        "bbox": "(self) -> 'dict[str, Any]'",
        "bbox_from_doc": "(self, *, doc: 'Any' = None) -> 'dict[str, Any]'",
        "body_interference": "(self) -> 'dict[str, Any]'",
        "clearance": "(self, comp_a: 'str', comp_b: 'str', *, doc: 'Any' = None) -> 'dict[str, Any]'",
        "custom_props": "(self) -> 'dict[str, Any]'",
        "draft_analysis": "(self, pull_direction: 'str', min_angle_deg: 'float' = 1.0, *, doc: 'Any' = None) -> 'dict[str, Any]'",
        "enabled_addins": "(self) -> 'dict[str, Any]'",
        "equations": "(self) -> 'dict[str, Any]'",
        "face_clearance": "(self, face_a: 'str', face_b: 'str', *, doc: 'Any' = None) -> 'dict[str, Any]'",
        "feature_errors": "(self) -> 'dict[str, Any]'",
        "feature_statistics": "(self) -> 'dict[str, Any]'",
        "get_inertia": "(self, doc: 'Any' = None) -> 'dict[str, Any]'",
        "import_diagnostics": "(self) -> 'dict[str, Any]'",
        "interference": "(self, *, doc: 'Any' = None) -> 'dict[str, Any]'",
        "mate_errors": "(self) -> 'dict[str, Any]'",
        "mbd": "(self, file_path: 'str | None' = None, *, doc: 'Any' = None) -> 'dict[str, Any]'",
        "measure": "(self, entity_a: 'str | None' = None, entity_b: 'str | None' = None) -> 'dict[str, Any]'",
        "measure_angle": "(self, *, doc: 'Any' = None) -> 'dict[str, Any]'",
        "measure_area": "(self, *, doc: 'Any' = None) -> 'dict[str, Any]'",
        "measure_durable_pair": "(self, durable_ref_a: 'str', durable_ref_b: 'str', *, doc: 'Any' = None) -> 'dict[str, Any]'",
        "measure_selection": "(self, *, doc: 'Any' = None) -> 'dict[str, Any]'",
        "min_wall_thickness": "(self, samples_per_face: 'int' = 4) -> 'dict[str, Any]'",
        "screenshot": "(self, width: 'int' = 640, height: 'int' = 360, fit_view: 'bool' = False, filename: 'str | None' = None) -> 'dict[str, Any]'",
        "section_props": "(self, *, doc: 'Any' = None) -> 'dict[str, Any]'",
        "selection": "(self, *, doc: 'Any' = None) -> 'dict[str, Any]'",
        "undercut_faces": "(self, pull_x: 'float' = 0.0, pull_y: 'float' = 1.0, pull_z: 'float' = 0.0) -> 'dict[str, Any]'",
        "volume": "(self) -> 'dict[str, Any]'",
    },
    "UrdfFacade": {
        "export": "(self, asm_doc: 'Any', output_dir: 'Any', **kwargs: 'Any') -> 'dict[str, Any]'",
    },
}

_CLASSES = {
    "SolidWorksClient": SolidWorksClient,
    "SolidWorksObserverFacade": SolidWorksObserverFacade,
    "SolidWorksMutatorFacade": SolidWorksMutatorFacade,
    "UrdfFacade": UrdfFacade,
    "SolidWorksExportFacade": SolidWorksExportFacade,
    "SolidWorksFeaturesFacade": SolidWorksFeaturesFacade,
}


@pytest.mark.parametrize("cls_name", sorted(_CLASSES))
def test_facade_surface_matches_snapshot(cls_name: str) -> None:
    actual = _surface(_CLASSES[cls_name])
    expected = EXPECTED[cls_name]
    added = set(actual) - set(expected)
    removed = set(expected) - set(actual)
    changed = {
        k: (expected[k], actual[k])
        for k in set(actual) & set(expected)
        if actual[k] != expected[k]
    }
    assert not (added or removed or changed), (
        f"{cls_name} public surface drifted — "
        f"added={sorted(added)} removed={sorted(removed)} changed={changed}. "
        f"If intentional, update EXPECTED in tests/test_facade_surface.py."
    )
