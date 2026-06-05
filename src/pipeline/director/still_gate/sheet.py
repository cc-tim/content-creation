from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

_THUMB_W = 480
_THUMB_H = 270
_LABEL_H = 28
_PAD = 8
_BG = (24, 18, 11)
_FG = (235, 225, 200)


def build_contact_sheet(
    items: list[tuple[str, Path, str]],
    out: Path,
    *,
    columns: int = 4,
) -> Path:
    """Grid the per-scene stills with a `scene_id · meta` caption under each."""
    cell_w = _THUMB_W + 2 * _PAD
    cell_h = _THUMB_H + _LABEL_H + 2 * _PAD
    rows = math.ceil(len(items) / columns) if items else 1
    sheet = Image.new("RGB", (cell_w * columns, cell_h * rows), _BG)
    draw = ImageDraw.Draw(sheet)

    for idx, (scene_id, png, meta) in enumerate(items):
        r, c = divmod(idx, columns)
        x0, y0 = c * cell_w + _PAD, r * cell_h + _PAD
        with Image.open(png) as thumb:
            thumb = thumb.convert("RGB").resize((_THUMB_W, _THUMB_H))
            sheet.paste(thumb, (x0, y0))
        draw.text((x0, y0 + _THUMB_H + 6), f"{scene_id} · {meta}", fill=_FG)

    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out
