"""Call-site migration + static fence for the font resolver (Sprint 8, E8 item 1).

The static fence keeps the Linux-assumption audit done: guardrails in code, not docs.
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from pipeline.utils import fonts
from pipeline.utils.fonts import FontResolutionError, drawtext_font_arg, install_hint

_SRC = Path(__file__).resolve().parents[2] / "src" / "pipeline"
_FONTS_PY = _SRC / "utils" / "fonts.py"
_CONFIG_PY = _SRC / "config.py"

# (pattern, description, files exempt from this rule)
_FENCE: list[tuple[re.Pattern[str], str, set[Path]]] = [
    # utils/fonts.py is exempt: its known-platform-dir search list is resolver step 3.
    (re.compile(r"/usr/share/fonts"), "hardcoded Linux font path", {_FONTS_PY}),
    (re.compile(r"/System/Library/Fonts"), "hardcoded macOS font path", {_FONTS_PY}),
    (re.compile(r"ImageFont\.load_default\("), "silent bitmap-font fallback", set()),
    (re.compile(r"ImageFont\.truetype\("), "font loaded outside the resolver", {_FONTS_PY}),
    # drawtext fontfile= is only built by drawtext_font_arg (a fontconfig pattern, never a path)
    (re.compile(r"fontfile="), "drawtext fontfile= outside the resolver", {_FONTS_PY}),
    (re.compile(r"""Path\(\s*["']output/"""), "cwd-relative output path literal", {_CONFIG_PY}),
    (re.compile(r"""["']output/gallery["']"""), "gallery path literal", {_CONFIG_PY}),
]


def _src_files() -> list[Path]:
    return sorted(_SRC.rglob("*.py"))


def test_static_fence_src_is_clean():
    violations: list[str] = []
    for path in _src_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for pattern, why, exempt in _FENCE:
                if path in exempt:
                    continue
                if pattern.search(line):
                    violations.append(f"{path.relative_to(_SRC)}:{lineno}: {why}: {line.strip()}")
    assert not violations, "font/path fence violations:\n" + "\n".join(violations)


@pytest.mark.parametrize(
    "snippet",
    [
        'X = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"',
        'X = "/System/Library/Fonts/PingFang.ttc"',
        "f = ImageFont.load_default()",
        "f = ImageFont.truetype(p, 12)",
        "vf = f\"drawtext=fontfile={p}:text='x'\"",
        'root = Path("output/projects")',
        'g = "output/gallery"',
    ],
)
def test_static_fence_catches_violations(snippet):
    assert any(p.search(snippet) for p, _, _ in _FENCE), snippet


# ── loud failure at every migrated PIL call site (A4) ─────────────────────────
@pytest.fixture
def no_fonts(monkeypatch):
    monkeypatch.delenv("PIPELINE_FONT_DIRS", raising=False)
    monkeypatch.setattr(fonts, "_fc_match_candidate", lambda family, style: None)
    monkeypatch.setattr(fonts, "platform_font_dirs", lambda platform=None: [])
    fonts.resolve_font.cache_clear()
    yield
    fonts.resolve_font.cache_clear()


def _assert_loud(exc_info):
    assert exc_info.value.suggested_fix == install_hint()
    assert install_hint() in str(exc_info.value)


def test_title_font_raises_when_fonts_missing(no_fonts):
    from pipeline.stages.compose import _title_font

    with pytest.raises(FontResolutionError) as ei:
        _title_font(40)
    _assert_loud(ei)


def test_running_out_raises_when_fonts_missing(no_fonts, tmp_path):
    from pipeline.composer.compartment_renderers.running_out import render_running_out_frames

    cfg = {"label": "剩餘", "stages": [{"value": "1", "face": "neutral"}]}
    with pytest.raises(FontResolutionError) as ei:
        render_running_out_frames(tmp_path, cfg, 320, 240)
    _assert_loud(ei)


def test_rich_slide_raises_when_fonts_missing(no_fonts):
    from pipeline.composer.rich_slide import _load_font

    with pytest.raises(FontResolutionError) as ei:
        _load_font("serif", "bold", 44)
    _assert_loud(ei)


def test_callout_raises_when_fonts_missing(no_fonts):
    from pipeline.composer.callout import Callout, render_callouts

    base = Image.new("RGB", (1280, 720), "white")
    with pytest.raises(FontResolutionError):
        render_callouts(
            [Callout(x=600, label="x")], base, left=128, right=1190, body_top=216,
            top_limit=90, leader_from_y=216, ink=(0, 0, 0), muted=(9, 9, 9), font_size=18,
        )


