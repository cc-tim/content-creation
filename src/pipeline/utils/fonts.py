"""The one font resolver used by every renderer (Sprint 8, E8 item 1).

Every PIL text render goes through :func:`load_pil_font`; every ffmpeg drawtext
font argument comes from :func:`drawtext_font_arg`; every family name handed to
fontconfig/libass is checked by :func:`verify_fontconfig_family`. There is no
cross-family substitution: a machine without Noto CJK fails loudly with a
platform-specific install command instead of silently drawing PingFang, a
bitmap default font, or tofu.

Resolution order for :func:`resolve_font` (first verified hit wins):
  1. ``PIPELINE_FONT_DIRS`` (``os.pathsep``-separated directories)
  2. fontconfig (``fc-match``), skipped when the CLI is absent
  3. known platform font directories (Linux + macOS)
  4. raise :class:`FontResolutionError`

Every candidate is opened and its ``getname()`` must equal ``(family, style)``;
TTC/OTC collections are scanned face by face, so the face index is found by
NAME (Debian per-weight TTCs keep TC at index 3, the Homebrew Super-OTC does not).

The glyph-distinctness probes used by ``pipeline doctor`` and the integration
test live here as well so both share one implementation.
"""
from __future__ import annotations

import functools
import os
import shutil
import subprocess
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from PIL import Image, ImageChops, ImageDraw, ImageFont

Role = Literal["sans", "serif"]
Weight = Literal["regular", "bold"]

DEFAULT_REGION = "TC"
DEFAULT_FAMILY = "Noto Sans CJK TC"

_ROLE_FAMILY: dict[str, str] = {"sans": "Noto Sans CJK", "serif": "Noto Serif CJK"}
_WEIGHT_STYLE: dict[str, str] = {"regular": "Regular", "bold": "Bold"}
_FONT_EXTS = frozenset({".ttc", ".otc", ".otf", ".ttf"})
_MAX_FACES = 256  # a Super-OTC holds ~70 faces; this only bounds a corrupt file


class FontResolutionError(RuntimeError):
    """A required font is missing or would be silently substituted.

    ``suggested_fix`` carries the platform-specific install command.
    """

    def __init__(self, message: str, suggested_fix: str | None = None) -> None:
        self.suggested_fix = suggested_fix or install_hint()
        super().__init__(f"{message}\n  fix: {self.suggested_fix}")


@dataclass(frozen=True)
class ResolvedFont:
    path: Path
    index: int  # TTC face index, found by NAME, never hardcoded
    family: str  # e.g. "Noto Sans CJK TC"
    style: str  # "Regular" | "Bold"


def install_hint(platform: str | None = None) -> str:
    """Platform-specific command that installs the Noto CJK fonts."""
    if (platform or sys.platform) == "darwin":
        return "brew install --cask font-noto-sans-cjk font-noto-serif-cjk && fc-cache -f"
    return "sudo apt install fonts-noto-cjk && fc-cache -f"


def fontconfig_hint(platform: str | None = None) -> str:
    if (platform or sys.platform) == "darwin":
        return "brew install fontconfig && fc-cache -f"
    return "sudo apt install fontconfig && fc-cache -f"


def family_name(role: Role, region: str = DEFAULT_REGION) -> str:
    return f"{_ROLE_FAMILY[role]} {region}"


def platform_font_dirs(platform: str | None = None) -> list[Path]:
    """Known Noto CJK install locations for the given platform."""
    home = Path.home()
    if (platform or sys.platform) == "darwin":
        return [
            home / "Library/Fonts",
            Path("/Library/Fonts"),
            Path("/opt/homebrew/share/fonts"),
            Path("/usr/local/share/fonts"),
        ]
    return [
        Path("/usr/share/fonts/opentype/noto"),
        Path("/usr/share/fonts/truetype/noto"),
        home / ".local/share/fonts",
        home / ".fonts",
    ]


