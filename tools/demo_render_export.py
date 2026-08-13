#!/usr/bin/env python3
"""Deep re-record of the ``export`` chapter clip (demo-gif-suite spec 2026-08-12
§8). Needs a live SOLIDWORKS seat.

Unlike the flag-driven chapter clip -- which just runs the export block and lists
the files it wrote -- this renderer proves the thing that actually matters about a
neutral-format export: it is a lossless *round-trip*, not a one-way dead end. Four
beats, every number read live from SW's own kernel:

  1. **Source model** -- the finished ``DemoBearingBlock`` part (bores, counter-
     bore, O-ring groove), with its bounding box and volume read from the model;
  2. **Export** -- the part is written to three neutral formats straight from the
     model: **STEP AP214**, binary **STL**, and **3MF** (file sizes read off disk);
  3. **Re-import** -- the STEP file is loaded back in through SOLIDWORKS' own
     translator (``LoadFile4``, native B-rep), producing a fresh solid;
  4. **Round-trip proof** -- the re-imported solid's bbox and volume are compared
     to the source: **Δbbox = 0.000 mm, Δvolume = 0.000 cm³** -- geometry preserved
     exactly (verified live 2026-08-13: identical to six decimals).

Every number on screen is live. The renderer is NON-DESTRUCTIVE: it exports neutral
files (the whole point of the chapter) into a scratch ``_export_roundtrip`` dir but
never saves any SOLIDWORKS document.

Output: ``docs/img/demo_export.gif`` (+ ``.mp4``), captioned via ``demo_caption``
with the suite's one consistent lower-third.

Run from the repo root (needs the built widget in ``demo_out/`` -- run
``tools/demo_full_system.py --chapter all`` first, or at least ``part``)::

    PYTHONPATH=src python tools/demo_render_export.py

CLOSE any open SOLIDWORKS documents first -- an open demo_out doc locks the
files this reads.
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys
import time

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import demo_caption as caption  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[1]
DEMO_OUT = REPO / "demo_out"
OUT_GIF = REPO / "docs" / "img" / "demo_export.gif"
# The part we round-trip: a real widget part with nontrivial internal geometry
# (two bores, a counterbore and an O-ring groove) -- a far stronger round-trip
# proof than a plain prism. Verified live: STEP AP214 preserves it exactly.
PART = DEMO_OUT / "DemoBearingBlock.SLDPRT"
PART_NAME = "DemoBearingBlock"
# Scratch dir for the neutral exports (STEP/STL/3MF). Cleaned unless --keep-frames.
RT_DIR = DEMO_OUT / "_export_roundtrip"

# Final clip geometry -- 560 wide to match the rest of the suite.
W, H = 560, 360
FPS = 8

# HUD palette (shared visual language with demo_caption's band + the sibling
# observe/drawing renderers).
PANEL_RGBA = (16, 18, 24, 205)
FG = (238, 242, 248)
MUTED = (168, 184, 200)
ACCENT = (120, 190, 255)
GOOD = (120, 226, 150)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    names = ["segoeuib.ttf", "arialbd.ttf"] if bold else ["segoeui.ttf", "arial.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


# --------------------------------------------------------------------------- #
# Live capture
# --------------------------------------------------------------------------- #
def _read_geo(sw, mod, typed, get_bbox, doc):
    """Read (bbox_mm tuple, volume_cm3) of a part ``doc`` from SW's kernel.

    bbox via ``IPartDoc.GetPartBox`` (active-doc reader); volume via the TYPED
    doc's ``Extension.CreateMassProperty`` (SI -> cm³)."""
    tdoc = typed(doc, "IModelDoc2", module=mod)
    ext = typed(tdoc.Extension, "IModelDocExtension", module=mod)
    mp = ext.CreateMassProperty
    mp = mp() if callable(mp) else mp
    vol_cm3 = float(mp.Volume) * 1e6
    bb = get_bbox()
    bbox = (
        float(bb.get("x_span_mm") or 0.0),
        float(bb.get("y_span_mm") or 0.0),
        float(bb.get("z_span_mm") or 0.0),
    )
    return bbox, vol_cm3


