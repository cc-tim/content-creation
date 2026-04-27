from __future__ import annotations

from pathlib import Path

from pipeline.publish.channels import ChannelProfile
from pipeline.utils.ffmpeg import run_ffmpeg


def build_outro(
    profile: ChannelProfile,
    profile_png_path: Path,
    output_path: Path,
    aspect_ratio: str = "16:9",
) -> None:
    """Render a 20s outro clip. Raises subprocess.CalledProcessError on FFmpeg failure."""
    raise NotImplementedError
