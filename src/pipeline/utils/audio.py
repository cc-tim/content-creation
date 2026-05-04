"""Audio normalization helpers for narration recording / upload.

Used by the dashboard's narration-source endpoint to convert browser-recorded
opus-in-webm uploads into a consistent WAV format suitable for the TTS-bypass
(`narration_source.engine = 'prerecorded'`) flow.
"""

from __future__ import annotations

from pathlib import Path

import structlog

from pipeline.utils.ffmpeg import run_ffmpeg

logger = structlog.get_logger()


def normalize_to_wav(src: Path, dst: Path) -> Path:
    """Normalize loudness and convert to 48kHz/stereo PCM WAV.

    Uses ffmpeg's single-pass `loudnorm` filter (target -16 LUFS, true-peak
    -1.5 dBTP, LRA 11) which is ample for narration. Two-pass loudnorm gives
    slightly tighter conformance but isn't worth the latency hit for this use.

    Resamples to 48000 Hz and forces stereo so downstream concat with
    project narration tracks (also 48k/stereo per `_synthesize_pass` and the
    Plan 1 transition renderer) doesn't trigger format mismatches.
    """
    if not src.exists():
        raise FileNotFoundError(f"audio source not found: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    logger.info("audio.normalize.start", src=str(src), dst=str(dst))
    run_ffmpeg([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(src),
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-ar", "48000",
        "-ac", "2",
        "-c:a", "pcm_s16le",
        str(dst),
    ])
    logger.info("audio.normalize.complete", dst=str(dst), size=dst.stat().st_size)
    return dst