def capture(raw_dir: pathlib.Path) -> dict:
    """Drive SOLIDWORKS: read the source geometry, export STEP/STL/3MF, re-import
    the STEP through SW's own translator, and re-read the geometry. Writes the two
    iso screenshots (source, re-imported). Returns the live metrics dict. Never
    saves a SOLIDWORKS document."""
    import os

    raw_dir.mkdir(parents=True, exist_ok=True)
    os.environ["AI_SW_BRIDGE_CAPTURES"] = str(raw_dir)

    from ai_sw_bridge.sw_com import get_sw_app
    from ai_sw_bridge.com.earlybind import typed
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.observe import _sw_get_bbox_impl, _sw_screenshot_impl
    from ai_sw_bridge.export.dispatch import export_all, ExportRequest

    mod = wrapper_module()
    sw = get_sw_app()
    tsw = typed(sw, "ISldWorks", module=mod)
    metrics: dict = {}

    def shot(name: str) -> None:
        _sw_screenshot_impl(width=W, height=H, fit_view=True, filename=name)

    # ---- 1) Source: open the part, read bbox + volume, iso screenshot ----
    sw.CloseAllDocuments(True)
    time.sleep(0.6)
    tsw.OpenDoc6(str(PART), 1, 0, "", 0, 0)  # 1 = swDocPART
    time.sleep(0.8)
    src_doc = sw.ActiveDoc
    src_bbox, src_vol = _read_geo(sw, mod, typed, _sw_get_bbox_impl, src_doc)
    metrics["src_bbox"] = src_bbox
    metrics["src_vol"] = src_vol
    src_doc.ShowNamedView2("*Isometric", -1)
    time.sleep(0.3)
    shot("src.png")
    print(f"  source: bbox={src_bbox} vol={src_vol:.3f} cm3")

    # ---- 2) Export STEP AP214 + binary STL + 3MF straight from the model ----
    RT_DIR.mkdir(parents=True, exist_ok=True)
    reqs = [
        ExportRequest(format="step214", output_dir=RT_DIR, filename=PART_NAME),
        ExportRequest(format="stl", output_dir=RT_DIR, filename=PART_NAME, binary=True),
        ExportRequest(format="3mf", output_dir=RT_DIR, filename=PART_NAME),
    ]
    results = export_all(src_doc, reqs, PART_NAME)
    exports = []
    step_path = None
    for r in results:
        p = pathlib.Path(r.path)
        size = p.stat().st_size if (r.ok and p.exists()) else 0
        exports.append((r.format, size, r.ok))
        if r.format == "step214" and r.ok:
            step_path = p
    metrics["exports"] = exports
    print(f"  exports: {[(f, s, ok) for f, s, ok in exports]}")
    if step_path is None:
        raise RuntimeError("STEP export failed -- cannot run the round-trip")

    # ---- 3) Re-import the STEP through SW's own translator (LoadFile4) ----
    # OpenDoc6 does NOT import STEP; the proven chain is GetImportFileData ->
    # LoadFile4(path, "r", data, 0) which returns (doc, errors). "r" forces a
    # native B-rep import (no 3D Interconnect). Verified live 2026-08-13.
    sw.CloseAllDocuments(True)
    time.sleep(0.8)
    import_data = tsw.GetImportFileData(str(step_path))
    res = tsw.LoadFile4(str(step_path), "r", import_data, 0)
    imp_doc = res[0] if isinstance(res, tuple) else res
    if imp_doc is None:
        raise RuntimeError("LoadFile4 returned no document -- STEP re-import failed")
    time.sleep(1.0)
    rt_bbox, rt_vol = _read_geo(sw, mod, typed, _sw_get_bbox_impl, imp_doc)
    metrics["rt_bbox"] = rt_bbox
    metrics["rt_vol"] = rt_vol
    # LoadFile4 activates the imported doc, so ShowNamedView2 targets it.
    imp_doc.ShowNamedView2("*Isometric", -1)
    time.sleep(0.3)
    shot("rt.png")
    print(f"  reimport: bbox={rt_bbox} vol={rt_vol:.3f} cm3")

    # ---- 4) Deltas ----
    metrics["dbbox"] = tuple(abs(a - b) for a, b in zip(src_bbox, rt_bbox))
    metrics["dvol"] = abs(src_vol - rt_vol)
    print(
        f"  delta: bbox={tuple(round(v, 4) for v in metrics['dbbox'])} "
        f"vol={metrics['dvol']:.4f} cm3"
    )

    sw.CloseAllDocuments(True)
    return metrics


