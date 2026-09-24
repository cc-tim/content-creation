"""Render-truth CJK checks with real Pillow + ffmpeg (Sprint 8, E8 item 1; A2 / B4).

Glyph distinctness, no OCR, platform-agnostic: two different CJK strings must
render differently and neither may equal the .notdef (tofu) render. Uses the
same probe implementation as `pipeline doctor`.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from pipeline.utils.fonts import (
    DEFAULT_FAMILY,
    NOTDEF_TEXT,
    drawtext_font_arg,
    glyphs_distinct,
    load_pil_font,
    probe_drawtext,
    probe_libass,
    probe_pil,
    verify_fontconfig_family,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed"),
]


def test_pil_probe_renders_distinct_cjk(tmp_path):
    r = probe_pil(tmp_path)
    assert r.ok, r.detail
    assert load_pil_font("sans", "regular", 20).getname() == ("Noto Sans CJK TC", "Regular")


def test_drawtext_probe_renders_distinct_cjk(tmp_path):
    r = probe_drawtext(tmp_path)
    assert r.ok, r.detail


def test_libass_probe_renders_distinct_cjk(tmp_path):
    r = probe_libass(tmp_path)
    assert r.ok, r.detail


def test_theme_family_not_substituted_by_fontconfig():
    for style in ("Regular", "Bold"):
        assert DEFAULT_FAMILY in verify_fontconfig_family(DEFAULT_FAMILY, style)


def _drawtext(tmp_path: Path, name: str, font_opt: str, text: str = "說為溫裡") -> Image.Image:
    out = tmp_path / f"{name}.png"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=white:s=420x110", "-frames:v", "1",
            "-vf", f"drawtext=text='{text}':{font_opt}:fontsize=72:fontcolor=black:x=8:y=12",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return Image.open(out).convert("RGB")


def _same(a: Image.Image, b: Image.Image) -> bool:
    return a.tobytes() == b.tobytes()


def test_drawtext_font_arg_style_reaches_fontconfig(tmp_path):
    """R1: the escaped fontconfig pattern selects the weight (Bold != Regular)."""
    bold = _drawtext(tmp_path, "bold", drawtext_font_arg("bold"))
    regular = _drawtext(tmp_path, "regular", drawtext_font_arg("regular"))
    assert not _same(bold, regular)


def test_drawtext_font_arg_selects_tc_not_a_substitute(tmp_path):
    """TC forms: differs from the HK face of the same family (and so is not a fallback)."""
    tc = _drawtext(tmp_path, "tc", drawtext_font_arg("bold"))
    hk = _drawtext(tmp_path, "hk", drawtext_font_arg("bold", family="Noto Sans CJK HK"))
    assert not _same(tc, hk)


def test_drawtext_regular_arg_matches_family_name_lookup(tmp_path):
    """The Regular pattern draws the same face overlays get from font='<family>'."""
    via_arg = _drawtext(tmp_path, "arg", drawtext_font_arg("regular"))
    via_family = _drawtext(tmp_path, "fam", f"font='{DEFAULT_FAMILY}'")
    assert _same(via_arg, via_family)


def test_distinctness_rejects_tofu(tmp_path):
    """Negative control: identical .notdef renders must FAIL the probe predicate."""
    box = _drawtext(tmp_path, "box", drawtext_font_arg("bold"), text=NOTDEF_TEXT * 2)
    ok, _ = glyphs_distinct(box, box, box)
    assert not ok
