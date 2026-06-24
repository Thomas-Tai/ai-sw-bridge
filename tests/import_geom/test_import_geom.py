"""Offline (SW-free) tests for ``ai_sw_bridge.import_geom``.

Covers schema, validator, and dispatch routing via mocks. The COM call
chain itself is seat-gated (S1 probe, then S2/S3 PAE); these tests pin
the contract around it.

Layers:
  - ``test_validator_valid_*`` — golden-path envelope parsing.
  - ``test_validator_rejects_*`` — fail-closed: unsupported ext, missing
    source, missing output parent, wrong output ext, bad verify fields,
    unknown kind.
  - ``test_dispatch_*`` — mocks ``sw_com``, ``earlybind``, and the doc
    object; asserts the exact LoadFile4 / GetImportFileData / SaveAs3 /
    GetBodies2 / CreateMassProperty sequence runs, and that each
    failure mode collapses into a typed ``ImportResult(ok=False)``.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from ai_sw_bridge.import_geom import (
    ImportResult,
    ImportSpec,
    ImportValidationError,
    import_part,
    parse_import_spec,
    validate_import_spec,
)
from ai_sw_bridge.import_geom.schema import SUPPORTED_EXTENSIONS


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_step(tmp_path: Path) -> Path:
    p = tmp_path / "vendor.step"
    p.write_bytes(b"ISO-10303-21;\n")
    return p


@pytest.fixture
def valid_iges(tmp_path: Path) -> Path:
    p = tmp_path / "vendor.igs"
    p.write_bytes(b"IGES fixture\n")
    return p


@pytest.fixture
def output_path(tmp_path: Path) -> Path:
    return tmp_path / "imported.sldprt"


@pytest.fixture
def valid_envelope(valid_step: Path, output_path: Path) -> dict[str, Any]:
    return {
        "kind": "import",
        "source": str(valid_step),
        "output": str(output_path),
    }


# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------


def test_supported_extensions() -> None:
    assert ".step" in SUPPORTED_EXTENSIONS
    assert ".stp" in SUPPORTED_EXTENSIONS
    assert ".iges" in SUPPORTED_EXTENSIONS
    assert ".igs" in SUPPORTED_EXTENSIONS
    # Case-insensitivity is enforced by the validator, not the set itself.
    assert all(ext == ext.lower() for ext in SUPPORTED_EXTENSIONS)


# ---------------------------------------------------------------------------
# validator — happy path
# ---------------------------------------------------------------------------


def test_validator_valid_step(
    valid_envelope: dict[str, Any], valid_step: Path, output_path: Path
) -> None:
    spec = validate_import_spec(valid_envelope)
    assert isinstance(spec, ImportSpec)
    assert spec.source == valid_step.resolve()
    assert spec.output == output_path.resolve()
    assert spec.verify is None
    assert spec.source_extension() == ".step"


def test_validator_valid_with_verify(valid_step: Path, output_path: Path) -> None:
    envelope = {
        "kind": "import",
        "source": str(valid_step),
        "output": str(output_path),
        "verify": {"volume_mm3": 24000.0, "volume_rel_tol": 0.02, "min_bodies": 1},
    }
    spec = validate_import_spec(envelope)
    assert spec.verify == envelope["verify"]


def test_validator_relative_paths_resolve_against_spec_dir(
    tmp_path: Path,
) -> None:
    sub = tmp_path / "nested"
    sub.mkdir()
    src = sub / "vendor.step"
    src.write_bytes(b"x")
    spec_path = sub / "import.json"
    spec_path.write_text(
        json.dumps(
            {
                "kind": "import",
                "source": "vendor.step",
                "output": "out.sldprt",
            }
        )
    )
    spec = parse_import_spec(spec_path)
    assert spec.source == src.resolve()
    assert spec.output == (sub / "out.sldprt").resolve()


# ---------------------------------------------------------------------------
# validator — fail-closed
# ---------------------------------------------------------------------------


def test_validator_rejects_wrong_kind(valid_envelope: dict) -> None:
    valid_envelope["kind"] = "build"
    with pytest.raises(ImportValidationError) as ei:
        validate_import_spec(valid_envelope)
    assert ei.value.path == "kind"


def test_validator_rejects_missing_kind(valid_step: Path, output_path: Path) -> None:
    with pytest.raises(ImportValidationError) as ei:
        validate_import_spec({"source": str(valid_step), "output": str(output_path)})
    assert ei.value.path == "kind"


@pytest.mark.parametrize("ext", [".txt", ".json", ".sldprt", ".py"])
def test_validator_rejects_unsupported_extension(
    tmp_path: Path, output_path: Path, ext: str
) -> None:
    src = tmp_path / f"vendor{ext}"
    src.write_bytes(b"x")
    with pytest.raises(ImportValidationError) as ei:
        validate_import_spec(
            {
                "kind": "import",
                "source": str(src),
                "output": str(output_path),
            }
        )
    assert ei.value.path == "source"
    assert "unsupported extension" in ei.value.message


@pytest.mark.parametrize("ext", [".STEP", ".STP", ".IGES", ".IGS"])
def test_validator_accepts_uppercase_supported_extension(
    tmp_path: Path, output_path: Path, ext: str
) -> None:
    """Extension matching is case-insensitive — ``.STEP`` == ``.step``."""
    src = tmp_path / f"vendor{ext}"
    src.write_bytes(b"x")
    spec = validate_import_spec(
        {"kind": "import", "source": str(src), "output": str(output_path)}
    )
    assert spec.source_extension() == ext.lower()


def test_validator_rejects_missing_source(output_path: Path) -> None:
    with pytest.raises(ImportValidationError) as ei:
        validate_import_spec(
            {
                "kind": "import",
                "source": "/no/such/file.step",
                "output": str(output_path),
            }
        )
    assert ei.value.path == "source"
    assert "does not exist" in ei.value.message


def test_validator_rejects_output_without_sldprt(
    valid_step: Path, tmp_path: Path
) -> None:
    bad_out = tmp_path / "out.stp"
    with pytest.raises(ImportValidationError) as ei:
        validate_import_spec(
            {
                "kind": "import",
                "source": str(valid_step),
                "output": str(bad_out),
            }
        )
    assert ei.value.path == "output"
    assert ".sldprt" in ei.value.message


def test_validator_rejects_output_parent_missing(
    valid_step: Path, tmp_path: Path
) -> None:
    out = tmp_path / "nope" / "out.sldprt"
    with pytest.raises(ImportValidationError) as ei:
        validate_import_spec(
            {
                "kind": "import",
                "source": str(valid_step),
                "output": str(out),
            }
        )
    assert ei.value.path == "output"
    assert "parent directory" in ei.value.message


def test_validator_rejects_bad_verify_volume(
    valid_step: Path, output_path: Path
) -> None:
    with pytest.raises(ImportValidationError) as ei:
        validate_import_spec(
            {
                "kind": "import",
                "source": str(valid_step),
                "output": str(output_path),
                "verify": {"volume_mm3": -1.0},
            }
        )
    assert ei.value.path == "verify.volume_mm3"


def test_validator_rejects_bad_verify_tolerance(
    valid_step: Path, output_path: Path
) -> None:
    with pytest.raises(ImportValidationError) as ei:
        validate_import_spec(
            {
                "kind": "import",
                "source": str(valid_step),
                "output": str(output_path),
                "verify": {"volume_mm3": 100.0, "volume_rel_tol": 2.0},
            }
        )
    assert ei.value.path == "verify.volume_rel_tol"


def test_validator_rejects_unknown_top_level_field(
    valid_envelope: dict,
) -> None:
    valid_envelope["bogus"] = 1
    with pytest.raises(ImportValidationError) as ei:
        validate_import_spec(valid_envelope)
    assert ei.value.path == "spec"
    assert "bogus" in ei.value.message


def test_parse_import_spec_rejects_bad_json(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("{not valid json")
    with pytest.raises(ImportValidationError) as ei:
        parse_import_spec(p)
    assert ei.value.path == "spec"
    assert "JSON" in ei.value.message


def test_parse_import_spec_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ImportValidationError) as ei:
        parse_import_spec(tmp_path / "nope.json")
    assert ei.value.path == "spec"


# ---------------------------------------------------------------------------
# dispatch — mocked COM
# ---------------------------------------------------------------------------


def _install_sw_stubs() -> None:
    """Inject synthetic ``ai_sw_bridge.sw_com`` and ``com.earlybind`` modules
    if pywin32 isn't available (CI / non-Windows).
    """
    if "ai_sw_bridge.sw_com" in sys.modules:
        return
    sw_com = types.ModuleType("ai_sw_bridge.sw_com")
    sw_com.get_sw_app = lambda: None  # type: ignore[attr-defined]
    sys.modules["ai_sw_bridge.sw_com"] = sw_com

    early = types.ModuleType("ai_sw_bridge.com.earlybind")

    def _typed(obj: Any, iface: str, *, module: Any | None = None) -> Any:
        return obj

    def _typed_qi(obj: Any, iface: str, *, module: Any | None = None) -> Any:
        return obj

    early.typed = _typed  # type: ignore[attr-defined]
    early.typed_qi = _typed_qi  # type: ignore[attr-defined]
    sys.modules["ai_sw_bridge.com.earlybind"] = early


@pytest.fixture(autouse=True)
def _stubs() -> None:
    _install_sw_stubs()


class _FakeBody:
    def __init__(self, face_count: int = 6) -> None:
        self._face_count = face_count

    def GetFaceCount(self) -> int:
        return self._face_count


class _FakeMassProp:
    def __init__(self, volume_m3: float) -> None:
        self.Volume = volume_m3


class _FakeExtension:
    def __init__(self, volume_m3: float | None) -> None:
        self._volume_m3 = volume_m3

    def CreateMassProperty(self):
        if self._volume_m3 is None:
            return None
        return _FakeMassProp(self._volume_m3)


class _FakeDoc:
    """Simulates an IModelDoc2 / IPartDoc-shaped import target."""

    def __init__(
        self,
        *,
        bodies: list[_FakeBody] | None = None,
        volume_m3: float | None = None,
        doc_type: int = 1,
    ) -> None:
        self._bodies = bodies if bodies is not None else [_FakeBody(6)]
        self.Extension = _FakeExtension(volume_m3)
        self._doc_type = doc_type
        self.saved_to: str | None = None
        self.closed = False

    def GetType(self) -> int:
        return self._doc_type

    def GetBodies2(self, body_type: int, all_bodies: bool):
        return list(self._bodies)

    def SaveAs3(self, path: str, _a: int, _b: int) -> int:
        self.saved_to = path
        # Write a fake .SLDPRT so the postcondition check passes
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"FAKE SLDPRT")
        return 0

    def GetTitle(self) -> str:
        return "imported.SLDPRT"


class _FakeSW:
    def __init__(self, doc: _FakeDoc | None) -> None:
        self._doc = doc
        self.closed: list[str] = []
        self.loadfile4_calls: list[tuple] = []
        self.getimportfiledata_returns: Any = object()

    def GetImportFileData(self, path: str) -> Any:
        return self.getimportfiledata_returns

    def LoadFile4(self, path: str, arg: str, import_data: Any, placeholder: int):
        self.loadfile4_calls.append((path, arg, import_data, placeholder))
        return (self._doc, 0)

    def CloseDoc(self, title: str) -> None:
        self.closed.append(title)


def _run_import(spec: ImportSpec, fake_sw: _FakeSW) -> ImportResult:
    """Inject ``fake_sw`` as the dispatched SldWorks.Application and run.

    The dispatch module ``from ai_sw_bridge.com.earlybind import typed_qi``
    inside ``_verify()`` — the imported name is read from the module object
    in ``sys.modules`` at call time, so we can patch attributes on the
    test-injected fake without fighting PEP-562 lazy-loading.
    """

    def _fake_typed(obj: Any, iface: str, *, module: Any | None = None) -> Any:
        return obj

    def _fake_typed_qi(obj: Any, iface: str, *, module: Any | None = None) -> Any:
        return obj

    earlybind_fake = sys.modules["ai_sw_bridge.com.earlybind"]
    original_typed = earlybind_fake.typed
    original_typed_qi = earlybind_fake.typed_qi
    earlybind_fake.typed = _fake_typed  # type: ignore[attr-defined]
    earlybind_fake.typed_qi = _fake_typed_qi  # type: ignore[attr-defined]

    with mock.patch(
        "ai_sw_bridge.import_geom.dispatch._resolve_sw_app",
        return_value=(fake_sw, fake_sw, None),
    ):
        try:
            return import_part(spec)
        finally:
            earlybind_fake.typed = original_typed  # type: ignore[attr-defined]
            earlybind_fake.typed_qi = original_typed_qi  # type: ignore[attr-defined]


def test_dispatch_happy_path(valid_step: Path, output_path: Path) -> None:
    doc = _FakeDoc(bodies=[_FakeBody(face_count=6)])
    fake_sw = _FakeSW(doc)
    spec = validate_import_spec(
        {"kind": "import", "source": str(valid_step), "output": str(output_path)}
    )
    result = _run_import(spec, fake_sw)
    assert result.ok is True, result.errors
    assert result.bodies == 1
    assert result.faces == 6
    assert doc.saved_to == str(output_path)
    # The doc was closed in the finally block
    assert "imported.SLDPRT" in fake_sw.closed
    # LoadFile4 was invoked with the ground-truth "r" arg-string
    assert fake_sw.loadfile4_calls
    assert fake_sw.loadfile4_calls[0][1] == "r"


def test_dispatch_bodyless_import_fails(valid_step: Path, output_path: Path) -> None:
    doc = _FakeDoc(bodies=[])  # zero bodies — the E4 trap
    fake_sw = _FakeSW(doc)
    spec = validate_import_spec(
        {"kind": "import", "source": str(valid_step), "output": str(output_path)}
    )
    result = _run_import(spec, fake_sw)
    assert result.ok is False
    assert any("E4" in e or "body" in e.lower() for e in result.errors)


def test_dispatch_faceless_body_fails(valid_step: Path, output_path: Path) -> None:
    doc = _FakeDoc(bodies=[_FakeBody(face_count=0)])
    fake_sw = _FakeSW(doc)
    spec = validate_import_spec(
        {"kind": "import", "source": str(valid_step), "output": str(output_path)}
    )
    result = _run_import(spec, fake_sw)
    assert result.ok is False
    assert any("face" in e.lower() for e in result.errors)


def test_dispatch_volume_match(valid_step: Path, output_path: Path) -> None:
    doc = _FakeDoc(volume_m3=24000.0 * 1e-9)  # 24000 mm³ in m³
    fake_sw = _FakeSW(doc)
    spec = validate_import_spec(
        {
            "kind": "import",
            "source": str(valid_step),
            "output": str(output_path),
            "verify": {"volume_mm3": 24000.0, "volume_rel_tol": 0.01},
        }
    )
    result = _run_import(spec, fake_sw)
    assert result.ok is True
    assert result.volume_mm3 == pytest.approx(24000.0, rel=1e-6)


def test_dispatch_volume_mismatch_fails(valid_step: Path, output_path: Path) -> None:
    doc = _FakeDoc(volume_m3=10000.0 * 1e-9)
    fake_sw = _FakeSW(doc)
    spec = validate_import_spec(
        {
            "kind": "import",
            "source": str(valid_step),
            "output": str(output_path),
            "verify": {"volume_mm3": 24000.0, "volume_rel_tol": 0.01},
        }
    )
    result = _run_import(spec, fake_sw)
    assert result.ok is False
    assert any("volume" in e.lower() for e in result.errors)


def test_dispatch_getimportfiledata_none_fails(
    valid_step: Path, output_path: Path
) -> None:
    fake_sw = _FakeSW(_FakeDoc())
    fake_sw.getimportfiledata_returns = None
    spec = validate_import_spec(
        {"kind": "import", "source": str(valid_step), "output": str(output_path)}
    )
    result = _run_import(spec, fake_sw)
    assert result.ok is False
    assert any("GetImportFileData" in e for e in result.errors)


def test_dispatch_loadfile4_returns_none_doc_fails(
    valid_step: Path, output_path: Path
) -> None:
    fake_sw = _FakeSW(None)  # LoadFile4 returns None doc
    spec = validate_import_spec(
        {"kind": "import", "source": str(valid_step), "output": str(output_path)}
    )
    result = _run_import(spec, fake_sw)
    assert result.ok is False
    assert any("LoadFile4" in e for e in result.errors)


def test_dispatch_saveas3_nonzero_error_fails(
    valid_step: Path, output_path: Path
) -> None:
    doc = _FakeDoc()

    def _saveas_fail(*_args, **_kwargs) -> int:
        return 2  # swGenericSaveError

    doc.SaveAs3 = _saveas_fail  # type: ignore[assignment]
    fake_sw = _FakeSW(doc)
    spec = validate_import_spec(
        {"kind": "import", "source": str(valid_step), "output": str(output_path)}
    )
    result = _run_import(spec, fake_sw)
    assert result.ok is False
    assert any("SaveAs3" in e for e in result.errors)


def test_dispatch_non_part_doc_type_fails(valid_step: Path, output_path: Path) -> None:
    doc = _FakeDoc(doc_type=2)  # assembly
    fake_sw = _FakeSW(doc)
    spec = validate_import_spec(
        {"kind": "import", "source": str(valid_step), "output": str(output_path)}
    )
    result = _run_import(spec, fake_sw)
    assert result.ok is False
    assert any("not a Part" in e for e in result.errors)


def test_result_to_dict_omits_empty_errors(valid_step: Path, output_path: Path) -> None:
    doc = _FakeDoc()
    fake_sw = _FakeSW(doc)
    spec = validate_import_spec(
        {"kind": "import", "source": str(valid_step), "output": str(output_path)}
    )
    result = _run_import(spec, fake_sw)
    d = result.to_dict()
    assert d["ok"] is True
    assert "errors" not in d  # empty errors list is omitted
    assert d["bodies"] == 1


def test_result_to_dict_includes_volume_only_when_set(
    valid_step: Path, output_path: Path
) -> None:
    doc = _FakeDoc()
    fake_sw = _FakeSW(doc)
    spec = validate_import_spec(
        {"kind": "import", "source": str(valid_step), "output": str(output_path)}
    )
    result = _run_import(spec, fake_sw)
    assert "volume_mm3" not in result.to_dict()
