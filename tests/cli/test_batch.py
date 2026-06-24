"""Tests for the ai-sw-batch CLI — the human-gated batch-commit ceremony.

The CLI routes through ``SolidWorksClient().mutate.batch`` → the facade's
``_sw_batch_feature_add_impl`` core, so that impl is the patch seam (mirroring the
ai-sw-properties test idiom). The ``[y/N]`` gate reads ``builtins.input``.

Crux assertions: the 'y'/--yes paths FIRE the engine (dry_run defaults False = a
real commit); the 'N'/EOF paths BYPASS it entirely (no COM, clean exit 0).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from ai_sw_bridge.cli import batch as cli_batch

_IMPL = "ai_sw_bridge.client._sw_batch_feature_add_impl"

_PROPS = [
    {"feature": {"type": "ref_plane", "distance_mm": 25.0},
     "target": {"plane": "Front Plane"}},
    {"feature": {"type": "com_point"}, "target": {"x": 0}},
]

_GREEN_MANIFEST = {
    "ok": True, "total": 2, "attempted": 2, "committed_count": 2,
    "doc_saved": True, "halted_at": None, "strict": False, "dry_run": False,
    "committed": [
        {"index": 0, "kind": "ref_plane", "note": "n0"},
        {"index": 1, "kind": "com_point", "note": "n1"},
    ],
    "fault": None, "skipped": [], "error": None,
}

_FAULT_MANIFEST = {
    "ok": False, "total": 3, "attempted": 2, "committed_count": 1,
    "doc_saved": True, "halted_at": 1, "strict": False, "dry_run": False,
    "committed": [{"index": 0, "kind": "ref_plane", "note": "n0"}],
    "fault": {"index": 1, "kind": "scale", "stage": "apply",
              "error": "no solid", "feature": {}, "target": {}},
    "skipped": [{"index": 2, "kind": "com_point"}],
    "error": "batch halted at 1/3 (scale): no solid",
}


def _props_file(tmp_path: Path, data=None) -> str:
    p = tmp_path / "proposals.json"
    p.write_text(json.dumps(_PROPS if data is None else data), encoding="utf-8")
    return str(p)


def _stdout_json(capsys) -> dict:
    out = capsys.readouterr().out
    return json.loads(out)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def test_parser_wires_args():
    parser = cli_batch._build_parser()
    args = parser.parse_args(["part.sldprt", "p.json", "--strict", "--yes"])
    assert args.file_path == "part.sldprt"
    assert args.proposals == "p.json"
    assert args.strict is True and args.yes is True


# ---------------------------------------------------------------------------
# Approve path ('y' / --yes) — fires the engine (real commit)
# ---------------------------------------------------------------------------

class TestApprove:
    def test_y_commits(self, tmp_path, monkeypatch, capsys):
        pf = _props_file(tmp_path)
        monkeypatch.setattr("builtins.input", lambda *_: "y")
        with patch(_IMPL, return_value=dict(_GREEN_MANIFEST)) as m:
            rc = cli_batch.main(["part.sldprt", pf])
        m.assert_called_once_with(
            doc_path="part.sldprt", proposals=_PROPS, strict=False
        )
        assert rc == 0
        assert _stdout_json(capsys)["ok"] is True

    def test_yes_flag_skips_prompt(self, tmp_path, capsys):
        pf = _props_file(tmp_path)

        def _boom(*_a, **_k):
            raise AssertionError("input must not be called with --yes")

        with patch("builtins.input", _boom), patch(
            _IMPL, return_value=dict(_GREEN_MANIFEST)
        ) as m:
            rc = cli_batch.main(["part.sldprt", pf, "--yes"])
        assert rc == 0 and m.called

    def test_strict_flag_threads_through(self, tmp_path, capsys):
        pf = _props_file(tmp_path)
        with patch(_IMPL, return_value=dict(_GREEN_MANIFEST)) as m:
            cli_batch.main(["part.sldprt", pf, "--yes", "--strict"])
        assert m.call_args.kwargs["strict"] is True

    def test_proposals_wrapper_object(self, tmp_path, capsys):
        pf = _props_file(tmp_path, data={"proposals": _PROPS})
        with patch(_IMPL, return_value=dict(_GREEN_MANIFEST)) as m:
            cli_batch.main(["part.sldprt", pf, "--yes"])
        assert m.call_args.kwargs["proposals"] == _PROPS


# ---------------------------------------------------------------------------
# Decline path ('N' / EOF) — bypasses the engine entirely
# ---------------------------------------------------------------------------

class TestDecline:
    def test_n_aborts_without_commit(self, tmp_path, monkeypatch, capsys):
        pf = _props_file(tmp_path)
        monkeypatch.setattr("builtins.input", lambda *_: "n")
        with patch(_IMPL) as m:
            rc = cli_batch.main(["part.sldprt", pf])
        m.assert_not_called()
        assert rc == 0  # clean decline
        payload = _stdout_json(capsys)
        assert payload["aborted"] is True and payload["ok"] is False

    def test_empty_response_aborts(self, tmp_path, monkeypatch, capsys):
        pf = _props_file(tmp_path)
        monkeypatch.setattr("builtins.input", lambda *_: "")
        with patch(_IMPL) as m:
            rc = cli_batch.main(["part.sldprt", pf])
        m.assert_not_called()
        assert rc == 0

    def test_eof_aborts(self, tmp_path, monkeypatch, capsys):
        pf = _props_file(tmp_path)

        def _eof(*_a):
            raise EOFError

        monkeypatch.setattr("builtins.input", _eof)
        with patch(_IMPL) as m:
            rc = cli_batch.main(["part.sldprt", pf])
        m.assert_not_called()
        assert rc == 0


# ---------------------------------------------------------------------------
# Input validation + fault rendering
# ---------------------------------------------------------------------------

class TestEdges:
    def test_missing_proposals_file(self, capsys):
        with patch(_IMPL) as m:
            rc = cli_batch.main(["part.sldprt", "/no/such/file.json", "--yes"])
        m.assert_not_called()
        assert rc == 1
        assert "not found" in _stdout_json(capsys)["error"]

    def test_malformed_json(self, tmp_path, capsys):
        pf = tmp_path / "bad.json"
        pf.write_text("{not json", encoding="utf-8")
        with patch(_IMPL) as m:
            rc = cli_batch.main(["part.sldprt", str(pf), "--yes"])
        m.assert_not_called()
        assert rc == 1 and "JSON" in _stdout_json(capsys)["error"]

    def test_fault_manifest_exit_1_and_renders(self, tmp_path, capsys):
        pf = _props_file(tmp_path)
        with patch(_IMPL, return_value=dict(_FAULT_MANIFEST)):
            rc = cli_batch.main(["part.sldprt", pf, "--yes"])
        captured = capsys.readouterr()
        assert rc == 1
        assert json.loads(captured.out)["ok"] is False
        # operator-facing render goes to stderr with the recovery info
        assert "HALTED" in captured.err
        assert "skipped" in captured.err.lower()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_render_manifest_green():
    line = cli_batch._render_manifest(_GREEN_MANIFEST)
    assert "COMMITTED 2/2" in line

def test_render_manifest_fault():
    text = cli_batch._render_manifest(_FAULT_MANIFEST)
    assert "HALTED" in text and "FAULT at index 1" in text
