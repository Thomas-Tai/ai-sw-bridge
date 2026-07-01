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


def test_run_doctor_ok_when_only_mcp_registration_unregistered(monkeypatch) -> None:
    # A healthy CLI-only operator (no MCP client registered) must still get
    # a green verdict — mcp_registration is advisory, not required.
    monkeypatch.setattr(doctor, "_check_python_bitness", lambda: _ok("python_bitness"))
    monkeypatch.setattr(doctor, "_check_pywin32", lambda: _ok("pywin32"))
    monkeypatch.setattr(
        doctor, "_check_scripts_on_path", lambda: _ok("scripts_on_path")
    )
    monkeypatch.setattr(
        doctor, "_check_solidworks_seat", lambda: _ok("solidworks_seat")
    )
    monkeypatch.setattr(
        doctor,
        "_check_mcp_registration",
        lambda: {
            "name": "mcp_registration",
            "ok": False,
            "detail": "ai-sw-bridge not found in config",
            "fix": "Run: ai-sw-doctor --register",
            "advisory": True,
        },
    )

    result = doctor.run_doctor()

    assert result["ok"] is True
    assert result["next_steps"] == []


def test_run_doctor_no_probe_ok_when_required_checks_green(monkeypatch) -> None:
    # --no-seat skips the live seat check; that skip is advisory and must
    # not block an otherwise-healthy verdict.
    monkeypatch.setattr(doctor, "_check_python_bitness", lambda: _ok("python_bitness"))
    monkeypatch.setattr(doctor, "_check_pywin32", lambda: _ok("pywin32"))
    monkeypatch.setattr(
        doctor, "_check_scripts_on_path", lambda: _ok("scripts_on_path")
    )
    monkeypatch.setattr(
        doctor, "_check_mcp_registration", lambda: _ok("mcp_registration")
    )

    result = doctor.run_doctor(run_probe=False)

    assert result["ok"] is True
    seat_check = next(c for c in result["checks"] if c["name"] == "solidworks_seat")
    assert seat_check["advisory"] is True
    assert seat_check["ok"] is False


def test_main_register_invokes_registrar(monkeypatch, capsys) -> None:
    calls = {}

    def fake_register(client):
        calls["client"] = client
        return {
            "ok": True,
            "client": client,
            "config_path": "X",
            "changed": True,
            "backup_path": None,
            "entry": {"command": "ai-sw-mcp", "args": []},
        }

    monkeypatch.setattr("ai_sw_bridge.mcp.registration.register", fake_register)
    monkeypatch.setattr("sys.argv", ["ai-sw-doctor", "--register"])

    rc = doctor.main()

    assert rc == 0
    assert calls["client"] == "claude_desktop"
    assert '"command": "ai-sw-mcp"' in capsys.readouterr().out