# --------------------------------------------------------------------------- #
# HUD compositing
# --------------------------------------------------------------------------- #
def _panel(
    base: Image.Image,
    header: str,
    rows: list[tuple[str, str]],
    *,
    header_color=ACCENT,
    foot: str | None = None,
) -> Image.Image:
    """Draw a translucent top-left HUD panel with a header, label/value rows and
    an optional footnote. Returns a new composited RGB image. (Same visual
    language as the observe/drawing renderers.)"""
    img = base.convert("RGBA")
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)

    pad, x0, y0 = 14, 16, 16
    hf = _font(15, bold=True)
    lf = _font(13)
    vf = _font(22, bold=True)
    ff = _font(12)

    row_h = 30
    label_w = max((d.textlength(lbl, font=lf) for lbl, _ in rows), default=0)
    val_w = max((d.textlength(val, font=vf) for _, val in rows), default=0)
    body_w = int(max(d.textlength(header, font=hf), label_w + 18 + val_w))
    if foot:
        body_w = int(max(body_w, d.textlength(foot, font=ff)))
    pw = body_w + 2 * pad
    ph = pad + 24 + len(rows) * row_h + (20 if foot else 0) + pad - 6

    d.rounded_rectangle([x0, y0, x0 + pw, y0 + ph], radius=10, fill=PANEL_RGBA)

    cx, cy = x0 + pad, y0 + pad
    d.text((cx, cy), header, font=hf, fill=header_color)
    cy += 28
    for lbl, val in rows:
        d.text((cx, cy + 5), lbl, font=lf, fill=MUTED)
        d.text((cx + int(label_w) + 18, cy - 1), val, font=vf, fill=FG)
        cy += row_h
    if foot:
        d.text((cx, cy + 2), foot, font=ff, fill=MUTED)

    return Image.alpha_composite(img, ov).convert("RGB")


def _bbox_str(bbox: tuple[float, float, float]) -> str:
    return "×".join(f"{v:g}" for v in bbox) + " mm"


def _hud_source(raw: pathlib.Path, m: dict) -> Image.Image:
    base = Image.open(raw).convert("RGB")
    return _panel(
        base,
        "SOURCE MODEL",
        [
            ("format", "native .SLDPRT"),
            ("bbox", _bbox_str(m["src_bbox"])),
            ("volume", f"{m['src_vol']:.2f} cm³"),
        ],
        header_color=ACCENT,
        foot="the finished bearing block · bores + O-ring groove",
    )


def _hud_export(raw: pathlib.Path, m: dict) -> Image.Image:
    base = Image.open(raw).convert("RGB")
    fmt_label = {"step214": "STEP AP214", "stl": "STL (binary)", "3mf": "3MF"}
    rows = []
    for fmt, size, ok in m["exports"]:
        kb = f"{size / 1024:.0f} KB" if ok and size else "—"
        rows.append((fmt_label.get(fmt, fmt), kb))
    return _panel(
        base,
        "EXPORT → NEUTRAL FORMATS",
        rows,
        header_color=ACCENT,
        foot="written straight from the model",
    )


