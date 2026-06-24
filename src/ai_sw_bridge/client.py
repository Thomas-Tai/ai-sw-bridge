"""SolidWorksClient — the v0.18 class-based public API boundary.

The commercial-contract entry point. A single stateful client owns the
connection state — the ``ISldWorks`` application pointer and the makepy wrapper
module, plus active-document resolution — and exposes domain facades that share
that one context::

    client = SolidWorksClient()
    client.observe.get_inertia()
    client.observe.analyze_stackup(["a-1", "b-1", "c-1"])
    client.mutate.propose_local_change("width_mm", "30")
    client.urdf.export(asm_doc, "out/")

Taxonomy: *domain objects on a single stateful client* (not a god-client, not
scattered standalone objects). The client owns COM state; each facade is a
namespaced view that delegates to the private ``_*_impl`` cores. The legacy
``sw_*`` free functions remain as ``PendingDeprecationWarning`` shims routing to
the same cores, so existing scripts keep working while this class API becomes
the stable boundary. The stateless v0.14 ``observe.SolidWorksObserver`` is the
precursor this supersedes.

v0.18 pilot slice: ``observe`` (get_inertia, analyze_stackup) + ``urdf`` +
``mutate`` (propose/dry_run/commit local_change + feature_add).
Remaining domains (assembly / drawing / export / features) fan out
behind the same pattern — a series of friction-triggered seams, not a big-bang
(see ``project_consolidation_policy``).
"""

from __future__ import annotations

from typing import Any

from .observe import (
    _sw_get_active_doc_impl,
    _sw_get_feature_errors_impl,
    _sw_get_equations_impl,
    _sw_get_bbox_impl,
    _sw_get_volume_impl,
    _sw_get_feature_statistics_impl,
    _sw_screenshot_impl,
    _sw_get_mate_errors_impl,
    _sw_get_custom_props_impl,
    _sw_measure_impl,
    _sw_undercut_faces_impl,
    _sw_min_wall_thickness_impl,
    _sw_get_enabled_addins_impl,
)
from .observe_bbox import _sw_get_assembly_bbox_from_doc_impl, _sw_get_bbox_from_doc_impl
from .observe_clearance import (
    _sw_analyze_stackup_impl,
    _sw_get_clearance_impl,
    _sw_get_face_clearance_impl,
)
from .observe_draft import _sw_get_draft_analysis_impl
from .observe_import_diag import _sw_get_import_diagnostics_impl
from .observe_inertia import _sw_get_inertia_impl
from .observe_interference import _sw_get_interference_impl
from .observe_measure import (
    _sw_get_measure_angle_from_doc_impl,
    _sw_get_measure_area_from_doc_impl,
    _sw_get_measure_durable_pair_impl,
    _sw_get_measure_from_doc_impl,
)
from .observe_section import _sw_get_section_props_impl
from .observe_selection import _sw_get_selection_impl
from .mutate import (
    _sw_propose_local_change_impl,
    _sw_dry_run_impl,
    _sw_commit_impl,
    _sw_undo_last_commit_impl,
    _sw_propose_feature_add_impl,
    _sw_dry_run_feature_add_impl,
    _sw_commit_feature_add_impl,
    # Batch M2: assembly verbs
    _sw_propose_assembly_impl,
    _sw_dry_run_assembly_impl,
    _sw_commit_assembly_impl,
    _sw_edit_assembly_impl,
    # Batch M3: drawing + properties verbs
    _sw_propose_drawing_impl,
    _sw_dry_run_drawing_impl,
    _sw_commit_drawing_impl,
    _sw_propose_properties_impl,
    _sw_dry_run_properties_impl,
    _sw_commit_properties_impl,
)
from .sw_com import get_active_doc, get_sw_app

_NO_DOC = {"ok": False, "error": "no_active_doc"}


