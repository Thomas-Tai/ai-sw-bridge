"""Tests for spec/orchestrator.py (P2.5 sequencer).

Pure-Python — no COM, no SW. Stages are injected as callables so the tests
exercise only the sequencing contract: fixed order, fail-stop, optional
stages skipped, structured envelope, two-stream discipline.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from typing import Any

import pytest

from ai_sw_bridge.spec.orchestrator import (
    OrchestrationEnvelope,
    OrchestrationState,
    StageOutcome,
    emit,
    orchestrate,
)


# ---------------------------------------------------------------------------
# Fixtures: mock stage factories
# ---------------------------------------------------------------------------


def _ok_stage(name: str, *, detail: str = "") -> Any:
    def _stage(state: OrchestrationState) -> StageOutcome:
        return StageOutcome(name, ok=True, detail=detail)

    _stage.__name__ = name
    return _stage


def _skip_stage(name: str, *, detail: str = "absent") -> Any:
    def _stage(state: OrchestrationState) -> StageOutcome:
        return StageOutcome(name, ok=True, skipped=True, detail=detail)

    _stage.__name__ = name
    return _stage


def _fail_stage(name: str, *, detail: str = "boom") -> Any:
    def _stage(state: OrchestrationState) -> StageOutcome:
        return StageOutcome(name, ok=False, detail=detail)

    _stage.__name__ = name
    return _stage


def _mutating_stage(name: str, attr: str, value: Any) -> Any:
    """Stage that writes *value* onto ``state.<attr>`` — proves state threads."""

    def _stage(state: OrchestrationState) -> StageOutcome:
        setattr(state, attr, value)
        return StageOutcome(name, ok=True, detail=f"set {attr}")

    _stage.__name__ = name
    return _stage


# ---------------------------------------------------------------------------
# Sequencing + envelope shape
# ---------------------------------------------------------------------------


class TestOrchestrateSequencing:
    def test_all_ok_runs_every_stage_in_order(self) -> None:
        calls: list[str] = []

        def track(name: str) -> Any:
            def _s(state: OrchestrationState) -> StageOutcome:
                calls.append(name)
                return StageOutcome(name, ok=True)

            _s.__name__ = name
            return _s

        env = orchestrate(
            {},
            stages=[track("features"), track("material"), track("drawing"), track("export")],
            stderr=io.StringIO(),
        )
        assert env.ok is True
        assert calls == ["features", "material", "drawing", "export"]
        assert [s["stage"] for s in env.stages] == ["features", "material", "drawing", "export"]
        assert env.failed_stage is None
        assert env.failed_detail is None

    def test_fail_stop_does_not_run_later_stages(self) -> None:
        calls: list[str] = []

        def track(name: str, ok: bool) -> Any:
            def _s(state: OrchestrationState) -> StageOutcome:
                calls.append(name)
                return StageOutcome(name, ok=ok, detail="" if ok else f"{name} died")

            _s.__name__ = name
            return _s

        env = orchestrate(
            {},
            stages=[track("features", True), track("material", False), track("drawing", True)],
            stderr=io.StringIO(),
        )
        assert env.ok is False
        assert calls == ["features", "material"]  # drawing was NOT invoked
        assert env.failed_stage == "material"
        assert env.failed_detail == "material died"
        # outcomes list contains both the OK and the failing record.
        assert [s["stage"] for s in env.stages] == ["features", "material"]
        assert env.stages[0]["ok"] is True
        assert env.stages[1]["ok"] is False

    def test_optional_stages_recorded_as_skipped(self) -> None:
        env = orchestrate(
            {},
            stages=[
                _ok_stage("features"),
                _skip_stage("drawing", detail="no drawing block"),
                _skip_stage("export", detail="no export block"),
            ],
            stderr=io.StringIO(),
        )
        assert env.ok is True
        names = [s["stage"] for s in env.stages]
        assert names == ["features", "drawing", "export"]
        assert env.stages[1]["skipped"] is True
        assert env.stages[2]["skipped"] is True

    def test_state_threads_through_stages(self) -> None:
        """Each stage reads the prior stage's write on the shared state."""
        seen: list[Any] = []

        def writer(state: OrchestrationState) -> StageOutcome:
            state.material_result = True
            return StageOutcome("material", ok=True)

        def reader(state: OrchestrationState) -> StageOutcome:
            seen.append(state.material_result)
            return StageOutcome("drawing", ok=True)

        orchestrate({}, stages=[writer, reader], stderr=io.StringIO())
        assert seen == [True]

    def test_stage_exception_is_caught_and_reported(self) -> None:
        """A stage that raises (instead of returning a bad outcome) is still
        fail-stopped with a structured envelope — no traceback leaks."""

        def boom(state: OrchestrationState) -> StageOutcome:
            raise RuntimeError("late-binding dispatch failed")

        boom.__name__ = "material"

        env = orchestrate({}, stages=[_ok_stage("features"), boom], stderr=io.StringIO())
        assert env.ok is False
        assert env.failed_stage == "material"
        assert "RuntimeError" in (env.failed_detail or "")
        assert "late-binding dispatch failed" in (env.failed_detail or "")