# ── face scanning ─────────────────────────────────────────────────────────────
@functools.lru_cache(maxsize=64)
def _face_names(path: str) -> tuple[tuple[str, str], ...]:
    """(family, style) of every face in a font file; () if unreadable."""
    names: list[tuple[str, str]] = []
    for index in range(_MAX_FACES):
        try:
            font = ImageFont.truetype(path, size=12, index=index)
        except (OSError, ValueError):
            break
        family, style = font.getname()
        names.append((family or "", style or ""))
    return tuple(names)


def _find_face(path: Path, family: str, style: str) -> int | None:
    try:
        faces = _face_names(str(path))
    except Exception:  # pragma: no cover - defensive: never let a bad file abort the scan
        return None
    for index, name in enumerate(faces):
        if name == (family, style):
            return index
    return None


def _face_matches(path: Path, index: int, family: str, style: str) -> bool:
    faces = _face_names(str(path))
    return 0 <= index < len(faces) and faces[index] == (family, style)


def _candidate_files(dirs: Iterable[Path]) -> Iterator[Path]:
    """Noto CJK font files under ``dirs`` (any packaging), in a stable order."""
    for d in dirs:
        if not d.is_dir():
            continue
        try:
            files = sorted(p for p in d.rglob("*") if p.suffix.lower() in _FONT_EXTS)
        except OSError:
            continue
        for p in files:
            name = p.name.lower()
            if "noto" in name and "cjk" in name and p.is_file():
                yield p


def _scan_dirs(dirs: Iterable[Path], family: str, style: str) -> ResolvedFont | None:
    for path in _candidate_files(dirs):
        index = _find_face(path, family, style)
        if index is not None:
            return ResolvedFont(path=path, index=index, family=family, style=style)
    return None


