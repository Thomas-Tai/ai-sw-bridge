"""Schema-v2 thin orchestrator — stage sequencer (spec.md §P2.5 / FR-2).

A schema-v2 spec runs as ordered stages::

    features -> material -> [drawing] -> [export]

Each mutating stage preserves propose->approve->execute (invariant #1). This
module is a *sequencer over existing builders* — it does not reimplement any
stage, it does not invent a new auto-approve, and it does not bypass any
stage's own PAE / dry-run gate. It threads one state object through the
chain, fails stop on the first stage error, and reports which stage failed
via a structured envelope.

Two-stream discipline (UIUX §3): machine-readable envelope -> stdout via
:func:`print(json.dumps(...))`; prose progress -> stderr via ``print(...,
file=sys.stderr)``. Mirrors the pattern in ``cli/build.py``,
``drawing/dispatch.py``, ``export/dispatch.py``.

Optional stages (drawing, export) are **skipped and recorded** when their
spec block is absent — never an error. The drawing block is forwarded to
``drawing.generate_all``; if a sub-view is SEAT-gated or unshipped, the
per-view failure is captured in ``DrawingResult`` without aborting the rest.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Protocol


@dataclass
class OrchestrationState:
    """Thread-through state for the stage chain.

    ``doc`` is the live COM doc handle that stages which need one (material,
    drawing, export) read from. ``part_path`` is the on-disk path of the part
    being built — drawing uses it for view references, export for the source
    file. ``spec`` is the validated schema-v2 dict. ``build_result`` is
    populated by the features stage; ``material_result``, ``drawing_results``,
    and ``export_results`` are populated by their respective stages.
    """

    spec: dict[str, Any]
    doc: Any = None
    part_path: str = ""
    build_result: Any = None
    material_result: Optional[bool] = None
    drawing_results: list[Any] = field(default_factory=list)
    export_results: list[Any] = field(default_factory=list)


@dataclass(frozen=True)
class StageOutcome:
    """One stage's verdict — the unit the sequencer reasons about."""

    stage: str
    ok: bool
    skipped: bool = False
    detail: str = ""


class Stage(Protocol):
    """Stage protocol: ``state -> StageOutcome``.

    Implementations are free to mutate ``state`` in place (that's how results
    propagate forward) but must return a non-None :class:`StageOutcome` so the
    sequencer can decide whether to continue.
    """

    def __call__(self, state: OrchestrationState) -> StageOutcome: ...


# ---------------------------------------------------------------------------
# Default stage runners — thin wrappers over the shipped entry points.
#
# Each is a standalone function so tests can monkeypatch or inject an
# alternative callable. They never raise into the sequencer: any exception
# is caught and surfaced as ``StageOutcome(ok=False, detail=...)`` so the
# chain fail-stops cleanly with a structured envelope instead of a traceback.
# ---------------------------------------------------------------------------


def _run_features(state: OrchestrationState, **build_kwargs: Any) -> StageOutcome:
    """Stage 1: feature loop via :func:`spec.builder.build`."""
    from .builder import build

    try:
        state.build_result = build(state.spec, **build_kwargs)
    except Exception as exc:  # noqa: BLE001
        return StageOutcome("features", ok=False, detail=f"{type(exc).__name__}: {exc}")
    br = state.build_result
    ok = bool(getattr(br, "ok", False))
    detail = "" if ok else str(getattr(br, "error", "unknown build error"))
    return StageOutcome("features", ok=ok, detail=detail)


def _run_material(state: OrchestrationState) -> StageOutcome:
    """Stage 2: material custom-property write via :func:`material.apply_material`."""
    from ..material import apply_material

    try:
        result = apply_material(state.doc, state.spec)
    except Exception as exc:  # noqa: BLE001
        return StageOutcome("material", ok=False, detail=f"{type(exc).__name__}: {exc}")
    state.material_result = result
    if result is None:
        return StageOutcome("material", ok=True, skipped=True, detail="no material in spec")
    if result is True:
        return StageOutcome("material", ok=True, detail="material applied")
    return StageOutcome("material", ok=False, detail="material write failed")


def _parse_drawing_requests(block: dict[str, Any]) -> list[Any]:
    """Turn the spec's ``drawing`` block into a list of :class:`DrawingRequest`."""
    from ..drawing import DrawingRequest

    views = block.get("views") if isinstance(block, dict) else None
    if not isinstance(views, list):
        return []
    out: list[Any] = []
    for entry in views:
        if not isinstance(entry, dict):
            continue
        out.append(
            DrawingRequest(
                view=str(entry.get("view", "")),
                x=entry.get("x"),
                y=entry.get("y"),
            )
        )
    return out


