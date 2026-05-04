"""Per-seam transition primitives for the compose pipeline.

A transition is a short clip rendered between scene N and scene N+1.
Storyboards declare transitions sparsely in the `transitions[]` array;
missing entries mean a hard cut.

v1 implementation uses ffmpeg's built-in `xfade` filter for all visual
styles. The `page-turn` style is initially aliased to `xfade slideleft`
— a slide-style approximation. The Protocol abstraction allows swapping
to a PNG/webm `OverlayRenderer` later behind the same interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import structlog

from pipeline.storyboard import Transition
from pipeline.utils.ffmpeg import run_ffmpeg

logger = structlog.get_logger()

SUPPORTED_STYLES: set[str] = {"none", "fade", "page-turn", "slide", "wipe"}


@dataclass(frozen=True)
class TransitionConfig:
    """Render-ready config for one transition between two scenes."""

    style: str
    duration_sec: float
    sfx: str | None

    def __post_init__(self) -> None:
        if self.style not in SUPPORTED_STYLES:
            raise ValueError(
                f"Unknown transition style: {self.style!r}. "
                f"Supported: {sorted(SUPPORTED_STYLES)}"
            )

    @classmethod
    def from_transition(cls, t: Transition) -> TransitionConfig:
        return cls(style=t.style, duration_sec=t.duration_sec, sfx=t.sfx)


class TransitionRenderer(Protocol):
    """Protocol implemented by each per-style renderer.

    Implementations should be deterministic: same inputs -> same output bytes.
    The cache layer above relies on this.
    """

    def render(
        self,
        scene_a: Path,
        scene_b: Path,
        cfg: TransitionConfig,
        out: Path,
        *,
        width: int,
        height: int,
        fps: int,
    ) -> Path | None:
        """Render the transition clip between scene_a and scene_b to `out`.

        Returns the output path on success, or None if no clip should be
        emitted (e.g. for HardCutRenderer — concat just stitches the two
        scenes directly).
        """
        ...


class HardCutRenderer:
    """Emits no transition clip — the master concat stitches scenes directly."""

    def render(
        self,
        scene_a: Path,
        scene_b: Path,
        cfg: TransitionConfig,
        out: Path,
        *,
        width: int,
        height: int,
        fps: int,
    ) -> Path | None:
        return None


class XfadeRenderer:
    """Renders a transition using ffmpeg's xfade filter.

    Pipeline:
      1. Extract the last frame of scene_a and first frame of scene_b as PNG.
      2. Build a static-frame video clip of cfg.duration_sec from each PNG
         (with silent stereo audio at 48kHz to match the project standard).
      3. Apply xfade between the two clips for cfg.duration_sec.
      4. If cfg.sfx is set, amix the sfx into the audio track.
      5. Encode H.264 + AAC with the same params as scene clips so the
         master concat demuxer can stream-copy the result.
    """

    def __init__(self, xfade_name: str) -> None:
        # xfade built-in transition name (fade | slideleft | slideright | wiperight | wipeleft ...)
        self.xfade_name = xfade_name

    def render(
        self,
        scene_a: Path,
        scene_b: Path,
        cfg: TransitionConfig,
        out: Path,
        *,
        width: int,
        height: int,
        fps: int,
    ) -> Path | None:
        work = out.parent
        work.mkdir(parents=True, exist_ok=True)
        frame_a = work / f"{out.stem}_a.png"
        frame_b = work / f"{out.stem}_b.png"

        # 1. Extract last frame of scene_a (sseof = seek from end)
        run_ffmpeg([
            "ffmpeg", "-y", "-sseof", "-0.05", "-i", str(scene_a),
            "-frames:v", "1", "-update", "1", str(frame_a),
        ])
        # 2. Extract first frame of scene_b
        run_ffmpeg([
            "ffmpeg", "-y", "-i", str(scene_b),
            "-frames:v", "1", "-update", "1", str(frame_b),
        ])

        # 3. Build the xfade + audio pipeline in one ffmpeg invocation.
        d = cfg.duration_sec
        # filter_complex pieces
        video_filter = (
            f"[0:v]scale={width}:{height},setsar=1,fps={fps},format=yuv420p[va];"
            f"[1:v]scale={width}:{height},setsar=1,fps={fps},format=yuv420p[vb];"
            f"[va][vb]xfade=transition={self.xfade_name}:duration={d}:offset=0[v]"
        )
        # Inputs: two static images looped, one anullsrc for silent base audio,
        # plus the sfx file if provided.
        cmd: list[str] = [
            "ffmpeg", "-y",
            "-loop", "1", "-t", str(d), "-i", str(frame_a),
            "-loop", "1", "-t", str(d), "-i", str(frame_b),
            "-f", "lavfi", "-t", str(d), "-i", "anullsrc=r=48000:cl=stereo",
        ]
        if cfg.sfx:
            cmd += ["-i", cfg.sfx]
            audio_filter = "[2:a][3:a]amix=inputs=2:duration=first:dropout_transition=0[a]"
        else:
            audio_filter = "[2:a]anull[a]"
        cmd += [
            "-filter_complex", f"{video_filter};{audio_filter}",
            "-map", "[v]", "-map", "[a]",
            "-t", str(d),
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-pix_fmt", "yuv420p", "-r", str(fps),
            "-c:a", "aac", "-ar", "48000", "-b:a", "128k",
            "-shortest", str(out),
        ]
        run_ffmpeg(cmd)
        # Cleanup intermediates
        frame_a.unlink(missing_ok=True)
        frame_b.unlink(missing_ok=True)
        return out
