"""Offline tests — ``_sw_batch_feature_add_impl`` + the fail-fast recovery manifest.

``batch`` applies a SEQUENCE of feature-add proposals in ONE open-doc transaction
(fail-fast best-effort default): execute in order, HALT on the first handler
``False``/exception, save the greens, return the ratified recovery manifest
(success trail / singular fault / skipped resume-queue).

The engine's COM seams are patched on the ``mutate`` module itself —
``_open_doc_typed`` (doc handle), ``_apply_feature`` (the registry dispatch, here
a scripted fake so the test controls WHICH index fails), ``_save_doc``,
``get_sw_app``, ``get_active_doc``.  The REAL manifest-assembly logic runs.

The crux assertion is fail-fast: when proposal index 1 fails, ``_apply_feature``
must be called EXACTLY twice — proposal 2 is never attempted.
"""

from __future__ import annotations

from ai_sw_bridge import mutate
from ai_sw_bridge.mutate import _sw_batch_feature_add_impl


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeDoc:
    def GetTitle(self) -> str:
        return "part.SLDPRT"


class _FakeSw:
    def __init__(self) -> None:
        self.closed: list = []

    def CloseDoc(self, title) -> None:
        self.closed.append(title)


class _FakeActive:
    def __init__(self, path: str) -> None:
        self.GetPathName = path  # resolve() reads this as a property


def _props(*kinds: str) -> list[dict]:
    """Build proposals; each feature/target echoes its kind+index for echo checks."""
    return [
        {"feature": {"type": k, "n": i}, "target": {"sketch": f"S{i}"}}
        for i, k in enumerate(kinds)
    ]


def _wire(
    monkeypatch,
    *,
    apply_results: list[tuple[bool, str | None]],
    open_ok: bool = True,
    save_ok: bool = True,
    save_raises: bool = False,
    active=None,
):
    """Patch the engine seams. ``apply_results`` is consumed in call order;
    a call past the script's end fails the test (fail-fast violation)."""
    sw = _FakeSw()
    monkeypatch.setattr(mutate, "get_sw_app", lambda: sw)
    monkeypatch.setattr(mutate, "get_active_doc", lambda sw_: active)
    monkeypatch.setattr(
        mutate, "_open_doc_typed", lambda p: (_FakeDoc() if open_ok else None)
    )

    calls: list[tuple[dict, dict]] = []

    def fake_apply(doc, feature, target):
        idx = len(calls)
        calls.append((feature, target))
        assert idx < len(apply_results), (
            f"_apply_feature called {idx + 1}× but script has "
            f"{len(apply_results)} — fail-fast violated (over-attempt)"
        )
        return apply_results[idx]

    monkeypatch.setattr(mutate, "_apply_feature", fake_apply)

    def fake_save(doc):
        if save_raises:
            raise RuntimeError("save boom")
        return save_ok

    monkeypatch.setattr(mutate, "_save_doc", fake_save)
    return sw, calls


# ---------------------------------------------------------------------------
# Validation — fail closed before any COM
# ---------------------------------------------------------------------------


class TestValidation:
    def test_empty_doc_path(self):
        r = _sw_batch_feature_add_impl("", _props("a"))
        assert r["ok"] is False and "doc_path" in r["error"]

    def test_proposals_not_list(self):
        r = _sw_batch_feature_add_impl("p.sldprt", {"feature": {}})  # type: ignore[arg-type]
        assert r["ok"] is False and "list" in r["error"]

    def test_empty_proposals(self):
        r = _sw_batch_feature_add_impl("p.sldprt", [])
        assert r["ok"] is False and "empty" in r["error"]

    def test_proposal_missing_feature(self):
        r = _sw_batch_feature_add_impl("p.sldprt", [{"target": {}}])
        assert r["ok"] is False and "proposal[0]" in r["error"]

    def test_proposal_missing_target(self):
        r = _sw_batch_feature_add_impl("p.sldprt", [{"feature": {}}])
        assert r["ok"] is False and "proposal[0]" in r["error"]


# ---------------------------------------------------------------------------
# Green path — all features commit
# ---------------------------------------------------------------------------