class SolidWorksObserverFacade:
    """Read-only observation facade — routes to the ``_impl`` cores (no warnings)."""

    def __init__(self, client: "SolidWorksClient") -> None:
        self._client = client

    def get_inertia(self, doc: Any = None) -> dict[str, Any]:
        """Inertia tensor / CoM / principal moments of the active (or given) part."""
        doc = doc if doc is not None else self._client.active_doc()
        if doc is None:
            return dict(_NO_DOC)
        return _sw_get_inertia_impl(doc)

    def analyze_stackup(
        self,
        component_names: Any,
        *,
        check_endpoints: bool = True,
        doc: Any = None,
    ) -> dict[str, Any]:
        """Tolerance stack-up / clearance-chain over an ordered component chain (W77)."""
        doc = doc if doc is not None else self._client.active_doc()
        if doc is None:
            return dict(_NO_DOC)
        return _sw_analyze_stackup_impl(
            doc, component_names, check_endpoints=check_endpoints)

    def interference(self, *, doc: Any = None) -> dict[str, Any]:
        """Detect physical interferences in the active (or given) assembly (W27/E4)."""
        doc = doc if doc is not None else self._client.active_doc()
        if doc is None:
            return dict(_NO_DOC)
        return _sw_get_interference_impl(doc)

    def draft_analysis(
        self,
        pull_direction: str,
        min_angle_deg: float = 1.0,
        *,
        doc: Any = None,
    ) -> dict[str, Any]:
        """DFM draft analysis of the active (or given) part (W37)."""
        doc = doc if doc is not None else self._client.active_doc()
        if doc is None:
            return dict(_NO_DOC)
        return _sw_get_draft_analysis_impl(doc, pull_direction, min_angle_deg)

    def section_props(self, *, doc: Any = None) -> dict[str, Any]:
        """Section properties of the pre-selected planar face (W58)."""
        doc = doc if doc is not None else self._client.active_doc()
        if doc is None:
            return dict(_NO_DOC)
        return _sw_get_section_props_impl(doc)

    def selection(self, *, doc: Any = None) -> dict[str, Any]:
        """Read the current selection from the active (or given) document (W43)."""
        doc = doc if doc is not None else self._client.active_doc()
        if doc is None:
            return dict(_NO_DOC)
        return _sw_get_selection_impl(doc)

    def bbox_from_doc(self, *, doc: Any = None) -> dict[str, Any]:
        """Bounding-box of the active (or given) part document (W30)."""
        doc = doc if doc is not None else self._client.active_doc()
        if doc is None:
            return dict(_NO_DOC)
        return _sw_get_bbox_from_doc_impl(doc)

    def assembly_bbox(self, *, doc: Any = None) -> dict[str, Any]:
        """Combined bounding-box of all components in the active (or given) assembly (W52)."""
        doc = doc if doc is not None else self._client.active_doc()
        if doc is None:
            return dict(_NO_DOC)
        return _sw_get_assembly_bbox_from_doc_impl(doc)

    # ── Batch O3: observe_measure + observe_clearance verbs ────────────────

    def measure_selection(self, *, doc: Any = None) -> dict[str, Any]:
        """Measure currently selected entities in the active (or given) document (W30)."""
        doc = doc if doc is not None else self._client.active_doc()
        if doc is None:
            return dict(_NO_DOC)
        return _sw_get_measure_from_doc_impl(doc)

    def measure_durable_pair(
        self,
        durable_ref_a: str,
        durable_ref_b: str,
        *,
        doc: Any = None,
    ) -> dict[str, Any]:
        """Measure between two durable-reference entities in the active (or given) document (W52)."""
        doc = doc if doc is not None else self._client.active_doc()
        if doc is None:
            return dict(_NO_DOC)
        return _sw_get_measure_durable_pair_impl(doc, durable_ref_a, durable_ref_b)

    def measure_angle(self, *, doc: Any = None) -> dict[str, Any]:
        """Measure the angle of currently selected entities in the active (or given) document (W52)."""
        doc = doc if doc is not None else self._client.active_doc()
        if doc is None:
            return dict(_NO_DOC)
        return _sw_get_measure_angle_from_doc_impl(doc)

    def measure_area(self, *, doc: Any = None) -> dict[str, Any]:
        """Measure the area of the currently selected face in the active (or given) document (W52)."""
        doc = doc if doc is not None else self._client.active_doc()
        if doc is None:
            return dict(_NO_DOC)
        return _sw_get_measure_area_from_doc_impl(doc)

    def clearance(
        self,
        comp_a: str,
        comp_b: str,
        *,
        doc: Any = None,
    ) -> dict[str, Any]:
        """Measure minimum distance between two assembly components (W35)."""
        doc = doc if doc is not None else self._client.active_doc()
        if doc is None:
            return dict(_NO_DOC)
        return _sw_get_clearance_impl(doc, comp_a, comp_b)

    def face_clearance(
        self,
        face_a: str,
        face_b: str,
        *,
        doc: Any = None,
    ) -> dict[str, Any]:
        """Measure minimum distance between two named faces (W52)."""
        doc = doc if doc is not None else self._client.active_doc()
        if doc is None:
            return dict(_NO_DOC)
        return _sw_get_face_clearance_impl(doc, face_a, face_b)

    # ── Batch O2: observe.py active-doc verbs ──────────────────────────────

    def active_doc(self) -> dict[str, Any]:
        """Return metadata about the currently active SOLIDWORKS document."""
        return _sw_get_active_doc_impl()

    def feature_errors(self) -> dict[str, Any]:
        """Walk the active document's feature tree and report non-OK features."""
        return _sw_get_feature_errors_impl()

    def equations(self) -> dict[str, Any]:
        """Dump every equation in the active document with its current value and status."""
        return _sw_get_equations_impl()

    def bbox(self) -> dict[str, Any]:
        """Return the active part's axis-aligned bounding box (parts only, legacy form)."""
        return _sw_get_bbox_impl()

    def volume(self) -> dict[str, Any]:
        """Return volume, surface area, mass, and CoM of the active part."""
        return _sw_get_volume_impl()

    def feature_statistics(self) -> dict[str, Any]:
        """Return build-tree statistics for the active part/assembly (W71)."""
        return _sw_get_feature_statistics_impl()

    def import_diagnostics(self) -> dict[str, Any]:
        """Geometric health of the active part — solid/surface body breakdown,
        IBody2.Check3 topology faults (decoded), and the IPartDoc.ImportDiagnosis
        status flag. Read-only; parts only."""
        return _sw_get_import_diagnostics_impl()

    def screenshot(
        self,
        width: int = 640,
        height: int = 360,
        fit_view: bool = False,
        filename: str | None = None,
    ) -> dict[str, Any]:
        """Capture the active SW viewport to a PNG on disk."""
        return _sw_screenshot_impl(width=width, height=height, fit_view=fit_view, filename=filename)

    def mate_errors(self) -> dict[str, Any]:
        """Walk an assembly's mate set and report status per mate."""
        return _sw_get_mate_errors_impl()

    def custom_props(self) -> dict[str, Any]:
        """Read every custom property from the active document."""
        return _sw_get_custom_props_impl()

    def measure(
        self,
        entity_a: str | None = None,
        entity_b: str | None = None,
    ) -> dict[str, Any]:
        """Measure entities in the active document."""
        return _sw_measure_impl(entity_a=entity_a, entity_b=entity_b)

    def undercut_faces(
        self,
        pull_x: float = 0.0,
        pull_y: float = 1.0,
        pull_z: float = 0.0,
    ) -> dict[str, Any]:
        """Report faces that block tool/mold withdrawal along a pull direction (DFM)."""
        return _sw_undercut_faces_impl(pull_x=pull_x, pull_y=pull_y, pull_z=pull_z)

    def min_wall_thickness(self, samples_per_face: int = 4) -> dict[str, Any]:
        """Report the minimum wall thickness of the active solid part (DFM)."""
        return _sw_min_wall_thickness_impl(samples_per_face=samples_per_face)

    def enabled_addins(self) -> dict[str, Any]:
        """Enumerate currently-loaded SOLIDWORKS add-ins (W7.1)."""
        return _sw_get_enabled_addins_impl()


