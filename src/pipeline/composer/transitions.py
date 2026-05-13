"""Per-seam transition primitives for the compose pipeline.

A transition is a short clip rendered between scene N and scene N+1.
Storyboards declare transitions sparsely in the `transitions[]` array;
missing entries mean a hard cut.

Most v1 styles use ffmpeg's built-in `xfade` filter. The legacy
`page-turn` style remains an alias to `xfade slideleft`; projects that need
a visible book/page metaphor should use `book-page-turn-v2` when render time
allows, or `book-page-turn` for the faster basic generated path.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import structlog

from pipeline.composer.book_scene import extract_video_frame, render_book_page_turn_v2
from pipeline.storyboard import Transition
from pipeline.utils.ffmpeg import run_ffmpeg

logger = structlog.get_logger()
_REPO_ROOT = Path(__file__).resolve().parents[3]

SUPPORTED_STYLES: set[str] = {
    "none",
    "fade",
    "page-turn",
    "book-page-turn",
    "book-page-turn-v2",
    "stock-book-page-turn",
    "slide",
    "wipe",
}
BOOK_PAGE_STYLES: set[str] = {
    "book-page-turn",
    "book-page-turn-v2",
    "stock-book-page-turn",
}
MAX_BOOK_PAGE_COUNT = 8
BOOK_PAGE_TURN_V2_RENDER_VERSION = "book-page-turn-v2.2"
SUPPORTED_RENDERER_MODES: set[str] = {
    "generated",
    "licensed_clip",
    "overlay",
}


@dataclass(frozen=True)
class TransitionConfig:
    """Render-ready config for one transition between two scenes."""

    style: str
    duration_sec: float
    sfx: str | None
    page_count: int | None = None
    renderer_mode: str | None = None
    asset_path: str | None = None
    asset_source: str | None = None
    asset_source_url: str | None = None
    asset_license: str | None = None
    asset_notes: str | None = None

    def __post_init__(self) -> None:
        if self.style not in SUPPORTED_STYLES:
            raise ValueError(
                f"Unknown transition style: {self.style!r}. "
                f"Supported: {sorted(SUPPORTED_STYLES)}"
            )
        if self.renderer_mode is not None and self.renderer_mode not in SUPPORTED_RENDERER_MODES:
            raise ValueError(
                f"Unknown transition renderer_mode: {self.renderer_mode!r}. "
                f"Supported: {sorted(SUPPORTED_RENDERER_MODES)}"
            )
        if self.page_count is not None and not 1 <= self.page_count <= MAX_BOOK_PAGE_COUNT:
            raise ValueError(f"page_count must be between 1 and {MAX_BOOK_PAGE_COUNT}")
        if self.effective_renderer_mode != "generated" and not self.asset_path:
            raise ValueError("asset_path is required when renderer_mode is licensed_clip or overlay")

    @classmethod
    def from_transition(cls, t: Transition) -> TransitionConfig:
        return cls(
            style=t.style,
            duration_sec=t.duration_sec,
            sfx=t.sfx,
            page_count=t.page_count,
            renderer_mode=t.renderer_mode,
            asset_path=t.asset_path,
            asset_source=t.asset_source,
            asset_source_url=t.asset_source_url,
            asset_license=t.asset_license,
            asset_notes=t.asset_notes,
        )

    @property
    def effective_renderer_mode(self) -> str:
        if self.renderer_mode:
            return self.renderer_mode
        if self.style == "stock-book-page-turn":
            return "licensed_clip"
        return "generated"

    @property
    def normalized_style(self) -> str:
        if self.style == "stock-book-page-turn":
            return "book-page-turn"
        return self.style


class TransitionRenderer(Protocol):
    """Protocol implemented by each per-style renderer.

    Implementations should be deterministic: same inputs -> same output bytes.
    The cache layer above relies on this.
    """

    def render(
        self,
        scene_a: Path,
        scene_b: Path,
        cfg: TransitionConfig,
        out: Path,
        *,
        width: int,
        height: int,
        fps: int,
    ) -> Path | None:
        """Render the transition clip between scene_a and scene_b to `out`.

        Returns the output path on success, or None if no clip should be
        emitted (e.g. for HardCutRenderer — concat just stitches the two
        scenes directly).
        """
        ...


class HardCutRenderer:
    """Emits no transition clip — the master concat stitches scenes directly."""

    def render(
        self,
        scene_a: Path,
        scene_b: Path,
        cfg: TransitionConfig,
        out: Path,
        *,
        width: int,
        height: int,
        fps: int,
    ) -> Path | None:
        return None


class XfadeRenderer:
    """Renders a transition using ffmpeg's xfade filter.

    Pipeline:
      1. Extract the last frame of scene_a and first frame of scene_b as PNG.
      2. Build a static-frame video clip of cfg.duration_sec from each PNG
         (with silent stereo audio at 48kHz to match the project standard).
      3. Apply xfade between the two clips for cfg.duration_sec.
      4. If cfg.sfx is set, amix the sfx into the audio track.
      5. Encode H.264 + AAC with the same params as scene clips so the
         master concat demuxer can stream-copy the result.
    """

    def __init__(self, xfade_name: str) -> None:
        # xfade built-in transition name (fade | slideleft | slideright | wiperight | wipeleft ...)
        self.xfade_name = xfade_name

    def render(
        self,
        scene_a: Path,
        scene_b: Path,
        cfg: TransitionConfig,
        out: Path,
        *,
        width: int,
        height: int,
        fps: int,
    ) -> Path | None:
        work = out.parent
        work.mkdir(parents=True, exist_ok=True)
        frame_a = work / f"{out.stem}_a.png"
        frame_b = work / f"{out.stem}_b.png"

        # 1. Extract last frame of scene_a (sseof = seek from end)
        run_ffmpeg([
            "ffmpeg", "-y", "-sseof", "-0.5", "-i", str(scene_a),
            "-frames:v", "1", "-update", "1", str(frame_a),
        ])
        # 2. Extract first frame of scene_b
        run_ffmpeg([
            "ffmpeg", "-y", "-i", str(scene_b),
            "-frames:v", "1", "-update", "1", str(frame_b),
        ])

        # 3. Build the xfade + audio pipeline in one ffmpeg invocation.
        d = cfg.duration_sec
        # filter_complex pieces
        video_filter = (
            f"[0:v]scale={width}:{height},setsar=1,fps={fps},format=yuv420p[va];"
            f"[1:v]scale={width}:{height},setsar=1,fps={fps},format=yuv420p[vb];"
            f"[va][vb]xfade=transition={self.xfade_name}:duration={d}:offset=0[v]"
        )
        # Inputs: two static images looped, one anullsrc for silent base audio,
        # plus the sfx file if provided.
        cmd: list[str] = [
            "ffmpeg", "-y",
            "-loop", "1", "-t", str(d), "-i", str(frame_a),
            "-loop", "1", "-t", str(d), "-i", str(frame_b),
            "-f", "lavfi", "-t", str(d), "-i", "anullsrc=r=48000:cl=stereo",
        ]
        if cfg.sfx:
            cmd += ["-i", cfg.sfx]
            audio_filter = "[2:a][3:a]amix=inputs=2:duration=first:dropout_transition=0[a]"
        else:
            audio_filter = "[2:a]anull[a]"
        cmd += [
            "-filter_complex", f"{video_filter};{audio_filter}",
            "-map", "[v]", "-map", "[a]",
            "-t", str(d),
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-pix_fmt", "yuv420p", "-r", str(fps),
            "-c:a", "aac", "-ar", "48000", "-b:a", "128k",
            "-shortest", str(out),
        ]
        run_ffmpeg(cmd)
        # Cleanup intermediates
        frame_a.unlink(missing_ok=True)
        frame_b.unlink(missing_ok=True)
        return out


class BookPageTurnRenderer:
    """Renders a book-aware page flip with visible sheets and cover base."""

    def render(
        self,
        scene_a: Path,
        scene_b: Path,
        cfg: TransitionConfig,
        out: Path,
        *,
        width: int,
        height: int,
        fps: int,
    ) -> Path | None:
        work = out.parent
        work.mkdir(parents=True, exist_ok=True)
        frame_a = work / f"{out.stem}_a.png"
        frame_b = work / f"{out.stem}_b.png"

        run_ffmpeg([
            "ffmpeg", "-y", "-sseof", "-0.5", "-i", str(scene_a),
            "-frames:v", "1", "-update", "1", str(frame_a),
        ])
        run_ffmpeg([
            "ffmpeg", "-y", "-i", str(scene_b),
            "-frames:v", "1", "-update", "1", str(frame_b),
        ])

        d = cfg.duration_sec
        page_count = cfg.page_count or 2
        crease_w = max(16, int(width * 0.045))
        base_h = max(36, int(height * 0.09))
        content_x = int(width * 0.125)
        content_y = int(height * 0.16)
        content_w = int(width * 0.75)
        content_h = int(height * 0.66)
        gutter_w = max(8, int(width * 0.014))
        page_overlays = self._page_flip_filters(
            page_count=page_count,
            duration=d,
            width=width,
            height=height,
            content_x=content_x,
            content_y=content_y,
            content_w=content_w,
            content_h=content_h,
            crease_w=crease_w,
        )
        video_filter = (
            f"[0:v]scale={width}:{height},setsar=1,fps={fps},format=yuv420p[va];"
            f"[1:v]scale={width}:{height},setsar=1,fps={fps},format=yuv420p[vb];"
            f"[va][vb]xfade=transition=coverleft:duration={d}:offset=0,"
            f"drawbox=x={int(width / 2 - gutter_w / 2)}:y={content_y}:"
            f"w={gutter_w}:h={content_h}:color=#d9c299@0.45:t=fill,"
            f"drawbox=x={int(width * 0.055)}:y={height - base_h}:"
            f"w={int(width * 0.89)}:h={max(8, base_h // 3)}:"
            f"color=#6f3f1e@0.92:t=fill,"
            f"drawbox=x={int(width * 0.065)}:y={height - base_h + max(8, base_h // 3)}:"
            f"w={int(width * 0.87)}:h={max(18, base_h // 2)}:"
            f"color=#2a1b10@0.72:t=fill,"
            f"{page_overlays}"
            f"drawbox=x='max(0,{width}-(t/{d})*{width}-{crease_w}/2)':"
            f"y={content_y}:w={crease_w}:h={content_h}:color=#fff4d8@0.62:t=fill,"
            f"drawbox=x='max(0,{width}-(t/{d})*{width}+{crease_w}/2)':"
            f"y={content_y}:w={max(4, crease_w // 3)}:h={content_h}:"
            f"color=#20160d@0.55:t=fill[v]"
        )
        cmd: list[str] = [
            "ffmpeg", "-y",
            "-loop", "1", "-t", str(d), "-i", str(frame_a),
            "-loop", "1", "-t", str(d), "-i", str(frame_b),
            "-f", "lavfi", "-t", str(d), "-i", "anullsrc=r=48000:cl=stereo",
        ]
        if cfg.sfx:
            cmd += ["-i", cfg.sfx]
            audio_filter = "[2:a][3:a]amix=inputs=2:duration=first:dropout_transition=0[a]"
        else:
            audio_filter = "[2:a]anull[a]"
        cmd += [
            "-filter_complex", f"{video_filter};{audio_filter}",
            "-map", "[v]", "-map", "[a]",
            "-t", str(d),
            "-c:v", "libx264", "-preset", "medium", "-crf", "22",
            "-pix_fmt", "yuv420p", "-r", str(fps),
            "-c:a", "aac", "-ar", "48000", "-b:a", "128k",
            "-shortest", str(out),
        ]
        try:
            run_ffmpeg(cmd)
        finally:
            frame_a.unlink(missing_ok=True)
            frame_b.unlink(missing_ok=True)
        return out

    def _page_flip_filters(
        self,
        *,
        page_count: int,
        duration: float,
        width: int,
        height: int,
        content_x: int,
        content_y: int,
        content_w: int,
        content_h: int,
        crease_w: int,
    ) -> str:
        filters = []
        gap = duration / page_count
        sheet_h = int(content_h * 1.02)
        sheet_y = content_y - int(content_h * 0.01)
        min_w = max(20, int(width * 0.04))
        max_w = int(content_w * 0.86)
        for idx in range(page_count):
            start = idx * gap
            end = min(duration, start + gap * 0.98)
            mid = start + (end - start) * 0.5
            # The page widens then narrows as it crosses the gutter. This is not
            # full 3D geometry, but it reads as a loose sheet instead of a wipe.
            w_expr = (
                f"if(lt(t,{mid:.4f}),"
                f"{min_w}+((t-{start:.4f})/{max(mid - start, 0.001):.4f})*{max_w - min_w},"
                f"{max_w}-((t-{mid:.4f})/{max(end - mid, 0.001):.4f})*{max_w - min_w})"
            )
            x_expr = (
                f"{content_x + content_w}-"
                f"((t-{start:.4f})/{max(end - start, 0.001):.4f})*{content_w}-({w_expr})/2"
            )
            filters.extend([
                f"drawbox=x='{x_expr}':y={sheet_y}:w='{w_expr}':h={sheet_h}:"
                f"color=#fbf0d2@0.97:t=fill:enable='between(t,{start:.4f},{end:.4f})'",
                f"drawbox=x='{x_expr}':y={sheet_y}:w='{w_expr}':h={max(6, height // 90)}:"
                f"color=#fff8e7@0.78:t=fill:enable='between(t,{start:.4f},{end:.4f})'",
                f"drawbox=x='{x_expr}':y={sheet_y + sheet_h - max(8, height // 70)}:"
                f"w='{w_expr}':h={max(8, height // 70)}:"
                f"color=#9b6b32@0.42:t=fill:enable='between(t,{start:.4f},{end:.4f})'",
                f"drawbox=x='{x_expr}':y={sheet_y}:w='{max(4, crease_w // 3)}':h={sheet_h}:"
                f"color=#6f451f@0.62:t=fill:enable='between(t,{start:.4f},{end:.4f})'",
                f"drawbox=x={content_x}:y={sheet_y + sheet_h - max(7, height // 90)}:"
                f"w={content_w}:h={max(5, height // 120)}:"
                f"color=#9b6b32@0.25:t=fill:enable='between(t,{start:.4f},{end:.4f})'",
            ])
        return ",".join(filters) + ","


class BookPageTurnV2Renderer:
    """Renders a higher-fidelity book page turn from real frame imagery."""

    def render(
        self,
        scene_a: Path,
        scene_b: Path,
        cfg: TransitionConfig,
        out: Path,
        *,
        width: int,
        height: int,
        fps: int,
    ) -> Path | None:
        work = out.parent
        work.mkdir(parents=True, exist_ok=True)
        frame_a = work / f"{out.stem}_a.png"
        frame_b = work / f"{out.stem}_b.png"
        try:
            extract_video_frame(scene_a, frame_a, first=False)
            extract_video_frame(scene_b, frame_b, first=True)
            return render_book_page_turn_v2(
                frame_a=frame_a,
                frame_b=frame_b,
                out=out,
                width=width,
                height=height,
                fps=fps,
                duration_sec=cfg.duration_sec,
                page_count=cfg.page_count or 2,
                sfx=cfg.sfx,
            )
        finally:
            frame_a.unlink(missing_ok=True)
            frame_b.unlink(missing_ok=True)


class LicensedClipRenderer:
    """Uses a licensed full-frame clip as the transition video."""

    def render(
        self,
        scene_a: Path,
        scene_b: Path,
        cfg: TransitionConfig,
        out: Path,
        *,
        width: int,
        height: int,
        fps: int,
    ) -> Path | None:
        asset = _resolve_asset_path(scene_a, cfg)
        d = cfg.duration_sec
        cmd: list[str] = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(asset),
            "-f", "lavfi", "-t", str(d), "-i", "anullsrc=r=48000:cl=stereo",
        ]
        if cfg.sfx:
            cmd += ["-i", cfg.sfx]
            audio_filter = "[1:a][2:a]amix=inputs=2:duration=first:dropout_transition=0[a]"
        else:
            audio_filter = "[1:a]anull[a]"
        video_filter = (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,fps={fps},format=yuv420p[v]"
        )
        cmd += [
            "-filter_complex", f"{video_filter};{audio_filter}",
            "-map", "[v]", "-map", "[a]",
            "-t", str(d),
            "-c:v", "libx264", "-preset", "medium", "-crf", "22",
            "-pix_fmt", "yuv420p", "-r", str(fps),
            "-c:a", "aac", "-ar", "48000", "-b:a", "128k",
            "-shortest", str(out),
        ]
        run_ffmpeg(cmd)
        return out


class OverlayAssetRenderer:
    """Overlays an alpha or green-screen stock asset on a generated base transition."""

    def render(
        self,
        scene_a: Path,
        scene_b: Path,
        cfg: TransitionConfig,
        out: Path,
        *,
        width: int,
        height: int,
        fps: int,
    ) -> Path | None:
        asset = _resolve_asset_path(scene_a, cfg)
        base_style = cfg.normalized_style if cfg.normalized_style != "none" else "fade"
        base_cfg = TransitionConfig(
            style=base_style,
            duration_sec=cfg.duration_sec,
            sfx=None,
            page_count=cfg.page_count,
        )
        base_renderer = _generated_renderer(base_style)
        base_clip = out.parent / f"{out.stem}_base.mp4"
        base_renderer.render(
            scene_a,
            scene_b,
            base_cfg,
            base_clip,
            width=width,
            height=height,
            fps=fps,
        )
        d = cfg.duration_sec
        alpha_asset = asset.suffix.lower() in {".mov", ".webm"}
        overlay_filter = (
            f"[1:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:"
            f"color={'black@0' if alpha_asset else '0x00FF00'},fps={fps},"
            + ("format=rgba[overlay]" if alpha_asset else "colorkey=0x00FF00:0.30:0.12,format=rgba[overlay]")
        )
        cmd: list[str] = [
            "ffmpeg", "-y",
            "-i", str(base_clip),
            "-stream_loop", "-1", "-i", str(asset),
            "-f", "lavfi", "-t", str(d), "-i", "anullsrc=r=48000:cl=stereo",
        ]
        if cfg.sfx:
            cmd += ["-i", cfg.sfx]
            audio_filter = "[2:a][3:a]amix=inputs=2:duration=first:dropout_transition=0[a]"
        else:
            audio_filter = "[2:a]anull[a]"
        video_filter = (
            f"[0:v]scale={width}:{height},setsar=1,fps={fps},format=yuv420p[base];"
            f"{overlay_filter};"
            "[base][overlay]overlay=(W-w)/2:(H-h)/2:shortest=1:format=auto[v]"
        )
        try:
            run_ffmpeg([
                *cmd,
                "-filter_complex", f"{video_filter};{audio_filter}",
                "-map", "[v]", "-map", "[a]",
                "-t", str(d),
                "-c:v", "libx264", "-preset", "medium", "-crf", "22",
                "-pix_fmt", "yuv420p", "-r", str(fps),
                "-c:a", "aac", "-ar", "48000", "-b:a", "128k",
                "-shortest", str(out),
            ])
        finally:
            base_clip.unlink(missing_ok=True)
        return out


REGISTRY: dict[str, TransitionRenderer] = {
    "none":      HardCutRenderer(),
    "fade":      XfadeRenderer(xfade_name="fade"),
    "page-turn": XfadeRenderer(xfade_name="slideleft"),  # v1 alias; swap to OverlayRenderer later
    "book-page-turn": BookPageTurnRenderer(),
    "book-page-turn-v2": BookPageTurnV2Renderer(),
    "stock-book-page-turn": BookPageTurnRenderer(),
    "slide":     XfadeRenderer(xfade_name="slideleft"),
    "wipe":      XfadeRenderer(xfade_name="wiperight"),
}


def _generated_renderer(style: str) -> TransitionRenderer:
    return REGISTRY["book-page-turn" if style == "stock-book-page-turn" else style]


def _project_root_for_scene(scene_path: Path) -> Path | None:
    for parent in scene_path.parents:
        if (parent / "storyboard.json").exists() or (parent / "context.json").exists():
            return parent
    return None


def _resolve_asset_path(
    scene_path: Path,
    cfg: TransitionConfig,
    *,
    project_root: Path | None = None,
) -> Path:
    if not cfg.asset_path:
        raise ValueError("asset_path is required for stock transition assets")
    raw = Path(cfg.asset_path)
    if raw.is_absolute():
        if not raw.exists():
            raise FileNotFoundError(f"transition asset not found: {raw}")
        return raw
    search_roots = [
        project_root,
        _project_root_for_scene(scene_path),
        _REPO_ROOT,
        Path.cwd(),
    ]
    seen: set[str] = set()
    for root in search_roots:
        if root is None:
            continue
        key = str(root.resolve())
        if key in seen:
            continue
        seen.add(key)
        candidate = (root / raw).resolve()
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"transition asset not found: {cfg.asset_path}")


def _file_sha1_short(path: Path, *, n_bytes: int = 65536) -> str:
    """Hash the first n_bytes of a file. Sufficient for cache invalidation
    when the scene clip changes — full-file hash isn't needed."""
    h = hashlib.sha1()
    with path.open("rb") as f:
        h.update(f.read(n_bytes))
    return h.hexdigest()[:16]


