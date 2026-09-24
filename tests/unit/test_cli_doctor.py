"""`pipeline doctor` — render-readiness check (Sprint 8, spec 4.3)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pipeline import cli_doctor
from pipeline.cli import app
from pipeline.cli_doctor import CheckResult
from pipeline.utils import fonts
from pipeline.utils.fonts import ProbeResult

runner = CliRunner()


def _all_pass(monkeypatch):
    monkeypatch.setattr(cli_doctor, "check_fonts", lambda: [CheckResult("fonts", True, "ok")])
    monkeypatch.setattr(
        cli_doctor, "check_fontconfig", lambda: [CheckResult("fontconfig", True, "ok")]
    )
    monkeypatch.setattr(cli_doctor, "check_ffmpeg", lambda: [CheckResult("ffmpeg", True, "ok")])
    monkeypatch.setattr(
        cli_doctor, "check_glyph_probes", lambda out: [CheckResult("probe", True, str(out))]
    )
    monkeypatch.setattr(
        cli_doctor, "check_home_tools", lambda: [CheckResult("home tools", True, "ok")]
    )


def test_doctor_registered_and_exit_0_when_all_pass(monkeypatch, tmp_path):
    _all_pass(monkeypatch)
    res = runner.invoke(app, ["doctor", "--out", str(tmp_path)])
    assert res.exit_code == 0, res.output
    lines = [ln for ln in res.output.splitlines() if ln.startswith(("PASS", "FAIL"))]
    assert len(lines) == 5 and all(ln.startswith("PASS") for ln in lines)
    assert str(tmp_path) in res.output


def test_doctor_exit_1_when_any_check_fails(monkeypatch, tmp_path):
    _all_pass(monkeypatch)
    monkeypatch.setattr(
        cli_doctor, "check_ffmpeg", lambda: [CheckResult("ffmpeg libass", False, "missing")]
    )
    res = runner.invoke(app, ["doctor", "--out", str(tmp_path)])
    assert res.exit_code == 1
    assert "FAIL  ffmpeg libass: missing" in res.output


def test_doctor_crashing_check_is_a_fail_not_a_traceback(monkeypatch, tmp_path):
    _all_pass(monkeypatch)

    def boom():
        raise RuntimeError("kaput")

    monkeypatch.setattr(cli_doctor, "check_fontconfig", boom)
    res = runner.invoke(app, ["doctor", "--out", str(tmp_path)])
    assert res.exit_code == 1
    assert "FAIL" in res.output and "kaput" in res.output


# ── check 1: resolver ───────────────────────────────────────────────────────
def test_check_fonts_fails_with_install_hint_when_missing(monkeypatch):
    monkeypatch.delenv("PIPELINE_FONT_DIRS", raising=False)
    monkeypatch.setattr(fonts, "_fc_match_candidate", lambda f, s: None)
    monkeypatch.setattr(fonts, "platform_font_dirs", lambda platform=None: [])
    fonts.resolve_font.cache_clear()
    try:
        results = cli_doctor.check_fonts()
    finally:
        fonts.resolve_font.cache_clear()
    assert len(results) == 4
    assert not any(r.ok for r in results)
    assert all(fonts.install_hint() in r.detail for r in results)


def test_check_fonts_prints_path_index_family_style(monkeypatch):
    rf = fonts.ResolvedFont(Path("/f/NotoSansCJK.ttc"), 17, "Noto Sans CJK TC", "Bold")
    monkeypatch.setattr(cli_doctor, "resolve_font", lambda role, weight: rf)
    results = cli_doctor.check_fonts()
    # the fake returns a sans family for serif too → serif rows must FAIL
    sans = [r for r in results if "sans" in r.name]
    serif = [r for r in results if "serif" in r.name]
    assert all(r.ok for r in sans) and not any(r.ok for r in serif)
    assert "/f/NotoSansCJK.ttc|17|Noto Sans CJK TC|Bold" in sans[0].detail


# ── check 2: fontconfig family ───────────────────────────────────────────────
def test_check_fontconfig_reports_substitution(monkeypatch):
    def fake_verify(family, style=None):
        raise fonts.FontResolutionError(f"substituted {family} {style}")

    monkeypatch.setattr(cli_doctor, "verify_fontconfig_family", fake_verify)
    results = cli_doctor.check_fontconfig()
    assert [r.ok for r in results] == [False, False]
    assert "Regular" in results[0].detail and "Bold" in results[1].detail


# ── check 3: ffmpeg capabilities ─────────────────────────────────────────────
_BUILDCONF = """  configuration:
    --enable-libfreetype
    --enable-libfontconfig
    --enable-libass
    --enable-libharfbuzz