class UrdfFacade:
    """URDF export facade — assembly → ROS robot model (W78)."""

    def __init__(self, client: "SolidWorksClient") -> None:
        self._client = client

    def export(self, asm_doc: Any, output_dir: Any, **kwargs: Any) -> dict[str, Any]:
        """Export *asm_doc* to a URDF package under *output_dir*.

        Threads the client's wrapper module so the orchestrator's internal
        mass-props reads use the shared ``_impl`` cores (no deprecation noise).
        """
        from .export_urdf import export_urdf

        kwargs.setdefault("mod", self._client.mod)
        return export_urdf(asm_doc, output_dir, **kwargs)


class SolidWorksExportFacade:
    """Export facade — wraps the ``export.export_all`` orchestrator.

    Facade-only (no ``sw_*`` free function, no shim): ``export_all`` is already
    the public dispatch entry. The internal build pipeline and URDF export route
    file output through here so ``SolidWorksClient`` is the single export seam.
    """

    def __init__(self, client: "SolidWorksClient") -> None:
        self._client = client

    def run(self, doc: Any, requests: Any, part_name: str) -> Any:
        """Export *doc* in every requested format; returns ``list[ExportResult]``.

        The import is lazy so the ``client`` ↔ ``export_urdf`` cycle never forms
        at module load (``export_urdf`` routes back through this facade).
        """
        from .export import export_all

        return export_all(doc, requests, part_name)