class TestAllGreen:
    def test_three_green(self, monkeypatch):
        sw, calls = _wire(
            monkeypatch,
            apply_results=[(True, "n0"), (True, "n1"), (True, "n2")],
        )
        r = _sw_batch_feature_add_impl(
            "p.sldprt", _props("ref_plane", "sketch", "boss_extrude_blind")
        )
        assert r["ok"] is True
        assert r["committed_count"] == 3 and r["attempted"] == 3
        assert r["doc_saved"] is True
        assert r["fault"] is None and r["skipped"] == [] and r["halted_at"] is None
        assert [c["kind"] for c in r["committed"]] == [
            "ref_plane",
            "sketch",
            "boss_extrude_blind",
        ]
        assert [c["note"] for c in r["committed"]] == ["n0", "n1", "n2"]
        assert len(sw.closed) == 1  # doc closed in finally

    def test_single_green(self, monkeypatch):
        _wire(monkeypatch, apply_results=[(True, "ok")])
        r = _sw_batch_feature_add_impl("p.sldprt", _props("scale"))
        assert r["ok"] is True and r["doc_saved"] is True


# ---------------------------------------------------------------------------
# THE canonical fail-fast case — feature 2 (index 1) fails
# ---------------------------------------------------------------------------


class TestFailFast:
    def test_index1_fault_halts_and_saves_greens(self, monkeypatch):
        sw, calls = _wire(
            monkeypatch,
            apply_results=[(True, "n0"), (False, "no solid materialized")],
        )
        proposals = _props("ref_plane", "boss_extrude_blind", "fillet_constant_radius")
        r = _sw_batch_feature_add_impl("p.sldprt", proposals)

        # fail-fast: proposal index 2 NEVER attempted
        assert len(calls) == 2, "feature 3 must not be attempted"
        assert r["attempted"] == 2 and r["halted_at"] == 1

        # success trail
        assert r["ok"] is False
        assert r["committed_count"] == 1
        assert r["committed"] == [{"index": 0, "kind": "ref_plane", "note": "n0"}]

        # singular fault — echoes the offending proposal VERBATIM
        assert r["fault"]["index"] == 1
        assert r["fault"]["kind"] == "boss_extrude_blind"
        assert r["fault"]["stage"] == "apply"
        assert r["fault"]["error"] == "no solid materialized"
        assert r["fault"]["feature"] == proposals[1]["feature"]
        assert r["fault"]["target"] == proposals[1]["target"]

        # resume queue
        assert r["skipped"] == [{"index": 2, "kind": "fillet_constant_radius"}]

        # greens persisted (best-effort)
        assert r["doc_saved"] is True
        assert "halted at 1/3" in r["error"]
        assert len(sw.closed) == 1

    def test_first_feature_fault_no_save(self, monkeypatch):
        sw, calls = _wire(monkeypatch, apply_results=[(False, "bad sketch")])
        proposals = _props("sketch", "boss_extrude_blind", "scale")
        r = _sw_batch_feature_add_impl("p.sldprt", proposals)
        assert len(calls) == 1
        assert r["committed_count"] == 0
        assert r["doc_saved"] is False  # nothing green to save
        assert r["fault"]["index"] == 0 and r["fault"]["stage"] == "apply"
        assert [s["index"] for s in r["skipped"]] == [1, 2]

    def test_handler_raises_is_a_fault(self, monkeypatch):
        # First feature succeeds, second RAISES — the engine must catch it and
        # render it as an apply-stage fault (not propagate).
        _wire(monkeypatch, apply_results=[(True, "n0")])
        calls = {"n": 0}

        def fake_apply(doc, feature, target):
            i = calls["n"]
            calls["n"] += 1
            if i == 0:
                return True, "n0"
            raise RuntimeError("COM topology error")

        monkeypatch.setattr(mutate, "_apply_feature", fake_apply)
        r = _sw_batch_feature_add_impl(
            "p.sldprt", _props("ref_plane", "boss_extrude_blind")
        )
        assert r["ok"] is False
        assert r["fault"]["stage"] == "apply"
        assert "handler raised" in r["fault"]["error"]
        assert "COM topology error" in r["fault"]["error"]
        assert r["committed_count"] == 1 and r["doc_saved"] is True


# ---------------------------------------------------------------------------
# strict=True — all-or-nothing (close without saving on fault)
# ---------------------------------------------------------------------------


