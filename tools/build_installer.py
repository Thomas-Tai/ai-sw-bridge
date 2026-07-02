#!/usr/bin/env python3
"""Stage a private CPython + offline wheelhouse and drive ISCC to build the
unsigned ai-sw-bridge Windows installer (Phase 5B).

Pure helpers (checksum, argv builders, layout) are unit-tested offline; the
full download/pip/ISCC path is Windows+network and is exercised by the CI
`workflow_dispatch` run, not the offline suite.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# --- Pinned interpreter: astral-sh/python-build-standalone, CPython 3.12,
# x86_64-pc-windows-msvc, install_only. URL + SHA-256 taken from the release's
# published SHA256SUMS; CI verifies the digest at download time (fail-loud).
PY_VERSION = "3.12"
PYBS_RELEASE = "20260623"
PYBS_ARCHIVE = (
    f"cpython-3.12.13+{PYBS_RELEASE}-x86_64-pc-windows-msvc-install_only.tar.gz"
)
PYBS_URL = (
    "https://github.com/astral-sh/python-build-standalone/releases/download/"
    f"{PYBS_RELEASE}/{PYBS_ARCHIVE}"
)
PYBS_SHA256 = "c6af85bb83d5158c9ff71f50dfad467853d1cd236f932b144e87e26e2ea2a83e"

# Wheelhouse closure: the app + its [mcp] extra, plus keyring (lazily imported
# but runtime-reachable via checkpoint.crypto.default_key_source).
WHEELHOUSE_TARGETS = [".[mcp]", "keyring"]


def verify_sha256(data: bytes, expected: str) -> None:
    """Raise ValueError if the SHA-256 of data does not match expected."""
    actual = hashlib.sha256(data).hexdigest()
    if actual.lower() != expected.lower():
        raise ValueError(f"SHA-256 mismatch: got {actual}, expected {expected}")


def stage_layout(staging: Path) -> dict[str, Path]:
    """Return the staging tree paths the .iss packages."""
    return {
        "runtime": staging / "runtime",
        "wheelhouse": staging / "wheelhouse",
        "iss": staging / "ai-sw-bridge.iss",
        "readme": staging / "README-first.txt",
    }


def pip_download_argv(python_exe: Path, dest: Path, targets: list[str]) -> list[str]:
    """argv to download the offline wheelhouse with the bundled interpreter."""
    return [
        str(python_exe),
        "-m",
        "pip",
        "download",
        "--only-binary=:all:",
        "--dest",
        str(dest),
        *targets,
    ]


def iscc_argv(iscc: Path, iss: Path, version: str, outdir: Path) -> list[str]:
    """argv to compile the installer with Inno Setup's ISCC."""
    return [
        str(iscc),
        f"/DAppVersion={version}",
        f"/O{outdir}",
        str(iss),
    ]


def _download(url: str, expected_sha: str) -> bytes:
    with urllib.request.urlopen(url) as resp:  # noqa: S310 (pinned https URL)
        data = resp.read()
    verify_sha256(data, expected_sha)
    return data


def run(version: str, iscc: Path, staging: Path | None = None) -> int:
    """Fetch interpreter, build wheelhouse, stage, and compile the installer."""
    staging = staging or Path(tempfile.mkdtemp(prefix="ai-sw-installer-"))
    layout = stage_layout(staging)
    layout["runtime"].mkdir(parents=True, exist_ok=True)
    layout["wheelhouse"].mkdir(parents=True, exist_ok=True)

    print(f"Fetching CPython {PY_VERSION} ({PYBS_RELEASE})...", file=sys.stderr)
    archive = _download(PYBS_URL, PYBS_SHA256)
    tar_path = staging / "python.tar.gz"
    tar_path.write_bytes(archive)
    with tarfile.open(tar_path) as tf:
        tf.extractall(staging)  # unpacks a top-level "python/" dir
    extracted = staging / "python"
    for item in extracted.iterdir():
        shutil.move(str(item), str(layout["runtime"] / item.name))

    python_exe = layout["runtime"] / "python.exe"
    print("Building offline wheelhouse...", file=sys.stderr)
    subprocess.run(
        pip_download_argv(python_exe, layout["wheelhouse"], WHEELHOUSE_TARGETS),
        cwd=REPO_ROOT,
        check=True,
    )
    subprocess.run(
        [
            str(python_exe),
            "-m",
            "build",
            "--wheel",
            "--outdir",
            str(layout["wheelhouse"]),
        ],
        cwd=REPO_ROOT,
        check=True,
    )

    shutil.copy2(REPO_ROOT / "installer" / "ai-sw-bridge.iss", layout["iss"])
    shutil.copy2(REPO_ROOT / "installer" / "README-first.txt", layout["readme"])

    outdir = REPO_ROOT / "dist"
    outdir.mkdir(exist_ok=True)
    print("Compiling installer with ISCC...", file=sys.stderr)
    subprocess.run(iscc_argv(iscc, layout["iss"], version, outdir), check=True)
    print(f"Installer written under {outdir}", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the ai-sw-bridge installer")
    parser.add_argument("--version", required=True, help="Installer version string")
    parser.add_argument(
        "--iscc",
        type=Path,
        default=Path("ISCC.exe"),
        help="Path to Inno Setup's ISCC.exe (default: on PATH)",
    )
    parser.add_argument(
        "--staging",
        type=Path,
        default=None,
        help="Staging dir (default: a fresh temp dir)",
    )
    args = parser.parse_args()
    return run(args.version, args.iscc, args.staging)


if __name__ == "__main__":
    sys.exit(main())
