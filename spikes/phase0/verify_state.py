"""
Read-only verification of the active part's feature tree.
Used after Spikes A and B to confirm what got built.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(_PKG_ROOT))

from ai_sw_bridge.sw_com import get_sw_app, get_active_doc  # noqa: E402


def main() -> int:
    sw = get_sw_app()
    doc = get_active_doc(sw)
    if doc is None:
        print(json.dumps({"ok": False, "error": "no active doc"}))
        return 1

    # GetFeatureCount and FirstFeature are properties under late-binding.
    count = doc.GetFeatureCount
    features = []
    feat = doc.FirstFeature
    while feat is not None:
        try:
            name = feat.Name
            ftype = feat.GetTypeName2
        except Exception:
            name, ftype = "?", "?"
        features.append({"name": name, "type": ftype})
        try:
            feat = feat.GetNextFeature
        except Exception:
            break

    print(
        json.dumps({"ok": True, "feature_count": count, "features": features}, indent=2)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
