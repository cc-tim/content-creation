from __future__ import annotations

from pathlib import Path

from pipeline.composer.compartment_renderers.running_out import (
    render_running_out_frames,
)
from pipeline.utils.ffmpeg import run_ffmpeg


def build_compartment_loop(
    compartment: dict,
    scene_duration_sec: float,
    scene_width: int,
    scene_height: int,
    work_dir: Path,
    scene_id: str,
) -> Path:
    """Build a looping compartment video sized for overlay on a scene.

    Returns a path to an mp4 whose duration matches scene_duration_sec so it
    can be laid over the main visual as a second input.
    """
    ctype = compartment.get("type", "running_out")
    if ctype != "running_out":
        raise ValueError(f"unknown compartment type: {ctype}")

    size = compartment.get("size", {"width": 0.35, "height": 0.6})
    # libx264 with yuv420p requires even dimensions.
    width = max(64, int(scene_width * float(size.get("width", 0.35))) // 2 * 2)
    height = max(64, int(scene_height * float(size.get("height", 0.6))) // 2 * 2)

    frames_dir = work_dir / f"{scene_id}_compartment_frames"
    frames = render_running_out_frames(
        out_dir=frames_dir,
        config=compartment.get("animation", {}),
        width=width,
        height=height,
    )
    if not frames:
        raise ValueError("compartment produced zero frames")

    # Build a concat list that loops through stages. Duration per frame lives
    # in each CompartmentFrame. The concat demuxer resolves `file '...'` entries
    # relative to the concat file's own directory, so we must write absolute
    # paths — otherwise a relative work_dir (as in production compose) causes
    # ffmpeg to double-prefix and fail.
    stage_list_path = work_dir / f"{scene_id}_compartment_frames.txt"
    lines: list[str] = []
    for frame in frames:
        lines.append(f"file '{frame.path.resolve().as_posix()}'")
        lines.append(f"duration {frame.duration_sec}")
    # ffmpeg concat demuxer requires the final file listed one extra time.
    lines.append(f"file '{frames[-1].path.resolve().as_posix()}'")
    stage_list_path.write_text("\n".join(lines) + "\n")

    loop_mp4 = work_dir / f"{scene_id}_compartment.mp4"
    # -stream_loop -1 loops the concat until we hit -t scene_duration_sec.
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-stream_loop",
            "-1",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(stage_list_path),
            "-t",
            f"{scene_duration_sec}",
            "-vf",
            f"fps=30,scale={width}:{height},format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            str(loop_mp4),
        ]
    )
    return loop_mp4


def composite_compartment_on_scene(
    scene_video: Path,
    compartment_video: Path,
    compartment_config: dict,
    scene_width: int,
    scene_height: int,
    work_dir: Path,
    scene_id: str,
) -> Path:
    """Overlay the compartment loop on top of the scene video using FFmpeg."""
    position = compartment_config.get("position", "right")
    size = compartment_config.get("size", {"width": 0.35, "height": 0.6})
    # libx264 with yuv420p requires even dimensions.
    cw = int(scene_width * float(size.get("width", 0.35))) // 2 * 2
    ch = int(scene_height * float(size.get("height", 0.6))) // 2 * 2

    if position == "right":
        x_expr = f"W-w-{int(scene_width * 0.03)}"
    elif position == "left":
        x_expr = f"{int(scene_width * 0.03)}"
    else:
        x_expr = "(W-w)/2"
    y_expr = "(H-h)/2"

    shake = compartment_config.get("animation", {}).get("shake", False)
    if shake:
        amp = max(2, cw // 40)
        x_expr = f"({x_expr})+({amp}*sin(6*t))"
        y_expr = f"({y_expr})+({amp}*cos(6*t))"

    out = work_dir / f"{scene_id}_with_compartment.mp4"
    filter_complex = (
        f"[1:v]scale={cw}:{ch}[comp];"
        f"[0:v][comp]overlay=x='{x_expr}':y='{y_expr}':format=auto[v]"
    )
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(scene_video),
            "-i",
            str(compartment_video),
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            str(out),
        ]
    )
    return out
