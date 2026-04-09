from __future__ import annotations

from pathlib import Path

from pipeline.utils.ffmpeg import run_ffmpeg


def _escape_drawtext(text: str) -> str:
    """Escape special characters for FFmpeg drawtext filter."""
    return (
        text.replace("\\", "\\\\")
        .replace("'", "'\\''")
        .replace(":", "\\:")
        .replace("%", "%%")
    )


def apply_overlay(
    visual_path: Path,
    overlay: dict,
    width: int,
    height: int,
    work_dir: Path,
    scene_id: str,
    theme: dict | None = None,
) -> Path:
    """Composite an overlay on top of a visual segment.

    Safe overlay types:
    - title: centered large text with dim band
    - namecard: upper-lower-third name + role
    - text_top: thin band near the top
    - text_left: left-third vertical panel
    - text_emphasis: big centered text at upper-third

    The legacy ``text`` type is forbidden because it anchored to the bottom
    third and collided with burned-in subtitles.
    """
    theme = theme or {}
    overlay_type = overlay.get("type")

    if overlay_type == "text":
        raise ValueError(
            "overlay.type='text' is forbidden (collides with subtitles). "
            "Use text_top, text_left, or text_emphasis."
        )

    if overlay_type == "title":
        return _render_title(visual_path, overlay, width, height, work_dir, scene_id, theme)
    if overlay_type == "namecard":
        return _render_namecard(visual_path, overlay, width, height, work_dir, scene_id, theme)
    if overlay_type == "text_top":
        return _render_text_top(visual_path, overlay, width, height, work_dir, scene_id, theme)
    if overlay_type == "text_left":
        return _render_text_left(visual_path, overlay, width, height, work_dir, scene_id, theme)
    if overlay_type == "text_emphasis":
        return _render_text_emphasis(visual_path, overlay, width, height, work_dir, scene_id, theme)

    raise ValueError(f"unknown overlay type: {overlay_type!r}")


def _default_font(theme: dict) -> str:
    return theme.get("font", "Noto Sans CJK TC")


def _out_path(work_dir: Path, scene_id: str) -> Path:
    return work_dir / f"{scene_id}_overlay.mp4"


def _render_with_filter(visual_path: Path, vf: str, out: Path) -> Path:
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
            "-pix_fmt",
            "yuv420p",
            str(out),
        ]
    )
    return out


def _render_title(visual_path, overlay, width, height, work_dir, scene_id, theme):
    text = _escape_drawtext(overlay.get("text", ""))
    font = _default_font(theme)
    out = _out_path(work_dir, scene_id)
    vf = (
        f"drawbox=y=ih*0.35:w=iw:h=ih*0.3:color=black@0.6:t=fill,"
        f"drawtext=text='{text}':fontsize=52:fontcolor=white:font='{font}'"
        f":x=(w-text_w)/2:y=(h-text_h)/2"
        f":shadowcolor=black:shadowx=2:shadowy=2"
    )
    return _render_with_filter(visual_path, vf, out)


def _render_namecard(visual_path, overlay, width, height, work_dir, scene_id, theme):
    name = _escape_drawtext(overlay.get("name", ""))
    role = _escape_drawtext(overlay.get("role", ""))
    font = _default_font(theme)
    out = _out_path(work_dir, scene_id)
    # Upper-lower third (65-79%) to avoid subtitle collision at bottom
    vf = (
        f"drawbox=y=ih*0.65:w=iw:h=ih*0.14:color=black@0.7:t=fill,"
        f"drawtext=text='{name}':fontsize=36:fontcolor=white:font='{font}'"
        f":x=w*0.05:y=h*0.67"
        f":shadowcolor=black:shadowx=1:shadowy=1,"
        f"drawtext=text='{role}':fontsize=24:fontcolor=#cccccc:font='{font}'"
        f":x=w*0.05:y=h*0.73"
    )
    return _render_with_filter(visual_path, vf, out)


def _render_text_top(visual_path, overlay, width, height, work_dir, scene_id, theme):
    text = _escape_drawtext(overlay.get("text", ""))
    font = _default_font(theme)
    color = overlay.get("color", theme.get("accent", "#38bdf8"))
    font_size = overlay.get("font_size", 44)
    out = _out_path(work_dir, scene_id)
    # Band at y = 4%..16% of height (well above the subtitles at the bottom)
    vf = (
        f"drawbox=x=0:y=ih*0.04:w=iw:h=ih*0.12:color=black@0.45:t=fill,"
        f"drawtext=text='{text}':fontsize={font_size}:fontcolor={color}:font='{font}'"
        f":x=(w-text_w)/2:y=h*0.08"
        f":shadowcolor=black@0.5:shadowx=2:shadowy=2"
    )
    return _render_with_filter(visual_path, vf, out)


def _render_text_left(visual_path, overlay, width, height, work_dir, scene_id, theme):
    text = _escape_drawtext(overlay.get("text", ""))
    font = _default_font(theme)
    color = overlay.get("color", theme.get("accent", "#38bdf8"))
    font_size = overlay.get("font_size", 40)
    out = _out_path(work_dir, scene_id)
    # Left third, vertical center, with a dim backing box for contrast.
    vf = (
        f"drawbox=x=iw*0.04:y=ih*0.25:w=iw*0.32:h=ih*0.50:color=black@0.40:t=fill,"
        f"drawtext=text='{text}':fontsize={font_size}:fontcolor={color}:font='{font}'"
        f":x=w*0.06:y=h*0.30:text_align=left"
        f":shadowcolor=black@0.5:shadowx=2:shadowy=2"
    )
    return _render_with_filter(visual_path, vf, out)


def _render_text_emphasis(visual_path, overlay, width, height, work_dir, scene_id, theme):
    text = _escape_drawtext(overlay.get("text", ""))
    font = _default_font(theme)
    color = overlay.get("color", theme.get("accent", "#fbbf24"))
    font_size = overlay.get("font_size", 72)
    out = _out_path(work_dir, scene_id)
    # Giant centered text, upper third (never below 60% height).
    vf = (
        f"drawtext=text='{text}':fontsize={font_size}:fontcolor={color}:font='{font}'"
        f":x=(w-text_w)/2:y=h*0.35"
        f":shadowcolor=black@0.7:shadowx=3:shadowy=3:borderw=2:bordercolor=black"
    )
    return _render_with_filter(visual_path, vf, out)