# ── migrated call sites use the resolver ─────────────────────────────────────
def test_rich_slide_load_font_delegates_to_resolver():
    from pipeline.composer.rich_slide import _load_font

    sentinel = object()
    with patch("pipeline.composer.rich_slide.load_pil_font", return_value=sentinel) as lp:
        assert _load_font("sans", "regular", 32) is sentinel
    lp.assert_called_once_with("sans", "regular", 32)


def test_title_font_is_serif_regular_tc():
    from pipeline.stages.compose import _title_font

    with patch("pipeline.stages.compose.load_pil_font", return_value="F") as lp:
        assert _title_font(40) == "F"
    lp.assert_called_once_with("serif", "regular", 40)


def test_outro_uses_fontconfig_pattern_not_file(tmp_path):
    from pipeline.outro.builder import build_outro
    from pipeline.publish.channels import ChannelProfile

    profile = ChannelProfile(
        name="p", niche="parenting", locale="zh-TW", channel_id="UC", voice_guide="",
        default_tags=[], category_id=27, display_name="理想父母", tagline="t",
        outro_enabled=True,
    )
    png = tmp_path / "p.png"
    Image.new("RGB", (10, 10)).save(png)
    with (
        patch("pipeline.outro.builder.run_ffmpeg") as run,
        patch("pipeline.outro.builder._make_circle_png"),
        patch("pipeline.outro.builder.verify_fontconfig_family") as verify,
    ):
        build_outro(profile=profile, profile_png_path=png, output_path=tmp_path / "o.mp4")
    fc = run.call_args[0][0][run.call_args[0][0].index("-filter_complex") + 1]
    assert fc.count(drawtext_font_arg("bold")) == 2  # channel name + subscribe pill
    assert fc.count(drawtext_font_arg("regular")) == 1  # tagline
    assert ".ttc" not in fc
    styles = {c.args[1] for c in verify.call_args_list}
    assert styles == {"Regular", "Bold"}


def test_outro_fails_before_ffmpeg_when_family_missing(tmp_path):
    from pipeline.outro.builder import build_outro
    from pipeline.publish.channels import ChannelProfile

    profile = ChannelProfile(
        name="p", niche="parenting", locale="zh-TW", channel_id="UC", voice_guide="",
        default_tags=[], category_id=27, display_name="d", tagline="t", outro_enabled=True,
    )
    with (
        patch("pipeline.outro.builder.run_ffmpeg") as run,
        patch(
            "pipeline.outro.builder.verify_fontconfig_family",
            side_effect=FontResolutionError("missing"),
        ),
        pytest.raises(FontResolutionError),
    ):
        build_outro(profile=profile, profile_png_path=tmp_path / "x.png", output_path=tmp_path / "o")
    run.assert_not_called()


def test_text_card_has_no_empty_fontfile(tmp_path):
    from pipeline.composer.text_card import render_text_card

    with patch("pipeline.composer.text_card.run_ffmpeg") as run:
        render_text_card({"text": "說明"}, 3.0, 1280, 720, tmp_path, "s1", theme={})
    vf = " ".join(run.call_args[0][0])
    assert "fontfile" not in vf
    assert "font='Noto Sans CJK TC'" in vf


# ── compose-start fontconfig verification ───────────────────────────────────
def test_compose_verifies_theme_font_before_rendering(tmp_path):
    from pipeline.stages.compose import verify_theme_fonts

    with patch("pipeline.stages.compose.verify_fontconfig_family") as v:
        verify_theme_fonts({"font": "Noto Serif CJK TC"})
    assert {(c.args[0], c.args[1]) for c in v.call_args_list} == {
        ("Noto Serif CJK TC", "Regular"),
        ("Noto Serif CJK TC", "Bold"),
    }


def test_compose_theme_font_default(tmp_path):
    from pipeline.stages.compose import verify_theme_fonts

    with patch("pipeline.stages.compose.verify_fontconfig_family") as v:
        verify_theme_fonts({})
    assert {c.args[0] for c in v.call_args_list} == {"Noto Sans CJK TC"}


def test_compose_theme_font_missing_raises():
    from pipeline.stages.compose import verify_theme_fonts

    with pytest.raises(FontResolutionError):
        verify_theme_fonts({"font": "Nonexistent Font XYZ"})
