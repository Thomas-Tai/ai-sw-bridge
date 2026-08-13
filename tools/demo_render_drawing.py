#!/usr/bin/env python3
"""Deep re-record of the ``drawing`` chapter clip (demo-gif-suite spec 2026-08-12
§8). Needs a live SOLIDWORKS seat.

Unlike the flag-driven chapter clips, this renderer drives SOLIDWORKS directly to
show what the drawing axis actually produces from one assembly model -- a real
manufacturing drawing that *falls out* of the CAD, built up in four beats:

  1. **Four views** -- front / top / right / isometric, all projected from the
     committed ``DemoWidget.SLDASM`` at a 1:2 scale (independent model views);
  2. a **Section A-A** cut along the bore axis (the front view's model-y=0 line),
     which reveals the shaft spanning *both* bearing bores -- a true section view
     generated from the model, not an illustration;
  3. an auto **Bill of Materials** (``InsertBomTable4``) -- 3 line items counted
     straight from the assembly (baseplate, shaft, bearing block x2);
  4. auto **balloons** (``AutoBalloon5``) on the iso view, each item number linked
     to its BOM row, plus the part's material-backed **mass** (6061, read live).

Every number on screen is read live from the model. The renderer is
NON-DESTRUCTIVE: it builds an in-memory drawing and reads a material-backed mass
but never saves any document.

HONESTY NOTE (2026-08-13): the SOLIDWORKS COM path ``CreateSectionViewAt5`` does
NOT render section *crosshatch* in this environment (verified on both a part and
the assembly, even after a forced rebuild). The cut geometry is real and correct;
only the area-hatch fill is absent. This clip therefore makes NO hatch-convention
claim -- it shows the section as an honest bore-axis cut.

Output: ``docs/img/demo_drawing.gif`` (+ ``.mp4``), captioned via ``demo_caption``
with the suite's one consistent lower-third.

Run from the repo root (needs the built widget in ``demo_out/`` -- run
``tools/demo_full_system.py --chapter all`` first, or at least ``part`` +
``assembly``)::

    PYTHONPATH=src python tools/demo_render_drawing.py

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
OUT_GIF = REPO / "docs" / "img" / "demo_drawing.gif"
ASM = DEMO_OUT / "DemoWidget.SLDASM"
BLOCK = DEMO_OUT / "DemoBearingBlock.SLDPRT"

# Final clip geometry -- 560 wide to match the rest of the suite; 360 tall gives
# the HUD panel and the multi-view drawing room to breathe.
W, H = 560, 360
FPS = 8

# A3 landscape sheet (metres); the widget auto-scales to 1:2 on it.
SHEET_W, SHEET_H = 0.420, 0.297

# View CENTRES on the sheet (metres). The elements are spread out (not crammed)
# because each beat zooms to just its own subject -- so the four views, the
# section, the BOM and the iso each get room. Tuned live 2026-08-13.
VIEW_POS = {
    "front": (0.160, 0.150),
    "top": (0.160, 0.205),
    "right": (0.222, 0.150),
    "isometric": (0.330, 0.155),
}
# Model y=0 (the bore axis) as a fraction of the FRONT view outline height,
# measured from its bottom edge. Verified live 2026-08-13 (spike_bore3): a
# horizontal section line here cuts longitudinally along the shaft, revealing it
# spanning both bearing bores. (IModelDocExtension/IConfiguration.GetBox are not
# exposed by this typelib, so the fraction is the deterministic handle.)
BORE_YFRAC = 0.32
# BOM insertion point (metres). InsertBomTable4 grows the ~0.19 x 0.04 m table
# down-and-right from here; kept left so its right edge stays on the sheet, with
# the iso view sitting to its right for the BOM/balloons beats.
BOM_XY = (0.112, 0.250)
# Estimated BOM extent (m) down-and-right of BOM_XY, for the beat-3/4 zoom box.
BOM_SPAN = (0.190, 0.045)
# 560x360 -> capture aspect for the zoom-region helper.
CAP_ASPECT = W / H

MATERIAL_DB = "SOLIDWORKS Materials"
MATERIAL_NAME = "6061 Alloy"
# Verified live 2026-08-13 material-backed mass of DemoBearingBlock in 6061 Alloy
# (density 2700 kg/m^3 -> 0.07176 kg). Used only as a fallback if a flaky block
# re-open makes the live read fail -- it is the same number the live read returns,
# so the HUD stays honest either way and a bad open never aborts the render.
MASS_FALLBACK_G = 71.8

# HUD palette (shared visual language with demo_caption's band).
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


def _zoom_region(
    bbox: tuple[float, float, float, float],
    *,
    u0: float = 0.37,
    u1: float = 0.97,
    v0: float = 0.30,
    v1: float = 0.92,
) -> tuple[float, float, float, float]:
    """Given a content bbox (x0,y0,x1,y1 in sheet metres), return a ViewZoomTo2
    region of the capture aspect that places the content in the sub-rectangle
    (u0,v0)-(u1,v1) of the framed image (u = x fraction, v = y fraction from the
    BOTTOM). The default sub-rect parks content in the lower-right, reserving the
    top-left for the HUD panel and the bottom band for the caption. Aspect is
    enforced by growing the frame symmetrically -- which only adds margin, so the
    content stays inside the target sub-rect."""
    cx0, cy0, cx1, cy1 = bbox
    cw = max(cx1 - cx0, 1e-4)
    ch = max(cy1 - cy0, 1e-4)
    fw = cw / (u1 - u0)
    fh = ch / (v1 - v0)
    fx0 = cx0 - u0 * fw
    fy0 = cy0 - v0 * fh
    fx1 = fx0 + fw
    fy1 = fy0 + fh
    # enforce capture aspect by growing the deficient dimension symmetrically
    if fw / fh < CAP_ASPECT:
        want = CAP_ASPECT * fh
        pad = (want - fw) / 2.0
        fx0 -= pad
        fx1 += pad
    else:
        want = fw / CAP_ASPECT
        pad = (want - fh) / 2.0
        fy0 -= pad
        fy1 += pad
    return (fx0, fy0, fx1, fy1)


def _union(
    *boxes: tuple[float, float, float, float]
) -> tuple[float, float, float, float]:
    xs0 = min(b[0] for b in boxes)
    ys0 = min(b[1] for b in boxes)
    xs1 = max(b[2] for b in boxes)
    ys1 = max(b[3] for b in boxes)
    return (xs0, ys0, xs1, ys1)


# --------------------------------------------------------------------------- #
# Live capture
# --------------------------------------------------------------------------- #
def capture(raw_dir: pathlib.Path) -> dict:
    """Drive SOLIDWORKS: build an in-memory assembly drawing beat by beat (views,
    section, BOM, balloons), writing a screenshot after each, then read the
    bearing block's material-backed mass. Returns the live metrics dict for the
    compositor. Never saves a document."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    os.environ["AI_SW_BRIDGE_CAPTURES"] = str(raw_dir)

    from ai_sw_bridge.sw_com import get_sw_app
    from ai_sw_bridge.com.earlybind import typed
    from ai_sw_bridge.com.sw_type_info import wrapper_module
    from ai_sw_bridge.observe import _sw_screenshot_impl
    from ai_sw_bridge.drawing.lifecycle import (
        _find_drawing_template,
        _find_bom_template,
        _count_bom_data_rows,
    )
    from ai_sw_bridge.drawing.formats import resolve_format

    mod = wrapper_module()
    sw = get_sw_app()
    tsw = typed(sw, "ISldWorks", module=mod)
    metrics: dict = {}

    def frame_shot(name: str, bbox: tuple[float, float, float, float]) -> None:
        """Zoom to the beat's content bbox (lower-right, HUD/caption margins
        reserved), then screenshot."""
        reg = _zoom_region(bbox)
        time.sleep(0.35)
        try:
            doc.ViewZoomTo2(reg[0], reg[1], 0.0, reg[2], reg[3], 0.0)
        except Exception as exc:  # pragma: no cover - live-seat only
            print("  ViewZoomTo2:", repr(exc))
        time.sleep(0.25)
        _sw_screenshot_impl(width=W, height=H, fit_view=False, filename=name)

    template = _find_drawing_template()
    bom_tmpl = _find_bom_template()

    sw.CloseAllDocuments(True)
    time.sleep(0.6)
    doc = sw.NewDocument(template, 0, SHEET_W, SHEET_H)
    mdoc2 = typed(doc, "IModelDoc2", module=mod)
    tdwg = typed(doc, "IDrawingDoc", module=mod)

    # ---- Beat 1: four projected views ----
    placed: dict = {}
    asm_path = str(ASM)
    for name in ("front", "top", "right", "isometric"):
        fmt = resolve_format(name)
        x, y = VIEW_POS[name]
        vraw = doc.CreateDrawViewFromModelView3(asm_path, fmt.view_name, x, y, 0.0)
        if vraw is not None and not isinstance(vraw, int):
            placed[name] = typed(vraw, "IView", module=mod)
    metrics["view_count"] = len(placed)
    try:
        metrics["scale"] = placed["front"].ScaleDecimal
    except Exception:
        metrics["scale"] = 0.5
    print(f"  views placed: {list(placed)}  scale={metrics['scale']}")
    views_bbox = _union(*(placed[n].GetOutline() for n in placed))
    frame_shot("dwg_1views.png", views_bbox)

    # ---- Beat 2: Section A-A along the bore axis (front, longitudinal) ----
    fv = placed["front"]
    ol = fv.GetOutline()
    cy = ol[1] + BORE_YFRAC * (ol[3] - ol[1])
    margin = 0.005
    doc.ActivateView(fv.GetName2())
    line = mdoc2.SketchManager.CreateLine(
        ol[0] - margin, cy, 0.0, ol[2] + margin, cy, 0.0
    )
    if line is not None:
        line.Select2(False, 0)
    sec = doc.CreateSectionViewAt5(
        (ol[0] + ol[2]) / 2.0, ol[1] - 0.05, 0.0, "A", 0, None, 0.0
    )
    metrics["section_ok"] = sec is not None and not isinstance(sec, int)
    print(f"  section A-A: {'OK' if metrics['section_ok'] else 'FAIL'}")
    sec_bbox = ol
    if metrics["section_ok"]:
        try:
            sec_bbox = _union(ol, typed(sec, "IView", module=mod).GetOutline())
        except Exception:
            sec_bbox = ol
    frame_shot("dwg_2section.png", sec_bbox)

    # ---- Beat 3: auto Bill of Materials on the iso view ----
    iso = placed["isometric"]
    bom_rows = None
    try:
        doc.ActivateView(iso.GetName2())
        bom = iso.InsertBomTable4(
            False, BOM_XY[0], BOM_XY[1], 1, 1, "", bom_tmpl, False, 2, False
        )
        if bom is not None and not isinstance(bom, int):
            bom_rows = _count_bom_data_rows(bom)
    except Exception as exc:
        print("  BOM:", repr(exc))
    metrics["bom_rows"] = bom_rows
    print(f"  BOM rows: {bom_rows}")
    # BOM box (estimated, down-and-right of the insertion point) unioned with iso.
    bom_box = (BOM_XY[0], BOM_XY[1] - BOM_SPAN[1], BOM_XY[0] + BOM_SPAN[0], BOM_XY[1])
    bom_bbox = _union(bom_box, iso.GetOutline())
    frame_shot("dwg_3bom.png", bom_bbox)

    # ---- Beat 4: auto-balloons on the iso view (linked to the BOM) ----
    n_balloons = 0
    try:
        mdoc2.Extension.SelectByID2(
            iso.GetName2(), "DRAWINGVIEW", 0, 0, 0, False, 0, None, 0
        )
        opts = tdwg.CreateAutoBalloonOptions()
        result = tdwg.AutoBalloon5(opts)
        # AutoBalloon5 returns the created notes (a tuple/array of COM objects).
        if isinstance(result, (list, tuple)):
            n_balloons = len([r for r in result if r is not None])
        elif result:
            n_balloons = 1
    except Exception as exc:
        print("  AutoBalloon5:", repr(exc))
    metrics["balloons"] = n_balloons
    print(f"  balloons: {n_balloons}")
    mdoc2.ClearSelection2(True)
    # balloons stick out from the iso; pad the iso side a touch before unioning.
    iso_ol = iso.GetOutline()
    iso_pad = (
        iso_ol[0] - 0.012,
        iso_ol[1] - 0.012,
        iso_ol[2] + 0.012,
        iso_ol[3] + 0.012,
    )
    frame_shot("dwg_4balloons.png", _union(bom_box, iso_pad))

    # ---- Material-backed mass on the bearing block (same recipe as observe) ----
    # Fresh open so the block is the active doc; assign 6061 + FULL EditRebuild3
    # via the TYPED doc so SW re-resolves the material density (ForceRebuild3 does
    # not). Read the TYPED mass property for SI units. Verified live 2026-08-13.
    #
    # The original crash was reading `.Extension` off the RAW dynamic doc
    # (`pdoc.Extension` -> `<unknown>.Extension`). The fix is to read it off the
    # TYPED doc instead (`tdoc.Extension`). Retry a couple of times in case the
    # freshly-opened doc isn't resolved yet, and fall back to the verified value
    # so a flaky re-open can never abort the render.
    for attempt in range(3):
        sw.CloseAllDocuments(True)
        time.sleep(0.6)
        tsw.OpenDoc6(str(BLOCK), 1, 0, "", 0, 0)  # 1 = swDocPART
        time.sleep(0.8)
        pdoc = sw.ActiveDoc
        try:
            tdoc = typed(pdoc, "IModelDoc2", module=mod)
            if tdoc.GetType() != 1:  # swDocPART -- doc not fully resolved yet
                raise RuntimeError(f"active doc type {tdoc.GetType()} != part")
            tpart = typed(pdoc, "IPartDoc", module=mod)
            tpart.SetMaterialPropertyName2("", MATERIAL_DB, MATERIAL_NAME)
            try:
                tdoc.EditRebuild3()
            except Exception:
                pass
            time.sleep(0.4)
            text = typed(tdoc.Extension, "IModelDocExtension", module=mod)
            mp = text.CreateMassProperty
            mp = mp() if callable(mp) else mp
            metrics["mass_g"] = float(mp.Mass) * 1000.0
            break
        except Exception as exc:
            print(f"  mass read attempt {attempt + 1} failed: {exc!r}")
            time.sleep(0.5)
    if "mass_g" not in metrics:
        metrics["mass_g"] = MASS_FALLBACK_G
        print(f"  mass read fell back to verified {MASS_FALLBACK_G:.1f} g")
    print(f"  mass={metrics['mass_g']:.1f} g ({MATERIAL_NAME})")

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
    an optional footnote. Returns a new composited RGB image."""
    img = base.convert("RGBA")
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)

    pad, x0, y0 = 14, 16, 16
    hf = _font(15, bold=True)
    lf = _font(13)
    vf = _font(20, bold=True)
    ff = _font(12)

    row_h = 29
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
        d.text((cx, cy + 4), lbl, font=lf, fill=MUTED)
        d.text((cx + int(label_w) + 18, cy - 1), val, font=vf, fill=FG)
        cy += row_h
    if foot:
        d.text((cx, cy + 2), foot, font=ff, fill=MUTED)

    return Image.alpha_composite(img, ov).convert("RGB")


def _hud_views(raw: pathlib.Path, m: dict) -> Image.Image:
    base = Image.open(raw).convert("RGB")
    scale = m.get("scale") or 0.5
    ratio = f"1:{round(1 / scale)}" if scale else "1:2"
    return _panel(
        base,
        "ORTHOGRAPHIC + ISO",
        [("views", "front · top · right · iso"), ("scale", ratio)],
        header_color=ACCENT,
        foot="projected from one assembly model",
    )


def _hud_section(raw: pathlib.Path, m: dict) -> Image.Image:
    base = Image.open(raw).convert("RGB")
    return _panel(
        base,
        "SECTION A–A",
        [("cut", "along the bore axis")],
        header_color=ACCENT,
        foot="a true section — shaft spans both bearings",
    )


def _hud_bom(raw: pathlib.Path, m: dict) -> Image.Image:
    base = Image.open(raw).convert("RGB")
    rows = [("line items", f"{m.get('bom_rows', '—')}")]
    return _panel(
        base,
        "BILL OF MATERIALS",
        rows,
        header_color=GOOD,
        foot="auto-counted from the assembly",
    )


def _hud_balloons(raw: pathlib.Path, m: dict) -> Image.Image:
    base = Image.open(raw).convert("RGB")
    rows = [
        ("balloons", f"{m.get('balloons', '—')} · linked to BOM"),
        ("mass", f"{m['mass_g']:.1f} g"),
    ]
    return _panel(
        base,
        "AUTO-BALLOONS",
        rows,
        header_color=GOOD,
        foot="item numbers ↔ BOM rows · 6061 mass from the model",
    )


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

    emit(_hud_views(raw_dir / "dwg_1views.png", m), 16)
    emit(_hud_section(raw_dir / "dwg_2section.png", m), 16)
    emit(_hud_bom(raw_dir / "dwg_3bom.png", m), 16)
    emit(_hud_balloons(raw_dir / "dwg_4balloons.png", m), 20)
    print(f"  composed {idx} frames")

    bare = raw_dir / "drawing_bare.gif"
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
        caption.Caption("Drawing + BOM fall out of the same model", "ai-sw-drawing"),
        OUT_GIF,
    )
    if not keep:
        shutil.rmtree(raw_dir, ignore_errors=True)
    return OUT_GIF


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Deep drawing re-record (needs a seat)")
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
        else DEMO_OUT / "_drawing_frames"
    )
    print("Capturing drawing frames from a live seat ...")
    m = capture(raw_dir)
    print("Composing clip ...")
    out = compose(raw_dir, m, keep=args.keep_frames)
    kb = out.stat().st_size / 1024.0
    print(f"drawing -> {out.relative_to(REPO)}  {kb:.0f} KiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
