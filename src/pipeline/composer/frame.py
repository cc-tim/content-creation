from __future__ import annotations

import subprocess
from pathlib import Path

from pipeline.utils.ffmpeg import run_ffmpeg

SUPPORTED_FRAME_STYLES: set[str] = {"open_book_page"}


def _open_book_geometry(width: int, height: int) -> dict[str, int | str]:
    margin_x = int(width * 0.065)
    margin_y = int(height * 0.075)
    page_x = margin_x
    page_y = margin_y
    page_w = width - margin_x * 2
    page_h = height - margin_y * 2
    inset_x = page_x + int(page_w * 0.075)
    inset_y = page_y + int(page_h * 0.105)
    inset_w = page_w - int(page_w * 0.15)
    inset_h = page_h - int(page_h * 0.21)

    return {
        "page_x": page_x,
        "page_y": page_y,
        "page_w": page_w,
        "page_h": page_h,
        "inset_x": inset_x,
        "inset_y": inset_y,
        "inset_w": inset_w,
        "inset_h": inset_h,
        "bg": "#2b1f14",
        "page": "#f4ead2",
        "page_edge": "#caa766",
        "shadow": "#1a120b",
        "gutter": "#d9c299",
    }


def composite_scene_frame(
    src: Path,
    out: Path,
    *,
    frame_style: str | None,
    width: int,
    height: int,
    fps: int = 30,
) -> Path:
    """Wrap a scene visual in a renderable theme frame.

    The frame is video-only by design. Compose muxes narration after this step,
    so audio handling stays centralized in ComposeStage._mux.
    """
    if not frame_style:
        return src
    if frame_style not in SUPPORTED_FRAME_STYLES:
        raise ValueError(
            f"Unknown frame style: {frame_style!r}. "
            f"Supported: {sorted(SUPPORTED_FRAME_STYLES)}"
        )
    if frame_style == "open_book_page":
        return _composite_open_book_page(src, out, width=width, height=height, fps=fps)
    raise AssertionError(f"Unhandled frame style: {frame_style}")


def _composite_open_book_page(
    src: Path,
    out: Path,
    *,
    width: int,
    height: int,
    fps: int,
) -> Path:
    g = _open_book_geometry(width, height)
    duration = _probe_duration_sec(src)
    page_x = g["page_x"]
    page_y = g["page_y"]
    page_w = g["page_w"]
    page_h = g["page_h"]
    inset_x = g["inset_x"]
    inset_y = g["inset_y"]
    inset_w = g["inset_w"]
    inset_h = g["inset_h"]

    book_filter = (
        f"[1:v]"
        f"drawbox=x={page_x + 16}:y={page_y + 18}:w={page_w}:h={page_h}:"
        f"color={g['shadow']}@0.58:t=fill,"
        f"drawbox=x={page_x}:y={page_y}:w={page_w}:h={page_h}:"
        f"color={g['page']}:t=fill,"
        f"drawbox=x={page_x}:y={page_y}:w={page_w}:h={page_h}:"
        f"color={g['page_edge']}:t=5,"
        f"drawbox=x={inset_x - 10}:y={inset_y - 10}:w={inset_w + 20}:h={inset_h + 20}:"
        f"color=#b08a4a@0.38:t=fill,"
        f"drawbox=x={inset_x - 4}:y={inset_y - 4}:w={inset_w + 8}:h={inset_h + 8}:"
        f"color=#3b2a18@0.45:t=3"
        f"[book]"
    )
    content_filter = (
        f"[0:v]scale={inset_w}:{inset_h}:force_original_aspect_ratio=decrease,"
        f"pad={inset_w}:{inset_h}:(ow-iw)/2:(oh-ih)/2:color=#18120b,"
        f"setsar=1,fps={fps},format=rgba[content]"
    )
    overlay_filter = (
        f"[book][content]overlay=x={inset_x}:y={inset_y},"
        f"format=yuv420p[v]"
    )
    run_ffmpeg([
        "ffmpeg", "-y",
        "-i", str(src),
        "-f", "lavfi", "-i", f"color=c={g['bg']}:s={width}x{height}:r={fps}:d={duration}",
        "-filter_complex", f"{book_filter};{content_filter};{overlay_filter}",
        "-map", "[v]",
        "-t", str(duration),
        "-an",
        "-c:v", "libx264", "-preset", "medium", "-crf", "21",
        "-pix_fmt", "yuv420p", "-r", str(fps),
        "-shortest", str(out),
    ])
    return out


def _probe_duration_sec(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return max(0.01, float(result.stdout.strip()))
