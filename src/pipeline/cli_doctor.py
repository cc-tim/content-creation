"""pipeline doctor — render-readiness check (Sprint 8, E8 item 1).

Scope-capped to font / ffmpeg / render readiness; not a general health
framework. Prints one PASS/FAIL line per check and exits 0 when all pass, 1 on
any FAIL. Glyph-probe PNGs are saved to ``--out`` for eyeballing.

Checks:
  1. resolve_font for sans/serif x regular/bold → Noto {Sans,Serif} CJK TC
  2. fontconfig resolves the theme default family (Regular, Bold) to itself
  3. ffmpeg build has libfreetype/libfontconfig/libass + drawtext/subtitles
  4. glyph-distinctness probes: PIL, drawtext, libass (render truth, no OCR)
  5. ~/.claude/bin/gen-image.py + keymanager.py present
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import typer

from pipeline.utils.fonts import (
    DEFAULT_FAMILY,
    FontResolutionError,
    family_name,
    resolve_font,
    run_glyph_probes,
    verify_fontconfig_family,
)

_REQUIRED_BUILD_FLAGS = ("libfreetype", "libfontconfig", "libass")
_REQUIRED_FILTERS = ("drawtext", "subtitles")


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def _ffmpeg_hint() -> str:
    if sys.platform == "darwin":
        return "brew install ffmpeg-full and put it first on PATH (it may be keg-only)"
    return "sudo apt install ffmpeg (a build with libfreetype, libfontconfig and libass)"


def check_fonts() -> list[CheckResult]:
    results: list[CheckResult] = []
    for role in ("sans", "serif"):
        for weight in ("regular", "bold"):
            name = f"font {role}/{weight}"
            want = family_name(role)  # type: ignore[arg-type]
            try:
                rf = resolve_font(role, weight)  # type: ignore[arg-type]
            except FontResolutionError as exc:
                results.append(CheckResult(name, False, str(exc).replace("\n", " ")))
                continue
            line = f"{rf.path}|{rf.index}|{rf.family}|{rf.style}"
            ok = rf.family == want
            results.append(CheckResult(name, ok, line if ok else f"{line} (want {want})"))
    return results


def check_fontconfig() -> list[CheckResult]:
    results: list[CheckResult] = []
    for style in ("Regular", "Bold"):
        name = f"fontconfig {DEFAULT_FAMILY} {style}"
        try:
            matched = verify_fontconfig_family(DEFAULT_FAMILY, style)
        except FontResolutionError as exc:
            results.append(CheckResult(name, False, f"{style}: {exc}".replace("\n", " ")))
            continue
        results.append(CheckResult(name, True, f"fc-match → {matched}"))
    return results


def check_ffmpeg() -> list[CheckResult]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return [CheckResult("ffmpeg", False, f"ffmpeg not on PATH; fix: {_ffmpeg_hint()}")]
    conf = subprocess.run(
        [ffmpeg, "-hide_banner", "-buildconf"], capture_output=True, text=True, timeout=30
    ).stdout
    filters = subprocess.run(
        [ffmpeg, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=30
    ).stdout
    results: list[CheckResult] = []
    for flag in _REQUIRED_BUILD_FLAGS:
        # configure also accepts the short spelling (--enable-fontconfig)
        ok = any(f"--enable-{n}" in conf for n in (flag, flag.removeprefix("lib")))
        detail = f"--enable-{flag} ({ffmpeg})" if ok else (
            f"--enable-{flag} missing from {ffmpeg} -buildconf; fix: {_ffmpeg_hint()}"
        )
        results.append(CheckResult(f"ffmpeg build {flag}", ok, detail))
    for flt in _REQUIRED_FILTERS:
        ok = re.search(rf"^\s*\S+\s+{flt}\s", filters, re.M) is not None
        detail = f"{flt} filter available" if ok else (
            f"{flt} filter missing; fix: {_ffmpeg_hint()}"
        )
        results.append(CheckResult(f"ffmpeg filter {flt}", ok, detail))
    return results


def check_glyph_probes(out_dir: Path) -> list[CheckResult]:
    results: list[CheckResult] = []
    for probe in run_glyph_probes(out_dir):
        where = f" [{', '.join(p.name for p in probe.files)}]" if probe.files else ""
        if probe.name == "libass" and sys.platform == "darwin":
            # libass may resolve FontName via CoreText, not fontconfig; a PingFang
            # substitute still passes distinctness, so eyeball the probe PNG.
            where += " (macOS: libass may use CoreText; check the PNG is Noto, not PingFang)"
        results.append(CheckResult(f"glyph probe {probe.name}", probe.ok, probe.detail + where))
    return results


def _home_tool_paths() -> list[Path]:
    from pipeline.providers.edit_image import _KM
    from pipeline.providers.gen_image import _GEN_IMAGE_BIN

    return [_GEN_IMAGE_BIN, _KM]


def check_home_tools() -> list[CheckResult]:
    results: list[CheckResult] = []
    for path in _home_tool_paths():
        ok = path.is_file()
        detail = str(path) if ok else (
            f"{path} missing: image generation fails and every rich_slide background "
            "quietly degrades to flat; copy ~/.claude/bin from the hub (docs/mac-setup.md)"
        )
        results.append(CheckResult(f"home tool {path.name}", ok, detail))
    return results


def run_checks(out_dir: Path) -> list[CheckResult]:
    groups: list[tuple[str, Callable[[], list[CheckResult]]]] = [
        ("fonts", check_fonts),
        ("fontconfig", check_fontconfig),
        ("ffmpeg", check_ffmpeg),
        ("glyph probes", lambda: check_glyph_probes(out_dir)),
        ("home tools", check_home_tools),
    ]
    results: list[CheckResult] = []
    for label, fn in groups:
        try:
            results.extend(fn())
        except Exception as exc:  # a crashing check is a FAIL line, not a traceback
            results.append(CheckResult(label, False, f"check crashed: {exc!r}"))
    return results


def doctor(
    out: Path = typer.Option(
        Path("tmp/doctor"), "--out", help="Directory for the glyph-probe PNGs."
    ),
) -> None:
    """Render-readiness check: fonts, fontconfig, ffmpeg capabilities, CJK glyph probes."""
    out.mkdir(parents=True, exist_ok=True)
    results = run_checks(out)
    for r in results:
        typer.echo(f"{'PASS' if r.ok else 'FAIL'}  {r.name}: {r.detail}")
    failed = sum(not r.ok for r in results)
    typer.echo(
        f"\n{len(results) - failed}/{len(results)} checks passed; probe PNGs in {out}"
    )
    raise typer.Exit(code=1 if failed else 0)
