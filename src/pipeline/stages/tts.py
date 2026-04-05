from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import structlog

from pipeline.config import PipelineConfig
from pipeline.stages.base import PipelineContext, PipelineStage
from pipeline.utils.srt import SrtEntry, write_srt

logger = structlog.get_logger()


def extract_narration_segments(script: str) -> list[str]:
    """Extract plain narration text from a script with markers."""
    segments: list[str] = []
    # Match all marker formats including extended ones like [HOOK - 0:00-0:30]
    marker_pattern = re.compile(
        r"^\["
        r"(HOOK|CONTEXT|RISING|CLIMAX|AFTERMATH|ANALYSIS|RISING ACTION)"
        r"(\s*-\s*[^\]]+)?"  # optional timestamp suffix like " - 0:00-0:30"
        r"\]$"
        r"|"
        r"^\[CLIP:[^\]]+\]$"
        r"|"
        r"^\[OVERLAY:[^\]]+\]$"
        r"|"
        r"^\[PAUSE:\d+s\]$"
    )

    for line in script.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if marker_pattern.match(stripped):
            continue
        segments.append(stripped)

    return segments


async def generate_edge_tts(text: str, voice: str, output_path: Path) -> dict[str, Any]:
    """Generate TTS audio using edge-tts. Returns timing metadata."""
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    submaker = edge_tts.SubMaker()

    with open(output_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.feed(chunk)

    return {
        "duration_ms": 0,  # edge-tts doesn't provide total duration directly
        "word_timings": [],  # simplified for MVP
    }


class TtsStage(PipelineStage):
    @property
    def name(self) -> str:
        return "tts"

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.script_path or not ctx.script_path.exists():
            raise ValueError("No script available — run scriptwrite stage first")

        logger.info("tts.start", locale=ctx.locale)

        config = PipelineConfig()
        voice = config.get_tts_voice(ctx.locale)
        script_text = ctx.script_path.read_text(encoding="utf-8")

        audio_dir = ctx.work_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        segments = extract_narration_segments(script_text)
        logger.info("tts.segments", count=len(segments))

        # Generate audio per segment
        segment_paths: list[Path] = []
        segment_timings: list[dict[str, Any]] = []
        cumulative_ms = 0

        for i, text in enumerate(segments):
            seg_path = audio_dir / f"segment_{i:03d}.mp3"
            await generate_edge_tts(text, voice, seg_path)

            # Get actual duration via ffprobe
            est_duration_ms = _get_audio_duration_ms(seg_path)

            segment_timings.append(
                {
                    "index": i,
                    "text": text,
                    "path": str(seg_path),
                    "start_ms": cumulative_ms,
                    "duration_ms": est_duration_ms,
                }
            )
            segment_paths.append(seg_path)
            cumulative_ms += est_duration_ms

        # Concatenate all segments into one file
        narration_path = audio_dir / f"narration_{ctx.locale}.mp3"
        _concatenate_audio(segment_paths, narration_path)
        ctx.narration_path = narration_path

        # Generate SRT from segment timings — split long text into subtitle chunks
        srt_entries = _build_subtitle_entries(segment_timings)
        subtitle_path = audio_dir / f"subtitles_{ctx.locale}.srt"
        write_srt(srt_entries, subtitle_path)
        ctx.subtitle_path = subtitle_path

        ctx.segment_timings = segment_timings

        logger.info("tts.complete", segments=len(segments), path=str(narration_path))
        return ctx


def _split_text_for_subtitles(text: str, max_chars: int = 18) -> list[str]:
    """Split text into subtitle-sized chunks.

    For CJK text, split by punctuation first (。！？，、；),
    then by max_chars if still too long. Max 2 lines per subtitle.
    """
    import re

    # Split on CJK sentence-ending punctuation
    parts = re.split(r"([。！？；])", text)

    # Rejoin punctuation with preceding text
    chunks: list[str] = []
    current = ""
    for part in parts:
        if re.match(r"^[。！？；]$", part):
            current += part
            if len(current) >= max_chars:
                chunks.append(current.strip())
                current = ""
        else:
            if current:
                if len(current) + len(part) > max_chars * 2:
                    chunks.append(current.strip())
                    current = part
                else:
                    current += part
            else:
                current = part

    if current.strip():
        chunks.append(current.strip())

    # Further split any chunk that's still too long
    result: list[str] = []
    for chunk in chunks:
        if len(chunk) <= max_chars * 2:
            result.append(chunk)
        else:
            # Split by comma or mid-point
            sub_parts = re.split(r"([，、])", chunk)
            sub_current = ""
            for sp in sub_parts:
                if len(sub_current) + len(sp) > max_chars * 2:
                    if sub_current.strip():
                        result.append(sub_current.strip())
                    sub_current = sp
                else:
                    sub_current += sp
            if sub_current.strip():
                result.append(sub_current.strip())

    return [r for r in result if r]


def _build_subtitle_entries(
    segment_timings: list[dict[str, Any]],
) -> list[SrtEntry]:
    """Build SRT entries from segment timings, splitting long text into chunks.

    Each subtitle shows max ~36 CJK characters (2 lines of ~18).
    Timing is distributed proportionally across chunks within each segment.
    """
    entries: list[SrtEntry] = []
    index = 1

    for t in segment_timings:
        text = t["text"]
        start_ms = t["start_ms"]
        duration_ms = t["duration_ms"]

        chunks = _split_text_for_subtitles(text, max_chars=18)
        if not chunks:
            continue

        # Distribute time proportionally by character count
        total_chars = sum(len(c) for c in chunks)
        if total_chars == 0:
            continue

        chunk_start = start_ms
        for chunk in chunks:
            proportion = len(chunk) / total_chars
            chunk_duration = int(duration_ms * proportion)
            chunk_end = chunk_start + chunk_duration

            entries.append(
                SrtEntry(
                    index=index,
                    start_ms=chunk_start,
                    end_ms=chunk_end,
                    text=chunk,
                )
            )
            index += 1
            chunk_start = chunk_end

    return entries


def _get_audio_duration_ms(path: Path) -> int:
    """Get audio duration in milliseconds using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return int(float(result.stdout.strip()) * 1000)
    except Exception:
        # Fallback: estimate from file size (~16kB/sec for edge-tts mp3)
        file_size = path.stat().st_size
        return max(int(file_size / 16 * 1000), 1000)


def _concatenate_audio(paths: list[Path], output: Path) -> None:
    """Concatenate MP3 files by simple binary append (sufficient for MP3)."""
    with open(output, "wb") as out:
        for p in paths:
            out.write(p.read_bytes())
