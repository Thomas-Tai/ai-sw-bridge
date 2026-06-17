"""Spike: bounding_box feature handler (W63 lane 2).

Runs the bounding_box handler on a live SOLIDWORKS seat to determine
which mode (A or B) succeeds for global bounding-box creation.

Mode-A: CreateDefinition(swFmBoundingBox=114) -> IBoundingBoxFeatureData
Mode-B: InsertGlobalBoundingBox (legacy)

PASS iff:
  - node-count delta = +1
  - a BoundingBox or BoundingBoxFolder node materializes
  - the feature survives save -> reopen

DO NOT run this script.  W0 fires it on the live seat.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

logging.basicConfig(level=logging.WARNING)

from ai_sw_bridge.features.bounding_box import create_bounding_box

try:
    from _feature_spike_fixtures import build_block, count_feature_nodes
except ImportError:
    def build_block(sw: Any) -> Any:
        """Fallback block builder — 40x30x10 mm box (W0 fixture not yet present)."""
        from ai_sw_bridge import mutate
        doc = mutate.get_sw_app().NewPart()
        spec = {
            "schema_version": 1,
            "name": "BBoxBlock",
            "features": [
                {
                    "type": "sketch_rectangle_on_plane",
                    "name": "SK_Block",
                    "plane": "Front",
                    "width": 40.0,
                    "height": 30.0,
                },
                {
                    "type": "boss_extrude_blind",
                    "name": "EX_Block",
                    "sketch": "SK_Block",
                    "depth": 10.0,
                },
            ],
        }
        from ai_sw_bridge.build import build_part
        build_part(doc, spec, no_dim=True)
        return doc

    def count_feature_nodes(doc: Any) -> int:
        """Fallback node counter."""
        feats = doc.FeatureManager.GetFeatures(False)
        return len(feats) if feats else 0


def main() -> None:
    from ai_sw_bridge.sw_com import get_sw_app

    sw = get_sw_app()
    doc = build_block(sw)

    feature = {"kind": "bounding_box", "name": "BBox-1", "best_fit": False}
    ok, note = create_bounding_box(doc, feature, {})

    node_count = count_feature_nodes(doc)
    print(f"bounding_box spike: ok={ok}, note={note!r}, nodes={node_count}")
    if ok:
        print(f"PASS — {note}")
    else:
        print(f"FAIL — {note}")

    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass


if __name__ == "__main__":
    main()