def transition_cache_key(scene_a: Path, scene_b: Path, cfg: TransitionConfig) -> str:
    """Cache key from style + duration + sfx + content hashes of adjacent scenes."""
    h = hashlib.sha1()
    h.update(cfg.style.encode())
    h.update(cfg.effective_renderer_mode.encode())
    h.update(f"{cfg.duration_sec:.4f}".encode())
    h.update((cfg.sfx or "").encode())
    h.update(str(cfg.page_count or "").encode())
    if cfg.style == "book-page-turn-v2":
        h.update(BOOK_PAGE_TURN_V2_RENDER_VERSION.encode())
    if cfg.asset_path:
        h.update(cfg.asset_path.encode())
        try:
            asset = _resolve_asset_path(scene_a, cfg)
        except FileNotFoundError:
            h.update(b"missing-asset")
        else:
            h.update(_file_sha1_short(asset).encode())
    h.update(_file_sha1_short(scene_a).encode())
    h.update(_file_sha1_short(scene_b).encode())
    return h.hexdigest()


def render_transition(
    scene_a: Path,
    scene_b: Path,
    cfg: TransitionConfig,
    cache_dir: Path,
    *,
    width: int,
    height: int,
    fps: int,
) -> Path | None:
    """Render a transition clip into the cache directory.

    Returns the path to the rendered clip, or None for hard-cut transitions
    (no clip is needed; the master concat stitches scenes directly).
    Cache hit: returns existing path without re-rendering.
    """
    if cfg.style == "none" and cfg.effective_renderer_mode == "generated":
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = transition_cache_key(scene_a, scene_b, cfg)
    out = cache_dir / f"{key}.mp4"
    if out.exists():
        logger.info("transition.cache_hit", key=key, style=cfg.style)
        return out
    logger.info(
        "transition.render",
        key=key,
        style=cfg.style,
        renderer_mode=cfg.effective_renderer_mode,
        duration=cfg.duration_sec,
        asset_path=cfg.asset_path,
    )
    if cfg.effective_renderer_mode == "licensed_clip":
        renderer: TransitionRenderer = LicensedClipRenderer()
    elif cfg.effective_renderer_mode == "overlay":
        renderer = OverlayAssetRenderer()
    else:
        renderer = _generated_renderer(cfg.normalized_style)
    return renderer.render(scene_a, scene_b, cfg, out, width=width, height=height, fps=fps)
