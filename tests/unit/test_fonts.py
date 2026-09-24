"""Unit tests for the single cross-platform font resolver (Sprint 8, E8 item 1)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from pipeline.utils import fonts
from pipeline.utils.fonts import (
    FontResolutionError,
    ResolvedFont,
    drawtext_font_arg,
    install_hint,
    load_pil_font,
    resolve_font,
    verify_fontconfig_family,
)

_DEBIAN_NOTO = Path("/usr/share/fonts/opentype/noto")
_HUB_FONTS = pytest.mark.skipif(
    not (_DEBIAN_NOTO / "NotoSansCJK-Bold.ttc").exists(),
    reason="hub (Debian fonts-noto-cjk) identity check",
)
_HAS_FC = pytest.mark.skipif(shutil.which("fc-match") is None, reason="fc-match not installed")


@pytest.fixture(autouse=True)
def _clear_cache():
    resolve_font.cache_clear()
    yield
    resolve_font.cache_clear()


@pytest.fixture
def no_fonts(monkeypatch):
    """Force every resolution step to find nothing."""
    monkeypatch.delenv("PIPELINE_FONT_DIRS", raising=False)
    monkeypatch.setattr(fonts, "_fc_match_candidate", lambda family, style: None)
    monkeypatch.setattr(fonts, "platform_font_dirs", lambda platform=None: [])
    resolve_font.cache_clear()
    yield
    resolve_font.cache_clear()


# ── A3: resolver identity on the hub (locks in the HK→TC fix) ────────────────
@_HUB_FONTS
@pytest.mark.parametrize(
    ("role", "weight", "filename", "family", "style"),
    [
        ("sans", "regular", "NotoSansCJK-Regular.ttc", "Noto Sans CJK TC", "Regular"),
        ("sans", "bold", "NotoSansCJK-Bold.ttc", "Noto Sans CJK TC", "Bold"),
        ("serif", "regular", "NotoSerifCJK-Regular.ttc", "Noto Serif CJK TC", "Regular"),
        ("serif", "bold", "NotoSerifCJK-Bold.ttc", "Noto Serif CJK TC", "Bold"),
    ],
)
def test_resolver_identity_on_hub(role, weight, filename, family, style):
    rf = resolve_font(role, weight)
    assert rf == ResolvedFont(path=_DEBIAN_NOTO / filename, index=3, family=family, style=style)


@_HUB_FONTS
def test_load_pil_font_opens_tc_face():
    f = load_pil_font("sans", "bold", 40)
    assert f.getname() == ("Noto Sans CJK TC", "Bold")
    assert f.size == 40


@_HUB_FONTS
def test_tc_face_differs_from_hk_face_for_cjk():
    """The old _TC_INDEX=4 was HK; TC forms must differ for zh-TW-specific glyphs."""
    from PIL import ImageFont

    tc = load_pil_font("sans", "regular", 64)
    hk = ImageFont.truetype(str(_DEBIAN_NOTO / "NotoSansCJK-Regular.ttc"), 64, index=4)
    assert hk.getname()[0] == "Noto Sans CJK HK"

    def render(font):
        img = Image.new("L", (400, 100), 0)
        ImageDraw.Draw(img).text((0, 0), "說為溫裡", font=font, fill=255)
        return img.tobytes()

    assert render(tc) != render(hk)


@_HUB_FONTS
def test_resolver_is_cached():
    assert resolve_font("sans", "regular") is resolve_font("sans", "regular")
    assert resolve_font.cache_info().hits >= 1


# ── Resolution order ─────────────────────────────────────────────────────────
@_HUB_FONTS
def test_override_dirs_scanned_by_name(monkeypatch, tmp_path):
    """PIPELINE_FONT_DIRS wins and the face index is found by NAME, not hardcoded."""
    d = tmp_path / "fonts"
    d.mkdir()
    (d / "NotoSansCJK-Bold.ttc").symlink_to(_DEBIAN_NOTO / "NotoSansCJK-Bold.ttc")
    monkeypatch.setenv("PIPELINE_FONT_DIRS", str(d))
    monkeypatch.setattr(fonts, "_fc_match_candidate", lambda f, s: pytest.fail("fc consulted"))
    rf = resolve_font("sans", "bold")
    assert rf.path == d / "NotoSansCJK-Bold.ttc"
    assert (rf.index, rf.family, rf.style) == (3, "Noto Sans CJK TC", "Bold")


@_HUB_FONTS
def test_override_dirs_region_selects_face(monkeypatch, tmp_path):
    monkeypatch.setenv("PIPELINE_FONT_DIRS", str(_DEBIAN_NOTO))
    assert resolve_font("sans", "regular", region="HK").index == 4
    assert resolve_font("sans", "regular", region="JP").index == 0


@_HUB_FONTS
def test_fontconfig_candidate_is_name_verified(monkeypatch):
    """A fontconfig answer pointing at the wrong face is rejected, not trusted."""
    monkeypatch.delenv("PIPELINE_FONT_DIRS", raising=False)
    monkeypatch.setattr(fonts, "platform_font_dirs", lambda platform=None: [])
    # Right file, wrong face (HK): the index is re-found by name, never trusted.
    wrong_face = (_DEBIAN_NOTO / "NotoSansCJK-Bold.ttc", 4)
    monkeypatch.setattr(fonts, "_fc_match_candidate", lambda f, s: wrong_face)
    assert resolve_font("sans", "bold").index == 3
    # A substitute file (another family entirely) is rejected → loud failure.
    resolve_font.cache_clear()
    substitute = (_DEBIAN_NOTO / "NotoSerifCJK-Bold.ttc", 3)
    monkeypatch.setattr(fonts, "_fc_match_candidate", lambda f, s: substitute)
    with pytest.raises(FontResolutionError):
        resolve_font("sans", "bold")


@_HUB_FONTS
def test_platform_dirs_used_when_fontconfig_absent(monkeypatch):
    monkeypatch.delenv("PIPELINE_FONT_DIRS", raising=False)
    monkeypatch.setattr(fonts, "_fc_match_candidate", lambda f, s: None)
    monkeypatch.setattr(fonts, "platform_font_dirs", lambda platform=None: [_DEBIAN_NOTO])
    rf = resolve_font("serif", "bold")
    assert (rf.path.name, rf.index) == ("NotoSerifCJK-Bold.ttc", 3)


def test_non_cjk_files_in_dirs_are_ignored(monkeypatch, tmp_path):
    (tmp_path / "Garbage.ttf").write_bytes(b"not a font")
    (tmp_path / "NotoSansCJK-Broken.ttc").write_bytes(b"not a font either")
    monkeypatch.setenv("PIPELINE_FONT_DIRS", str(tmp_path))
    monkeypatch.setattr(fonts, "_fc_match_candidate", lambda f, s: None)
    monkeypatch.setattr(fonts, "platform_font_dirs", lambda platform=None: [])
    with pytest.raises(FontResolutionError):
        resolve_font("sans", "regular")


def test_platform_font_dirs_per_platform():
    linux = fonts.platform_font_dirs("linux")
    mac = fonts.platform_font_dirs("darwin")
    assert Path("/usr/share/fonts/opentype/noto") in linux
    assert Path("/usr/share/fonts/truetype/noto") in linux
    assert Path.home() / ".local/share/fonts" in linux
    assert Path.home() / "Library/Fonts" in mac
    assert Path("/Library/Fonts") in mac
    assert Path("/opt/homebrew/share/fonts") in mac


# ── A4: loud failure ─────────────────────────────────────────────────────────
def test_nothing_found_raises_with_platform_fix(no_fonts):
    with pytest.raises(FontResolutionError) as ei:
        resolve_font("sans", "bold")
    assert ei.value.suggested_fix == install_hint()
    assert ei.value.suggested_fix in str(ei.value)
    assert "Noto Sans CJK TC" in str(ei.value)


def test_install_hint_names_platform_command():
    assert "apt install fonts-noto-cjk" in install_hint("linux")
    mac = install_hint("darwin")
    assert "brew install --cask font-noto-sans-cjk font-noto-serif-cjk" in mac
    assert "fc-cache -f" in mac


def test_load_pil_font_propagates_failure(no_fonts):
    with pytest.raises(FontResolutionError):
        load_pil_font("serif", "regular", 20)


@_HAS_FC
def test_verify_fontconfig_family_rejects_substitution():
    with pytest.raises(FontResolutionError) as ei:
        verify_fontconfig_family("Nonexistent Font XYZ")
    assert ei.value.suggested_fix


@_HAS_FC
@_HUB_FONTS
def test_verify_fontconfig_family_accepts_installed():
    matched = verify_fontconfig_family("Noto Sans CJK TC", "Bold")
    assert "Noto Sans CJK TC" in matched
    verify_fontconfig_family("Noto Sans CJK TC")


def test_verify_fontconfig_family_style_mismatch(monkeypatch):
    monkeypatch.setattr(fonts.shutil, "which", lambda name: "/usr/bin/fc-match")

    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout="Noto Sans CJK TC|Regular", stderr="")

    monkeypatch.setattr(fonts.subprocess, "run", fake_run)
    with pytest.raises(FontResolutionError, match="style"):
        verify_fontconfig_family("Noto Sans CJK TC", "Bold")
    assert verify_fontconfig_family("Noto Sans CJK TC", "Regular")


def test_verify_fontconfig_family_accepts_family_list(monkeypatch):
    monkeypatch.setattr(fonts.shutil, "which", lambda name: "/usr/bin/fc-match")
    out = "Noto Sans CJK TC,Noto Sans CJK TC Bold|Bold,Regular"
    monkeypatch.setattr(
        fonts.subprocess,
        "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout=out, stderr=""),
    )
    assert verify_fontconfig_family("Noto Sans CJK TC", "Bold") == out


def test_verify_fontconfig_family_without_fc_match(monkeypatch):
    monkeypatch.setattr(fonts.shutil, "which", lambda name: None)
    with pytest.raises(FontResolutionError) as ei:
        verify_fontconfig_family("Noto Sans CJK TC")
    assert "fontconfig" in ei.value.suggested_fix


# ── drawtext argument builder ────────────────────────────────────────────────
def test_drawtext_font_arg_is_escaped_fontconfig_pattern():
    assert drawtext_font_arg("bold") == r"fontfile='Noto Sans CJK TC\:style=Bold'"
    assert drawtext_font_arg() == r"fontfile='Noto Sans CJK TC\:style=Regular'"
    assert drawtext_font_arg("regular", family="Noto Serif CJK TC") == (
        r"fontfile='Noto Serif CJK TC\:style=Regular'"
    )


def test_drawtext_font_arg_never_a_path():
    arg = drawtext_font_arg("bold")
    assert "/" not in arg and ".tt" not in arg


def test_drawtext_font_arg_rejects_quote():
    with pytest.raises(ValueError):
        drawtext_font_arg("bold", family="Bad'Family")