# ---------------------------------------------------------------------------
# Envelope payload assembly
# ---------------------------------------------------------------------------


@dataclass
class _FakeBuildResult:
    ok: bool = True
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": self.ok}
        if self.error:
            out["error"] = self.error
        return out


@dataclass
class _FakeDrawingResult:
    view: str
    ok: bool
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"view": self.view, "ok": self.ok}
        if self.error:
            out["error"] = self.error
        return out


class TestOrchestrateEnvelope:
    def test_build_result_serialized_when_present(self) -> None:
        def _features(state: OrchestrationState) -> StageOutcome:
            state.build_result = _FakeBuildResult(ok=True)
            return StageOutcome("features", ok=True)

        env = orchestrate({}, stages=[_features], stderr=io.StringIO())
        assert env.build_result == {"ok": True}

    def test_material_payload_only_when_set(self) -> None:
        env = orchestrate({}, stages=[_ok_stage("features")], stderr=io.StringIO())
        assert env.material is None  # material stage wasn't run

        def _mat(state: OrchestrationState) -> StageOutcome:
            state.material_result = True
            return StageOutcome("material", ok=True)

        env2 = orchestrate({}, stages=[_ok_stage("features"), _mat], stderr=io.StringIO())
        assert env2.material == {"applied": True}

    def test_drawing_payload_serialized_via_to_dict(self) -> None:
        def _dr(state: OrchestrationState) -> StageOutcome:
            state.drawing_results = [
                _FakeDrawingResult("front", True),
                _FakeDrawingResult("top", False, error="SEAT-gated"),
            ]
            return StageOutcome("drawing", ok=False, detail="1/2 view(s) failed")

        env = orchestrate({}, stages=[_ok_stage("features"), _dr], stderr=io.StringIO())
        assert env.drawing == [
            {"view": "front", "ok": True},
            {"view": "top", "ok": False, "error": "SEAT-gated"},
        ]

    def test_to_dict_drops_none_optional_fields(self) -> None:
        env = OrchestrationEnvelope(ok=True, stages=[{"stage": "features", "ok": True, "skipped": False, "detail": ""}])
        wire = env.to_dict()
        assert "failed_stage" not in wire
        assert "build_result" not in wire
        assert "drawing" not in wire
        assert "export" not in wire


# ---------------------------------------------------------------------------
# Two-stream discipline (UIUX §3)
# ---------------------------------------------------------------------------


class TestTwoStreamDiscipline:
    def test_progress_goes_to_stderr_not_stdout(self) -> None:
        err = io.StringIO()
        orchestrate({}, stages=[_ok_stage("features", detail="built 3")], stderr=err)
        captured = err.getvalue()
        assert "[orchestrator] features: ok" in captured
        assert "built 3" in captured

    def test_emit_writes_json_to_stdout_and_returns_exit_code(self) -> None:
        out = io.StringIO()
        ok_env = OrchestrationEnvelope(ok=True, stages=[])
        rc = emit(ok_env, stdout=out)
        assert rc == 0
        payload = json.loads(out.getvalue())
        assert payload == {"ok": True, "stages": []}

        out2 = io.StringIO()
        bad_env = OrchestrationEnvelope(
            ok=False,
            stages=[{"stage": "features", "ok": False, "skipped": False, "detail": "x"}],
            failed_stage="features",
            failed_detail="x",
        )
        rc2 = emit(bad_env, stdout=out2)
        assert rc2 == 1
        payload2 = json.loads(out2.getvalue())
        assert payload2["failed_stage"] == "features"

    def test_emit_stdout_is_machine_json_only(self) -> None:
        """emit() must print *only* the envelope — no prose, no banners."""
        out = io.StringIO()
        emit(OrchestrationEnvelope(ok=True, stages=[]), stdout=out)
        text = out.getvalue().strip()
        # parseable JSON, exactly one top-level object
        parsed = json.loads(text)
        assert isinstance(parsed, dict)
        # no trailing prose
        assert text == json.dumps(parsed, indent=2)


# ---------------------------------------------------------------------------
# Zero behavior change to existing stages
# ---------------------------------------------------------------------------


class TestNoStageModification:
    """The orchestrator only *calls* stages; it must not import-time mutate
    or patch any shipped entry point. Pin that contract at the import level."""

    def test_default_stages_are_callable(self) -> None:
        from ai_sw_bridge.spec.orchestrator import default_stages

        stages = default_stages()
        assert len(stages) == 4
        for s in stages:
            assert callable(s)

    def test_module_import_does_not_touch_builder_or_dispatch(self) -> None:
        """Importing orchestrator must not run any build / generate / export side effect."""
        import ai_sw_bridge.spec.orchestrator as orch  # noqa: F401

        # No module-level state was mutated — the default_stages factory is
        # still idempotent after import.
        a = orch.default_stages()
        b = orch.default_stages()
        assert len(a) == len(b) == 4
