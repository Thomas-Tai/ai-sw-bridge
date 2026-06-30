"""ai-sw-build maps an unreadable spec file to a clean exit-2 JSON error.

Review follow-up: a spec file that exists but cannot be decoded (a non-UTF-8
file, or an OSError such as a permission/IO failure) used to escape the
``json.JSONDecodeError``-only ``try`` as an uncaught traceback. The doc
contract says exit 2 = "missing or malformed-JSON spec file"; this test pins
that an unreadable file degrades to the same clean exit-2 JSON envelope rather
than crashing.
"""

from __future__ import annotations

import json

from ai_sw_bridge.cli import build as build_cli


def test_non_utf8_spec_file_exits_2(tmp_path, capsys, monkeypatch) -> None:
    bad = tmp_path / "bad.json"
    # 0xFF is an invalid UTF-8 start byte -> read_text(encoding="utf-8") raises
    # UnicodeDecodeError (the OSError branch is the same except clause).
    bad.write_bytes(b"\xff\xfe not utf-8 \x00")
    monkeypatch.setattr("sys.argv", ["ai-sw-build", str(bad)])

    rc = build_cli.main()

    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "could not be read" in payload["error"]
    assert payload["spec_path"] == str(bad)
