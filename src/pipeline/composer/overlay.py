from __future__ import annotations

from pathlib import Path

from pipeline.utils.ffmpeg import run_ffmpeg


def _escape_drawtext(text: str) -> str:
    """Escape special characters for FFmpeg drawtext filter."""
    return text.replace("\\", "\\\\").replace("'", "'\\''").replace(":", "\\:").replace("%", "%%")


def apply_overlay(
    visual_path: Path,
    overlay: dict,
    output_path: Path,
    width: int = 1280,
    height: int = 720,
) -> Path:
    """Composite an overlay (title, text, namecard) on top of a visual segment.

    Overlay types:
    - title: centered large text
    - text: lower-third bar with text
    - namecard: lower-third bar with name + role
    """
    overlay_type = overlay.get("type", "text")
    font = "Noto Sans CJK TC"

    if overlay_type == "title":
        text = _escape_drawtext(overlay.get("text", ""))
        vf = (
            f"drawbox=y=ih*0.35:w=iw:h=ih*0.3:color=black@0.6:t=fill,"
            f"drawtext=text='{text}':fontsize=52"
            f":fontcolor=white:font='{font}'"
            f":x=(w-text_w)/2:y=(h-text_h)/2"
            f":shadowcolor=black:shadowx=2:shadowy=2"
        )

    elif overlay_type == "namecard":
        name = _escape_drawtext(overlay.get("name", ""))
        role = _escape_drawtext(overlay.get("role", ""))
        # Position at upper-lower area (65-79%) to avoid subtitle collision at bottom
        vf = (
            f"drawbox=y=ih*0.65:w=iw:h=ih*0.14:color=black@0.7:t=fill,"
            f"drawtext=text='{name}':fontsize=36"
            f":fontcolor=white:font='{font}'"
            f":x=w*0.05:y=h*0.67"
            f":shadowcolor=black:shadowx=1:shadowy=1,"
            f"drawtext=text='{role}':fontsize=24"
            f":fontcolor=#cccccc:font='{font}'"
            f":x=w*0.05:y=h*0.73"
        )

    else:
        # Default: text overlay as lower-third bar
        text = _escape_drawtext(overlay.get("text", ""))
        vf = (
            f"drawbox=y=ih*0.82:w=iw:h=ih*0.12:color=black@0.7:t=fill,"
            f"drawtext=text='{text}':fontsize=32"
            f":fontcolor=white:font='{font}'"
            f":x=(w-text_w)/2:y=h*0.85"
            f":shadowcolor=black:shadowx=1:shadowy=1"
        )

    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(visual_path),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-c:a",
            "copy",
            str(output_path),
        ]
    )
    return output_path
