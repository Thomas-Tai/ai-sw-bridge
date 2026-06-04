"""Build the BASE part (pre-built, not via lifecycle) for slice-8b PAE."""
import json
import os
import sys

sys.path.insert(0, r"C:\D\WorkSpace\[Local]_Station\01_Heavy_Assets\aisw-W9\src")

from ai_sw_bridge.spec.builder import build as part_build
from ai_sw_bridge.brep.manifest import Manifest

BASE_SPEC = {
    "schema_version": 1,
    "name": "BoxBase",
    "features": [
        {
            "type": "sketch_rectangle_on_plane",
            "name": "SK_Base",
            "plane": "Front",
            "width": 30.0,
            "height": 30.0,
        },
        {
            "type": "boss_extrude_blind",
            "name": "EX_Box",
            "sketch": "SK_Base",
            "depth": 10.0,
        },
    ],
}

SAVE_TO = r"C:\D\WorkSpace\[Local]_Station\01_Heavy_Assets\aisw-W9\spikes\slice8b_box_base.SLDPRT"

print(f"Building base part to {SAVE_TO}...")
try:
    result = part_build(BASE_SPEC, save_as=SAVE_TO, save_format="current", no_dim=True)
    print(f"Build result: ok={result.ok}, save_as_verified={result.save_as_verified}")
    print(f"Features built: {result.features_built}")
    if result.error:
        print(f"Build error: {result.error}")
except Exception as exc:
    print(f"Build RAISED: {exc!r}")
    # Robustness guard: check if file exists anyway
    if os.path.isfile(SAVE_TO):
        print(f"FILE EXISTS despite exception: {SAVE_TO}")
    else:
        print("File does not exist. Build truly failed.")
        sys.exit(1)

# Now capture face data from the built part
if os.path.isfile(SAVE_TO):
    print(f"\nFile verified on disk: {SAVE_TO}")
    print(f"File size: {os.path.getsize(SAVE_TO)} bytes")

    # Open the part and capture manifest
    from ai_sw_bridge.sw_com import get_sw_app
    sw = get_sw_app()
    doc = sw.OpenDoc6(SAVE_TO, 1, 1, "", 0, "")[0]  # 1=part doc
    if doc is None:
        print("ERROR: OpenDoc6 returned None")
        sys.exit(1)

    try:
        manifest = Manifest.from_model_doc(doc)
        faces = manifest.faces
        print(f"\nManifest captured: {len(faces)} faces")
        for i, face in enumerate(faces):
            print(f"  Face {i}: normal={face.get('normal')}, centroid={face.get('centroid')}, "
                  f"fingerprint={face.get('fingerprint')[:12]}..., area={face.get('area_mm2'):.1f}mm2")

        # Save manifest for reference
        manifest_path = SAVE_TO.replace(".SLDPRT", "_manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest.to_dict(), f, indent=2)
        print(f"\nManifest saved to {manifest_path}")

        # Find +Z and -Z faces for the mate
        top_face = None
        for face in faces:
            n = face.get("normal", [0, 0, 0])
            if abs(n[2] - 1.0) < 0.01:  # +Z normal
                top_face = face
                break

        if top_face:
            print(f"\nTOP FACE (+Z): {json.dumps(top_face, indent=2)}")
        else:
            print("\nWARNING: Could not find +Z face")

    finally:
        sw.CloseDoc(doc.GetTitle())
else:
    print(f"ERROR: File not found: {SAVE_TO}")
    sys.exit(1)
