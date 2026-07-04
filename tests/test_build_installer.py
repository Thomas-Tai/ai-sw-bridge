"""Offline unit tests for the pure helpers in tools/build_installer.py.

The download/pip/ISCC path is Windows+network and is proven by the CI
workflow_dispatch run, not here.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_TOOLS = _ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import build_installer as bi  # noqa: E402


def test_pybs_url_and_sha_shape() -> None:
    assert bi.PYBS_URL.startswith("https://")
    assert bi.PYBS_URL.endswith(".tar.gz")
    assert "windows" in bi.PYBS_URL and "install_only" in bi.PYBS_URL
    assert re.fullmatch(r"[0-9a-fA-F]{64}", bi.PYBS_SHA256)
    assert bi.PY_VERSION == "3.12"


def test_wheelhouse_targets_include_app_and_keyring() -> None:
    assert ".[mcp]" in bi.WHEELHOUSE_TARGETS
    assert "keyring" in bi.WHEELHOUSE_TARGETS


def test_verify_sha256_passes_on_match() -> None:
    data = b"hello"
    bi.verify_sha256(data, hashlib.sha256(data).hexdigest())


def test_verify_sha256_raises_on_mismatch() -> None:
    with pytest.raises(ValueError):
        bi.verify_sha256(b"hello", "0" * 64)


def test_stage_layout_keys() -> None:
    layout = bi.stage_layout(Path("C:/tmp/stage"))
    assert set(layout) == {"runtime", "wheelhouse", "iss", "readme"}
    assert layout["runtime"].name == "runtime"
    assert layout["wheelhouse"].name == "wheelhouse"


def test_pip_wheel_argv() -> None:
    argv = bi.pip_wheel_argv(Path("py.exe"), Path("wh"), [".[mcp]", "keyring"])
    assert argv[:4] == ["py.exe", "-m", "pip", "wheel"]
    assert argv[-2:] == [".[mcp]", "keyring"]
    assert "--wheel-dir" in argv


def test_iscc_argv() -> None:
    argv = bi.iscc_argv(Path("ISCC.exe"), Path("a.iss"), "1.8.0", Path("dist"))
    assert argv[0] == "ISCC.exe"
    assert "/DAppVersion=1.8.0" in argv
    assert argv[-1] == "a.iss"
