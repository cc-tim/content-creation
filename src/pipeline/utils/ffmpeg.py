from __future__ import annotations

import shutil
import subprocess


def check_ffmpeg_available() -> bool:
    """Check if ffmpeg is on PATH."""
    return shutil.which("ffmpeg") is not None


def build_extract_clip_cmd(
    input_path: str,
    output_path: str,
    start_sec: float,
    end_sec: float,
) -> list[str]:
    """Build ffmpeg command to extract a clip between start and end seconds."""
    duration = end_sec - start_sec
    return [
        "ffmpeg", "-y",
        "-ss", str(start_sec),
        "-i", input_path,
        "-t", str(duration),
        "-c", "copy",
        output_path,
    ]


def build_burn_subtitles_cmd(
    input_path: str,
    subtitle_path: str,
    output_path: str,
    font_name: str = "Noto Sans CJK TC",
    font_size: int = 24,
) -> list[str]:
    """Build ffmpeg command to burn subtitles into video."""
    # Escape special chars for FFmpeg filter syntax: \ : [ ] ; , '
    escaped_sub_path = subtitle_path.replace("\\", "\\\\").replace(":", "\\:")
    style = f"FontName={font_name},FontSize={font_size}"
    subtitle_filter = f"subtitles={escaped_sub_path}:force_style='{style}'"
    return [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", subtitle_filter,
        "-c:a", "copy",
        output_path,
    ]


def build_concat_cmd(
    filelist_path: str,
    output_path: str,
) -> list[str]:
    """Build ffmpeg command to concatenate files listed in a text file."""
    return [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", filelist_path,
        "-c", "copy",
        output_path,
    ]


def run_ffmpeg(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess[str]:
    """Execute an ffmpeg command. Raises on failure."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )
