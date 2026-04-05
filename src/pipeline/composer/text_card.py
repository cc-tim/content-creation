from __future__ import annotations

from pathlib import Path

from pipeline.utils.ffmpeg import run_ffmpeg


def _escape_drawtext(text: str) -> str:
    """Escape special characters for FFmpeg drawtext filter."""
    return text.replace("\\", "\\\\").replace("'", "'\\''").replace(":", "\\:").replace("%", "%%")


def render_text_card(
    visual: dict,
    duration_sec: float,
    width: int,
    height: int,
    work_dir: Path,
    scene_id: str,
) -> Path:
    """Generate a text card: styled text on a solid background."""
    text = visual.get("text", "")
    bg_color = visual.get("background", "#1a1a2e")
    font_size = visual.get("font_size", 48)
    font = "Noto Sans CJK TC"

    output = work_dir / f"{scene_id}_visual.mp4"
    escaped = _escape_drawtext(text)

    # Handle multi-line: split by \n and stack with line_spacing
    lines = escaped.split("\\n")
    if len(lines) == 1:
        drawtext = (
            f"drawtext=text='{escaped}':fontfile=:fontsize={font_size}"
            f":fontcolor=white:font='{font}'"
            f":x=(w-text_w)/2:y=(h-text_h)/2"
            f":shadowcolor=black:shadowx=2:shadowy=2"
        )
    else:
        # Stack multiple drawtext filters for each line
        filters = []
        total_lines = len(lines)
        for i, line in enumerate(lines):
            y_offset = f"(h/2)+({i}-{total_lines}/2)*{font_size + 10}"
            filters.append(
                f"drawtext=text='{line}':fontsize={font_size}"
                f":fontcolor=white:font='{font}'"
                f":x=(w-text_w)/2:y={y_offset}"
                f":shadowcolor=black:shadowx=2:shadowy=2"
            )
        drawtext = ",".join(filters)

    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={bg_color}:s={width}x{height}:d={duration_sec}:r=30",
            "-vf",
            drawtext,
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
