"""Seat proof: the `merge` field drives modeling-time UNION vs multi-body.

Two overlapping bosses (Block_A on Front, Block_B on Right — the W53-proven
overlap). merge:true (default) => they fuse => 1 body. merge:false => Block_B
stays separate => 2 bodies. Verify-the-EFFECT = body count.

Uses sys.path.insert(0, worktree/src) FIRST so the WORKTREE builder (with the
merge field) wins over the editable-install main-repo copy.
"""
from __future__ import annotations

import sys
from pathlib import Path

_WT_SRC = str(Path(__file__).resolve().parents[1] / "src")
sys.path.insert(0, _WT_SRC)

import tempfile  # noqa: E402

from ai_sw_bridge.spec import builder  # noqa: E402
from ai_sw_bridge.com.earlybind import typed, typed_qi  # noqa: E402
from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.sw_com import get_sw_app  # noqa: E402


def _spec(merge: bool) -> dict:
    return {
        "schema_version": 1,
        "name": "MergeProbe",
        "features": [
            {"type": "sketch_rectangle_on_plane", "name": "SK_A",
             "plane": "Front", "width": 50.0, "height": 50.0},
            {"type": "boss_extrude_blind", "name": "Block_A",
             "sketch": "SK_A", "depth": 50.0},
            {"type": "sketch_rectangle_on_plane", "name": "SK_B",
             "plane": "Right", "width": 100.0, "height": 100.0},
            {"type": "boss_extrude_blind", "name": "Block_B",
             "sketch": "SK_B", "depth": 100.0, "merge": merge},
        ],
    }


def _body_count(sw, mod, path: str) -> int:
    tsw = typed(sw, "ISldWorks", module=mod)
    ret = tsw.OpenDoc6(path, 1, 1, "", 0, 0)
    md = ret[0] if isinstance(ret, tuple) else ret
    pdoc = typed_qi(md, "IPartDoc", module=mod)
    bodies = pdoc.GetBodies2(0, True)  # swSolidBody=0
    n = len(bodies) if bodies else 0
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    return n


def main() -> int:
    print(f"builder from: {builder.__file__}")
    sw = get_sw_app()
    mod = wrapper_module()
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    tmp = Path(tempfile.gettempdir())
    results = {}
    for merge in (True, False):
        path = str(tmp / f"merge_probe_{'merge' if merge else 'separate'}.SLDPRT")
        builder.build(_spec(merge), no_dim=True, save_as=path)
        n = _body_count(sw, mod, path)
        results[merge] = n
        print(f"  merge={merge!s:5} -> {n} body(ies)")
    ok = results.get(True) == 1 and results.get(False) == 2
    print(f"\n=== {'GREEN' if ok else 'RED'} "
          f"(expect merge=True->1, merge=False->2) ===")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