def _run_drawing(state: OrchestrationState) -> StageOutcome:
    """Stage 3 (optional): drawing views via :func:`drawing.generate_all`."""
    block = state.spec.get("drawing") if isinstance(state.spec, dict) else None
    if not block:
        return StageOutcome("drawing", ok=True, skipped=True, detail="no drawing block")
    from ..drawing import generate_all

    requests = _parse_drawing_requests(block)
    try:
        results = generate_all(state.doc, requests, state.part_path)
    except Exception as exc:  # noqa: BLE001
        return StageOutcome("drawing", ok=False, detail=f"{type(exc).__name__}: {exc}")
    state.drawing_results = list(results) if results else []
    failed = [r for r in state.drawing_results if not getattr(r, "ok", True)]
    if failed:
        return StageOutcome(
            "drawing",
            ok=False,
            detail=f"{len(failed)}/{len(state.drawing_results)} view(s) failed",
        )
    return StageOutcome("drawing", ok=True, detail=f"{len(state.drawing_results)} view(s) placed")


def _parse_export_requests(block: list[Any]) -> list[Any]:
    """Turn the spec's ``export`` array into a list of :class:`ExportRequest`."""
    from ..export import ExportRequest

    out: list[Any] = []
    for entry in block:
        if not isinstance(entry, dict):
            continue
        fmt = entry.get("format")
        if not fmt:
            continue
        out_dir = entry.get("output_dir")
        sheets = entry.get("sheets", "all")
        out.append(
            ExportRequest(
                format=str(fmt),
                output_dir=Path(out_dir) if out_dir else Path("."),
                filename=entry.get("filename"),
                sheets=sheets,
            )
        )
    return out


def _run_export(state: OrchestrationState) -> StageOutcome:
    """Stage 4 (optional): export via :func:`export.export_all`."""
    block = state.spec.get("export") if isinstance(state.spec, dict) else None
    if not block:
        return StageOutcome("export", ok=True, skipped=True, detail="no export block")
    from ..client import SolidWorksClient

    requests = _parse_export_requests(block)
    part_name = Path(state.part_path).stem if state.part_path else state.spec.get("name", "part")
    try:
        results = SolidWorksClient().export.run(state.doc, requests, str(part_name))
    except Exception as exc:  # noqa: BLE001
        return StageOutcome("export", ok=False, detail=f"{type(exc).__name__}: {exc}")
    state.export_results = list(results) if results else []
    failed = [r for r in state.export_results if not getattr(r, "ok", True)]
    if failed:
        return StageOutcome(
            "export",
            ok=False,
            detail=f"{len(failed)}/{len(state.export_results)} export(s) failed",
        )
    return StageOutcome("export", ok=True, detail=f"{len(state.export_results)} export(s) written")


def default_stages(**build_kwargs: Any) -> list[Stage]:
    """The shipped stage chain, in order.

    ``build_kwargs`` are forwarded to :func:`spec.builder.build` (no_dim,
    deferred_dim, save_as, checkpoint, strict, ...). Tests inject a custom
    chain via :func:`orchestrate`'s ``stages=`` override.
    """

    def _features(state: OrchestrationState) -> StageOutcome:
        return _run_features(state, **build_kwargs)

    return [_features, _run_material, _run_drawing, _run_export]


# ---------------------------------------------------------------------------
# Sequencer + envelope
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OrchestrationEnvelope:
    """Machine-JSON envelope emitted to stdout after the stage chain runs.

    Shape mirrors ``BuildResult.to_dict()``'s conventions: ``ok`` at the top
    level, ``failed_stage`` / ``failed_detail`` only when a stage failed,
    ``stages`` records every outcome in order (including skipped optionals).
    """

    ok: bool
    stages: list[dict[str, Any]]
    failed_stage: Optional[str] = None
    failed_detail: Optional[str] = None
    build_result: Optional[dict[str, Any]] = None
    material: Optional[dict[str, Any]] = None
    drawing: Optional[list[dict[str, Any]]] = None
    export: Optional[list[dict[str, Any]]] = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": self.ok, "stages": self.stages}
        if self.failed_stage is not None:
            out["failed_stage"] = self.failed_stage
        if self.failed_detail is not None:
            out["failed_detail"] = self.failed_detail
        if self.build_result is not None:
            out["build_result"] = self.build_result
        if self.material is not None:
            out["material"] = self.material
        if self.drawing is not None:
            out["drawing"] = self.drawing
        if self.export is not None:
            out["export"] = self.export
        return out


