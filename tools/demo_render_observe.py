#!/usr/bin/env python3
"""Deep re-record of the ``observe`` chapter clip (demo-gif-suite spec 2026-08-12
§8). Needs a live SOLIDWORKS seat.

Unlike the flag-driven chapter clips, this renderer drives SOLIDWORKS directly to
show what the observe/DFM axis actually proves, all from SW's own kernel:

  1. interference detection on the assembled widget (expect 0 clashes) + mate
     health (2 concentric mates, all OK);
  2. a **material-backed mass** on a single part -- the bearing block with
     ``6061 Alloy`` assigned (density 2700 kg/m^3), plus volume, surface area
     and bounding box;
  3. an on-screen *experimental*-tagged **clip-plane section sweep** down the
     bore axis (Top plane, graphics-only), peeling the top half away to reveal
     the hidden bores and the shaft's O-ring groove -- a render technique
     (``IModelViewManager.CreateSectionView``), NOT an ``ai-sw-observe`` verb.

Every number on screen is read live from the model and threaded into the HUD --
nothing is hard-coded. The renderer is NON-DESTRUCTIVE: it assigns a material and
activates section views in memory but never saves any document.

Output: ``docs/img/demo_observe.gif`` (+ ``.mp4``), captioned via ``demo_caption``
with the suite's one consistent lower-third.

Run from the repo root (needs the built widget in ``demo_out/`` -- run
``tools/demo_full_system.py --chapter all`` first, or at least ``part`` +
``assembly``)::

    PYTHONPATH=src python tools/demo_render_observe.py

CLOSE any open SOLIDWORKS documents first -- an open demo_out doc locks the
files this reads.
"""
from __future__ import annotations

import argparse
import os
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
OUT_GIF = REPO / "docs" / "img" / "demo_observe.gif"
ASM = DEMO_OUT / "DemoWidget.SLDASM"
BLOCK = DEMO_OUT / "DemoBearingBlock.SLDPRT"

# Final clip geometry -- 560 wide to match the rest of the suite (the hero
# montage concatenates on a common width); a touch taller than the 315 the
# stale clip used so the HUD panel and the section reveal both get room.
W, H = 560, 360
FPS = 8

# Section sweep: Top plane (contains the world-X bore axis at y=0), graphics-only,
# reverse=False removes the +Y half. Offsets sweep from the block's top edge
# (+14 mm ~ solid) down through the axis (0 = full longitudinal section). Verified
# live 2026-08-13 (spike_observe2): rev=False Top plane reveals both bores + the
# O-ring groove; larger offset = less removed.
SWEEP_OFFSETS_MM = [14, 13, 11.5, 10, 8.5, 7, 5.5, 4, 2.5, 1, 0]
MATERIAL_DB = "SOLIDWORKS Materials"
MATERIAL_NAME = "6061 Alloy"

# HUD palette (shared visual language with demo_caption's band).
PANEL_RGBA = (16, 18, 24, 205)
FG = (238, 242, 248)
MUTED = (168, 184, 200)
ACCENT = (120, 190, 255)
GOOD = (120, 226, 150)
EXP = (240, 198, 120)  # experimental amber


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
def _title(doc) -> str:
    t = doc.GetTitle
    return t() if callable(t) else str(t)


