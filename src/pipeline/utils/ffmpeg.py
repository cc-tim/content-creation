from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

logger = logging.getLogger(__name__)


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
        "ffmpeg",
        "-y",
        "-ss",
        str(start_sec),
        "-i",
        input_path,
        "-t",
        str(duration),
        "-c",
        "copy",
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
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-vf",
        subtitle_filter,
        "-c:a",
        "copy",
        output_path,
    ]


def build_concat_cmd(
    filelist_path: str,
    output_path: str,
) -> list[str]:
    """Build ffmpeg command to concatenate files listed in a text file."""
    return [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        filelist_path,
        "-c",
        "copy",
        output_path,
    ]


def ffmpeg_concat(inputs: list[Path], output: Path) -> None:
    """Stream-copy concatenate video files using the concat demuxer (no re-encode)."""
    list_file = output.parent / f"_concat_{output.stem}.txt"
    list_file.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in inputs),
        encoding="utf-8",
    )
    try:
        run_ffmpeg(build_concat_cmd(str(list_file), str(output)))
    finally:
        list_file.unlink(missing_ok=True)


def run_ffmpeg(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess[str]:
    """Execute an ffmpeg command. Raises on failure."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )


# -- async / parallel infrastructure --

_FFMPEG_EXECUTOR: ThreadPoolExecutor | None = None
_EXECUTOR_LOCK = threading.Lock()


def init_ffmpeg_executor(max_workers: int) -> ThreadPoolExecutor:
    """Initialize (or reinitialize) the global executor for FFmpeg subprocesses."""
    global _FFMPEG_EXECUTOR
    with _EXECUTOR_LOCK:
        old = _FFMPEG_EXECUTOR
        _FFMPEG_EXECUTOR = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="ffmpeg"
        )
        if old is not None:
            old.shutdown(wait=False)
    return _FFMPEG_EXECUTOR


def get_ffmpeg_executor() -> ThreadPoolExecutor:
    """Return the shared executor. Lazily initializes with 4 workers."""
    global _FFMPEG_EXECUTOR
    if _FFMPEG_EXECUTOR is None:
        with _EXECUTOR_LOCK:
            if _FFMPEG_EXECUTOR is None:
                _FFMPEG_EXECUTOR = ThreadPoolExecutor(
                    max_workers=4, thread_name_prefix="ffmpeg"
                )
    return _FFMPEG_EXECUTOR


def shutdown_ffmpeg_executor(wait: bool = True) -> None:
    """Clean shutdown of the shared executor. Idempotent."""
    global _FFMPEG_EXECUTOR
    with _EXECUTOR_LOCK:
        if _FFMPEG_EXECUTOR is not None:
            _FFMPEG_EXECUTOR.shutdown(wait=wait)
            _FFMPEG_EXECUTOR = None


async def async_run_ffmpeg(
    cmd: list[str], timeout: int = 600
) -> subprocess.CompletedProcess[str]:
    """Run FFmpeg in the shared thread pool without blocking the event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        get_ffmpeg_executor(),
        lambda: run_ffmpeg(cmd, timeout),
    )


def verify_is_image(path: Path) -> bool:
    """Return True if *path* is a valid image (not HTML, SVG, or corrupt)."""
    try:
        from PIL import Image
        img = Image.open(path)
        img.verify()
        return True
    except Exception:
        logger.warning("verify_is_image.failed", path=str(path))
        return False
