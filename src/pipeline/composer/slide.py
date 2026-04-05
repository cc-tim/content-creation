from __future__ import annotations

from pathlib import Path

from pipeline.utils.ffmpeg import run_ffmpeg


def _escape_drawtext(text: str) -> str:
    """Escape special characters for FFmpeg drawtext filter."""
    return text.replace("\\", "\\\\").replace("'", "'\\''").replace(":", "\\:").replace("%", "%%")


def render_slide(
    visual: dict,
    duration_sec: float,
    width: int,
    height: int,
    work_dir: Path,
    scene_id: str,
) -> Path:
    """Render a presentation-style slide: title + bullet points."""
    title = visual.get("title", "")
    bullets = visual.get("bullets", [])
    font = "Noto Sans CJK TC"
    bg_color = "#1a1a2e"
    output = work_dir / f"{scene_id}_visual.mp4"

    # Build filter chain: title at top, bullets below
    filters = []

    # Title — large, centered near top
    if title:
        escaped_title = _escape_drawtext(title)
        filters.append(
            f"drawtext=text='{escaped_title}':fontsize=56"
            f":fontcolor=white:font='{font}'"
            f":x=(w-text_w)/2:y=h*0.15"
            f":shadowcolor=black:shadowx=2:shadowy=2"
        )

    # Bullets — smaller, left-aligned with bullet marker
    for i, bullet in enumerate(bullets):
        escaped = _escape_drawtext(f"  {bullet}")
        y_pos = f"h*0.35+{i}*60"
        filters.append(
            f"drawtext=text='{escaped}':fontsize=36"
            f":fontcolor=#cccccc:font='{font}'"
            f":x=w*0.1:y={y_pos}"
        )

    vf = ",".join(filters) if filters else "null"

    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={bg_color}:s={width}x{height}:d={duration_sec}:r=30",
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            str(output),
        ]
    )
    return output