class SolidWorksFeaturesFacade:
    """Read-only introspection over the feature ``HANDLER_REGISTRY``.

    Discovery surface — *which* seat-proven feature kinds the current build
    advertises — for consumers deciding what to dispatch. The write path stays
    on :meth:`SolidWorksClient.mutate.propose_feature_add`; it is NOT duplicated
    here, preserving the read/write boundary.
    """

    def list_kinds(self) -> list[str]:
        """Sorted list of registered (seat-proven GREEN) feature kinds."""
        from .features import HANDLER_REGISTRY

        return sorted(HANDLER_REGISTRY)

    def supports(self, kind: str) -> bool:
        """True iff *kind* is a registered feature handler."""
        from .features import HANDLER_REGISTRY

        return kind in HANDLER_REGISTRY


class SolidWorksMutatorFacade:
    """Mutation facade — Propose-Approve-Execute transaction lifecycle (v0.18).

    Routes to the ``_impl`` cores directly (no deprecation warnings). The
    proposal store is module-level, stateless, disk-backed; this facade
    holds zero transaction state — the ``proposal_id`` string is the only
    handle.
    """

    def __init__(self, client: "SolidWorksClient") -> None:
        self._client = client

    def propose_local_change(self, var: str, new_value: str) -> dict[str, Any]:
        """Stage a change to a single variable in the linked *_locals.txt file."""
        return _sw_propose_local_change_impl(var=var, new_value=new_value)

    def dry_run(self, proposal_id: str) -> dict[str, Any]:
        """Apply a proposed change, force-rebuild, capture state, roll back."""
        return _sw_dry_run_impl(proposal_id=proposal_id)

    def commit(self, proposal_id: str) -> dict[str, Any]:
        """Re-apply a proposal that passed dry-run, save the SW document."""
        return _sw_commit_impl(proposal_id=proposal_id)

    def undo_last_commit(self) -> dict[str, Any]:
        """Revert the most recently committed proposal."""
        return _sw_undo_last_commit_impl()

    def propose_feature_add(
        self, doc_path: str, feature: dict, target: dict
    ) -> dict[str, Any]:
        """Stage a feature-add proposal — no SW state is modified yet."""
        return _sw_propose_feature_add_impl(
            doc_path=doc_path, feature=feature, target=target
        )

    def dry_run_feature_add(self, proposal_id: str) -> dict[str, Any]:
        """Apply a feature-add proposal, rebuild, close without saving."""
        return _sw_dry_run_feature_add_impl(proposal_id=proposal_id)

    def commit_feature_add(self, proposal_id: str) -> dict[str, Any]:
        """Re-run a dry-run-ok feature-add and save the SW document."""
        return _sw_commit_feature_add_impl(proposal_id=proposal_id)

    # ── Batch M2: assembly verbs ─────────────────────────────────────────

    def propose_assembly(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Stage an assembly proposal — validate offline; no SW state touched."""
        return _sw_propose_assembly_impl(spec=spec)

    def dry_run_assembly(self, proposal_id: str) -> dict[str, Any]:
        """Dry-run an assembly proposal — validate bindings without mutating SW."""
        return _sw_dry_run_assembly_impl(proposal_id=proposal_id)

    def commit_assembly(
        self,
        proposal_id: str,
        output_path: str,
        *,
        part_paths: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Build the assembly — place components, create mates, save."""
        return _sw_commit_assembly_impl(
            proposal_id=proposal_id, output_path=output_path, part_paths=part_paths
        )

    def edit_assembly(
        self, manifest_path: str, op: dict[str, Any]
    ) -> dict[str, Any]:
        """Edit an assembly via its manifest sidecar."""
        return _sw_edit_assembly_impl(manifest_path=manifest_path, op=op)

    # ── Batch M3: drawing + properties verbs ─────────────────────────────

    def propose_drawing(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Stage a drawing proposal — validate offline; no SW state touched."""
        return _sw_propose_drawing_impl(spec=spec)

    def dry_run_drawing(self, proposal_id: str) -> dict[str, Any]:
        """Dry-run a drawing proposal — confirm model file exists."""
        return _sw_dry_run_drawing_impl(proposal_id=proposal_id)

    def commit_drawing(
        self,
        proposal_id: str,
        output_path: str,
    ) -> dict[str, Any]:
        """Build the drawing — create views, save .SLDDRW."""
        return _sw_commit_drawing_impl(proposal_id=proposal_id, output_path=output_path)

    def propose_properties(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Stage a properties proposal — validate offline; no SW state touched."""
        return _sw_propose_properties_impl(spec=spec)

    def dry_run_properties(self, proposal_id: str) -> dict[str, Any]:
        """Dry-run a properties proposal — confirm model file exists."""
        return _sw_dry_run_properties_impl(proposal_id=proposal_id)

    def commit_properties(self, proposal_id: str) -> dict[str, Any]:
        """Commit a properties proposal — set custom properties on the model."""
        return _sw_commit_properties_impl(proposal_id=proposal_id)


class SolidWorksClient:
    """Stateful owner of the SOLIDWORKS connection; root of the class-based API.

    Connection state (app pointer + wrapper module) is acquired lazily so the
    client can be constructed cheaply / in tests, and injected explicitly
    (``app=``, ``mod=``) when a caller already holds them — e.g. a CLI entry that
    opened a document, or the MCP ComExecutor STA worker.
    """

    def __init__(self, *, app: Any = None, mod: Any = None) -> None:
        self._app = app
        self._mod = mod
        self._observe: SolidWorksObserverFacade | None = None
        self._urdf: UrdfFacade | None = None
        self._mutate: SolidWorksMutatorFacade | None = None
        self._export: SolidWorksExportFacade | None = None
        self._features: SolidWorksFeaturesFacade | None = None

    # ── connection state ────────────────────────────────────────────────
    @property
    def app(self) -> Any:
        """The ``ISldWorks`` application pointer (acquired on first use)."""
        if self._app is None:
            self._app = get_sw_app()
        return self._app

    @property
    def mod(self) -> Any:
        """The makepy wrapper module used by ``typed()`` (acquired on first use)."""
        if self._mod is None:
            from .com.sw_type_info import wrapper_module
            self._mod = wrapper_module()
        return self._mod

    def active_doc(self) -> Any:
        """Resolve the active ``IModelDoc2`` (or ``None`` if no document is open)."""
        return get_active_doc(self.app)

    # ── domain facades (cached) ─────────────────────────────────────────
    @property
    def observe(self) -> SolidWorksObserverFacade:
        if self._observe is None:
            self._observe = SolidWorksObserverFacade(self)
        return self._observe

    @property
    def urdf(self) -> UrdfFacade:
        if self._urdf is None:
            self._urdf = UrdfFacade(self)
        return self._urdf

    @property
    def export(self) -> SolidWorksExportFacade:
        if self._export is None:
            self._export = SolidWorksExportFacade(self)
        return self._export

    @property
    def features(self) -> SolidWorksFeaturesFacade:
        if self._features is None:
            self._features = SolidWorksFeaturesFacade()
        return self._features

    @property
    def mutate(self) -> SolidWorksMutatorFacade:
        if self._mutate is None:
            self._mutate = SolidWorksMutatorFacade(self)
        return self._mutate
