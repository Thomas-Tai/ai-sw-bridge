"""Unit tests for ai-sw-doctor: static env checks + probe/registration wrap.

All COM/probe seams are patched on the doctor module namespace so no live
SOLIDWORKS seat is ever touched (mirrors the project's monkeypatch-seam
convention). run_doctor() is a pure aggregator over check functions.
"""

from __future__ import annotations

import ai_sw_bridge.cli.doctor as doctor


def test_run_doctor_reports_all_checks_and_overall_ok(monkeypatch) -> None:
    # Force every check green.
    monkeypatch.setattr(doctor, "_check_python_bitness", lambda: _ok("python_bitness"))
    monkeypatch.setattr(doctor, "_check_pywin32", lambda: _ok("pywin32"))
    monkeypatch.setattr(
        doctor, "_check_scripts_on_path", lambda: _ok("scripts_on_path")
    )
    monkeypatch.setattr(
        doctor, "_check_solidworks_seat", lambda: _ok("solidworks_seat")
    )
    monkeypatch.setattr(
        doctor, "_check_mcp_registration", lambda: _ok("mcp_registration")
    )

    result = doctor.run_doctor()

    assert result["ok"] is True
    names = [c["name"] for c in result["checks"]]
    assert names == [
        "python_bitness",
        "pywin32",
        "scripts_on_path",
        "solidworks_seat",
        "mcp_registration",
    ]
    assert result["next_steps"] == []


def test_run_doctor_overall_false_when_any_check_fails(monkeypatch) -> None:
    monkeypatch.setattr(doctor, "_check_python_bitness", lambda: _ok("python_bitness"))
    monkeypatch.setattr(doctor, "_check_pywin32", lambda: _ok("pywin32"))
    monkeypatch.setattr(
        doctor, "_check_scripts_on_path", lambda: _ok("scripts_on_path")
    )
    monkeypatch.setattr(
        doctor,
        "_check_solidworks_seat",
        lambda: {
            "name": "solidworks_seat",
            "ok": False,
            "detail": "no seat",
            "fix": "Open SOLIDWORKS, then re-run ai-sw-doctor.",
        },
    )
    monkeypatch.setattr(
        doctor, "_check_mcp_registration", lambda: _ok("mcp_registration")
    )

    result = doctor.run_doctor()

    assert result["ok"] is False
    # The failing check's fix is surfaced in next_steps.
    assert any("Open SOLIDWORKS" in step for step in result["next_steps"])


def _ok(name: str) -> dict:
    return {"name": name, "ok": True, "detail": "fine", "fix": None}
