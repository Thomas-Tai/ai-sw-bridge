"""Offline unit tests for the W78 URDF export orchestrator.

The seat PAE (spikes/v0_2x/spike_urdf_pae.py) proves the live COM path; these
tests pin the PURE logic — link-name sanitization, rotation→rpy extraction, the
URDF XML fragments, and the two-phase orchestration/fail-closed flow — with the
Phase-1 data read (_extract_link_data), the session flush (get_sw_app), and the
Phase-2 mesh export (_export_part_stl) mocked. The generated URDF is parsed with
ElementTree to prove it is well-formed.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from unittest.mock import patch

import ai_sw_bridge.export_urdf as U


# ── Pure helpers ────────────────────────────────────────────────────────────


def test_sanitize_link_name_maps_and_dedups():
    used: set[str] = set()
    assert U.sanitize_link_name("base-1", used) == "base_1"
    assert U.sanitize_link_name("arm<2>", used) == "arm_2"
    # Collision -> suffixed.
    assert U.sanitize_link_name("base-1", used) == "base_1_2"


def test_sanitize_leading_digit_and_empty():
    assert U.sanitize_link_name("3dprint").startswith("link_")
    assert U.sanitize_link_name("@@@") == "link"


def test_rotmat_to_rpy_identity():
    ident = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    r, p, y = U.rotmat_to_rpy(ident)
    assert abs(r) < 1e-9 and abs(p) < 1e-9 and abs(y) < 1e-9


def test_rotmat_to_rpy_yaw_90():
    # +90° about Z: [[0,-1,0],[1,0,0],[0,0,1]] in row-major 4x4.
    rot = [0, -1, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    r, p, y = U.rotmat_to_rpy(rot)
    assert abs(y - math.pi / 2) < 1e-9
    assert abs(r) < 1e-9 and abs(p) < 1e-9


def test_link_xml_well_formed_and_carries_values():
    xml = U.link_xml(
        "arm",
        0.027,
        [0.0, 0.0, 0.015],
        [[1e-6, 0, 0], [0, 2e-6, 0], [0, 0, 3e-6]],
        "meshes/arm.stl",
    )
    el = ET.fromstring(xml)
    assert el.tag == "link" and el.get("name") == "arm"
    assert el.find("inertial/mass").get("value") == U._f(0.027)
    assert el.find("inertial/origin").get("xyz").split()[2] == U._f(0.015)
    assert el.find("inertial/inertia").get("izz") == U._f(3e-6)
    assert el.find("visual/geometry/mesh").get("filename") == "meshes/arm.stl"
    assert el.find("collision/geometry/mesh").get("filename") == "meshes/arm.stl"


def test_joint_xml_fixed():
    xml = U.joint_xml("base_to_arm", "base_link", "arm", (0.06, 0, 0), (0, 0, 0))
    el = ET.fromstring(xml)
    assert el.get("type") == "fixed"
    assert el.find("parent").get("link") == "base_link"
    assert el.find("child").get("link") == "arm"
    assert el.find("origin").get("xyz").split()[0] == U._f(0.06)


def test_assemble_urdf_is_valid_xml():
    doc = U.assemble_urdf("bot", ['  <link name="base_link"/>\n'], [])
    el = ET.fromstring(doc)
    assert el.tag == "robot" and el.get("name") == "bot"


# ── Orchestrator (mocked COM) ───────────────────────────────────────────────


class _FakeSW:
    """Stands in for ISldWorks across the Phase-1→Phase-2 session flush."""

    def __init__(self):
        self.close_calls = 0

    def CloseAllDocuments(self, _save):
        self.close_calls += 1
        return True


class _FakeAsm:
    def __init__(self, comps):
        self._comps = comps

    def GetComponents(self, _top):
        return self._comps


def _fake_data_factory(comps):
    """Phase-1 stand-in: pure data record incl. a synthetic .sldprt path."""

    def fake_data(comp, used, mod):
        i = comps.index(comp)
        name = U.sanitize_link_name(f"part-{i + 1}", used)
        return {
            "ok": True,
            "name": name,
            "raw_name": f"part-{i + 1}",
            "mass_kg": 0.008 * (i + 1),
            "com_m": [0.0, 0.0, 0.01 * (i + 1)],
            "tensor": [[1e-6, 0, 0], [0, 1e-6, 0], [0, 0, 1e-6]],
            "xyz": (0.06 * i, 0.0, 0.0),
            "rpy": (0.0, 0.0, 0.0),
            "part_path": f"C:/fake/part_{i + 1}.sldprt",
        }

    return fake_data


def _stl_ok(sw, part_path, stl_name, meshes_dir, binary, mod):
    return True, None


def test_export_urdf_two_components(tmp_path):
    comps = [object(), object()]
    with (
        patch.object(U, "wrapper_module", return_value=object()),
        patch.object(U, "resolve", return_value=U.SW_DOC_ASSEMBLY),
        patch.object(U, "typed", return_value=_FakeAsm(comps)),
        patch.object(U, "get_sw_app", return_value=_FakeSW()),
        patch.object(U, "_extract_link_data", side_effect=_fake_data_factory(comps)),
        patch.object(U, "_export_part_stl", side_effect=_stl_ok),
    ):
        res = U.export_urdf(object(), tmp_path, robot_name="bot")

    assert res["ok"] is True
    assert res["warnings"] == []
    assert len(res["links"]) == 2 and len(res["joints"]) == 2
    # The written URDF parses and has base_link + 2 component links + 2 joints.
    tree = ET.parse(res["urdf_path"])
    root = tree.getroot()
    assert root.get("name") == "bot"
    links = root.findall("link")
    joints = root.findall("joint")
    assert len(links) == 3  # base_link + 2
    assert len(joints) == 2
    assert {ln.get("name") for ln in links} == {"base_link", "part_1", "part_2"}
    # Each component link references its part mesh.
    meshes = {
        ln.get("name"): ln.find("visual/geometry/mesh").get("filename")
        for ln in links
        if ln.find("visual") is not None
    }
    assert meshes == {"part_1": "meshes/part_1.stl", "part_2": "meshes/part_2.stl"}
    # Asymmetric inertial: part_2 is heavier (mass scales with index).
    masses = {
        ln.get("name"): ln.find("inertial/mass").get("value")
        for ln in links
        if ln.find("inertial") is not None
    }
    assert masses["part_2"] == U._f(0.016)
    assert all(j.get("type") == "fixed" for j in joints)


def test_export_urdf_dedups_shared_part_mesh(tmp_path):
    # Two instances of the SAME part file -> one STL export, shared mesh ref.
    comps = [object(), object()]

    def same_path_data(comp, used, mod):
        i = comps.index(comp)
        name = U.sanitize_link_name(f"inst-{i + 1}", used)
        return {
            "ok": True,
            "name": name,
            "raw_name": f"inst-{i + 1}",
            "mass_kg": 0.01,
            "com_m": [0, 0, 0.01],
            "tensor": [[1e-6, 0, 0], [0, 1e-6, 0], [0, 0, 1e-6]],
            "xyz": (0.05 * i, 0, 0),
            "rpy": (0, 0, 0),
            "part_path": "C:/fake/shared.sldprt",
        }

    calls: list[str] = []

    def counting_stl(sw, part_path, stl_name, meshes_dir, binary, mod):
        calls.append(part_path)
        return True, None

    with (
        patch.object(U, "wrapper_module", return_value=object()),
        patch.object(U, "resolve", return_value=U.SW_DOC_ASSEMBLY),
        patch.object(U, "typed", return_value=_FakeAsm(comps)),
        patch.object(U, "get_sw_app", return_value=_FakeSW()),
        patch.object(U, "_extract_link_data", side_effect=same_path_data),
        patch.object(U, "_export_part_stl", side_effect=counting_stl),
    ):
        res = U.export_urdf(object(), tmp_path)

    assert res["ok"] is True
    assert len(calls) == 1  # exported once, not per-instance
    assert len(res["links"]) == 2  # but still two links
    meshes = {ln["name"]: ln["mesh"] for ln in res["links"]}
    assert set(meshes.values()) == {"meshes/shared.stl"}


def test_export_urdf_rejects_non_assembly(tmp_path):
    with (
        patch.object(U, "wrapper_module", return_value=object()),
        patch.object(U, "resolve", return_value=1),
    ):  # swDocPART
        res = U.export_urdf(object(), tmp_path)
    assert res["ok"] is False and "assembly" in res["error"]


def test_export_urdf_flush_failure_is_fail_closed(tmp_path):
    comps = [object()]

    class _BoomSW:
        def CloseAllDocuments(self, _save):
            raise RuntimeError("rpc died")

    with (
        patch.object(U, "wrapper_module", return_value=object()),
        patch.object(U, "resolve", return_value=U.SW_DOC_ASSEMBLY),
        patch.object(U, "typed", return_value=_FakeAsm(comps)),
        patch.object(U, "get_sw_app", return_value=_BoomSW()),
        patch.object(U, "_extract_link_data", side_effect=_fake_data_factory(comps)),
    ):
        res = U.export_urdf(object(), tmp_path)

    assert res["ok"] is False and "session flush" in res["error"]


def test_export_urdf_partial_skips_warn_but_succeed(tmp_path):
    comps = [object(), object()]

    def half_data(comp, used, mod):
        i = comps.index(comp)
        if i == 0:
            return {
                "ok": False,
                "name": "bad",
                "raw_name": "bad-1",
                "error": "GetModelDoc2 returned None",
            }
        name = U.sanitize_link_name("good-1", used)
        return {
            "ok": True,
            "name": name,
            "raw_name": "good-1",
            "mass_kg": 0.01,
            "com_m": [0, 0, 0.01],
            "tensor": [[1e-6, 0, 0], [0, 1e-6, 0], [0, 0, 1e-6]],
            "xyz": (0, 0, 0),
            "rpy": (0, 0, 0),
            "part_path": "C:/fake/good.sldprt",
        }

    with (
        patch.object(U, "wrapper_module", return_value=object()),
        patch.object(U, "resolve", return_value=U.SW_DOC_ASSEMBLY),
        patch.object(U, "typed", return_value=_FakeAsm(comps)),
        patch.object(U, "get_sw_app", return_value=_FakeSW()),
        patch.object(U, "_extract_link_data", side_effect=half_data),
        patch.object(U, "_export_part_stl", side_effect=_stl_ok),
    ):
        res = U.export_urdf(object(), tmp_path)

    assert res["ok"] is True
    assert len(res["links"]) == 1
    assert any("skipped" in w for w in res["warnings"])


def test_export_urdf_stl_failure_skips_component(tmp_path):
    # Phase-1 ok, but Phase-2 STL export fails -> component dropped with warning.
    comps = [object()]

    def stl_fail(sw, part_path, stl_name, meshes_dir, binary, mod):
        return False, "0-byte ghost"

    with (
        patch.object(U, "wrapper_module", return_value=object()),
        patch.object(U, "resolve", return_value=U.SW_DOC_ASSEMBLY),
        patch.object(U, "typed", return_value=_FakeAsm(comps)),
        patch.object(U, "get_sw_app", return_value=_FakeSW()),
        patch.object(U, "_extract_link_data", side_effect=_fake_data_factory(comps)),
        patch.object(U, "_export_part_stl", side_effect=stl_fail),
    ):
        res = U.export_urdf(object(), tmp_path)

    assert res["ok"] is False and "no usable components" in res["error"]
    assert any("0-byte ghost" in w for w in res["warnings"])


def test_export_urdf_all_failed_is_fail_closed(tmp_path):
    comps = [object()]

    def bad_data(comp, used, mod):
        return {"ok": False, "name": "x", "raw_name": "x-1", "error": "boom"}

    with (
        patch.object(U, "wrapper_module", return_value=object()),
        patch.object(U, "resolve", return_value=U.SW_DOC_ASSEMBLY),
        patch.object(U, "typed", return_value=_FakeAsm(comps)),
        patch.object(U, "get_sw_app", return_value=_FakeSW()),
        patch.object(U, "_extract_link_data", side_effect=bad_data),
    ):
        res = U.export_urdf(object(), tmp_path)

    assert res["ok"] is False and "no usable components" in res["error"]
