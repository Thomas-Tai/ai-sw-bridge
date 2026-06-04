"""Probe faces from base part - simplified: just normals + persist_id."""
import json
import os
import sys
import hashlib
import base64

sys.path.insert(0, r"C:\D\WorkSpace\[Local]_Station\01_Heavy_Assets\aisw-W9\src")

from ai_sw_bridge.sw_com import get_sw_app
from ai_sw_bridge.com.earlybind import typed, typed_extension
from ai_sw_bridge.com.sw_type_info import wrapper_module

SAVE_TO = r"C:\D\WorkSpace\[Local]_Station\01_Heavy_Assets\aisw-W9\spikes\slice8b_box_base.SLDPRT"

sw = get_sw_app()
mod = wrapper_module()
tsw = typed(sw, "ISldWorks", module=mod)

ret = tsw.OpenDoc6(SAVE_TO, 1, 1, "", 0, 0)
doc = ret[0] if isinstance(ret, tuple) else ret
if doc is None:
    print("ERROR: OpenDoc6 returned None")
    sys.exit(1)

print(f"Doc: {doc.GetTitle()}")

try:
    tpart = typed(doc, "IPartDoc", module=mod)
    bodies = tpart.GetBodies2(0, True)
    body = bodies[0]
    faces = body.GetFaces()
    print(f"Faces: {len(faces)}")

    ext = typed_extension(doc, module=mod)
    face_data_list = []

    for idx, face in enumerate(faces):
        try:
            iface = typed(face, "IFace2", module=mod)
            normal = list(iface.Normal)
            area = iface.GetArea()
            bbox = iface.GetBox()

            persist_id = None
            try:
                pid_bytes = ext.GetPersistReference3(face)
                if pid_bytes:
                    persist_id = base64.b64encode(bytes(pid_bytes)).decode("ascii")
            except Exception as e:
                print(f"    persist_id failed for face {idx}: {e}")

            # Compute centroid from bbox center
            cx = (bbox[0] + bbox[3]) / 2.0
            cy = (bbox[1] + bbox[4]) / 2.0
            cz = (bbox[2] + bbox[5]) / 2.0

            face_info = {
                "face_idx": idx,
                "body_id": 0,
                "normal": [round(normal[0], 6), round(normal[1], 6), round(normal[2], 6)],
                "centroid": [round(cx * 1000, 3), round(cy * 1000, 3), round(cz * 1000, 3)],
                "area_mm2": round(area * 1e6, 2),
                "bbox": [
                    [round(bbox[0] * 1000, 3), round(bbox[1] * 1000, 3), round(bbox[2] * 1000, 3)],
                    [round(bbox[3] * 1000, 3), round(bbox[4] * 1000, 3), round(bbox[5] * 1000, 3)],
                ],
                "is_surface": False,
            }
            if persist_id:
                face_info["persist_id"] = persist_id

            fp_str = f"{face_info['normal']}:{face_info['centroid']}"
            face_info["fingerprint"] = hashlib.sha256(fp_str.encode()).hexdigest()[:16]

            face_data_list.append(face_info)
            print(f"  Face {idx}: normal={[round(x,3) for x in normal]}, "
                  f"centroid_mm={[round(x,1) for x in face_info['centroid']]}, "
                  f"area={face_info['area_mm2']:.1f}mm2, "
                  f"persist={'yes' if persist_id else 'no'}")

        except Exception as exc:
            print(f"  Face {idx}: ERROR: {exc}")

    manifest_path = SAVE_TO.replace(".SLDPRT", "_faces.json")
    with open(manifest_path, "w") as f:
        json.dump(face_data_list, f, indent=2)
    print(f"\nFace data saved to {manifest_path}")

    for fd in face_data_list:
        n = fd["normal"]
        if abs(n[2] - 1.0) < 0.01:
            print(f"\n=== +Z FACE (base top) ===\n{json.dumps(fd, indent=2)}")
        if abs(n[2] - (-1.0)) < 0.01:
            print(f"\n=== -Z FACE (base bottom) ===\n{json.dumps(fd, indent=2)}")

finally:
    sw.CloseDoc(doc.GetTitle())
