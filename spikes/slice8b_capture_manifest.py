"""Capture face manifest from the already-built base part."""

import json
import os
import sys

sys.path.insert(0, r"C:\path\to\aisw-W9\src")

from ai_sw_bridge.sw_com import get_sw_app
from ai_sw_bridge.com.earlybind import typed
from ai_sw_bridge.com.sw_type_info import wrapper_module
from ai_sw_bridge.brep.manifest import Manifest

SAVE_TO = r"C:\path\to\aisw-W9\spikes\slice8b_box_base.SLDPRT"

sw = get_sw_app()
mod = wrapper_module()
tsw = typed(sw, "ISldWorks", module=mod)

ret = tsw.OpenDoc6(SAVE_TO, 1, 1, "", 0, 0)
if isinstance(ret, tuple):
    doc = ret[0]
else:
    doc = ret

if doc is None:
    print("ERROR: OpenDoc6 returned None")
    sys.exit(1)

print(f"Doc title: {doc.GetTitle()}")

try:
    manifest = Manifest.from_model_doc(doc)
    faces = manifest.faces
    print(f"\nManifest captured: {len(faces)} faces")
    for i, face in enumerate(faces):
        print(
            f"  Face {i}: normal={face.get('normal')}, centroid={face.get('centroid')}, "
            f"fingerprint={face.get('fingerprint','?')[:16]}..., area={face.get('area_mm2',0):.1f}mm2, "
            f"persist_id={'yes' if face.get('persist_id') else 'no'}"
        )

    manifest_path = SAVE_TO.replace(".SLDPRT", "_manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest.to_dict(), f, indent=2)
    print(f"\nManifest saved to {manifest_path}")

    for face in faces:
        n = face.get("normal", [0, 0, 0])
        if abs(n[2] - 1.0) < 0.01:
            print(f"\n=== TOP FACE (+Z) ===\n{json.dumps(face, indent=2)}")
        if abs(n[2] - (-1.0)) < 0.01:
            print(f"\n=== BOTTOM FACE (-Z) ===\n{json.dumps(face, indent=2)}")

finally:
    sw.CloseDoc(doc.GetTitle())
