"""W62 composite-curve derisk spike (LIVE seat only — do NOT run offline).

Probes the dual-mode composite handler on a real SOLIDWORKS seat:
  Mode-A: CreateDefinition(swFmRefCurve=14) → QI ICompositeCurveFeatureData
          → SetEntitiesToJoin → CreateFeature
  Mode-B: select edges → InsertCompositeCurve() (legacy)

PASS iff a new feature node materializes AND survives save→reopen.
Reports which mode fired.

Fixture: fx.build_block (40×30×10 mm boss-extrude) + fx.top_face_edges
(2–3 connected top-face edges).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(name)s %(levelname)s %(message)s")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = str(_REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import _feature_spike_fixtures as fx  # noqa: E402  (sibling import — script dir is on sys.path[0])
from ai_sw_bridge.features.composite import create_composite  # noqa: E402


def main() -> None:
    sw = fx.connect()
    doc = fx.build_block(sw)
    edges = fx.top_face_edges(doc, n=2)

    print(f"[composite] block built; {len(edges)} top-face edges acquired")
    nodes_before = fx.count_feature_nodes(doc)
    print(f"[composite] feature nodes before: {nodes_before}")

    ok, note = create_composite(doc, {}, {"edges": edges})
    print(f"[composite] handler returned: ok={ok}, note={note!r}")

    nodes_after = fx.count_feature_nodes(doc)
    print(f"[composite] feature nodes after: {nodes_after} (delta={nodes_after - nodes_before})")

    if not ok:
        print("[composite] FAIL — handler returned False")
        return

    print("[composite] saving and reopening...")
    doc2 = fx.save_and_reopen(sw, doc)
    nodes_reopen = fx.count_feature_nodes(doc2)
    print(f"[composite] feature nodes after reopen: {nodes_reopen}")

    if nodes_reopen > nodes_before:
        print(f"[composite] PASS — composite curve survived reopen (mode: {note})")
    else:
        print("[composite] FAIL — composite curve did NOT survive reopen")


if __name__ == "__main__":
    main()