class TestStrict:
    def test_strict_fault_discards_greens(self, monkeypatch):
        save_calls = {"n": 0}

        def counting_save(doc):
            save_calls["n"] += 1
            return True

        _wire(monkeypatch, apply_results=[(True, "n0"), (False, "boom")])
        monkeypatch.setattr(mutate, "_save_doc", counting_save)
        r = _sw_batch_feature_add_impl(
            "p.sldprt", _props("ref_plane", "boss_extrude_blind", "scale"), strict=True
        )
        assert r["strict"] is True
        assert r["committed_count"] == 1
        assert r["doc_saved"] is False
        assert save_calls["n"] == 0, "strict must NOT save on fault"
        assert "discarded" in r["error"]

    def test_strict_all_green_still_saves(self, monkeypatch):
        _wire(monkeypatch, apply_results=[(True, "a"), (True, "b")])
        r = _sw_batch_feature_add_impl(
            "p.sldprt", _props("ref_plane", "sketch"), strict=True
        )
        assert r["ok"] is True and r["doc_saved"] is True


# ---------------------------------------------------------------------------
# open_doc + save stage faults
# ---------------------------------------------------------------------------


class TestStageFaults:
    def test_open_doc_fault(self, monkeypatch):
        sw, calls = _wire(monkeypatch, apply_results=[], open_ok=False)
        proposals = _props("ref_plane", "sketch")
        r = _sw_batch_feature_add_impl("p.sldprt", proposals)
        assert len(calls) == 0 and r["attempted"] == 0
        assert r["fault"]["stage"] == "open_doc" and r["fault"]["index"] == 0
        assert r["fault"]["feature"] == proposals[0]["feature"]
        assert [s["index"] for s in r["skipped"]] == [1]

    def test_save_stage_fault_all_green(self, monkeypatch):
        _wire(monkeypatch, apply_results=[(True, "a"), (True, "b")], save_raises=True)
        r = _sw_batch_feature_add_impl("p.sldprt", _props("ref_plane", "sketch"))
        assert r["ok"] is False
        assert r["fault"]["stage"] == "save"
        assert r["doc_saved"] is False
        assert "Save raised" in r["error"]


# ---------------------------------------------------------------------------
# dry_run (PLAN-ONLY) — validates every feature but NEVER saves
# ---------------------------------------------------------------------------


class TestDryRun:
    def _counting_save(self, monkeypatch):
        n = {"saves": 0}

        def save(doc):
            n["saves"] += 1
            return True

        monkeypatch.setattr(mutate, "_save_doc", save)
        return n

    def test_all_green_dry_run_never_saves(self, monkeypatch):
        _wire(monkeypatch, apply_results=[(True, "a"), (True, "b"), (True, "c")])
        saves = self._counting_save(monkeypatch)
        r = _sw_batch_feature_add_impl(
            "p.sldprt", _props("ref_plane", "scale", "com_point"), dry_run=True
        )
        assert r["dry_run"] is True
        assert r["ok"] is True  # all features WOULD commit
        assert r["committed_count"] == 3  # the would-commit trail
        assert r["doc_saved"] is False  # nothing persisted
        assert saves["saves"] == 0  # _save_doc NEVER called

    def test_dry_run_fault_still_reported_no_save(self, monkeypatch):
        _wire(monkeypatch, apply_results=[(True, "a"), (False, "bad")])
        saves = self._counting_save(monkeypatch)
        r = _sw_batch_feature_add_impl(
            "p.sldprt", _props("ref_plane", "scale", "com_point"), dry_run=True
        )
        assert r["dry_run"] is True and r["ok"] is False
        assert r["committed_count"] == 1 and r["halted_at"] == 1
        assert r["fault"]["index"] == 1
        assert [s["kind"] for s in r["skipped"]] == ["com_point"]
        assert r["doc_saved"] is False and saves["saves"] == 0


# ---------------------------------------------------------------------------
# active-doc guard + facade delegation
# ---------------------------------------------------------------------------


class TestGuardAndFacade:
    def test_active_doc_guard(self, monkeypatch, tmp_path):
        doc_path = str(tmp_path / "part.sldprt")
        _wire(monkeypatch, apply_results=[], active=_FakeActive(doc_path))
        r = _sw_batch_feature_add_impl(doc_path, _props("ref_plane"))
        assert r["ok"] is False and "active document" in r["error"]

    def test_facade_routes_to_impl(self, monkeypatch):
        from ai_sw_bridge.client import SolidWorksClient

        _wire(monkeypatch, apply_results=[(True, "n0"), (True, "n1")])
        client = SolidWorksClient()
        r = client.mutate.batch("p.sldprt", _props("ref_plane", "sketch"))
        assert r["ok"] is True and r["committed_count"] == 2

    def test_never_raises(self):
        for bad in (None, 5, "x"):
            r = _sw_batch_feature_add_impl("p.sldprt", bad)  # type: ignore[arg-type]
            assert r["ok"] is False