def _fc_match_candidate(family: str, style: str) -> tuple[Path, int] | None:
    """Ask fontconfig where ``family:style`` lives. None when fc-match is absent."""
    fc = shutil.which("fc-match")
    if fc is None:
        return None
    try:
        res = subprocess.run(
            [fc, "-f", "%{file}|%{index}", f"{_fc_escape(family)}:style={style}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0 or "|" not in res.stdout:
        return None
    file_s, _, index_s = res.stdout.strip().rpartition("|")
    try:
        return Path(file_s), int(index_s or 0)
    except ValueError:
        return None


def _override_dirs() -> list[Path]:
    raw = os.environ.get("PIPELINE_FONT_DIRS", "")
    return [Path(p).expanduser() for p in raw.split(os.pathsep) if p.strip()]


@functools.cache
def resolve_font(role: Role, weight: Weight, region: str = DEFAULT_REGION) -> ResolvedFont:
    """Find the exact Noto CJK face for (role, weight, region) or raise."""
    family = family_name(role, region)
    style = _WEIGHT_STYLE[weight]

    # 1. explicit override
    override = _override_dirs()
    if override:
        hit = _scan_dirs(override, family, style)
        if hit is not None:
            return hit

    # 2. fontconfig, name-verified (fontconfig happily returns a substitute)
    cand = _fc_match_candidate(family, style)
    if cand is not None:
        path, index = cand
        if _face_matches(path, index, family, style):
            return ResolvedFont(path=path, index=index, family=family, style=style)
        # fontconfig may report face 0 of a collection; scan that file by name too
        found = _find_face(path, family, style)
        if found is not None:
            return ResolvedFont(path=path, index=found, family=family, style=style)

    # 3. known platform directories
    hit = _scan_dirs(platform_font_dirs(), family, style)
    if hit is not None:
        return hit

    searched = [*override, *platform_font_dirs()]
    raise FontResolutionError(
        f"font '{family}' ({style}) not found (searched PIPELINE_FONT_DIRS, fontconfig, "
        f"{', '.join(str(d) for d in searched)}). No substitute font is used."
    )


def load_pil_font(
    role: Role, weight: Weight, size: int, region: str = DEFAULT_REGION
) -> ImageFont.FreeTypeFont:
    """Pillow font for (role, weight). Raises FontResolutionError; never falls back."""
    rf = resolve_font(role, weight, region)
    return ImageFont.truetype(str(rf.path), size=size, index=rf.index)


# ── ffmpeg / fontconfig ───────────────────────────────────────────────────────
def _fc_escape(family: str) -> str:
    """Escape fontconfig pattern metacharacters inside a family name."""
    out = family
    for ch in ("\\", "-", ":", ","):
        out = out.replace(ch, "\\" + ch)
    return out


def drawtext_font_arg(weight: Weight = "regular", family: str = DEFAULT_FAMILY) -> str:
    """The escaped drawtext font option selecting ``family`` + style via fontconfig.

    Deviation from the spec's literal ``font=...`` wording, measured on the hub
    (ffmpeg 6.1): drawtext's ``font=`` is added to the fontconfig pattern as a
    *literal family string*, so ``font='Noto Sans CJK TC\\:style=Bold'`` names a
    nonexistent family and silently renders tofu. The fontconfig *pattern*
    (family + style) is only parsed from ``fontfile=`` when it is not a readable
    path, which is exactly how the ffmpeg docs select a style. The value here is
    never a filesystem path. ``:`` is escaped once for the filter-option level
    (the single quotes protect it at the filtergraph level).
    """
    if "'" in family or "\\" in family:
        raise ValueError(f"unsupported character in font family: {family!r}")
    pattern = f"{_fc_escape(family)}:style={_WEIGHT_STYLE[weight]}"
    return "fontfile='" + pattern.replace(":", "\\:") + "'"


def verify_fontconfig_family(family: str, style: str | None = None) -> str:
    """Fail unless fontconfig resolves ``family`` (and ``style``) to itself.

    fontconfig never errors on a missing family (``fc-match 'Nonexistent'`` exits 0
    with a substitute), so drawtext ``font=``/libass ``FontName=`` would silently
    draw another family. Returns fc-match's ``family|style`` line.
    """
    fc = shutil.which("fc-match")
    if fc is None:
        raise FontResolutionError(
            "fc-match not found: ffmpeg drawtext/libass font lookup needs fontconfig",
            suggested_fix=fontconfig_hint(),
        )
    pattern = _fc_escape(family) + (f":style={style}" if style else "")
    try:
        res = subprocess.run(
            [fc, "-f", "%{family}|%{style}", pattern],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise FontResolutionError(f"fc-match failed for '{pattern}': {exc}") from exc
    out = (res.stdout or "").strip()
    fam_s, _, style_s = out.partition("|")
    families = [f.strip() for f in fam_s.split(",") if f.strip()]
    styles = [s.strip() for s in style_s.split(",") if s.strip()]
    if res.returncode != 0 or family not in families:
        raise FontResolutionError(
            f"fontconfig substitutes {families or ['<nothing>']} for font family "
            f"'{family}' — the font is not installed (or fc-cache is stale)"
        )
    if style is not None and style not in styles:
        raise FontResolutionError(
            f"fontconfig has '{family}' but not style '{style}' (got {styles})"
        )
    return out


# ── glyph-distinctness probes (render truth; shared by doctor + integration) ──
PROBE_TEXTS: tuple[str, str] = ("說明", "學步")
NOTDEF_TEXT = ""  # private-use codepoint → .notdef box


@dataclass
class ProbeResult:
    name: str
    ok: bool
    detail: str
    files: list[Path] = field(default_factory=list)


def _same(a: Image.Image, b: Image.Image) -> bool:
    if a.size != b.size:
        return False
    return ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox() is None


def glyphs_distinct(cjk_a: Image.Image, cjk_b: Image.Image, notdef: Image.Image) -> tuple[bool, str]:
    """PASS iff the two CJK renders differ and neither equals the .notdef render."""
    if _same(cjk_a, cjk_b):
        return False, "the two CJK strings rendered identically (tofu or blank)"
    if _same(cjk_a, notdef) or _same(cjk_b, notdef):
        return False, "a CJK string rendered the same as the .notdef probe (tofu)"
    blank = Image.new(cjk_a.mode, cjk_a.size, cjk_a.getpixel((0, 0)))
    if _same(cjk_a, blank) or _same(cjk_b, blank):
        return False, "a CJK string rendered blank"
    return True, "CJK glyphs distinct and not .notdef"


def _probe_from_files(name: str, files: list[Path], detail_ok: str) -> ProbeResult:
    imgs = [Image.open(p).convert("RGB") for p in files]
    ok, detail = glyphs_distinct(imgs[0], imgs[1], imgs[2])
    return ProbeResult(name, ok, f"{detail_ok}: {detail}" if ok else detail, files)


def _probe_paths(out_dir: Path, kind: str) -> list[Path]:
    return [out_dir / f"probe_{kind}_{tag}.png" for tag in ("cjk_a", "cjk_b", "notdef")]


def probe_pil(out_dir: Path) -> ProbeResult:
    """(a) Pillow via load_pil_font — the path used by chart/callout/rich_slide."""
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        font = load_pil_font("sans", "regular", 64)
    except FontResolutionError as exc:
        return ProbeResult("pil", False, str(exc))
    paths = _probe_paths(out_dir, "pil")
    for text, path in zip((*PROBE_TEXTS, NOTDEF_TEXT), paths, strict=True):
        img = Image.new("RGB", (320, 110), "white")
        ImageDraw.Draw(img).text((16, 12), text, font=font, fill="black")
        img.save(path)
    return _probe_from_files("pil", paths, "/".join(font.getname()))


def _ffmpeg_png(cmd: list[str], cwd: Path | None = None) -> str | None:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=cwd)
    except (OSError, subprocess.SubprocessError) as exc:
        return str(exc)
    return None if res.returncode == 0 else (res.stderr.strip().splitlines() or ["?"])[-1]


def probe_drawtext(out_dir: Path, ffmpeg: str = "ffmpeg") -> ProbeResult:
    """(b) ffmpeg drawtext with exactly the drawtext_font_arg() string."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = _probe_paths(out_dir, "drawtext")
    font_arg = drawtext_font_arg("bold")
    for text, path in zip((*PROBE_TEXTS, NOTDEF_TEXT), paths, strict=True):
        err = _ffmpeg_png(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=white:s=320x110",
                "-frames:v", "1",
                "-vf", f"drawtext=text='{text}':{font_arg}:fontsize=64:fontcolor=black:x=16:y=16",
                str(path),
            ]
        )
        if err is not None:
            return ProbeResult("drawtext", False, f"ffmpeg drawtext failed: {err}")
    return _probe_from_files("drawtext", paths, font_arg)


def probe_libass(out_dir: Path, ffmpeg: str = "ffmpeg", family: str = DEFAULT_FAMILY) -> ProbeResult:
    """(c) libass subtitle burn with FontName=<family>, as the compose burn pass does."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = _probe_paths(out_dir, "libass")
    style = f"FontName={family},FontSize=120,Bold=1,PrimaryColour=&H00000000,Outline=0,Shadow=0"
    for i, (text, path) in enumerate(zip((*PROBE_TEXTS, NOTDEF_TEXT), paths, strict=True)):
        srt = out_dir / f"probe_libass_{i}.srt"
        srt.write_text(f"1\n00:00:00,000 --> 00:00:05,000\n{text}\n", encoding="utf-8")
        # Relative file name + cwd keeps the subtitles= path free of escaping.
        err = _ffmpeg_png(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=white:s=320x110:d=1",
                "-frames:v", "1",
                "-vf", f"subtitles={srt.name}:force_style='{style}'",
                str(path.resolve()),
            ],
            cwd=out_dir,
        )
        srt.unlink(missing_ok=True)
        if err is not None:
            return ProbeResult("libass", False, f"ffmpeg subtitles failed: {err}")
    return _probe_from_files("libass", paths, f"FontName={family}")


def run_glyph_probes(out_dir: Path, ffmpeg: str = "ffmpeg") -> list[ProbeResult]:
    return [probe_pil(out_dir), probe_drawtext(out_dir, ffmpeg), probe_libass(out_dir, ffmpeg)]