"""
_FILTERS = """ ... drawtext          V->V       Draw text on top of video frames using libfreetype library.
 ... subtitles         V->V       Render text subtitles onto input video using the libass library.
"""


def _fake_ffmpeg(buildconf: str, filters: str):
    def run(cmd, **kw):
        out = buildconf if "-buildconf" in cmd else filters
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")

    return run


def test_check_ffmpeg_all_present(monkeypatch):
    monkeypatch.setattr(cli_doctor.shutil, "which", lambda n: "/usr/bin/ffmpeg")
    monkeypatch.setattr(cli_doctor.subprocess, "run", _fake_ffmpeg(_BUILDCONF, _FILTERS))
    results = cli_doctor.check_ffmpeg()
    assert results and all(r.ok for r in results)


@pytest.mark.parametrize("missing", ["libfreetype", "libfontconfig", "libass"])
def test_check_ffmpeg_missing_flag(monkeypatch, missing):
    conf = _BUILDCONF.replace(f"--enable-{missing}\n", "")
    monkeypatch.setattr(cli_doctor.shutil, "which", lambda n: "/usr/bin/ffmpeg")
    monkeypatch.setattr(cli_doctor.subprocess, "run", _fake_ffmpeg(conf, _FILTERS))
    failed = [r for r in cli_doctor.check_ffmpeg() if not r.ok]
    assert len(failed) == 1 and missing in failed[0].name
    assert "ffmpeg-full" in failed[0].detail or "apt" in failed[0].detail


def test_check_ffmpeg_missing_filter(monkeypatch):
    filters = _FILTERS.splitlines()[0] + "\n"  # drawtext only
    monkeypatch.setattr(cli_doctor.shutil, "which", lambda n: "/usr/bin/ffmpeg")
    monkeypatch.setattr(cli_doctor.subprocess, "run", _fake_ffmpeg(_BUILDCONF, filters))
    failed = [r for r in cli_doctor.check_ffmpeg() if not r.ok]
    assert [r.name for r in failed] == ["ffmpeg filter subtitles"]


def test_check_ffmpeg_absent(monkeypatch):
    monkeypatch.setattr(cli_doctor.shutil, "which", lambda n: None)
    results = cli_doctor.check_ffmpeg()
    assert len(results) == 1 and not results[0].ok


# ── check 4: glyph probes ────────────────────────────────────────────────────
def test_check_glyph_probes_maps_probe_results(monkeypatch, tmp_path):
    monkeypatch.setattr(
        cli_doctor,
        "run_glyph_probes",
        lambda out: [
            ProbeResult("pil", True, "ok", [out / "a.png"]),
            ProbeResult("drawtext", False, "tofu"),
            ProbeResult("libass", True, "ok"),
        ],
    )
    results = cli_doctor.check_glyph_probes(tmp_path)
    assert [r.ok for r in results] == [True, False, True]
    assert "tofu" in results[1].detail


# ── check 5: home-dir tools ──────────────────────────────────────────────────
def test_check_home_tools(monkeypatch, tmp_path):
    bin_dir = tmp_path / ".claude" / "bin"
    bin_dir.mkdir(parents=True)
    monkeypatch.setattr(cli_doctor, "_home_tool_paths", lambda: [
        bin_dir / "gen-image.py", bin_dir / "keymanager.py"
    ])
    results = cli_doctor.check_home_tools()
    assert not any(r.ok for r in results)
    assert "flat" in results[0].detail  # explains the quiet degradation
    (bin_dir / "gen-image.py").write_text("#")
    (bin_dir / "keymanager.py").write_text("#")
    assert all(r.ok for r in cli_doctor.check_home_tools())


def test_home_tool_paths_match_providers():
    from pipeline.providers.edit_image import _KM
    from pipeline.providers.gen_image import _GEN_IMAGE_BIN

    assert cli_doctor._home_tool_paths() == [_GEN_IMAGE_BIN, _KM]
