"""Model sheets: an engine-drawn reference page for one bank character (turnaround,
expressions, palette). Ports SHEET (`character_tim.py` 39-98, the round-4 style tryout Tim
approved) onto the resource bank: the character's `Look` (`toon.render._look`), the
`stand_rest` pose for a five-angle turnaround, every bank expression applied to the head, and
`style.palette` swatches. Labels are drawn with `PIL.ImageFont.load_default` -- the only place
in `src/toon` that draws text, because a model sheet is a reference document, not animation.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from toon.bank import Bank
from toon.cairo_compat import cairo
from toon.engine.camera import orbit
from toon.engine.head import draw_head
from toon.engine.mathx import V
from toon.engine.order import character_parts, run
from toon.engine.paper import composite
from toon.engine.pen import Pen
from toon.engine.rig import HIP_STAND, rig
from toon.render import _look
from toon.timeline import pose_of

# The camera math below (orbit distance/focal) is tuned to a 1920x1080 reference frame -- the
# same frame the approved tryout sheet used -- so angles/faces keep the same proportions
# regardless of how large the actual canvas grows to fit more bank content.
_REF_W, _REF_H = 1920, 1080

_ANGLES = (0, 45, 90, 135, 180)
_TURN_X0, _TURN_DX, _TURN_Y = 150, 270, 290
_FACE_X0, _FACE_DX, _FACE_Y, _FACE_R = 130, 190, 690, 70
_PAL_X0, _PAL_Y0, _PAL_DX, _PAL_DY, _PAL_COLS = 130, 900, 160, 150, 6
_PAL_BOX = (100, 80)
_LABEL_COLOR = (90, 86, 84)
# PIL.ImageFont.load_default() is a small bitmap font: it has no glyph for an em dash or curly
# quotes (bank provenance notes are free text and may contain either), so unsupported
# characters would otherwise draw as tofu boxes. Bank-derived label text is normalized through
# this before drawing; labels we author ourselves just avoid the characters in the first place.
_ASCII_SUBS = {"—": "--", "–": "-", "‘": "'", "’": "'", "“": '"', "”": '"'}


def _ascii_safe(text: str) -> str:
    for bad, good in _ASCII_SUBS.items():
        text = text.replace(bad, good)
    return text


def _font() -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=26)
    except TypeError:  # older Pillow: load_default() takes no size
        return ImageFont.load_default()


def _pen(ctx, bank: Bank, zoom: float) -> Pen:
    # Fixed boil=0: a model sheet is a static reference, not a drawing-on-twos animation, so
    # every stroke uses the same (single) doodle seed. mode/shimmer still come from the bank so
    # the sheet reflects Tim's chosen line-boil style (soft/full/still).
    return Pen(ctx, 0, zoom=zoom, px=1.0, mode=bank.style.boil.mode, shimmer=bank.style.boil.shimmer)


def _turnaround(ctx, bank: Bank, look, pose, az: float, center: tuple[float, float]) -> None:
    cam = orbit(az, 5, 60, V(0, 2.1, 0), 60 * 62, _REF_W, _REF_H,
                shift=(center[0] - _REF_W / 2, center[1] - _REF_H / 2))
    pen = _pen(ctx, bank, zoom=0.55)
    parts, _rg = character_parts(pen, cam, look, pose, HIP_STAND, 0.0, 0.0, HIP_STAND)
    run(parts.low + parts.high)


def _face(ctx, bank: Bank, look, pose, center: tuple[float, float]) -> None:
    rg = rig(pose, 0.0, root=HIP_STAND, yaw=0.0)
    cam = orbit(18, 4, 60, rg["head"], 60 * _FACE_R, _REF_W, _REF_H,
                shift=(center[0] - _REF_W / 2, center[1] - _REF_H / 2))
    pen = _pen(ctx, bank, zoom=0.55)
    draw_head(pen, cam, rg, pose, 0.0, look)


def _palette_swatch(ctx, bank: Bank, color, x: float, y: float) -> None:
    w, h = _PAL_BOX
    ink = bank.style.line.get("ink", (0.11, 0.10, 0.10))
    ctx.rectangle(x, y, w, h)
    ctx.set_source_rgb(*color)
    ctx.fill_preserve()
    ctx.set_source_rgb(*ink)
    ctx.set_line_width(3)
    ctx.stroke()


def model_sheet(bank: Bank, character: str, out_path: Path) -> Path:
    """Render `character`'s model sheet (turnaround + expressions + palette) and save it as
    `<out_path>/<character>_model_sheet.png`. Returns the saved file's path."""
    out_dir = Path(out_path)
    look = _look(bank, character)
    picked = bank.characters[character].picked

    expr_names = list(bank.expressions)
    palette_names = list(bank.style.palette)
    pal_rows = -(-len(palette_names) // _PAL_COLS)  # ceil
    canvas_w = max(_TURN_X0 + (len(_ANGLES) - 1) * _TURN_DX + 250,
                   _FACE_X0 + (len(expr_names) - 1) * _FACE_DX + 250,
                   _PAL_X0 + _PAL_COLS * _PAL_DX + 100)
    canvas_h = max(_PAL_Y0 + pal_rows * _PAL_DY + 150, _FACE_Y + 250)

    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, canvas_w, canvas_h)
    ctx = cairo.Context(surf)

    turn_pose = pose_of(bank, "stand_rest", "neutral")
    for i, az in enumerate(_ANGLES):
        _turnaround(ctx, bank, look, turn_pose, az, (_TURN_X0 + i * _TURN_DX, _TURN_Y))

    for i, name in enumerate(expr_names):
        expr_pose = pose_of(bank, "stand_rest", name)
        _face(ctx, bank, look, expr_pose, (_FACE_X0 + i * _FACE_DX, _FACE_Y))

    for i, name in enumerate(palette_names):
        col, row = i % _PAL_COLS, i // _PAL_COLS
        _palette_swatch(ctx, bank, bank.style.palette[name],
                        _PAL_X0 + col * _PAL_DX, _PAL_Y0 + row * _PAL_DY)

    img = Image.fromarray(composite(surf, canvas_w, canvas_h, bank.style.grain)[..., [2, 1, 0]])
    d = ImageDraw.Draw(img)
    font = _font()
    d.text((20, 12), _ascii_safe(f"{character} - model sheet ({picked.date}, {picked.source})"),
           fill=_LABEL_COLOR, font=font)
    for i, az in enumerate(_ANGLES):
        d.text((_TURN_X0 + i * _TURN_DX - 35, _TURN_Y + 180), f"{az}°", fill=_LABEL_COLOR, font=font)
    for i, name in enumerate(expr_names):
        d.text((_FACE_X0 + i * _FACE_DX - 50, _FACE_Y + 110), name, fill=_LABEL_COLOR, font=font)
    for i, name in enumerate(palette_names):
        col, row = i % _PAL_COLS, i // _PAL_COLS
        d.text((_PAL_X0 + col * _PAL_DX, _PAL_Y0 + row * _PAL_DY + _PAL_BOX[1] + 5), name,
               fill=_LABEL_COLOR, font=font)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{character}_model_sheet.png"
    img.save(out_file)
    return out_file
