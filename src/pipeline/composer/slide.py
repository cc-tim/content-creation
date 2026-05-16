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
    theme: dict | None = None,
) -> Path:
    """Render a presentation-style slide: title + bullet points.

    Tolerates the rich_slide-shaped variant the storyboard model sometimes emits
    (``{type: "slide", text, layout}``): forwards to ``render_rich_slide`` so
    the scene renders via Pillow with proper CJK support instead of producing
    an empty background. Raises if no renderable text is present at all.
    """
    theme = theme or {}
    title = visual.get("title", "")
    bullets = visual.get("bullets", [])
    text = visual.get("text", "")

    if not title and not bullets:
        if not text:
            raise ValueError(
                f"slide visual for {scene_id} has no title/bullets/text; "
                f"keys={sorted(visual.keys())!r}"
            )
        from pipeline.composer.rich_slide import render_rich_slide

        rich_visual = dict(visual)
        layout = rich_visual.get("layout")
        if layout not in ("slide", "quote"):
            rich_visual["layout"] = "quote"
        return render_rich_slide(
            rich_visual, duration_sec, width, height, work_dir, scene_id, theme
        )
    font = theme.get("font", "Noto Sans CJK TC")
    bg_color = visual.get("background", theme.get("background", "#1e293b"))
    text_color = theme.get("text_color", "white")
    accent = theme.get("accent", "#38bdf8")
    output = work_dir / f"{scene_id}_visual.mp4"

    # Build filter chain: accent bar at top, title, bullets
    filters = []

    # Accent bar at top (thin colored line for visual interest)
    filters.append(
        f"drawbox=x=0:y=0:w=iw:h=4:color={accent}:t=fill"
    )

    # Title — large, centered near top, accent color
    if title:
        escaped_title = _escape_drawtext(title)
        filters.append(
            f"drawtext=text='{escaped_title}':fontsize=56"
            f":fontcolor={accent}:font='{font}'"
            f":x=(w-text_w)/2:y=h*0.15"
            f":shadowcolor=black@0.3:shadowx=1:shadowy=1"
        )

    # Bullets — lighter color, left-aligned
    for i, bullet in enumerate(bullets):
        escaped = _escape_drawtext(f"  {bullet}")
        y_pos = f"h*0.35+{i}*60"
        filters.append(
            f"drawtext=text='{escaped}':fontsize=36"
            f":fontcolor={text_color}:font='{font}'"
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