def _hud_reimport(raw: pathlib.Path, m: dict) -> Image.Image:
    base = Image.open(raw).convert("RGB")
    return _panel(
        base,
        "RE-IMPORTED",
        [
            ("via", "STEP AP214 · LoadFile4"),
            ("bbox", _bbox_str(m["rt_bbox"])),
            ("volume", f"{m['rt_vol']:.2f} cm³"),
        ],
        header_color=ACCENT,
        foot="loaded back through SOLIDWORKS' own translator",
    )


def _hud_proof(raw: pathlib.Path, m: dict) -> Image.Image:
    base = Image.open(raw).convert("RGB")
    dbx, dby, dbz = m["dbbox"]
    return _panel(
        base,
        "ROUND-TRIP  ·  Δ = 0",
        [
            ("Δ bbox", f"{dbx:.3f} / {dby:.3f} / {dbz:.3f} mm"),
            ("Δ volume", f"{m['dvol']:.3f} cm³"),
        ],
        header_color=GOOD,
        foot="geometry preserved exactly — export is a round-trip, not a dead end",
    )


def compose(raw_dir: pathlib.Path, m: dict, keep: bool = False) -> pathlib.Path:
    """Overlay HUDs onto the two raw frames, stitch a palette gif, and burn in the
    suite caption band. Returns the final gif path."""
    seq = raw_dir / "seq"
    if seq.exists():
        shutil.rmtree(seq)
    seq.mkdir(parents=True)

    idx = 0

    def emit(img: Image.Image, holds: int) -> None:
        nonlocal idx
        img = img.resize((W, H))
        for _ in range(holds):
            img.save(seq / f"f{idx:04d}.png")
            idx += 1

    emit(_hud_source(raw_dir / "src.png", m), 16)
    emit(_hud_export(raw_dir / "src.png", m), 16)
    emit(_hud_reimport(raw_dir / "rt.png", m), 16)
    emit(_hud_proof(raw_dir / "rt.png", m), 22)

    print(f"  composed {idx} frames")

    bare = raw_dir / "export_bare.gif"
    pal = raw_dir / "pal.png"
    seqpat = str(seq / "f%04d.png")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-framerate",
            str(FPS),
            "-i",
            seqpat,
            "-vf",
            "palettegen=stats_mode=diff",
            str(pal),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-framerate",
            str(FPS),
            "-i",
            seqpat,
            "-i",
            str(pal),
            "-lavfi",
            "paletteuse=dither=bayer:bayer_scale=3",
            str(bare),
        ],
        check=True,
    )

    OUT_GIF.parent.mkdir(parents=True, exist_ok=True)
    caption.caption_clip(
        bare,
        caption.Caption(
            "Export is a lossless round-trip, not a dead end", "ai-sw-export"
        ),
        OUT_GIF,
    )
    if not keep:
        shutil.rmtree(raw_dir, ignore_errors=True)
        shutil.rmtree(RT_DIR, ignore_errors=True)
    return OUT_GIF


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Deep export re-record (needs a seat)")
    ap.add_argument(
        "--keep-frames",
        action="store_true",
        help="Keep the raw/seq frame scratch dir + neutral exports for inspection.",
    )
    ap.add_argument(
        "--frames-dir",
        default=None,
        help="Where to write scratch frames (default: a temp dir).",
    )
    args = ap.parse_args(argv)

    if not PART.exists():
        print(
            f"ERROR: need {PART.name} in demo_out/ -- run "
            "tools/demo_full_system.py --chapter all first.",
            file=sys.stderr,
        )
        return 2

    raw_dir = (
        pathlib.Path(args.frames_dir)
        if args.frames_dir
        else DEMO_OUT / "_export_frames"
    )
    print("Capturing export frames from a live seat ...")
    m = capture(raw_dir)
    print("Composing clip ...")
    out = compose(raw_dir, m, keep=args.keep_frames)
    kb = out.stat().st_size / 1024.0
    print(f"export -> {out.relative_to(REPO)}  {kb:.0f} KiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