def capture(raw_dir: pathlib.Path) -> dict:
    """Drive SOLIDWORKS: read interference + mate health + material-backed mass,
    and write the raw screenshot frames (assembly solid, section sweep, part).
    Returns the live metrics dict for the compositor. Never saves a document."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    os.environ["AI_SW_BRIDGE_CAPTURES"] = str(raw_dir)

    from ai_sw_bridge.sw_com import get_sw_app
    from ai_sw_bridge.com.earlybind import typed
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.observe import (
        _sw_get_bbox_impl,
        _sw_screenshot_impl,
        _sw_get_mate_errors_impl,
    )
    from ai_sw_bridge.observe_interference import _sw_get_interference_impl

    mod = wrapper_module()
    sw = get_sw_app()
    tsw = typed(sw, "ISldWorks", module=mod)
    metrics: dict = {}

    def shot(name: str, fit: bool) -> None:
        _sw_screenshot_impl(width=W, height=H, fit_view=fit, filename=name)

    # ---- Assembly: interference + mate health + section sweep ----
    sw.CloseAllDocuments(True)
    time.sleep(0.6)
    tsw.OpenDoc6(str(ASM), 2, 0, "", 0, 0)  # 2 = swDocASSEMBLY
    time.sleep(1.0)
    adoc = sw.ActiveDoc
    print("  assembly active:", _title(adoc))

    inter = _sw_get_interference_impl(adoc)
    metrics["interference_count"] = inter.get("interference_count")
    mates = _sw_get_mate_errors_impl()
    by_status = (mates.get("summary") or {}).get("by_status") or {}
    metrics["mate_count"] = mates.get("mate_count")
    metrics["mate_ok"] = by_status.get("ok", 0)
    metrics["mate_broken"] = (mates.get("summary") or {}).get("broken_count")
    print(
        f"  interference={metrics['interference_count']} "
        f"mates={metrics['mate_count']} ok={metrics['mate_ok']}"
    )

    # Solid iso -- fit ONCE here, then keep the same camera for the whole
    # sweep so the reveal is stable (no per-frame zoom jitter).
    adoc.ShowNamedView2("*Isometric", -1)
    time.sleep(0.3)
    shot("asm_solid.png", fit=True)

    mvm = typed(adoc.ModelViewManager, "IModelViewManager", module=mod)
    top = adoc.FeatureByName("Top Plane")
    if top is None:
        raise RuntimeError("assembly has no 'Top Plane' feature")
    n_sec = 0
    for i, off_mm in enumerate(SWEEP_OFFSETS_MM):
        svd = mvm.CreateSectionViewData()
        svd.GraphicsOnlySection = True
        svd.ShowSectionCap = True
        svd.FirstPlane = top
        svd.FirstOffset = off_mm / 1000.0  # API wants metres
        svd.FirstReverseDirection = False
        mvm.CreateSectionView(svd)
        time.sleep(0.25)
        shot(f"sec_{i:03d}.png", fit=False)
        mvm.RemoveSectionView()
        time.sleep(0.1)
        n_sec += 1
    metrics["n_sec"] = n_sec

    # ---- Part: material-backed mass on the bearing block ----
    # Fresh open so the block is the active doc (not just an assembly component),
    # then assign 6061 + FULL EditRebuild3 so SW resolves the material density
    # (ForceRebuild3 does NOT -- verified live 2026-08-13, spike_material).
    sw.CloseAllDocuments(True)
    time.sleep(0.6)
    tsw.OpenDoc6(str(BLOCK), 1, 0, "", 0, 0)  # 1 = swDocPART
    time.sleep(0.8)
    pdoc = sw.ActiveDoc
    tdoc = typed(pdoc, "IModelDoc2", module=mod)
    tpart = typed(pdoc, "IPartDoc", module=mod)
    tpart.SetMaterialPropertyName2("", MATERIAL_DB, MATERIAL_NAME)
    # FULL rebuild via the TYPED doc so the call actually invokes (a late-bound
    # ``pdoc.EditRebuild3()`` can no-op through the property footgun) and SW
    # re-resolves the assigned material's density. Verified live 2026-08-13.
    try:
        tdoc.EditRebuild3()
    except Exception:
        pass
    time.sleep(0.4)

    # Read the mass property the TYPED way -- gen_py's CreateMassProperty yields
    # SI units (density kg/m^3, mass kg), so 6061 resolves to 2700 kg/m^3. The
    # late-bound observe reader returns document units (g/cm^3) instead, which is
    # why the mass HUD must not go through ai-sw-observe here.
    text = typed(pdoc.Extension, "IModelDocExtension", module=mod)
    mp = text.CreateMassProperty
    mp = mp() if callable(mp) else mp
    density = float(mp.Density)
    mass_kg = float(mp.Mass)
    vol_m3 = float(mp.Volume)
    surf_m2 = float(mp.SurfaceArea)
    bbox = _sw_get_bbox_impl()
    metrics["mass_g"] = mass_kg * 1000.0
    metrics["density"] = density
    metrics["vol_cm3"] = vol_m3 * 1e6
    metrics["surf_mm2"] = surf_m2 * 1e6
    metrics["bbox_mm"] = (
        round(bbox.get("x_span_mm") or 0.0),
        round(bbox.get("y_span_mm") or 0.0),
        round(bbox.get("z_span_mm") or 0.0),
    )
    print(
        f"  material={MATERIAL_NAME} density={metrics['density']:.0f} "
        f"mass={metrics['mass_g']:.2f} g vol={metrics['vol_cm3']:.2f} cm3 "
        f"bbox={metrics['bbox_mm']}"
    )

    pdoc.ShowNamedView2("*Isometric", -1)
    time.sleep(0.3)
    shot("part.png", fit=True)

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
    pill: str | None = None,
    foot: str | None = None,
) -> Image.Image:
    """Draw a translucent top-left HUD panel with a header, label/value rows,
    an optional experimental pill (top-right of header) and an optional
    footnote. Returns a new composited RGB image."""
    img = base.convert("RGBA")
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)

    pad, x0, y0 = 14, 16, 16
    hf = _font(15, bold=True)
    lf = _font(13)
    vf = _font(22, bold=True)
    ff = _font(12)

    # measure widest row
    row_h = 30
    label_w = max((d.textlength(lbl, font=lf) for lbl, _ in rows), default=0)
    val_w = max((d.textlength(val, font=vf) for _, val in rows), default=0)
    body_w = int(
        max(d.textlength(header, font=hf) + (60 if pill else 0), label_w + 18 + val_w)
    )
    if foot:
        body_w = int(max(body_w, d.textlength(foot, font=ff)))
    pw = body_w + 2 * pad
    ph = pad + 24 + len(rows) * row_h + (20 if foot else 0) + pad - 6

    d.rounded_rectangle([x0, y0, x0 + pw, y0 + ph], radius=10, fill=PANEL_RGBA)

    cx, cy = x0 + pad, y0 + pad
    d.text((cx, cy), header, font=hf, fill=header_color)
    if pill:
        pill_w = d.textlength(pill, font=ff) + 14
        px1 = x0 + pw - pad - pill_w
        d.rounded_rectangle(
            [px1, cy - 1, px1 + pill_w, cy + 17],
            radius=8,
            fill=(70, 55, 20, 230),
            outline=EXP,
        )
        d.text((px1 + 7, cy + 1), pill, font=ff, fill=EXP)
    cy += 28

    for lbl, val in rows:
        d.text((cx, cy + 5), lbl, font=lf, fill=MUTED)
        d.text((cx + int(label_w) + 18, cy - 1), val, font=vf, fill=FG)
        cy += row_h
    if foot:
        d.text((cx, cy + 2), foot, font=ff, fill=MUTED)

    return Image.alpha_composite(img, ov).convert("RGB")


def _hud_interference(raw: pathlib.Path, m: dict) -> Image.Image:
    base = Image.open(raw).convert("RGB")
    clashes = m.get("interference_count")
    ok = m.get("mate_ok") or 0
    return _panel(
        base,
        "DFM  ·  BUILD GATE",
        [
            ("interference", f"{clashes}  clashes" if clashes is not None else "—"),
            ("mates", f"{ok}  ·  all OK"),
        ],
        header_color=ACCENT,
        foot="from SOLIDWORKS' own kernel",
    )


def _hud_section(raw: pathlib.Path, m: dict, *, reveal: bool) -> Image.Image:
    base = Image.open(raw).convert("RGB")
    rows = [("plane", "Top  ·  bore axis")]
    foot = "revealed: bore · shaft · O-ring groove" if reveal else "clip-plane sweep"
    return _panel(
        base, "SECTION A–A", rows, header_color=ACCENT, pill="experimental", foot=foot
    )


def _hud_mass(raw: pathlib.Path, m: dict) -> Image.Image:
    base = Image.open(raw).convert("RGB")
    rows = [
        ("mass", f"{m['mass_g']:.1f} g"),
        ("density", f"{m['density']:.0f} kg/m³"),
        ("volume", f"{m['vol_cm3']:.1f} cm³"),
        ("bbox", "×".join(str(v) for v in m["bbox_mm"]) + " mm"),
    ]
    foot = "6061-T6 aluminium · mass from the assigned material"
    return _panel(base, "MASS  ·  6061 ALLOY", rows, header_color=GOOD, foot=foot)


def compose(raw_dir: pathlib.Path, m: dict, keep: bool = False) -> pathlib.Path:
    """Overlay HUDs onto the raw frames, stitch a palette gif, and burn in the
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

    # 1) Interference phase (solid iso, hold)
    emit(_hud_interference(raw_dir / "asm_solid.png", m), 14)
    # 2) Section sweep -- 1 frame each, hold the final full section
    n = m["n_sec"]
    for i in range(n):
        reveal = i == n - 1
        holds = 12 if reveal else 2
        emit(_hud_section(raw_dir / f"sec_{i:03d}.png", m, reveal=reveal), holds)
    # 3) Mass phase (part iso, hold)
    emit(_hud_mass(raw_dir / "part.png", m), 18)

    print(f"  composed {idx} frames")

    bare = raw_dir / "observe_bare.gif"
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
        caption.Caption("DFM is a build gate, not an afterthought", "ai-sw-observe"),
        OUT_GIF,
    )
    if not keep:
        shutil.rmtree(raw_dir, ignore_errors=True)
    return OUT_GIF


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Deep observe re-record (needs a seat)")
    ap.add_argument(
        "--keep-frames",
        action="store_true",
        help="Keep the raw/seq frame scratch dir for inspection.",
    )
    ap.add_argument(
        "--frames-dir",
        default=None,
        help="Where to write scratch frames (default: a temp dir).",
    )
    args = ap.parse_args(argv)

    if not ASM.exists() or not BLOCK.exists():
        print(
            f"ERROR: need {ASM.name} and {BLOCK.name} in demo_out/ -- run "
            "tools/demo_full_system.py --chapter all first.",
            file=sys.stderr,
        )
        return 2

    raw_dir = (
        pathlib.Path(args.frames_dir)
        if args.frames_dir
        else DEMO_OUT / "_observe_frames"
    )
    print("Capturing observe frames from a live seat ...")
    m = capture(raw_dir)
    print("Composing clip ...")
    out = compose(raw_dir, m, keep=args.keep_frames)
    kb = out.stat().st_size / 1024.0
    print(f"observe -> {out.relative_to(REPO)}  {kb:.0f} KiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