def orchestrate(
    spec: dict[str, Any],
    *,
    doc: Any = None,
    part_path: str = "",
    stages: Optional[list[Stage]] = None,
    stderr: Any = None,
) -> OrchestrationEnvelope:
    """Sequence the stage chain over *spec*.

    * ``stages`` overrides :func:`default_stages` for tests / adapters; default
      wires the shipped entry points.
    * On any stage failure, the chain stops and the envelope carries
      ``failed_stage`` + ``failed_detail``; subsequent stages are NOT run.
    * Optional stages absent from the spec are recorded as ``skipped=true``
      in ``stages`` and the chain continues.
    * Prose progress lines go to *stderr* (default ``sys.stderr``); the
      returned envelope is the machine payload the caller prints to stdout.
    """
    out_stream = stderr if stderr is not None else sys.stderr
    state = OrchestrationState(spec=spec, doc=doc, part_path=part_path)
    chain: list[Stage] = list(stages) if stages is not None else default_stages()

    outcomes: list[StageOutcome] = []
    failed: Optional[StageOutcome] = None
    for stage in chain:
        try:
            outcome = stage(state)
        except Exception as exc:  # noqa: BLE001
            outcome = StageOutcome(
                stage=getattr(stage, "__name__", "unknown"),
                ok=False,
                detail=f"{type(exc).__name__}: {exc}",
            )
        outcomes.append(outcome)
        try:
            print(
                f"[orchestrator] {outcome.stage}: "
                f"{'skip' if outcome.skipped else ('ok' if outcome.ok else 'FAIL')}"
                + (f" ({outcome.detail})" if outcome.detail else ""),
                file=out_stream,
            )
        except Exception:  # noqa: BLE001
            pass
        if not outcome.ok:
            failed = outcome
            break

    stages_wire = [
        {
            "stage": o.stage,
            "ok": o.ok,
            "skipped": o.skipped,
            "detail": o.detail,
        }
        for o in outcomes
    ]

    build_payload: Optional[dict[str, Any]] = None
    if state.build_result is not None and hasattr(state.build_result, "to_dict"):
        try:
            build_payload = state.build_result.to_dict()
        except Exception:  # noqa: BLE001
            build_payload = None

    material_payload: Optional[dict[str, Any]] = None
    if state.material_result is not None:
        material_payload = {"applied": state.material_result}

    drawing_payload: Optional[list[dict[str, Any]]] = None
    if state.drawing_results:
        drawing_payload = [
            r.to_dict() if hasattr(r, "to_dict") else {"view": getattr(r, "view", ""), "ok": bool(getattr(r, "ok", False))}
            for r in state.drawing_results
        ]

    export_payload: Optional[list[dict[str, Any]]] = None
    if state.export_results:
        export_payload = [
            r.to_dict() if hasattr(r, "to_dict") else {"format": getattr(r, "format", ""), "ok": bool(getattr(r, "ok", False))}
            for r in state.export_results
        ]

    return OrchestrationEnvelope(
        ok=failed is None,
        stages=stages_wire,
        failed_stage=failed.stage if failed else None,
        failed_detail=failed.detail if failed else None,
        build_result=build_payload,
        material=material_payload,
        drawing=drawing_payload,
        export=export_payload,
    )


def emit(envelope: OrchestrationEnvelope, *, stdout: Any = None) -> int:
    """Print the envelope as JSON to *stdout* (default ``sys.stdout``).

    Returns the conventional exit code: 0 on ``ok=True``, 1 otherwise.
    Kept as a thin helper so callers mirror the ``cli/build.py::_emit`` shape
    exactly; the orchestrator itself is stdout-free (UIUX §3 — sequencing is
    silent, only the envelope is machine-emitted).
    """
    out = stdout if stdout is not None else sys.stdout
    print(json.dumps(envelope.to_dict(), indent=2), file=out)
    return 0 if envelope.ok else 1


__all__ = [
    "OrchestrationEnvelope",
    "OrchestrationState",
    "Stage",
    "StageOutcome",
    "default_stages",
    "emit",
    "orchestrate",
]
